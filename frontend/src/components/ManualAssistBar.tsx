import React, { useState } from "react";
import { ClipboardPaste, ExternalLink, Loader2, X } from "lucide-react";
import { EntryAuditResult } from "../types";

interface ManualAssistBarProps {
  entry: EntryAuditResult;
  onPasteMerge: (pastedBibtex: string) => Promise<void>;
}

export const ManualAssistBar: React.FC<ManualAssistBarProps> = ({
  entry,
  onPasteMerge,
}) => {
  const [modalOpen, setModalOpen] = useState(false);
  const [pastedText, setPastedText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const links = entry.search_links || {};
  const needsAttention =
    entry.status === "SUSPECTED_HALLUCINATION" ||
    entry.status === "METADATA_MISMATCH" ||
    entry.status === "ERROR";

  const handleMerge = async () => {
    if (!pastedText.trim()) return;
    setSubmitting(true);
    setErrMsg(null);
    try {
      await onPasteMerge(pastedText);
      setPastedText("");
      setModalOpen(false);
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : "解析粘贴文本失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <footer
        className={`flex shrink-0 flex-wrap items-center justify-between gap-2 border-t px-5 py-2.5 text-xs ${
          needsAttention
            ? "border-amber-200/80 bg-amber-50/40"
            : "border-slate-200/80 bg-white"
        }`}
      >
        <div className="flex flex-wrap items-center gap-3 text-slate-500">
          <span>外部查证:</span>
          {links.google_scholar && (
            <a
              href={links.google_scholar}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-slate-700 hover:text-indigo-600 transition"
            >
              Google Scholar
              <ExternalLink className="h-3 w-3 opacity-60" />
            </a>
          )}
          {links.bing && (
            <a
              href={links.bing}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-slate-700 hover:text-indigo-600 transition"
            >
              Bing
              <ExternalLink className="h-3 w-3 opacity-60" />
            </a>
          )}
          {links.dblp && (
            <a
              href={links.dblp}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-slate-700 hover:text-indigo-600 transition"
            >
              DBLP
              <ExternalLink className="h-3 w-3 opacity-60" />
            </a>
          )}
          {links.semantic_scholar && (
            <a
              href={links.semantic_scholar}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-slate-700 hover:text-indigo-600 transition"
            >
              Semantic Scholar
              <ExternalLink className="h-3 w-3 opacity-60" />
            </a>
          )}
        </div>

        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1 font-medium text-slate-700 hover:bg-slate-100 transition"
        >
          <ClipboardPaste className="h-3.5 w-3.5 text-slate-500" />
          粘贴外部 BibTeX 合并
        </button>
      </footer>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h4 className="text-sm font-semibold text-slate-900">
                  粘贴外部 BibTeX 智能合并
                </h4>
                <p className="text-xs text-slate-500 mt-0.5">
                  自动锁死原键值{" "}
                  <code className="font-mono font-semibold text-indigo-600">
                    {entry.cite_key}
                  </code>
                  ，剔除垃圾字段并转义特殊字符
                </p>
              </div>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <textarea
              rows={6}
              autoFocus
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
              placeholder={`@inproceedings{any_key,\n  title={...},\n  author={...}\n}`}
              className="mt-3.5 w-full rounded-xl border border-slate-200 bg-slate-50/50 p-3 font-mono text-xs text-slate-800 focus:border-indigo-500 focus:bg-white focus:outline-none"
            />
            {errMsg && (
              <p className="mt-1.5 text-xs font-medium text-rose-600">
                {errMsg}
              </p>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="rounded-lg px-3.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
              >
                取消
              </button>
              <button
                type="button"
                disabled={!pastedText.trim() || submitting}
                onClick={handleMerge}
                className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-40"
              >
                {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                合并并采纳
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
