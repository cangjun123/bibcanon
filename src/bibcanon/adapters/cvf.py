"""CVF Open Access adapter (CVPR / ICCV / WACV) with local SQLite ToC caching."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from bibcanon.core.bib_parser import parse_single_bibtex_block
from bibcanon.core.formatter import sanitize_publisher_fields
from bibcanon.core.normalizer import normalize_title
from bibcanon.models import CandidateRecord
from bibcanon.providers.base import RateLimitedHttpClient, UpstreamNetworkError
from bibcanon.storage.cache import BibCache

_CVF_VENUES = {"CVPR", "ICCV", "WACV"}


def _extract_bibtex_from_cvf_html(html_text: str) -> str | None:
    """Extract raw @InProceedings BibTeX block from a CVF paper detail HTML page."""
    soup = BeautifulSoup(html_text, "lxml")

    node = soup.select_one("div.bibref")
    if node is None:
        node = soup.select_one('div[id^="bibtex"]')
    if node is None:
        for pre in soup.find_all(["pre", "div"]):
            txt = pre.get_text(" ", strip=True)
            if "@inproceedings" in txt.lower() or "@article" in txt.lower():
                node = pre
                break

    if node is None:
        return None

    for br in node.find_all("br"):
        br.replace_with("\n")

    raw_bib = node.get_text()
    if "@" not in raw_bib:
        return None
    return raw_bib.strip()


def _parse_cvf_toc_html(html_text: str, base_url: str) -> list[tuple[str, str, str]]:
    """Extract (norm_title, raw_title, full_paper_url) tuples from CVF proceedings ToC HTML."""
    soup = BeautifulSoup(html_text, "lxml")
    items: list[tuple[str, str, str]] = []
    for dt_el in soup.select("dt.ptitle"):
        a_el = dt_el.find("a", href=True)
        if not a_el:
            continue
        raw_t = re.sub(r"\s+", " ", a_el.get_text(" ", strip=True)).strip()
        norm_t = normalize_title(raw_t)
        href = str(a_el["href"]).strip()
        if not norm_t or not href:
            continue
        full_url = urljoin(base_url, href)
        items.append((norm_t, raw_t, full_url))
    return items


async def _ensure_cvf_toc_cached(
    client: RateLimitedHttpClient,
    cache: BibCache,
    venue: str,
    year: int,
) -> None:
    if cache.has_cvf_toc(venue, year, ttl_days=client.config.cache_ttl_days):
        return

    base_index_url = f"https://openaccess.thecvf.com/{venue.upper()}{year}"
    resp = await client.get(f"{base_index_url}?day=all", allow_404=True)
    items: list[tuple[str, str, str]] = []

    if resp.status_code == 200:
        items = _parse_cvf_toc_html(resp.text, base_index_url)

    # Older CVF proceedings (e.g., 2018-2020) sometimes list per-day links on the main page
    if not items:
        main_resp = await client.get(base_index_url, allow_404=True)
        if main_resp.status_code == 200:
            items = _parse_cvf_toc_html(main_resp.text, base_index_url)
            if not items:
                soup = BeautifulSoup(main_resp.text, "lxml")
                day_urls: list[str] = []
                for a_el in soup.find_all("a", href=True):
                    href = str(a_el["href"])
                    if "day=" in href and "day=all" not in href:
                        full_day = urljoin(base_index_url, href)
                        if full_day not in day_urls:
                            day_urls.append(full_day)
                for d_url in day_urls[:6]:
                    d_resp = await client.get(d_url, allow_404=True)
                    if d_resp.status_code == 200:
                        items.extend(_parse_cvf_toc_html(d_resp.text, d_url))

    if items:
        cache.save_cvf_toc(venue, year, items)


def _find_direct_cvf_html_url(cand: CandidateRecord) -> str | None:
    all_urls = list(cand.ee_urls) + ([cand.url] if cand.url else [])
    for u in all_urls:
        if "openaccess.thecvf.com" not in u.lower():
            continue
        if u.lower().endswith(".html"):
            return u
        if u.lower().endswith(".pdf") and "/papers/" in u:
            return u.replace("/papers/", "/html/")[:-4] + ".html"
    return None


async def fetch_cvf_bibtex(
    client: RateLimitedHttpClient,
    cand: CandidateRecord,
    cache: BibCache | None = None,
    noise_blacklist: list[str] | None = None,
) -> tuple[str, str, dict[str, str]] | None:
    """Attempt to extract official CVF Open Access BibTeX for CVPR/ICCV/WACV papers."""
    detail_url = _find_direct_cvf_html_url(cand)

    if (
        not detail_url
        and cache is not None
        and cand.canonical_venue_id in _CVF_VENUES
        and cand.venue_tier == "MAIN_CONF"
        and cand.matched_year
    ):
        try:
            await _ensure_cvf_toc_cached(
                client, cache, cand.canonical_venue_id, cand.matched_year
            )
            detail_url = cache.lookup_cvf_paper_url(
                cand.canonical_venue_id,
                cand.matched_year,
                normalize_title(cand.matched_title),
            )
        except UpstreamNetworkError:
            detail_url = None

    if not detail_url:
        return None

    try:
        resp = await client.get(detail_url, allow_404=True)
    except UpstreamNetworkError:
        return None

    if resp.status_code != 200:
        return None

    raw_bib = _extract_bibtex_from_cvf_html(resp.text)
    if not raw_bib:
        return None

    etype, _, raw_fields = parse_single_bibtex_block(raw_bib)
    cleaned = sanitize_publisher_fields(raw_fields, noise_blacklist=noise_blacklist)
    if not cleaned.get("title"):
        return None

    return "CVF Open Access", etype, cleaned
