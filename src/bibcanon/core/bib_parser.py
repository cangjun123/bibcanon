"""Lossless character-span BibTeX parser, single-entry extractor, and file splicer."""

from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path

import bibtexparser
from bibtexparser.bparser import BibTexParser

from bibcanon.core.formatter import format_bibtex_entry, rekey_raw_bibtex
from bibcanon.models import (
    DecisionPayload,
    EntryAuditResult,
    ExportStats,
    ParsedBibDocument,
    ParsedBibEntry,
    StyleMode,
)

_ENTRY_HEADER_RE = re.compile(r"^@\s*([A-Za-z0-9_\-]+)\s*([{(])\s*([^,\s})]*)\s*,", re.DOTALL)
_FALLBACK_FIELD_RE = re.compile(
    r"([A-Za-z0-9_\-:.]+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[A-Za-z0-9_\-]+)",
    re.DOTALL,
)


def _scan_raw_blocks(raw_text: str) -> list[tuple[str, int, int]]:
    """Scan raw BibTeX text and return (entry_type, span_start, span_end) for every @-block.

    Comments starting with '%' outside entries (and at top-level between fields) are skipped
    so commented-out entries are never parsed as active entries.
    """
    blocks: list[tuple[str, int, int]] = []
    n = len(raw_text)
    i = 0

    while i < n:
        ch = raw_text[i]
        if ch == "%":
            nl = raw_text.find("\n", i)
            if nl == -1:
                break
            i = nl + 1
            continue

        if ch != "@":
            i += 1
            continue

        start = i
        i += 1
        while i < n and raw_text[i].isspace():
            i += 1

        type_start = i
        while i < n and (raw_text[i].isalnum() or raw_text[i] in "_-"):
            i += 1
        entry_type = raw_text[type_start:i]
        if not entry_type:
            continue

        while i < n and raw_text[i].isspace():
            i += 1

        if i >= n:
            break

        open_delim = raw_text[i]
        if open_delim not in "{(":
            # Handle bare @comment without braces
            if entry_type.lower() == "comment":
                nl = raw_text.find("\n", i)
                i = n if nl == -1 else nl + 1
            continue

        outer_is_paren = open_delim == "("
        paren_depth = 1 if outer_is_paren else 0
        brace_depth = 0 if outer_is_paren else 1
        top_brace_depth = 0 if outer_is_paren else 1

        in_quotes = False
        quote_base_depth = top_brace_depth
        i += 1

        while i < n:
            c = raw_text[i]
            if c == "\\":
                i += 2
                continue

            if not in_quotes and brace_depth == top_brace_depth and c == "%":
                nl = raw_text.find("\n", i)
                if nl == -1:
                    i = n
                    break
                i = nl + 1
                continue

            if c == '"':
                if not in_quotes and brace_depth == top_brace_depth:
                    in_quotes = True
                    quote_base_depth = brace_depth
                elif in_quotes and brace_depth == quote_base_depth:
                    in_quotes = False
                i += 1
                continue

            if c == "{":
                brace_depth += 1
            elif c == "}":
                if brace_depth > 0:
                    brace_depth -= 1
                if not outer_is_paren and not in_quotes and brace_depth == 0:
                    i += 1
                    blocks.append((entry_type, start, i))
                    break
            elif outer_is_paren and not in_quotes and brace_depth == 0:
                if c == "(":
                    paren_depth += 1
                elif c == ")":
                    paren_depth -= 1
                    if paren_depth == 0:
                        i += 1
                        blocks.append((entry_type, start, i))
                        break
            i += 1

    return blocks


def parse_single_bibtex_block(
    raw_block: str,
    string_defs: list[str] | None = None,
) -> tuple[str, str, dict[str, str]]:
    """Parse a single BibTeX entry block into (entry_type, cite_key, fields_dict)."""
    header_match = _ENTRY_HEADER_RE.match(raw_block.strip())
    fallback_type = header_match.group(1).lower() if header_match else "misc"
    fallback_key = header_match.group(3).strip() if header_match else "unknown"

    prefix = ("\n".join(string_defs) + "\n") if string_defs else ""
    combined = prefix + raw_block

    try:
        parser = BibTexParser(common_strings=True, interpolate_strings=True)
        parser.ignore_nonstandard_types = False
        parser.homogenize_fields = False
        db = bibtexparser.loads(combined, parser=parser)
        if db.entries:
            ent = db.entries[-1]
            entry_type = str(ent.get("ENTRYTYPE", fallback_type)).lower()
            cite_key = str(ent.get("ID", fallback_key))
            fields: dict[str, str] = {"ENTRYTYPE": entry_type}
            for k, v in ent.items():
                if k in {"ID", "ENTRYTYPE"}:
                    continue
                if isinstance(v, str):
                    fields[k] = v
                else:
                    fields[k] = str(v)
            # Keep exact case of cite_key from header if bibtexparser altered anything
            if header_match and header_match.group(3).strip():
                cite_key = header_match.group(3).strip()
            return entry_type, cite_key, fields
    except Exception:
        pass

    # Resilient regex fallback for slightly malformed BibTeX entries
    fields = {"ENTRYTYPE": fallback_type}
    body = raw_block[header_match.end() :] if header_match else raw_block
    for m in _FALLBACK_FIELD_RE.finditer(body):
        fname = m.group(1).strip()
        fval = m.group(2).strip()
        if (fval.startswith("{") and fval.endswith("}")) or (
            fval.startswith('"') and fval.endswith('"')
        ):
            fval = fval[1:-1]
        fields[fname] = fval

    return fallback_type, fallback_key, fields


def parse_bib_content(raw_text: str, source_path: str | None = None) -> ParsedBibDocument:
    """Losslessly parse a full .bib text into entries with exact character spans."""
    blocks = _scan_raw_blocks(raw_text)
    string_defs: list[str] = []
    entries: list[ParsedBibEntry] = []
    idx = 0

    for raw_type, span_start, span_end in blocks:
        low_type = raw_type.lower()
        raw_slice = raw_text[span_start:span_end]
        if low_type == "string":
            string_defs.append(raw_slice)
            continue
        if low_type in {"preamble", "comment"}:
            continue

        entry_type, cite_key, fields = parse_single_bibtex_block(raw_slice, string_defs)
        entries.append(
            ParsedBibEntry(
                cite_key=cite_key,
                entry_index=idx,
                entry_type=entry_type,
                span_start=span_start,
                span_end=span_end,
                raw_bibtex=raw_slice,
                fields=fields,
            )
        )
        idx += 1

    return ParsedBibDocument(raw_text=raw_text, entries=entries, source_path=source_path)


def parse_bib_file(path: str | Path) -> ParsedBibDocument:
    """Read a local .bib file using explicit UTF-8 encoding and parse it losslessly."""
    file_path = Path(path).expanduser().resolve()
    raw_text = file_path.read_text(encoding="utf-8")
    return parse_bib_content(raw_text, source_path=str(file_path))


def splice_bib_document(
    raw_text: str,
    audit_entries: list[EntryAuditResult],
    style_mode: StyleMode = "canonical",
    protect_title_case: bool = True,
    decisions_override: dict[str, DecisionPayload] | None = None,
    noise_blacklist: list[str] | None = None,
) -> tuple[str, ExportStats]:
    """Losslessly splice updated entries back into raw_text using exact character spans.

    Untouched entries, @string macros, @preamble blocks, comments, and original line endings
    between entries remain 100% byte-for-byte intact.
    """
    ordered = sorted(audit_entries, key=lambda e: e.span_start)
    chunks: list[str] = []
    cursor = 0

    accepted_count = 0
    kept_count = 0
    custom_count = 0

    # Detect file's dominant line ending so newly synthesized entries match surrounding file style
    newline = "\r\n" if "\r\n" in raw_text else "\n"

    for entry in ordered:
        chunks.append(raw_text[cursor : entry.span_start])

        payload = decisions_override.get(entry.cite_key) if decisions_override else None
        decision = payload.decision if payload else entry.decision
        cand_idx = (
            payload.selected_candidate_idx
            if (payload and payload.selected_candidate_idx is not None)
            else entry.selected_candidate_idx
        )
        custom_bib = (
            payload.custom_bibtex
            if (payload and payload.custom_bibtex is not None)
            else entry.custom_bibtex
        )
        target_key = (
            payload.override_cite_key
            if (payload and payload.override_cite_key)
            else entry.cite_key
        )

        replacement: str | None = None

        if decision == "custom" and custom_bib and custom_bib.strip():
            rendered_custom = custom_bib.strip()
            if payload and payload.override_cite_key:
                rendered_custom = rekey_raw_bibtex(rendered_custom, target_key)
            replacement = rendered_custom.replace("\r\n", "\n").replace("\n", newline)
            custom_count += 1
        elif decision == "accept" and entry.candidates:
            idx = cand_idx if (cand_idx is not None and 0 <= cand_idx < len(entry.candidates)) else 0
            cand = entry.candidates[idx]
            if cand.raw_publisher_fields:
                rendered = format_bibtex_entry(
                    cite_key=target_key,
                    entry_type=cand.entry_type,
                    raw_fields=cand.raw_publisher_fields,
                    style_mode=style_mode,
                    protect_title_case=protect_title_case,
                    noise_blacklist=noise_blacklist,
                )
            else:
                rendered = (
                    cand.compact_bibtex
                    if style_mode == "compact" and cand.compact_bibtex
                    else cand.canonical_bibtex
                )
                if target_key != entry.cite_key and rendered:
                    rendered = rekey_raw_bibtex(rendered, target_key)
            if rendered.strip():
                replacement = rendered.strip().replace("\r\n", "\n").replace("\n", newline)
                accepted_count += 1

        if replacement is None:
            chunks.append(raw_text[entry.span_start : entry.span_end])
            kept_count += 1
        else:
            chunks.append(replacement)

        cursor = entry.span_end

    chunks.append(raw_text[cursor:])
    stats = ExportStats(
        total_entries=len(ordered),
        accepted_count=accepted_count,
        kept_original_count=kept_count,
        custom_count=custom_count,
    )
    return "".join(chunks), stats


def write_bib_with_backup(target_path: str | Path, output_bibtex: str) -> Path:
    """Create a timestamped .bak.<YYYYMMDD_HHMMSS> backup and write UTF-8 content to target_path."""
    dest = Path(target_path).expanduser().resolve()
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = dest.with_name(f"{dest.name}.bak.{timestamp}")

    if dest.exists():
        shutil.copy2(dest, backup_path)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text("", encoding="utf-8")

    dest.write_text(output_bibtex, encoding="utf-8")
    return backup_path
