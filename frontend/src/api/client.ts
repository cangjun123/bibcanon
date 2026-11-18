import {
  AppConfig,
  AuthStatusResponse,
  BootstrapResponse,
  CacheStats,
  CreateJobResponse,
  DecisionPayload,
  EntryAuditResult,
  ExportRenderResponse,
  ExportWriteLocalResponse,
  StyleMode,
} from "../types";

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (err?.detail) detail = String(err.detail);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function fetchAuthStatus(): Promise<AuthStatusResponse> {
  const res = await fetch("/api/auth/status");
  return handleJson<AuthStatusResponse>(res);
}

export async function loginApi(
  username: string,
  password: string
): Promise<{ authenticated: boolean; cloud_mode: boolean; username?: string }> {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return handleJson(res);
}

export async function logoutApi(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST" });
}

export async function fetchBootstrap(): Promise<BootstrapResponse> {
  const res = await fetch("/api/bootstrap");
  return handleJson<BootstrapResponse>(res);
}

export async function createScanJob(params: {
  bib_content?: string;
  bib_path?: string;
  force_refresh?: boolean;
}): Promise<CreateJobResponse> {
  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      bib_content: params.bib_content ?? null,
      bib_path: params.bib_path ?? null,
      force_refresh: params.force_refresh ?? false,
    }),
  });
  return handleJson<CreateJobResponse>(res);
}

export function subscribeJobStream(
  jobId: string,
  handlers: {
    onEntryUpdated: (payload: {
      entry: EntryAuditResult;
      completed: number;
      total: number;
    }) => void;
    onJobCompleted: (payload: {
      entries: EntryAuditResult[];
      completed: number;
      total: number;
    }) => void;
    onJobCancelled?: (payload: { completed: number; total: number }) => void;
    onError?: (err: Event) => void;
  }
): () => void {
  const es = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/stream`);

  es.addEventListener("entry_updated", (ev) => {
    try {
      const data = JSON.parse((ev as MessageEvent).data);
      handlers.onEntryUpdated(data);
    } catch {
      // ignore malformed frame
    }
  });

  es.addEventListener("job_completed", (ev) => {
    try {
      const data = JSON.parse((ev as MessageEvent).data);
      handlers.onJobCompleted(data);
    } finally {
      es.close();
    }
  });

  es.addEventListener("job_cancelled", (ev) => {
    try {
      const data = JSON.parse((ev as MessageEvent).data);
      handlers.onJobCancelled?.(data);
    } finally {
      es.close();
    }
  });

  es.onerror = (err) => {
    handlers.onError?.(err);
    es.close();
  };

  return () => es.close();
}

export async function cancelScanJob(jobId: string): Promise<void> {
  await fetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
  });
}

export async function retrySingleEntry(
  jobId: string,
  citeKey: string,
  overrideQueryTitle?: string
): Promise<EntryAuditResult> {
  const res = await fetch(
    `/api/jobs/${encodeURIComponent(jobId)}/entries/${encodeURIComponent(citeKey)}/retry`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        override_query_title: overrideQueryTitle || null,
        force_refresh: true,
      }),
    }
  );
  return handleJson<EntryAuditResult>(res);
}

export async function pasteMergeEntry(
  jobId: string,
  citeKey: string,
  pastedBibtex: string
): Promise<EntryAuditResult> {
  const res = await fetch(
    `/api/jobs/${encodeURIComponent(jobId)}/entries/${encodeURIComponent(citeKey)}/paste-merge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pasted_bibtex: pastedBibtex }),
    }
  );
  return handleJson<EntryAuditResult>(res);
}

export async function renderExportBib(params: {
  job_id: string;
  style_mode: StyleMode;
  protect_title_case: boolean;
  decisions: Record<string, DecisionPayload>;
}): Promise<ExportRenderResponse> {
  const res = await fetch("/api/export/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return handleJson<ExportRenderResponse>(res);
}

export async function writeLocalBib(params: {
  job_id: string;
  style_mode: StyleMode;
  protect_title_case: boolean;
  target_bib_path: string;
  decisions: Record<string, DecisionPayload>;
}): Promise<ExportWriteLocalResponse> {
  const res = await fetch("/api/export/write-local", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return handleJson<ExportWriteLocalResponse>(res);
}

export async function fetchSettings(): Promise<AppConfig> {
  const res = await fetch("/api/settings");
  return handleJson<AppConfig>(res);
}

export async function saveSettings(cfg: AppConfig): Promise<AppConfig> {
  const res = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
  return handleJson<AppConfig>(res);
}

export async function fetchCacheStats(): Promise<CacheStats> {
  const res = await fetch("/api/cache/stats");
  return handleJson<CacheStats>(res);
}

export async function clearCacheApi(
  scope: "all" | "queries"
): Promise<{ scope: string; deleted_entries: number }> {
  const res = await fetch(`/api/cache?scope=${scope}`, { method: "DELETE" });
  return handleJson(res);
}
