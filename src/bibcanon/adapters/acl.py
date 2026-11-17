"""ACL Anthology official .bib adapter (ACL / EMNLP / NAACL / EACL / TACL / COLING)."""

from __future__ import annotations

import re

from bibcanon.core.bib_parser import parse_single_bibtex_block
from bibcanon.core.formatter import sanitize_publisher_fields
from bibcanon.models import CandidateRecord
from bibcanon.providers.base import RateLimitedHttpClient, UpstreamNetworkError

_ACL_URL_RE = re.compile(r"aclanthology\.org/([A-Za-z0-9.\-]+?)(?:\.pdf|\.bib|/)?$", re.IGNORECASE)
_ACL_DOI_RE = re.compile(r"^10\.18653/v1/([A-Za-z0-9.\-]+)$", re.IGNORECASE)


def _extract_acl_id(cand: CandidateRecord) -> str | None:
    if cand.doi:
        m_doi = _ACL_DOI_RE.match(cand.doi.strip())
        if m_doi:
            return m_doi.group(1)

    all_urls = list(cand.ee_urls) + ([cand.url] if cand.url else [])
    for u in all_urls:
        m = _ACL_URL_RE.search(u.strip())
        if m:
            acl_id = m.group(1).strip("/")
            if acl_id:
                return acl_id
    return None


async def fetch_acl_bibtex(
    client: RateLimitedHttpClient,
    cand: CandidateRecord,
    noise_blacklist: list[str] | None = None,
) -> tuple[str, str, dict[str, str]] | None:
    """Fetch official BibTeX directly from https://aclanthology.org/{id}.bib."""
    acl_id = _extract_acl_id(cand)
    if not acl_id:
        return None

    try:
        resp = await client.get(f"https://aclanthology.org/{acl_id}.bib", allow_404=True)
    except UpstreamNetworkError:
        return None

    if resp.status_code != 200 or "@" not in resp.text:
        return None

    etype, _, raw_fields = parse_single_bibtex_block(resp.text)
    cleaned = sanitize_publisher_fields(raw_fields, noise_blacklist=noise_blacklist)
    if not cleaned.get("title"):
        return None

    return "ACL Anthology", etype, cleaned
