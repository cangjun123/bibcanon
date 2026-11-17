"""Multi-dimensional similarity scoring, anti-hallucination guardrails, and two-branch election."""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from bibcanon.core.normalizer import (
    decode_latex_to_unicode,
    extract_author_surnames,
    normalize_title,
)
from bibcanon.core.venue_dict import (
    get_canonical_venue_id,
    is_preprint_venue,
    is_workshop_venue,
    match_venue_entry,
)
from bibcanon.models import (
    AuditWarning,
    CandidateRecord,
    DecisionType,
    ExtractedEntryFeatures,
    VerificationStatus,
    WarningCode,
)


@dataclass
class ElectionOutcome:
    """Result of scoring, guardrails, and candidate election for a single entry."""

    status: VerificationStatus
    confidence: float
    candidates: list[CandidateRecord] = field(default_factory=list)
    selected_candidate_idx: int | None = None
    warnings: list[AuditWarning] = field(default_factory=list)
    decision: DecisionType = "keep_original"


def refine_candidate_tier(cand: CandidateRecord) -> CandidateRecord:
    """Enforce strict PREPRINT and WORKSHOP tiering rules per SPEC.md Section 4.4."""
    venue = (cand.matched_venue or "").strip()
    if cand.doi and cand.doi.lower().startswith("10.48550/arxiv."):
        cand.doi = None
        cand.venue_tier = "PREPRINT"
        cand.canonical_venue_id = None
        cand.entry_type = "misc"
        return cand

    if venue:
        if venue.lower() == "corr" or is_preprint_venue(venue):
            cand.venue_tier = "PREPRINT"
            cand.canonical_venue_id = None
            cand.entry_type = "misc"
            return cand
        if is_workshop_venue(venue):
            cand.venue_tier = "WORKSHOP"
            cand.canonical_venue_id = get_canonical_venue_id(venue)
            cand.entry_type = "inproceedings"
            return cand
        matched = match_venue_entry(venue)
        if matched and cand.venue_tier != "PREPRINT":
            cand.venue_tier = matched.tier
            cand.canonical_venue_id = matched.canonical_id
            cand.entry_type = "article" if matched.tier == "JOURNAL" else "inproceedings"

    if str(cand.crossref_extra.get("type", "")).lower() == "posted-content":
        cand.venue_tier = "PREPRINT"
        cand.canonical_venue_id = None
        cand.entry_type = "misc"

    return cand


def score_candidate(orig: ExtractedEntryFeatures, cand: CandidateRecord) -> CandidateRecord:
    """Compute multi-dimensional score (Title 0.55 + Author 0.30 + Year 0.15) for a candidate."""
    refine_candidate_tier(cand)

    norm_orig = orig.normalized_title
    norm_cand = normalize_title(cand.matched_title)

    if not norm_orig or not norm_cand:
        cand.score = 0.0
        cand.score_breakdown = {"title_score": 0.0, "author_score": 0.0, "year_score": 0.0}
        return cand

    r_basic = float(fuzz.ratio(norm_orig, norm_cand))
    r_sort = float(fuzz.token_sort_ratio(norm_orig, norm_cand))
    s_title = 0.6 * r_basic + 0.4 * r_sort

    short_title_cap = False
    if orig.title_word_count <= 4:
        s_title = r_basic
        if r_basic < 92.0:
            short_title_cap = True

    # Author score
    cand_surnames, _ = extract_author_surnames(cand.matched_authors)
    first_ratio = 0.0
    if not orig.author_surnames:
        s_author = 50.0
        first_match = 50.0
    elif not cand_surnames:
        s_author = 0.0
        first_match = 0.0
    else:
        first_ratio = float(fuzz.ratio(orig.author_surnames[0], cand_surnames[0]))
        if first_ratio >= 85.0:
            first_match = 100.0
        elif any(fuzz.ratio(orig.author_surnames[0], cs) >= 85.0 for cs in cand_surnames[:3]):
            first_match = 60.0
        else:
            first_match = 0.0

        matched_orig = sum(
            1
            for os_ in orig.author_surnames
            if any(fuzz.ratio(os_, cs) >= 85.0 for cs in cand_surnames)
        )
        matched_cand = sum(
            1
            for cs in cand_surnames
            if any(fuzz.ratio(cs, os_) >= 85.0 for os_ in orig.author_surnames)
        )
        recall = matched_orig / len(orig.author_surnames)
        precision = matched_cand / len(cand_surnames)
        if orig.has_et_al:
            overlap = recall
        else:
            overlap = (
                (2.0 * precision * recall / (precision + recall))
                if (precision + recall) > 0
                else 0.0
            )
        s_author = 0.5 * first_match + 0.5 * (overlap * 100.0)

    # Year score
    if orig.year is None or cand.matched_year is None:
        s_year = 70.0
    elif orig.is_preprint and cand.venue_tier != "PREPRINT":
        diff = cand.matched_year - orig.year
        if -1 <= diff <= 3:
            s_year = 100.0
        elif abs(diff) == 4:
            s_year = 50.0
        else:
            s_year = 0.0
    else:
        adiff = abs(cand.matched_year - orig.year)
        if adiff == 0:
            s_year = 100.0
        elif adiff == 1:
            s_year = 80.0
        elif adiff == 2:
            s_year = 40.0
        else:
            s_year = 0.0

    # Subtitle colon tolerance (SPEC.md 4.3.1)
    if not short_title_cap and orig.title_word_count >= 5:
        decoded_cand = decode_latex_to_unicode(cand.matched_title)
        if ":" in decoded_cand:
            main_prefix = normalize_title(decoded_cand.split(":", 1)[0])
            if main_prefix == norm_orig and first_ratio >= 85.0 and s_year >= 80.0:
                s_title = max(s_title, 92.0)

    total = 0.55 * s_title + 0.30 * s_author + 0.15 * s_year
    if short_title_cap:
        total = min(total, 59.0)

    cand.score = round(total, 2)
    cand.score_breakdown = {
        "title_score": round(s_title, 2),
        "author_score": round(s_author, 2),
        "year_score": round(s_year, 2),
    }
    return cand


def _are_same_edition(a: CandidateRecord, b: CandidateRecord) -> bool:
    """Return True if two CandidateRecords represent the same venue edition of the same paper."""
    if a.venue_tier != b.venue_tier:
        return False
    if a.doi and b.doi and a.doi.lower() == b.doi.lower():
        return True
    norm_a = normalize_title(a.matched_title)
    norm_b = normalize_title(b.matched_title)
    if a.venue_tier == "PREPRINT":
        if a.arxiv_id and b.arxiv_id and a.arxiv_id.lower() == b.arxiv_id.lower():
            return True
        return fuzz.ratio(norm_a, norm_b) >= 95.0
    if (
        a.canonical_venue_id
        and b.canonical_venue_id
        and a.canonical_venue_id == b.canonical_venue_id
        and a.matched_year == b.matched_year
        and fuzz.ratio(norm_a, norm_b) >= 92.0
    ):
        return True
    return False


def _merge_two_candidates(primary: CandidateRecord, secondary: CandidateRecord) -> CandidateRecord:
    """Merge metadata clues from `secondary` into `primary` without losing upstream fields."""
    if secondary.score > primary.score:
        primary, secondary = secondary, primary

    merged_ee = list(primary.ee_urls)
    for u in secondary.ee_urls:
        if u and u not in merged_ee:
            merged_ee.append(u)
    primary.ee_urls = merged_ee

    if not primary.doi and secondary.doi:
        primary.doi = secondary.doi
    if not primary.arxiv_id and secondary.arxiv_id:
        primary.arxiv_id = secondary.arxiv_id
    if not primary.dblp_key and secondary.dblp_key:
        primary.dblp_key = secondary.dblp_key
    if not primary.dblp_type and secondary.dblp_type:
        primary.dblp_type = secondary.dblp_type
    if not primary.url and secondary.url:
        primary.url = secondary.url
    if len(secondary.matched_authors) > len(primary.matched_authors):
        primary.matched_authors = list(secondary.matched_authors)
    if (
        secondary.matched_venue
        and len(secondary.matched_venue) > len(primary.matched_venue or "")
        and primary.venue_tier != "PREPRINT"
    ):
        primary.matched_venue = secondary.matched_venue

    merged_extra = dict(secondary.crossref_extra)
    merged_extra.update(primary.crossref_extra)
    primary.crossref_extra = merged_extra

    if not primary.raw_publisher_fields and secondary.raw_publisher_fields:
        primary.raw_publisher_fields = dict(secondary.raw_publisher_fields)
        if not primary.bibtex_origin and secondary.bibtex_origin:
            primary.bibtex_origin = secondary.bibtex_origin

    return primary


def merge_equivalent_candidates(candidates: list[CandidateRecord]) -> list[CandidateRecord]:
    """Consolidate duplicate hits from multiple discovery APIs into distinct venue editions."""
    merged: list[CandidateRecord] = []
    for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
        placed = False
        for idx, existing in enumerate(merged):
            if _are_same_edition(existing, cand):
                merged[idx] = _merge_two_candidates(existing, cand)
                placed = True
                break
        if not placed:
            merged.append(cand.model_copy(deep=True))
    return merged


def _branch2_sort_key(cand: CandidateRecord) -> tuple[int, int, int, int, float]:
    """Ranking key for preprint auto-upgrade:
    JOURNAL / MAIN_CONF (preferring title_score >= 95; JOURNAL > MAIN_CONF on tie) > WORKSHOP > PREPRINT.
    """
    tier_rank = {"JOURNAL": 4, "MAIN_CONF": 3, "WORKSHOP": 2, "PREPRINT": 1}.get(
        cand.venue_tier, 1
    )
    is_formal_main = 1 if cand.venue_tier in {"JOURNAL", "MAIN_CONF"} else 0
    high_title_formal = (
        1
        if (
            is_formal_main
            and cand.score_breakdown.get("title_score", 0.0) >= 95.0
            and cand.score >= 85.0
        )
        else 0
    )
    high_conf = 1 if cand.score >= 88.0 else 0
    return (high_conf, high_title_formal, is_formal_main, tier_rank, cand.score)


def elect_and_classify(
    orig: ExtractedEntryFeatures,
    raw_candidates: list[CandidateRecord],
    *,
    doi_is_404: bool = False,
    doi_lookup_cand: CandidateRecord | None = None,
    arxiv_is_invalid: bool = False,
    all_sources_failed: bool = False,
) -> ElectionOutcome:
    """Score candidates, enforce hard anti-hallucination guardrails, and run two-branch election."""
    if all_sources_failed and not raw_candidates and doi_lookup_cand is None:
        return ElectionOutcome(
            status=VerificationStatus.ERROR,
            confidence=0.0,
            decision="keep_original",
        )

    warnings: list[AuditWarning] = []

    all_pool = list(raw_candidates)
    if doi_lookup_cand is not None:
        score_candidate(orig, doi_lookup_cand)
        all_pool.append(doi_lookup_cand)

    for c in all_pool:
        score_candidate(orig, c)

    merged = merge_equivalent_candidates(all_pool)

    # Hard Guardrail Rule C: Invalid or hijacked DOI
    has_invalid_doi = False
    if orig.doi:
        if doi_is_404:
            has_invalid_doi = True
        elif (
            doi_lookup_cand is not None
            and doi_lookup_cand.score_breakdown.get("title_score", 0.0) < 65.0
        ):
            has_invalid_doi = True

    if has_invalid_doi:
        warnings.append(
            AuditWarning(
                code=WarningCode.INVALID_DOI,
                severity="error",
                message=f"原条目包含的 DOI ({orig.doi}) 返回 404 死链或指向另一篇完全不同的论文",
            )
        )

    # Check invalid arXiv ID
    has_invalid_arxiv = False
    if orig.arxiv_id:
        if arxiv_is_invalid:
            has_invalid_arxiv = True
        else:
            id_matches = [
                c
                for c in merged
                if c.arxiv_id and c.arxiv_id.lower() == orig.arxiv_id.lower()
            ]
            if id_matches and max(c.score_breakdown.get("title_score", 0.0) for c in id_matches) < 65.0:
                has_invalid_arxiv = True

    if has_invalid_arxiv:
        warnings.append(
            AuditWarning(
                code=WarningCode.INVALID_ARXIV_ID,
                severity="error",
                message=f"原条目包含的 arXiv ID ({orig.arxiv_id}) 不存在或与标题完全不符",
            )
        )

    # Hard Guardrail Rule A: Author mismatch on high-similarity title (张冠李戴熔断)
    high_title_cands = [
        c for c in merged if c.score_breakdown.get("title_score", 0.0) >= 88.0
    ]
    if high_title_cands and orig.author_surnames:
        best_author_among_high_title = max(
            c.score_breakdown.get("author_score", 0.0) for c in high_title_cands
        )
        if best_author_among_high_title < 35.0:
            best_ht = max(high_title_cands, key=lambda c: c.score)
            warnings.append(
                AuditWarning(
                    code=WarningCode.AUTHOR_MISMATCH,
                    severity="error",
                    message=(
                        f"标题高度匹配，但作者与官方记录 ({', '.join(best_ht.matched_authors[:3])}) 严重不符"
                    ),
                )
            )
            # If author_score == 0 and generic/ambiguous title, classify as SUSPECTED_HALLUCINATION
            is_hallucination = (
                best_ht.score_breakdown.get("author_score", 0.0) == 0.0
                and (len(high_title_cands) > 1 or orig.title_word_count <= 4)
            )
            status = (
                VerificationStatus.SUSPECTED_HALLUCINATION
                if is_hallucination
                else VerificationStatus.METADATA_MISMATCH
            )
            top_cands = sorted(high_title_cands, key=lambda c: c.score, reverse=True)[:5]
            return ElectionOutcome(
                status=status,
                confidence=best_ht.score,
                candidates=top_cands,
                selected_candidate_idx=0,
                warnings=warnings,
                decision="keep_original",
            )

    # Valid candidate filter
    valid_cands = [
        c
        for c in merged
        if c.score >= 65.0
        and c.score_breakdown.get("title_score", 0.0) >= 75.0
        and (not orig.author_surnames or c.score_breakdown.get("author_score", 0.0) >= 35.0)
    ]

    if not valid_cands:
        best_score = max((c.score for c in merged), default=0.0)
        fallback_cands = [c for c in merged if c.score >= 45.0][:3]
        return ElectionOutcome(
            status=VerificationStatus.SUSPECTED_HALLUCINATION,
            confidence=best_score,
            candidates=fallback_cands,
            selected_candidate_idx=0 if fallback_cands else None,
            warnings=warnings,
            decision="keep_original",
        )

    # --- Two-Branch Candidate Election (SPEC.md Section 4.4) ---
    ordered: list[CandidateRecord] = []
    status: VerificationStatus

    if not orig.is_preprint and orig.raw_venue:
        # Branch 1: Original entry specifies a formal publication venue
        formal_cands = [c for c in valid_cands if c.venue_tier != "PREPRINT"]

        # Hard Guardrail Rule B: False Published Venue (only preprints exist)
        if not formal_cands:
            ordered = sorted(valid_cands, key=lambda c: c.score, reverse=True)
            warnings.append(
                AuditWarning(
                    code=WarningCode.FALSE_PUBLISHED_VENUE,
                    severity="error",
                    message=(
                        f"原条目声称发表于正式场馆 ({orig.raw_venue})，但全网仅查到预印本记录，未查到正式录用记录"
                    ),
                )
            )
            status = VerificationStatus.METADATA_MISMATCH
        else:
            if orig.canonical_venue_id:
                venue_matches = [
                    c
                    for c in formal_cands
                    if c.canonical_venue_id == orig.canonical_venue_id
                ]
            else:
                norm_orig_v = normalize_title(orig.raw_venue)
                venue_matches = [
                    c
                    for c in formal_cands
                    if fuzz.token_set_ratio(norm_orig_v, normalize_title(c.matched_venue or ""))
                    >= 85.0
                ]

            if venue_matches:
                # Case 1.1: Respect original venue intent as candidates[0]
                venue_matches.sort(key=lambda c: c.score, reverse=True)
                winner = venue_matches[0]
                rest = [c for c in valid_cands if c is not winner]

                journal_exts = [
                    c
                    for c in rest
                    if c.venue_tier == "JOURNAL"
                    and winner.venue_tier != "JOURNAL"
                    and c.score >= 85.0
                ]
                journal_exts.sort(key=lambda c: c.score, reverse=True)

                if journal_exts:
                    j_ext = journal_exts[0]
                    others = [c for c in rest if c is not j_ext]
                    others.sort(key=_branch2_sort_key, reverse=True)
                    ordered = [winner, j_ext, *others]
                    warnings.append(
                        AuditWarning(
                            code=WarningCode.JOURNAL_EXTENSION_AVAILABLE,
                            severity="info",
                            message=(
                                f"已尊重原意默认保留 {winner.canonical_venue_id or winner.matched_venue} 官方版；"
                                f"另检测到后续期刊版 ({j_ext.canonical_venue_id or j_ext.matched_venue}"
                                f"{' ' + str(j_ext.matched_year) if j_ext.matched_year else ''}) 可在候选栏按需切换"
                            ),
                        )
                    )
                else:
                    rest.sort(key=_branch2_sort_key, reverse=True)
                    ordered = [winner, *rest]

                status = (
                    VerificationStatus.VERIFIED_CANONICAL
                    if winner.score >= 88.0
                    else VerificationStatus.METADATA_MISMATCH
                )
            else:
                # Case 1.2: Published only in a DIFFERENT formal venue
                ordered = sorted(valid_cands, key=_branch2_sort_key, reverse=True)
                winner = ordered[0]
                warnings.append(
                    AuditWarning(
                        code=WarningCode.VENUE_DIFFERS_FROM_ORIGINAL,
                        severity="warning",
                        message=(
                            f"原条目填写的场馆 ({orig.raw_venue}) 与检索到的实际发表场馆 "
                            f"({winner.matched_venue or winner.canonical_venue_id}) 不一致"
                        ),
                    )
                )
                status = VerificationStatus.METADATA_MISMATCH
    else:
        # Branch 2: Original entry is a preprint or omits venue -> auto-elect highest tier
        ordered = sorted(valid_cands, key=_branch2_sort_key, reverse=True)
        winner = ordered[0]
        if winner.score < 88.0:
            status = VerificationStatus.METADATA_MISMATCH
        elif winner.venue_tier in {"JOURNAL", "MAIN_CONF", "WORKSHOP"}:
            status = (
                VerificationStatus.PREPRINT_UPGRADE
                if orig.is_preprint
                else VerificationStatus.VERIFIED_CANONICAL
            )
        else:
            status = VerificationStatus.VERIFIED_PREPRINT_ONLY

    winner = ordered[0]

    # Post-election safety downgrades
    if not orig.author_surnames:
        status = VerificationStatus.METADATA_MISMATCH

    if has_invalid_doi or has_invalid_arxiv:
        status = VerificationStatus.METADATA_MISMATCH

    if (
        not orig.is_preprint
        and orig.year is not None
        and winner.matched_year is not None
        and abs(winner.matched_year - orig.year) >= 2
    ):
        warnings.append(
            AuditWarning(
                code=WarningCode.YEAR_DISCREPANCY,
                severity="warning",
                message=f"原条目年份 ({orig.year}) 与出版记录年份 ({winner.matched_year}) 存在明显出入",
            )
        )
        status = VerificationStatus.METADATA_MISMATCH

    top_five = ordered[:5]
    has_blocking_warning = any(w.severity in {"error", "warning"} for w in warnings)
    if (
        status
        in {
            VerificationStatus.VERIFIED_CANONICAL,
            VerificationStatus.PREPRINT_UPGRADE,
            VerificationStatus.VERIFIED_PREPRINT_ONLY,
        }
        and not has_blocking_warning
    ):
        decision: DecisionType = "accept"
    else:
        decision = "keep_original"

    return ElectionOutcome(
        status=status,
        confidence=winner.score,
        candidates=top_five,
        selected_candidate_idx=0,
        warnings=warnings,
        decision=decision,
    )
