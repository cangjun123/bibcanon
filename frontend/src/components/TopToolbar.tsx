import React, { useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  ClipboardCopy,
  Download,
  FilePlus2,
  Loader2,
  LogOut,
  Save,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Square,
} from "lucide-react";
import { StyleMode } from "../types";

export const SAMPLE_DEMO_BIB = `% === Overleaf Demo Bibliography ===
@string{cvpr = "Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition"}

@inproceedings{he2022mae,
  title = {Masked Autoencoders Are Scalable Vision Learners},
  author = {He, Kaiming and Chen, Xinlei and Xie, Saining and Li, Yanghao and Doll{\\'a}r, Piotr and Girshick, Ross},
  booktitle = cvpr,
  year = {2022}
}

@article{lora2021arxiv,
  title = {LoRA: Low-Rank Adaptation of Large Language Models},
  author = {Hu, Edward J. and Shen, Yelong and Wallis, Phillip and Allen-Zhu, Zeyuan and Li, Yuanzhi and Wang, Shean and Wang, Lu and Chen, Weizhu},
  journal = {arXiv preprint arXiv:2106.09685},
  year = {2021}
}

@article{kirillov2023sam,
  title = {Segment Anything},
  author = {Kirillov, Alexander and Mintun, Eric and Ravi, Nikhila and others},
  journal = {arXiv:2304.02643},
  year = {2023}
}

@inproceedings{fake2025hallucination,
  title = {Hyperbolic Quantum Telepathy for Zero-Shot 4D Scene Reconstruction},
  author = {Nobody, Alice and Ghost, Bob},
  booktitle = {CVPR},
  year = {2025}
}
`;

interface TopToolbarProps {
  isScanning: boolean;
  progress: { completed: number; total: number };
  sourcePath: string | null;
  cloudMode?: boolean;
  styleMode: StyleMode;
  protectTitleCase: boolean;
  hasEntries: boolean;
  acceptedCount: number;
  onOpenImport: () => void;
  onCancelScan: () => void;
  onChangeStyleMode: (mode: StyleMode) => void;
  onToggleProtectTitleCase: (val: boolean) => void;
  onBatchAcceptHighConfidence: () => void;
  onCopyBib: () => void;
  onDownloadBib: () => void;
  onWriteLocalBib: () => void;
  onOpenSettings: () => void;
  onLogout?: () => void;
}

export const TopToolbar: React.FC<TopToolbarProps> = ({
  isScanning,
  progress,
  sourcePath,
  cloudMode = false,
  styleMode,
  protectTitleCase,
  hasEntries,
  acceptedCount,
  onOpenImport,
  onCancelScan,
  onChangeStyleMode,
  onToggleProtectTitleCase,
  onBatchAcceptHighConfidence,
  onCopyBib,
  onDownloadBib,
  onWriteLocalBib,
  onOpenSettings,
  onLogout,
}) => {
  const [formatMenuOpen, setFormatMenuOpen] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const formatRef = useRef<HTMLDivElement | null>(null);
  const exportRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (formatRef.current && !formatRef.current.contains(e.target as Node)) {
        setFormatMenuOpen(false);
      }
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setExportMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const fileNameLabel = sourcePath
    ? sourcePath.split(/[\\/]/).pop()
    : null;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200/90 bg-white px-4">
      {/* Left: Brand & File Switcher + Inline Scan Status */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-900 text-xs font-bold text-white">
            B
          </div>
          <span className="text-sm font-semibold tracking-tight text-slate-900">
            bibcanon
          </span>
        </div>

        {hasEntries && (
          <>
            <div className="h-4 w-px bg-slate-200" />
            <button
              type="button"
              onClick={onOpenImport}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50/70 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 transition"
            >
              <FilePlus2 className="h-3.5 w-3.5 text-slate-500" />
              <span>{fileNameLabel ? fileNameLabel : "导入新 .bib"}</span>
            </button>
          </>
        )}

        {isScanning && (
          <div className="flex items-center gap-2.5 rounded-full border border-indigo-100 bg-indigo-50/70 px-3 py-1">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-600" />
            <span className="text-xs font-medium text-indigo-900">
              正在核验 {progress.completed}/{progress.total}
            </span>
            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-indigo-100">
              <div
                className="h-full bg-indigo-600 transition-all duration-200"
                style={{
                  width: `${
                    progress.total > 0
                      ? Math.round((progress.completed / progress.total) * 100)
                      : 0
                  }%`,
                }}
              />
            </div>
            <button
              type="button"
              onClick={onCancelScan}
              className="inline-flex items-center gap-0.5 text-[11px] font-medium text-slate-500 hover:text-rose-600"
              title="中止扫描"
            >
              <Square className="h-2.5 w-2.5 fill-current" />
              停止
            </button>
          </div>
        )}
      </div>

      {/* Right: Clean Actions */}
      <div className="flex items-center gap-2">
        {hasEntries && (
          <>
            {/* Format Popover */}
            <div ref={formatRef} className="relative">
              <button
                type="button"
                onClick={() => setFormatMenuOpen((v) => !v)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition"
              >
                <SlidersHorizontal className="h-3.5 w-3.5 text-slate-500" />
                <span>
                  {styleMode === "canonical" ? "原汁原味" : "缩写省页"}
                  {protectTitleCase ? " · 大写保护" : ""}
                </span>
                <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
              </button>

              {formatMenuOpen && (
                <div className="absolute right-0 mt-1.5 w-72 rounded-xl border border-slate-200 bg-white p-3.5 shadow-lg z-40 space-y-3">
                  <div>
                    <div className="text-[11px] font-semibold text-slate-500 mb-1.5">
                      字段输出风格
                    </div>
                    <div className="grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1 text-xs">
                      <button
                        type="button"
                        onClick={() => onChangeStyleMode("canonical")}
                        className={`rounded-md py-1.5 font-medium transition ${
                          styleMode === "canonical"
                            ? "bg-white text-slate-900 shadow-xs"
                            : "text-slate-600 hover:text-slate-900"
                        }`}
                      >
                        出版方原汁原味
                      </button>
                      <button
                        type="button"
                        onClick={() => onChangeStyleMode("compact")}
                        className={`rounded-md py-1.5 font-medium transition ${
                          styleMode === "compact"
                            ? "bg-white text-slate-900 shadow-xs"
                            : "text-slate-600 hover:text-slate-900"
                        }`}
                      >
                        会议缩写省页
                      </button>
                    </div>
                    <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
                      {styleMode === "canonical"
                        ? "保留出版方提供的全部真实字段，仅剥离 abstract/file 等本地管理软件噪音。"
                        : "使用 CVPR / ICLR / IEEE TPAMI 等标准缩写，并精简页码外冗余出版信息。"}
                    </p>
                  </div>

                  <div className="border-t border-slate-100 pt-2.5">
                    <label className="flex items-start gap-2 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={protectTitleCase}
                        onChange={(e) =>
                          onToggleProtectTitleCase(e.target.checked)
                        }
                        className="mt-0.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <div>
                        <div className="text-xs font-medium text-slate-800">
                          标题专有名词大写保护
                        </div>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          幂等包裹 {"{3D}"}、{"{ResNet}"}、{"{Gaussian}"}，防止老旧 .bst 样式强制转小写。
                        </p>
                      </div>
                    </label>
                  </div>
                </div>
              )}
            </div>

            {/* Batch Accept */}
            <button
              type="button"
              onClick={onBatchAcceptHighConfidence}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition"
              title="自动勾选所有高置信度且无警告的标准更新与预印本转正，跳过存疑条目"
            >
              <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
              一键采纳推荐
            </button>

            {/* Primary Split Export Button */}
            <div ref={exportRef} className="relative inline-flex rounded-lg shadow-xs">
              <button
                type="button"
                onClick={onCopyBib}
                className="inline-flex items-center gap-1.5 rounded-l-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800 transition"
              >
                <ClipboardCopy className="h-3.5 w-3.5" />
                <span>复制完整 .bib</span>
                {acceptedCount > 0 && (
                  <span className="rounded bg-white/20 px-1.5 py-0.2 text-[10px]">
                    {acceptedCount}
                  </span>
                )}
              </button>
              <button
                type="button"
                onClick={() => setExportMenuOpen((v) => !v)}
                className="inline-flex items-center rounded-r-lg border-l border-slate-700 bg-slate-900 px-1.5 py-1.5 text-white hover:bg-slate-800 transition"
                title="更多导出方式"
              >
                <ChevronDown className="h-3.5 w-3.5" />
              </button>

              {exportMenuOpen && (
                <div className="absolute right-0 top-full mt-1.5 w-52 rounded-xl border border-slate-200 bg-white py-1 shadow-lg z-40 text-xs">
                  <button
                    type="button"
                    onClick={() => {
                      setExportMenuOpen(false);
                      onDownloadBib();
                    }}
                    className="flex w-full items-center gap-2 px-3.5 py-2 text-left text-slate-700 hover:bg-slate-50"
                  >
                    <Download className="h-3.5 w-3.5 text-slate-500" />
                    下载 .bib 文件
                  </button>
                  {sourcePath && !cloudMode && (
                    <button
                      type="button"
                      onClick={() => {
                        setExportMenuOpen(false);
                        onWriteLocalBib();
                      }}
                      className="flex w-full items-center gap-2 px-3.5 py-2 text-left text-indigo-700 font-medium hover:bg-indigo-50/60"
                    >
                      <Save className="h-3.5 w-3.5 text-indigo-600" />
                      备份并写回原本地文件
                    </button>
                  )}
                </div>
              )}
            </div>
          </>
        )}

        <button
          type="button"
          onClick={onOpenSettings}
          className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white p-1.5 text-slate-500 hover:bg-slate-50 hover:text-slate-800 transition"
          title="全局设置与缓存管理"
        >
          <Settings className="h-4 w-4" />
        </button>

        {cloudMode && onLogout && (
          <button
            type="button"
            onClick={onLogout}
            className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600 transition"
            title="退出登录"
          >
            <LogOut className="h-4 w-4" />
          </button>
        )}
      </div>
    </header>
  );
};
