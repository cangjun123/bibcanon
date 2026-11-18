"""Publisher-verbatim ('canonical') and compact BibTeX formatting with LaTeX safety."""

from __future__ import annotations

import html
import re

from bibcanon.core.venue_dict import PROTECTED_PROPER_NOUNS, get_compact_venue_name
from bibcanon.models import DEFAULT_NOISE_BLACKLIST, StyleMode

# Canonical display casing for standard BibTeX fields
_FIELD_CASING: dict[str, str] = {
    "archiveprefix": "archivePrefix",
    "primaryclass": "primaryClass",
}

# Preferred human-friendly field order; any unlisted publisher fields follow in original order
_PREFERRED_FIELD_ORDER: tuple[str, ...] = (
    "author",
    "title",
    "booktitle",
    "journal",
    "editor",
    "volume",
    "number",
    "series",
    "pages",
    "articleno",
    "numpages",
    "year",
    "month",
    "publisher",
    "institution",
    "school",
    "organization",
    "address",
    "location",
    "edition",
    "isbn",
    "issn",
    "doi",
    "eprint",
    "archiveprefix",
    "primaryclass",
    "pdf",
    "url",
    "howpublished",
    "note",
)

# Fields omitted in optional `compact` (page-saving) mode for published conference/journal entries
_COMPACT_STRIP_FIELDS: frozenset[str] = frozenset(
    {
        "url",
        "doi",
        "month",
        "publisher",
        "organization",
        "address",
        "location",
        "editor",
        "series",
        "isbn",
        "issn",
        "pdf",
        "numpages",
        "keywords",
        "issue_date",
    }
)

# Fields whose raw characters (&, %) must NEVER be LaTeX-escaped
_RAW_LINK_FIELDS: frozenset[str] = frozenset({"url", "doi", "pdf", "eprint"})

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PAGE_DASH_RE = re.compile(r"(?<=[0-9A-Za-z])\s*(?:--|[-–—−])\s*(?=[0-9A-Za-z])")
_ENTRY_KEY_HEADER_RE = re.compile(r"^(\s*@\s*[A-Za-z0-9_\-]+\s*[{(]\s*)([^,\s})]+)(\s*,)", re.DOTALL)
_WORD_OR_COMPOUND_RE = re.compile(r"[A-Za-z0-9]+(?:[-+/][A-Za-z0-9]+)*\+*")
_UNET_STYLE_RE = re.compile(r"^[A-Z]-Net(?:s)?$")


def rekey_raw_bibtex(raw_bibtex: str, new_cite_key: str) -> str:
    """Replace only the citation key in a raw BibTeX entry header."""
    return _ENTRY_KEY_HEADER_RE.sub(rf"\g<1>{new_cite_key}\g<3>", raw_bibtex, count=1)


def clean_control_and_nbsp(value: str) -> str:
    """Replace non-breaking spaces with standard spaces and strip invisible control chars."""
    cleaned = value.replace("\u00a0", " ")
    cleaned = _CONTROL_CHARS_RE.sub("", cleaned)
    return cleaned.strip()


def normalize_pages(pages_val: str) -> str:
    """Normalize page intervals (-, –, —) into standard LaTeX double-dash (--) idempotently."""
    cleaned = clean_control_and_nbsp(pages_val)
    return _PAGE_DASH_RE.sub("--", cleaned)


def escape_latex_special_outside_math(text: str) -> str:
    """Escape unescaped bare '&' and '%' outside $...$ inline math regions idempotently."""
    # Convert stray HTML &amp; to & first (only when not preceded by backslash) so it becomes \&
    text = re.sub(r"(?<!\\)&amp;", "&", text)
    text = html.unescape(text) if ("&#" in text or "&quot;" in text) else text

    out: list[str] = []
    in_math = False
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            out.append(text[i : i + 2])
            i += 2
            continue
        if ch == "$":
            in_math = not in_math
            out.append(ch)
            i += 1
            continue
        if not in_math:
            if ch == "&":
                out.append(r"\&")
                i += 1
                continue
            if ch == "%":
                out.append(r"\%")
                i += 1
                continue
        out.append(ch)
        i += 1

    return "".join(out)


def _is_whole_string_braced(text: str) -> bool:
    """Return True if text is already wrapped in a single outer pair of '{...}'."""
    stripped = text.strip()
    if len(stripped) < 2 or stripped[0] != "{" or stripped[-1] != "}":
        return False
    depth = 0
    i = 0
    n = len(stripped)
    while i < n:
        ch = stripped[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and i < n - 1:
                return False
        i += 1
    return depth == 0


def _needs_word_protection(word: str) -> bool:
    """Determine if a single unbraced word requires '{...}' case protection."""
    if len(word) < 2:
        return False
    alpha_chars = [c for c in word if c.isalpha()]
    if not alpha_chars:
        return False
    upper_count = sum(1 for c in alpha_chars if c.isupper())
    has_digit = any(c.isdigit() for c in word)

    # 1. Multi-uppercase acronym, plural acronym, or CamelCase (CNN, LLMs, ResNet, ViT, NeRF, LoRA)
    if upper_count >= 2:
        return True
    # 2. Alphanumeric technical term with uppercase (3D, 4D, GPT4, L1, SE3)
    if has_digit and upper_count >= 1:
        return True
    # 3. Lowercase prefix with internal uppercase (mAP, mIoU, iPhone, nuScenes, vSLAM)
    if word[0].islower() and upper_count >= 1:
        return True
    # 4. Curated CV/AI/ML proper nouns (Gaussian, Bayesian, Markov, Fourier, Transformer, etc.)
    base = word.rstrip("+")
    if word[0].isupper() and base.lower() in PROTECTED_PROPER_NOUNS:
        return True
    return False


def _protect_compound_token(token: str) -> str:
    """Apply case protection to a simple or hyphenated/compound token."""
    if "-" not in token and "/" not in token:
        return f"{{{token}}}" if _needs_word_protection(token) else token

    if _UNET_STYLE_RE.match(token):
        return f"{{{token}}}"

    # Split preserving delimiters '-' and '/'
    parts = re.split(r"([-+/])", token)
    word_parts = [p for p in parts if p and p not in "-+/"]

    # Check if the compound as a whole is an acronym/model token (e.g., RGB-D, R-CNN, CLIP-ViT, GPT-4)
    if len(word_parts) >= 2:
        has_strong_part = any(_needs_word_protection(p) for p in word_parts)
        all_parts_technical = all(
            _needs_word_protection(p)
            or (len(p) == 1 and p.isupper())
            or p.isdigit()
            for p in word_parts
        )
        if has_strong_part and all_parts_technical:
            return f"{{{token}}}"

    # Otherwise protect individual sub-words (e.g., 3D-Aware -> {3D}-Aware, Self-Attention -> Self-Attention)
    rebuilt: list[str] = []
    for p in parts:
        if p in "-+/" or not p:
            rebuilt.append(p)
        elif _needs_word_protection(p):
            rebuilt.append(f"{{{p}}}")
        else:
            rebuilt.append(p)
    return "".join(rebuilt)


def apply_title_case_protection(title: str) -> str:
    """Idempotently wrap acronyms, CamelCase model names, and proper nouns in '{...}'."""
    if not title or _is_whole_string_braced(title):
        return title

    result: list[str] = []
    plain_buf: list[str] = []
    brace_depth = 0
    in_math = False
    i = 0
    n = len(title)

    def flush_plain(left_braced: bool, right_braced: bool) -> None:
        if not plain_buf:
            return
        segment = "".join(plain_buf)
        plain_buf.clear()

        def _replacer(m: re.Match[str]) -> str:
            # Skip wrapping fragments already attached to an adjacent {...} group (e.g. DeepLab{V3}, {P}oly{G}en)
            if left_braced and m.start() == 0:
                return m.group(0)
            if right_braced and m.end() == len(segment):
                return m.group(0)
            return _protect_compound_token(m.group(0))

        protected_seg = _WORD_OR_COMPOUND_RE.sub(_replacer, segment)
        result.append(protected_seg)

    prev_was_closing_brace = False

    while i < n:
        ch = title[i]
        if ch == "\\" and i + 1 < n:
            # LaTeX command/escape: flush plain buffer and keep command sequence intact
            flush_plain(prev_was_closing_brace, False)
            prev_was_closing_brace = False
            cmd_start = i
            i += 1
            if title[i].isalpha():
                while i < n and title[i].isalpha():
                    i += 1
            else:
                i += 1
            result.append(title[cmd_start:i])
            continue

        if ch == "$" and brace_depth == 0:
            flush_plain(prev_was_closing_brace, False)
            prev_was_closing_brace = False
            in_math = not in_math
            result.append(ch)
            i += 1
            continue

        if ch == "{":
            if brace_depth == 0 and not in_math:
                flush_plain(prev_was_closing_brace, True)
                prev_was_closing_brace = False
            brace_depth += 1
            result.append(ch)
            i += 1
            continue

        if ch == "}":
            if brace_depth > 0:
                brace_depth -= 1
                if brace_depth == 0 and not in_math:
                    prev_was_closing_brace = True
            result.append(ch)
            i += 1
            continue

        if brace_depth == 0 and not in_math:
            if ch.isspace() and not plain_buf:
                prev_was_closing_brace = False
            plain_buf.append(ch)
        else:
            result.append(ch)
        i += 1

    flush_plain(prev_was_closing_brace, False)
    return "".join(result)


def clean_doi_url_value(field_lower: str, val: str) -> str:
    """Normalize DOI / URL strings without mangling query ampersands or percent-encoding."""
    cleaned = clean_control_and_nbsp(html.unescape(val))
    if field_lower == "doi":
        # Strip leading https://doi.org/ or http://dx.doi.org/ if publisher put URL in doi field
        cleaned = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", cleaned, flags=re.IGNORECASE)
    elif field_lower == "url":
        cleaned = re.sub(r"^http://dx\.doi\.org/", "https://doi.org/", cleaned, flags=re.IGNORECASE)
    return cleaned


def sanitize_publisher_fields(
    raw_fields: dict[str, str],
    noise_blacklist: list[str] | None = None,
) -> dict[str, str]:
    """Strip blacklisted noise fields while preserving all authentic publisher fields."""
    blacklist = {
        f.strip().lower()
        for f in (noise_blacklist if noise_blacklist is not None else DEFAULT_NOISE_BLACKLIST)
    }
    blacklist.update({"id", "entrytype"})

    cleaned_fields: dict[str, str] = {}
    for k, v in raw_fields.items():
        k_low = k.strip().lower()
        if not k_low or k_low in blacklist:
            continue
        if v is None:
            continue
        val_str = clean_control_and_nbsp(str(v))
        if not val_str:
            continue
        canonical_key = _FIELD_CASING.get(k_low, k_low)
        cleaned_fields[canonical_key] = val_str

    return cleaned_fields


def format_bibtex_entry(
    cite_key: str,
    entry_type: str,
    raw_fields: dict[str, str],
    style_mode: StyleMode = "canonical",
    protect_title_case: bool = True,
    noise_blacklist: list[str] | None = None,
) -> str:
    """Format a BibTeX entry locking `cite_key`, preserving publisher fields in canonical mode,
    and ensuring full LaTeX compilation safety.
    """
    etype = (entry_type or raw_fields.get("ENTRYTYPE", "misc")).strip().lower()
    fields = sanitize_publisher_fields(raw_fields, noise_blacklist=noise_blacklist)

    is_formal_venue = etype in {"inproceedings", "article", "incollection", "proceedings"} and (
        "booktitle" in fields or "journal" in fields
    )

    if style_mode == "compact" and is_formal_venue:
        if "booktitle" in fields:
            abbr = get_compact_venue_name(fields["booktitle"])
            if abbr:
                fields["booktitle"] = abbr
        if "journal" in fields:
            abbr = get_compact_venue_name(fields["journal"])
            if abbr:
                fields["journal"] = abbr
        fields = {
            k: v for k, v in fields.items() if k.lower() not in _COMPACT_STRIP_FIELDS
        }

    # Apply field-level LaTeX safety & formatting
    processed: dict[str, str] = {}
    for k, val in fields.items():
        k_low = k.lower()
        if k_low in _RAW_LINK_FIELDS:
            val = clean_doi_url_value(k_low, val)
        elif k_low == "pages":
            val = normalize_pages(val)
            val = escape_latex_special_outside_math(val)
        elif k_low == "title":
            # Strip trailing period added by some aggregators (e.g., DBLP) unless abbreviation/ellipsis
            if val.endswith(".") and not val.endswith("..."):
                val = val[:-1].rstrip()
            val = escape_latex_special_outside_math(val)
            if protect_title_case:
                val = apply_title_case_protection(val)
        else:
            val = escape_latex_special_outside_math(val)

        # Collapse multi-line whitespace inside fields into clean single spaces
        val = re.sub(r"\s+", " ", val).strip()
        if val:
            processed[k] = val

    # Order fields predictably while keeping any custom publisher fields at the end
    ordered_keys: list[str] = []
    lower_to_actual = {k.lower(): k for k in processed}
    for pref in _PREFERRED_FIELD_ORDER:
        if pref in lower_to_actual:
            ordered_keys.append(lower_to_actual[pref])
    for k in processed:
        if k not in ordered_keys:
            ordered_keys.append(k)

    lines = [f"@{etype}{{{cite_key},"]
    for idx, key_name in enumerate(ordered_keys):
        comma = "," if idx < len(ordered_keys) - 1 else ""
        lines.append(f"  {key_name} = {{{processed[key_name]}}}{comma}")
    lines.append("}")
    return "\n".join(lines)
