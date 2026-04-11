"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { X, Youtube, Send, Instagram, Upload, ExternalLink, CheckCircle2 } from "lucide-react";
import { API_BASE, CHANNEL_PRESETS } from "../constants";
import type { PlatformAuth } from "../hooks/usePlatformAuth";

interface UploadModalProps {
  show: boolean;
  onClose: () => void;
  generatedVideoPath: string | null;
  uploadChannel: string;
  topic: string;
  initialTitle: string;
  initialDescription: string;
  initialTags: string;
  platformAuth: PlatformAuth;
}

export function UploadModal({
  show, onClose, generatedVideoPath, uploadChannel, topic,
  initialTitle, initialDescription, initialTags,
  platformAuth,
}: UploadModalProps) {
  const [uploadPlatform, setUploadPlatform] = useState<"youtube" | "tiktok" | "instagram">("youtube");
  const [uploadTitle, setUploadTitle] = useState(initialTitle);
  const [uploadDescription, setUploadDescription] = useState(initialDescription);
  const [uploadTags, setUploadTags] = useState(initialTags);

  // props 변경 시 state 동기화 (modal 재오픈 시 새 값 반영)
  React.useEffect(() => { setUploadTitle(initialTitle); }, [initialTitle]);
  React.useEffect(() => { setUploadDescription(initialDescription); }, [initialDescription]);
  React.useEffect(() => { setUploadTags(initialTags); }, [initialTags]);
  const [uploadPrivacy, setUploadPrivacy] = useState("private");
  const [ttPrivacy, setTtPrivacy] = useState("SELF_ONLY");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ success: boolean; url?: string; error?: string; scheduled_at?: string } | null>(null);
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleDate, setScheduleDate] = useState("");

  const {
    ytConnected, ytChannels, ytSelectedChannel, setYtSelectedChannel,
    ttConnected, igConnected,
    handlePlatformAuth, checkPlatformStatus,
  } = platformAuth;

  if (!show) return null;

  const handleUpload = async () => {
    if (!generatedVideoPath) return;
    setUploading(true);
    setUploadResult(null);
    try {
      let body: Record<string, unknown>;
      let endpoint: string;

      if (uploadPlatform === "youtube") {
        endpoint = "/api/youtube/upload";
        const hashtagsInDesc = (uploadDescription.match(/#[^\s#]+/g) || []).map(t => t.slice(1));
        const manualTags = uploadTags.split(/[,\s]+/).map(t => t.replace(/^#/, "").trim()).filter(Boolean);
        const allTags = [...new Set([...hashtagsInDesc, ...manualTags])];
        const hasHashtagsInDesc = /#[^\s#]+/.test(uploadDescription);
        const extraHashtags = manualTags.filter(t => !hashtagsInDesc.includes(t));
        const hashtagLine = extraHashtags.map(t => `#${t.replace(/\s+/g, "")}`).join(" ");
        const finalDesc = hasHashtagsInDesc
          ? (hashtagLine ? `${uploadDescription}\n${hashtagLine}` : uploadDescription)
          : (hashtagLine ? `${uploadDescription}\n\n${hashtagLine}` : uploadDescription);
        body = {
          video_path: generatedVideoPath,
          title: uploadTitle || topic,
          description: finalDesc,
          tags: allTags,
          privacy: scheduleEnabled ? "private" : uploadPrivacy,
          channel_id: (() => {
            const matched = ytChannels.find((ch: any) => ch.title?.toLowerCase().replace(/\s/g, '') === (uploadChannel || '').toLowerCase().replace(/\s/g, ''));
            return matched?.id || ytSelectedChannel || undefined;
          })(),
          channel: uploadChannel || undefined,
          ...(scheduleEnabled && scheduleDate ? { publish_at: new Date(scheduleDate).toISOString() } : {}),
        };
      } else if (uploadPlatform === "tiktok") {
        endpoint = "/api/tiktok/upload";
        body = {
          video_path: generatedVideoPath,
          title: uploadTitle || topic,
          privacy_level: ttPrivacy,
          channel: uploadChannel || undefined,
          ...(scheduleEnabled && scheduleDate ? { schedule_time: Math.floor(new Date(scheduleDate).getTime() / 1000) } : {}),
        };
      } else {
        endpoint = "/api/instagram/upload";
        body = {
          video_path: generatedVideoPath,
          caption: `${uploadTitle || topic}\n\n${uploadDescription}`.trim(),
          channel: uploadChannel || undefined,
        };
      }

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success) {
        setUploadResult({ success: true, url: data.url, scheduled_at: data.scheduled_at });
      } else {
        setUploadResult({ success: false, error: data.error });
      }
    } catch {
      setUploadResult({ success: false, error: "\uc5c5\ub85c\ub4dc \uc694\uccad \uc2e4\ud328" });
    } finally {
      setUploading(false);
    }
  };

  const preset = uploadChannel ? CHANNEL_PRESETS[uploadChannel] : null;
  const platformMap: Record<string, string> = { youtube: "youtube", tiktok: "tiktok", reels: "instagram" };
  const availablePlatforms = preset
    ? preset.platforms.map(p => platformMap[p] || p).filter((v, i, a) => a.indexOf(v) === i) as ("youtube" | "tiktok" | "instagram")[]
    : ["youtube" as const, "tiktok" as const, "instagram" as const];

  const isNotConnected = (uploadPlatform === "youtube" && !ytConnected) ||
    (uploadPlatform === "tiktok" && !ttConnected) ||
    (uploadPlatform === "instagram" && !igConnected);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={() => !uploading && onClose()}
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md glass-panel rounded-2xl border border-white/10 p-6 space-y-5 max-h-[85vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <h3 className="text-lg text-white font-bold">
            {"\uc5c5\ub85c\ub4dc"} {"\u2014"} <span className="text-indigo-400">{(() => { const p = uploadChannel ? CHANNEL_PRESETS[uploadChannel] : null; return p ? `${p.flag} ${p.label}` : uploadChannel || ""; })()}</span>
          </h3>
          <button onClick={() => !uploading && onClose()} className="text-gray-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Platform tabs */}
        {availablePlatforms.length > 1 && (
          <div className="flex gap-1 bg-white/5 rounded-xl p-1">
            {availablePlatforms.includes("youtube") && (
              <button onClick={() => { setUploadPlatform("youtube"); setUploadResult(null); }}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-colors ${uploadPlatform === "youtube" ? "bg-red-600 text-white" : "text-gray-400 hover:text-white"}`}>
                <Youtube className="w-4 h-4" /> YouTube
              </button>
            )}
            {availablePlatforms.includes("tiktok") && (
              <button onClick={() => { setUploadPlatform("tiktok"); setUploadResult(null); }}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-colors ${uploadPlatform === "tiktok" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"}`}>
                <Send className="w-4 h-4" /> TikTok
              </button>
            )}
            {availablePlatforms.includes("instagram") && (
              <button onClick={() => { setUploadPlatform("instagram"); setUploadResult(null); }}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-colors ${uploadPlatform === "instagram" ? "bg-gradient-to-r from-purple-600 to-pink-500 text-white" : "text-gray-400 hover:text-white"}`}>
                <Instagram className="w-4 h-4" /> Reels
              </button>
            )}
          </div>
        )}

        {/* Not connected */}
        {isNotConnected ? (
          <div className="space-y-4 text-center py-4">
            <p className="text-gray-400 text-sm">
              {uploadPlatform === "youtube" && "YouTube \uacc4\uc815\uc744 \uba3c\uc800 \uc5f0\ub3d9\ud574\uc8fc\uc138\uc694."}
              {uploadPlatform === "tiktok" && "TikTok \uacc4\uc815\uc744 \uba3c\uc800 \uc5f0\ub3d9\ud574\uc8fc\uc138\uc694."}
              {uploadPlatform === "instagram" && "Instagram Business \uacc4\uc815\uc744 \uba3c\uc800 \uc5f0\ub3d9\ud574\uc8fc\uc138\uc694."}
            </p>
            <button
              onClick={() => handlePlatformAuth(uploadPlatform, uploadChannel, (msg) => setUploadResult({ success: false, error: msg }))}
              className={`px-6 py-3 text-white font-semibold rounded-xl transition-colors flex items-center gap-2 mx-auto ${
                uploadPlatform === "youtube" ? "bg-red-600 hover:bg-red-500" :
                uploadPlatform === "tiktok" ? "bg-gray-700 hover:bg-gray-600" :
                "bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400"
              }`}
            >
              {uploadPlatform === "youtube" && <Youtube className="w-5 h-5" />}
              {uploadPlatform === "tiktok" && <Send className="w-5 h-5" />}
              {uploadPlatform === "instagram" && <Instagram className="w-5 h-5" />}
              {"\uacc4\uc815 \uc5f0\ub3d9"}
            </button>
            {uploadResult && !uploadResult.success && (
              <p className="text-red-400 text-sm">{uploadResult.error}</p>
            )}
          </div>
        ) : uploadResult?.success ? (
          <div className="space-y-4 text-center py-4">
            <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto" />
            <h4 className="text-white font-bold">
              {uploadResult.scheduled_at ? "\uc608\uc57d \uc5c5\ub85c\ub4dc \uc644\ub8cc!" : "\uc5c5\ub85c\ub4dc \uc644\ub8cc!"}
            </h4>
            {uploadResult.scheduled_at && (
              <p className="text-indigo-300 text-sm">
                {new Date(typeof uploadResult.scheduled_at === "number" ? uploadResult.scheduled_at * 1000 : uploadResult.scheduled_at).toLocaleString("ko-KR")}{"\uc5d0 \uacf5\uac1c\ub429\ub2c8\ub2e4."}
              </p>
            )}
            {uploadResult.url && (
              <a href={uploadResult.url} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl transition-colors">
                <ExternalLink className="w-4 h-4" /> {"\uc601\uc0c1 \ubcf4\uae30"}
              </a>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="text-gray-400 text-xs mb-1 block">{"\uc81c\ubaa9"}</label>
              <input type="text" value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)}
                maxLength={uploadPlatform === "tiktok" ? 150 : 100}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50" />
            </div>

            {uploadPlatform !== "tiktok" && (
              <div>
                <label className="text-gray-400 text-xs mb-1 block">
                  {uploadPlatform === "instagram" ? "\uce21\uc158" : "\uc124\uba85"}
                </label>
                <textarea value={uploadDescription} onChange={(e) => setUploadDescription(e.target.value)}
                  rows={3} maxLength={uploadPlatform === "instagram" ? 2200 : 5000}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 resize-none" />
              </div>
            )}

            {uploadPlatform === "youtube" && (
              <div>
                <label className="text-gray-400 text-xs mb-1 block">{"\ud0dc\uadf8 (\uc27c\ud45c\ub85c \uad6c\ubd84)"}</label>
                <input type="text" value={uploadTags} onChange={(e) => setUploadTags(e.target.value)}
                  placeholder="AI, \uc21f\ud3fc, \uacfc\ud559"
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50" />
              </div>
            )}

            {uploadPlatform === "youtube" && ytChannels.length > 0 && (
              <div>
                <label className="text-gray-400 text-xs mb-1 block">{"\ucc44\ub110 \uc120\ud0dd"}</label>
                <select
                  value={(() => {
                    const channelNameMap: Record<string, string> = {
                      askanything: "AskAnything", wonderdrop: "Wonder Drop", exploratodo: "ExploraTodo", prismtale: "Prism Tale",
                    };
                    const targetName = channelNameMap[uploadChannel] || "";
                    const matched = ytChannels.find(c => c.title === targetName);
                    return matched?.id || ytSelectedChannel;
                  })()}
                  onChange={(e) => setYtSelectedChannel(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 appearance-none cursor-pointer"
                >
                  {ytChannels.filter(ch => ch.connected).map(ch => (
                    <option key={ch.id} value={ch.id} className="bg-gray-900">{ch.title}</option>
                  ))}
                </select>
              </div>
            )}

            <div>
              <label className="text-gray-400 text-xs mb-1 block">{"\uacf5\uac1c \uc124\uc815"}</label>
              {uploadPlatform === "youtube" ? (
                <select value={uploadPrivacy} onChange={(e) => setUploadPrivacy(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 appearance-none cursor-pointer">
                  <option value="private" className="bg-gray-900">{"\ube44\uacf5\uac1c"}</option>
                  <option value="unlisted" className="bg-gray-900">{"\ubbf8\ub4f1\ub85d (\ub9c1\ud06c \uacf5\uc720)"}</option>
                  <option value="public" className="bg-gray-900">{"\uacf5\uac1c"}</option>
                </select>
              ) : uploadPlatform === "tiktok" ? (
                <select value={ttPrivacy} onChange={(e) => setTtPrivacy(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 appearance-none cursor-pointer">
                  <option value="SELF_ONLY" className="bg-gray-900">{"\ubcf8\uc778\ub9cc"}</option>
                  <option value="MUTUAL_FOLLOW_FRIENDS" className="bg-gray-900">{"\uce5c\uad6c\ub9cc"}</option>
                  <option value="FOLLOWER_OF_CREATOR" className="bg-gray-900">{"\ud314\ub85c\uc6cc\ub9cc"}</option>
                  <option value="PUBLIC_TO_EVERYONE" className="bg-gray-900">{"\uc804\uccb4 \uacf5\uac1c"}</option>
                </select>
              ) : (
                <p className="text-gray-500 text-xs">Instagram Reels{"\ub294 \ud56d\uc0c1 \uacf5\uac1c\ub85c \uac8c\uc2dc\ub429\ub2c8\ub2e4."}</p>
              )}
            </div>

            {uploadPlatform !== "instagram" && (
              <div>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={scheduleEnabled}
                    onChange={(e) => { setScheduleEnabled(e.target.checked); if (!e.target.checked) setScheduleDate(""); }}
                    className="w-4 h-4 rounded bg-white/5 border-white/20 text-indigo-500 focus:ring-indigo-500/50" />
                  <span className="text-gray-300 text-sm">{"\uc608\uc57d \uc5c5\ub85c\ub4dc"}</span>
                </label>
                {scheduleEnabled && (
                  <div className="mt-2">
                    <input type="datetime-local" value={scheduleDate}
                      onChange={(e) => setScheduleDate(e.target.value)}
                      min={new Date(Date.now() + (uploadPlatform === "tiktok" ? 15 * 60 * 1000 : 60 * 1000)).toISOString().slice(0, 16)}
                      max={uploadPlatform === "tiktok" ? new Date(Date.now() + 75 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16) : undefined}
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50" />
                    {uploadPlatform === "youtube" && (() => {
                      const windows: Record<string, {start: number, end: number, label: string}> = {
                        askanything: {start: 18, end: 22, label: "KST"},
                        wonderdrop: {start: 6, end: 10, label: "KST (=EST 17~21\uc2dc)"},
                        exploratodo: {start: 9, end: 13, label: "KST (=CST 19~23\uc2dc)"},
                        prismtale: {start: 7, end: 11, label: "KST (=EST 18~22\uc2dc)"},
                      };
                      const w = windows[uploadChannel] || windows.askanything;
                      const tomorrow = new Date();
                      tomorrow.setDate(tomorrow.getDate() + 1);
                      const slots = [];
                      for (let h = w.start; h < w.end; h++) {
                        const d = new Date(tomorrow);
                        d.setHours(h, 0, 0, 0);
                        slots.push(d);
                      }
                      const halfSlot = new Date(tomorrow);
                      halfSlot.setHours(w.start, 30, 0, 0);
                      slots.splice(1, 0, halfSlot);
                      return (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          <span className="text-[10px] text-gray-500 w-full">{"\ucd94\ucc9c \uc2dc\uac04"} ({w.label}):</span>
                          {slots.slice(0, 5).map((slot, i) => (
                            <button key={i} type="button"
                              onClick={() => {
                                const iso = new Date(slot.getTime() - slot.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
                                setScheduleDate(iso);
                              }}
                              className={`px-2.5 py-1 rounded-lg text-xs transition-colors ${scheduleDate && new Date(scheduleDate).getHours() === slot.getHours() && new Date(scheduleDate).getMinutes() === slot.getMinutes() ? 'bg-indigo-600 text-white' : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white'}`}
                            >
                              {slot.getHours().toString().padStart(2, '0')}:{slot.getMinutes().toString().padStart(2, '0')}
                            </button>
                          ))}
                        </div>
                      );
                    })()}
                    <p className="text-gray-500 text-xs mt-1">
                      {uploadPlatform === "youtube"
                        ? "\ube44\uacf5\uac1c\ub85c \uc5c5\ub85c\ub4dc \ud6c4 \uc608\uc57d \uc2dc\uac04\uc5d0 \uc790\ub3d9 \uacf5\uac1c\ub429\ub2c8\ub2e4."
                        : "15\ubd84 ~ 75\uc77c \uc774\ub0b4\ub85c \uc124\uc815\ud574\uc8fc\uc138\uc694."}
                    </p>
                  </div>
                )}
              </div>
            )}

            {uploadPlatform === "instagram" && (
              <div>
                <p className="text-amber-400/80 text-xs">Instagram{"\uc740 \uacf5\uac1c URL\uc774 \ud544\uc694\ud569\ub2c8\ub2e4."} PUBLIC_SERVER_URL {"\ub610\ub294"} ngrok {"\uc124\uc815\uc774 \ud544\uc694\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4."}</p>
                <p className="text-gray-500 text-xs mt-1">Instagram{"\uc740 API\ub97c \ud1b5\ud55c \uc608\uc57d \uc5c5\ub85c\ub4dc\ub97c \uc9c0\uc6d0\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4."}</p>
              </div>
            )}

            {uploadResult && !uploadResult.success && (
              <p className="text-red-400 text-sm">{uploadResult.error}</p>
            )}

            <button
              onClick={handleUpload}
              disabled={uploading || !uploadTitle.trim() || (scheduleEnabled && !scheduleDate)}
              className={`w-full py-3 disabled:bg-gray-700 disabled:text-gray-400 text-white font-semibold rounded-xl transition-colors flex items-center justify-center gap-2 ${
                uploadPlatform === "youtube" ? "bg-red-600 hover:bg-red-500" :
                uploadPlatform === "tiktok" ? "bg-gray-700 hover:bg-gray-600" :
                "bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400"
              }`}
            >
              {uploading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {"\uc5c5\ub85c\ub4dc \uc911..."}
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  {scheduleEnabled
                    ? (uploadPlatform === "youtube" ? "YouTube \uc608\uc57d \uc5c5\ub85c\ub4dc" : "TikTok \uc608\uc57d \uc5c5\ub85c\ub4dc")
                    : (uploadPlatform === "youtube" ? "YouTube \uc5c5\ub85c\ub4dc" : uploadPlatform === "tiktok" ? "TikTok \uc5c5\ub85c\ub4dc" : "Reels \uc5c5\ub85c\ub4dc")
                  }
                </>
              )}
            </button>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}
