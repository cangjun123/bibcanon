"""DBLP Search API discovery provider and DBLP curated .bib fallback fetcher."""

from __future__ import annotations

import re
from typing import Any

from bibcanon.core.bib_parser import parse_single_bibtex_block
from bibcanon.core.formatter import sanitize_publisher_fields
from bibcanon.core.normalizer import (
    clean_display_title,
    extract_arxiv_id_from_text,
    extract_doi_from_text,
    strip_dblp_author_number,
)
from bibcanon.core.venue_dict import (
    get_canonical_venue_id,
    is_preprint_venue,
    is_workshop_venue,
    match_venue_entry,
)
from bibcanon.models import CandidateRecord, VenueTier
from bibcanon.providers.base import RateLimitedHttpClient

_DBLP_BIB_AUTHOR_NUM_RE = re.compile(r"\s+\d{4}(?=\s+and\b|\s*$)", re.IGNORECASE)


def _classify_dblp_tier(
    venue_str: str,
    dblp_type: str,
    doi: str | None,
) -> VenueTier:
    if not venue_str and dblp_type == "Informal and Other Publications":
        return "PREPRINT"
    if venue_str.strip().lower() == "corr" or is_preprint_venue(venue_str):
        return "PREPRINT"
    if dblp_type == "Informal and Other Publications":
        return "PREPRINT"
    if is_workshop_venue(venue_str):
        return "WORKSHOP"
    matched = match_venue_entry(venue_str)
    if matched:
        return matched.tier
    if dblp_type == "Journal Articles":
        return "JOURNAL"
    if dblp_type == "Conference and Workshop Papers":
        return "MAIN_CONF"
    if doi:
        return "MAIN_CONF"
    return "PREPRINT"


def parse_dblp_hit(info: dict[str, Any]) -> CandidateRecord | None:
    """Parse a single DBLP `hit['info']` object handling single-vs-list pitfalls."""
    raw_title = str(info.get("title", "")).strip()
    if not raw_title:
        return None
    title = clean_display_title(raw_title)

    # Pitfall 1: single author is a dict, multiple authors is a list[dict]
    authors_container = info.get("authors", {})
    raw_authors_node = (
        authors_container.get("author", []) if isinstance(authors_container, dict) else []
    )
    if isinstance(raw_authors_node, dict):
        raw_authors_list = [raw_authors_node]
    elif isinstance(raw_authors_node, str):
        raw_authors_list = [raw_authors_node]
    elif isinstance(raw_authors_node, list):
        raw_authors_list = raw_authors_node
    else:
        raw_authors_list = []

    authors: list[str] = []
    for item in raw_authors_list:
        if isinstance(item, dict):
            name = str(item.get("text", "")).strip()
        else:
            name = str(item).strip()
        # Pitfall 3: strip 4-digit DBLP homonym disambiguation suffix
        cleaned_name = strip_dblp_author_number(name)
        if cleaned_name:
            authors.append(cleaned_name)

    # Pitfall 2: `ee` can be str or list[str]
    raw_ee = info.get("ee", [])
    if isinstance(raw_ee, str):
        ee_urls = [raw_ee.strip()] if raw_ee.strip() else []
    elif isinstance(raw_ee, list):
        ee_urls = [str(u).strip() for u in raw_ee if str(u).strip()]
    else:
        ee_urls = []

    raw_venue = info.get("venue", "")
    if isinstance(raw_venue, list):
        venue_str = " / ".join(str(v).strip() for v in raw_venue if str(v).strip())
    else:
        venue_str = str(raw_venue).strip()

    year_raw = str(info.get("year", "")).strip()
    year = int(year_raw) if year_raw.isdigit() else None

    doi = extract_doi_from_text(str(info.get("doi", "")))
    if not doi:
        for u in ee_urls:
            doi = extract_doi_from_text(u)
            if doi:
                break

    arxiv_id: str | None = None
    if venue_str.lower() == "corr":
        arxiv_id = extract_arxiv_id_from_text(str(info.get("volume", "")))
    if not arxiv_id:
        for u in ee_urls:
            arxiv_id = extract_arxiv_id_from_text(u)
            if arxiv_id:
                break

    dblp_type = str(info.get("type", "")).strip()
    dblp_key = str(info.get("key", "")).strip() or None
    tier = _classify_dblp_tier(venue_str, dblp_type, doi)
    canonical_vid = get_canonical_venue_id(venue_str) if tier != "PREPRINT" else None

    entry_type = "misc"
    if tier == "JOURNAL":
        entry_type = "article"
    elif tier in {"MAIN_CONF", "WORKSHOP"}:
        entry_type = "inproceedings"

    return CandidateRecord(
        source_discovery="dblp",
        venue_tier=tier,
        canonical_venue_id=canonical_vid,
        matched_title=title,
        matched_authors=authors,
        matched_year=year,
        matched_venue=venue_str or None,
        doi=doi,
        arxiv_id=arxiv_id,
        url=ee_urls[0] if ee_urls else (str(info.get("url", "")) or None),
        ee_urls=ee_urls,
        dblp_key=dblp_key,
        dblp_type=dblp_type or None,
        crossref_extra={
            k: str(info[k])
            for k in ("pages", "volume", "number")
            if info.get(k) is not None and str(info.get(k)).strip()
        },
        entry_type=entry_type,
    )


async def search_dblp(
    client: RateLimitedHttpClient,
    title: str,
    max_hits: int = 10,
) -> list[CandidateRecord]:
    """Query DBLP Search API by clean paper title."""
    clean_t = clean_display_title(title)
    if not clean_t:
        return []

    resp = await client.get(
        "https://dblp.org/search/publ/api",
        params={"q": clean_t, "h": max_hits, "format": "json"},
    )
    if resp.status_code != 200:
        return []

    try:
        data = resp.json()
    except Exception:
        return []

    hits_node = data.get("result", {}).get("hits", {}).get("hit", [])
    if isinstance(hits_node, dict):
        hits_list = [hits_node]
    elif isinstance(hits_node, list):
        hits_list = hits_node
    else:
        hits_list = []

    results: list[CandidateRecord] = []
    for hit in hits_list:
        if not isinstance(hit, dict):
            continue
        info = hit.get("info")
        if isinstance(info, dict):
            cand = parse_dblp_hit(info)
            if cand is not None:
                results.append(cand)
    return results


def clean_dblp_bibtex_fields(raw_fields: dict[str, str], noise_blacklist: list[str] | None = None) -> dict[str, str]:
    """Strip DBLP noise fields, 4-digit author disambiguation numbers, and trailing title period."""
    fields = sanitize_publisher_fields(raw_fields, noise_blacklist=noise_blacklist)
    for person_key in ("author", "editor"):
        if person_key in fields:
            fields[person_key] = _DBLP_BIB_AUTHOR_NUM_RE.sub("", fields[person_key]).strip()
    if "title" in fields:
        t = fields["title"].strip()
        if t.endswith(".") and not t.endswith("..."):
            fields["title"] = t[:-1].rstrip()
    return fields


async def fetch_dblp_bibtex(
    client: RateLimitedHttpClient,
    dblp_key: str,
    noise_blacklist: list[str] | None = None,
) -> tuple[str, dict[str, str]] | None:
    """Fetch and sanitize official DBLP .bib entry as universal fallback (Adapter 7)."""
    if not dblp_key:
        return None
    url = f"https://dblp.org/rec/{dblp_key}.bib"
    resp = await client.get(url, params={"param": "1"}, allow_404=True)
    if resp.status_code != 200 or "@" not in resp.text:
        return None

    etype, _, raw_fields = parse_single_bibtex_block(resp.text)
    cleaned = clean_dblp_bibtex_fields(raw_fields, noise_blacklist=noise_blacklist)
    if not cleaned.get("title"):
        return None
    return etype, cleaned
