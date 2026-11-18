"""Asynchronous verification, routing, caching, and manual paste-merge pipeline."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable

from bibcanon.adapters.router import (
    enrich_candidate_with_publisher_bibtex,
    render_candidate_variants,
)
from bibcanon.core.bib_parser import parse_single_bibtex_block
from bibcanon.core.dedup import mark_duplicate_entries
from bibcanon.core.formatter import sanitize_publisher_fields
from bibcanon.core.normalizer import (
    build_search_links,
    clean_display_title,
    extract_arxiv_id_from_text,
    extract_doi_from_text,
    extract_entry_features,
    extract_year,
    is_template_placeholder,
    normalize_title,
)
from bibcanon.core.scorer import elect_and_classify
from bibcanon.core.venue_dict import (
    get_canonical_venue_id,
    is_preprint_venue,
    is_workshop_venue,
    match_venue_entry,
)
from bibcanon.models import (
    AppConfig,
    AuditWarning,
    CandidateRecord,
    EntryAuditResult,
    ParsedBibDocument,
    ParsedBibEntry,
    VenueTier,
    VerificationStatus,
    WarningCode,
)
from bibcanon.providers.arxiv import lookup_arxiv_by_id, search_arxiv_by_title
from bibcanon.providers.base import RateLimitedHttpClient, UpstreamNetworkError
from bibcanon.providers.crossref import lookup_crossref_doi, search_crossref
from bibcanon.providers.dblp import search_dblp
from bibcanon.providers.openalex import search_openalex
from bibcanon.providers.semantic_scholar import search_semantic_scholar
from bibcanon.storage.cache import BibCache

ProgressCallback = Callable[[EntryAuditResult, int, int], Awaitable[None] | None]


def build_initial_audit_entries(doc: ParsedBibDocument) -> list[EntryAuditResult]:
    """Construct initial UNPROCESSED EntryAuditResult objects with prebuilt search links and dedup."""
    results: list[EntryAuditResult] = []
    for ent in doc.entries:
        feat = extract_entry_features(ent)
        links = build_search_links(feat.raw_title, feat.first_author_surname)
        results.append(
            EntryAuditResult(
                cite_key=ent.cite_key,
                entry_index=ent.entry_index,
                span_start=ent.span_start,
                span_end=ent.span_end,
                original_bibtex=ent.raw_bibtex,
                original_fields=ent.fields,
                status=VerificationStatus.UNPROCESSED,
                search_links=links,
            )
        )
    return mark_duplicate_entries(results, doc.entries)


async def verify_single_entry(
    parsed_entry: ParsedBibEntry,
    client: RateLimitedHttpClient,
    cache: BibCache | None = None,
    config: AppConfig | None = None,
    *,
    force_refresh: bool = False,
    override_query_title: str | None = None,
) -> EntryAuditResult:
    """Verify a single ParsedBibEntry end-to-end (discovery -> scoring/election -> publisher BibTeX)."""
    cfg = config or client.config
    if is_template_placeholder(parsed_entry) and not override_query_title:
        return EntryAuditResult(
            cite_key=parsed_entry.cite_key,
            entry_index=parsed_entry.entry_index,
            span_start=parsed_entry.span_start,
            span_end=parsed_entry.span_end,
            original_bibtex=parsed_entry.raw_bibtex,
            original_fields=parsed_entry.fields,
            status=VerificationStatus.SUSPECTED_HALLUCINATION,
            confidence=0.0,
            warnings=[
                AuditWarning(
                    code=WarningCode.FALSE_PUBLISHED_VENUE,
                    severity="warning",
                    message="检测到 LaTeX 模板自带占位示例条目 (FirstName / Frobnication)，非真实论文",
                )
            ],
            decision="keep_original",
            search_links=build_search_links(parsed_entry.fields.get("title", "")),
        )

    features = extract_entry_features(parsed_entry)

    if override_query_title and override_query_title.strip():
        features.raw_title = override_query_title.strip()
        features.normalized_title = normalize_title(features.raw_title)
        features.title_word_count = len([w for w in features.normalized_title.split(" ") if w])

    search_links = build_search_links(features.raw_title, features.first_author_surname)
    cache_key = BibCache.build_query_key(features)

    # 1. Check SQLite cache
    if cache is not None and not force_refresh:
        cached = cache.get_query_result(cache_key, ttl_days=cfg.cache_ttl_days)
        if cached is not None:
            try:
                status = VerificationStatus(cached["status"])
                cands = [CandidateRecord.model_validate(c) for c in cached.get("candidates", [])]
                for c in cands:
                    render_candidate_variants(c, cite_key=parsed_entry.cite_key, config=cfg)
                warnings = [
                    AuditWarning.model_validate(w)
                    for w in cached.get("warnings", [])
                    if w.get("code") != WarningCode.DUPLICATE_IN_BIB.value
                ]
                decision = cached.get("decision", "keep_original")
                if (
                    decision == "accept"
                    and cands
                    and cands[0].canonical_bibtex.strip() == parsed_entry.raw_bibtex.strip()
                ):
                    decision = "keep_original"
                return EntryAuditResult(
                    cite_key=parsed_entry.cite_key,
                    entry_index=parsed_entry.entry_index,
                    span_start=parsed_entry.span_start,
                    span_end=parsed_entry.span_end,
                    original_bibtex=parsed_entry.raw_bibtex,
                    original_fields=parsed_entry.fields,
                    status=status,
                    confidence=float(cached.get("confidence", 0.0)),
                    warnings=warnings,
                    selected_candidate_idx=cached.get("selected_candidate_idx"),
                    candidates=cands,
                    decision=decision,
                    search_links=search_links,
                )
            except Exception:
                pass

    # 2. Multi-source concurrent discovery
    query_title = features.raw_title
    tasks: dict[str, Awaitable[object]] = {}
    if query_title.strip():
        tasks["dblp"] = search_dblp(client, query_title)
        tasks["crossref"] = search_crossref(
            client, query_title, features.first_author_surname
        )
        tasks["openalex"] = search_openalex(client, query_title)
        tasks["arxiv_search"] = search_arxiv_by_title(client, query_title)
        if cfg.semantic_scholar_api_key.strip():
            tasks["s2"] = search_semantic_scholar(client, query_title)

    if features.doi:
        tasks["doi_lookup"] = lookup_crossref_doi(client, features.doi)
    if features.arxiv_id:
        tasks["arxiv_id"] = lookup_arxiv_by_id(client, features.arxiv_id)

    task_names = list(tasks.keys())
    raw_outputs = await asyncio.gather(*tasks.values(), return_exceptions=True)

    discovered: list[CandidateRecord] = []
    doi_lookup_cand: CandidateRecord | None = None
    doi_is_404 = False
    arxiv_is_invalid = False
    primary_succeeded = 0
    primary_errors = 0

    for name, out in zip(task_names, raw_outputs, strict=True):
        if isinstance(out, UpstreamNetworkError):
            if name != "s2":
                primary_errors += 1
            continue
        if isinstance(out, Exception):
            if name != "s2":
                primary_errors += 1
            continue

        if name != "s2":
            primary_succeeded += 1

        if name == "doi_lookup" and isinstance(out, tuple):
            cand_opt, is_404 = out
            doi_lookup_cand = cand_opt
            doi_is_404 = bool(is_404)
        elif name == "arxiv_id" and isinstance(out, tuple):
            ax_list, is_bad = out
            discovered.extend(ax_list)
            arxiv_is_invalid = bool(is_bad)
        elif isinstance(out, list):
            discovered.extend(out)

    # Low-priority S2 fallback when no API key is configured and primary sources found no formal record
    if (
        not cfg.semantic_scholar_api_key.strip()
        and query_title.strip()
        and not any(c.venue_tier != "PREPRINT" for c in discovered)
        and not (primary_succeeded == 0 and primary_errors > 0)
    ):
        s2_fallback = await search_semantic_scholar(client, query_title)
        discovered.extend(s2_fallback)

    all_sources_failed = primary_succeeded == 0 and primary_errors > 0

    # 3. Multi-dimensional scoring, guardrails, and two-branch election
    outcome = elect_and_classify(
        features,
        discovered,
        doi_is_404=doi_is_404,
        doi_lookup_cand=doi_lookup_cand,
        arxiv_is_invalid=arxiv_is_invalid,
        all_sources_failed=all_sources_failed,
    )

    # 4. Route top candidates to publisher-native BibTeX adapters concurrently
    if outcome.candidates:
        enriched = await asyncio.gather(
            *(
                enrich_candidate_with_publisher_bibtex(
                    client,
                    cand,
                    cite_key=parsed_entry.cite_key,
                    cache=cache,
                    config=cfg,
                )
                for cand in outcome.candidates
            )
        )
        outcome.candidates = list(enriched)

    decision = outcome.decision
    if (
        decision == "accept"
        and outcome.candidates
        and outcome.candidates[0].canonical_bibtex.strip() == parsed_entry.raw_bibtex.strip()
    ):
        decision = "keep_original"

    result = EntryAuditResult(
        cite_key=parsed_entry.cite_key,
        entry_index=parsed_entry.entry_index,
        span_start=parsed_entry.span_start,
        span_end=parsed_entry.span_end,
        original_bibtex=parsed_entry.raw_bibtex,
        original_fields=parsed_entry.fields,
        status=outcome.status,
        confidence=outcome.confidence,
        warnings=outcome.warnings,
        selected_candidate_idx=outcome.selected_candidate_idx,
        candidates=outcome.candidates,
        decision=decision,
        search_links=search_links,
    )

    # 5. Persist in SQLite query_cache (never cache transient network ERRORs)
    if cache is not None and outcome.status != VerificationStatus.ERROR:
        cache_payload = {
            "status": result.status.value,
            "confidence": result.confidence,
            "warnings": [
                w.model_dump()
                for w in result.warnings
                if w.code != WarningCode.DUPLICATE_IN_BIB
            ],
            "selected_candidate_idx": result.selected_candidate_idx,
            "candidates": [c.model_dump() for c in result.candidates],
            "decision": outcome.decision,
        }
        cache.set_query_result(cache_key, cache_payload)

    return result


def merge_pasted_bibtex(
    audit_entry: EntryAuditResult,
    pasted_bibtex: str,
    config: AppConfig | None = None,
) -> EntryAuditResult:
    """Parse external pasted BibTeX, lock original cite_key, strip noise, and select as candidate[0]."""
    cfg = config or AppConfig()
    if not pasted_bibtex or "@" not in pasted_bibtex:
        raise ValueError("粘贴的内容不包含有效的 BibTeX 条目 (@type{...})")

    etype, _, raw_fields = parse_single_bibtex_block(pasted_bibtex.strip())
    cleaned = sanitize_publisher_fields(raw_fields, noise_blacklist=cfg.noise_field_blacklist)
    if not cleaned or len(cleaned) == 0:
        raise ValueError("无法从粘贴文本中提取有效的 BibTeX 字段")

    raw_title = cleaned.get("title", "")
    title = clean_display_title(raw_title) if raw_title else audit_entry.cite_key
    authors_raw = cleaned.get("author", "")
    authors = (
        [a.strip() for a in authors_raw.split(" and ") if a.strip()]
        if authors_raw
        else []
    )
    year = extract_year(cleaned)
    venue = cleaned.get("booktitle") or cleaned.get("journal") or None
    doi = extract_doi_from_text(cleaned.get("doi") or cleaned.get("url"))
    arxiv_id = extract_arxiv_id_from_text(
        cleaned.get("eprint") or cleaned.get("journal") or cleaned.get("url")
    )

    tier: VenueTier = "MAIN_CONF"
    if etype == "misc" and (arxiv_id or not venue) or is_preprint_venue(venue):
        tier = "PREPRINT"
    elif is_workshop_venue(venue):
        tier = "WORKSHOP"
    else:
        mv = match_venue_entry(venue)
        if mv:
            tier = mv.tier
        elif etype == "article":
            tier = "JOURNAL"

    manual_cand = CandidateRecord(
        source_discovery="manual",
        bibtex_origin="Manual Paste",
        venue_tier=tier,
        canonical_venue_id=get_canonical_venue_id(venue) if tier != "PREPRINT" else None,
        score=100.0,
        score_breakdown={"title_score": 100.0, "author_score": 100.0, "year_score": 100.0},
        matched_title=title,
        matched_authors=authors,
        matched_year=year,
        matched_venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        url=cleaned.get("url") or (f"https://doi.org/{doi}" if doi else None),
        entry_type=etype,
        raw_publisher_fields=cleaned,
    )
    render_candidate_variants(manual_cand, cite_key=audit_entry.cite_key, config=cfg)

    # Remove previous Manual Paste entries if user pastes again, then insert at index 0
    remaining = [c for c in audit_entry.candidates if c.bibtex_origin != "Manual Paste"]
    audit_entry.candidates = [manual_cand, *remaining][:5]
    audit_entry.selected_candidate_idx = 0
    audit_entry.decision = "accept"
    audit_entry.custom_bibtex = None
    audit_entry.confidence = 100.0
    audit_entry.status = (
        VerificationStatus.VERIFIED_PREPRINT_ONLY
        if tier == "PREPRINT"
        else VerificationStatus.VERIFIED_CANONICAL
    )
    # Keep only duplicate warnings if present; clear prior mismatch/hallucination warnings
    audit_entry.warnings = [
        w for w in audit_entry.warnings if w.code == WarningCode.DUPLICATE_IN_BIB
    ]
    return audit_entry


async def run_verification_pipeline(
    doc: ParsedBibDocument,
    config: AppConfig | None = None,
    cache: BibCache | None = None,
    *,
    force_refresh: bool = False,
    on_entry_updated: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
    client: RateLimitedHttpClient | None = None,
    max_parallel_entries: int = 5,
) -> list[EntryAuditResult]:
    """Run full concurrent verification pipeline on a ParsedBibDocument with SSE callback support."""
    cfg = config or AppConfig()
    results = build_initial_audit_entries(doc)
    total = len(doc.entries)
    if total == 0:
        return results

    owns_client = client is None
    http_client = client or RateLimitedHttpClient(config=cfg)
    entry_sem = asyncio.Semaphore(max_parallel_entries)
    completed = 0
    progress_lock = asyncio.Lock()

    async def _worker(idx: int, pe: ParsedBibEntry) -> None:
        nonlocal completed
        if cancel_event is not None and cancel_event.is_set():
            return
        async with entry_sem:
            if cancel_event is not None and cancel_event.is_set():
                return
            verified = await verify_single_entry(
                pe,
                http_client,
                cache=cache,
                config=cfg,
                force_refresh=force_refresh,
            )
            async with progress_lock:
                results[idx] = verified
                completed += 1
                curr_completed = completed
                if on_entry_updated is not None:
                    cb_res = on_entry_updated(verified, curr_completed, total)
                    if inspect.isawaitable(cb_res):
                        await cb_res

    try:
        await asyncio.gather(*(_worker(i, pe) for i, pe in enumerate(doc.entries)))
    finally:
        if owns_client:
            await http_client.aclose()

    mark_duplicate_entries(results, doc.entries)
    return results
