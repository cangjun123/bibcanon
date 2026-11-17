"""Optional Semantic Scholar Graph API discovery provider (gracefully degrades on 429)."""

from __future__ import annotations

from typing import Any

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
from bibcanon.providers.base import RateLimitedHttpClient, UpstreamNetworkError


def parse_s2_paper(paper: dict[str, Any]) -> CandidateRecord | None:
    """Parse a Semantic Scholar paper object into a CandidateRecord."""
    raw_title = str(paper.get("title") or "").strip()
    if not raw_title:
        return None
    title = clean_display_title(raw_title)

    authors: list[str] = []
    for a in paper.get("authors") or []:
        if isinstance(a, dict) and a.get("name"):
            authors.append(str(a["name"]).strip())

    year = paper.get("year")
    year_int = int(year) if isinstance(year, int) else None

    ext_ids = paper.get("externalIds") if isinstance(paper.get("externalIds"), dict) else {}
    doi = extract_doi_from_text(str(ext_ids.get("DOI") or ""))
    arxiv_id = extract_arxiv_id_from_text(str(ext_ids.get("ArXiv") or ""))

    pub_venue = paper.get("publicationVenue")
    venue = ""
    if isinstance(pub_venue, dict) and pub_venue.get("name"):
        venue = str(pub_venue["name"]).strip()
    if not venue and paper.get("venue"):
        venue = str(paper["venue"]).strip()

    ee_urls: list[str] = []
    oa_pdf = paper.get("openAccessPdf")
    if isinstance(oa_pdf, dict) and oa_pdf.get("url"):
        ee_urls.append(str(oa_pdf["url"]).strip())
    if paper.get("url"):
        ee_urls.append(str(paper["url"]).strip())

    tier: VenueTier = "PREPRINT"
    pub_types = [str(t).lower() for t in (paper.get("publicationTypes") or [])]
    if not venue or is_preprint_venue(venue):
        tier = "PREPRINT"
    elif is_workshop_venue(venue):
        tier = "WORKSHOP"
    else:
        matched = match_venue_entry(venue)
        if matched:
            tier = matched.tier
        elif "journalarticle" in pub_types:
            tier = "JOURNAL"
        elif "conference" in pub_types or doi:
            tier = "MAIN_CONF"

    canonical_vid = get_canonical_venue_id(venue) if tier != "PREPRINT" else None
    entry_type = (
        "article"
        if tier == "JOURNAL"
        else ("inproceedings" if tier in {"MAIN_CONF", "WORKSHOP"} else "misc")
    )

    return CandidateRecord(
        source_discovery="semantic_scholar",
        venue_tier=tier,
        canonical_venue_id=canonical_vid,
        matched_title=title,
        matched_authors=authors,
        matched_year=year_int,
        matched_venue=venue or None,
        doi=doi,
        arxiv_id=arxiv_id,
        url=f"https://doi.org/{doi}" if doi else (ee_urls[0] if ee_urls else None),
        ee_urls=ee_urls,
        entry_type=entry_type,
    )


async def search_semantic_scholar(
    client: RateLimitedHttpClient,
    title: str,
    limit: int = 5,
) -> list[CandidateRecord]:
    """Optional S2 lookup; silently returns [] on 429 or network error per SPEC.md 5.1."""
    clean_t = clean_display_title(title)
    if not clean_t:
        return []

    headers: dict[str, str] = {}
    if client.config.semantic_scholar_api_key.strip():
        headers["x-api-key"] = client.config.semantic_scholar_api_key.strip()

    try:
        resp = await client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": clean_t,
                "limit": limit,
                "fields": "title,authors,year,venue,publicationVenue,externalIds,publicationTypes,openAccessPdf,url",
            },
            headers=headers or None,
        )
    except UpstreamNetworkError:
        return []

    if resp.status_code != 200:
        return []

    try:
        items = resp.json().get("data", [])
    except Exception:
        return []

    results: list[CandidateRecord] = []
    for item in items:
        if isinstance(item, dict):
            cand = parse_s2_paper(item)
            if cand is not None:
                results.append(cand)
    return results
