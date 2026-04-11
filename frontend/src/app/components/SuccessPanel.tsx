"use client";

import { motion } from "framer-motion";
import { CheckCircle2, Download, Youtube, Send, Instagram, Loader2 } from "lucide-react";
import { CHANNEL_PRESETS } from "../constants";

interface SuccessPanelProps {
  successMessage: string | null;
  isGenerating: boolean;
  errorMessage: string | null;
  generatedVideoUrl: string | null;
  generatedVideoPath: string | null;
  isDownloading: boolean;
  setIsDownloading: (v: boolean) => void;
  topic: string;
  channel: string;
  selectedChannels: string[];
  todayMeta: Record<string, { title: string; description: string; hashtags: string }> | null;
  onOpenUpload: (platform: "youtube" | "tiktok" | "instagram", ch: string, videoUrl: string) => void;
}

export function SuccessPanel({
  successMessage, isGenerating, errorMessage,
  generatedVideoUrl, generatedVideoPath,
  isDownloading, setIsDownloading,
  topic, channel, selectedChannels, todayMeta,
  onOpenUpload,
}: SuccessPanelProps) {
  if (!successMessage || isGenerating || errorMessage) return null;

  const activeChannel = selectedChannels.length === 1 ? selectedChannels[0] : channel;
  const preset = activeChannel ? CHANNEL_PRESETS[activeChannel] : null;
  const channelPlatforms = preset ? preset.platforms : ["youtube", "tiktok", "reels"];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      className="mt-16 w-full max-w-sm glass-panel p-6 rounded-[2.5rem] relative z-10 flex flex-col justify-center items-center shadow-2xl shadow-indigo-500/20 text-center space-y-4"
    >
      {generatedVideoUrl ? (
        <div className="w-full rounded-2xl overflow-hidden bg-black/50 border border-white/10">
          <video
            src={generatedVideoUrl}
            controls
            autoPlay
            loop
            playsInline
            className="w-full aspect-[9/16] max-h-[50vh] object-contain"
          />
        </div>
      ) : (
        <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto" />
      )}
      <h3 className="text-xl text-white font-bold">{"\uc0dd\uc131 \uc131\uacf5!"}</h3>
      {generatedVideoPath && (
        <div className="flex flex-col gap-2 w-full">
          <button
            disabled={isDownloading}
            onClick={async () => {
              if (!generatedVideoUrl || isDownloading) return;
              setIsDownloading(true);
              try {
                const res = await fetch(generatedVideoUrl);
                if (!res.ok) throw new Error(res.statusText);
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                const activeChName = selectedChannels.length === 1 ? selectedChannels[0] : (channel || "shorts");
                a.download = `${activeChName}_${(topic || "video").slice(0, 50)}.mp4`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
              } catch {
                window.open(generatedVideoUrl, "_blank");
              } finally {
                setIsDownloading(false);
              }
            }}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 disabled:opacity-50 text-white text-sm rounded-xl transition-colors"
          >
            {isDownloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            {isDownloading ? "\ub2e4\uc6b4\ub85c\ub4dc \uc911..." : "\ub2e4\uc6b4\ub85c\ub4dc"}
          </button>
          {channelPlatforms.includes("youtube") && (
            <button onClick={() => onOpenUpload("youtube", activeChannel || "", generatedVideoUrl!)} className="flex items-center justify-center gap-2 px-5 py-2.5 bg-red-600 hover:bg-red-500 text-white font-semibold rounded-xl transition-colors w-full">
              <Youtube className="w-5 h-5" /> YouTube Shorts
            </button>
          )}
          {(channelPlatforms.includes("tiktok") || channelPlatforms.includes("reels")) && (
            <div className="flex gap-2">
              {channelPlatforms.includes("tiktok") && (
                <button onClick={() => onOpenUpload("tiktok", activeChannel || "", generatedVideoUrl!)} className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white font-semibold rounded-xl transition-colors text-sm">
                  <Send className="w-4 h-4" /> TikTok
                </button>
              )}
              {channelPlatforms.includes("reels") && (
                <button onClick={() => onOpenUpload("instagram", activeChannel || "", generatedVideoUrl!)} className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400 text-white font-semibold rounded-xl transition-colors text-sm">
                  <Instagram className="w-4 h-4" /> Reels
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}
