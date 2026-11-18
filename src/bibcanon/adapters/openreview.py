"""OpenReview API (v2 & v1) and NeurIPS Proceedings official BibTeX adapter."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from bibcanon.core.bib_parser import parse_single_bibtex_block
from bibcanon.core.formatter import sanitize_publisher_fields
from bibcanon.models import CandidateRecord
from bibcanon.providers.base import RateLimitedHttpClient, UpstreamNetworkError

_REJECTED_VENUE_RE = re.compile(
    r"\b(?:submitted\s+to|rejected|withdrawn|desk\s+reject)", re.IGNORECASE
)


def _extract_openreview_note_id(cand: CandidateRecord) -> str | None:
    all_urls = list(cand.ee_urls) + ([cand.url] if cand.url else [])
    for u in all_urls:
        if "openreview.net" not in u.lower():
            continue
        parsed = urlparse(u)
        qs = parse_qs(parsed.query)
        if "id" in qs and qs["id"]:
            return qs["id"][0].strip()
    return None


def _extract_neurips_url(cand: CandidateRecord) -> str | None:
    all_urls = list(cand.ee_urls) + ([cand.url] if cand.url else [])
    for u in all_urls:
        low = u.lower()
        if "papers.nips.cc" in low or "proceedings.neurips.cc" in low:
            return u
    return None


async def _fetch_neurips_proceedings_bib(
    client: RateLimitedHttpClient,
    nips_url: str,
    noise_blacklist: list[str] | None = None,
) -> tuple[str, str, dict[str, str]] | None:
    try:
        low_url = nips_url.lower()
        if low_url.endswith(".bib"):
            bib_resp = await client.get(nips_url, allow_404=True)
            if bib_resp.status_code == 200 and "@" in bib_resp.text:
                etype, _, raw_fields = parse_single_bibtex_block(bib_resp.text)
                cleaned = sanitize_publisher_fields(raw_fields, noise_blacklist=noise_blacklist)
                if cleaned.get("title"):
                    return "NeurIPS Proceedings", etype, cleaned
            return None

        # Convert direct NeurIPS PDF URLs (e.g. .../file/<hash>-Paper-Conference.pdf or -Paper.pdf)
        # straight to their sibling -Bibtex*.bib URL without downloading multi-MB PDFs!
        if low_url.endswith(".pdf") and "/file/" in low_url:
            direct_bib_candidates = [
                re.sub(r"-Paper(-[^/.]+)?\.pdf$", r"-Bibtex\1.bib", nips_url, flags=re.I),
                re.sub(r"-Paper(-[^/.]+)?\.pdf$", "-Bibtex.bib", nips_url, flags=re.I),
            ]
            for cand_bib_url in dict.fromkeys(direct_bib_candidates):
                if cand_bib_url != nips_url:
                    bib_resp = await client.get(cand_bib_url, allow_404=True)
                    if bib_resp.status_code == 200 and "@" in bib_resp.text:
                        etype, _, raw_fields = parse_single_bibtex_block(bib_resp.text)
                        cleaned = sanitize_publisher_fields(
                            raw_fields, noise_blacklist=noise_blacklist
                        )
                        if cleaned.get("title"):
                            return "NeurIPS Proceedings", etype, cleaned

            # Fallback to corresponding /hash/<hash>-Abstract*.html page instead of fetching PDF
            nips_url = re.sub(
                r"/file/([a-f0-9]+)-Paper(-[^/.]+)?\.pdf$",
                r"/hash/\1-Abstract\2.html",
                nips_url,
                flags=re.I,
            )
            if nips_url.lower().endswith(".pdf"):
                return None

        page_resp = await client.get(nips_url, allow_404=True)
        if page_resp.status_code != 200:
            return None

        soup = BeautifulSoup(page_resp.text, "lxml")
        bib_href: str | None = None
        for a_el in soup.find_all("a", href=True):
            href = str(a_el["href"]).strip()
            label = a_el.get_text(" ", strip=True).lower()
            if href.lower().endswith(".bib") or "bibtex" in label or "-bibtex" in href.lower():
                bib_href = urljoin(nips_url, href)
                break

        if not bib_href:
            return None

        bib_resp = await client.get(bib_href, allow_404=True)
        if bib_resp.status_code != 200 or "@" not in bib_resp.text:
            return None

        etype, _, raw_fields = parse_single_bibtex_block(bib_resp.text)
        cleaned = sanitize_publisher_fields(raw_fields, noise_blacklist=noise_blacklist)
        if not cleaned.get("title"):
            return None
        return "NeurIPS Proceedings", etype, cleaned
    except UpstreamNetworkError:
        return None


async def _fetch_openreview_api_bib(
    client: RateLimitedHttpClient,
    note_id: str,
    noise_blacklist: list[str] | None = None,
) -> tuple[str, str, dict[str, str]] | None:
    # Step 1: OpenReview API v2
    try:
        resp_v2 = await client.get(
            "https://api2.openreview.net/notes",
            params={"id": note_id},
            allow_404=True,
        )
        if resp_v2.status_code == 200:
            notes = resp_v2.json().get("notes", [])
            if notes and isinstance(notes[0], dict):
                content = notes[0].get("content") or {}
                venue_node = content.get("venue")
                venue_val = (
                    str(venue_node.get("value", ""))
                    if isinstance(venue_node, dict)
                    else str(venue_node or "")
                )
                if not _REJECTED_VENUE_RE.search(venue_val):
                    bib_node = content.get("_bibtex")
                    raw_bib = (
                        str(bib_node.get("value", ""))
                        if isinstance(bib_node, dict)
                        else str(bib_node or "")
                    )
                    if "@" in raw_bib:
                        etype, _, raw_fields = parse_single_bibtex_block(raw_bib)
                        cleaned = sanitize_publisher_fields(
                            raw_fields, noise_blacklist=noise_blacklist
                        )
                        if cleaned.get("title"):
                            return "OpenReview Official", etype, cleaned
    except (UpstreamNetworkError, ValueError):
        pass

    # Step 2: OpenReview API v1 fallback
    try:
        resp_v1 = await client.get(
            "https://api.openreview.net/notes",
            params={"id": note_id},
            allow_404=True,
        )
        if resp_v1.status_code == 200:
            notes = resp_v1.json().get("notes", [])
            if notes and isinstance(notes[0], dict):
                content = notes[0].get("content") or {}
                venue_val = str(content.get("venue") or "")
                if not _REJECTED_VENUE_RE.search(venue_val):
                    raw_bib = str(content.get("_bibtex") or "")
                    if "@" in raw_bib:
                        etype, _, raw_fields = parse_single_bibtex_block(raw_bib)
                        cleaned = sanitize_publisher_fields(
                            raw_fields, noise_blacklist=noise_blacklist
                        )
                        if cleaned.get("title"):
                            return "OpenReview Official", etype, cleaned
    except (UpstreamNetworkError, ValueError):
        pass

    return None


async def fetch_openreview_or_neurips_bibtex(
    client: RateLimitedHttpClient,
    cand: CandidateRecord,
    noise_blacklist: list[str] | None = None,
) -> tuple[str, str, dict[str, str]] | None:
    """Extract official BibTeX from NeurIPS Proceedings or OpenReview API v2/v1."""
    nips_url = _extract_neurips_url(cand)
    if nips_url:
        res = await _fetch_neurips_proceedings_bib(
            client, nips_url, noise_blacklist=noise_blacklist
        )
        if res is not None:
            return res

    note_id = _extract_openreview_note_id(cand)
    if note_id:
        return await _fetch_openreview_api_bib(
            client, note_id, noise_blacklist=noise_blacklist
        )

    return None
