"""OpenAlex Works API discovery provider."""

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
from bibcanon.providers.base import RateLimitedHttpClient


def parse_openalex_work(work: dict[str, Any]) -> list[CandidateRecord]:
    """Parse an OpenAlex Work object, extracting published and preprint candidates from locations."""
    raw_title = str(work.get("title") or work.get("display_name") or "").strip()
    if not raw_title:
        return []
    title = clean_display_title(raw_title)

    authors: list[str] = []
    for auth in work.get("authorships") or []:
        if isinstance(auth, dict):
            author_obj = auth.get("author") or {}
            name = str(author_obj.get("display_name") or auth.get("raw_author_name") or "").strip()
            if name:
                authors.append(name)

    pub_year = work.get("publication_year")
    year = int(pub_year) if isinstance(pub_year, int) else None

    raw_doi = str(work.get("doi") or "").strip()
    doi = extract_doi_from_text(raw_doi)
    arxiv_id = extract_arxiv_id_from_text(raw_doi)

    ee_urls: list[str] = []
    published_venue = ""
    source_type = ""

    locations = work.get("locations") or []
    primary_loc = work.get("primary_location")
    all_locs = ([primary_loc] if isinstance(primary_loc, dict) else []) + [
        loc for loc in locations if isinstance(loc, dict)
    ]

    for loc in all_locs:
        for url_key in ("landing_page_url", "pdf_url"):
            u = str(loc.get(url_key) or "").strip()
            if u and u not in ee_urls:
                ee_urls.append(u)
                if not arxiv_id:
                    arxiv_id = extract_arxiv_id_from_text(u)
                if not doi:
                    doi = extract_doi_from_text(u)

        src = loc.get("source")
        if isinstance(src, dict):
            sname = str(src.get("display_name") or "").strip()
            stype = str(src.get("type") or "").strip().lower()
            if sname and not is_preprint_venue(sname) and stype != "repository":
                if not published_venue:
                    published_venue = sname
                    source_type = stype

    if not published_venue and isinstance(primary_loc, dict):
        src = primary_loc.get("source")
        if isinstance(src, dict):
            published_venue = str(src.get("display_name") or "").strip()
            source_type = str(src.get("type") or "").strip().lower()

    work_type = str(work.get("type") or "").strip().lower()

    tier: VenueTier = "PREPRINT"
    if published_venue and not is_preprint_venue(published_venue):
        if is_workshop_venue(published_venue):
            tier = "WORKSHOP"
        else:
            matched = match_venue_entry(published_venue)
            if matched:
                tier = matched.tier
            elif source_type == "journal":
                tier = "JOURNAL"
            elif source_type == "conference" or work_type == "proceedings-article":
                tier = "MAIN_CONF"
            elif doi:
                tier = "JOURNAL" if work_type == "article" else "MAIN_CONF"
    elif work_type == "preprint" or is_preprint_venue(published_venue):
        tier = "PREPRINT"
    elif doi:
        tier = "MAIN_CONF"

    canonical_vid = get_canonical_venue_id(published_venue) if tier != "PREPRINT" else None
    entry_type = (
        "article"
        if tier == "JOURNAL"
        else ("inproceedings" if tier in {"MAIN_CONF", "WORKSHOP"} else "misc")
    )

    biblio = work.get("biblio") if isinstance(work.get("biblio"), dict) else {}
    first_page = str(biblio.get("first_page") or "").strip()
    last_page = str(biblio.get("last_page") or "").strip()
    pages = f"{first_page}--{last_page}" if (first_page and last_page and first_page != last_page) else first_page

    extra: dict[str, Any] = {}
    if pages:
        extra["page"] = pages
    if biblio.get("volume"):
        extra["volume"] = str(biblio["volume"])
    if biblio.get("issue"):
        extra["issue"] = str(biblio["issue"])

    return [
        CandidateRecord(
            source_discovery="openalex",
            venue_tier=tier,
            canonical_venue_id=canonical_vid,
            matched_title=title,
            matched_authors=authors,
            matched_year=year,
            matched_venue=published_venue or None,
            doi=doi,
            arxiv_id=arxiv_id,
            url=f"https://doi.org/{doi}" if doi else (ee_urls[0] if ee_urls else None),
            ee_urls=ee_urls,
            crossref_extra=extra,
            entry_type=entry_type,
        )
    ]


async def search_openalex(
    client: RateLimitedHttpClient,
    title: str,
    per_page: int = 5,
) -> list[CandidateRecord]:
    """Query OpenAlex Works API by title."""
    clean_t = clean_display_title(title)
    if not clean_t:
        return []

    params: dict[str, str | int] = {"search": clean_t, "per-page": per_page}
    if client.config.openalex_api_key.strip():
        params["api_key"] = client.config.openalex_api_key.strip()
    elif client.config.polite_email.strip():
        params["mailto"] = client.config.polite_email.strip()

    resp = await client.get("https://api.openalex.org/works", params=params)
    if resp.status_code != 200:
        return []

    try:
        results_raw = resp.json().get("results", [])
    except Exception:
        return []

    candidates: list[CandidateRecord] = []
    for item in results_raw:
        if isinstance(item, dict):
            candidates.extend(parse_openalex_work(item))
    return candidates
