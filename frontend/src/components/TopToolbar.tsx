import React, { useRef, useState } from "react";
import {
  CheckCheck,
  ClipboardCopy,
  Download,
  FileCode2,
  FolderOpen,
  Loader2,
  Save,
  Settings,
  Sparkles,
  Square,
  Upload,
} from "lucide-react";
import { FilterTab, StyleMode } from "../types";

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
  activeFilter: FilterTab;
  filterCounts: Record<FilterTab, number>;
  styleMode: StyleMode;
  protectTitleCase: boolean;
  hasEntries: boolean;
  acceptedCount: number;
  onStartScanContent: (content: string, forceRefresh: boolean) => void;
  onStartScanPath: (path: string, forceRefresh: boolean) => void;
  onCancelScan: () => void;
  onChangeFilter: (tab: FilterTab) => void;
  onChangeStyleMode: (mode: StyleMode) => void;
  onToggleProtectTitleCase: (val: boolean) => void;
  onBatchAcceptHighConfidence: () => void;
  onCopyBib: () => void;
  onDownloadBib: () => void;
  onWriteLocalBib: () => void;
  onOpenSettings: () => void;
}

const FILTER_ITEMS: Array<{ id: FilterTab; label: string; colorClass: string }> = [
  { id: "all", label: "全部", colorClass: "text-slate-700" },
  { id: "hallucination", label: "❌ 疑似虚假", colorClass: "text-rose-700" },
  { id: "mismatch", label: "⚠️ 信息出入", colorClass: "text-amber-700" },
  { id: "upgrade", label: "🔄 可转正升级", colorClass: "text-indigo-700" },
  { id: "updatable", label: "✅ 已核验可更新", colorClass: "text-emerald-700" },
  { id: "identical", label: "✅ 已一致", colorClass: "text-slate-600" },
  { id: "duplicate", label: "🔁 重复条目", colorClass: "text-purple-700" },
];

export const TopToolbar: React.FC<TopToolbarProps> = ({
  isScanning,
  progress,
  sourcePath,
  activeFilter,
  filterCounts,
  styleMode,
  protectTitleCase,
  hasEntries,
  acceptedCount,
  onStartScanContent,
  onStartScanPath,
  onCancelScan,
  onChangeFilter,
  onChangeStyleMode,
  onToggleProtectTitleCase,
  onBatchAcceptHighConfidence,
  onCopyBib,
  onDownloadBib,
  onWriteLocalBib,
  onOpenSettings,
}) => {
  const [showPasteDrawer, setShowPasteDrawer] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [localPathInput, setLocalPathInput] = useState(sourcePath ?? "");
  const [forceRefresh, setForceRefresh] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    if (sourcePath) {
      setLocalPathInput(sourcePath);
    }
  }, [sourcePath]);

  const handleFileUpload = async (file: File) => {
    const text = await file.text();
    onStartScanContent(text, forceRefresh);
    setShowPasteDrawer(false);
  };

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      await handleFileUpload(file);
    }
  };

  return (
    <header
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      className={`border-b border-slate-200 bg-white shadow-sm transition-colors ${
        dragActive ? "ring-2 ring-inset ring-indigo-500 bg-indigo-50/40" : ""
      }`}
    >
      {/* Row 1: Brand, Import Controls, Global Mode Toggles & Export Actions */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold shadow-sm">
              B
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-bold tracking-tight text-slate-900 text-base">
                  bibcanon
                </span>
                <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-700 border border-indigo-200">
                  CV / AI / ML
                </span>
              </div>
            </div>
          </div>

          <div className="h-5 w-px bg-slate-200 mx-1" />

          {/* Import Buttons & Local Path Input */}
          <button
            type="button"
            onClick={() => setShowPasteDrawer((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <FileCode2 className="h-3.5 w-3.5 text-indigo-600" />
            粘贴 .bib 全文
          </button>

          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            title="支持直接拖拽 .bib 文件到顶部栏"
          >
            <Upload className="h-3.5 w-3.5 text-indigo-600" />
            上传/拖拽 .bib
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".bib,text/plain"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFileUpload(f);
              e.target.value = "";
            }}
          />

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (localPathInput.trim()) {
                onStartScanPath(localPathInput.trim(), forceRefresh);
              }
            }}
            className="flex items-center gap-1"
          >
            <div className="relative flex items-center">
              <FolderOpen className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-slate-400" />
              <input
                type="text"
                value={localPathInput}
                onChange={(e) => setLocalPathInput(e.target.value)}
                placeholder="本地 .bib 文件路径 (如 D:\paper\refs.bib)"
                className="w-60 rounded-md border border-slate-300 py-1.5 pl-8 pr-2 text-xs text-slate-800 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <button
              type="submit"
              disabled={!localPathInput.trim() || isScanning}
              className="rounded-md bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              加载扫描
            </button>
          </form>

          <label className="inline-flex items-center gap-1 text-xs text-slate-500 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={forceRefresh}
              onChange={(e) => setForceRefresh(e.target.checked)}
              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            绕过缓存
          </label>
        </div>

        {/* Right: Style Switches, Batch Accept, Export & Settings */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Style Mode Segmented Switch */}
          <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => onChangeStyleMode("canonical")}
              className={`rounded px-2.5 py-1 font-medium transition ${
                styleMode === "canonical"
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
              title="保留出版方提供的全部标准字段（仅剔除本地管理软件垃圾字段）"
            >
              出版方原汁原味版
            </button>
            <button
              type="button"
              onClick={() => onChangeStyleMode("compact")}
              className={`rounded px-2.5 py-1 font-medium transition ${
                styleMode === "compact"
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
              title="顶会投稿省页码模式：使用标准会议/期刊缩写并精简冗余出版字段"
            >
              省页码缩写版
            </button>
          </div>

          {/* Title Case Protection Checkbox */}
          <label
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700 cursor-pointer select-none hover:bg-slate-100"
            title="幂等包裹 {3D}、{ResNet}、{ViT}、{Gaussian} 等缩写与专有名词，防止老旧 .bst 将其转为小写"
          >
            <input
              type="checkbox"
              checked={protectTitleCase}
              onChange={(e) => onToggleProtectTitleCase(e.target.checked)}
              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span>标题大写保护 {"{3D}/{ViT}"}</span>
          </label>

          <div className="h-5 w-px bg-slate-200" />

          <button
            type="button"
            disabled={!hasEntries}
            onClick={onBatchAcceptHighConfidence}
            className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-40"
          >
            <Sparkles className="h-3.5 w-3.5 text-emerald-600" />
            一键采纳高置信度更新
          </button>

          <button
            type="button"
            disabled={!hasEntries}
            onClick={onCopyBib}
            className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-40"
            title="无损拼接并复制完整 .bib 全文，可直接粘贴回 Overleaf"
          >
            <ClipboardCopy className="h-3.5 w-3.5" />
            复制完整 .bib {acceptedCount > 0 ? `(${acceptedCount})` : ""}
          </button>

          <button
            type="button"
            disabled={!hasEntries}
            onClick={onDownloadBib}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
          >
            <Download className="h-3.5 w-3.5" />
            下载 .bib
          </button>

          {sourcePath && (
            <button
              type="button"
              disabled={!hasEntries}
              onClick={onWriteLocalBib}
              className="inline-flex items-center gap-1 rounded-md border border-indigo-300 bg-indigo-50 px-2.5 py-1.5 text-xs font-medium text-indigo-800 hover:bg-indigo-100 disabled:opacity-40"
              title={`自动生成时间戳 .bak 备份后覆盖写回 ${sourcePath}`}
            >
              <Save className="h-3.5 w-3.5" />
              备份并覆盖本地文件
            </button>
          )}

          <button
            type="button"
            onClick={onOpenSettings}
            className="inline-flex items-center justify-center rounded-md border border-slate-200 p-1.5 text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            title="全局设置与缓存管理"
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Collapsible Paste Drawer */}
      {showPasteDrawer && (
        <div className="border-t border-slate-200 bg-slate-50 px-4 py-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700">
              粘贴 Overleaf / 本地单个 .bib 文件全文（将保留全部注释与 @string 宏定义）
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPasteText(SAMPLE_DEMO_BIB)}
                className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
              >
                填入综合测试示例 .bib
              </button>
              <button
                type="button"
                onClick={() => setShowPasteDrawer(false)}
                className="text-xs text-slate-500 hover:text-slate-700"
              >
                收起
              </button>
            </div>
          </div>
          <textarea
            rows={7}
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder="@inproceedings{he2016deep, ...}"
            className="w-full rounded-md border border-slate-300 bg-white p-2.5 font-mono text-xs text-slate-800 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowPasteDrawer(false)}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              取消
            </button>
            <button
              type="button"
              disabled={!pasteText.trim() || isScanning}
              onClick={() => {
                onStartScanContent(pasteText, forceRefresh);
                setShowPasteDrawer(false);
              }}
              className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              <CheckCheck className="h-3.5 w-3.5" />
              开始全量核验
            </button>
          </div>
        </div>
      )}

      {/* Row 2: Filter Capsules & Live SSE Scan Progress */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/70 px-4 py-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          {FILTER_ITEMS.map((item) => {
            const count = filterCounts[item.id] ?? 0;
            const active = activeFilter === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onChangeFilter(item.id)}
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium transition ${
                  active
                    ? "bg-slate-900 text-white shadow-sm"
                    : `bg-white border border-slate-200 hover:bg-slate-100 ${item.colorClass}`
                }`}
              >
                <span>{item.label}</span>
                <span
                  className={`rounded-full px-1.5 text-[11px] ${
                    active ? "bg-slate-700 text-slate-100" : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {isScanning && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-xs font-medium text-indigo-700">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>
                正在并发核验 {progress.completed} / {progress.total}
              </span>
            </div>
            <div className="h-2 w-32 overflow-hidden rounded-full bg-slate-200">
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
              className="inline-flex items-center gap-1 rounded border border-rose-200 bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700 hover:bg-rose-100"
            >
              <Square className="h-3 w-3 fill-current" />
              中止
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
