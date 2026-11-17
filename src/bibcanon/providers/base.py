"""Rate-limited async HTTP client with per-domain semaphores, proxy, and backoff retries."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from bibcanon import __version__
from bibcanon.models import AppConfig


class UpstreamNetworkError(Exception):
    """Raised when an upstream service fails due to network error, timeout, or HTTP 5xx/429."""


@dataclass
class DomainPolicy:
    """Concurrency and rate-limiting policy for a specific upstream domain."""

    max_concurrency: int
    min_interval_sec: float
    no_retry_on_429: bool = False


class _DomainLimiter:
    """Async semaphore + minimum inter-request spacing per domain."""

    def __init__(self, policy: DomainPolicy) -> None:
        self.policy = policy
        self.semaphore = asyncio.Semaphore(policy.max_concurrency)
        self._lock = asyncio.Lock()
        self._next_allowed_time = 0.0

    async def wait_turn(self) -> None:
        if self.policy.min_interval_sec <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            if now < self._next_allowed_time:
                delay = self._next_allowed_time - now
                self._next_allowed_time += self.policy.min_interval_sec
            else:
                delay = 0.0
                self._next_allowed_time = now + self.policy.min_interval_sec
        if delay > 0:
            await asyncio.sleep(delay)


def _build_domain_policies(config: AppConfig) -> dict[str, DomainPolicy]:
    openalex_rps = 15.0 if config.openalex_api_key.strip() else 5.0
    return {
        "dblp.org": DomainPolicy(max_concurrency=2, min_interval_sec=0.5),
        "api.crossref.org": DomainPolicy(max_concurrency=3, min_interval_sec=0.2),
        "doi.org": DomainPolicy(max_concurrency=3, min_interval_sec=0.2),
        "dx.doi.org": DomainPolicy(max_concurrency=3, min_interval_sec=0.2),
        "api.openalex.org": DomainPolicy(
            max_concurrency=4, min_interval_sec=1.0 / openalex_rps
        ),
        "export.arxiv.org": DomainPolicy(max_concurrency=1, min_interval_sec=1.0),
        "arxiv.org": DomainPolicy(max_concurrency=1, min_interval_sec=1.0),
        "openaccess.thecvf.com": DomainPolicy(max_concurrency=3, min_interval_sec=1.0 / 3.0),
        "proceedings.mlr.press": DomainPolicy(max_concurrency=3, min_interval_sec=0.25),
        "mlr.press": DomainPolicy(max_concurrency=3, min_interval_sec=0.25),
        "api2.openreview.net": DomainPolicy(max_concurrency=2, min_interval_sec=1.0 / 3.0),
        "api.openreview.net": DomainPolicy(max_concurrency=2, min_interval_sec=1.0 / 3.0),
        "openreview.net": DomainPolicy(max_concurrency=2, min_interval_sec=1.0 / 3.0),
        "papers.nips.cc": DomainPolicy(max_concurrency=2, min_interval_sec=1.0 / 3.0),
        "proceedings.neurips.cc": DomainPolicy(max_concurrency=2, min_interval_sec=1.0 / 3.0),
        "aclanthology.org": DomainPolicy(max_concurrency=3, min_interval_sec=0.25),
        "api.semanticscholar.org": DomainPolicy(
            max_concurrency=1, min_interval_sec=1.0, no_retry_on_429=True
        ),
    }


class RateLimitedHttpClient:
    """Shared async HTTP client enforcing polite headers, per-domain rate limits, and retries."""

    def __init__(
        self,
        config: AppConfig | None = None,
        timeout_sec: float = 15.0,
        max_retries: int = 2,
        backoff_base: float = 1.0,
        enable_rate_sleep: bool = True,
    ) -> None:
        self.config = config or AppConfig()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.enable_rate_sleep = enable_rate_sleep

        email = self.config.polite_email.strip() or "opensource@bibcanon.local"
        self.user_agent = (
            f"bibcanon/{__version__} (Academic BibTeX Verifier; mailto:{email})"
        )
        self._policies = _build_domain_policies(self.config)
        self._default_policy = DomainPolicy(max_concurrency=3, min_interval_sec=0.2)
        self._limiters: dict[str, _DomainLimiter] = {}

        proxy = self.config.proxy_url.strip() or None
        self._client = httpx.AsyncClient(
            trust_env=True,
            follow_redirects=True,
            proxy=proxy,
            timeout=httpx.Timeout(timeout_sec),
            headers={"User-Agent": self.user_agent},
        )

    def _get_limiter(self, url: str) -> _DomainLimiter:
        host = (urlparse(url).hostname or "").lower()
        if host not in self._limiters:
            policy = self._policies.get(host, self._default_policy)
            if not self.enable_rate_sleep:
                policy = DomainPolicy(
                    max_concurrency=policy.max_concurrency,
                    min_interval_sec=0.0,
                    no_retry_on_429=policy.no_retry_on_429,
                )
            self._limiters[host] = _DomainLimiter(policy)
        return self._limiters[host]

    async def get(
        self,
        url: str,
        *,
        params: dict[str, str | int] | None = None,
        headers: dict[str, str] | None = None,
        allow_404: bool = False,
    ) -> httpx.Response:
        """Perform a rate-limited GET request with exponential backoff on transient errors."""
        limiter = self._get_limiter(url)
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with limiter.semaphore:
                    await limiter.wait_turn()
                    resp = await self._client.get(url, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < self.max_retries and self.backoff_base > 0:
                    await asyncio.sleep(self.backoff_base * (2**attempt))
                    continue
                if attempt < self.max_retries:
                    continue
                raise UpstreamNetworkError(f"Network error contacting {url}: {exc}") from exc

            if resp.status_code == 404 and allow_404:
                return resp

            if resp.status_code in {429, 500, 502, 503, 504}:
                if resp.status_code == 429 and limiter.policy.no_retry_on_429:
                    raise UpstreamNetworkError(f"Rate limited (429) by {url}")
                if attempt < self.max_retries:
                    wait_sec = self.backoff_base * (2**attempt)
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            ra_val = float(retry_after)
                            if 0 <= ra_val <= 10.0 and self.backoff_base > 0:
                                wait_sec = ra_val
                        except ValueError:
                            pass
                    if wait_sec > 0:
                        await asyncio.sleep(wait_sec)
                    continue
                raise UpstreamNetworkError(
                    f"Upstream HTTP {resp.status_code} from {url}"
                )

            return resp

        raise UpstreamNetworkError(f"Exhausted retries contacting {url}: {last_exc}")

    async def aclose(self) -> None:
        """Close the underlying httpx.AsyncClient."""
        await self._client.aclose()

    async def __aenter__(self) -> RateLimitedHttpClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()
