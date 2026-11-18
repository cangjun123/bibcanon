import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowUpRight,
  Check,
  Code2,
  Edit3,
  ExternalLink,
  Info,
  Lock,
  RefreshCw,
  RotateCcw,
  Table2,
} from "lucide-react";
import {
  CandidateRecord,
  DecisionPayload,
  DecisionType,
  EntryAuditResult,
  StyleMode,
} from "../types";
import {
  computeSideBySideDiff,
  computeTargetEntryBibtex,
  renderCandidateLivePreview,
} from "../utils/bibtexPreview";
import { ManualAssistBar } from "./ManualAssistBar";

interface DiffWorkbenchProps {
  entry: EntryAuditResult | null;
  decisionPayload: DecisionPayload | undefined;
  styleMode: StyleMode;
  protectTitleCase: boolean;
  onUpdateDecision: (citeKey: string, patch: Partial<DecisionPayload>) => void;
  onRetryEntry: (citeKey: string, overrideTitle?: string) => Promise<void>;
  onPasteMerge: (citeKey: string, pastedBibtex: string) => Promise<void>;
  onJumpToEntry: (citeKey: string) => void;
}

type WorkbenchTab = "bibtex" | "fields" | "edit";

function cleanBraces(val: string | undefined): string {
  if (!val) return "-";
  return val.replace(/[{}]/g, "").replace(/\s+/g, " ").trim() || "-";
}

export const DiffWorkbench: React.FC<DiffWorkbenchProps> = ({
  entry,
  decisionPayload,
  styleMode,
  protectTitleCase,
  onUpdateDecision,
  onRetryEntry,
  onPasteMerge,
  onJumpToEntry,
}) => {
  const [activeTab, setActiveTab] = useState<WorkbenchTab>("bibtex");
  const [retrying, setRetrying] = useState(false);
  const [showRetryBar, setShowRetryBar] = useState(false);
  const [overrideTitle, setOverrideTitle] = useState("");
  const [editingKey, setEditingKey] = useState(false);
  const [keyDraft, setKeyDraft] = useState("");

  const currentDecision: DecisionType =
    decisionPayload?.decision ?? entry?.decision ?? "keep_original";

  useEffect(() => {
    setShowRetryBar(false);
    setEditingKey(false);
    if (entry) {
      setOverrideTitle(cleanBraces(entry.original_fields.title));
      setKeyDraft(decisionPayload?.override_cite_key || entry.cite_key);
      if (
        (decisionPayload?.decision ?? entry.decision) === "custom" &&
        activeTab !== "edit"
      ) {
        setActiveTab("edit");
      } else if (activeTab === "edit" && (decisionPayload?.decision ?? entry.decision) !== "custom") {
        setActiveTab("bibtex");
      }
    }
  }, [entry?.cite_key]);

  if (!entry) {
    return (
      <main className="flex h-full items-center justify-center bg-[#F8FAFC] text-xs text-slate-400">
        请在左侧选择一条引用查看详情
      </main>
    );
  }

  const selectedCandIdx =
    decisionPayload?.selected_candidate_idx ?? entry.selected_candidate_idx ?? 0;
  const activeCand: CandidateRecord | undefined =
    entry.candidates[selectedCandIdx] ?? entry.candidates[0];
  const effectiveCiteKey = decisionPayload?.override_cite_key || entry.cite_key;

  const targetBibtex = computeTargetEntryBibtex(
    entry,
    decisionPayload,
    styleMode,
    protectTitleCase
  );

  const { leftLines, rightLines } = computeSideBySideDiff(
    entry.original_bibtex.trim(),
    targetBibtex
  );

  const origVenue =
    entry.original_fields.booktitle ||
    entry.original_fields.journal ||
    entry.original_fields.institution ||
    entry.original_fields.howpublished ||
    "-";
  const candVenue =
    activeCand?.raw_publisher_fields?.booktitle ||
    activeCand?.raw_publisher_fields?.journal ||
    activeCand?.matched_venue ||
    (activeCand?.arxiv_id ? `arXiv:${activeCand.arxiv_id}` : "-");

  const origPages =
    entry.original_fields.pages || entry.original_fields.articleno || "-";
  const candPages =
    activeCand?.raw_publisher_fields?.pages ||
    activeCand?.raw_publisher_fields?.articleno ||
    "-";

  const origId =
    entry.original_fields.doi || entry.original_fields.eprint || "-";
  const candId =
    activeCand?.doi ||
    activeCand?.raw_publisher_fields?.doi ||
    activeCand?.arxiv_id ||
    activeCand?.raw_publisher_fields?.eprint ||
    "-";

  const metaRows = [
    {
      field: "标题 Title",
      orig: cleanBraces(entry.original_fields.title),
      cand: activeCand
        ? cleanBraces(
            activeCand.raw_publisher_fields?.title || activeCand.matched_title
          )
        : "-",
    },
    {
      field: "作者 Authors",
      orig: cleanBraces(entry.original_fields.author),
      cand: activeCand
        ? cleanBraces(
            activeCand.raw_publisher_fields?.author ||
              activeCand.matched_authors.join(" and ")
          )
        : "-",
    },
    {
      field: "发表场馆 Venue",
      orig: cleanBraces(origVenue),
      cand: activeCand ? cleanBraces(candVenue) : "-",
    },
    {
      field: "年份 Year",
      orig: cleanBraces(entry.original_fields.year),
      cand: activeCand
        ? String(
            activeCand.raw_publisher_fields?.year ??
              activeCand.matched_year ??
              "-"
          )
        : "-",
    },
    {
      field: "页码 Pages",
      orig: cleanBraces(origPages),
      cand: activeCand ? cleanBraces(candPages) : "-",
    },
    {
      field: "标识符 DOI/arXiv",
      orig: cleanBraces(origId),
      cand: activeCand ? cleanBraces(candId) : "-",
    },
  ];

  const changedFieldCount = metaRows.filter(
    (r) => r.cand !== "-" && r.orig.toLowerCase() !== r.cand.toLowerCase()
  ).length;

  const displayTitle =
    activeCand?.matched_title || cleanBraces(entry.original_fields.title);

  const handleTriggerRetry = async (customTitle?: string) => {
    setRetrying(true);
    try {
      await onRetryEntry(entry.cite_key, customTitle);
      setShowRetryBar(false);
    } finally {
      setRetrying(false);
    }
  };

  const handleSwitchToEdit = () => {
    setActiveTab("edit");
    if (currentDecision !== "custom") {
      const seed = activeCand
        ? renderCandidateLivePreview(
            activeCand,
            effectiveCiteKey,
            styleMode,
            protectTitleCase
          )
        : entry.original_bibtex.trim();
      onUpdateDecision(entry.cite_key, {
        decision: "custom",
        custom_bibtex: seed,
      });
    }
  };

  return (
    <main className="flex h-full flex-col bg-[#F8FAFC] overflow-hidden">
      {/* Clean Paper Summary Header */}
      <div className="border-b border-slate-200/90 bg-white px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h1 className="text-sm font-semibold leading-snug text-slate-900">
              {displayTitle}
            </h1>

            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-slate-500">
              {/* Locked Citation Key */}
              {!editingKey ? (
                <button
                  type="button"
                  onClick={() => {
                    setKeyDraft(effectiveCiteKey);
                    setEditingKey(true);
                  }}
                  className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs font-medium text-slate-800 hover:bg-slate-200/70 transition"
                  title="默认 100% 锁死原 Citation Key；点击可手动重命名"
                >
                  <Lock className="h-3 w-3 text-emerald-600" />
                  <span>{effectiveCiteKey}</span>
                </button>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <input
                    type="text"
                    value={keyDraft}
                    onChange={(e) => setKeyDraft(e.target.value)}
                    className="w-40 rounded border border-indigo-400 px-2 py-0.5 font-mono text-xs text-slate-900"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      const t = keyDraft.trim();
                      onUpdateDecision(entry.cite_key, {
                        override_cite_key:
                          t && t !== entry.cite_key ? t : null,
                      });
                      setEditingKey(false);
                    }}
                    className="rounded bg-slate-900 px-2 py-0.5 text-[11px] text-white"
                  >
                    保存
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      onUpdateDecision(entry.cite_key, {
                        override_cite_key: null,
                      });
                      setEditingKey(false);
                    }}
                    className="text-[11px] text-slate-500 hover:text-slate-800"
                  >
                    还原
                  </button>
                </span>
              )}

              {activeCand && (
                <>
                  <span>·</span>
                  <span>
                    来源:{" "}
                    <strong className="font-medium text-slate-700">
                      {activeCand.bibtex_origin}
                    </strong>
                  </span>
                  <span>·</span>
                  <span>
                    匹配度{" "}
                    <strong
                      className={
                        entry.confidence >= 88
                          ? "text-emerald-600"
                          : entry.confidence >= 65
                          ? "text-amber-600"
                          : "text-rose-600"
                      }
                    >
                      {entry.confidence.toFixed(0)}%
                    </strong>
                  </span>
                </>
              )}

              {activeCand?.url && (
                <>
                  <span>·</span>
                  <a
                    href={activeCand.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-0.5 font-medium text-indigo-600 hover:text-indigo-700"
                  >
                    出版页
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </>
              )}

              <span>·</span>
              <button
                type="button"
                disabled={retrying}
                onClick={() => handleTriggerRetry()}
                className="inline-flex items-center gap-1 text-slate-500 hover:text-slate-800 disabled:opacity-40"
              >
                <RefreshCw
                  className={`h-3 w-3 ${retrying ? "animate-spin text-indigo-600" : ""}`}
                />
                重查
              </button>
              <button
                type="button"
                onClick={() => setShowRetryBar((v) => !v)}
                className="text-slate-400 hover:text-slate-700"
              >
                改词重查
              </button>
            </div>
          </div>

          {/* Primary Decision Pill */}
          <div className="inline-flex shrink-0 rounded-lg bg-slate-100 p-1 text-xs font-medium">
            <button
              type="button"
              disabled={entry.candidates.length === 0}
              onClick={() => {
                onUpdateDecision(entry.cite_key, { decision: "accept" });
                if (activeTab === "edit") setActiveTab("bibtex");
              }}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 transition disabled:opacity-35 ${
                currentDecision === "accept"
                  ? "bg-white text-emerald-700 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Check className="h-3.5 w-3.5" />
              采纳新版本
            </button>
            <button
              type="button"
              onClick={() => {
                onUpdateDecision(entry.cite_key, { decision: "keep_original" });
                if (activeTab === "edit") setActiveTab("bibtex");
              }}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
                currentDecision === "keep_original"
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <RotateCcw className="h-3 w-3" />
              保留原条目
            </button>
          </div>
        </div>

        {/* Optional Custom Query Retry Input */}
        {showRetryBar && (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-2">
            <input
              type="text"
              value={overrideTitle}
              onChange={(e) => setOverrideTitle(e.target.value)}
              placeholder="输入调整后的论文标题重新检索..."
              className="flex-1 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-800 focus:border-indigo-500 focus:outline-none"
            />
            <button
              type="button"
              disabled={retrying || !overrideTitle.trim()}
              onClick={() => handleTriggerRetry(overrideTitle.trim())}
              className="rounded-md bg-slate-900 px-3 py-1 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-40"
            >
              重新检索
            </button>
          </div>
        )}

        {/* Concise Callout Alerts (Only rendered when meaningful) */}
        <div className="mt-3 space-y-1.5 empty:hidden">
          {entry.status === "PREPRINT_UPGRADE" && activeCand && (
            <div className="flex items-center gap-2 rounded-lg border border-indigo-100 bg-indigo-50/70 px-3 py-2 text-xs text-indigo-900">
              <ArrowUpRight className="h-4 w-4 shrink-0 text-indigo-600" />
              <span>
                原条目为预印本，已自动匹配正式发表版{" "}
                <strong>
                  {activeCand.canonical_venue_id || activeCand.matched_venue}{" "}
                  {activeCand.matched_year ?? ""}
                </strong>
              </span>
            </div>
          )}

          {entry.status === "SUSPECTED_HALLUCINATION" &&
            entry.warnings.length === 0 && (
              <div className="flex items-center gap-2 rounded-lg border border-rose-200/80 bg-rose-50/70 px-3 py-2 text-xs text-rose-900">
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
                <span>
                  多源学术数据库均未检索到匹配论文，请使用下方外部检索链接人工核查。
                </span>
              </div>
            )}

          {entry.status === "ERROR" && (
            <div className="flex items-center gap-2 rounded-lg border border-purple-200 bg-purple-50/70 px-3 py-2 text-xs text-purple-900">
              <AlertTriangle className="h-4 w-4 shrink-0 text-purple-600" />
              <span>
                上游接口连接超时（未误判为虚假文献），请检查网络或代理后点击“重查”。
              </span>
            </div>
          )}

          {entry.warnings.map((w, idx) => {
            const styles = {
              error: "border-rose-200/80 bg-rose-50/70 text-rose-900",
              warning: "border-amber-200/80 bg-amber-50/70 text-amber-900",
              info: "border-sky-200/80 bg-sky-50/70 text-sky-900",
            };
            const Icon =
              w.severity === "error"
                ? AlertCircle
                : w.severity === "warning"
                ? AlertTriangle
                : Info;
            return (
              <div
                key={`${w.code}-${idx}`}
                className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs ${
                  styles[w.severity]
                }`}
              >
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 shrink-0 opacity-80" />
                  <span>{w.message}</span>
                </div>
                {w.other_cite_keys.length > 0 && (
                  <div className="flex items-center gap-1">
                    <span className="opacity-75">跳转:</span>
                    {w.other_cite_keys.map((k) => (
                      <button
                        key={k}
                        type="button"
                        onClick={() => onJumpToEntry(k)}
                        className="rounded bg-white/80 px-1.5 py-0.5 font-mono text-[11px] font-medium underline hover:bg-white"
                      >
                        {k}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Multi-Edition Switcher (ONLY shown when multiple editions exist!) */}
        {entry.candidates.length > 1 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium text-slate-400 mr-1">
              可选版本:
            </span>
            {entry.candidates.map((cand, idx) => {
              const isSelected = idx === selectedCandIdx;
              const vName =
                cand.canonical_venue_id || cand.matched_venue || cand.venue_tier;
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() =>
                    onUpdateDecision(entry.cite_key, {
                      selected_candidate_idx: idx,
                      decision:
                        currentDecision === "keep_original"
                          ? "accept"
                          : currentDecision,
                    })
                  }
                  className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition ${
                    isSelected
                      ? "border-slate-900 bg-slate-900 text-white font-medium"
                      : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  <span>
                    {vName} {cand.matched_year ?? ""}
                  </span>
                  <span
                    className={`text-[10px] ${
                      isSelected ? "text-slate-300" : "text-slate-400"
                    }`}
                  >
                    {cand.bibtex_origin.replace("DOI Official ", "")}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* View Mode Tabs Bar (Eliminates vertical duplication of Table + Code!) */}
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200/80 bg-white px-6">
        <div className="flex items-center gap-5 text-xs font-medium">
          <button
            type="button"
            onClick={() => setActiveTab("bibtex")}
            className={`inline-flex items-center gap-1.5 border-b-2 py-2.5 transition ${
              activeTab === "bibtex"
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Code2 className="h-3.5 w-3.5" />
            BibTeX 源码对比
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("fields")}
            className={`inline-flex items-center gap-1.5 border-b-2 py-2.5 transition ${
              activeTab === "fields"
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Table2 className="h-3.5 w-3.5" />
            字段级对比
            {changedFieldCount > 0 && (
              <span className="rounded-full bg-slate-100 px-1.5 py-0.2 text-[10px] text-slate-600">
                {changedFieldCount}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={handleSwitchToEdit}
            className={`inline-flex items-center gap-1.5 border-b-2 py-2.5 transition ${
              activeTab === "edit"
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Edit3 className="h-3.5 w-3.5" />
            手动编辑
            {currentDecision === "custom" && (
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            )}
          </button>
        </div>

        <div className="text-[11px] text-slate-400">
          {currentDecision === "keep_original"
            ? "当前状态：导出时保留左侧原条目"
            : currentDecision === "custom"
            ? "当前状态：导出时使用自定义编辑内容"
            : "当前状态：导出时采用右侧标准版本"}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-5">
        {activeTab === "bibtex" && (
          <div className="overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-xs">
            <div className="grid grid-cols-2 border-b border-slate-100 bg-slate-50/70 text-[11px] font-medium text-slate-500">
              <div className="border-r border-slate-100 px-4 py-2">
                原 .bib 条目
              </div>
              <div className="px-4 py-2 flex items-center justify-between">
                <span>导出后结果预览</span>
                <span className="text-slate-400">
                  {styleMode === "canonical" ? "原汁原味" : "缩写省页"}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-2 divide-x divide-slate-100 font-mono text-xs leading-relaxed">
              {/* Left Original */}
              <div className="overflow-x-auto py-3 bg-slate-50/25">
                {leftLines.map((line, idx) => (
                  <div
                    key={idx}
                    className={`flex px-4 py-0.5 whitespace-pre-wrap break-all ${
                      line.type === "removed"
                        ? "bg-rose-50/70 text-rose-900"
                        : "text-slate-600"
                    }`}
                  >
                    <span className="w-6 shrink-0 select-none pr-2 text-right text-[10px] text-slate-300">
                      {line.lineNo}
                    </span>
                    <span className="flex-1">{line.text}</span>
                  </div>
                ))}
              </div>

              {/* Right Target */}
              <div className="overflow-x-auto py-3">
                {rightLines.map((line, idx) => (
                  <div
                    key={idx}
                    className={`flex px-4 py-0.5 whitespace-pre-wrap break-all ${
                      line.type === "added"
                        ? "bg-emerald-50/75 text-emerald-950"
                        : "text-slate-800"
                    }`}
                  >
                    <span className="w-6 shrink-0 select-none pr-2 text-right text-[10px] text-slate-300">
                      {line.lineNo}
                    </span>
                    <span className="flex-1">{line.text}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === "fields" && (
          <div className="overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-xs">
            <table className="w-full table-fixed text-xs">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70 text-left text-[11px] font-medium text-slate-500">
                  <th className="w-32 px-4 py-2.5">字段</th>
                  <th className="px-4 py-2.5">原 .bib 值</th>
                  <th className="px-4 py-2.5">出版方标准值</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {metaRows.map((row) => {
                  const changed =
                    row.cand !== "-" &&
                    row.orig.toLowerCase() !== row.cand.toLowerCase();
                  return (
                    <tr key={row.field}>
                      <td className="px-4 py-2.5 font-medium text-slate-500">
                        {row.field}
                      </td>
                      <td className="px-4 py-2.5 break-words text-slate-600">
                        {row.orig}
                      </td>
                      <td
                        className={`px-4 py-2.5 break-words ${
                          changed
                            ? "bg-emerald-50/50 font-medium text-slate-900"
                            : "text-slate-600"
                        }`}
                      >
                        {row.cand}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === "edit" && (
          <div className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-xs">
            <div className="mb-2.5 flex items-center justify-between text-xs">
              <span className="font-medium text-slate-700">
                直接微调此条目的导出 BibTeX 源码
              </span>
              {activeCand && (
                <button
                  type="button"
                  onClick={() =>
                    onUpdateDecision(entry.cite_key, {
                      decision: "custom",
                      custom_bibtex: renderCandidateLivePreview(
                        activeCand,
                        effectiveCiteKey,
                        styleMode,
                        protectTitleCase
                      ),
                    })
                  }
                  className="text-indigo-600 hover:underline"
                >
                  重置为当前候选标准源码
                </button>
              )}
            </div>
            <textarea
              rows={15}
              value={
                decisionPayload?.custom_bibtex ??
                entry.custom_bibtex ??
                targetBibtex
              }
              onChange={(e) =>
                onUpdateDecision(entry.cite_key, {
                  decision: "custom",
                  custom_bibtex: e.target.value,
                })
              }
              className="w-full rounded-lg border border-slate-200 bg-slate-50/40 p-3 font-mono text-xs leading-relaxed text-slate-900 focus:border-indigo-500 focus:bg-white focus:outline-none"
            />
          </div>
        )}
      </div>

      <ManualAssistBar
        entry={entry}
        onPasteMerge={(pasted) => onPasteMerge(entry.cite_key, pasted)}
      />
    </main>
  );
};
