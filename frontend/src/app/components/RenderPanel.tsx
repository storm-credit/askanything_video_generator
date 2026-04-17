"use client";

import { motion } from "framer-motion";
import { Download, Youtube, Send, Instagram } from "lucide-react";
import { API_BASE, CHANNEL_PRESETS, type RenderResult } from "../constants";
import type { UploadTopicMeta } from "../../components/types";

interface RenderPanelProps {
  renderResults: Record<string, RenderResult>;
  activeRenderTab: string;
  setActiveRenderTab: (tab: string) => void;
  topic: string;
  todayMeta: Record<string, UploadTopicMeta> | null;
  onOpenUpload: (platform: "youtube" | "tiktok" | "instagram", ch: string, videoUrl: string) => void;
}

export function RenderPanel({ renderResults, activeRenderTab, setActiveRenderTab, topic, todayMeta, onOpenUpload }: RenderPanelProps) {
  if (Object.keys(renderResults).length === 0) return null;

  const result = renderResults[activeRenderTab];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className="mt-8 w-full max-w-xl glass-panel p-5 rounded-3xl relative z-10 border border-white/[0.08]"
    >
      <h3 className="text-sm font-semibold text-white mb-3">{"\ucc44\ub110\ubcc4 \ub80c\ub354\ub9c1 \ud604\ud669"}</h3>
      {/* Tabs */}
      <div className="flex gap-1.5 mb-3 border-b border-white/[0.06] pb-2">
        {Object.entries(renderResults).map(([ch, r]) => {
          const preset = CHANNEL_PRESETS[ch];
          const isActive = ch === activeRenderTab;
          return (
            <button key={ch} onClick={() => setActiveRenderTab(ch)}
              className={`px-3 py-1 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 ${isActive ? "bg-indigo-600/30 text-indigo-300 border border-indigo-500/30" : "text-gray-500 hover:text-gray-300 hover:bg-white/5"}`}>
              {preset?.flag} {preset?.label}
              <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                r.status === 'done' ? 'bg-green-500/20 text-green-400' :
                r.status === 'error' ? 'bg-red-500/20 text-red-400' :
                'bg-blue-500/20 text-blue-400'
              }`}>
                {r.status === 'done' ? '\uc644\ub8cc' : r.status === 'error' ? '\uc624\ub958' : `${r.progress}%`}
              </span>
            </button>
          );
        })}
      </div>
      {/* Active tab detail */}
      {result && (
        <div>
          <div className="h-2 bg-white/10 rounded-full overflow-hidden mb-3">
            <div className={`h-full rounded-full transition-all duration-500 ${
              result.status === 'done' ? 'bg-green-500' :
              result.status === 'error' ? 'bg-red-500' : 'bg-indigo-500'
            }`} style={{ width: `${result.progress}%` }} />
          </div>
          {result.status === 'done' && result.videoUrl && (
            <div className="space-y-3 mb-3">
              <div className="rounded-xl overflow-hidden bg-black/50 border border-white/10">
                <video src={result.videoUrl} controls playsInline className="w-full aspect-[9/16] max-h-[40vh] object-contain" />
              </div>
              <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={async () => {
                    try {
                      const res = await fetch(result.videoUrl!);
                      const blob = await res.blob();
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `${activeRenderTab}_${(topic || "video").slice(0, 50)}.mp4`;
                      document.body.appendChild(a); a.click(); a.remove();
                      URL.revokeObjectURL(url);
                    } catch { window.open(result.videoUrl!, "_blank"); }
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white text-xs rounded-lg transition-colors"
                >
                  <Download className="w-3.5 h-3.5" /> {"\ub2e4\uc6b4\ub85c\ub4dc"}
                </button>
                {(() => {
                  const renderPreset = CHANNEL_PRESETS[activeRenderTab];
                  const renderPlatforms = renderPreset?.platforms || ["youtube"];
                  return (
                    <>
                      {renderPlatforms.includes("youtube") && (
                        <button onClick={() => onOpenUpload("youtube", activeRenderTab, result.videoUrl!)} className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-xs font-semibold rounded-lg transition-colors">
                          <Youtube className="w-3.5 h-3.5" /> YouTube
                        </button>
                      )}
                      {renderPlatforms.includes("tiktok") && (
                        <button onClick={() => onOpenUpload("tiktok", activeRenderTab, result.videoUrl!)} className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-semibold rounded-lg transition-colors">
                          <Send className="w-3.5 h-3.5" /> TikTok
                        </button>
                      )}
                      {renderPlatforms.includes("reels") && (
                        <button onClick={() => onOpenUpload("instagram", activeRenderTab, result.videoUrl!)} className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400 text-white text-xs font-semibold rounded-lg transition-colors">
                          <Instagram className="w-3.5 h-3.5" /> Reels
                        </button>
                      )}
                    </>
                  );
                })()}
              </div>
            </div>
          )}
          {result.status === 'error' && result.errorMsg && (
            <p className="text-xs text-red-400 mb-2">{result.errorMsg}</p>
          )}
          {result.status !== 'done' && (
            <div className="max-h-32 overflow-y-auto space-y-0.5 custom-scrollbar pr-1">
              {result.logs.slice(-10).map((log, i) => (
                <p key={i} className="text-[10px] text-gray-500 truncate">{log}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}
