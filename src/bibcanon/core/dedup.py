"""Internal .bib duplicate paper detection across DOI, arXiv ID, and normalized title."""

from __future__ import annotations

from collections import defaultdict

from bibcanon.core.normalizer import (
    extract_arxiv_id_from_text,
    extract_author_surnames,
    extract_doi_from_text,
    extract_entry_features,
    normalize_title,
)
from bibcanon.models import AuditWarning, EntryAuditResult, ParsedBibEntry, WarningCode


def _entry_signatures(
    parsed_entry: ParsedBibEntry | None,
    audit_entry: EntryAuditResult,
) -> set[str]:
    """Build canonical identity signatures for an entry from both original and verified metadata."""
    sigs: set[str] = set()

    if parsed_entry is not None:
        feat = extract_entry_features(parsed_entry)
    else:
        dummy = ParsedBibEntry(
            cite_key=audit_entry.cite_key,
            entry_index=audit_entry.entry_index,
            entry_type=audit_entry.original_fields.get("ENTRYTYPE", "misc"),
            span_start=audit_entry.span_start,
            span_end=audit_entry.span_end,
            raw_bibtex=audit_entry.original_bibtex,
            fields=audit_entry.original_fields,
        )
        feat = extract_entry_features(dummy)

    if feat.doi:
        sigs.add(f"doi:{feat.doi.lower()}")
    if feat.arxiv_id:
        sigs.add(f"arxiv:{feat.arxiv_id.lower()}")
    if feat.normalized_title and (len(feat.normalized_title) >= 12 or feat.title_word_count >= 3):
        first_author = feat.first_author_surname or ""
        sigs.add(f"title_author:{feat.normalized_title}|{first_author}")
        if feat.title_word_count >= 5:
            sigs.add(f"title5:{feat.normalized_title}")

    # Also include verified selected candidate identity (catches arXiv entry + CVPR entry of same paper!)
    if audit_entry.candidates:
        idx = (
            audit_entry.selected_candidate_idx
            if (
                audit_entry.selected_candidate_idx is not None
                and 0 <= audit_entry.selected_candidate_idx < len(audit_entry.candidates)
            )
            else 0
        )
        cand = audit_entry.candidates[idx]
        if cand.score >= 85.0:
            c_doi = extract_doi_from_text(cand.doi)
            if c_doi:
                sigs.add(f"doi:{c_doi.lower()}")
            c_arxiv = extract_arxiv_id_from_text(cand.arxiv_id)
            if c_arxiv:
                sigs.add(f"arxiv:{c_arxiv.lower()}")
            c_norm_title = normalize_title(cand.matched_title)
            c_words = [w for w in c_norm_title.split(" ") if w]
            c_surnames, _ = extract_author_surnames(cand.matched_authors)
            c_first = c_surnames[0] if c_surnames else ""
            if c_norm_title and (len(c_norm_title) >= 12 or len(c_words) >= 3):
                sigs.add(f"title_author:{c_norm_title}|{c_first}")
                if len(c_words) >= 5:
                    sigs.add(f"title5:{c_norm_title}")

    return sigs


def mark_duplicate_entries(
    audit_entries: list[EntryAuditResult],
    parsed_entries: list[ParsedBibEntry] | None = None,
) -> list[EntryAuditResult]:
    """Detect duplicate papers within the same .bib and attach DUPLICATE_IN_BIB warnings."""
    parsed_by_index: dict[int, ParsedBibEntry] = (
        {pe.entry_index: pe for pe in parsed_entries} if parsed_entries else {}
    )

    sig_to_indices: dict[str, list[int]] = defaultdict(list)
    for i, ae in enumerate(audit_entries):
        pe = parsed_by_index.get(ae.entry_index)
        for sig in _entry_signatures(pe, ae):
            sig_to_indices[sig].append(i)

    dup_map: dict[int, set[int]] = defaultdict(set)
    for indices in sig_to_indices.values():
        if len(indices) > 1:
            for i in indices:
                for j in indices:
                    if i != j:
                        dup_map[i].add(j)

    for i, ae in enumerate(audit_entries):
        # Remove any stale DUPLICATE_IN_BIB warnings before refreshing
        ae.warnings = [w for w in ae.warnings if w.code != WarningCode.DUPLICATE_IN_BIB]
        if i in dup_map:
            other_keys = [
                audit_entries[j].cite_key for j in sorted(dup_map[i])
            ]
            # Deduplicate while preserving order
            seen: set[str] = set()
            unique_other_keys: list[str] = []
            for k in other_keys:
                if k not in seen and k != ae.cite_key:
                    seen.add(k)
                    unique_other_keys.append(k)
                elif k == ae.cite_key and len(dup_map[i]) > 0 and k not in seen:
                    # Identical duplicate cite_key in same .bib
                    seen.add(k)
                    unique_other_keys.append(k)

            ae.warnings.append(
                AuditWarning(
                    code=WarningCode.DUPLICATE_IN_BIB,
                    severity="warning",
                    message=f"当前 .bib 文件内存在指向同一篇论文的重复条目: {', '.join(unique_other_keys)}",
                    other_cite_keys=unique_other_keys,
                )
            )

    return audit_entries
