import React from "react";
import { Search } from "lucide-react";
import { DecisionPayload, EntryAuditResult, VerificationStatus } from "../types";

interface EntryListProps {
  entries: EntryAuditResult[];
  selectedKey: string | null;
  searchQuery: string;
  decisions: Record<string, DecisionPayload>;
  onSearchChange: (q: string) => void;
  onSelectEntry: (citeKey: string) => void;
  onToggleDecision: (entry: EntryAuditResult, checked: boolean) => void;
}

function getStatusBadge(status: VerificationStatus): {
  label: string;
  className: string;
} {
  switch (status) {
    case "VERIFIED_CANONICAL":
      return {
        label: "✅ 标准版",
        className: "bg-emerald-50 text-emerald-700 border-emerald-200",
      };
    case "PREPRINT_UPGRADE":
      return {
        label: "🔄 可转正升级",
        className: "bg-indigo-50 text-indigo-700 border-indigo-200",
      };
    case "VERIFIED_PREPRINT_ONLY":
      return {
        label: "📄 仅预印本",
        className: "bg-sky-50 text-sky-700 border-sky-200",
      };
    case "METADATA_MISMATCH":
      return {
        label: "⚠️ 信息出入",
        className: "bg-amber-50 text-amber-800 border-amber-200",
      };
    case "SUSPECTED_HALLUCINATION":
      return {
        label: "❌ 疑似虚假",
        className: "bg-rose-50 text-rose-700 border-rose-200 font-semibold",
      };
    case "ERROR":
      return {
        label: "⚡ 网络异常",
        className: "bg-purple-50 text-purple-700 border-purple-200",
      };
    case "UNPROCESSED":
    default:
      return {
        label: "⏳ 待处理",
        className: "bg-slate-100 text-slate-600 border-slate-200",
      };
  }
}

function shortOriginBadge(origin: string): string {
  if (!origin) return "";
  if (origin.includes("CVF")) return "CVF";
  if (origin.includes("PMLR")) return "PMLR";
  if (origin.includes("OpenReview")) return "OpenReview";
  if (origin.includes("NeurIPS")) return "NeurIPS";
  if (origin.includes("ACL")) return "ACL";
  if (origin.includes("IEEE")) return "IEEE DOI";
  if (origin.includes("ACM")) return "ACM DOI";
  if (origin.includes("Springer")) return "Springer DOI";
  if (origin.includes("AAAI")) return "AAAI DOI";
  if (origin.includes("arXiv")) return "arXiv";
  if (origin.includes("DBLP")) return "DBLP";
  if (origin.includes("Manual")) return "手动合并";
  return origin.replace("DOI Official ", "");
}

export const EntryList: React.FC<EntryListProps> = ({
  entries,
  selectedKey,
  searchQuery,
  decisions,
  onSearchChange,
  onSelectEntry,
  onToggleDecision,
}) => {
  return (
    <aside className="flex h-full flex-col border-r border-slate-200 bg-white">
      {/* Search Bar */}
      <div className="border-b border-slate-200 p-2.5">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="搜索 cite_key / 标题 / 作者 / 会议 (支持 ↑↓ 键切换)"
            className="w-full rounded-md border border-slate-300 py-1.5 pl-8 pr-2.5 text-xs text-slate-800 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
      </div>

      {/* Scrollable Entry Rows */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
        {entries.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            当前筛选条件下暂无引用条目
          </div>
        ) : (
          entries.map((entry) => {
            const isSelected = entry.cite_key === selectedKey;
            const dec = decisions[entry.cite_key]?.decision ?? entry.decision;
            const candIdx =
              decisions[entry.cite_key]?.selected_candidate_idx ??
              entry.selected_candidate_idx ??
              0;
            const activeCand = entry.candidates[candIdx] ?? entry.candidates[0];
            const statusBadge = getStatusBadge(entry.status);
            const hasDup = entry.warnings.some(
              (w) => w.code === "DUPLICATE_IN_BIB"
            );
            const hasJournalExt = entry.warnings.some(
              (w) => w.code === "JOURNAL_EXTENSION_AVAILABLE"
            );
            const titleDisplay =
              activeCand?.matched_title ||
              entry.original_fields.title?.replace(/[{}]/g, "") ||
              "(无标题)";
            const canAccept = entry.candidates.length > 0 || dec === "custom";

            return (
              <div
                key={`${entry.entry_index}-${entry.cite_key}`}
                onClick={() => onSelectEntry(entry.cite_key)}
                className={`group flex cursor-pointer items-start gap-2.5 px-3 py-2.5 transition ${
                  isSelected
                    ? "bg-indigo-50/80 border-l-4 border-l-indigo-600 pl-2"
                    : "hover:bg-slate-50"
                }`}
              >
                <div
                  className="pt-0.5"
                  onClick={(e) => e.stopPropagation()}
                  title={
                    canAccept
                      ? "勾选后在导出时采用右侧新版本；取消勾选保留原条目不变"
                      : "无可用候选替换项，保留原条目"
                  }
                >
                  <input
                    type="checkbox"
                    disabled={!canAccept}
                    checked={dec === "accept" || dec === "custom"}
                    onChange={(e) => onToggleDecision(entry, e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:opacity-30"
                  />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-1.5">
                    <span className="truncate font-mono text-xs font-semibold text-slate-900">
                      {entry.cite_key}
                    </span>
                    <span
                      className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] ${statusBadge.className}`}
                    >
                      {statusBadge.label}
                    </span>
                  </div>

                  <p className="mt-1 line-clamp-2 text-xs leading-snug text-slate-600">
                    {titleDisplay}
                  </p>

                  <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    {activeCand?.bibtex_origin && (
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-700 border border-slate-200">
                        {shortOriginBadge(activeCand.bibtex_origin)}
                      </span>
                    )}
                    {activeCand?.canonical_venue_id && (
                      <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700">
                        {activeCand.canonical_venue_id}{" "}
                        {activeCand.matched_year ?? ""}
                      </span>
                    )}
                    {dec === "custom" && (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
                        ✏️ 手动微调
                      </span>
                    )}
                    {hasJournalExt && (
                      <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[10px] text-sky-700 border border-sky-200">
                        含期刊扩展版
                      </span>
                    )}
                    {hasDup && (
                      <span className="rounded bg-purple-50 px-1.5 py-0.5 text-[10px] font-medium text-purple-700 border border-purple-200">
                        🔁 重复
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
