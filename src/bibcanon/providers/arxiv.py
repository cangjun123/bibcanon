"""arXiv Query API discovery provider and official @misc BibTeX adapter."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from bibcanon.core.bib_parser import parse_single_bibtex_block
from bibcanon.core.formatter import sanitize_publisher_fields
from bibcanon.core.normalizer import (
    clean_display_title,
    extract_arxiv_id_from_text,
    extract_doi_from_text,
)
from bibcanon.core.venue_dict import get_canonical_venue_id, is_workshop_venue, match_venue_entry
from bibcanon.models import CandidateRecord
from bibcanon.providers.base import RateLimitedHttpClient

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _parse_arxiv_atom_feed(xml_text: str) -> list[CandidateRecord]:
    """Parse Atom XML returned by export.arxiv.org/api/query."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    records: list[CandidateRecord] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        id_text = (entry.findtext("atom:id", default="", namespaces=_ATOM_NS) or "").strip()
        raw_title = (entry.findtext("atom:title", default="", namespaces=_ATOM_NS) or "").strip()
        # arXiv returns an error entry with title "Error" when id_list is malformed
        if not raw_title or raw_title.lower() == "error":
            continue
        title = clean_display_title(re.sub(r"\s+", " ", raw_title))
        arxiv_id = extract_arxiv_id_from_text(id_text)
        if not arxiv_id:
            continue

        authors: list[str] = []
        for author_el in entry.findall("atom:author", _ATOM_NS):
            name = (author_el.findtext("atom:name", default="", namespaces=_ATOM_NS) or "").strip()
            if name:
                authors.append(name)

        published = (entry.findtext("atom:published", default="", namespaces=_ATOM_NS) or "").strip()
        year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None

        primary_cat_el = entry.find("arxiv:primary_category", _ATOM_NS)
        primary_class = (
            primary_cat_el.attrib.get("term", "").strip()
            if primary_cat_el is not None
            else ""
        )

        arxiv_doi_raw = (
            entry.findtext("arxiv:doi", default="", namespaces=_ATOM_NS) or ""
        ).strip()
        journal_ref = (
            entry.findtext("arxiv:journal_ref", default="", namespaces=_ATOM_NS) or ""
        ).strip()
        pub_doi = extract_doi_from_text(arxiv_doi_raw)

        abs_url = f"https://arxiv.org/abs/{arxiv_id}"
        preprint_fields: dict[str, str] = {
            "title": title,
            "author": " and ".join(authors),
            "year": str(year) if year else "",
            "eprint": arxiv_id,
            "archivePrefix": "arXiv",
            "url": abs_url,
        }
        if primary_class:
            preprint_fields["primaryClass"] = primary_class

        records.append(
            CandidateRecord(
                source_discovery="arxiv",
                bibtex_origin="arXiv Official",
                venue_tier="PREPRINT",
                canonical_venue_id=None,
                matched_title=title,
                matched_authors=authors,
                matched_year=year,
                matched_venue=f"arXiv:{arxiv_id}",
                doi=None,
                arxiv_id=arxiv_id,
                url=abs_url,
                ee_urls=[abs_url],
                crossref_extra={"primaryClass": primary_class} if primary_class else {},
                entry_type="misc",
                raw_publisher_fields={k: v for k, v in preprint_fields.items() if v},
            )
        )

        # If arXiv entry explicitly carries a formal published DOI or journal_ref, also emit a clue candidate
        if pub_doi or journal_ref:
            tier = "MAIN_CONF"
            if journal_ref:
                if is_workshop_venue(journal_ref):
                    tier = "WORKSHOP"
                else:
                    mv = match_venue_entry(journal_ref)
                    if mv:
                        tier = mv.tier
            records.append(
                CandidateRecord(
                    source_discovery="arxiv",
                    venue_tier=tier,
                    canonical_venue_id=get_canonical_venue_id(journal_ref) if journal_ref else None,
                    matched_title=title,
                    matched_authors=authors,
                    matched_year=year,
                    matched_venue=journal_ref or None,
                    doi=pub_doi,
                    arxiv_id=arxiv_id,
                    url=f"https://doi.org/{pub_doi}" if pub_doi else abs_url,
                    ee_urls=[f"https://doi.org/{pub_doi}"] if pub_doi else [],
                    entry_type="article" if tier == "JOURNAL" else "inproceedings",
                )
            )

    return records


async def lookup_arxiv_by_id(
    client: RateLimitedHttpClient,
    arxiv_id: str,
) -> tuple[list[CandidateRecord], bool]:
    """Lookup a specific arXiv ID. Returns (candidates, is_invalid_id)."""
    clean_id = extract_arxiv_id_from_text(arxiv_id) or arxiv_id.strip()
    if not clean_id:
        return [], False

    resp = await client.get(
        "https://export.arxiv.org/api/query",
        params={"id_list": clean_id},
        allow_404=True,
    )
    if resp.status_code in {400, 404}:
        return [], True
    if resp.status_code != 200:
        return [], False

    cands = _parse_arxiv_atom_feed(resp.text)
    if not cands:
        return [], True
    return cands, False


async def search_arxiv_by_title(
    client: RateLimitedHttpClient,
    title: str,
    max_results: int = 5,
) -> list[CandidateRecord]:
    """Search arXiv API by exact/phrase title."""
    clean_t = clean_display_title(title)
    if not clean_t:
        return []
    # Strip double quotes inside query phrase
    safe_t = clean_t.replace('"', " ").strip()
    resp = await client.get(
        "https://export.arxiv.org/api/query",
        params={"search_query": f'ti:"{safe_t}"', "max_results": max_results},
    )
    if resp.status_code != 200:
        return []
    return _parse_arxiv_atom_feed(resp.text)


async def fetch_arxiv_official_bibtex(
    client: RateLimitedHttpClient,
    arxiv_id: str,
    fallback_fields: dict[str, str] | None = None,
    noise_blacklist: list[str] | None = None,
) -> tuple[str, dict[str, str]] | None:
    """Fetch official @misc BibTeX from https://arxiv.org/bibtex/{arxiv_id} (Adapter 6)."""
    clean_id = extract_arxiv_id_from_text(arxiv_id) or arxiv_id.strip()
    if not clean_id:
        return None

    resp = await client.get(f"https://arxiv.org/bibtex/{clean_id}", allow_404=True)
    if resp.status_code == 200 and "@" in resp.text:
        _, _, raw_fields = parse_single_bibtex_block(resp.text)
        cleaned = sanitize_publisher_fields(raw_fields, noise_blacklist=noise_blacklist)
        if cleaned.get("title"):
            cleaned.setdefault("eprint", clean_id)
            cleaned.setdefault("archivePrefix", "arXiv")
            cleaned.setdefault("url", f"https://arxiv.org/abs/{clean_id}")
            return "misc", cleaned

    if fallback_fields and fallback_fields.get("title"):
        fb = dict(fallback_fields)
        fb.setdefault("eprint", clean_id)
        fb.setdefault("archivePrefix", "arXiv")
        fb.setdefault("url", f"https://arxiv.org/abs/{clean_id}")
        return "misc", fb

    return None
