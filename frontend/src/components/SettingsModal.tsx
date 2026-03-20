"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { X, Plus, Trash2, Eye, EyeOff, BarChart3, Key, Puzzle, Tv, Globe, ChevronDown, ChevronUp, Youtube, Music, Instagram } from "lucide-react";
import { API_BASE, KeyConfig, KeyStatus, KeyUsageStats, KEY_CONFIGS } from "./types";

// ── 언어 목록 ──
const LANGUAGES: { code: string; label: string }[] = [
  { code: "ko", label: "한국어" },
  { code: "en", label: "English" },
  { code: "ja", label: "日本語" },
  { code: "zh", label: "中文" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
  { code: "pt", label: "Português" },
  { code: "ar", label: "العربية" },
  { code: "ru", label: "Русский" },
  { code: "hi", label: "हिन्दी" },
  { code: "it", label: "Italiano" },
  { code: "sv", label: "Svenska" },
  { code: "da", label: "Dansk" },
  { code: "no", label: "Norsk" },
  { code: "nl", label: "Nederlands" },
  { code: "tr", label: "Türkçe" },
  { code: "pl", label: "Polski" },
];

// ── 채널 데이터 타입 ──
interface ChannelConfig {
  language: string;
  platforms: string[];
  tts_speed: number;
  caption_size: number;
  caption_y: number;
  visual_style: string;
  tone: string;
  upload_accounts: Record<string, string | null>;
}

interface SettingsModalProps {
  serverKeyStatus: KeyStatus | null;
  savedKeys: Record<string, string[]>;
  inputValues: Record<string, string>;
  visibleKeys: Record<string, boolean>;
  outputPath: string;
  keyUsageStats: KeyUsageStats | null;
  totalServerKeys: number;
  totalSavedKeys: number;
  googleKeyCount: number;
  serverMaskedKeys: Record<string, string[]>;
  onClose: () => void;
  onInputChange: (configId: string, value: string) => void;
  onAddKey: (configId: string) => void;
  onRemoveKey: (configId: string, index: number) => void;
  onToggleVisible: (configId: string) => void;
  onOutputPathChange: (value: string) => void;
}

export function SettingsModal({
  serverKeyStatus,
  savedKeys,
  inputValues,
  visibleKeys,
  outputPath,
  keyUsageStats,
  totalServerKeys,
  totalSavedKeys,
  googleKeyCount,
  serverMaskedKeys,
  onClose,
  onInputChange,
  onAddKey,
  onRemoveKey,
  onToggleVisible,
  onOutputPathChange,
}: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<"core" | "extra" | "channels">("core");

  // ── 채널 관리 상태 ──
  const [channels, setChannels] = useState<Record<string, ChannelConfig>>({});
  const [channelsLoading, setChannelsLoading] = useState(false);
  const [expandedChannel, setExpandedChannel] = useState<string | null>(null);
  const [channelSaveStatus, setChannelSaveStatus] = useState<Record<string, "saved" | "saving" | "error" | null>>({});

  // ── 채널 데이터 로드 ──
  const fetchChannels = useCallback(async () => {
    setChannelsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/channels`);
      if (res.ok) {
        const data = await res.json();
        setChannels(data.channels || {});
      }
    } catch { /* server offline */ }
    setChannelsLoading(false);
  }, []);

  // Escape 키로 모달 닫기
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // 채널 탭 진입 시 로드
  useEffect(() => {
    if (activeTab === "channels") fetchChannels();
  }, [activeTab, fetchChannels]);

  const coreConfigs = KEY_CONFIGS.filter((c) => c.group === "core");
  const extraConfigs = KEY_CONFIGS.filter((c) => c.group === "extra");

  // ── 채널 필드 수정 (로컬 상태 업데이트) ──
  const updateChannelField = (name: string, field: string, value: unknown) => {
    setChannels((prev) => ({
      ...prev,
      [name]: { ...prev[name], [field]: value },
    }));
    setChannelSaveStatus((prev) => ({ ...prev, [name]: null })); // 변경됨 표시
  };

  // ── 플랫폼 토글 ──
  const togglePlatform = (name: string, platform: string) => {
    const current = channels[name]?.platforms || [];
    const updated = current.includes(platform)
      ? current.filter((p) => p !== platform)
      : [...current, platform];
    updateChannelField(name, "platforms", updated);
  };

  return (
    <>
      {/* 오버레이 */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[60]"
      />
      {/* 모달 */}
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="설정"
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
        className="fixed inset-4 sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:w-[600px] sm:max-h-[85vh] z-[70] bg-gray-900/95 border border-white/10 rounded-3xl shadow-2xl overflow-hidden flex flex-col"
      >
        {/* 모달 헤더 + 탭 */}
        <div className="px-6 pt-5 pb-0 border-b border-white/10">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-bold text-white">설정</h2>
              <p className="text-xs text-gray-500 mt-1">API 키, 엔진, 채널 관리</p>
            </div>
            <button
              onClick={onClose}
              aria-label="설정 닫기"
              className="w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          {/* 탭 버튼 */}
          <div className="flex gap-1">
            <button
              onClick={() => setActiveTab("core")}
              className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-t-xl transition-colors ${
                activeTab === "core"
                  ? "bg-white/[0.06] text-indigo-400 border-b-2 border-indigo-400"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              <Key className="w-3.5 h-3.5" />
              핵심 키
            </button>
            <button
              onClick={() => setActiveTab("extra")}
              className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-t-xl transition-colors ${
                activeTab === "extra"
                  ? "bg-white/[0.06] text-purple-400 border-b-2 border-purple-400"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              <Puzzle className="w-3.5 h-3.5" />
              추가 엔진
            </button>
            <button
              onClick={() => setActiveTab("channels")}
              className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-t-xl transition-colors ${
                activeTab === "channels"
                  ? "bg-white/[0.06] text-teal-400 border-b-2 border-teal-400"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              <Tv className="w-3.5 h-3.5" />
              채널 관리
            </button>
          </div>
        </div>

        {/* 모달 바디 — 탭 콘텐츠 */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 custom-scrollbar">
          {activeTab === "core" && (
            <>
              <p className="text-[10px] text-gray-500">Google 또는 OpenAI 중 하나 + ElevenLabs = 최소 구성</p>
              {coreConfigs.map((config) => (
                <KeySection
                  key={config.id}
                  config={config}
                  serverStatus={serverKeyStatus?.[config.statusKey] ?? null}
                  savedKeys={savedKeys[config.id] || []}
                  inputValue={inputValues[config.id] || ""}
                  isVisible={visibleKeys[config.id] || false}
                  serverKeyCount={config.id === "gemini" ? googleKeyCount : undefined}
                  envMaskedKeys={serverMaskedKeys[config.statusKey] || []}
                  onInputChange={(v) => onInputChange(config.id, v)}
                  onAdd={() => onAddKey(config.id)}
                  onRemove={(idx) => onRemoveKey(config.id, idx)}
                  onToggleVisible={() => onToggleVisible(config.id)}
                />
              ))}

              {/* 저장 경로 설정 */}
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">출력 설정</h3>
                <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <span className="text-sm font-medium text-white">저장 경로</span>
                      <p className="text-xs text-gray-500 mt-0.5">비어있으면 브라우저 다운로드 폴더에 저장됩니다</p>
                    </div>
                  </div>
                  <input
                    type="text"
                    value={outputPath}
                    onChange={(e) => onOutputPathChange(e.target.value)}
                    placeholder={"예: C:\\Users\\사용자\\Desktop\\output.mp4"}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-indigo-500/50 font-mono"
                  />
                </div>
              </div>

              {/* Google API 키 사용량 */}
              {keyUsageStats && keyUsageStats.total_keys > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-cyan-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                    <BarChart3 className="w-3.5 h-3.5" />
                    Google API 키 사용량 (세션)
                  </h3>
                  <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5 space-y-2">
                    <p className="text-[10px] text-gray-500 mb-2">
                      총 {keyUsageStats.total_keys}개 키 등록 · 서버 재시작 시 초기화
                    </p>
                    {keyUsageStats.keys.map((k) => {
                      const stateStyle = k.state === "blocked"
                        ? "bg-red-500/5 border border-red-500/20"
                        : k.state === "warning"
                          ? "bg-amber-500/5 border border-amber-500/20"
                          : "bg-white/[0.02]";
                      const keyColor = k.state === "blocked" ? "text-red-400" : k.state === "warning" ? "text-amber-400" : "text-gray-400";
                      const totalColor = k.state === "blocked" ? "text-red-400" : k.state === "warning" ? "text-amber-400" : "text-white";
                      return (
                        <div key={k.key} className={`flex items-center gap-2 px-3 py-2 rounded-lg ${stateStyle}`}>
                          <div className="flex items-center gap-1.5 w-32 shrink-0">
                            <div className={`w-2 h-2 rounded-full shrink-0 ${k.state === "blocked" ? "bg-red-500" : k.state === "warning" ? "bg-amber-500" : "bg-green-500"}`} />
                            <span className={`text-xs font-mono ${keyColor}`}>{k.key}</span>
                          </div>
                          <div className="flex-1 flex items-center gap-1.5 flex-wrap">
                            {Object.entries(k.blocked_services || {}).map(([svc, hours]) => (
                              <span key={svc} className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 font-medium">
                                {svc} {hours}h
                              </span>
                            ))}
                            {Object.entries(k.usage).map(([service, count]) => (
                              <span key={service} className={`text-[10px] px-1.5 py-0.5 rounded ${
                                (k.blocked_services || {})[service] ? "bg-red-500/10 text-red-400/60 line-through" : "bg-cyan-500/15 text-cyan-400"
                              }`}>
                                {service}: {count}
                              </span>
                            ))}
                            {k.total === 0 && k.state === "active" && <span className="text-[10px] text-gray-600">미사용</span>}
                          </div>
                          <span className={`text-xs font-bold shrink-0 ${totalColor}`}>{k.total}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          )}

          {activeTab === "extra" && (
            <>
              <p className="text-[10px] text-gray-500">기획 대안 · 비디오 대안 · 팩트체크</p>
              {extraConfigs.map((config) => (
                <KeySection
                  key={config.id}
                  config={config}
                  serverStatus={serverKeyStatus?.[config.statusKey] ?? null}
                  savedKeys={savedKeys[config.id] || []}
                  inputValue={inputValues[config.id] || ""}
                  isVisible={visibleKeys[config.id] || false}
                  envMaskedKeys={serverMaskedKeys[config.statusKey] || []}
                  onInputChange={(v) => onInputChange(config.id, v)}
                  onAdd={() => onAddKey(config.id)}
                  onRemove={(idx) => onRemoveKey(config.id, idx)}
                  onToggleVisible={() => onToggleVisible(config.id)}
                />
              ))}
            </>
          )}

          {/* ════════ 채널 관리 탭 ════════ */}
          {activeTab === "channels" && (
            <>
              <p className="text-[10px] text-gray-500">
                채널별 언어 · 플랫폼 · 업로드 설정 관리. 채널 프리셋은 서버 <code className="text-gray-400">channel_config.py</code>에서 정의됩니다.
              </p>

              {/* 채널 추가 버튼 */}
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="새 채널 이름 (영문, 예: fushigi)"
                  className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-teal-500/50"
                  onKeyDown={async (e) => {
                    if (e.key !== "Enter") return;
                    const name = (e.target as HTMLInputElement).value.trim().toLowerCase();
                    if (!name || channels[name]) return;
                    try {
                      const res = await fetch(`${API_BASE}/api/channels/${encodeURIComponent(name)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ language: "en", platforms: ["youtube"], tts_speed: 0.9, caption_size: 44, caption_y: 28, visual_style: "", tone: "" }) });
                      if (res.ok) { fetchChannels(); (e.target as HTMLInputElement).value = ""; }
                    } catch {}
                  }}
                />
                <span className="text-[10px] text-gray-600">Enter로 추가</span>
              </div>

              {channelsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="w-5 h-5 border-2 border-teal-400/30 border-t-teal-400 rounded-full animate-spin" />
                  <span className="ml-2 text-xs text-gray-500">채널 로딩 중...</span>
                </div>
              ) : Object.keys(channels).length === 0 ? (
                <div className="text-center py-8">
                  <Tv className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                  <p className="text-sm text-gray-500">등록된 채널이 없습니다</p>
                  <p className="text-[10px] text-gray-600 mt-1">서버가 실행 중인지 확인하세요</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {Object.entries(channels).map(([name, ch]) => {
                    const isExpanded = expandedChannel === name;
                    const saveStatus = channelSaveStatus[name];
                    const langLabel = LANGUAGES.find((l) => l.code === ch.language)?.label || ch.language;
                    return (
                      <div key={name} className="rounded-2xl bg-white/[0.03] border border-white/5 overflow-hidden">
                        {/* 채널 헤더 (접기/펼치기) */}
                        <button
                          onClick={() => setExpandedChannel(isExpanded ? null : name)}
                          className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.02] transition-colors"
                        >
                          <div className="w-8 h-8 rounded-full bg-teal-500/20 flex items-center justify-center shrink-0">
                            <Tv className="w-4 h-4 text-teal-400" />
                          </div>
                          <div className="flex-1 text-left">
                            <span className="text-sm font-medium text-white">{name}</span>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-400">{langLabel}</span>
                              {(ch.platforms || []).map((p) => {
                                const connected = !!ch.upload_accounts?.[p];
                                return (
                                  <span key={p} className={`text-[10px] px-1.5 py-0.5 rounded flex items-center gap-1 ${connected ? "bg-green-500/15 text-green-400" : "bg-purple-500/15 text-purple-400"}`}>
                                    <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-green-500" : "bg-gray-500"}`} />
                                    {p}
                                  </span>
                                );
                              })}
                              {saveStatus === "saved" && <span className="text-[10px] text-green-400">저장됨</span>}
                              {saveStatus === "error" && <span className="text-[10px] text-red-400">오류</span>}
                            </div>
                          </div>
                          {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
                        </button>

                        {/* 채널 상세 설정 (펼쳐진 상태) */}
                        {isExpanded && (
                          <div className="px-4 pb-4 space-y-3 border-t border-white/5 pt-3">
                            {/* 언어 선택 */}
                            <div className="flex items-center gap-3">
                              <Globe className="w-4 h-4 text-blue-400 shrink-0" />
                              <div className="flex-1">
                                <label className="text-[10px] text-gray-500 block mb-1">기본 언어</label>
                                <select
                                  value={ch.language || "ko"}
                                  onChange={(e) => updateChannelField(name, "language", e.target.value)}
                                  className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500/50 appearance-none cursor-pointer"
                                >
                                  {LANGUAGES.map((l) => (
                                    <option key={l.code} value={l.code} className="bg-gray-900">{l.label} ({l.code})</option>
                                  ))}
                                </select>
                              </div>
                            </div>

                            {/* 플랫폼 선택 (멀티 토글) */}
                            <div>
                              <label className="text-[10px] text-gray-500 block mb-1.5">업로드 플랫폼</label>
                              <div className="flex gap-2">
                                {[
                                  { id: "youtube", label: "YouTube Shorts", icon: Youtube, color: "red" },
                                  { id: "tiktok", label: "TikTok", icon: Music, color: "pink" },
                                  { id: "instagram", label: "Instagram Reels", icon: Instagram, color: "orange" },
                                ].map(({ id, label, icon: Icon, color }) => {
                                  const active = (ch.platforms || []).includes(id);
                                  return (
                                    <button
                                      key={id}
                                      onClick={() => togglePlatform(name, id)}
                                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                                        active
                                          ? ({ red: "bg-red-500/20 text-red-400 border border-red-500/30", pink: "bg-pink-500/20 text-pink-400 border border-pink-500/30", orange: "bg-orange-500/20 text-orange-400 border border-orange-500/30" }[color] || "bg-white/15 text-white border border-white/20")
                                          : "bg-white/5 text-gray-500 border border-white/5 hover:bg-white/10"
                                      }`}
                                    >
                                      <Icon className="w-3.5 h-3.5" />
                                      {label}
                                    </button>
                                  );
                                })}
                              </div>
                            </div>

                            {/* 업로드 계정 연결 */}
                            <div>
                              <label className="text-[10px] text-gray-500 block mb-1.5">플랫폼 계정 연결</label>
                              <div className="space-y-1.5">
                                {(ch.platforms || []).map((platform) => {
                                  const accountId = ch.upload_accounts?.[platform];
                                  return (
                                    <div key={platform} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.02] border border-white/5">
                                      <span className="text-xs text-gray-400 w-20 shrink-0 capitalize">{platform}</span>
                                      <input
                                        type="text"
                                        value={accountId || ""}
                                        onChange={(e) => {
                                          const accounts = { ...(ch.upload_accounts || {}) };
                                          accounts[platform] = e.target.value || null;
                                          updateChannelField(name, "upload_accounts", accounts);
                                        }}
                                        placeholder={platform === "youtube" ? "채널 ID (UC...)" : platform === "tiktok" ? "Open ID" : "IG User ID"}
                                        className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1 text-[10px] text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-teal-500/50 font-mono"
                                      />
                                      <div className={`w-2 h-2 rounded-full ${accountId ? "bg-green-500" : "bg-gray-600"}`} />
                                      {platform === "youtube" && !accountId && (
                                        <button
                                          type="button"
                                          onClick={async () => {
                                            try {
                                              const res = await fetch(`${API_BASE}/api/youtube/auth`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({channel: name}) });
                                              const data = await res.json();
                                              if (data.auth_url) window.open(data.auth_url, "_blank", "width=500,height=600");
                                              else alert(data.error || "인증 URL 생성 실패");
                                            } catch { alert("서버 연결 실패"); }
                                          }}
                                          className="px-2 py-0.5 text-[9px] bg-red-500/20 text-red-300 rounded hover:bg-red-500/30 transition-colors whitespace-nowrap"
                                        >
                                          연동
                                        </button>
                                      )}
                                    </div>
                                  );
                                })}
                                {(ch.platforms || []).length === 0 && (
                                  <p className="text-[10px] text-gray-600 italic">플랫폼을 먼저 선택하세요</p>
                                )}
                              </div>
                            </div>

                            {/* TTS / 자막 설정 */}
                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <label className="text-[10px] text-gray-500 block mb-1">TTS 속도</label>
                                <input
                                  type="range"
                                  min={0.5}
                                  max={1.5}
                                  step={0.05}
                                  value={ch.tts_speed || 0.9}
                                  onChange={(e) => updateChannelField(name, "tts_speed", parseFloat(e.target.value))}
                                  className="w-full accent-teal-500"
                                />
                                <span className="text-[10px] text-gray-500">{(ch.tts_speed || 0.9).toFixed(2)}x</span>
                              </div>
                              <div>
                                <label className="text-[10px] text-gray-500 block mb-1">자막 크기</label>
                                <input
                                  type="range"
                                  min={32}
                                  max={64}
                                  step={2}
                                  value={ch.caption_size || 48}
                                  onChange={(e) => updateChannelField(name, "caption_size", parseInt(e.target.value))}
                                  className="w-full accent-teal-500"
                                />
                                <span className="text-[10px] text-gray-500">{ch.caption_size || 48}px</span>
                              </div>
                            </div>

                            {/* 비주얼 스타일 / 톤 */}
                            <div>
                              <label className="text-[10px] text-gray-500 block mb-1">비주얼 스타일</label>
                              <input
                                type="text"
                                value={ch.visual_style || ""}
                                onChange={(e) => updateChannelField(name, "visual_style", e.target.value)}
                                placeholder="cinematic dark, dramatic lighting..."
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500/50"
                              />
                            </div>
                            <div>
                              <label className="text-[10px] text-gray-500 block mb-1">톤 / 분위기</label>
                              <input
                                type="text"
                                value={ch.tone || ""}
                                onChange={(e) => updateChannelField(name, "tone", e.target.value)}
                                placeholder="궁금증 자극, 충격적 팩트..."
                                className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500/50"
                              />
                            </div>

                            {/* 이 채널의 플랫폼 연동 상태 */}
                            {(ch.platforms || []).length > 0 && (
                              <div className="mt-1">
                                <label className="text-[10px] text-gray-500 block mb-1.5">연동 상태</label>
                                <PlatformStatusPanel filterPlatforms={ch.platforms} />
                              </div>
                            )}

                            {/* 저장 안내 */}
                            <p className="text-[10px] text-gray-600 italic">
                              채널 설정 변경은 다음 생성 시 자동 적용됩니다. 영구 변경은 서버의 <code className="text-gray-400">channel_config.py</code>를 수정하세요.
                            </p>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>

        {/* 모달 푸터 */}
        <div className="px-6 py-4 border-t border-white/10 flex items-center justify-between">
          <p className="text-xs text-gray-600">
            {activeTab === "channels"
              ? `${Object.keys(channels).length}개 채널 등록됨`
              : `서버 키 ${totalServerKeys}개 | 브라우저 키 ${totalSavedKeys}개`}
          </p>
          <button
            onClick={onClose}
            className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-xl transition-colors"
          >
            완료
          </button>
        </div>
      </motion.div>
    </>
  );
}


/* ─── 플랫폼 연동 상태 패널 ─── */
function PlatformStatusPanel({ filterPlatforms }: { filterPlatforms?: string[] }) {
  const [ytStatus, setYtStatus] = useState<{ connected: boolean; channels?: { id: string; title: string }[] } | null>(null);
  const [ttStatus, setTtStatus] = useState<{ connected: boolean } | null>(null);
  const [igStatus, setIgStatus] = useState<{ connected: boolean } | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [yt, tt, ig] = await Promise.all([
          fetch(`${API_BASE}/api/youtube/status`).then((r) => r.ok ? r.json() : null).catch(() => null),
          fetch(`${API_BASE}/api/tiktok/status`).then((r) => r.ok ? r.json() : null).catch(() => null),
          fetch(`${API_BASE}/api/instagram/status`).then((r) => r.ok ? r.json() : null).catch(() => null),
        ]);
        if (yt) setYtStatus(yt);
        if (tt) setTtStatus(tt);
        if (ig) setIgStatus(ig);
      } catch { /* ignore */ }
    })();
  }, []);

  const allPlatforms = [
    { id: "youtube", label: "YouTube Shorts", icon: Youtube, status: ytStatus, color: "red" },
    { id: "tiktok", label: "TikTok", icon: Music, status: ttStatus, color: "pink" },
    { id: "instagram", label: "Instagram Reels", icon: Instagram, status: igStatus, color: "orange" },
  ];

  const platforms = filterPlatforms ? allPlatforms.filter(p => filterPlatforms.includes(p.id)) : allPlatforms;

  return (
    <div className="space-y-1.5">
      {platforms.map(({ id, label, icon: Icon, status, color }) => (
        <div key={id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/[0.02] border border-white/5">
          <Icon className={`w-4 h-4 ${{ red: "text-red-400", pink: "text-pink-400", orange: "text-orange-400" }[color] || "text-gray-400"}`} />
          <span className="text-xs text-gray-300 flex-1">{label}</span>
          <div className={`w-2 h-2 rounded-full ${status?.connected ? "bg-green-500" : "bg-gray-600"}`} />
          <span className="text-[10px] text-gray-500">
            {status === null ? "확인 중..." : status?.connected ? "연결됨" : "미연결"}
          </span>
        </div>
      ))}
    </div>
  );
}


/* ─── 키 섹션 컴포넌트 ─── */
function KeySection({
  config,
  serverStatus,
  savedKeys,
  inputValue,
  isVisible,
  serverKeyCount,
  envMaskedKeys = [],
  onInputChange,
  onAdd,
  onRemove,
  onToggleVisible,
}: {
  config: KeyConfig;
  serverStatus: boolean | null;
  savedKeys: string[];
  inputValue: string;
  isVisible: boolean;
  serverKeyCount?: number;
  envMaskedKeys?: string[];
  onInputChange: (v: string) => void;
  onAdd: () => void;
  onRemove: (idx: number) => void;
  onToggleVisible: () => void;
}) {
  const maskKey = (key: string) => {
    if (key.length <= 8) return "****";
    return key.slice(0, 4) + "..." + key.slice(-4);
  };

  const totalKeys = envMaskedKeys.length + savedKeys.length;

  return (
    <div className="mb-4 p-4 rounded-2xl bg-white/[0.03] border border-white/5">
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white">{config.label}</span>
            {config.required && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400 font-medium">필수</span>
            )}
            {config.multiKey && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400 font-medium">멀티키</span>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-0.5">{config.description}</p>
        </div>
        {/* 상태 표시 */}
        <div className="flex items-center gap-1.5 shrink-0 ml-3">
          <div className={`w-2 h-2 rounded-full ${totalKeys > 0 ? "bg-green-500" : serverStatus === false ? "bg-gray-600" : "bg-gray-700 animate-pulse"}`} />
          <span className="text-[10px] text-gray-500">
            {totalKeys > 0
              ? `${totalKeys}키 등록됨`
              : serverStatus === false ? "미설정" : "확인 중"}
          </span>
        </div>
      </div>

      {/* .env 키 목록 (서버에서 마스킹된 키) */}
      {envMaskedKeys.length > 0 && (
        <div className="space-y-1 mb-2">
          {envMaskedKeys.map((masked, idx) => (
            <div key={`env-${idx}`} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-green-500/10 border border-green-500/20">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0" />
              <span className="text-xs text-green-300 font-mono flex-1">{masked}</span>
              <span className="text-[10px] text-green-500/60">.env</span>
            </div>
          ))}
        </div>
      )}

      {/* 브라우저 저장 키 목록 */}
      {savedKeys.length > 0 && (
        <div className="space-y-1 mb-2">
          {savedKeys.map((key, idx) => (
            <div key={key} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <div className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
              <span className="text-xs text-blue-300 font-mono flex-1">
                {isVisible ? key : maskKey(key)}
              </span>
              <span className="text-[10px] text-blue-500/60">브라우저</span>
              <button onClick={onToggleVisible} aria-label={isVisible ? "API 키 숨기기" : "API 키 보기"} className="text-gray-500 hover:text-gray-300 transition-colors">
                {isVisible ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
              </button>
              <button onClick={() => onRemove(idx)} aria-label="API 키 삭제" className="text-gray-500 hover:text-red-400 transition-colors">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 키 입력 */}
      <div className="flex items-center gap-2">
        <input
          type={isVisible ? "text" : "password"}
          value={inputValue}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onAdd()}
          placeholder={`${config.envName} 입력...`}
          aria-label={`${config.label} 키 입력`}
          className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-indigo-500/50 font-mono"
        />
        <button
          onClick={onAdd}
          disabled={!inputValue.trim()}
          className="w-8 h-8 rounded-lg bg-white/5 hover:bg-white/10 disabled:opacity-30 flex items-center justify-center text-gray-400 hover:text-white transition-all"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {config.multiKey && savedKeys.length > 0 && (
        <p className="text-[10px] text-gray-600 mt-1.5">
          등록된 {savedKeys.length}개의 키 중 랜덤으로 선택되어 사용됩니다 (무료 티어 로테이션)
        </p>
      )}
    </div>
  );
}
