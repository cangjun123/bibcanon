"""Intelligent publisher BibTeX router orchestrating Phase 3 adapters."""

from __future__ import annotations

from bibcanon.adapters.acl import fetch_acl_bibtex
from bibcanon.adapters.cvf import fetch_cvf_bibtex
from bibcanon.adapters.doi_negotiator import fetch_doi_negotiated_bibtex
from bibcanon.adapters.openreview import fetch_openreview_or_neurips_bibtex
from bibcanon.adapters.pmlr import fetch_pmlr_bibtex
from bibcanon.core.formatter import format_bibtex_entry, sanitize_publisher_fields
from bibcanon.models import AppConfig, CandidateRecord
from bibcanon.providers.arxiv import fetch_arxiv_official_bibtex
from bibcanon.providers.base import RateLimitedHttpClient, UpstreamNetworkError
from bibcanon.providers.dblp import fetch_dblp_bibtex
from bibcanon.storage.cache import BibCache


def _synthesize_fallback_fields(cand: CandidateRecord) -> tuple[str, str, dict[str, str]]:
    """Build clean BibTeX fields from candidate discovery metadata when no upstream .bib endpoint responds."""
    etype = cand.entry_type or (
        "article"
        if cand.venue_tier == "JOURNAL"
        else ("inproceedings" if cand.venue_tier in {"MAIN_CONF", "WORKSHOP"} else "misc")
    )
    fields: dict[str, str] = {}
    if cand.matched_authors:
        fields["author"] = " and ".join(cand.matched_authors)
    if cand.matched_title:
        fields["title"] = cand.matched_title
    if cand.matched_venue and cand.venue_tier != "PREPRINT":
        if etype == "article":
            fields["journal"] = cand.matched_venue
        else:
            fields["booktitle"] = cand.matched_venue
    if cand.matched_year:
        fields["year"] = str(cand.matched_year)

    for src_k, dst_k in (
        ("page", "pages"),
        ("pages", "pages"),
        ("article-number", "articleno"),
        ("volume", "volume"),
        ("issue", "number"),
        ("number", "number"),
        ("publisher", "publisher"),
        ("isbn", "isbn"),
        ("issn", "issn"),
    ):
        if dst_k not in fields and cand.crossref_extra.get(src_k):
            fields[dst_k] = str(cand.crossref_extra[src_k])

    if cand.doi:
        fields["doi"] = cand.doi
    if cand.venue_tier == "PREPRINT" and cand.arxiv_id:
        etype = "misc"
        fields["eprint"] = cand.arxiv_id
        fields["archivePrefix"] = "arXiv"
        if cand.crossref_extra.get("primaryClass"):
            fields["primaryClass"] = str(cand.crossref_extra["primaryClass"])
        fields["url"] = f"https://arxiv.org/abs/{cand.arxiv_id}"
        return "arXiv Official", etype, fields

    if cand.url:
        fields["url"] = cand.url

    origin = cand.bibtex_origin or f"{cand.source_discovery.upper()} Metadata"
    return origin, etype, fields


def render_candidate_variants(
    cand: CandidateRecord,
    cite_key: str,
    config: AppConfig | None = None,
) -> CandidateRecord:
    """Render both `canonical_bibtex` and `compact_bibtex` on a candidate locked to `cite_key`."""
    cfg = config or AppConfig()
    if not cand.raw_publisher_fields:
        origin, etype, synth = _synthesize_fallback_fields(cand)
        cand.bibtex_origin = cand.bibtex_origin or origin
        cand.entry_type = etype
        cand.raw_publisher_fields = sanitize_publisher_fields(
            synth, noise_blacklist=cfg.noise_field_blacklist
        )

    cand.canonical_bibtex = format_bibtex_entry(
        cite_key=cite_key,
        entry_type=cand.entry_type,
        raw_fields=cand.raw_publisher_fields,
        style_mode="canonical",
        protect_title_case=cfg.default_protect_title_case,
        noise_blacklist=cfg.noise_field_blacklist,
    )
    cand.compact_bibtex = format_bibtex_entry(
        cite_key=cite_key,
        entry_type=cand.entry_type,
        raw_fields=cand.raw_publisher_fields,
        style_mode="compact",
        protect_title_case=cfg.default_protect_title_case,
        noise_blacklist=cfg.noise_field_blacklist,
    )
    return cand


async def enrich_candidate_with_publisher_bibtex(
    client: RateLimitedHttpClient,
    cand: CandidateRecord,
    cite_key: str,
    cache: BibCache | None = None,
    config: AppConfig | None = None,
) -> CandidateRecord:
    """Route candidate to the appropriate official publisher BibTeX adapter per SPEC.md 5.3."""
    cfg = config or client.config
    blacklist = cfg.noise_field_blacklist
    resolved: tuple[str, str, dict[str, str]] | None = None

    all_urls_low = [u.lower() for u in cand.ee_urls] + (
        [cand.url.lower()] if cand.url else []
    )

    if cand.venue_tier == "PREPRINT":
        # Adapter 6: Official arXiv @misc
        if cand.arxiv_id:
            try:
                ax_res = await fetch_arxiv_official_bibtex(
                    client,
                    cand.arxiv_id,
                    fallback_fields=cand.raw_publisher_fields,
                    noise_blacklist=blacklist,
                )
                if ax_res is not None:
                    resolved = ("arXiv Official", ax_res[0], ax_res[1])
            except UpstreamNetworkError:
                if cand.raw_publisher_fields:
                    resolved = ("arXiv Official", "misc", dict(cand.raw_publisher_fields))

        if resolved is None and cand.dblp_key:
            try:
                dblp_res = await fetch_dblp_bibtex(
                    client, cand.dblp_key, noise_blacklist=blacklist
                )
                if dblp_res is not None:
                    resolved = ("DBLP Curated", dblp_res[0], dblp_res[1])
            except UpstreamNetworkError:
                pass
    else:
        # Adapter 1: CVF Open Access (CVPR / ICCV / WACV)
        if cand.canonical_venue_id in {"CVPR", "ICCV", "WACV"} or any(
            "openaccess.thecvf.com" in u for u in all_urls_low
        ):
            resolved = await fetch_cvf_bibtex(
                client, cand, cache=cache, noise_blacklist=blacklist
            )

        # Adapter 2: PMLR (ICML / AISTATS / CoRL / COLT / ACML)
        if resolved is None and any("mlr.press" in u for u in all_urls_low):
            resolved = await fetch_pmlr_bibtex(
                client, cand, noise_blacklist=blacklist
            )

        # Adapter 3: OpenReview & NeurIPS Proceedings (ICLR / NeurIPS / TMLR)
        if resolved is None and any(
            host in u
            for u in all_urls_low
            for host in ("papers.nips.cc", "proceedings.neurips.cc", "openreview.net")
        ):
            resolved = await fetch_openreview_or_neurips_bibtex(
                client, cand, noise_blacklist=blacklist
            )

        # Adapter 4: ACL Anthology (ACL / EMNLP / NAACL / EACL / TACL)
        if resolved is None and (
            any("aclanthology.org" in u for u in all_urls_low)
            or (cand.doi and cand.doi.lower().startswith("10.18653/v1/"))
        ):
            resolved = await fetch_acl_bibtex(
                client, cand, noise_blacklist=blacklist
            )

        # Adapter 5: DOI Content Negotiation + Crossref/DBLP Defect Repair
        if resolved is None and cand.doi:
            resolved = await fetch_doi_negotiated_bibtex(
                client, cand, noise_blacklist=blacklist
            )

        # Adapter 7: Universal DBLP Curated .bib Fallback
        if resolved is None and cand.dblp_key:
            try:
                dblp_res = await fetch_dblp_bibtex(
                    client, cand.dblp_key, noise_blacklist=blacklist
                )
                if dblp_res is not None:
                    resolved = ("DBLP Curated", dblp_res[0], dblp_res[1])
            except UpstreamNetworkError:
                pass

    if resolved is None:
        resolved = _synthesize_fallback_fields(cand)

    origin, etype, pub_fields = resolved
    cand.bibtex_origin = origin
    cand.entry_type = etype
    cand.raw_publisher_fields = pub_fields
    return render_candidate_variants(cand, cite_key=cite_key, config=cfg)
