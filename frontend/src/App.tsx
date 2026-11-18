import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelScanJob,
  clearCacheApi,
  createScanJob,
  fetchAuthStatus,
  fetchBootstrap,
  fetchCacheStats,
  loginApi,
  logoutApi,
  pasteMergeEntry,
  renderExportBib,
  retrySingleEntry,
  saveSettings,
  subscribeJobStream,
  writeLocalBib,
} from "./api/client";
import { DiffWorkbench } from "./components/DiffWorkbench";
import { EntryList } from "./components/EntryList";
import { ImportModal } from "./components/ImportModal";
import { LoginScreen } from "./components/LoginScreen";
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
import { copyTextToClipboard } from "./utils/clipboard";

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
  const [authChecking, setAuthChecking] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [authenticated, setAuthenticated] = useState(true);
  const [cloudMode, setCloudMode] = useState(false);

  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);

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
      }, 4000);
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
              showToast(`扫描已停止（已完成 ${completed}/${total} 条）`, "info");
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

  const loadBootstrap = useCallback(async () => {
    const boot = await fetchBootstrap();
    setConfig(boot.settings);
    setCacheStats(boot.cache_stats);
    setCloudMode(Boolean(boot.cloud_mode));
    setStyleMode(boot.settings.default_style_mode);
    setProtectTitleCase(boot.settings.default_protect_title_case);
    if (boot.initial_bib_path && !boot.cloud_mode) {
      launchJob({ bib_path: boot.initial_bib_path, force_refresh: false });
    }
  }, [launchJob]);

  useEffect(() => {
    let mounted = true;
    fetchAuthStatus()
      .then(async (status) => {
        if (!mounted) return;
        setAuthRequired(status.auth_required);
        setAuthenticated(status.authenticated);
        setCloudMode(status.cloud_mode);
        if (status.authenticated) {
          await loadBootstrap();
        }
      })
      .catch(() => {})
      .finally(() => {
        if (mounted) setAuthChecking(false);
      });
    return () => {
      mounted = false;
      if (unsubRef.current) unsubRef.current();
    };
  }, [loadBootstrap]);

  const matchesFilterTab = useCallback(
    (entry: EntryAuditResult, tab: FilterTab): boolean => {
      const hasDup = entry.warnings.some((w) => w.code === "DUPLICATE_IN_BIB");
      switch (tab) {
        case "all":
          return true;
        case "attention":
          return (
            entry.status === "SUSPECTED_HALLUCINATION" ||
            entry.status === "METADATA_MISMATCH" ||
            entry.status === "ERROR" ||
            hasDup
          );
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
      }
    },
    [styleMode, protectTitleCase]
  );

  const filterCounts = useMemo<Record<FilterTab, number>>(() => {
    const counts: Record<FilterTab, number> = {
      all: entries.length,
      attention: 0,
      upgrade: 0,
      updatable: 0,
      identical: 0,
    };
    for (const e of entries) {
      if (matchesFilterTab(e, "attention")) counts.attention++;
      if (matchesFilterTab(e, "upgrade")) counts.upgrade++;
      if (matchesFilterTab(e, "updatable")) counts.updatable++;
      if (matchesFilterTab(e, "identical")) counts.identical++;
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

  // Keyboard up/down navigation
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        settingsOpen ||
        importModalOpen
      )
        return;
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      if (filteredEntries.length === 0) return;

      e.preventDefault();
      const idx = filteredEntries.findIndex(
        (item) => item.cite_key === selectedKey
      );
      if (e.key === "ArrowDown") {
        const next =
          idx < 0
            ? filteredEntries[0]
            : filteredEntries[Math.min(filteredEntries.length - 1, idx + 1)];
        setSelectedKey(next.cite_key);
      } else if (e.key === "ArrowUp") {
        const prev = idx <= 0 ? filteredEntries[0] : filteredEntries[idx - 1];
        setSelectedKey(prev.cite_key);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filteredEntries, selectedKey, settingsOpen, importModalOpen]);

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
    showToast(`已勾选 ${count} 条高置信度更新（存疑条目已跳过）`, "success");
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
      await copyTextToClipboard(res.output_bibtex);
      showToast(
        `已复制完整 .bib（更新 ${
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
      showToast(`已写回原文件，备份已保存至: ${res.backup_path}`, "success");
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
    showToast(`已合并外部 BibTeX 并锁死键值 ${citeKey}`, "success");
  };

  const hasEntries = entries.length > 0;

  if (authChecking) {
    return <div className="min-h-screen bg-[#F8FAFC]" />;
  }

  if (authRequired && !authenticated) {
    return (
      <LoginScreen
        onLogin={async (username, password) => {
          await loginApi(username, password);
          setAuthenticated(true);
          await loadBootstrap();
        }}
      />
    );
  }

  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={async (e) => {
        const f = e.dataTransfer.files?.[0];
        if (f && (f.name.endsWith(".bib") || f.type.startsWith("text"))) {
          e.preventDefault();
          const text = await f.text();
          launchJob({ bib_content: text, force_refresh: false });
          setImportModalOpen(false);
        }
      }}
      className="flex h-screen flex-col overflow-hidden bg-[#F8FAFC] text-slate-900"
    >
      <TopToolbar
        isScanning={isScanning}
        progress={progress}
        sourcePath={sourcePath}
        cloudMode={cloudMode}
        styleMode={styleMode}
        protectTitleCase={protectTitleCase}
        hasEntries={hasEntries}
        acceptedCount={acceptedCount}
        onOpenImport={() => setImportModalOpen(true)}
        onCancelScan={() => {
          if (jobId) cancelScanJob(jobId);
          if (unsubRef.current) unsubRef.current();
          setIsScanning(false);
        }}
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
        onLogout={async () => {
          await logoutApi();
          if (unsubRef.current) unsubRef.current();
          setEntries([]);
          setJobId(null);
          setAuthenticated(false);
        }}
      />

      {!hasEntries ? (
        <ImportModal
          isModal={false}
          open={true}
          cloudMode={cloudMode}
          initialPath={sourcePath}
          isScanning={isScanning}
          onStartScanContent={(content, force) =>
            launchJob({ bib_content: content, force_refresh: force })
          }
          onStartScanPath={(path, force) =>
            launchJob({ bib_path: path, force_refresh: force })
          }
        />
      ) : (
        <div className="flex flex-1 overflow-hidden">
          <div className="w-[31%] min-w-[290px] max-w-[420px] h-full">
            <EntryList
              entries={filteredEntries}
              selectedKey={selectedKey}
              activeFilter={activeFilter}
              filterCounts={filterCounts}
              searchQuery={searchQuery}
              decisions={decisions}
              onChangeFilter={setActiveFilter}
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
      )}

      <ImportModal
        isModal={true}
        open={importModalOpen}
        cloudMode={cloudMode}
        initialPath={sourcePath}
        isScanning={isScanning}
        onClose={() => setImportModalOpen(false)}
        onStartScanContent={(content, force) =>
          launchJob({ bib_content: content, force_refresh: force })
        }
        onStartScanPath={(path, force) =>
          launchJob({ bib_path: path, force_refresh: force })
        }
      />

      {toast && (
        <div
          className={`fixed bottom-5 right-5 z-50 rounded-xl px-4 py-2.5 text-xs font-medium shadow-lg transition ${
            toast.tone === "error"
              ? "bg-rose-600 text-white"
              : "bg-slate-900 text-white"
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
          showToast("设置已保存", "success");
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
