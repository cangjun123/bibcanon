export type VerificationStatus =
  | "VERIFIED_CANONICAL"
  | "PREPRINT_UPGRADE"
  | "VERIFIED_PREPRINT_ONLY"
  | "METADATA_MISMATCH"
  | "SUSPECTED_HALLUCINATION"
  | "UNPROCESSED"
  | "ERROR";

export type WarningCode =
  | "DUPLICATE_IN_BIB"
  | "INVALID_DOI"
  | "INVALID_ARXIV_ID"
  | "FALSE_PUBLISHED_VENUE"
  | "VENUE_DIFFERS_FROM_ORIGINAL"
  | "JOURNAL_EXTENSION_AVAILABLE"
  | "AUTHOR_MISMATCH"
  | "YEAR_DISCREPANCY";

export type VenueTier = "JOURNAL" | "MAIN_CONF" | "WORKSHOP" | "PREPRINT";
export type DecisionType = "accept" | "keep_original" | "custom";
export type StyleMode = "canonical" | "compact";
export type WarningSeverity = "error" | "warning" | "info";

export type FilterTab =
  | "all"
  | "attention"
  | "upgrade"
  | "updatable"
  | "identical";

export interface AuditWarning {
  code: WarningCode;
  severity: WarningSeverity;
  message: string;
  other_cite_keys: string[];
}

export interface CandidateRecord {
  source_discovery: string;
  bibtex_origin: string;
  venue_tier: VenueTier;
  canonical_venue_id: string | null;
  score: number;
  score_breakdown: Record<string, number>;
  matched_title: string;
  matched_authors: string[];
  matched_year: number | null;
  matched_venue: string | null;
  doi: string | null;
  arxiv_id: string | null;
  url: string | null;
  ee_urls: string[];
  dblp_key: string | null;
  dblp_type: string | null;
  crossref_extra: Record<string, unknown>;
  entry_type: string;
  raw_publisher_fields: Record<string, string>;
  canonical_bibtex: string;
  compact_bibtex: string;
}

export interface EntryAuditResult {
  cite_key: string;
  entry_index: number;
  span_start: number;
  span_end: number;
  original_bibtex: string;
  original_fields: Record<string, string>;
  status: VerificationStatus;
  confidence: number;
  warnings: AuditWarning[];
  selected_candidate_idx: number | null;
  candidates: CandidateRecord[];
  decision: DecisionType;
  custom_bibtex: string | null;
  search_links: Record<string, string>;
}

export interface DecisionPayload {
  decision: DecisionType;
  selected_candidate_idx?: number | null;
  custom_bibtex?: string | null;
  override_cite_key?: string | null;
}

export interface AppConfig {
  polite_email: string;
  openalex_api_key: string;
  semantic_scholar_api_key: string;
  proxy_url: string;
  noise_field_blacklist: string[];
  cache_ttl_days: number;
  default_protect_title_case: boolean;
  default_style_mode: StyleMode;
}

export interface CacheStats {
  db_path: string;
  db_size_bytes: number;
  query_cache_count: number;
  cvf_toc_venues_count: number;
  cvf_toc_papers_count: number;
}

export interface AuthStatusResponse {
  auth_required: boolean;
  authenticated: boolean;
  cloud_mode: boolean;
  username: string | null;
}

export interface BootstrapResponse {
  initial_bib_path: string | null;
  cloud_mode?: boolean;
  username?: string | null;
  settings: AppConfig;
  cache_stats: CacheStats;
}

export interface CreateJobResponse {
  job_id: string;
  total_entries: number;
  source_path: string | null;
  entries: EntryAuditResult[];
}

export interface ExportStats {
  total_entries: number;
  accepted_count: number;
  kept_original_count: number;
  custom_count: number;
}

export interface ExportRenderResponse {
  output_bibtex: string;
  stats: ExportStats;
}

export interface ExportWriteLocalResponse extends ExportRenderResponse {
  backup_path: string;
  target_bib_path: string;
}
