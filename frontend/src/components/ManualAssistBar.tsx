import React, { useState } from "react";
import { ClipboardPaste, ExternalLink, Loader2 } from "lucide-react";
import { EntryAuditResult } from "../types";

interface ManualAssistBarProps {
  entry: EntryAuditResult;
  onPasteMerge: (pastedBibtex: string) => Promise<void>;
}

export const ManualAssistBar: React.FC<ManualAssistBarProps> = ({
  entry,
  onPasteMerge,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [pastedText, setPastedText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const handleMerge = async () => {
    if (!pastedText.trim()) return;
    setSubmitting(true);
    setErrMsg(null);
    try {
      await onPasteMerge(pastedText);
      setPastedText("");
      setExpanded(false);
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : "粘贴解析失败");
    } finally {
      setSubmitting(false);
    }
  };

  const links = entry.search_links || {};

  return (
    <div className="border-t border-slate-200 bg-slate-50 px-4 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-medium text-slate-500 mr-1">
            半自动外部检索兜底:
          </span>
          {links.google_scholar && (
            <a
              href={links.google_scholar}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
            >
              🔍 Google Scholar
              <ExternalLink className="h-3 w-3 text-slate-400" />
            </a>
          )}
          {links.bing && (
            <a
              href={links.bing}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
            >
              🔍 Bing 搜索
              <ExternalLink className="h-3 w-3 text-slate-400" />
            </a>
          )}
          {links.dblp && (
            <a
              href={links.dblp}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
            >
              🔍 DBLP
              <ExternalLink className="h-3 w-3 text-slate-400" />
            </a>
          )}
          {links.semantic_scholar && (
            <a
              href={links.semantic_scholar}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
            >
              🔍 Semantic Scholar
              <ExternalLink className="h-3 w-3 text-slate-400" />
            </a>
          )}
        </div>

        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-md border border-indigo-300 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-800 hover:bg-indigo-100"
        >
          <ClipboardPaste className="h-3.5 w-3.5" />
          {expanded
            ? "收起外部 BibTeX 合并框"
            : "粘贴外部 BibTeX 自动锁 Key 合并"}
        </button>
      </div>

      {expanded && (
        <div className="mt-2.5 rounded-md border border-indigo-200 bg-white p-3 shadow-sm">
          <div className="mb-1.5 flex items-center justify-between text-xs text-slate-600">
            <span>
              粘贴从官网或 Google Scholar 复制的任意 BibTeX，系统将自动锁死原{" "}
              <code className="rounded bg-slate-100 px-1 font-mono font-semibold text-indigo-700">
                {entry.cite_key}
              </code>{" "}
              并完成去噪与安全转义：
            </span>
          </div>
          <textarea
            rows={4}
            value={pastedText}
            onChange={(e) => setPastedText(e.target.value)}
            placeholder={`@inproceedings{any_external_key,\n  title={...},\n  author={...}\n}`}
            className="w-full rounded border border-slate-300 p-2 font-mono text-xs text-slate-800 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          {errMsg && (
            <p className="mt-1 text-xs font-medium text-rose-600">{errMsg}</p>
          )}
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="rounded border border-slate-300 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
            >
              取消
            </button>
            <button
              type="button"
              disabled={!pastedText.trim() || submitting}
              onClick={handleMerge}
              className="inline-flex items-center gap-1 rounded bg-indigo-600 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {submitting && <Loader2 className="h-3 w-3 animate-spin" />}
              锁死 {entry.cite_key} 并合并采纳
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
