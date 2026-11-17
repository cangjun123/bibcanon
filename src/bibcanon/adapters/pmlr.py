"""PMLR official BibTeX adapter (ICML / AISTATS / CoRL / COLT / ACML)."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from bibcanon.core.bib_parser import parse_single_bibtex_block
from bibcanon.core.formatter import sanitize_publisher_fields
from bibcanon.models import CandidateRecord
from bibcanon.providers.base import RateLimitedHttpClient, UpstreamNetworkError


def _resolve_pmlr_html_url(cand: CandidateRecord) -> str | None:
    all_urls = list(cand.ee_urls) + ([cand.url] if cand.url else [])
    for u in all_urls:
        low = u.lower()
        if "proceedings.mlr.press" not in low and "mlr.press" not in low:
            continue
        if low.endswith(".html"):
            return u
        # Convert https://proceedings.mlr.press/v235/foo24a/foo24a.pdf -> .../v235/foo24a.html
        m = re.match(r"^(https?://(?:proceedings\.)?mlr\.press/v\d+/[^/]+)/[^/]+\.pdf$", u, re.I)
        if m:
            return f"{m.group(1)}.html"
        if not low.endswith(".pdf"):
            return u.rstrip("/") + ".html" if not u.endswith("/") else u
    return None


async def fetch_pmlr_bibtex(
    client: RateLimitedHttpClient,
    cand: CandidateRecord,
    noise_blacklist: list[str] | None = None,
) -> tuple[str, str, dict[str, str]] | None:
    """Fetch official PMLR @InProceedings BibTeX from #bibtex node."""
    page_url = _resolve_pmlr_html_url(cand)
    if not page_url:
        return None

    try:
        resp = await client.get(page_url, allow_404=True)
    except UpstreamNetworkError:
        return None

    if resp.status_code != 200:
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    bib_el = soup.select_one("#bibtex")
    if bib_el is None:
        for el in soup.find_all(["code", "pre", "div"]):
            txt = el.get_text(" ", strip=True)
            if "@inproceedings" in txt.lower():
                bib_el = el
                break

    if bib_el is None:
        return None

    raw_bib = bib_el.get_text()
    if "@" not in raw_bib:
        return None

    etype, _, raw_fields = parse_single_bibtex_block(raw_bib)
    cleaned = sanitize_publisher_fields(raw_fields, noise_blacklist=noise_blacklist)
    if not cleaned.get("title"):
        return None

    return "PMLR Official", etype, cleaned
