import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  Edit3,
  ExternalLink,
  Info,
  KeyRound,
  Lock,
  RefreshCw,
  RotateCcw,
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
  const [retrying, setRetrying] = useState(false);
  const [showRetryInput, setShowRetryInput] = useState(false);
  const [overrideTitle, setOverrideTitle] = useState("");
  const [editingKey, setEditingKey] = useState(false);
  const [keyDraft, setKeyDraft] = useState("");

  useEffect(() => {
    setShowRetryInput(false);
    setEditingKey(false);
    if (entry) {
      setOverrideTitle(cleanBraces(entry.original_fields.title));
      setKeyDraft(decisionPayload?.override_cite_key || entry.cite_key);
    }
  }, [entry?.cite_key]);

  if (!entry) {
    return (
      <main className="flex h-full flex-col items-center justify-center bg-slate-50 p-12 text-center">
        <div className="max-w-md rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 font-bold text-xl">
            B
          </div>
          <h2 className="text-base font-bold text-slate-900">
            欢迎使用 bibcanon 参考文献核验工作台
          </h2>
          <p className="mt-2 text-xs leading-relaxed text-slate-600">
            请在上方粘贴 Overleaf 的单个 <code className="font-mono">.bib</code>{" "}
            全文、拖拽上传 <code className="font-mono">.bib</code> 文件，或输入本地{" "}
            <code className="font-mono">.bib</code> 路径开始核验。
          </p>
          <ul className="mt-4 space-y-1.5 text-left text-xs text-slate-500">
            <li>• 100% 锁死原始 Citation Key，无损保留文件内注释与 @string 宏</li>
            <li>• 直连 CVF / PMLR / OpenReview / NeurIPS / ACL / DOI / arXiv 获取官方原汁原味 BibTeX</li>
            <li>• 尊重已写明顶会原意，仅对预印本自动推荐升级正式版</li>
          </ul>
        </div>
      </main>
    );
  }

  const currentDecision: DecisionType =
    decisionPayload?.decision ?? entry.decision;
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

  const handleTriggerRetry = async (customTitle?: string) => {
    setRetrying(true);
    try {
      await onRetryEntry(entry.cite_key, customTitle);
      setShowRetryInput(false);
    } finally {
      setRetrying(false);
    }
  };

  const handleEnterCustomEdit = () => {
    const seed =
      decisionPayload?.custom_bibtex ||
      (activeCand
        ? renderCandidateLivePreview(
            activeCand,
            effectiveCiteKey,
            styleMode,
            protectTitleCase
          )
        : entry.original_bibtex.trim());
    onUpdateDecision(entry.cite_key, {
      decision: "custom",
      custom_bibtex: seed,
    });
  };

  // Metadata comparison rows
  const origVenue =
    entry.original_fields.booktitle ||
    entry.original_fields.journal ||
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
      field: "Title",
      orig: cleanBraces(entry.original_fields.title),
      cand: activeCand ? cleanBraces(activeCand.raw_publisher_fields?.title || activeCand.matched_title) : "-",
    },
    {
      field: "Authors",
      orig: cleanBraces(entry.original_fields.author),
      cand: activeCand
        ? cleanBraces(
            activeCand.raw_publisher_fields?.author ||
              activeCand.matched_authors.join(" and ")
          )
        : "-",
    },
    {
      field: "Venue",
      orig: cleanBraces(origVenue),
      cand: activeCand ? cleanBraces(candVenue) : "-",
    },
    {
      field: "Year",
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
      field: "Pages / ArtNo",
      orig: cleanBraces(origPages),
      cand: activeCand ? cleanBraces(candPages) : "-",
    },
    {
      field: "DOI / arXiv",
      orig: cleanBraces(origId),
      cand: activeCand ? cleanBraces(candId) : "-",
    },
  ];

  return (
    <main className="flex h-full flex-col bg-slate-50 overflow-hidden">
      {/* Top Action Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          {!editingKey ? (
            <div className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2.5 py-1 font-mono text-xs font-bold text-slate-900 border border-slate-200">
              <Lock className="h-3 w-3 text-emerald-600" />
              <span>{effectiveCiteKey}</span>
              <button
                type="button"
                onClick={() => {
                  setKeyDraft(effectiveCiteKey);
                  setEditingKey(true);
                }}
                className="ml-1 text-[10px] font-sans font-normal text-slate-500 hover:text-indigo-600"
                title="默认 100% 锁死原 Citation Key；仅在确实需要重命名时手动解锁"
              >
                修改
              </button>
            </div>
          ) : (
            <div className="inline-flex items-center gap-1">
              <KeyRound className="h-3.5 w-3.5 text-amber-600" />
              <input
                type="text"
                value={keyDraft}
                onChange={(e) => setKeyDraft(e.target.value)}
                className="w-44 rounded border border-amber-400 px-2 py-0.5 font-mono text-xs font-semibold"
              />
              <button
                type="button"
                onClick={() => {
                  const trimmed = keyDraft.trim();
                  onUpdateDecision(entry.cite_key, {
                    override_cite_key:
                      trimmed && trimmed !== entry.cite_key ? trimmed : null,
                  });
                  setEditingKey(false);
                }}
                className="rounded bg-amber-600 px-2 py-0.5 text-xs text-white"
              >
                确认
              </button>
              <button
                type="button"
                onClick={() => {
                  onUpdateDecision(entry.cite_key, { override_cite_key: null });
                  setEditingKey(false);
                }}
                className="rounded border border-slate-300 px-2 py-0.5 text-xs text-slate-600"
              >
                恢复原 Key
              </button>
            </div>
          )}

          <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
            匹配置信度:{" "}
            <strong
              className={
                entry.confidence >= 88
                  ? "text-emerald-700"
                  : entry.confidence >= 65
                  ? "text-amber-700"
                  : "text-rose-700"
              }
            >
              {entry.confidence.toFixed(1)}
            </strong>
          </span>

          <button
            type="button"
            disabled={retrying}
            onClick={() => handleTriggerRetry()}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3 w-3 ${retrying ? "animate-spin text-indigo-600" : ""}`}
            />
            重新检索
          </button>

          <button
            type="button"
            onClick={() => setShowRetryInput((v) => !v)}
            className="text-xs text-indigo-600 hover:underline"
          >
            微调搜索词重查
          </button>
        </div>

        {/* Decision Mode Switcher */}
        <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-0.5 text-xs">
          <button
            type="button"
            disabled={entry.candidates.length === 0}
            onClick={() =>
              onUpdateDecision(entry.cite_key, { decision: "accept" })
            }
            className={`inline-flex items-center gap-1 rounded px-2.5 py-1 font-medium transition disabled:opacity-40 ${
              currentDecision === "accept"
                ? "bg-emerald-600 text-white shadow-sm"
                : "text-slate-700 hover:text-slate-900"
            }`}
          >
            <Check className="h-3.5 w-3.5" />
            采纳候选版
          </button>
          <button
            type="button"
            onClick={() =>
              onUpdateDecision(entry.cite_key, { decision: "keep_original" })
            }
            className={`inline-flex items-center gap-1 rounded px-2.5 py-1 font-medium transition ${
              currentDecision === "keep_original"
                ? "bg-slate-800 text-white shadow-sm"
                : "text-slate-700 hover:text-slate-900"
            }`}
          >
            <RotateCcw className="h-3 w-3" />
            保留原条目
          </button>
          <button
            type="button"
            onClick={handleEnterCustomEdit}
            className={`inline-flex items-center gap-1 rounded px-2.5 py-1 font-medium transition ${
              currentDecision === "custom"
                ? "bg-amber-600 text-white shadow-sm"
                : "text-slate-700 hover:text-slate-900"
            }`}
          >
            <Edit3 className="h-3 w-3" />
            手动微调
          </button>
        </div>
      </div>

      {/* Optional Override Title Search Bar */}
      {showRetryInput && (
        <div className="flex items-center gap-2 border-b border-indigo-100 bg-indigo-50/60 px-4 py-2">
          <span className="text-xs font-medium text-indigo-900 shrink-0">
            自定义检索标题:
          </span>
          <input
            type="text"
            value={overrideTitle}
            onChange={(e) => setOverrideTitle(e.target.value)}
            className="flex-1 rounded border border-indigo-300 bg-white px-2.5 py-1 text-xs text-slate-800"
          />
          <button
            type="button"
            disabled={retrying || !overrideTitle.trim()}
            onClick={() => handleTriggerRetry(overrideTitle.trim())}
            className="rounded bg-indigo-600 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            强制重查
          </button>
        </div>
      )}

      {/* Main Scrollable Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Diagnostic Banners */}
        {entry.status === "PREPRINT_UPGRADE" && activeCand && (
          <div className="flex items-center justify-between rounded-lg border border-indigo-200 bg-indigo-50 px-3.5 py-2 text-xs text-indigo-900">
            <span>
              🔄 <strong>可转正升级：</strong>原条目为预印本，已匹配到正式发表版本{" "}
              <strong>
                {activeCand.canonical_venue_id || activeCand.matched_venue}{" "}
                {activeCand.matched_year ?? ""}
              </strong>{" "}
              （来源：{activeCand.bibtex_origin}）
            </span>
            {activeCand.url && (
              <a
                href={activeCand.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-medium text-indigo-700 hover:underline"
              >
                查看出版页 <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        )}

        {entry.status === "SUSPECTED_HALLUCINATION" && (
          <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2 text-xs text-rose-900">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>
              <strong>疑似虚假引用 / 查无此文：</strong>
              多源学术库均未检索到与该标题和作者吻合的真实论文，请使用下方 Google Scholar / Bing 按钮人工核实！
            </span>
          </div>
        )}

        {entry.status === "ERROR" && (
          <div className="flex items-center gap-2 rounded-lg border border-purple-200 bg-purple-50 px-3.5 py-2 text-xs text-purple-900">
            <AlertTriangle className="h-4 w-4 shrink-0 text-purple-600" />
            <span>
              <strong>网络异常：</strong>
              上游学术接口请求超时或连接受阻（未误判为虚假文献），请检查网络或代理设置后点击“重新检索”。
            </span>
          </div>
        )}

        {entry.warnings.map((w, idx) => {
          const styleMap = {
            error: "border-rose-200 bg-rose-50 text-rose-900",
            warning: "border-amber-200 bg-amber-50 text-amber-900",
            info: "border-sky-200 bg-sky-50 text-sky-900",
          };
          const IconComp =
            w.severity === "error"
              ? AlertCircle
              : w.severity === "warning"
              ? AlertTriangle
              : Info;
          return (
            <div
              key={`${w.code}-${idx}`}
              className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3.5 py-2 text-xs ${
                styleMap[w.severity]
              }`}
            >
              <div className="flex items-center gap-2">
                <IconComp className="h-4 w-4 shrink-0" />
                <span>{w.message}</span>
              </div>
              {w.other_cite_keys.length > 0 && (
                <div className="flex items-center gap-1">
                  <span className="text-[11px] opacity-80">跳转冲突条目:</span>
                  {w.other_cite_keys.map((k) => (
                    <button
                      key={k}
                      type="button"
                      onClick={() => onJumpToEntry(k)}
                      className="rounded bg-white/80 px-1.5 py-0.5 font-mono text-[11px] font-semibold underline hover:bg-white"
                    >
                      {k}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* Multi-Candidate Edition Tabs */}
        {entry.candidates.length > 0 && (
          <div className="rounded-lg border border-slate-200 bg-white p-2.5 shadow-sm">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                候选出版版本切换 ({entry.candidates.length})
              </span>
              {activeCand?.url && (
                <a
                  href={activeCand.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline"
                >
                  打开候选落地页 <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {entry.candidates.map((cand, idx) => {
                const isSelected = idx === selectedCandIdx;
                const venueLabel =
                  cand.canonical_venue_id ||
                  cand.matched_venue ||
                  cand.venue_tier;
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
                    className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs transition ${
                      isSelected
                        ? "border-indigo-600 bg-indigo-50 text-indigo-900 font-semibold shadow-sm"
                        : "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    <span className="rounded bg-white px-1 text-[10px] font-mono border border-slate-200">
                      #{idx + 1}
                    </span>
                    <span>{cand.bibtex_origin || cand.source_discovery}</span>
                    <span className="text-slate-400">·</span>
                    <span>
                      {venueLabel} {cand.matched_year ?? ""}
                    </span>
                    <span className="rounded bg-slate-200/70 px-1 text-[10px] text-slate-700">
                      {cand.score.toFixed(0)}分
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Metadata Field-Level Comparison Table */}
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            核心元数据字段级比对
          </div>
          <table className="w-full table-fixed text-xs">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/50 text-left text-slate-500">
                <th className="w-28 px-3 py-1.5 font-medium">字段</th>
                <th className="px-3 py-1.5 font-medium">原 .bib 条目</th>
                <th className="px-3 py-1.5 font-medium">当前选中候选标准记录</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {metaRows.map((row) => {
                const changed =
                  row.cand !== "-" &&
                  row.orig.toLowerCase() !== row.cand.toLowerCase();
                return (
                  <tr key={row.field} className={changed ? "bg-amber-50/30" : ""}>
                    <td className="px-3 py-1.5 font-mono text-[11px] font-medium text-slate-500">
                      {row.field}
                    </td>
                    <td className="px-3 py-1.5 break-words text-slate-700">
                      {row.orig}
                    </td>
                    <td
                      className={`px-3 py-1.5 break-words ${
                        changed
                          ? "font-medium text-indigo-900 bg-emerald-50/40"
                          : "text-slate-700"
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

        {/* Side-by-Side BibTeX Source Diff / Custom Editor */}
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="grid grid-cols-2 border-b border-slate-200 bg-slate-50 text-xs font-semibold text-slate-700">
            <div className="border-r border-slate-200 px-3 py-2 flex items-center justify-between">
              <span>原始 BibTeX 块</span>
              <span className="text-[11px] font-normal text-slate-400">
                只读对照
              </span>
            </div>
            <div className="px-3 py-2 flex items-center justify-between">
              <span>
                导出预览 BibTeX 块{" "}
                <span className="font-normal text-slate-500">
                  ({styleMode === "canonical" ? "出版方原汁原味" : "省页码缩写"}
                  {protectTitleCase ? " · 大写保护已开启" : ""})
                </span>
              </span>
              {currentDecision !== "custom" ? (
                <button
                  type="button"
                  onClick={handleEnterCustomEdit}
                  className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700 hover:bg-slate-100"
                >
                  <Edit3 className="h-3 w-3" />
                  手动微调
                </button>
              ) : (
                <span className="rounded bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-900">
                  正在手动微调源码
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 divide-x divide-slate-200 font-mono text-xs">
            {/* Left Original BibTeX */}
            <div className="overflow-x-auto bg-slate-50/40 py-2">
              {leftLines.map((line, idx) => (
                <div
                  key={idx}
                  className={`flex px-3 py-0.5 whitespace-pre-wrap break-all ${
                    line.type === "removed"
                      ? "bg-rose-50 text-rose-900"
                      : "text-slate-700"
                  }`}
                >
                  <span className="w-6 shrink-0 select-none text-right pr-2 text-[10px] text-slate-400">
                    {line.lineNo}
                  </span>
                  <span className="w-4 shrink-0 select-none text-rose-500">
                    {line.type === "removed" ? "-" : " "}
                  </span>
                  <span className="flex-1">{line.text}</span>
                </div>
              ))}
            </div>

            {/* Right Target Preview or Custom Textarea */}
            {currentDecision === "custom" ? (
              <div className="p-2 bg-amber-50/20">
                <textarea
                  rows={Math.max(12, targetBibtex.split("\n").length + 2)}
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
                  className="w-full rounded border border-amber-300 bg-white p-2.5 font-mono text-xs leading-relaxed text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            ) : (
              <div className="overflow-x-auto py-2">
                {rightLines.map((line, idx) => (
                  <div
                    key={idx}
                    className={`flex px-3 py-0.5 whitespace-pre-wrap break-all ${
                      line.type === "added"
                        ? "bg-emerald-50 text-emerald-950"
                        : "text-slate-800"
                    }`}
                  >
                    <span className="w-6 shrink-0 select-none text-right pr-2 text-[10px] text-slate-400">
                      {line.lineNo}
                    </span>
                    <span className="w-4 shrink-0 select-none text-emerald-600">
                      {line.type === "added" ? "+" : " "}
                    </span>
                    <span className="flex-1">{line.text}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom Semi-Automatic Fallback Bar */}
      <ManualAssistBar
        entry={entry}
        onPasteMerge={(pasted) => onPasteMerge(entry.cite_key, pasted)}
      />
    </main>
  );
};
