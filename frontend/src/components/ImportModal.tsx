import React, { useRef, useState } from "react";
import {
  FileCode2,
  FolderOpen,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { SAMPLE_DEMO_BIB } from "./TopToolbar";

interface ImportModalProps {
  isModal: boolean;
  open: boolean;
  initialPath?: string | null;
  isScanning: boolean;
  onClose?: () => void;
  onStartScanContent: (content: string, forceRefresh: boolean) => void;
  onStartScanPath: (path: string, forceRefresh: boolean) => void;
}

export const ImportModal: React.FC<ImportModalProps> = ({
  isModal,
  open,
  initialPath,
  isScanning,
  onClose,
  onStartScanContent,
  onStartScanPath,
}) => {
  const [tab, setTab] = useState<"upload_paste" | "local_path">(
    initialPath ? "local_path" : "upload_paste"
  );
  const [pasteText, setPasteText] = useState("");
  const [localPath, setLocalPath] = useState(initialPath ?? "");
  const [forceRefresh, setForceRefresh] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  if (!open) return null;

  const handleFile = async (file: File) => {
    const text = await file.text();
    onStartScanContent(text, forceRefresh);
    onClose?.();
  };

  const cardContent = (
    <div className="w-full max-w-2xl rounded-2xl border border-slate-200/90 bg-white shadow-xl shadow-slate-200/50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white font-semibold text-sm">
            B
          </div>
          <div>
            <h2 className="text-sm font-semibold text-slate-900">
              导入参考文献 (.bib)
            </h2>
            <p className="text-xs text-slate-500">
              100% 锁死原 Citation Key · 无损保留注释与 @String 宏
            </p>
          </div>
        </div>
        {isModal && onClose && (
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Mode Switcher */}
      <div className="px-6 pt-4">
        <div className="inline-flex rounded-lg bg-slate-100 p-1 text-xs font-medium">
          <button
            type="button"
            onClick={() => setTab("upload_paste")}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
              tab === "upload_paste"
                ? "bg-white text-slate-900 shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <FileCode2 className="h-3.5 w-3.5" />
            上传或粘贴 .bib (Overleaf)
          </button>
          <button
            type="button"
            onClick={() => setTab("local_path")}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${
              tab === "local_path"
                ? "bg-white text-slate-900 shadow-xs"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <FolderOpen className="h-3.5 w-3.5" />
            打开本地 .bib 路径
          </button>
        </div>
      </div>

      <div className="p-6 pt-4 space-y-4">
        {tab === "upload_paste" ? (
          <>
            {/* Clean Dropzone */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const f = e.dataTransfer.files?.[0];
                if (f) handleFile(f);
              }}
              onClick={() => fileInputRef.current?.click()}
              className={`flex cursor-pointer items-center justify-center gap-3 rounded-xl border border-dashed px-4 py-4 transition ${
                dragging
                  ? "border-indigo-500 bg-indigo-50/50 text-indigo-700"
                  : "border-slate-300 bg-slate-50/60 text-slate-600 hover:border-slate-400 hover:bg-slate-50"
              }`}
            >
              <Upload className="h-4 w-4 text-slate-400" />
              <span className="text-xs">
                拖拽单个 <code className="font-mono text-slate-800">.bib</code>{" "}
                文件到此处，或{" "}
                <span className="font-medium text-indigo-600 underline underline-offset-2">
                  点击选择文件
                </span>
              </span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".bib,text/plain"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFile(f);
                  e.target.value = "";
                }}
              />
            </div>

            {/* Textarea */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label className="text-xs font-medium text-slate-600">
                  或直接粘贴 .bib 全文
                </label>
                <button
                  type="button"
                  onClick={() => setPasteText(SAMPLE_DEMO_BIB)}
                  className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
                >
                  <Sparkles className="h-3 w-3" />
                  填入示例体验
                </button>
              </div>
              <textarea
                rows={8}
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder={`@inproceedings{he2016deep,\n  title={Deep Residual Learning for Image Recognition},\n  author={He, Kaiming and Zhang, Xiangyu and Ren, Shaoqing and Sun, Jian},\n  booktitle={CVPR},\n  year={2016}\n}`}
                className="w-full rounded-xl border border-slate-200 bg-slate-50/40 p-3 font-mono text-xs leading-relaxed text-slate-800 placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
              />
            </div>

            <div className="flex items-center justify-between pt-1">
              <label className="inline-flex items-center gap-2 text-xs text-slate-500 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={forceRefresh}
                  onChange={(e) => setForceRefresh(e.target.checked)}
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                忽略本地缓存重新联网查询
              </label>

              <div className="flex items-center gap-2">
                {isModal && onClose && (
                  <button
                    type="button"
                    onClick={onClose}
                    className="rounded-lg px-3.5 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100"
                  >
                    取消
                  </button>
                )}
                <button
                  type="button"
                  disabled={!pasteText.trim() || isScanning}
                  onClick={() => {
                    onStartScanContent(pasteText, forceRefresh);
                    onClose?.();
                  }}
                  className="rounded-lg bg-slate-900 px-5 py-2 text-xs font-medium text-white shadow-xs hover:bg-slate-800 disabled:opacity-40 transition"
                >
                  开始核验
                </button>
              </div>
            </div>
          </>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (localPath.trim()) {
                onStartScanPath(localPath.trim(), forceRefresh);
                onClose?.();
              }
            }}
            className="space-y-4"
          >
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1.5">
                本地 .bib 文件绝对路径
              </label>
              <input
                type="text"
                value={localPath}
                onChange={(e) => setLocalPath(e.target.value)}
                placeholder="例如: C:\Users\dell\Desktop\paper\main.bib"
                className="w-full rounded-xl border border-slate-200 bg-slate-50/40 px-3.5 py-2.5 font-mono text-xs text-slate-800 placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
              />
              <p className="mt-1.5 text-[11px] text-slate-500">
                通过本地路径打开时，审核完成后支持一键自动备份（.bak）并就地写回原文件。
              </p>
            </div>

            <div className="flex items-center justify-between pt-2">
              <label className="inline-flex items-center gap-2 text-xs text-slate-500 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={forceRefresh}
                  onChange={(e) => setForceRefresh(e.target.checked)}
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                忽略本地缓存重新联网查询
              </label>

              <div className="flex items-center gap-2">
                {isModal && onClose && (
                  <button
                    type="button"
                    onClick={onClose}
                    className="rounded-lg px-3.5 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100"
                  >
                    取消
                  </button>
                )}
                <button
                  type="submit"
                  disabled={!localPath.trim() || isScanning}
                  className="rounded-lg bg-slate-900 px-5 py-2 text-xs font-medium text-white shadow-xs hover:bg-slate-800 disabled:opacity-40 transition"
                >
                  加载并核验
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );

  if (isModal) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
        {cardContent}
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center p-6">
      {cardContent}
    </div>
  );
};
