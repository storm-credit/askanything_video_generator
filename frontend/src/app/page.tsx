"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Settings, Globe, Crown, FolderOpen, FlaskConical, Square, Youtube, Download, AlertCircle } from "lucide-react";
import { API_BASE } from "../components/types";
import { KeyStatus, KeyUsageStats } from "../components/types";
import { SettingsModal } from "../components/SettingsModal";
import { ProgressPanel } from "../components/ProgressPanel";
import { CHANNEL_PRESETS } from "./constants";

// Hooks
import { useLocalSettings } from "./hooks/useLocalSettings";
import { useSSEGenerate } from "./hooks/useSSEGenerate";
import { usePlatformAuth } from "./hooks/usePlatformAuth";

// Components
import { ChannelSelector } from "./components/ChannelSelector";
import { EnginePanel } from "./components/EnginePanel";
import { DirectionPanel } from "./components/DirectionPanel";
import { DashboardModal } from "./components/DashboardModal";
import { TodayModal } from "./components/TodayModal";
import { SessionBrowser } from "./components/SessionBrowser";
import { UploadModal } from "./components/UploadModal";
import { MultiChannelPanel } from "./components/MultiChannelPanel";
import { RenderPanel } from "./components/RenderPanel";
import { PreviewPanel } from "./components/PreviewPanel";
import { SuccessPanel } from "./components/SuccessPanel";

export default function Home() {
  const [topic, setTopic] = useState("");
  const [todayCuts, setTodayCuts] = useState<Record<string, any[]> | null>(null);
  const [todayMeta, setTodayMeta] = useState<Record<string, { title: string; description: string; hashtags: string }> | null>(null);

  // Today modal state
  const [showTodayModal, setShowTodayModal] = useState(false);
  const [todayTopics, setTodayTopics] = useState<any[]>([]);
  const [todayFile, setTodayFile] = useState("");
  const [todayDate, setTodayDate] = useState<string | null>(null);
  const [todayPrevDate, setTodayPrevDate] = useState<string | null>(null);
  const [todayNextDate, setTodayNextDate] = useState<string | null>(null);

  // Dashboard modal
  const [showDashboard, setShowDashboard] = useState(false);
  const [dashboardData, setDashboardData] = useState<Record<string, any>>({});
  const [dashboardLoading, setDashboardLoading] = useState(false);

  // Session browser
  const [showSessionBrowser, setShowSessionBrowser] = useState(false);
  const [savedSessions, setSavedSessions] = useState<Array<{ folder: string; title: string; cuts_count: number; image_count: number; has_video: boolean; channel: string; language: string; created_at: string }>>([]);

  // Upload modal
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadChannel, setUploadChannel] = useState("");
  const [uploadInitialTitle, setUploadInitialTitle] = useState("");
  const [uploadInitialDesc, setUploadInitialDesc] = useState("");
  const [uploadInitialTags, setUploadInitialTags] = useState("");

  // Settings modal
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [serverKeyStatus, setServerKeyStatus] = useState<KeyStatus | null>(null);
  const [googleKeyCount, setGoogleKeyCount] = useState(0);
  const [serverMaskedKeys, setServerMaskedKeys] = useState<Record<string, string[]>>({});
  const [savedKeys, setSavedKeys] = useState<Record<string, string[]>>(() => {
    if (typeof window === "undefined") return {};
    try { const stored = localStorage.getItem("askanything_keys"); return stored ? JSON.parse(stored) : {}; } catch { return {}; }
  });
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  const [keyUsageStats, setKeyUsageStats] = useState<KeyUsageStats | null>(null);
  const [modelLimits, setModelLimits] = useState<Record<string, { rpm: number; rpd: number; used: number; total_rpd: number; remaining: number }> | null>(null);

  // Hooks
  const settings = useLocalSettings();
  const platformAuth = usePlatformAuth();
  const sse = useSSEGenerate({
    settings,
    savedKeys,
    topic,
    todayCuts,
    todayMeta,
    checkPlatformStatus: platformAuth.checkPlatformStatus,
  });

  // YouTube URL detection
  const isYouTubeUrl = (text: string) => /(?:youtube\.com\/(?:shorts\/|watch\?v=)|youtu\.be\/)/.test(text.trim());
  const detectedRefUrl = isYouTubeUrl(topic) ? topic.trim() : undefined;

  // Settings key management
  const fetchKeyStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      if (res.ok) {
        const data = await res.json();
        setServerKeyStatus(data.keys || null);
        if (data.google_key_count) setGoogleKeyCount(data.google_key_count);
        if (data.masked_keys) setServerMaskedKeys(data.masked_keys);
      }
    } catch {}
  }, []);

  const fetchKeyUsage = useCallback(async () => {
    try { const res = await fetch(`${API_BASE}/api/key-usage`); if (res.ok) setKeyUsageStats(await res.json()); } catch {}
  }, []);

  const fetchModelLimits = useCallback(async () => {
    try { const res = await fetch(`${API_BASE}/api/model-limits`); if (res.ok) setModelLimits(await res.json()); } catch {}
  }, []);

  useEffect(() => { fetchKeyStatus(); }, [fetchKeyStatus]);
  useEffect(() => { fetchModelLimits(); }, [fetchModelLimits]);
  useEffect(() => {
    if (isSettingsOpen) { fetchKeyStatus(); fetchKeyUsage(); fetchModelLimits(); }
  }, [isSettingsOpen, fetchKeyStatus, fetchKeyUsage, fetchModelLimits]);

  useEffect(() => {
    try { localStorage.setItem("askanything_keys", JSON.stringify(savedKeys)); } catch {}
  }, [savedKeys]);

  const addKey = async (configId: string) => {
    const value = (inputValues[configId] || "").trim();
    if (!value) return;
    setSavedKeys((prev) => {
      const existing = prev[configId] || [];
      if (existing.includes(value)) return prev;
      return { ...prev, [configId]: [...existing, value] };
    });
    setInputValues((prev) => ({ ...prev, [configId]: "" }));
    try {
      await fetch(`${API_BASE}/api/settings/add-env-key`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyType: configId, key: value }),
      });
    } catch {}
  };

  const removeKey = (configId: string, index: number) => {
    setSavedKeys((prev) => {
      const existing = [...(prev[configId] || [])];
      existing.splice(index, 1);
      return { ...prev, [configId]: existing };
    });
  };

  const remainLabel = (modelId: string): string => {
    if (!modelLimits || !modelLimits[modelId]) return "";
    const m = modelLimits[modelId];
    return ` [${m.remaining}/${m.total_rpd}\ud68c]`;
  };

  // Key status badge
  const totalSavedKeys = Object.values(savedKeys).reduce((sum, arr) => sum + arr.length, 0);
  const totalServerKeys = serverKeyStatus ? Object.values(serverKeyStatus).filter(Boolean).length : 0;
  const hasOpenai = !!(serverKeyStatus?.openai || (savedKeys["openai"]?.length ?? 0) > 0);
  const hasElevenlabs = !!(serverKeyStatus?.elevenlabs || (savedKeys["elevenlabs"]?.length ?? 0) > 0);
  const requiredAllSet = hasOpenai && hasElevenlabs;
  const requiredSomeSet = hasOpenai || hasElevenlabs || totalServerKeys > 0 || totalSavedKeys > 0;
  const iconStyle = requiredAllSet
    ? "border-green-500/40 bg-green-500/10 text-green-400 hover:bg-green-500/20"
    : requiredSomeSet
      ? "border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
      : "border-white/20 bg-white/5 text-gray-400 hover:bg-white/10";

  // Upload modal open helper
  const openUploadModal = (platform: "youtube" | "tiktok" | "instagram", ch: string, videoUrl: string) => {
    const videoPath = decodeURIComponent(videoUrl.replace(API_BASE, ''));
    sse.setGeneratedVideoPath(videoPath);
    sse.setGeneratedVideoUrl(videoUrl);
    setUploadChannel(ch);
    const meta = todayMeta?.[ch];
    const chPreview = sse.channelPreviews[ch];
    const genTitle = meta?.title || chPreview?.title || topic;
    const genDesc = meta?.description || (chPreview?.cuts || []).map((c: any) => c.script || "").filter(Boolean).join("\n") || `AI\uac00 \uc0dd\uc131\ud55c \uc21f\ud3fc \uc601\uc0c1: ${genTitle}`;
    const genTags = meta?.hashtags || (chPreview?.cuts?.[0] as any)?.tags?.join(", ") || topic;
    setUploadInitialTitle(genTitle);
    setUploadInitialDesc(genDesc);
    setUploadInitialTags(platform === "youtube" ? genTags : "");
    setShowUploadModal(true);
    platformAuth.checkPlatformStatus();
  };

  // Today topic select handler
  const handleSelectTodayTopic = (t: any) => {
    const topicName = t.topic_group?.replace(/^[^\s]+\s*/, "") || t.topic_group;
    setTopic(topicName);
    setTodayCuts(null);
    const channelMeta: Record<string, { title: string; description: string; hashtags: string }> = {};
    if (t.channels) {
      for (const [ch, chData] of Object.entries(t.channels as Record<string, any>)) {
        channelMeta[ch] = { title: chData.title || topicName, description: chData.description || "", hashtags: chData.hashtags || "" };
      }
    }
    setTodayMeta(Object.keys(channelMeta).length > 0 ? channelMeta : null);
    const topicChannels = Object.keys(t.channels || {});
    if (topicChannels.length > 0) {
      settings.setSelectedChannels(topicChannels);
      if (topicChannels.length === 1) settings.setChannel(topicChannels[0]);
      const langMap: Record<string, string> = { askanything: "ko", wonderdrop: "en", exploratodo: "es", prismtale: "es" };
      settings.setLanguage(topicChannels.length === 1 ? (langMap[topicChannels[0]] || "ko") : "auto");
    }
    setShowTodayModal(false);
  };

  return (
    <main className="min-h-screen relative flex flex-col items-center justify-center p-6 sm:p-24 bg-black overflow-hidden">

      {/* Top right buttons */}
      <div className="absolute top-6 right-6 z-50 flex gap-2">
        <button
          onClick={async () => {
            setShowDashboard(true);
            setDashboardLoading(true);
            try {
              const res = await fetch(`${API_BASE}/api/stats/all?refresh=true`);
              const data = await res.json();
              if (data.success) setDashboardData(data.channels || {});
            } catch {}
            setDashboardLoading(false);
          }}
          className={`w-11 h-11 rounded-full border backdrop-blur-md flex items-center justify-center transition-all duration-300 hover:scale-110 ${iconStyle}`}
          title={"\uc131\uacfc \ub300\uc2dc\ubcf4\ub4dc"}
        >
          <span className="text-lg">{"\ud83d\udcca"}</span>
        </button>
        <button
          onClick={() => setIsSettingsOpen(true)}
          className={`w-11 h-11 rounded-full border backdrop-blur-md flex items-center justify-center transition-all duration-300 hover:scale-110 ${iconStyle}`}
          title="API \ud0a4 \uc124\uc815"
          aria-label="API \ud0a4 \uc124\uc815"
        >
          <Settings className="w-5 h-5" />
        </button>
      </div>

      {/* Settings modal */}
      <AnimatePresence>
        {isSettingsOpen && (
          <SettingsModal
            serverKeyStatus={serverKeyStatus}
            savedKeys={savedKeys}
            inputValues={inputValues}
            visibleKeys={visibleKeys}
            outputPath={settings.outputPath}
            keyUsageStats={keyUsageStats}
            totalServerKeys={totalServerKeys}
            totalSavedKeys={totalSavedKeys}
            googleKeyCount={googleKeyCount}
            serverMaskedKeys={serverMaskedKeys}
            onClose={() => setIsSettingsOpen(false)}
            onInputChange={(id, v) => setInputValues((prev) => ({ ...prev, [id]: v }))}
            onAddKey={addKey}
            onRemoveKey={removeKey}
            onToggleVisible={(id) => setVisibleKeys((prev) => ({ ...prev, [id]: !prev[id] }))}
            onOutputPathChange={settings.setOutputPath}
          />
        )}
      </AnimatePresence>

      {/* Background ambient light */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-500/20 rounded-full blur-[120px] pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="z-10 w-full max-w-2xl text-center space-y-8"
      >
        <div className="space-y-4">
          <motion.div
            initial={{ scale: 0.95 }}
            animate={{ scale: 1 }}
            transition={{ duration: 1.5, repeat: Infinity, repeatType: "reverse" }}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass-panel text-sm text-gray-300"
          >
            <Sparkles className="w-4 h-4 text-indigo-400" />
            <span>{"\ud504\ub9ac\ubbf8\uc5c4 AI \ube44\ub514\uc624 \uc2a4\ud29c\ub514\uc624"}</span>
          </motion.div>
          <h1 className="text-5xl sm:text-7xl font-bold tracking-tight text-gradient">
            {"\ub2f9\uc2e0\uc758 \uc0c1\uc0c1\uc744"}<br/>{"\uc601\uc0c1\uc73c\ub85c."}
          </h1>
          <p className="text-gray-400 text-lg sm:text-xl">
            {"\ub2e8 \ud558\ub098\uc758 \uc8fc\uc81c\ub9cc \uc785\ub825\ud558\uc138\uc694. \uae30\ud68d, \ub514\uc790\uc778, \ud3b8\uc9d1\uc744 AI \uc804\ubb38\uac00\ub4e4\uc774 \uc54c\uc544\uc11c \uc644\uc131\ud569\ub2c8\ub2e4."}
          </p>
        </div>

        <form onSubmit={sse.handleGenerate} className="relative max-w-xl mx-auto mt-12 space-y-4">
          <div className="relative flex items-center">
            <input
              type="text"
              value={topic}
              onChange={(e) => { setTopic(e.target.value); setTodayCuts(null); setTodayMeta(null); }}
              disabled={sse.isGenerating}
              placeholder={"\uc8fc\uc81c \ub610\ub294 YouTube URL \u2014 \uc608: \ube14\ub799\ud640\uc5d0 \ub5a8\uc5b4\uc9c0\uba74 \uc5b4\ub5bb\uac8c \ub420\uae4c?"}
              className="w-full bg-white/5 border border-white/10 rounded-2xl py-5 pl-6 pr-6 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all text-lg backdrop-blur-md"
            />
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-center gap-2 flex-wrap">
            {sse.isGenerating ? (
              <button type="button" onClick={sse.handleCancel} aria-label={"\uc0dd\uc131 \ucde8\uc18c"}
                className="bg-red-600 text-white hover:bg-red-500 font-semibold px-6 py-2.5 rounded-xl transition-colors flex items-center gap-2 text-sm">
                <Square className="w-4 h-4 fill-current" /> {"\ucde8\uc18c"}
              </button>
            ) : (
              <>
                <button type="button"
                  onClick={() => sse.loadSessionList(setSavedSessions, setShowSessionBrowser)}
                  className="bg-blue-600 text-white hover:bg-blue-500 font-semibold px-4 py-2.5 rounded-xl transition-colors text-sm">
                  {"\ubd88\ub7ec\uc624\uae30"}
                </button>
                <button type="button"
                  onClick={async () => {
                    try {
                      const res = await fetch(`${API_BASE}/api/batch/today-topics`);
                      const data = await res.json();
                      if (data.success && data.topics?.length > 0) {
                        setTodayTopics(data.topics);
                        setTodayFile(data.file || "");
                        setTodayDate(data.current_date || null);
                        setTodayPrevDate(data.prev_date || null);
                        setTodayNextDate(data.next_date || null);
                        setShowTodayModal(true);
                      } else {
                        sse.setErrorMessage(data.message || "\uc624\ub298 \uc8fc\uc81c\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4");
                      }
                    } catch {
                      sse.setErrorMessage("\uc624\ub298 \ud560 \uc77c \ubd88\ub7ec\uc624\uae30 \uc2e4\ud328: \uc11c\ubc84 \uc5f0\uacb0\uc744 \ud655\uc778\ud558\uc138\uc694.");
                    }
                  }}
                  className="bg-emerald-600 text-white hover:bg-emerald-500 font-semibold px-4 py-2.5 rounded-xl transition-colors text-sm flex items-center gap-1.5">
                  <Download className="w-3.5 h-3.5" /> {"\uc624\ub298 \ud560 \uc77c"}
                </button>
                <button type="button" onClick={sse.handlePrepare} disabled={!topic.trim()}
                  className="bg-purple-600 text-white hover:bg-purple-500 disabled:bg-gray-700 disabled:text-gray-400 font-semibold px-4 py-2.5 rounded-xl transition-colors text-sm">
                  {"\ubbf8\ub9ac\ubcf4\uae30"}
                </button>
                <button type="submit" disabled={!topic.trim()}
                  className="bg-orange-500 text-white hover:bg-orange-400 disabled:bg-gray-700 disabled:text-gray-400 font-semibold px-4 py-2.5 rounded-xl transition-colors text-sm">
                  {"\ubc14\ub85c\uc0dd\uc131"}
                </button>
              </>
            )}
          </div>

          {/* YouTube URL detection */}
          <AnimatePresence>
            {detectedRefUrl && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="w-full max-w-2xl mx-auto">
                <div className="flex items-center gap-2 px-3 py-2 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-xs text-indigo-300">
                  <Youtube className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>YouTube URL {"\uac10\uc9c0 \u2014 \uc774 \uc601\uc0c1\uc744 \ub808\ud37c\ub7f0\uc2a4\ub85c \ubd84\uc11d\ud558\uc5ec \ube44\uc2b7\ud55c \uc2a4\ud0c0\uc77c\uc758 \uc601\uc0c1\uc744 \uc0dd\uc131\ud569\ub2c8\ub2e4"}</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Control panels */}
          <div className="w-full max-w-2xl mx-auto space-y-3">
            {/* Global settings row */}
            <div className="bg-white/[0.04] border border-white/[0.08] rounded-2xl p-3">
              <div className="flex items-center justify-center gap-1.5">
                <div className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-full px-3 py-1.5">
                  <Crown className="w-3.5 h-3.5 text-amber-400" />
                  <select value={settings.qualityPreset} onChange={(e) => settings.applyPreset(e.target.value)} disabled={sse.isGenerating} aria-label={"\ud488\uc9c8 \uc120\ud0dd"} className="bg-transparent text-xs text-gray-200 focus:outline-none cursor-pointer appearance-none pr-3">
                    <option value="best" className="bg-gray-900">{"\ucd5c\uace0 \ud488\uc9c8"}</option>
                    <option value="balanced" className="bg-gray-900">{"\ud569\ub9ac\uc801"}</option>
                    <option value="fast" className="bg-gray-900">{"\ube60\ub978 \uc0dd\uc131"}</option>
                    <option value="manual" className="bg-gray-900">{"\uc218\ub3d9"}</option>
                  </select>
                </div>
                <div className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-full px-3 py-1.5">
                  <Globe className="w-3.5 h-3.5 text-blue-400" />
                  <select value={settings.selectedChannels.length >= 2 ? "auto" : settings.language} onChange={(e) => settings.setLanguage(e.target.value)} disabled={sse.isGenerating || settings.selectedChannels.length >= 2} aria-label={"\uc5b8\uc5b4 \uc120\ud0dd"} className={`bg-transparent text-xs focus:outline-none appearance-none pr-3 ${settings.selectedChannels.length >= 2 ? "text-gray-500 cursor-not-allowed" : "text-gray-200 cursor-pointer"}`}>
                    <option value="auto" className="bg-gray-900">Auto ({"\ucc44\ub110\ubcc4"})</option>
                    <option value="ko" className="bg-gray-900">{"\ud55c\uad6d\uc5b4"}</option>
                    <option value="en" className="bg-gray-900">English</option>
                    <option value="ja" className="bg-gray-900">{"\u65e5\u672c\u8a9e"}</option>
                    <option value="zh" className="bg-gray-900">{"\u4e2d\u6587"}</option>
                    <option value="es" className="bg-gray-900">{"Espa\u00f1ol"}</option>
                    <option value="fr" className="bg-gray-900">{"Fran\u00e7ais"}</option>
                    <option value="de" className="bg-gray-900">Deutsch</option>
                    <option value="pt" className="bg-gray-900">{"Portugu\u00eas"}</option>
                    <option value="ar" className="bg-gray-900">{"\u0627\u0644\u0639\u0631\u0628\u064a\u0629"}</option>
                    <option value="ru" className="bg-gray-900">{"\u0420\u0443\u0441\u0441\u043a\u0438\u0439"}</option>
                    <option value="hi" className="bg-gray-900">{"\u0939\u093f\u0928\u094d\u0926\u0940"}</option>
                    <option value="it" className="bg-gray-900">Italiano</option>
                    <option value="sv" className="bg-gray-900">Svenska</option>
                    <option value="da" className="bg-gray-900">Dansk</option>
                    <option value="no" className="bg-gray-900">Norsk</option>
                    <option value="nl" className="bg-gray-900">Nederlands</option>
                    <option value="tr" className="bg-gray-900">{"T\u00fcrk\u00e7e"}</option>
                  </select>
                </div>
                <div
                  className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-full px-3 py-1.5 cursor-pointer hover:bg-white/10 transition-colors"
                  onClick={() => {
                    const path = typeof window !== "undefined" ? window.prompt("영상 저장 경로 (비우면 기본 assets/ 사용):", settings.outputPath) : null;
                    if (path !== null) settings.setOutputPath(path);
                  }}
                  title={settings.outputPath || "\uae30\ubcf8 \uacbd\ub85c (assets/)"}
                >
                  <FolderOpen className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-xs text-gray-400 max-w-[80px] truncate">
                    {settings.outputPath ? settings.outputPath.split(/[\\/]/).pop() : "\uae30\ubcf8"}
                  </span>
                </div>
                <label className={`flex items-center gap-1 border rounded-full px-3 py-1.5 text-xs cursor-pointer transition-colors ${settings.testMode ? "bg-red-500/20 border-red-500/50 text-red-300" : "bg-white/5 border-white/10 text-gray-500 hover:bg-white/10"}`}>
                  <input type="checkbox" checked={settings.testMode} onChange={(e) => settings.setTestMode(e.target.checked)} className="sr-only" />
                  <FlaskConical className="w-3.5 h-3.5" />
                  <span>{settings.testMode ? "3\ucef7" : "TEST"}</span>
                </label>
              </div>
            </div>

            <ChannelSelector settings={settings} isGenerating={sse.isGenerating} />
            <EnginePanel settings={settings} isGenerating={sse.isGenerating} remainLabel={remainLabel} />
            <DirectionPanel settings={settings} isGenerating={sse.isGenerating} />
          </div>
        </form>
      </motion.div>

      {/* Progress panel (single channel) */}
      <AnimatePresence>
        {sse.isGenerating && Object.keys(sse.renderResults).length === 0 && (settings.selectedChannels.length < 2 || sse.previewMode || !sse.channelResults || Object.keys(sse.channelResults).length === 0) && (
          <ProgressPanel progress={sse.progress} logs={sse.logs} />
        )}
      </AnimatePresence>

      {/* Multi-channel generation panel */}
      <AnimatePresence>
        {((sse.isGenerating && settings.selectedChannels.length >= 2) || Object.values(sse.channelResults).some(r => r.status === 'done')) && Object.keys(sse.channelResults).length > 0 && (
          <MultiChannelPanel
            channelResults={sse.channelResults}
            channelPreviews={sse.channelPreviews}
            topic={topic}
            todayMeta={todayMeta}
            onOpenUpload={openUploadModal}
          />
        )}
      </AnimatePresence>

      {/* Render results panel */}
      <AnimatePresence>
        {Object.keys(sse.renderResults).length > 0 && (
          <RenderPanel
            renderResults={sse.renderResults}
            activeRenderTab={sse.activeRenderTab}
            setActiveRenderTab={sse.setActiveRenderTab}
            topic={topic}
            todayMeta={todayMeta}
            onOpenUpload={openUploadModal}
          />
        )}
      </AnimatePresence>

      {/* Preview panel */}
      <AnimatePresence>
        <PreviewPanel
          previewMode={sse.previewMode}
          isGenerating={sse.isGenerating}
          previewData={sse.previewData}
          channelPreviews={sse.channelPreviews}
          activePreviewTab={sse.activePreviewTab}
          setActivePreviewTab={sse.setActivePreviewTab}
          editedScripts={sse.editedScripts}
          setEditedScripts={sse.setEditedScripts}
          editedScriptsMap={sse.editedScriptsMap}
          setEditedScriptsMap={sse.setEditedScriptsMap}
          replacingCut={sse.replacingCut}
          regeneratingCut={sse.regeneratingCut}
          generatingScripts={sse.generatingScripts}
          progress={sse.progress}
          logs={sse.logs}
          setPreviewMode={sse.setPreviewMode}
          setPreviewData={sse.setPreviewData}
          setChannelPreviews={sse.setChannelPreviews}
          onRender={sse.handleRender}
          onGenerateScripts={sse.handleGenerateScripts}
          onBatchGenerateImages={sse.handleBatchGenerateImages}
          onRegenerateImage={sse.regenerateImage}
          onReplaceImage={sse.replaceImage}
        />
      </AnimatePresence>

      {/* Success panel */}
      <AnimatePresence>
        <SuccessPanel
          successMessage={sse.successMessage}
          isGenerating={sse.isGenerating}
          errorMessage={sse.errorMessage}
          generatedVideoUrl={sse.generatedVideoUrl}
          generatedVideoPath={sse.generatedVideoPath}
          isDownloading={sse.isDownloading}
          setIsDownloading={sse.setIsDownloading}
          topic={topic}
          channel={settings.channel}
          selectedChannels={settings.selectedChannels}
          todayMeta={todayMeta}
          onOpenUpload={openUploadModal}
        />
      </AnimatePresence>

      {/* Today modal */}
      <AnimatePresence>
        <TodayModal
          show={showTodayModal}
          onClose={() => setShowTodayModal(false)}
          todayTopics={todayTopics}
          todayFile={todayFile}
          todayDate={todayDate}
          todayPrevDate={todayPrevDate}
          todayNextDate={todayNextDate}
          setTodayTopics={setTodayTopics}
          setTodayFile={setTodayFile}
          setTodayDate={setTodayDate}
          setTodayPrevDate={setTodayPrevDate}
          setTodayNextDate={setTodayNextDate}
          onSelectTopic={handleSelectTodayTopic}
        />
      </AnimatePresence>

      {/* Session browser */}
      <AnimatePresence>
        <SessionBrowser
          show={showSessionBrowser}
          onClose={() => setShowSessionBrowser(false)}
          savedSessions={savedSessions}
          onRestore={(folders) => sse.restoreSession(folders, setTopic, setShowSessionBrowser)}
        />
      </AnimatePresence>

      {/* Upload modal */}
      <AnimatePresence>
        <UploadModal
          show={showUploadModal}
          onClose={() => setShowUploadModal(false)}
          generatedVideoPath={sse.generatedVideoPath}
          uploadChannel={uploadChannel}
          topic={topic}
          initialTitle={uploadInitialTitle}
          initialDescription={uploadInitialDesc}
          initialTags={uploadInitialTags}
          platformAuth={platformAuth}
        />
      </AnimatePresence>

      {/* Dashboard modal */}
      <AnimatePresence>
        <DashboardModal
          show={showDashboard}
          onClose={() => setShowDashboard(false)}
          dashboardData={dashboardData}
          dashboardLoading={dashboardLoading}
        />
      </AnimatePresence>

      {/* Error panel */}
      <AnimatePresence>
        {sse.errorMessage && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="mt-6 w-full max-w-xl glass-panel p-6 rounded-2xl relative z-10 border border-red-500/30 shadow-2xl shadow-red-500/10"
          >
            <div className="flex items-start gap-3">
              <AlertCircle className="w-6 h-6 text-red-500 shrink-0 mt-0.5" />
              <div className="space-y-2">
                <h3 className="text-lg text-red-400 font-bold">{"\uc624\ub958 \ubc1c\uc0dd"}</h3>
                <p className="text-gray-300 text-sm whitespace-pre-line">{sse.errorMessage}</p>
                <button onClick={sse.handleClearError}
                  className="mt-2 px-4 py-2 bg-white/10 hover:bg-white/20 text-gray-300 text-sm rounded-xl transition-colors">
                  {"\ub2eb\uae30"}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

    </main>
  );
}
