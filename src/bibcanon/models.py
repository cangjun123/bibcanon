"""Core Pydantic models and API schemas for bibcanon."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

DEFAULT_NOISE_BLACKLIST: list[str] = [
    "abstract",
    "file",
    "local-url",
    "mendeley-tags",
    "zotero-key",
    "annote",
    "biburl",
    "bibsource",
    "timestamp",
]


class VerificationStatus(str, Enum):
    """Entry verification status enumeration."""

    VERIFIED_CANONICAL = "VERIFIED_CANONICAL"
    PREPRINT_UPGRADE = "PREPRINT_UPGRADE"
    VERIFIED_PREPRINT_ONLY = "VERIFIED_PREPRINT_ONLY"
    METADATA_MISMATCH = "METADATA_MISMATCH"
    SUSPECTED_HALLUCINATION = "SUSPECTED_HALLUCINATION"
    UNPROCESSED = "UNPROCESSED"
    ERROR = "ERROR"


class WarningCode(str, Enum):
    """Structured diagnostic warning codes."""

    DUPLICATE_IN_BIB = "DUPLICATE_IN_BIB"
    INVALID_DOI = "INVALID_DOI"
    INVALID_ARXIV_ID = "INVALID_ARXIV_ID"
    FALSE_PUBLISHED_VENUE = "FALSE_PUBLISHED_VENUE"
    VENUE_DIFFERS_FROM_ORIGINAL = "VENUE_DIFFERS_FROM_ORIGINAL"
    JOURNAL_EXTENSION_AVAILABLE = "JOURNAL_EXTENSION_AVAILABLE"
    AUTHOR_MISMATCH = "AUTHOR_MISMATCH"
    YEAR_DISCREPANCY = "YEAR_DISCREPANCY"


VenueTier = Literal["JOURNAL", "MAIN_CONF", "WORKSHOP", "PREPRINT"]
DecisionType = Literal["accept", "keep_original", "custom"]
StyleMode = Literal["canonical", "compact"]
WarningSeverity = Literal["error", "warning", "info"]


class AuditWarning(BaseModel):
    """Structured diagnostic warning attached to an audited entry."""

    code: WarningCode
    severity: WarningSeverity
    message: str
    other_cite_keys: list[str] = Field(default_factory=list)


class CandidateRecord(BaseModel):
    """A candidate bibliographic match discovered and enriched from upstream sources."""

    source_discovery: str
    bibtex_origin: str = ""
    venue_tier: VenueTier = "PREPRINT"
    canonical_venue_id: str | None = None
    score: float = 0.0
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    matched_title: str = ""
    matched_authors: list[str] = Field(default_factory=list)
    matched_year: int | None = None
    matched_venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    ee_urls: list[str] = Field(default_factory=list)
    dblp_key: str | None = None
    dblp_type: str | None = None
    crossref_extra: dict[str, Any] = Field(default_factory=dict)
    entry_type: str = "misc"
    raw_publisher_fields: dict[str, str] = Field(default_factory=dict)
    canonical_bibtex: str = ""
    compact_bibtex: str = ""


class EntryAuditResult(BaseModel):
    """Audit result for a single BibTeX entry."""

    cite_key: str
    entry_index: int
    span_start: int
    span_end: int
    original_bibtex: str
    original_fields: dict[str, str] = Field(default_factory=dict)
    status: VerificationStatus = VerificationStatus.UNPROCESSED
    confidence: float = 0.0
    warnings: list[AuditWarning] = Field(default_factory=list)
    selected_candidate_idx: int | None = None
    candidates: list[CandidateRecord] = Field(default_factory=list)
    decision: DecisionType = "keep_original"
    custom_bibtex: str | None = None
    search_links: dict[str, str] = Field(default_factory=dict)


class ParsedBibEntry(BaseModel):
    """Losslessly parsed BibTeX entry with exact character offsets."""

    cite_key: str
    entry_index: int
    entry_type: str
    span_start: int
    span_end: int
    raw_bibtex: str
    fields: dict[str, str] = Field(default_factory=dict)


class ParsedBibDocument(BaseModel):
    """Losslessly parsed BibTeX file preserving full raw text and entry spans."""

    raw_text: str
    entries: list[ParsedBibEntry] = Field(default_factory=list)
    source_path: str | None = None


class ExtractedEntryFeatures(BaseModel):
    """Normalized features extracted from an original BibTeX entry for verification."""

    cite_key: str
    entry_type: str
    raw_title: str = ""
    normalized_title: str = ""
    title_word_count: int = 0
    raw_authors: str = ""
    author_surnames: list[str] = Field(default_factory=list)
    first_author_surname: str | None = None
    has_et_al: bool = False
    year: int | None = None
    raw_venue: str | None = None
    canonical_venue_id: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    is_preprint: bool = False


class AppConfig(BaseModel):
    """Global user configuration persisted in ~/.bibcanon/config.json."""

    polite_email: str = ""
    openalex_api_key: str = ""
    semantic_scholar_api_key: str = ""
    proxy_url: str = ""
    noise_field_blacklist: list[str] = Field(
        default_factory=lambda: list(DEFAULT_NOISE_BLACKLIST)
    )
    cache_ttl_days: int = 30
    default_protect_title_case: bool = True
    default_style_mode: StyleMode = "canonical"


# --- REST & SSE API Schemas ---


class CreateJobRequest(BaseModel):
    """Request payload for POST /api/jobs."""

    bib_content: str | None = None
    bib_path: str | None = None
    force_refresh: bool = False


class CreateJobResponse(BaseModel):
    """Response payload for POST /api/jobs."""

    job_id: str
    total_entries: int
    source_path: str | None = None
    entries: list[EntryAuditResult]


class RetryEntryRequest(BaseModel):
    """Request payload for POST /api/jobs/{job_id}/entries/{cite_key}/retry."""

    override_query_title: str | None = None
    force_refresh: bool = True


class PasteMergeRequest(BaseModel):
    """Request payload for POST /api/jobs/{job_id}/entries/{cite_key}/paste-merge."""

    pasted_bibtex: str


class DecisionPayload(BaseModel):
    """Per-entry user review decision passed during export rendering."""

    decision: DecisionType = "keep_original"
    selected_candidate_idx: int | None = 0
    custom_bibtex: str | None = None
    override_cite_key: str | None = None


class ExportRenderRequest(BaseModel):
    """Request payload for POST /api/export/render."""

    job_id: str
    style_mode: StyleMode = "canonical"
    protect_title_case: bool = True
    decisions: dict[str, DecisionPayload] = Field(default_factory=dict)


class ExportStats(BaseModel):
    """Summary counts returned when rendering or writing exported BibTeX."""

    total_entries: int = 0
    accepted_count: int = 0
    kept_original_count: int = 0
    custom_count: int = 0


class ExportRenderResponse(BaseModel):
    """Response payload for POST /api/export/render."""

    output_bibtex: str
    stats: ExportStats


class ExportWriteLocalRequest(ExportRenderRequest):
    """Request payload for POST /api/export/write-local."""

    target_bib_path: str


class ExportWriteLocalResponse(BaseModel):
    """Response payload for POST /api/export/write-local."""

    output_bibtex: str
    backup_path: str
    target_bib_path: str
    stats: ExportStats


class CacheClearResponse(BaseModel):
    """Response payload for DELETE /api/cache."""

    scope: str
    deleted_entries: int
