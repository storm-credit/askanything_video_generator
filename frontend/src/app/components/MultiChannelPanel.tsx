"use client";

import { motion } from "framer-motion";
import { Download, Youtube, Send, Instagram } from "lucide-react";
import { API_BASE, CHANNEL_PRESETS, type ChannelStatus, type PreviewData } from "../constants";
import type { UploadTopicMeta } from "../../components/types";

interface MultiChannelPanelProps {
  channelResults: Record<string, ChannelStatus>;
  channelPreviews: Record<string, PreviewData>;
  topic: string;
  todayMeta: Record<string, UploadTopicMeta> | null;
  onOpenUpload: (platform: "youtube" | "tiktok" | "instagram", ch: string, videoUrl: string) => void;
}

export function MultiChannelPanel({ channelResults, channelPreviews, topic, todayMeta, onOpenUpload }: MultiChannelPanelProps) {
  if (Object.keys(channelResults).length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className="mt-8 w-full max-w-xl glass-panel p-5 rounded-3xl relative z-10 border border-white/[0.08]"
    >
      <h3 className="text-sm font-semibold text-white mb-3">{"\ucc44\ub110\ubcc4 \uc0dd\uc131 \ud604\ud669"}</h3>
      <div className="space-y-3">
        {Object.entries(channelResults).map(([ch, result]) => {
          const preset = CHANNEL_PRESETS[ch];
          return (
            <div key={ch} className="bg-white/5 rounded-xl p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-gray-200">
                  {preset?.flag} {preset?.label || ch}
                </span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                  result.status === 'done' ? 'bg-green-500/20 text-green-400' :
                  result.status === 'error' ? 'bg-red-500/20 text-red-400' :
                  result.status === 'generating' ? 'bg-blue-500/20 text-blue-400' :
                  'bg-gray-500/20 text-gray-400'
                }`}>
                  {result.status === 'done' ? 'complete' : result.status === 'error' ? 'error' : `${result.progress}%`}
                </span>
              </div>
              <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    result.status === 'done' ? 'bg-green-500' :
                    result.status === 'error' ? 'bg-red-500' : 'bg-indigo-500'
                  }`}
                  style={{ width: `${result.progress}%` }}
                />
              </div>
              {result.status === 'done' && result.videoUrl && (
                <div className="mt-2 space-y-2">
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
                          a.download = `${ch}_${(topic || "video").slice(0, 50)}.mp4`;
                          document.body.appendChild(a); a.click(); a.remove();
                          URL.revokeObjectURL(url);
                        } catch { window.open(result.videoUrl!, "_blank"); }
                      }}
                      className="flex items-center gap-1 px-2.5 py-1.5 bg-white/10 hover:bg-white/20 text-white text-[10px] rounded-lg transition-colors"
                    >
                      <Download className="w-3 h-3" /> {"\ub2e4\uc6b4\ub85c\ub4dc"}
                    </button>
                    {(() => {
                      const chPlatforms = preset?.platforms || ["youtube"];
                      return (
                        <>
                          {chPlatforms.includes("youtube") && (
                            <button onClick={() => onOpenUpload("youtube", ch, result.videoUrl!)} className="flex items-center gap-1 px-2.5 py-1.5 bg-red-600 hover:bg-red-500 text-white text-[10px] font-semibold rounded-lg transition-colors">
                              <Youtube className="w-3 h-3" /> YouTube
                            </button>
                          )}
                          {chPlatforms.includes("tiktok") && (
                            <button onClick={() => onOpenUpload("tiktok", ch, result.videoUrl!)} className="flex items-center gap-1 px-2.5 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-[10px] font-semibold rounded-lg transition-colors">
                              <Send className="w-3 h-3" /> TikTok
                            </button>
                          )}
                          {chPlatforms.includes("reels") && (
                            <button onClick={() => onOpenUpload("instagram", ch, result.videoUrl!)} className="flex items-center gap-1 px-2.5 py-1.5 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400 text-white text-[10px] font-semibold rounded-lg transition-colors">
                              <Instagram className="w-3 h-3" /> Reels
                            </button>
                          )}
                        </>
                      );
                    })()}
                  </div>
                </div>
              )}
              {result.status === 'error' && result.errorMsg && (
                <p className="mt-1 text-[10px] text-red-400 truncate">{result.errorMsg}</p>
              )}
              {result.status !== 'done' && result.logs.length > 0 && (
                <p className="mt-1 text-[10px] text-gray-500 truncate">{result.logs[result.logs.length - 1]}</p>
              )}
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
