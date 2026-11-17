import React, { useEffect, useState } from "react";
import { Database, RotateCcw, Save, Trash2, X } from "lucide-react";
import { AppConfig, CacheStats } from "../types";

const DEFAULT_NOISE_FIELDS = [
  "abstract",
  "file",
  "local-url",
  "mendeley-tags",
  "zotero-key",
  "annote",
  "biburl",
  "bibsource",
  "timestamp",
];

interface SettingsModalProps {
  open: boolean;
  config: AppConfig;
  cacheStats: CacheStats | null;
  onClose: () => void;
  onSave: (cfg: AppConfig) => Promise<void>;
  onClearCache: (scope: "all" | "queries") => Promise<void>;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  open,
  config,
  cacheStats,
  onClose,
  onSave,
  onClearCache,
}) => {
  const [form, setForm] = useState<AppConfig>(config);
  const [blacklistText, setBlacklistText] = useState(
    config.noise_field_blacklist.join(", ")
  );
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    setForm(config);
    setBlacklistText(config.noise_field_blacklist.join(", "));
  }, [config, open]);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const parsedList = blacklistText
        .split(/[,;\n]+/)
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);
      await onSave({
        ...form,
        noise_field_blacklist: parsedList,
      });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async (scope: "all" | "queries") => {
    setClearing(true);
    try {
      await onClearCache(scope);
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs">
      <div className="w-full max-w-xl rounded-xl border border-slate-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5">
          <h3 className="text-sm font-bold text-slate-900">
            全局设置与本地缓存管理 (~/.bibcanon/config.json)
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 p-5 text-xs">
          <div>
            <label className="block font-semibold text-slate-700">
              礼貌池邮箱 (Crossref / OpenAlex Polite Pool — 可选推荐)
            </label>
            <p className="mt-0.5 text-[11px] text-slate-500">
              无需注册，填写学术/个人邮箱即可进入官方高速通道，大幅降低限流概率。
            </p>
            <input
              type="email"
              value={form.polite_email}
              onChange={(e) =>
                setForm({ ...form, polite_email: e.target.value })
              }
              placeholder="your.name@university.edu"
              className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-semibold text-slate-700">
                OpenAlex API Key (可选免费增强)
              </label>
              <input
                type="password"
                value={form.openalex_api_key}
                onChange={(e) =>
                  setForm({ ...form, openalex_api_key: e.target.value })
                }
                placeholder="留空默认免 Key 运行"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700">
                Semantic Scholar API Key (可选)
              </label>
              <input
                type="password"
                value={form.semantic_scholar_api_key}
                onChange={(e) =>
                  setForm({
                    ...form,
                    semantic_scholar_api_key: e.target.value,
                  })
                }
                placeholder="留空默认免 Key 兜底"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs"
              />
            </div>
          </div>

          <div>
            <label className="block font-semibold text-slate-700">
              本地网络代理地址 Proxy URL (可选)
            </label>
            <p className="mt-0.5 text-[11px] text-slate-500">
              默认自动读取系统环境变量；如需显式指定本地代理可填写如{" "}
              <code className="font-mono">http://127.0.0.1:7890</code>。
            </p>
            <input
              type="text"
              value={form.proxy_url}
              onChange={(e) => setForm({ ...form, proxy_url: e.target.value })}
              placeholder="http://127.0.0.1:7890"
              className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-1.5 font-mono text-xs"
            />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="font-semibold text-slate-700">
                本地垃圾字段剔除黑名单 (逗号分隔)
              </label>
              <button
                type="button"
                onClick={() => setBlacklistText(DEFAULT_NOISE_FIELDS.join(", "))}
                className="inline-flex items-center gap-1 text-[11px] text-indigo-600 hover:underline"
              >
                <RotateCcw className="h-3 w-3" />
                恢复默认黑名单
              </button>
            </div>
            <p className="mt-0.5 text-[11px] text-slate-500">
              在出版方原汁原味模式下，仅剥离下列文献管理软件垃圾字段，保留全部真实出版字段。
            </p>
            <textarea
              rows={2}
              value={blacklistText}
              onChange={(e) => setBlacklistText(e.target.value)}
              className="mt-1.5 w-full rounded-md border border-slate-300 p-2 font-mono text-xs"
            />
          </div>

          {/* Local SQLite Cache Management */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 font-semibold text-slate-800">
                <Database className="h-3.5 w-3.5 text-indigo-600" />
                <span>本地 SQLite 缓存状态</span>
              </div>
              {cacheStats && (
                <span className="text-[11px] text-slate-500">
                  {(cacheStats.db_size_bytes / 1024).toFixed(1)} KB
                </span>
              )}
            </div>
            {cacheStats && (
              <p className="mt-1 text-[11px] text-slate-600">
                查询结果缓存: <strong>{cacheStats.query_cache_count}</strong> 条
                {" · "}CVF 会议目录缓存:{" "}
                <strong>{cacheStats.cvf_toc_venues_count}</strong> 场馆 (
                {cacheStats.cvf_toc_papers_count} 篇论文)
              </p>
            )}
            <div className="mt-2.5 flex gap-2">
              <button
                type="button"
                disabled={clearing}
                onClick={() => handleClear("queries")}
                className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
              >
                <Trash2 className="h-3 w-3 text-slate-500" />
                清空查询缓存
              </button>
              <button
                type="button"
                disabled={clearing}
                onClick={() => handleClear("all")}
                className="inline-flex items-center gap-1 rounded border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700 hover:bg-rose-100 disabled:opacity-50"
              >
                <Trash2 className="h-3 w-3" />
                清空全部缓存 (含 CVF 目录)
              </button>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-300 px-3.5 py-1.5 font-medium text-slate-600 hover:bg-slate-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-1.5 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" />
              保存配置
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
