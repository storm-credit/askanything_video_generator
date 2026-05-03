"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { motion } from "framer-motion";
import { X, Plus, Trash2, Eye, EyeOff, BarChart3, Key, Puzzle, Tv, Globe, ChevronDown, ChevronUp, Youtube, Music, Instagram, Wallet, UploadCloud, GripVertical, CalendarClock, Play, RefreshCw } from "lucide-react";
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

interface BillingSettings {
  current_krw: number;
  total_krw: number;
  threshold_krw: number;
  cron_enabled: boolean;
  cron_minute: number;
  updated_at?: string | null;
}

interface BillingOverviewChannelModel {
  key: string;
  label: string;
  count: number;
  usd: number;
  krw: number;
  unit_krw: number;
}

interface BillingOverviewChannel {
  success: number;
  failed: number;
  total_usd: number;
  total_krw: number;
  video_count: number;
  video_usd: number;
  video_krw: number;
  video_models: BillingOverviewChannelModel[];
}

interface BillingOverview {
  date: string;
  exchange_rate: number;
  total_usd: number;
  total_krw: number;
  channels: Record<string, BillingOverviewChannel>;
}

interface VertexSaAccount {
  id: string;
  filename: string;
  source: "managed" | "root";
  managed: boolean;
  enabled: boolean;
  project_id: string;
  client_email: string;
  fingerprint: string;
  is_next?: boolean;
  last_used?: boolean;
  blocked?: boolean;
  blocked_remaining_sec?: number;
}

interface VertexSaSummary {
  backend: string;
  sa_only: boolean;
  enabled_count: number;
  next_account: VertexSaAccount | null;
}

interface SchedulerJob {
  name: string;
  type: string;
  schedule: string;
  next_run: string;
  last_run?: string | null;
}

interface SchedulerRunResult {
  topic?: string;
  topic_group?: string;
  source_topic?: string;
  channel?: string;
  status?: string;
  error?: string | null;
  publish_at?: string | null;
  youtube_url?: string | null;
  format_type?: string | null;
}

interface SchedulerChannelSummary {
  target?: Record<string, number>;
  scheduled?: Record<string, number>;
  completed?: Record<string, number>;
  rollout_holdback?: Record<string, number>;
  rollout_pending?: Record<string, number>;
  final_expected?: Record<string, number>;
  publish_on_date?: Record<string, number>;
  carryover_next_days?: Record<string, number>;
}

interface SchedulerRolloutItem {
  id?: number;
  topic_group?: string;
  lead_channel?: string;
  holdback_channels?: string[];
  holdback_payload?: Record<string, SchedulerHoldbackPayload> | null;
  source_topics?: Record<string, string>;
  status?: string;
  expand_after?: string | null;
  lead_publish_at?: string | null;
  lead_video_url?: string | null;
  format_type?: string | null;
  metric_views?: number | null;
  threshold_views?: number | null;
  last_error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface SchedulerHoldbackPayload {
  title?: string;
  source_topic?: string;
  _llm_topic_override?: string;
  format_type?: string;
  [key: string]: unknown;
}

interface SchedulerRolloutOverview {
  enabled?: boolean;
  lead_topics?: number;
  holdback_total?: number;
  pending_topics?: number;
  pending_channels?: number;
  items?: SchedulerRolloutItem[];
}

interface SchedulerRunStatus {
  running: boolean;
  current_date: string | null;
  total: number;
  completed: number;
  failed: number;
  current_task: string | null;
  results: SchedulerRunResult[];
  started_at: string | null;
  finished_at: string | null;
  stale_recovered?: boolean;
  message?: string;
  channel_summary?: SchedulerChannelSummary;
  publish_dates?: Record<string, Record<string, number>>;
  rollout_overview?: SchedulerRolloutOverview;
}

interface SchedulerPreviewStatus {
  file: string | null;
  date: string | null;
  total: number;
  channel_summary: SchedulerChannelSummary;
  publish_dates: Record<string, Record<string, number>>;
  rollout_overview?: SchedulerRolloutOverview | null;
}

interface SchedulerRolloutQueueSummary {
  counts?: Record<string, number>;
  due_now?: number;
  pending?: number;
  processing?: number;
}

interface SchedulerRolloutQueueStatus {
  queue?: SchedulerRolloutQueueSummary;
  items: SchedulerRolloutItem[];
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
  onRefreshServerKeys?: () => Promise<void> | void;
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
  onRefreshServerKeys,
}: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<"core" | "extra" | "vertex" | "billing" | "cron" | "channels">("core");

  // ── 채널 관리 상태 ──
  const [channels, setChannels] = useState<Record<string, ChannelConfig>>({});
  const [channelsLoading, setChannelsLoading] = useState(false);
  const [expandedChannel, setExpandedChannel] = useState<string | null>(null);
  const [channelSaveStatus, setChannelSaveStatus] = useState<Record<string, "saved" | "saving" | "error" | null>>({});
  const [ytConnectedChannels, setYtConnectedChannels] = useState<string[]>([]);
  const [billingSettings, setBillingSettings] = useState<BillingSettings>({
    current_krw: 0,
    total_krw: 0,
    threshold_krw: 400000,
    cron_enabled: true,
    cron_minute: 5,
  });
  const [billingLoading, setBillingLoading] = useState(false);
  const [billingStatus, setBillingStatus] = useState<string>("");
  const [billingOverview, setBillingOverview] = useState<BillingOverview | null>(null);
  const [vertexAccounts, setVertexAccounts] = useState<VertexSaAccount[]>([]);
  const [vertexLoading, setVertexLoading] = useState(false);
  const [vertexStatus, setVertexStatus] = useState("");
  const [vertexSummary, setVertexSummary] = useState<VertexSaSummary>({
    backend: "vertex_ai",
    sa_only: true,
    enabled_count: 0,
    next_account: null,
  });
  const [vertexTestingId, setVertexTestingId] = useState<string | null>(null);
  const [schedulerJobs, setSchedulerJobs] = useState<SchedulerJob[]>([]);
  const [schedulerStatus, setSchedulerStatus] = useState("");
  const [schedulerLoading, setSchedulerLoading] = useState(false);
  const [schedulerRunError, setSchedulerRunError] = useState("");
  const [schedulerRunStatus, setSchedulerRunStatus] = useState<SchedulerRunStatus>({
    running: false,
    current_date: null,
    total: 0,
    completed: 0,
    failed: 0,
    current_task: null,
    results: [],
    started_at: null,
    finished_at: null,
  });
  const [schedulerPreview, setSchedulerPreview] = useState<SchedulerPreviewStatus | null>(null);
  const [schedulerRolloutQueue, setSchedulerRolloutQueue] = useState<SchedulerRolloutQueueStatus | null>(null);
  const [schedulerRolloutError, setSchedulerRolloutError] = useState("");
  const [schedulerRolloutRunning, setSchedulerRolloutRunning] = useState(false);

  // YouTube 연동 상태 로드
  useEffect(() => {
    fetch(`${API_BASE}/api/youtube/status`).then(r => r.json()).then(data => {
      if (data.channels) setYtConnectedChannels(data.channels.filter((c: {connected: boolean}) => c.connected).map((c: {id: string}) => c.id));
    }).catch(() => {});
  }, []);

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

  const fetchBillingSettings = useCallback(async () => {
    setBillingLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/settings/billing`);
      if (res.ok) {
        const data = await res.json();
        setBillingSettings((prev) => ({ ...prev, ...(data.settings || {}) }));
        setBillingOverview(data.overview || null);
      }
    } catch { /* server offline */ }
    setBillingLoading(false);
  }, []);

  const fetchVertexAccounts = useCallback(async () => {
    setVertexLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/settings/vertex-sa`);
      if (res.ok) {
        const data = await res.json();
        setVertexAccounts(data.accounts || []);
        setVertexSummary({
          backend: data.backend || "vertex_ai",
          sa_only: !!data.sa_only,
          enabled_count: Number(data.enabled_count || 0),
          next_account: data.next_account || null,
        });
      }
    } catch { /* server offline */ }
    setVertexLoading(false);
  }, []);

  const saveVertexAccounts = useCallback(async (accounts: VertexSaAccount[], message = "저장됨") => {
    setVertexStatus("저장 중...");
    try {
      const res = await fetch(`${API_BASE}/api/settings/vertex-sa`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accounts }),
      });
      const data = await res.json();
      if (res.ok && data.accounts) {
        setVertexAccounts(data.accounts);
        await fetchVertexAccounts();
        setVertexStatus(message);
      } else {
        setVertexStatus(data.detail || "저장 실패");
      }
    } catch {
      setVertexStatus("저장 실패: 서버 연결을 확인하세요");
    }
  }, [fetchVertexAccounts]);

  const fetchSchedulerStatus = useCallback(async () => {
    setSchedulerLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/scheduler/cron`);
      const data = await res.json();
      if (res.ok && data.jobs) {
        setSchedulerJobs(data.jobs);
        setSchedulerStatus(data.running ? "크론 실행 중" : "크론 중지됨");
      } else {
        setSchedulerStatus(data.message || "크론 상태 확인 실패");
      }
    } catch {
      setSchedulerStatus("크론 상태 확인 실패: 서버 연결을 확인하세요");
    }
    setSchedulerLoading(false);
  }, []);

  const fetchSchedulerRolloutQueue = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/scheduler/rollout-expansions?limit=8`);
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.success !== false) {
        setSchedulerRolloutQueue({
          queue: data.queue || {},
          items: Array.isArray(data.items) ? data.items : [],
        });
        setSchedulerRolloutError("");
      } else {
        setSchedulerRolloutError(data.message || data.detail || "롤아웃 큐 확인 실패");
      }
    } catch {
      setSchedulerRolloutError("롤아웃 큐 확인 실패: 서버 연결을 확인하세요");
    }
  }, []);

  const fetchSchedulerRunStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/scheduler/status`);
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setSchedulerRunStatus({
          running: !!data.running,
          current_date: data.current_date || null,
          total: Number(data.total || 0),
          completed: Number(data.completed || 0),
          failed: Number(data.failed || 0),
          current_task: data.current_task || null,
          results: Array.isArray(data.results) ? data.results : [],
          started_at: data.started_at || null,
          finished_at: data.finished_at || null,
          stale_recovered: !!data.stale_recovered,
          message: data.message || "",
          channel_summary: data.channel_summary || {},
          publish_dates: data.publish_dates || {},
          rollout_overview: data.rollout_overview || undefined,
        });
        setSchedulerRunError("");
      } else {
        setSchedulerRunError(data.message || data.detail || "배치 상태 확인 실패");
      }
    } catch {
      setSchedulerRunError("배치 상태 확인 실패: 서버 연결을 확인하세요");
    }
    await fetchSchedulerRolloutQueue();
  }, [fetchSchedulerRolloutQueue]);

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
    if (activeTab === "billing") fetchBillingSettings();
    if (activeTab === "vertex") fetchVertexAccounts();
    if (activeTab === "cron") {
      fetchSchedulerStatus();
      fetchSchedulerRunStatus();
    }
  }, [activeTab, fetchChannels, fetchBillingSettings, fetchVertexAccounts, fetchSchedulerStatus, fetchSchedulerRunStatus]);

  useEffect(() => {
    if (activeTab !== "cron" || !schedulerRunStatus.running) return;
    const timer = setInterval(() => {
      fetchSchedulerRunStatus();
    }, 5000);
    return () => clearInterval(timer);
  }, [activeTab, schedulerRunStatus.running, fetchSchedulerRunStatus]);

  const coreConfigs = KEY_CONFIGS.filter((c) => c.group === "core");
  const extraConfigs = KEY_CONFIGS.filter((c) => c.group === "extra");

  // ── 채널 설정 서버 자동저장 (디바운스 500ms) ──
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const saveChannelToServer = useCallback((name: string, data: object) => {
    if (saveTimers.current[name]) clearTimeout(saveTimers.current[name]);
    saveTimers.current[name] = setTimeout(async () => {
      setChannelSaveStatus((prev) => ({ ...prev, [name]: "saving" }));
      try {
        const res = await fetch(`${API_BASE}/api/channels/${encodeURIComponent(name)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        });
        setChannelSaveStatus((prev) => ({ ...prev, [name]: res.ok ? "saved" : "error" }));
      } catch {
        setChannelSaveStatus((prev) => ({ ...prev, [name]: "error" }));
      }
    }, 500);
  }, []);

  // ── 채널 필드 수정 (로컬 + 서버 자동저장) ──
  const updateChannelField = (name: string, field: string, value: unknown) => {
    setChannels((prev) => {
      const updated = { ...prev, [name]: { ...prev[name], [field]: value } };
      saveChannelToServer(name, updated[name]);
      return updated;
    });
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
          <div className="flex gap-1 flex-wrap">
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
            <button
              onClick={() => setActiveTab("vertex")}
              className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-t-xl transition-colors ${
                activeTab === "vertex"
                  ? "bg-white/[0.06] text-cyan-400 border-b-2 border-cyan-400"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              <UploadCloud className="w-3.5 h-3.5" />
              Vertex SA
            </button>
            <button
              onClick={() => setActiveTab("billing")}
              className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-t-xl transition-colors ${
                activeTab === "billing"
                  ? "bg-white/[0.06] text-emerald-400 border-b-2 border-emerald-400"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              <Wallet className="w-3.5 h-3.5" />
              비용 알림
            </button>
            <button
              onClick={() => setActiveTab("cron")}
              className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-t-xl transition-colors ${
                activeTab === "cron"
                  ? "bg-white/[0.06] text-sky-400 border-b-2 border-sky-400"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              <CalendarClock className="w-3.5 h-3.5" />
              크론
            </button>
          </div>
        </div>

        {/* 모달 바디 — 탭 콘텐츠 */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 custom-scrollbar">
          {activeTab === "core" && (
            <>
              <p className="text-[10px] text-gray-500">Google + 활성 TTS = 최소 구성. OpenAI는 선택 기능이 켜진 경우에만 사용</p>
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
                  onRefreshServerKeys={onRefreshServerKeys}
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
                  onRefreshServerKeys={onRefreshServerKeys}
                />
              ))}
            </>
          )}

          {activeTab === "billing" && (
            <BillingSettingsPanel
              settings={billingSettings}
              overview={billingOverview}
              loading={billingLoading}
              status={billingStatus}
              onChange={(next) => setBillingSettings((prev) => ({ ...prev, ...next }))}
              onSave={async () => {
                setBillingStatus("저장 중...");
                try {
                  const res = await fetch(`${API_BASE}/api/settings/billing`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(billingSettings),
                  });
                  const data = await res.json();
                  if (res.ok && data.settings) {
                    setBillingSettings((prev) => ({ ...prev, ...data.settings }));
                    setBillingStatus(data.settings.cron_enabled
                      ? "저장됨. 크론은 다음 매시간 체크부터 적용됩니다."
                      : "저장됨. 기준 초과 상태라 비용 알림 크론은 꺼졌습니다.");
                  } else {
                    setBillingStatus("저장 실패");
                  }
                } catch {
                  setBillingStatus("저장 실패: 서버 연결을 확인하세요");
                }
              }}
              onCheck={async () => {
                setBillingStatus("텔레그램 알림 조건 확인 중...");
                try {
                  await fetch(`${API_BASE}/api/settings/billing`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(billingSettings),
                  });
                  const res = await fetch(`${API_BASE}/api/settings/billing/check`, { method: "POST" });
                  const data = await res.json();
                  const result = data.result || {};
                  if (result.skipped) {
                    setBillingStatus(`확인 스킵: ${result.reason || "조건 없음"}`);
                  } else if (result.crossed) {
                    setBillingStatus(result.sent ? "기준 초과 알림 전송됨" : "기준 초과. 텔레그램 전송은 실패 또는 중복 처리됨");
                  } else {
                    setBillingStatus("아직 기준선 아래입니다.");
                  }
                } catch {
                  setBillingStatus("확인 실패: 서버 연결을 확인하세요");
                }
              }}
            />
          )}

          {activeTab === "vertex" && (
            <VertexSaPanel
              accounts={vertexAccounts}
              loading={vertexLoading}
              status={vertexStatus}
              summary={vertexSummary}
              testingId={vertexTestingId}
              onRefresh={fetchVertexAccounts}
              onUpload={async (files) => {
                if (!files.length) return;
                setVertexStatus("업로드 중...");
                for (const file of files) {
                  const form = new FormData();
                  form.append("file", file);
                  const res = await fetch(`${API_BASE}/api/settings/vertex-sa/upload`, {
                    method: "POST",
                    body: form,
                  });
                  if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    setVertexStatus(data.detail || `${file.name} 업로드 실패`);
                    return;
                  }
                }
                await fetchVertexAccounts();
                setVertexStatus("업로드됨. 다음 요청부터 순서대로 SA를 씁니다.");
              }}
              onTest={async (id) => {
                setVertexTestingId(id || "__next__");
                setVertexStatus("Vertex 연결 테스트 중...");
                try {
                  const res = await fetch(`${API_BASE}/api/settings/vertex-sa/test`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(id ? { item_id: id } : {}),
                  });
                  const data = await res.json();
                  if (res.ok && data.account) {
                    setVertexStatus(`${data.account.project_id} 연결 성공`);
                    await fetchVertexAccounts();
                  } else {
                    setVertexStatus(data.detail || "Vertex 연결 테스트 실패");
                  }
                } catch {
                  setVertexStatus("Vertex 연결 테스트 실패: 서버 연결을 확인하세요");
                } finally {
                  setVertexTestingId(null);
                }
              }}
              onReorder={(next) => {
                setVertexAccounts(next);
                saveVertexAccounts(next, "순서 저장됨. 위에서부터 한 번씩 씁니다.");
              }}
              onToggle={(id, enabled) => {
                const next = vertexAccounts.map((item) => item.id === id ? { ...item, enabled } : item);
                setVertexAccounts(next);
                saveVertexAccounts(next, enabled ? "SA 활성화됨" : "SA 비활성화됨");
              }}
              onDelete={async (id) => {
                if (!confirm("이 SA 파일을 삭제할까요? 업로드한 관리 SA만 삭제됩니다.")) return;
                setVertexStatus("삭제 중...");
                try {
                  const res = await fetch(`${API_BASE}/api/settings/vertex-sa/${encodeURIComponent(id)}`, { method: "DELETE" });
                  const data = await res.json();
                  if (res.ok && data.accounts) {
                    setVertexAccounts(data.accounts);
                    await fetchVertexAccounts();
                    setVertexStatus("삭제됨");
                  } else {
                    setVertexStatus(data.detail || "삭제 실패");
                  }
                } catch {
                  setVertexStatus("삭제 실패: 서버 연결을 확인하세요");
                }
              }}
            />
          )}

          {activeTab === "cron" && (
            <SchedulerPanel
              jobs={schedulerJobs}
              loading={schedulerLoading}
              status={schedulerStatus}
              runError={schedulerRunError}
              runStatus={schedulerRunStatus}
              preview={schedulerPreview}
              rolloutQueue={schedulerRolloutQueue}
              rolloutError={schedulerRolloutError}
              rolloutRunning={schedulerRolloutRunning}
              onRefresh={() => {
                fetchSchedulerStatus();
                fetchSchedulerRunStatus();
              }}
              onPreview={async () => {
                setSchedulerStatus("오늘 할 일 스케줄 계산 중...");
                try {
                  const res = await fetch(`${API_BASE}/api/scheduler/preview`);
                  const data = await res.json();
                  if (res.ok) {
                    const total = Number(data.total_videos || data.total || data.summary?.total_videos || data.schedule?.length || 0);
                    const holdback = Number(data.rollout_overview?.holdback_total || 0);
                    setSchedulerPreview({
                      file: data.file || null,
                      date: data.date || null,
                      total,
                      channel_summary: data.channel_summary || {},
                      publish_dates: data.publish_dates || {},
                      rollout_overview: data.rollout_overview || null,
                    });
                    setSchedulerStatus(
                      holdback > 0
                        ? `오늘 할 일 미리보기 완료: 즉시 ${total}개 · 보류 ${holdback}개 · 최종 ${total + holdback}개`
                        : `오늘 할 일 미리보기 완료: ${total}개`
                    );
                  } else {
                    setSchedulerPreview(null);
                    setSchedulerStatus(data.message || "미리보기 실패");
                  }
                } catch {
                  setSchedulerPreview(null);
                  setSchedulerStatus("미리보기 실패: 서버 연결을 확인하세요");
                }
              }}
              onRunToday={async () => {
                if (!confirm("오늘 할 일을 지금 자동 생성/예약 업로드로 실행할까요? 유료 API가 사용됩니다.")) return;
                setSchedulerStatus("오늘 할 일 자동 배포 시작 중...");
                try {
                  const res = await fetch(`${API_BASE}/api/scheduler/run?max_per_channel=3`, { method: "POST" });
                  const data = await res.json();
                  if (res.ok && data.success) {
                    setSchedulerStatus(data.message || "오늘 할 일 자동 배포 시작됨");
                    await fetchSchedulerRunStatus();
                  } else {
                    setSchedulerStatus(data.message || "자동 배포 시작 실패");
                  }
                } catch {
                  setSchedulerStatus("자동 배포 시작 실패: 서버 연결을 확인하세요");
                }
              }}
              onRunRolloutExpansion={async () => {
                if (!confirm("판정 가능한 롤아웃 보류분을 지금 실행할까요? 기준 통과 시 나머지 채널 영상 생성/예약 업로드로 유료 API가 사용됩니다.")) return;
                setSchedulerRolloutRunning(true);
                setSchedulerStatus("롤아웃 보류분 판정 실행 중...");
                try {
                  const res = await fetch(`${API_BASE}/api/scheduler/rollout-expansions/run?limit=6`, { method: "POST" });
                  const data = await res.json().catch(() => ({}));
                  if (res.ok && data.success) {
                    const processed = Number(data.processed || 0);
                    const results = Array.isArray(data.results) ? data.results : [];
                    const expanded = results.filter((item: { status?: string }) => item.status === "expanded").length;
                    const retry = results.filter((item: { status?: string }) => String(item.status || "").includes("retry")).length;
                    const deferred = results.filter((item: { status?: string }) => item.status === "deferred").length;
                    setSchedulerStatus(
                      processed > 0
                        ? `롤아웃 판정 완료: 처리 ${processed}건 · 확장 ${expanded}건 · 재시도대기 ${retry}건 · 보류 ${deferred}건`
                        : "롤아웃 판정 완료: 지금 처리할 후보 없음"
                    );
                    await fetchSchedulerRunStatus();
                  } else {
                    setSchedulerStatus(data.message || "롤아웃 판정 실행 실패");
                    await fetchSchedulerRunStatus();
                  }
                } catch {
                  setSchedulerStatus("롤아웃 판정 실행 실패: 서버 연결을 확인하세요");
                } finally {
                  setSchedulerRolloutRunning(false);
                }
              }}
            />
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
                                const hasAccount = !!ch.upload_accounts?.[p];
                                const isYtConnected = p === "youtube" && ytConnectedChannels.length > 0;
                                const connected = hasAccount || isYtConnected;
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
                                <YouTubeAccountRow channelName={name} accountId={ch.upload_accounts?.youtube} onUpdate={(id) => { const accounts = { ...(ch.upload_accounts || {}) }; accounts.youtube = id || null; updateChannelField(name, "upload_accounts", accounts); }} />
                                {(ch.platforms || []).filter(p => p !== "youtube").map((platform) => {
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
                                        placeholder={platform === "tiktok" ? "Open ID" : "IG User ID"}
                                        className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1 text-[10px] text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-teal-500/50 font-mono"
                                      />
                                      <div className={`w-2 h-2 rounded-full ${accountId ? "bg-green-500" : "bg-gray-600"}`} />
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

                            {/* 저장 상태 */}
                            {channelSaveStatus[name] === "saving" && <p className="text-[10px] text-yellow-400">저장 중...</p>}
                            {channelSaveStatus[name] === "saved" && <p className="text-[10px] text-green-400">자동 저장됨</p>}
                            {channelSaveStatus[name] === "error" && <p className="text-[10px] text-red-400">저장 실패</p>}
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
              : activeTab === "vertex"
                ? `Vertex SA ${vertexAccounts.filter((a) => a.enabled).length}/${vertexAccounts.length}개 사용`
              : activeTab === "cron"
                ? `${schedulerJobs.length}개 크론 잡`
              : activeTab === "billing"
                ? `청구 기준 ${billingSettings.threshold_krw.toLocaleString()}원`
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


/* ─── 크론 / 오늘 할 일 패널 ─── */
function SchedulerPanel({
  jobs,
  loading,
  status,
  runError,
  runStatus,
  preview,
  rolloutQueue,
  rolloutError,
  rolloutRunning,
  onRefresh,
  onPreview,
  onRunToday,
  onRunRolloutExpansion,
}: {
  jobs: SchedulerJob[];
  loading: boolean;
  status: string;
  runError: string;
  runStatus: SchedulerRunStatus;
  preview: SchedulerPreviewStatus | null;
  rolloutQueue: SchedulerRolloutQueueStatus | null;
  rolloutError: string;
  rolloutRunning: boolean;
  onRefresh: () => void;
  onPreview: () => void;
  onRunToday: () => void;
  onRunRolloutExpansion: () => void;
}) {
  const channelMeta: Record<string, { label: string; badge: string }> = {
    askanything: { label: "AskAnything", badge: "KO" },
    wonderdrop: { label: "WonderDrop", badge: "EN" },
    exploratodo: { label: "ExploraTodo", badge: "ES" },
    prismtale: { label: "Prism Tale", badge: "ES-US" },
  };
  const channelOrder = ["askanything", "wonderdrop", "exploratodo", "prismtale"];

  const formatRunTime = (value: string | null | undefined) => {
    if (!value) return "-";
    const dt = new Date(value);
    return Number.isNaN(dt.getTime()) ? value : dt.toLocaleString("ko-KR");
  };

  const hasBucketValues = (bucket?: Record<string, number>) =>
    Object.values(bucket || {}).some((value) => Number(value || 0) > 0);
  const getHoldbackPayload = (item: SchedulerRolloutItem): Record<string, SchedulerHoldbackPayload> =>
    item.holdback_payload && typeof item.holdback_payload === "object" && !Array.isArray(item.holdback_payload)
      ? item.holdback_payload
      : {};
  const getHoldbackChannels = (item: SchedulerRolloutItem) => {
    const payloadChannels = Object.keys(getHoldbackPayload(item));
    const explicitChannels = item.holdback_channels || [];
    return explicitChannels.length > 0 ? explicitChannels : payloadChannels;
  };
  const getSourceLabel = (payload: SchedulerHoldbackPayload) =>
    String(payload.source_topic || payload._llm_topic_override || payload.title || "").trim();
  const statusLabel: Record<string, string> = {
    pending: "판정대기",
    processing: "확장중",
    expanded: "확장완료",
    skipped: "스킵",
    skipped_retention: "완시율스킵",
    failed: "실패",
  };
  const statusClass = (value?: string | null) => {
    const statusValue = String(value || "").toLowerCase();
    if (["expanded", "success"].includes(statusValue)) return "bg-emerald-500/20 text-emerald-300";
    if (["failed", "skipped", "skipped_retention"].includes(statusValue)) return "bg-red-500/20 text-red-300";
    if (statusValue === "processing") return "bg-sky-500/20 text-sky-300";
    return "bg-amber-500/15 text-amber-300";
  };

  const recentResults = [...(runStatus.results || [])].slice(-3).reverse();
  const rolloutQueueItems = rolloutQueue?.items || [];
  const rolloutCounts = rolloutQueue?.queue?.counts || {};
  const rolloutDueNow = Number(rolloutQueue?.queue?.due_now || 0);
  const renderChannelSummary = (
    title: string,
    summary: SchedulerChannelSummary | undefined,
    rollout: SchedulerRolloutOverview | undefined | null,
    subtitle?: string,
  ) => {
    if (!summary) return null;
    const keys = new Set<string>();
    [
      summary.target,
      summary.scheduled,
      summary.completed,
      summary.rollout_holdback,
      summary.rollout_pending,
      summary.final_expected,
      summary.publish_on_date,
      summary.carryover_next_days,
    ].forEach((bucket) => {
      Object.keys(bucket || {}).forEach((key) => keys.add(key));
    });
    const channels = [...channelOrder.filter((channel) => keys.has(channel)), ...[...keys].filter((channel) => !channelOrder.includes(channel))];
    if (channels.length === 0) return null;

    const hasCompleted = hasBucketValues(summary.completed);
    const hasScheduled = hasBucketValues(summary.scheduled);
    const primaryLabel = hasCompleted ? "완료" : hasScheduled ? "예약됨" : "진행";
    const primaryBucket = hasCompleted ? summary.completed || {} : hasScheduled ? summary.scheduled || {} : {};
    const holdbackBucket = summary.rollout_pending || summary.rollout_holdback || {};
    const rolloutItems = rollout?.items || [];
    const holdbackTotal = Number(rollout?.pending_channels ?? rollout?.holdback_total ?? 0);

    return (
      <div className="rounded-xl border border-white/10 bg-black/20 p-3 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h4 className="text-xs font-semibold text-white">{title}</h4>
            {subtitle && <p className="text-[10px] text-gray-500 mt-0.5">{subtitle}</p>}
          </div>
          {holdbackTotal > 0 && (
            <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-300">
              보류 {holdbackTotal}개
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {channels.map((channel) => {
            const meta = channelMeta[channel] || { label: channel, badge: "--" };
            const primary = Number(primaryBucket[channel] || 0);
            const target = Number(summary.target?.[channel] || 0);
            const holdback = Number(holdbackBucket[channel] || 0);
            const finalExpected = Number(summary.final_expected?.[channel] || target || primary + holdback);
            const publishToday = Number(summary.publish_on_date?.[channel] || 0);
            const carryover = Number(summary.carryover_next_days?.[channel] || 0);

            return (
              <div key={channel} className="rounded-lg bg-white/[0.03] px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs text-white">{meta.label}</p>
                  <span className="rounded bg-white/10 px-1.5 py-0.5 text-[9px] text-gray-300">{meta.badge}</span>
                </div>
                <p className="mt-1 text-[11px] text-gray-400">
                  {primaryLabel} <span className="text-gray-200">{primary}</span>
                  {holdback > 0 && <> · 보류 <span className="text-amber-300">{holdback}</span></>}
                  {finalExpected > 0 && <> · 최종 <span className="text-emerald-300">{finalExpected}</span></>}
                </p>
                <p className="text-[10px] text-gray-500 mt-1">
                  오늘 공개 {publishToday}
                  {carryover > 0 && <> · 다음날 {carryover}</>}
                  {target > 0 && <> · Day 목표 {target}</>}
                </p>
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-gray-500">
          예약됨/완료는 실제 생성·예약된 수, 보류는 리드 채널 성과 확인 후 확장할 후보야.
        </p>

        {rolloutItems.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-[10px] text-gray-500">리드채널 실험</p>
            {rolloutItems.map((item, index) => {
              const holdbackChannels = getHoldbackChannels(item);
              const sourceEntries = Object.entries(item.source_topics || {});
              return (
                <div key={`${item.topic_group || "topic"}-${index}`} className="rounded-lg bg-white/[0.03] px-3 py-2 text-[10px] text-gray-300">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-gray-200 break-words">{item.topic_group || "-"}</p>
                    {item.status && (
                      <span className={`shrink-0 rounded-full px-2 py-0.5 ${statusClass(item.status)}`}>
                        {statusLabel[item.status] || item.status}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-gray-500">
                    리드 {item.lead_channel || "-"} · 보류 {holdbackChannels.join(", ") || "-"}
                    {item.expand_after ? ` · 판정 ${formatRunTime(item.expand_after)}` : ""}
                  </p>
                  {sourceEntries.length > 0 && (
                    <p className="mt-1 text-sky-300 break-words">
                      원본주제 {sourceEntries.map(([channel, source]) => `${channel}: ${source}`).join(" · ")}
                    </p>
                  )}
                  {item.last_error && <p className="mt-1 text-red-300 break-words">{item.last_error}</p>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      <p className="text-[10px] text-gray-500">
        자동 배포 크론 상태를 확인하고, 오늘 할 일을 필요할 때 바로 시작합니다.
      </p>

      <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white">오늘 할 일 트리거</h3>
            <p className="text-xs text-gray-500 mt-0.5">미리보기는 비용 없이 시간표만 계산합니다.</p>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            className="px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 text-xs rounded-lg transition-colors flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            새로고침
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onPreview}
            className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-200 text-xs font-medium rounded-lg transition-colors"
          >
            오늘 할 일 미리보기
          </button>
          <button
            type="button"
            onClick={onRunToday}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium rounded-lg transition-colors flex items-center justify-center gap-1.5"
          >
            <Play className="w-3.5 h-3.5" />
            오늘 할 일 실행
          </button>
        </div>

        <div className="rounded-xl border border-white/10 bg-black/20 p-3 space-y-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h4 className="text-xs font-semibold text-white">오늘 할 일 실행 상태</h4>
              <p className="text-[10px] text-gray-500 mt-0.5">
                {runStatus.current_date ? `${runStatus.current_date} 기준` : "최근 실행 기록 없음"}
              </p>
            </div>
            <span className={`text-[10px] px-2 py-1 rounded-full border ${
              runStatus.running
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                : "border-white/10 bg-white/5 text-gray-400"
            }`}>
              {runStatus.running ? "실행 중" : "대기"}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div className="rounded-lg bg-white/[0.03] px-3 py-2">
              <p className="text-gray-500 mb-1">총 작업</p>
              <p className="text-gray-200">{runStatus.total}</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] px-3 py-2">
              <p className="text-gray-500 mb-1">완료</p>
              <p className="text-emerald-300">{runStatus.completed}</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] px-3 py-2">
              <p className="text-gray-500 mb-1">실패</p>
              <p className="text-red-300">{runStatus.failed}</p>
            </div>
            <div className="rounded-lg bg-white/[0.03] px-3 py-2">
              <p className="text-gray-500 mb-1">시작 시각</p>
              <p className="text-gray-200">{runStatus.started_at ? formatRunTime(runStatus.started_at) : "-"}</p>
            </div>
          </div>

          {runStatus.current_task && (
            <div className="rounded-lg bg-sky-500/10 border border-sky-500/20 px-3 py-2 text-xs">
              <p className="text-sky-300">현재 작업</p>
              <p className="text-gray-200 mt-1 break-words">{runStatus.current_task}</p>
            </div>
          )}

          {runStatus.stale_recovered && (
            <p className="text-[10px] text-amber-300">
              이전 서버 세션에서 남은 상태를 복구해 보여주는 중이야. 새 실행을 시작하면 최신 상태로 덮어써져.
            </p>
          )}
          {runError && (
            <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[10px] text-red-300">
              {runError}
            </p>
          )}
          {!runStatus.current_task && runStatus.message && (
            <p className="text-[10px] text-gray-500">{runStatus.message}</p>
          )}

          {recentResults.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] text-gray-500">최근 결과</p>
              {recentResults.map((item, idx) => {
                const displayTopic = item.topic || item.topic_group || "-";
                const sourceTopic = item.source_topic && item.source_topic !== displayTopic ? item.source_topic : "";
                return (
                  <div key={`${item.channel || "ch"}-${displayTopic}-${idx}`} className="flex items-start justify-between gap-3 rounded-lg bg-white/[0.03] px-3 py-2 text-xs">
                    <div className="min-w-0">
                      <p className="text-gray-200 break-words">{item.channel || "-"} · {displayTopic}</p>
                      <p className="mt-1 text-[10px] text-gray-500">
                        {item.format_type ? `${item.format_type} · ` : ""}
                        {item.publish_at ? `예약 ${formatRunTime(item.publish_at)}` : "예약 시간 없음"}
                      </p>
                      {sourceTopic && <p className="mt-1 text-[10px] text-sky-300 break-words">원본주제: {sourceTopic}</p>}
                      {item.youtube_url && <p className="mt-1 text-[10px] text-gray-500 break-words">{item.youtube_url}</p>}
                      {item.error && <p className="text-red-300 mt-1 break-words">{item.error}</p>}
                    </div>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${statusClass(item.status)}`}>
                      {item.status || "-"}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {preview && renderChannelSummary(
          "오늘 할 일 미리보기",
          preview.channel_summary,
          preview.rollout_overview,
          preview.file ? `${preview.file}${preview.date ? ` · ${preview.date}` : ""}` : undefined,
        )}

        {renderChannelSummary(
          "최근 실행 채널별 요약",
          runStatus.channel_summary,
          runStatus.rollout_overview,
          runStatus.current_date ? `${runStatus.current_date} 기준` : undefined,
        )}

        {(rolloutQueueItems.length > 0 || rolloutError) && (
          <div className="rounded-xl border border-white/10 bg-black/20 p-3 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h4 className="text-xs font-semibold text-white">롤아웃 보류 큐</h4>
                <p className="text-[10px] text-gray-500 mt-0.5">
                  리드 채널 24시간 성과를 본 뒤 나머지 채널을 확장하는 대기열입니다.
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5">
                {rolloutDueNow > 0 && (
                  <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-1 text-[10px] text-sky-300">
                    지금 판정 {rolloutDueNow}개
                  </span>
                )}
                <button
                  type="button"
                  onClick={onRunRolloutExpansion}
                  disabled={rolloutRunning || rolloutQueueItems.length === 0}
                  className="rounded-lg border border-amber-400/20 bg-amber-500/10 px-2.5 py-1.5 text-[10px] font-medium text-amber-200 transition-colors hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {rolloutRunning ? "판정 실행 중..." : "보류분 판정 실행"}
                </button>
              </div>
            </div>

            {rolloutError && (
              <p className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-[10px] text-red-300">
                {rolloutError}
              </p>
            )}

            <div className="flex flex-wrap gap-1.5 text-[10px]">
              {[
                ["pending", "판정대기"],
                ["processing", "확장중"],
                ["expanded", "완료"],
                ["skipped", "스킵"],
                ["failed", "실패"],
              ].map(([key, label]) => (
                <span key={key} className="rounded-full bg-white/[0.04] px-2 py-1 text-gray-400">
                  {label} <span className="text-gray-200">{Number(rolloutCounts[key] || 0)}</span>
                </span>
              ))}
            </div>
            {rolloutDueNow === 0 && rolloutQueueItems.length > 0 && (
              <p className="text-[10px] text-gray-500">
                아직 판정 시간이 안 된 후보는 실행해도 업로드하지 않고 0건 처리로 끝납니다.
              </p>
            )}

            {rolloutQueueItems.length === 0 ? (
              <p className="text-[10px] text-gray-500">현재 보류 큐에 남은 항목이 없습니다.</p>
            ) : (
              <div className="space-y-1.5">
                {rolloutQueueItems.map((item, index) => {
                  const payload = getHoldbackPayload(item);
                  const holdbackChannels = getHoldbackChannels(item);
                  const sourceEntries = Object.entries(payload)
                    .map(([channel, value]) => [channel, getSourceLabel(value)] as const)
                    .filter(([, value]) => value);
                  return (
                    <div key={`${item.id || item.topic_group || "rollout"}-${index}`} className="rounded-lg bg-white/[0.03] px-3 py-2 text-[10px] text-gray-300">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-gray-200 break-words">{item.topic_group || "-"}</p>
                        <span className={`shrink-0 rounded-full px-2 py-0.5 ${statusClass(item.status)}`}>
                          {statusLabel[item.status || ""] || item.status || "대기"}
                        </span>
                      </div>
                      <p className="mt-1 text-gray-500">
                        리드 {item.lead_channel || "-"} · 보류 {holdbackChannels.join(", ") || "-"}
                        {item.format_type ? ` · ${item.format_type}` : ""}
                      </p>
                      <p className="mt-1 text-gray-500">
                        리드 공개 {formatRunTime(item.lead_publish_at)} · 확장 판정 {formatRunTime(item.expand_after)}
                      </p>
                      {(item.metric_views != null || item.threshold_views != null) && (
                        <p className="mt-1 text-gray-500">
                          조회 {item.metric_views ?? "-"} / 기준 {item.threshold_views ?? "-"}
                        </p>
                      )}
                      {sourceEntries.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {sourceEntries.slice(0, 4).map(([channel, source]) => (
                            <p key={channel} className="text-sky-300 break-words">
                              {channel}: {source}
                            </p>
                          ))}
                        </div>
                      )}
                      {item.lead_video_url && <p className="mt-2 text-gray-500 break-words">{item.lead_video_url}</p>}
                      {item.last_error && <p className="mt-2 text-red-300 break-words">{item.last_error}</p>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        <div>
          <h4 className="text-xs font-semibold text-gray-400 mb-2">등록된 크론</h4>
          {loading ? (
            <div className="flex items-center gap-2 text-xs text-gray-500 py-4">
              <div className="w-4 h-4 border-2 border-sky-400/30 border-t-sky-400 rounded-full animate-spin" />
              크론 상태 불러오는 중...
            </div>
          ) : jobs.length === 0 ? (
            <p className="text-xs text-gray-600 py-3">등록된 크론 잡이 없습니다.</p>
          ) : (
            <div className="space-y-1.5">
              {jobs.map((job) => (
                <div key={`${job.name}-${job.schedule}`} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/[0.02] border border-white/5">
                  <CalendarClock className="w-4 h-4 text-sky-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-white truncate">{job.name}</p>
                    <p className="text-[10px] text-gray-500 truncate">{job.schedule} · 다음 {job.next_run}</p>
                  </div>
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300">
                    {job.type}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {status && <p className="text-[10px] text-gray-500">{status}</p>}
      </div>
    </>
  );
}


/* ─── Vertex SA 관리 패널 ─── */
function VertexSaPanel({
  accounts,
  loading,
  status,
  summary,
  testingId,
  onRefresh,
  onUpload,
  onTest,
  onReorder,
  onToggle,
  onDelete,
}: {
  accounts: VertexSaAccount[];
  loading: boolean;
  status: string;
  summary: VertexSaSummary;
  testingId: string | null;
  onRefresh: () => void;
  onUpload: (files: File[]) => Promise<void>;
  onTest: (id?: string) => Promise<void>;
  onReorder: (next: VertexSaAccount[]) => void;
  onToggle: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const [draggingId, setDraggingId] = useState<string | null>(null);

  const moveAccount = (fromId: string, toId: string) => {
    if (fromId === toId) return;
    const fromIndex = accounts.findIndex((item) => item.id === fromId);
    const toIndex = accounts.findIndex((item) => item.id === toId);
    if (fromIndex < 0 || toIndex < 0) return;
    const next = [...accounts];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
    onReorder(next);
  };

  return (
    <>
      <p className="text-[10px] text-gray-500">
        Gemini/Imagen/Veo3는 Vertex AI service account만 사용합니다. 위에서 아래 순서로 한 요청마다 다음 SA를 씁니다.
      </p>

      <div className="p-4 rounded-2xl bg-cyan-500/8 border border-cyan-500/15 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white">다음 사용 예정 SA</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              활성 SA {summary.enabled_count}개 · {summary.backend === "vertex_ai" ? "Vertex AI" : summary.backend}
              {summary.sa_only ? " · SA 전용" : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onTest()}
            disabled={testingId === "__next__" || !summary.next_account}
            className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 disabled:text-gray-400 text-white text-xs rounded-lg transition-colors"
          >
            {testingId === "__next__" ? "테스트 중..." : "다음 SA 테스트"}
          </button>
        </div>
        {summary.next_account ? (
          <div className="rounded-lg bg-white/[0.03] border border-white/10 px-3 py-2">
            <p className="text-xs text-white">{summary.next_account.project_id}</p>
            <p className="text-[10px] text-gray-400 truncate">{summary.next_account.client_email}</p>
            <p className="text-[10px] text-gray-500 truncate">{summary.next_account.filename}</p>
          </div>
        ) : (
          <p className="text-xs text-gray-500">현재 사용할 수 있는 활성 SA가 없습니다.</p>
        )}
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={async (e) => {
          e.preventDefault();
          setDragOver(false);
          await onUpload(Array.from(e.dataTransfer.files).filter((file) => file.name.toLowerCase().endsWith(".json")));
        }}
        className={`p-5 rounded-2xl border border-dashed transition-colors ${
          dragOver ? "bg-cyan-500/10 border-cyan-400/60" : "bg-white/[0.03] border-white/10"
        }`}
      >
        <div className="flex items-center gap-3">
          <UploadCloud className="w-6 h-6 text-cyan-400" />
          <div className="flex-1">
            <p className="text-sm font-medium text-white">SA JSON 드래그앤드롭</p>
            <p className="text-xs text-gray-500 mt-0.5">Google service_account JSON만 받습니다. 키 본문은 화면에 표시하지 않습니다.</p>
          </div>
          <label className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium rounded-lg cursor-pointer transition-colors">
            파일 선택
            <input
              type="file"
              accept="application/json,.json"
              multiple
              className="hidden"
              onChange={async (e) => {
                await onUpload(Array.from(e.target.files || []));
                e.currentTarget.value = "";
              }}
            />
          </label>
        </div>
      </div>

      <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">SA 로테이션 순서</h3>
            <p className="text-xs text-gray-500 mt-0.5">켜진 SA만 사용합니다. 드래그해서 순서를 바꾸세요.</p>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            className="px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 text-xs rounded-lg transition-colors"
          >
            새로고침
          </button>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-xs text-gray-500 py-4">
            <div className="w-4 h-4 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
            SA 목록 불러오는 중...
          </div>
        ) : accounts.length === 0 ? (
          <div className="text-center py-6">
            <Key className="w-8 h-8 text-gray-600 mx-auto mb-2" />
            <p className="text-sm text-gray-500">등록된 Vertex SA가 없습니다</p>
          </div>
        ) : (
          <div className="space-y-2">
            {accounts.map((account, index) => (
              <div
                key={account.id}
                draggable
                onDragStart={() => setDraggingId(account.id)}
                onDragEnd={() => setDraggingId(null)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (draggingId) moveAccount(draggingId, account.id);
                }}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg border ${
                  account.enabled ? "bg-white/[0.03] border-white/10" : "bg-white/[0.015] border-white/5 opacity-55"
                }`}
              >
                <GripVertical className="w-4 h-4 text-gray-600 cursor-grab shrink-0" />
                <span className="w-6 h-6 rounded bg-cyan-500/15 text-cyan-300 text-xs flex items-center justify-center shrink-0">
                  {index + 1}
                </span>
                <div className="flex-1 min-w-0 text-left">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-white truncate">{account.project_id}</span>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded ${account.source === "managed" ? "bg-cyan-500/15 text-cyan-300" : "bg-amber-500/15 text-amber-300"}`}>
                      {account.source === "managed" ? "업로드" : "루트"}
                    </span>
                    {account.is_next && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300">
                        다음
                      </span>
                    )}
                    {account.last_used && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300">
                        방금 사용
                      </span>
                    )}
                    {account.blocked && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-500/15 text-red-300">
                        429 대기 {Math.max(1, Number(account.blocked_remaining_sec || 0))}초
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-gray-500 truncate">{account.client_email}</p>
                  <p className="text-[9px] text-gray-600 truncate">{account.filename}</p>
                </div>
                <label className="flex items-center gap-1.5 text-[10px] text-gray-400 shrink-0">
                  <input
                    type="checkbox"
                    checked={account.enabled}
                    onChange={(e) => onToggle(account.id, e.target.checked)}
                    className="accent-cyan-500"
                  />
                  사용
                </label>
                <button
                  type="button"
                  onClick={() => onTest(account.id)}
                  disabled={testingId === account.id}
                  className="px-2 py-1 bg-white/5 hover:bg-white/10 disabled:bg-gray-800 disabled:text-gray-500 border border-white/10 text-[10px] text-gray-300 rounded-md transition-colors"
                >
                  {testingId === account.id ? "테스트 중" : "테스트"}
                </button>
                <button
                  type="button"
                  disabled={!account.managed}
                  onClick={() => onDelete(account.id)}
                  title={account.managed ? "삭제" : "루트 파일은 여기서 삭제하지 않습니다"}
                  className="text-gray-600 hover:text-red-400 disabled:opacity-30 disabled:hover:text-gray-600 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
        {status && <p className="text-[10px] text-gray-500">{status}</p>}
      </div>
    </>
  );
}


/* ─── 청구 금액 알림 설정 패널 ─── */
function BillingSettingsPanel({
  settings,
  overview,
  loading,
  status,
  onChange,
  onSave,
  onCheck,
}: {
  settings: BillingSettings;
  overview: BillingOverview | null;
  loading: boolean;
  status: string;
  onChange: (next: Partial<BillingSettings>) => void;
  onSave: () => void;
  onCheck: () => void;
}) {
  const parseKrwInput = (value: string) => Number(value.replace(/[^\d]/g, "") || 0);
  const thresholdReached = settings.total_krw >= settings.threshold_krw && settings.threshold_krw > 0;
  const overKrw = Math.max(0, settings.total_krw - settings.threshold_krw);

  return (
    <>
      <p className="text-[10px] text-gray-500">
        결제 화면의 금액을 넣어두면 내부 크론이 매시간 확인합니다. 기준선을 넘으면 Telegram으로 한 번 알리고 크론을 자동으로 끕니다.
      </p>

      <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white">청구 금액 경보</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              현재 입력값: {settings.current_krw.toLocaleString()}원 / {settings.total_krw.toLocaleString()}원
            </p>
          </div>
          <span className={`text-[10px] px-2 py-1 rounded-full border ${
            thresholdReached
              ? "bg-red-500/15 text-red-300 border-red-500/30"
              : "bg-green-500/10 text-green-300 border-green-500/20"
          }`}>
            {thresholdReached ? `초과 ${overKrw.toLocaleString()}원` : "기준선 아래"}
          </span>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <div className="w-4 h-4 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" />
            불러오는 중...
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <BillingMoneyInput
                label="현재 사용금액"
                value={settings.current_krw}
                placeholder="16,434"
                onChange={(value) => onChange({ current_krw: parseKrwInput(value) })}
              />
              <BillingMoneyInput
                label="총 청구금액"
                value={settings.total_krw}
                placeholder="453,008"
                onChange={(value) => onChange({ total_krw: parseKrwInput(value) })}
              />
              <BillingMoneyInput
                label="알림 기준"
                value={settings.threshold_krw}
                placeholder="400,000"
                onChange={(value) => onChange({ threshold_krw: parseKrwInput(value) })}
              />
              <div>
                <label className="text-[10px] text-gray-500 block mb-1">크론 체크 시각</label>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">매시간</span>
                  <input
                    type="number"
                    min={0}
                    max={59}
                    value={settings.cron_minute}
                    onChange={(e) => onChange({ cron_minute: Math.max(0, Math.min(59, Number(e.target.value || 0))) })}
                    className="w-20 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-emerald-500/50"
                  />
                  <span className="text-xs text-gray-400">분</span>
                </div>
              </div>
            </div>

            <label className="flex items-center gap-2 text-xs text-gray-300">
              <input
                type="checkbox"
                checked={settings.cron_enabled}
                onChange={(e) => onChange({ cron_enabled: e.target.checked })}
                className="accent-emerald-500"
              />
              매시간 자동 체크 사용
            </label>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onSave}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg transition-colors"
              >
                저장
              </button>
              <button
                type="button"
                onClick={onCheck}
                className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-200 text-xs font-medium rounded-lg transition-colors"
              >
                지금 확인
              </button>
              {status && <span className="text-[10px] text-gray-500">{status}</span>}
            </div>

            {overview && (
              <div className="rounded-xl border border-white/10 bg-black/20 p-3 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold text-white">오늘 비용 상세</p>
                    <p className="text-[10px] text-gray-500">
                      {overview.date} · 총 {overview.total_krw.toLocaleString()}원 · 환율 $1 = {overview.exchange_rate.toLocaleString()}원
                    </p>
                  </div>
                  <span className="text-[10px] px-2 py-1 rounded-full border border-cyan-500/20 bg-cyan-500/10 text-cyan-300">
                    비디오 {Object.values(overview.channels).reduce((sum, item) => sum + item.video_count, 0)}클립
                  </span>
                </div>

                <div className="space-y-2">
                  {Object.entries(overview.channels).length === 0 ? (
                    <p className="text-[11px] text-gray-500">오늘 기록된 생성 비용이 아직 없습니다.</p>
                  ) : Object.entries(overview.channels).map(([channel, info]) => (
                    <div key={channel} className="rounded-lg bg-white/[0.03] border border-white/5 p-3 space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-xs text-white font-medium">{channel}</p>
                          <p className="text-[10px] text-gray-500">
                            성공 {info.success} · 실패 {info.failed} · 비디오 {info.video_count}클립
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-white font-medium">{info.total_krw.toLocaleString()}원</p>
                          <p className="text-[10px] text-gray-500">영상 {info.video_krw.toLocaleString()}원</p>
                        </div>
                      </div>
                      {info.video_models.length > 0 && (
                        <div className="space-y-1.5">
                          {info.video_models.map((model) => (
                            <div key={`${channel}-${model.key}`} className="flex items-center justify-between gap-3 text-[11px]">
                              <div className="text-gray-300">
                                {model.label}
                                <span className="text-gray-500"> · {model.count}클립 · {model.unit_krw.toLocaleString()}원/clip</span>
                              </div>
                              <div className="text-gray-200">{model.krw.toLocaleString()}원</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}


function BillingMoneyInput({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string;
  value: number;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="text-[10px] text-gray-500 block mb-1">{label}</label>
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">₩</span>
        <input
          type="text"
          inputMode="numeric"
          value={value ? value.toLocaleString() : ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-white/5 border border-white/10 rounded-lg pl-7 pr-3 py-2 text-xs text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-emerald-500/50 font-mono"
        />
      </div>
    </div>
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
  onRefreshServerKeys,
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
  onRefreshServerKeys?: () => Promise<void> | void;
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
              : serverStatus === false ? "미설정" : "서버 설정됨"}
          </span>
        </div>
      </div>

      {/* .env 키 목록 (서버에서 마스킹된 키) */}
      {envMaskedKeys.length > 0 && (
        <div className="space-y-1 mb-2">
          {envMaskedKeys.map((masked, idx) => (
            <div key={`env-${idx}`} id={`env-key-${idx}`} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-green-500/10 border border-green-500/20">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0" />
              <span className="text-xs text-green-300 font-mono flex-1">{masked}</span>
              <span className="text-[10px] text-green-500/60">.env</span>
              <button
                onClick={async () => {
                  if (!confirm(`이 키(${masked})를 .env에서 제거할까요?`)) return;
                  try {
                    const res = await fetch(`${API_BASE}/api/settings/remove-env-key`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ keyType: config.id, maskedKey: masked }),
                    });
                    const data = await res.json();
                    if (data.ok && data.removed > 0) {
                      await onRefreshServerKeys?.();
                    } else {
                      alert("키 제거 실패: 매칭되는 키를 찾을 수 없습니다");
                    }
                  } catch {
                    alert("키 제거 중 오류 발생");
                  }
                }}
                aria-label=".env 키 제거"
                className="text-gray-500 hover:text-red-400 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
              </button>
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


/* ─── YouTube 계정 연결 행 (연동 상태 자동 표시) ─── */
function YouTubeAccountRow({ channelName, accountId, onUpdate }: { channelName: string; accountId?: string | null; onUpdate: (id: string) => void }) {
  const [ytChannels, setYtChannels] = useState<{ id: string; title: string; connected: boolean }[]>([]);
  const [channelStatus, setChannelStatus] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/youtube/status`).then(r => r.json()).then(data => {
      if (data.channels) setYtChannels(data.channels);
      if (data.channel_status) setChannelStatus(data.channel_status);
    }).catch(() => {});
  }, []);

  // 이 채널 프리셋이 실제로 연동됐는지 (channel_status 기준)
  const isConnected = channelStatus[channelName] === true;
  const displayId = accountId || "";
  const displayTitle = ytChannels.find(c => c.id === displayId)?.title;

  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.02] border border-white/5">
      <span className="text-xs text-gray-400 w-20 shrink-0">YouTube</span>
      {isConnected ? (
        <div className="flex-1 flex items-center gap-2">
          <span className="text-[10px] text-green-400 font-mono">{displayTitle || displayId}</span>
          <span className="text-[9px] text-gray-600">{displayId.slice(0, 8)}...</span>
        </div>
      ) : (
        <input
          type="text"
          value={displayId}
          onChange={(e) => onUpdate(e.target.value)}
          placeholder="채널 ID (UC...)"
          className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1 text-[10px] text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-teal-500/50 font-mono"
        />
      )}
      <div className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-500" : "bg-gray-600"}`} />
      {!isConnected && (
        <button
          type="button"
          disabled={loading}
          onClick={async () => {
            setLoading(true);
            try {
              const res = await fetch(`${API_BASE}/api/youtube/auth`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({channel: channelName}) });
              const data = await res.json();
              if (data.auth_url) window.location.href = data.auth_url;
              else alert(data.error || "인증 URL 생성 실패");
            } catch { alert("서버 연결 실패"); }
            setLoading(false);
          }}
          className="px-2 py-0.5 text-[9px] bg-red-500/20 text-red-300 rounded hover:bg-red-500/30 transition-colors whitespace-nowrap"
        >
          {loading ? "..." : "연동"}
        </button>
      )}
    </div>
  );
}
