import React from "react";
import { Search } from "lucide-react";
import {
  DecisionPayload,
  EntryAuditResult,
  FilterTab,
  VerificationStatus,
} from "../types";

interface EntryListProps {
  entries: EntryAuditResult[];
  selectedKey: string | null;
  activeFilter: FilterTab;
  filterCounts: Record<FilterTab, number>;
  searchQuery: string;
  decisions: Record<string, DecisionPayload>;
  onChangeFilter: (tab: FilterTab) => void;
  onSearchChange: (q: string) => void;
  onSelectEntry: (citeKey: string) => void;
  onToggleDecision: (entry: EntryAuditResult, checked: boolean) => void;
}

const FILTER_TABS: Array<{ id: FilterTab; label: string; dotClass?: string }> = [
  { id: "all", label: "全部" },
  { id: "attention", label: "需关注", dotClass: "bg-rose-500" },
  { id: "upgrade", label: "可转正", dotClass: "bg-indigo-500" },
  { id: "updatable", label: "可规范", dotClass: "bg-emerald-500" },
  { id: "identical", label: "已一致" },
];

function getStatusVisual(
  entry: EntryAuditResult
): { dotClass: string; summary: string; textClass: string } {
  const status: VerificationStatus = entry.status;
  const hasDup = entry.warnings.some((w) => w.code === "DUPLICATE_IN_BIB");
  const isTemplateDummy = entry.warnings.some((w) =>
    w.message.includes("模板自带占位")
  );
  const cand = entry.candidates[entry.selected_candidate_idx ?? 0] ?? entry.candidates[0];
  const venueLabel = cand
    ? [cand.canonical_venue_id || cand.matched_venue, cand.matched_year]
        .filter(Boolean)
        .join(" ")
    : "";

  if (isTemplateDummy) {
    return {
      dotClass: "bg-slate-400",
      summary: "模板示例占位",
      textClass: "text-slate-500",
    };
  }

  switch (status) {
    case "SUSPECTED_HALLUCINATION":
      return {
        dotClass: "bg-rose-500",
        summary: "查无此文 · 需人工核实",
        textClass: "text-rose-600 font-medium",
      };
    case "METADATA_MISMATCH":
      return {
        dotClass: "bg-amber-500",
        summary: "信息有出入 · 请核对",
        textClass: "text-amber-700 font-medium",
      };
    case "ERROR":
      return {
        dotClass: "bg-purple-500",
        summary: "网络请求超时",
        textClass: "text-purple-600",
      };
    case "PREPRINT_UPGRADE":
      return {
        dotClass: "bg-indigo-500",
        summary: venueLabel ? `可转正 → ${venueLabel}` : "可升级正式发表版",
        textClass: "text-indigo-600 font-medium",
      };
    case "VERIFIED_PREPRINT_ONLY":
      return {
        dotClass: hasDup ? "bg-amber-500" : "bg-sky-500",
        summary: hasDup ? "重复引用 · arXiv 预印本" : "arXiv 预印本",
        textClass: hasDup ? "text-amber-700" : "text-slate-500",
      };
    case "VERIFIED_CANONICAL":
      return {
        dotClass: hasDup ? "bg-amber-500" : "bg-emerald-500",
        summary: hasDup
          ? `重复引用 · ${venueLabel}`
          : venueLabel || cand?.bibtex_origin || "已核验",
        textClass: hasDup ? "text-amber-700" : "text-slate-500",
      };
    case "UNPROCESSED":
    default:
      return {
        dotClass: "bg-slate-300 animate-pulse",
        summary: "等待核验...",
        textClass: "text-slate-400",
      };
  }
}

export const EntryList: React.FC<EntryListProps> = ({
  entries,
  selectedKey,
  activeFilter,
  filterCounts,
  searchQuery,
  decisions,
  onChangeFilter,
  onSearchChange,
  onSelectEntry,
  onToggleDecision,
}) => {
  return (
    <aside className="flex h-full flex-col border-r border-slate-200/90 bg-white">
      {/* Compact Filter Tabs + Search */}
      <div className="space-y-2 border-b border-slate-100 p-3">
        <div className="flex items-center gap-1 overflow-x-auto pb-0.5">
          {FILTER_TABS.map((tab) => {
            const count = filterCounts[tab.id] ?? 0;
            const active = activeFilter === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onChangeFilter(tab.id)}
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                  active
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {tab.dotClass && !active && count > 0 && (
                  <span className={`h-1.5 w-1.5 rounded-full ${tab.dotClass}`} />
                )}
                <span>{tab.label}</span>
                <span
                  className={`text-[11px] ${
                    active ? "text-slate-300" : "text-slate-400"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="筛选 key、标题或会议 (支持 ↑↓ 键)"
            className="w-full rounded-lg border border-slate-200 bg-slate-50/60 py-1.5 pl-8 pr-2.5 text-xs text-slate-800 placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:outline-none"
          />
        </div>
      </div>

      {/* Calm, Scannable Entry List */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-100/80">
        {entries.length === 0 ? (
          <div className="px-6 py-12 text-center text-xs text-slate-400">
            该分类下暂无条目
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
            const titleDisplay =
              activeCand?.matched_title ||
              entry.original_fields.title?.replace(/[{}]/g, "") ||
              entry.cite_key;
            const visual = getStatusVisual(entry);
            const canAccept = entry.candidates.length > 0 || dec === "custom";
            const isAdopted = dec === "accept" || dec === "custom";

            return (
              <div
                key={`${entry.entry_index}-${entry.cite_key}`}
                onClick={() => onSelectEntry(entry.cite_key)}
                className={`group flex cursor-pointer items-center gap-3 px-3.5 py-2.5 transition ${
                  isSelected
                    ? "bg-indigo-50/70"
                    : "hover:bg-slate-50/80"
                }`}
              >
                {/* Status Indicator Dot */}
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${visual.dotClass}`}
                />

                {/* Title + Subtle Subtitle */}
                <div className="min-w-0 flex-1">
                  <div
                    className={`truncate text-xs ${
                      isSelected
                        ? "font-semibold text-slate-950"
                        : "font-medium text-slate-800"
                    }`}
                  >
                    {titleDisplay}
                  </div>
                  <div className="mt-0.5 flex items-center gap-1.5 truncate text-[11px]">
                    <span className="font-mono text-slate-400 truncate max-w-[130px]">
                      {entry.cite_key}
                    </span>
                    <span className="text-slate-300">·</span>
                    <span className={`truncate ${visual.textClass}`}>
                      {visual.summary}
                    </span>
                  </div>
                </div>

                {/* Right Adopt Checkbox */}
                <div
                  onClick={(e) => e.stopPropagation()}
                  className="shrink-0"
                  title={
                    canAccept
                      ? isAdopted
                        ? "已勾选采纳更新（点击取消将保留原条目）"
                        : "点击采纳此候选版本"
                      : "保留原条目"
                  }
                >
                  <input
                    type="checkbox"
                    disabled={!canAccept}
                    checked={isAdopted}
                    onChange={(e) => onToggleDecision(entry, e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-slate-300 text-slate-900 focus:ring-slate-900 disabled:opacity-20 cursor-pointer"
                  />
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
