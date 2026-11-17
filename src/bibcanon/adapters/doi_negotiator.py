"""DOI Content Negotiation adapter with Crossref/DBLP structural defect repair."""

from __future__ import annotations

import html
import re
from urllib.parse import quote, unquote

from bibcanon.core.bib_parser import parse_single_bibtex_block
from bibcanon.core.formatter import sanitize_publisher_fields
from bibcanon.core.normalizer import extract_doi_from_text
from bibcanon.core.venue_dict import get_canonical_venue_id
from bibcanon.models import CandidateRecord
from bibcanon.providers.base import RateLimitedHttpClient, UpstreamNetworkError

_DOI_PUBLISHER_LABELS: tuple[tuple[str, str], ...] = (
    ("10.1109/", "DOI Official (IEEE)"),
    ("10.1145/", "DOI Official (ACM)"),
    ("10.1007/", "DOI Official (Springer)"),
    ("10.1609/", "DOI Official (AAAI)"),
    ("10.1016/", "DOI Official (Elsevier)"),
    ("10.1038/", "DOI Official (Nature)"),
    ("10.1126/", "DOI Official (Science)"),
    ("10.1137/", "DOI Official (SIAM)"),
    ("10.1162/", "DOI Official (MIT Press)"),
    ("10.18653/", "DOI Official (ACL)"),
    ("10.24963/", "DOI Official (IJCAI)"),
)


def label_doi_origin(doi: str) -> str:
    """Map a DOI prefix to a descriptive publisher origin badge."""
    low = doi.lower().strip()
    for prefix, label in _DOI_PUBLISHER_LABELS:
        if low.startswith(prefix):
            return label
    return "DOI Official"


def _is_springer_conference_chapter(
    etype: str,
    fields: dict[str, str],
    cand: CandidateRecord,
) -> bool:
    """Detect Springer LNCS / conference proceedings chapters mis-typed as @inbook by Crossref."""
    if etype not in {"inbook", "incollection"}:
        return False
    if cand.dblp_type == "Conference and Workshop Papers":
        return True
    if cand.venue_tier in {"MAIN_CONF", "WORKSHOP"}:
        return True
    booktitle = fields.get("booktitle", "")
    series = fields.get("series", "")
    if re.search(
        r"lecture\s+notes|lncs|lnai|conference|symposium|workshop|proceedings|eccv|miccai|accv|icann",
        f"{booktitle} {series}",
        re.IGNORECASE,
    ):
        return True
    if get_canonical_venue_id(booktitle) is not None:
        return True
    return False


async def fetch_doi_negotiated_bibtex(
    client: RateLimitedHttpClient,
    cand: CandidateRecord,
    noise_blacklist: list[str] | None = None,
) -> tuple[str, str, dict[str, str]] | None:
    """Fetch publisher BibTeX via https://doi.org/{doi} Content Negotiation and repair known quirks."""
    clean_doi = extract_doi_from_text(cand.doi)
    if not clean_doi:
        return None

    encoded_doi = quote(clean_doi, safe="/")
    try:
        resp = await client.get(
            f"https://doi.org/{encoded_doi}",
            headers={"Accept": "application/x-bibtex; charset=utf-8"},
            allow_404=True,
        )
    except UpstreamNetworkError:
        return None

    if resp.status_code != 200 or "@" not in resp.text:
        return None

    etype, _, raw_fields = parse_single_bibtex_block(resp.text)
    cleaned = sanitize_publisher_fields(raw_fields, noise_blacklist=noise_blacklist)
    if not cleaned.get("title"):
        return None

    # Defect Fix 1: Springer LNCS (e.g., ECCV / MICCAI) @inbook -> @inproceedings
    if _is_springer_conference_chapter(etype, cleaned, cand):
        etype = "inproceedings"
        if "booktitle" not in cleaned:
            container = str(cand.crossref_extra.get("container-title") or cand.matched_venue or "").strip()
            if container:
                cleaned["booktitle"] = container

    # Defect Fix 2: Missing pages / articleno completion from Crossref JSON or DBLP
    if "pages" not in cleaned and "articleno" not in cleaned:
        cr_page = str(cand.crossref_extra.get("page") or "").strip()
        cr_artno = str(cand.crossref_extra.get("article-number") or "").strip()
        dblp_pages = str(cand.crossref_extra.get("pages") or "").strip()
        if cr_page:
            cleaned["pages"] = cr_page
        elif cr_artno:
            cleaned["articleno"] = cr_artno
        elif dblp_pages:
            cleaned["pages"] = dblp_pages

    # Defect Fix 3: HTML entity decoding & dx.doi.org URL normalization
    for k, val in list(cleaned.items()):
        if k in {"url", "doi"}:
            unq = unquote(html.unescape(val)).strip()
            if k == "url":
                unq = re.sub(
                    r"^http://dx\.doi\.org/",
                    "https://doi.org/",
                    unq,
                    flags=re.IGNORECASE,
                )
            elif k == "doi":
                unq = re.sub(
                    r"^https?://(?:dx\.)?doi\.org/",
                    "",
                    unq,
                    flags=re.IGNORECASE,
                )
            cleaned[k] = unq
        else:
            # Decode HTML entities like &amp; -> & (formatter will safely escape bare & -> \&)
            cleaned[k] = html.unescape(val)

    cleaned.setdefault("doi", clean_doi)
    return label_doi_origin(clean_doi), etype, cleaned
