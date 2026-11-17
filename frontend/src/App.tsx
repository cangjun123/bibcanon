import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelScanJob,
  clearCacheApi,
  createScanJob,
  fetchBootstrap,
  fetchCacheStats,
  pasteMergeEntry,
  renderExportBib,
  retrySingleEntry,
  saveSettings,
  subscribeJobStream,
  writeLocalBib,
} from "./api/client";
import { DiffWorkbench } from "./components/DiffWorkbench";
import { EntryList } from "./components/EntryList";
import { SettingsModal } from "./components/SettingsModal";
import { TopToolbar } from "./components/TopToolbar";
import {
  AppConfig,
  CacheStats,
  DecisionPayload,
  EntryAuditResult,
  FilterTab,
  StyleMode,
} from "./types";
import { isEntryAlreadyIdentical } from "./utils/bibtexPreview";

const DEFAULT_CONFIG: AppConfig = {
  polite_email: "",
  openalex_api_key: "",
  semantic_scholar_api_key: "",
  proxy_url: "",
  noise_field_blacklist: [
    "abstract",
    "file",
    "local-url",
    "mendeley-tags",
    "zotero-key",
    "annote",
    "biburl",
    "bibsource",
    "timestamp",
  ],
  cache_ttl_days: 30,
  default_protect_title_case: true,
  default_style_mode: "canonical",
};

export const App: React.FC = () => {
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [jobId, setJobId] = useState<string | null>(null);
  const [sourcePath, setSourcePath] = useState<string | null>(null);
  const [entries, setEntries] = useState<EntryAuditResult[]>([]);
  const [decisions, setDecisions] = useState<Record<string, DecisionPayload>>(
    {}
  );
  const [userTouchedKeys, setUserTouchedKeys] = useState<Set<string>>(
    new Set()
  );

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterTab>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [styleMode, setStyleMode] = useState<StyleMode>("canonical");
  const [protectTitleCase, setProtectTitleCase] = useState<boolean>(true);

  const [isScanning, setIsScanning] = useState(false);
  const [progress, setProgress] = useState({ completed: 0, total: 0 });
  const [toast, setToast] = useState<{
    text: string;
    tone: "success" | "error" | "info";
  } | null>(null);

  const unsubRef = useRef<(() => void) | null>(null);
  const userTouchedRef = useRef<Set<string>>(new Set());
  userTouchedRef.current = userTouchedKeys;

  const showToast = useCallback(
    (text: string, tone: "success" | "error" | "info" = "info") => {
      setToast({ text, tone });
      window.setTimeout(() => {
        setToast((prev) => (prev?.text === text ? null : prev));
      }, 4500);
    },
    []
  );

  const launchJob = useCallback(
    async (params: {
      bib_content?: string;
      bib_path?: string;
      force_refresh?: boolean;
    }) => {
      if (unsubRef.current) {
        unsubRef.current();
        unsubRef.current = null;
      }
      try {
        const res = await createScanJob(params);
        setJobId(res.job_id);
        setSourcePath(res.source_path);
        setEntries(res.entries);
        setDecisions({});
        setUserTouchedKeys(new Set());
        setActiveFilter("all");
        setSelectedKey(res.entries[0]?.cite_key ?? null);
        setProgress({ completed: 0, total: res.total_entries });
        setIsScanning(res.total_entries > 0);

        if (res.total_entries > 0) {
          unsubRef.current = subscribeJobStream(res.job_id, {
            onEntryUpdated: ({ entry, completed, total }) => {
              setProgress({ completed, total });
              setEntries((prev) =>
                prev.map((item) =>
                  item.entry_index === entry.entry_index ? entry : item
                )
              );
              if (!userTouchedRef.current.has(entry.cite_key)) {
                setDecisions((prev) => ({
                  ...prev,
                  [entry.cite_key]: {
                    decision: entry.decision,
                    selected_candidate_idx: entry.selected_candidate_idx ?? 0,
                  },
                }));
              }
            },
            onJobCompleted: ({ entries: finalEntries, completed, total }) => {
              setEntries(finalEntries);
              setProgress({ completed, total });
              setIsScanning(false);
              fetchCacheStats()
                .then(setCacheStats)
                .catch(() => {});
              showToast(`已完成全部 ${total} 条引用的核验`, "success");
            },
            onJobCancelled: ({ completed, total }) => {
              setIsScanning(false);
              showToast(`已中止扫描（已完成 ${completed}/${total} 条）`, "info");
            },
            onError: () => {
              setIsScanning(false);
            },
          });
        }
      } catch (err) {
        showToast(
          err instanceof Error ? err.message : "创建扫描任务失败",
          "error"
        );
      }
    },
    [showToast]
  );

  useEffect(() => {
    let mounted = true;
    fetchBootstrap()
      .then((boot) => {
        if (!mounted) return;
        setConfig(boot.settings);
        setCacheStats(boot.cache_stats);
        setStyleMode(boot.settings.default_style_mode);
        setProtectTitleCase(boot.settings.default_protect_title_case);
        if (boot.initial_bib_path) {
          launchJob({ bib_path: boot.initial_bib_path, force_refresh: false });
        }
      })
      .catch(() => {});
    return () => {
      mounted = false;
      if (unsubRef.current) unsubRef.current();
    };
  }, [launchJob]);

  const matchesFilterTab = useCallback(
    (entry: EntryAuditResult, tab: FilterTab): boolean => {
      switch (tab) {
        case "all":
          return true;
        case "hallucination":
          return entry.status === "SUSPECTED_HALLUCINATION";
        case "mismatch":
          return entry.status === "METADATA_MISMATCH" || entry.status === "ERROR";
        case "upgrade":
          return entry.status === "PREPRINT_UPGRADE";
        case "updatable":
          return (
            (entry.status === "VERIFIED_CANONICAL" ||
              entry.status === "VERIFIED_PREPRINT_ONLY") &&
            !isEntryAlreadyIdentical(entry, styleMode, protectTitleCase)
          );
        case "identical":
          return (
            (entry.status === "VERIFIED_CANONICAL" ||
              entry.status === "VERIFIED_PREPRINT_ONLY") &&
            isEntryAlreadyIdentical(entry, styleMode, protectTitleCase)
          );
        case "duplicate":
          return entry.warnings.some((w) => w.code === "DUPLICATE_IN_BIB");
      }
    },
    [styleMode, protectTitleCase]
  );

  const filterCounts = useMemo<Record<FilterTab, number>>(() => {
    const counts: Record<FilterTab, number> = {
      all: entries.length,
      hallucination: 0,
      mismatch: 0,
      upgrade: 0,
      updatable: 0,
      identical: 0,
      duplicate: 0,
    };
    for (const e of entries) {
      if (matchesFilterTab(e, "hallucination")) counts.hallucination++;
      if (matchesFilterTab(e, "mismatch")) counts.mismatch++;
      if (matchesFilterTab(e, "upgrade")) counts.upgrade++;
      if (matchesFilterTab(e, "updatable")) counts.updatable++;
      if (matchesFilterTab(e, "identical")) counts.identical++;
      if (matchesFilterTab(e, "duplicate")) counts.duplicate++;
    }
    return counts;
  }, [entries, matchesFilterTab]);

  const filteredEntries = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return entries.filter((entry) => {
      if (!matchesFilterTab(entry, activeFilter)) return false;
      if (!q) return true;
      const cand = entry.candidates[0];
      const hay = [
        entry.cite_key,
        entry.original_fields.title,
        entry.original_fields.author,
        entry.original_fields.booktitle,
        entry.original_fields.journal,
        cand?.matched_title,
        cand?.canonical_venue_id,
        cand?.bibtex_origin,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [entries, activeFilter, searchQuery, matchesFilterTab]);

  // Keyboard up/down navigation in left list
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || settingsOpen) return;
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      if (filteredEntries.length === 0) return;

      e.preventDefault();
      const idx = filteredEntries.findIndex((item) => item.cite_key === selectedKey);
      if (e.key === "ArrowDown") {
        const next =
          idx < 0
            ? filteredEntries[0]
            : filteredEntries[Math.min(filteredEntries.length - 1, idx + 1)];
        setSelectedKey(next.cite_key);
      } else if (e.key === "ArrowUp") {
        const prev =
          idx <= 0 ? filteredEntries[0] : filteredEntries[idx - 1];
        setSelectedKey(prev.cite_key);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filteredEntries, selectedKey, settingsOpen]);

  const selectedEntry = useMemo(
    () => entries.find((e) => e.cite_key === selectedKey) ?? null,
    [entries, selectedKey]
  );

  const updateDecision = useCallback(
    (citeKey: string, patch: Partial<DecisionPayload>) => {
      setUserTouchedKeys((prev) => new Set(prev).add(citeKey));
      setDecisions((prev) => {
        const existing = prev[citeKey] ?? {
          decision: "keep_original",
          selected_candidate_idx: 0,
        };
        return {
          ...prev,
          [citeKey]: {
            ...existing,
            ...patch,
          },
        };
      });
    },
    []
  );

  const handleBatchAcceptHighConfidence = () => {
    let count = 0;
    const nextDecisions = { ...decisions };
    const touched = new Set(userTouchedKeys);

    for (const e of entries) {
      const hasSeriousWarn = e.warnings.some(
        (w) => w.severity === "error" || w.severity === "warning"
      );
      const isHighConf =
        (e.status === "VERIFIED_CANONICAL" ||
          e.status === "PREPRINT_UPGRADE" ||
          e.status === "VERIFIED_PREPRINT_ONLY") &&
        e.confidence >= 88 &&
        !hasSeriousWarn &&
        e.candidates.length > 0 &&
        !isEntryAlreadyIdentical(e, styleMode, protectTitleCase);

      if (isHighConf) {
        nextDecisions[e.cite_key] = {
          ...(nextDecisions[e.cite_key] ?? {}),
          decision: "accept",
          selected_candidate_idx:
            nextDecisions[e.cite_key]?.selected_candidate_idx ??
            e.selected_candidate_idx ??
            0,
        };
        touched.add(e.cite_key);
        count++;
      }
    }
    setDecisions(nextDecisions);
    setUserTouchedKeys(touched);
    showToast(`已选中 ${count} 条高置信度可更新条目（存疑条目已跳过）`, "success");
  };

  const acceptedCount = useMemo(() => {
    let n = 0;
    for (const e of entries) {
      const d = decisions[e.cite_key]?.decision ?? e.decision;
      if (d === "accept" || d === "custom") n++;
    }
    return n;
  }, [entries, decisions]);

  const buildDecisionsMap = useCallback((): Record<string, DecisionPayload> => {
    const out: Record<string, DecisionPayload> = {};
    for (const e of entries) {
      out[e.cite_key] = decisions[e.cite_key] ?? {
        decision: e.decision,
        selected_candidate_idx: e.selected_candidate_idx ?? 0,
        custom_bibtex: e.custom_bibtex,
      };
    }
    return out;
  }, [entries, decisions]);

  const handleCopyBib = async () => {
    if (!jobId) return;
    try {
      const res = await renderExportBib({
        job_id: jobId,
        style_mode: styleMode,
        protect_title_case: protectTitleCase,
        decisions: buildDecisionsMap(),
      });
      await navigator.clipboard.writeText(res.output_bibtex);
      showToast(
        `已复制完整 .bib 全文（采纳 ${
          res.stats.accepted_count + res.stats.custom_count
        } 条，原样保留 ${res.stats.kept_original_count} 条）`,
        "success"
      );
    } catch (err) {
      showToast(err instanceof Error ? err.message : "导出复制失败", "error");
    }
  };

  const handleDownloadBib = async () => {
    if (!jobId) return;
    try {
      const res = await renderExportBib({
        job_id: jobId,
        style_mode: styleMode,
        protect_title_case: protectTitleCase,
        decisions: buildDecisionsMap(),
      });
      const blob = new Blob([res.output_bibtex], {
        type: "text/plain;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "references.bibcanon.bib";
      a.click();
      URL.revokeObjectURL(url);
      showToast("已开始下载 references.bibcanon.bib", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "下载失败", "error");
    }
  };

  const handleWriteLocalBib = async () => {
    if (!jobId || !sourcePath) return;
    try {
      const res = await writeLocalBib({
        job_id: jobId,
        style_mode: styleMode,
        protect_title_case: protectTitleCase,
        target_bib_path: sourcePath,
        decisions: buildDecisionsMap(),
      });
      showToast(
        `已写回本地文件！原文件已自动备份至: ${res.backup_path}`,
        "success"
      );
    } catch (err) {
      showToast(err instanceof Error ? err.message : "写回本地文件失败", "error");
    }
  };

  const handleRetryEntry = async (citeKey: string, overrideTitle?: string) => {
    if (!jobId) return;
    try {
      const updated = await retrySingleEntry(jobId, citeKey, overrideTitle);
      setEntries((prev) =>
        prev.map((item) => (item.cite_key === citeKey ? updated : item))
      );
      setDecisions((prev) => ({
        ...prev,
        [citeKey]: {
          decision: updated.decision,
          selected_candidate_idx: updated.selected_candidate_idx ?? 0,
        },
      }));
      showToast(`已完成 ${citeKey} 的重新检索`, "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "单条重查失败", "error");
    }
  };

  const handlePasteMerge = async (citeKey: string, pastedBibtex: string) => {
    if (!jobId) return;
    const updated = await pasteMergeEntry(jobId, citeKey, pastedBibtex);
    setEntries((prev) =>
      prev.map((item) => (item.cite_key === citeKey ? updated : item))
    );
    setUserTouchedKeys((prev) => new Set(prev).add(citeKey));
    setDecisions((prev) => ({
      ...prev,
      [citeKey]: {
        decision: "accept",
        selected_candidate_idx: 0,
        custom_bibtex: null,
      },
    }));
    showToast(`已锁死 ${citeKey} 并合并外部 BibTeX`, "success");
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-50">
      <TopToolbar
        isScanning={isScanning}
        progress={progress}
        sourcePath={sourcePath}
        activeFilter={activeFilter}
        filterCounts={filterCounts}
        styleMode={styleMode}
        protectTitleCase={protectTitleCase}
        hasEntries={entries.length > 0}
        acceptedCount={acceptedCount}
        onStartScanContent={(content, force) =>
          launchJob({ bib_content: content, force_refresh: force })
        }
        onStartScanPath={(path, force) =>
          launchJob({ bib_path: path, force_refresh: force })
        }
        onCancelScan={() => {
          if (jobId) cancelScanJob(jobId);
          if (unsubRef.current) unsubRef.current();
          setIsScanning(false);
        }}
        onChangeFilter={setActiveFilter}
        onChangeStyleMode={setStyleMode}
        onToggleProtectTitleCase={setProtectTitleCase}
        onBatchAcceptHighConfidence={handleBatchAcceptHighConfidence}
        onCopyBib={handleCopyBib}
        onDownloadBib={handleDownloadBib}
        onWriteLocalBib={handleWriteLocalBib}
        onOpenSettings={() => {
          fetchCacheStats()
            .then(setCacheStats)
            .catch(() => {});
          setSettingsOpen(true);
        }}
      />

      {/* Main Split Workspace: Left 32% List + Right 68% Diff Workbench */}
      <div className="flex flex-1 overflow-hidden">
        <div className="w-[32%] min-w-[300px] max-w-[460px] h-full">
          <EntryList
            entries={filteredEntries}
            selectedKey={selectedKey}
            searchQuery={searchQuery}
            decisions={decisions}
            onSearchChange={setSearchQuery}
            onSelectEntry={setSelectedKey}
            onToggleDecision={(entry, checked) =>
              updateDecision(entry.cite_key, {
                decision: checked ? "accept" : "keep_original",
              })
            }
          />
        </div>

        <div className="flex-1 h-full overflow-hidden">
          <DiffWorkbench
            entry={selectedEntry}
            decisionPayload={
              selectedEntry ? decisions[selectedEntry.cite_key] : undefined
            }
            styleMode={styleMode}
            protectTitleCase={protectTitleCase}
            onUpdateDecision={updateDecision}
            onRetryEntry={handleRetryEntry}
            onPasteMerge={handlePasteMerge}
            onJumpToEntry={(targetKey) => {
              setActiveFilter("all");
              setSearchQuery("");
              setSelectedKey(targetKey);
            }}
          />
        </div>
      </div>

      {/* Toast Notification */}
      {toast && (
        <div
          className={`fixed bottom-5 right-5 z-50 rounded-lg border px-4 py-2.5 text-xs font-medium shadow-lg transition ${
            toast.tone === "success"
              ? "border-emerald-300 bg-emerald-900 text-white"
              : toast.tone === "error"
              ? "border-rose-300 bg-rose-900 text-white"
              : "border-slate-700 bg-slate-900 text-white"
          }`}
        >
          {toast.text}
        </div>
      )}

      <SettingsModal
        open={settingsOpen}
        config={config}
        cacheStats={cacheStats}
        onClose={() => setSettingsOpen(false)}
        onSave={async (newCfg) => {
          const saved = await saveSettings(newCfg);
          setConfig(saved);
          showToast("全局设置已保存", "success");
        }}
        onClearCache={async (scope) => {
          const res = await clearCacheApi(scope);
          const stats = await fetchCacheStats();
          setCacheStats(stats);
          showToast(`已清理缓存 (${res.deleted_entries} 条记录)`, "success");
        }}
      />
    </div>
  );
};

export default App;
