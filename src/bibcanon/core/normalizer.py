"""Text decoding, Unicode/LaTeX normalization, and bibliographic feature extraction."""

from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import quote_plus

from pylatexenc.latex2text import LatexNodes2Text

from bibcanon.core.venue_dict import get_canonical_venue_id, is_preprint_venue
from bibcanon.models import ExtractedEntryFeatures, ParsedBibEntry

_LATEX_CONVERTER = LatexNodes2Text(keep_braced_groups=False)

_SPECIAL_CHAR_MAP = str.maketrans(
    {
        "ß": "ss",
        "ø": "o",
        "Ø": "O",
        "ł": "l",
        "Ł": "L",
        "æ": "ae",
        "Æ": "AE",
        "œ": "oe",
        "Œ": "OE",
        "đ": "d",
        "Đ": "D",
        "ı": "i",
    }
)

_ARXIV_DOI_RE = re.compile(
    r"10\.48550/arxiv\.(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?",
    re.IGNORECASE,
)
_ARXIV_URL_OR_PREFIX_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html|bibtex)/|arxiv\s*:\s*|corr/abs[-/])"
    r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?(?:\.pdf)?\b",
    re.IGNORECASE,
)
_ARXIV_BARE_NEW_RE = re.compile(
    r"(?<![A-Za-z0-9./\-])(\d{2})(\d{2})\.(\d{4,5})(?:v\d+)?(?![A-Za-z0-9./])"
)
_ARXIV_BARE_OLD_RE = re.compile(
    r"(?<![A-Za-z0-9./\-])([a-z\-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?(?![A-Za-z0-9./])",
    re.IGNORECASE,
)
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)")
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_DBLP_AUTHOR_SUFFIX_RE = re.compile(r"\s+\d{4}$")
_NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}
_TEMPLATE_PLACEHOLDER_RE = re.compile(
    r"\b(?:frobnicat(?:e|ion|able)|journal\s+of\s+foo|firstname\s+(?:lastname|alpher))\b",
    re.IGNORECASE,
)


def strip_dblp_author_number(name: str) -> str:
    """Remove DBLP's 4-digit homonym disambiguation suffix (e.g. 'Yang Liu 0001' -> 'Yang Liu')."""
    return _DBLP_AUTHOR_SUFFIX_RE.sub("", name.strip()).strip()


def decode_latex_to_unicode(text: str) -> str:
    """Convert BibTeX/LaTeX escaped strings and HTML entities into clean Unicode."""
    if not text:
        return ""
    unescaped = html.unescape(text)
    # Handle common BibTeX accent forms cleanly before/during pylatexenc conversion
    try:
        decoded = _LATEX_CONVERTER.latex_to_text(unescaped)
    except Exception:
        decoded = unescaped
    # Strip any remaining protective braces and normalize whitespace
    decoded = decoded.replace("{", "").replace("}", "")
    decoded = decoded.replace("\u00a0", " ")
    decoded = re.sub(r"\s+", " ", decoded).strip()
    return decoded


def fold_unicode_accents(text: str) -> str:
    """Fold accented/diacritic characters into base ASCII equivalents (e.g., Schölkopf -> Scholkopf)."""
    if not text:
        return ""
    mapped = text.translate(_SPECIAL_CHAR_MAP)
    decomposed = unicodedata.normalize("NFKD", mapped)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped


def normalize_title(raw_title: str) -> str:
    """Normalize a paper title for fuzzy and exact comparison."""
    if not raw_title:
        return ""
    decoded = decode_latex_to_unicode(raw_title)
    folded = fold_unicode_accents(decoded).lower()
    # Replace hyphens/dashes/slashes with spaces
    folded = re.sub(r"[-–—−/]+", " ", folded)
    # Remove all punctuation except word characters and spaces
    folded = re.sub(r"[^\w\s]", "", folded)
    folded = folded.replace("_", " ")
    return re.sub(r"\s+", " ", folded).strip()


def clean_display_title(raw_title: str) -> str:
    """Clean a raw BibTeX/DBLP title for readable display and external search queries."""
    cleaned = decode_latex_to_unicode(raw_title)
    if cleaned.endswith(".") and not cleaned.endswith("..."):
        cleaned = cleaned[:-1].strip()
    return cleaned


def extract_surname_from_person(raw_person: str) -> str | None:
    """Extract normalized lowercase surname from a single person's name string."""
    if not raw_person:
        return None
    person = strip_dblp_author_number(decode_latex_to_unicode(raw_person))
    person = fold_unicode_accents(person).strip()
    if not person:
        return None

    lowered = person.lower().strip(".")
    if lowered in {"others", "et al", "et al."}:
        return None

    if "," in person:
        # BibTeX "Last, First" or "Last, Jr., First"
        surname_part = person.split(",", 1)[0].strip()
    else:
        tokens = [t for t in re.split(r"\s+", person) if t]
        while len(tokens) > 1 and tokens[-1].lower().rstrip(",") in _NAME_SUFFIXES:
            tokens.pop()
        surname_part = tokens[-1] if tokens else ""

    surname_norm = re.sub(r"[^\w\s\-]", "", surname_part.lower()).strip()
    # Unify hyphenated surname spacing
    surname_norm = re.sub(r"\s+", " ", surname_norm)
    return surname_norm or None


def extract_author_surnames(raw_authors: str | list[str]) -> tuple[list[str], bool]:
    """Extract normalized author surnames and `has_et_al` flag from BibTeX string or list."""
    has_et_al = False
    if isinstance(raw_authors, str):
        if not raw_authors.strip():
            return [], False
        # Replace newlines/tabs with spaces before splitting on BibTeX 'and'
        flat = re.sub(r"\s+", " ", raw_authors.strip())
        parts = re.split(r"\s+and\s+", flat, flags=re.IGNORECASE)
    else:
        parts = list(raw_authors)

    surnames: list[str] = []
    for part in parts:
        cleaned_part = decode_latex_to_unicode(part).strip()
        low = cleaned_part.lower().rstrip(".")
        if low in {"others", "et al"}:
            has_et_al = True
            continue
        surname = extract_surname_from_person(part)
        if surname:
            surnames.append(surname)

    return surnames, has_et_al


def _is_valid_arxiv_yymm(yy_str: str, mm_str: str) -> bool:
    """Validate YYMM for modern arXiv IDs (started 0704 in April 2007)."""
    yy = int(yy_str)
    mm = int(mm_str)
    if not (7 <= yy <= 40 and 1 <= mm <= 12):
        return False
    if yy == 7 and mm < 4:
        return False
    return True


def extract_arxiv_id_from_text(
    text: str | None, *, require_context: bool = False
) -> str | None:
    """Extract bare arXiv ID (without version suffix) from text or URL.

    When `require_context=True` (used for DOI, URL, booktitle, journal, note),
    requires explicit arXiv prefix/domain/DOI so IEEE DOIs like `10.1109/CVPR52733.2024.01363`
    or `10.1109/CVPR.2019.00686` are never misidentified as arXiv IDs.
    """
    if not text:
        return None
    m_doi = _ARXIV_DOI_RE.search(text)
    if m_doi:
        return m_doi.group(1)
    m_ctx = _ARXIV_URL_OR_PREFIX_RE.search(text)
    if m_ctx:
        cand_id = m_ctx.group(1)
        if "." in cand_id and "/" not in cand_id:
            yymm = cand_id.split(".", 1)[0]
            if len(yymm) == 4 and yymm.isdigit() and not _is_valid_arxiv_yymm(yymm[:2], yymm[2:]):
                return None
        return cand_id

    if require_context:
        return None

    for m_new in _ARXIV_BARE_NEW_RE.finditer(text):
        yy_s, mm_s, seq_s = m_new.group(1), m_new.group(2), m_new.group(3)
        if _is_valid_arxiv_yymm(yy_s, mm_s):
            return f"{yy_s}{mm_s}.{seq_s}"

    m_old = _ARXIV_BARE_OLD_RE.search(text)
    if m_old:
        return m_old.group(1)
    return None


def is_template_placeholder(entry: ParsedBibEntry) -> bool:
    """Return True if the entry is a built-in CVPR/ICCV/IEEE LaTeX template dummy entry."""
    hay = " ".join(
        str(entry.fields.get(k, ""))
        for k in ("author", "title", "journal", "booktitle", "note")
    )
    return bool(_TEMPLATE_PLACEHOLDER_RE.search(hay))


def extract_doi_from_text(text: str | None) -> str | None:
    """Extract clean published DOI from text/URL, excluding 10.48550/arXiv.* preprints."""
    if not text:
        return None
    unescaped = html.unescape(text).strip()
    m = _DOI_RE.search(unescaped)
    if not m:
        return None
    doi = m.group(1).rstrip(".,;)}]>\"'")
    if doi.lower().startswith("10.48550/arxiv."):
        return None
    return doi


def extract_year(fields: dict[str, str]) -> int | None:
    """Extract 4-digit publication year from BibTeX fields."""
    for key in ("year", "date"):
        val = fields.get(key, "")
        if val:
            m = _YEAR_RE.search(val)
            if m:
                return int(m.group(1))
    return None


def build_search_links(title: str, first_author: str | None = None) -> dict[str, str]:
    """Build manual fallback search URLs for Google Scholar, Bing, DBLP, and Semantic Scholar."""
    clean_t = clean_display_title(title)
    query_core = f'"{clean_t}"' if clean_t else ""
    if first_author and clean_t:
        scholar_q = f'"{clean_t}" {first_author}'
    else:
        scholar_q = query_core or clean_t

    q_scholar = quote_plus(scholar_q.strip())
    q_title = quote_plus(clean_t.strip())
    return {
        "google_scholar": f"https://scholar.google.com/scholar?q={q_scholar}",
        "bing": f"https://www.bing.com/search?q={quote_plus((clean_t + ' bibtex').strip())}",
        "dblp": f"https://dblp.org/search?q={q_title}",
        "semantic_scholar": f"https://www.semanticscholar.org/search?q={q_title}",
    }


def extract_entry_features(entry: ParsedBibEntry) -> ExtractedEntryFeatures:
    """Extract normalized matching and classification features from a ParsedBibEntry."""
    fields = {k.lower(): v for k, v in entry.fields.items()}
    entry_type = entry.entry_type.lower()

    raw_title = fields.get("title", "")
    norm_title = normalize_title(raw_title)
    words = [w for w in norm_title.split(" ") if w]

    raw_authors = fields.get("author", "")
    surnames, has_et_al = extract_author_surnames(raw_authors)
    first_surname = surnames[0] if surnames else None

    year = extract_year(fields)

    # Extract arXiv ID following SPEC.md priority:
    # eprint (allows bare YYMM.NNNNN) -> journal/booktitle/note/howpublished/doi/url (requires arXiv context)
    arxiv_id: str | None = None
    eprint_val = fields.get("eprint")
    if eprint_val:
        is_arxiv_eprint = fields.get("archiveprefix", "arxiv").strip().lower() in {"", "arxiv"}
        if is_arxiv_eprint:
            arxiv_id = extract_arxiv_id_from_text(eprint_val, require_context=False)

    if not arxiv_id:
        for fkey in ("journal", "booktitle", "note", "howpublished", "doi", "url"):
            val = fields.get(fkey)
            if val:
                candidate_arxiv = extract_arxiv_id_from_text(val, require_context=True)
                if candidate_arxiv:
                    arxiv_id = candidate_arxiv
                    break

    # Extract formal DOI (excluding 10.48550/arXiv.*)
    doi: str | None = None
    for fkey in ("doi", "url", "ee", "note"):
        val = fields.get(fkey)
        if val:
            candidate_doi = extract_doi_from_text(val)
            if candidate_doi:
                doi = candidate_doi
                break

    booktitle = fields.get("booktitle", "").strip()
    journal = fields.get("journal", "").strip()
    howpublished = fields.get("howpublished", "").strip()
    raw_venue = booktitle or journal or None
    canonical_venue_id = get_canonical_venue_id(raw_venue) if raw_venue else None

    # Determine is_preprint per SPEC.md 4.2.5
    has_arxiv_marker = bool(
        arxiv_id
        or fields.get("archiveprefix", "").strip().lower() == "arxiv"
        or "arxiv" in journal.lower()
        or "arxiv" in booktitle.lower()
        or "arxiv" in howpublished.lower()
    )

    if booktitle or journal:
        # Has explicit venue: preprint iff that venue itself is a preprint server (arXiv/CoRR/bioRxiv/etc.)
        is_preprint = is_preprint_venue(booktitle or journal)
    else:
        # No booktitle or journal
        if entry_type in {"unpublished", "techreport"}:
            is_preprint = True
        elif entry_type == "misc" and (has_arxiv_marker or is_preprint_venue(howpublished)):
            is_preprint = True
        elif arxiv_id is not None or bool(fields.get("eprint", "").strip()):
            is_preprint = True
        elif is_preprint_venue(howpublished) or is_preprint_venue(fields.get("note", "")):
            is_preprint = True
        else:
            is_preprint = False

    return ExtractedEntryFeatures(
        cite_key=entry.cite_key,
        entry_type=entry_type,
        raw_title=raw_title,
        normalized_title=norm_title,
        title_word_count=len(words),
        raw_authors=raw_authors,
        author_surnames=surnames,
        first_author_surname=first_surname,
        has_et_al=has_et_al,
        year=year,
        raw_venue=raw_venue,
        canonical_venue_id=canonical_venue_id,
        doi=doi,
        arxiv_id=arxiv_id,
        is_preprint=is_preprint,
    )
