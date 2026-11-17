"""Crossref REST API discovery and DOI verification provider."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from bibcanon.core.normalizer import (
    clean_display_title,
    extract_arxiv_id_from_text,
    extract_doi_from_text,
)
from bibcanon.core.venue_dict import (
    get_canonical_venue_id,
    is_preprint_venue,
    is_workshop_venue,
    match_venue_entry,
)
from bibcanon.models import CandidateRecord, VenueTier
from bibcanon.providers.base import RateLimitedHttpClient


def _extract_crossref_year(item: dict[str, Any]) -> int | None:
    for date_key in ("published-print", "published-online", "published", "issued"):
        node = item.get(date_key)
        if isinstance(node, dict):
            parts = node.get("date-parts")
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                yr = parts[0][0]
                if isinstance(yr, int) and 1900 <= yr <= 2100:
                    return yr
    return None


def _classify_crossref_tier(cr_type: str, venue: str, doi: str | None) -> VenueTier:
    low_type = cr_type.lower()
    if low_type == "posted-content" or is_preprint_venue(venue):
        return "PREPRINT"
    if doi and doi.lower().startswith("10.48550/arxiv."):
        return "PREPRINT"
    if is_workshop_venue(venue):
        return "WORKSHOP"
    matched = match_venue_entry(venue)
    if matched:
        return matched.tier
    if low_type == "journal-article":
        return "JOURNAL"
    if low_type in {"proceedings-article", "book-chapter"}:
        return "MAIN_CONF"
    return "MAIN_CONF" if doi else "PREPRINT"


def parse_crossref_item(item: dict[str, Any]) -> CandidateRecord | None:
    """Convert a Crossref Works JSON item into a CandidateRecord."""
    titles = item.get("title") or []
    raw_title = str(titles[0]).strip() if isinstance(titles, list) and titles else ""
    if not raw_title:
        return None
    title = clean_display_title(raw_title)

    authors: list[str] = []
    for a in item.get("author") or []:
        if not isinstance(a, dict):
            continue
        given = str(a.get("given", "")).strip()
        family = str(a.get("family", "")).strip()
        full = f"{given} {family}".strip() if (given or family) else str(a.get("name", "")).strip()
        if full:
            authors.append(full)

    containers = item.get("container-title") or []
    venue = str(containers[0]).strip() if isinstance(containers, list) and containers else ""
    if not venue and isinstance(item.get("event"), dict):
        venue = str(item["event"].get("name", "")).strip()

    year = _extract_crossref_year(item)
    raw_doi = str(item.get("DOI", "")).strip()
    doi = extract_doi_from_text(raw_doi)
    arxiv_id = extract_arxiv_id_from_text(raw_doi)

    cr_type = str(item.get("type", "")).strip()
    tier = _classify_crossref_tier(cr_type, venue, doi)
    canonical_vid = get_canonical_venue_id(venue) if tier != "PREPRINT" else None

    ee_urls: list[str] = []
    if item.get("URL"):
        ee_urls.append(str(item["URL"]).strip())
    for link in item.get("link") or []:
        if isinstance(link, dict) and link.get("URL"):
            u = str(link["URL"]).strip()
            if u not in ee_urls:
                ee_urls.append(u)

    entry_type = "misc"
    if tier == "JOURNAL":
        entry_type = "article"
    elif tier in {"MAIN_CONF", "WORKSHOP"}:
        entry_type = "inproceedings"

    extra: dict[str, Any] = {"type": cr_type}
    for k in ("page", "article-number", "volume", "issue", "publisher"):
        if item.get(k):
            extra[k] = str(item[k]).strip()
    if venue:
        extra["container-title"] = venue
    if isinstance(item.get("ISBN"), list) and item["ISBN"]:
        extra["isbn"] = str(item["ISBN"][0]).strip()
    if isinstance(item.get("ISSN"), list) and item["ISSN"]:
        extra["issn"] = str(item["ISSN"][0]).strip()

    return CandidateRecord(
        source_discovery="crossref",
        venue_tier=tier,
        canonical_venue_id=canonical_vid,
        matched_title=title,
        matched_authors=authors,
        matched_year=year,
        matched_venue=venue or None,
        doi=doi,
        arxiv_id=arxiv_id,
        url=f"https://doi.org/{doi}" if doi else (ee_urls[0] if ee_urls else None),
        ee_urls=ee_urls,
        crossref_extra=extra,
        entry_type=entry_type,
    )


async def lookup_crossref_doi(
    client: RateLimitedHttpClient,
    doi: str,
) -> tuple[CandidateRecord | None, bool]:
    """Lookup a specific DOI in Crossref. Returns (candidate, is_404)."""
    clean_doi = extract_doi_from_text(doi)
    if not clean_doi:
        return None, False

    encoded = quote(clean_doi, safe="")
    params: dict[str, str | int] = {}
    if client.config.polite_email.strip():
        params["mailto"] = client.config.polite_email.strip()

    resp = await client.get(
        f"https://api.crossref.org/works/{encoded}",
        params=params or None,
        allow_404=True,
    )
    if resp.status_code == 404:
        return None, True
    if resp.status_code != 200:
        return None, False

    try:
        msg = resp.json().get("message", {})
        if isinstance(msg, dict):
            return parse_crossref_item(msg), False
    except Exception:
        pass
    return None, False


async def search_crossref(
    client: RateLimitedHttpClient,
    title: str,
    first_author: str | None = None,
    rows: int = 5,
) -> list[CandidateRecord]:
    """Query Crossref Works API by title and optional first author surname."""
    clean_t = clean_display_title(title)
    if not clean_t:
        return []

    query = f"{clean_t} {first_author}".strip() if first_author else clean_t
    params: dict[str, str | int] = {
        "query.bibliographic": query,
        "rows": rows,
    }
    if client.config.polite_email.strip():
        params["mailto"] = client.config.polite_email.strip()

    resp = await client.get("https://api.crossref.org/works", params=params)
    if resp.status_code != 200:
        return []

    try:
        items = resp.json().get("message", {}).get("items", [])
    except Exception:
        return []

    results: list[CandidateRecord] = []
    for item in items:
        if isinstance(item, dict):
            cand = parse_crossref_item(item)
            if cand is not None:
                results.append(cand)
    return results
