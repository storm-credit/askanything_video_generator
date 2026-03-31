"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, CheckCircle2, AlertCircle, Settings, Brain, ImageIcon, Square, Globe, Upload, Youtube, X, ExternalLink, Video, Music, Instagram, Send, Tv, Mic, Type, MoveVertical, Zap, Crown, Film, FolderOpen, Download, Loader2, FlaskConical } from "lucide-react";
import { API_BASE, KeyStatus, KeyUsageStats } from "../components/types";
import { SettingsModal } from "../components/SettingsModal";
import { ProgressPanel } from "../components/ProgressPanel";

// 채널 프리셋 정의
const CHANNEL_PRESETS: Record<string, { label: string; flag: string; language: string; ttsSpeed: number; platforms: string[]; captionSize: number; captionY: number; cameraStyle: string }> = {
  askanything: { label: "AskAnything", flag: "\ud83c\uddf0\ud83c\uddf7", language: "ko", ttsSpeed: 0.9, platforms: ["youtube"], captionSize: 54, captionY: 35, cameraStyle: "auto" },
  wonderdrop: { label: "WonderDrop", flag: "\ud83c\uddfa\ud83c\uddf8", language: "en", ttsSpeed: 0.85, platforms: ["youtube"], captionSize: 50, captionY: 35, cameraStyle: "auto" },
  exploratodo: { label: "ExploraTodo", flag: "\ud83c\uddea\ud83c\uddf8", language: "es", ttsSpeed: 0.95, platforms: ["youtube"], captionSize: 50, captionY: 35, cameraStyle: "auto" },
  prismtale: { label: "Prism Tale", flag: "\ud83c\uddfa\ud83c\uddf8", language: "es", ttsSpeed: 0.9, platforms: ["youtube"], captionSize: 50, captionY: 35, cameraStyle: "auto" },
};

// localStorage 유틸
// SSR/CSR 초기 렌더에서는 항상 fallback 반환 (hydration 불일치 방지)
// localStorage 복원은 _restoreSettings useEffect에서 수행
let _hydrated = false;
const loadSetting = <T,>(key: string, fallback: T): T => {
  if (!_hydrated || typeof window === "undefined") return fallback;
  try { const v = localStorage.getItem(`aa_${key}`); return v !== null ? JSON.parse(v) : fallback; } catch { return fallback; }
};
const saveSetting = (key: string, value: unknown) => {
  if (typeof window === "undefined") return;
  try { localStorage.setItem(`aa_${key}`, JSON.stringify(value)); } catch { /* quota exceeded */ }
};

export default function Home() {
  const [topic, setTopic] = useState("");
  const [todayCuts, setTodayCuts] = useState<Record<string, any[]> | null>(null); // Day 파일 스크립트 저장
  const [todayMeta, setTodayMeta] = useState<Record<string, {title: string, description: string, hashtags: string}> | null>(null); // Day 파일 메타데이터
  const [qualityPreset, setQualityPreset] = useState(() => loadSetting("qualityPreset", "best"));
  const [llmProvider, setLlmProvider] = useState(() => loadSetting("llmProvider", "gemini"));
  const [llmModel, setLlmModel] = useState(() => loadSetting("llmModel", ""));
  const [imageEngine, setImageEngine] = useState(() => loadSetting("imageEngine", "imagen"));
  const [imageModel, setImageModel] = useState(() => loadSetting("imageModel", ""));
  const [videoEngine, setVideoEngine] = useState(() => loadSetting("videoEngine", "none"));
  const [videoModel, setVideoModel] = useState(() => loadSetting("videoModel", ""));
  const [testMode, setTestMode] = useState(() => loadSetting("testMode", false));
  const [isDownloading, setIsDownloading] = useState(false);
  const [language, setLanguage] = useState(() => loadSetting("language", "ko"));
  const [cameraStyle, setCameraStyle] = useState(() => loadSetting("cameraStyle", "auto"));
  const [bgmTheme, setBgmTheme] = useState(() => loadSetting("bgmTheme", "random"));

  // 오늘 할 일 모달
  const [showTodayModal, setShowTodayModal] = useState(false);
  const [todayTopics, setTodayTopics] = useState<any[]>([]);
  const [todayFile, setTodayFile] = useState("");

  // YouTube URL 자동 감지 (토픽 입력란에서)
  const isYouTubeUrl = (text: string) => /(?:youtube\.com\/(?:shorts\/|watch\?v=)|youtu\.be\/)/.test(text.trim());
  const detectedRefUrl = isYouTubeUrl(topic) ? topic.trim() : undefined;
  const [channel, setChannel] = useState(() => loadSetting("channel", ""));
  const [selectedChannels, setSelectedChannels] = useState<string[]>(() => loadSetting("selectedChannels", []));
  const [platforms, setPlatforms] = useState<string[]>(() => loadSetting("platforms", ["youtube"]));

  // 멀티채널 진행 상태
  type ChannelStatus = { progress: number; logs: string[]; status: 'idle' | 'generating' | 'done' | 'error'; videoUrl?: string; errorMsg?: string; genId?: string };
  const [channelResults, setChannelResults] = useState<Record<string, ChannelStatus>>({});
  const multiAbortRefs = useRef<Record<string, AbortController>>({});
  const [ttsSpeed, setTtsSpeed] = useState(() => loadSetting("ttsSpeed", 0.9));
  const [voiceId, setVoiceId] = useState(() => loadSetting("voiceId", "auto"));
  const [captionSize, setCaptionSize] = useState(() => loadSetting("captionSize", 54));
  const [captionY, setCaptionY] = useState(() => loadSetting("captionY", 35));

  // 설정 변경 시 localStorage에 자동 저장
  useEffect(() => {
    saveSetting("qualityPreset", qualityPreset);
    saveSetting("llmProvider", llmProvider);
    saveSetting("llmModel", llmModel);
    saveSetting("imageEngine", imageEngine);
    saveSetting("imageModel", imageModel);
    saveSetting("videoEngine", videoEngine);
    saveSetting("videoModel", videoModel);
    saveSetting("testMode", testMode);
    saveSetting("language", language);
    saveSetting("cameraStyle", cameraStyle);
    saveSetting("bgmTheme", bgmTheme);
    saveSetting("channel", channel);
    saveSetting("selectedChannels", selectedChannels);
    saveSetting("platforms", platforms);
    saveSetting("ttsSpeed", ttsSpeed);
    saveSetting("voiceId", voiceId);
    saveSetting("captionSize", captionSize);
    saveSetting("captionY", captionY);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qualityPreset, llmProvider, llmModel, imageEngine, imageModel, videoEngine, videoModel, testMode, language, cameraStyle, bgmTheme, channel, selectedChannels, platforms, ttsSpeed, voiceId, captionSize, captionY]);

  // localStorage → state 복원 (hydration 후 1회만 실행)
  useEffect(() => {
    _hydrated = true;
    const _load = <T,>(key: string, fallback: T): T => {
      try { const v = localStorage.getItem(`aa_${key}`); return v !== null ? JSON.parse(v) : fallback; } catch { return fallback; }
    };
    setQualityPreset(_load("qualityPreset", "best"));
    setLlmProvider(_load("llmProvider", "gemini"));
    setLlmModel(_load("llmModel", ""));
    setImageEngine(_load("imageEngine", "imagen"));
    setImageModel(_load("imageModel", ""));
    setVideoEngine(_load("videoEngine", "none"));
    setVideoModel(_load("videoModel", ""));
    setTestMode(_load("testMode", false));
    setLanguage(_load("language", "ko"));
    setCameraStyle(_load("cameraStyle", "auto"));
    setBgmTheme(_load("bgmTheme", "random"));
    setChannel(_load("channel", ""));
    setSelectedChannels(_load("selectedChannels", []));
    setPlatforms(_load("platforms", ["youtube"]));
    setTtsSpeed(_load("ttsSpeed", 0.9));
    setVoiceId(_load("voiceId", "auto"));
    setCaptionSize(_load("captionSize", 54));
    setCaptionY(_load("captionY", 35));
  }, []);

  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // 배포 모드: 생성만 (업로드는 모달에서 수동)
  const [publishMode] = useState<"realtime" | "private" | "scheduled" | "local">("local");
  const [scheduledTime, setScheduledTime] = useState("");

  // 설정 모달
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [serverKeyStatus, setServerKeyStatus] = useState<KeyStatus | null>(null);
  const [googleKeyCount, setGoogleKeyCount] = useState(0);
  const [serverMaskedKeys, setServerMaskedKeys] = useState<Record<string, string[]>>({});

  // 멀티키 저장소: { openai: ["sk-..."], elevenlabs: ["sk_..."], ... }
  const [savedKeys, setSavedKeys] = useState<Record<string, string[]>>(() => {
    if (typeof window === "undefined") return {};
    try {
      const stored = localStorage.getItem("askanything_keys");
      return stored ? JSON.parse(stored) : {};
    } catch { return {}; }
  });
  // 입력 중인 키 값
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  // 비밀번호 표시 토글
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  // 저장 경로 설정
  const [outputPath, setOutputPath] = useState(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem("askanything_output_path") || "";
  });
  // 키 사용량 통계
  const [keyUsageStats, setKeyUsageStats] = useState<KeyUsageStats | null>(null);
  // 모델별 잔여 호출 수
  const [modelLimits, setModelLimits] = useState<Record<string, { rpm: number; rpd: number; used: number; total_rpd: number; remaining: number }> | null>(null);
  // 업로드 (멀티 플랫폼)
  const [generatedVideoPath, setGeneratedVideoPath] = useState<string | null>(null);
  const [generatedVideoUrl, setGeneratedVideoUrl] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadPlatform, setUploadPlatform] = useState<"youtube" | "tiktok" | "instagram">("youtube");
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDescription, setUploadDescription] = useState("");
  const [uploadTags, setUploadTags] = useState("");
  const [uploadPrivacy, setUploadPrivacy] = useState("private");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ success: boolean; url?: string; error?: string; scheduled_at?: string } | null>(null);
  const [uploadChannel, setUploadChannel] = useState("");  // 업로드 모달에 전달할 채널 이름
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleDate, setScheduleDate] = useState("");
  // YouTube
  const [ytConnected, setYtConnected] = useState(false);
  const [ytChannelStatus, setYtChannelStatus] = useState<Record<string, boolean>>({});
  const [ytChannels, setYtChannels] = useState<{ id: string; title: string; connected: boolean }[]>([]);
  const [ytSelectedChannel, setYtSelectedChannel] = useState<string>("");
  // TikTok
  const [ttConnected, setTtConnected] = useState(false);
  const [ttPrivacy, setTtPrivacy] = useState("SELF_ONLY");
  // Instagram
  const [igConnected, setIgConnected] = useState(false);

  // 미리보기 모드
  const [previewMode, setPreviewMode] = useState(false);
  type PreviewData = {
    sessionId: string;
    title: string;
    channel?: string;
    cuts: { index: number; script: string; prompt: string; description?: string; image_url: string | null }[];
  };
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [editedScripts, setEditedScripts] = useState<Record<number, string>>({});
  // 멀티채널 미리보기
  const [channelPreviews, setChannelPreviews] = useState<Record<string, PreviewData>>({});
  const [activePreviewTab, setActivePreviewTab] = useState<string>("");
  const [editedScriptsMap, setEditedScriptsMap] = useState<Record<string, Record<number, string>>>({});
  const [replacingCut, setReplacingCut] = useState<number | null>(null); // 이미지 교체 중인 컷
  const [regeneratingCut, setRegeneratingCut] = useState<number | null>(null); // 이미지 재생성 중인 컷
  const [generatingScripts, setGeneratingScripts] = useState(false); // 스크립트 생성 중
  const [showSessionBrowser, setShowSessionBrowser] = useState(false);
  const [savedSessions, setSavedSessions] = useState<Array<{folder: string; title: string; cuts_count: number; image_count: number; has_video: boolean; channel: string; language: string; created_at: string}>>([]);
  const [selectedFolders, setSelectedFolders] = useState<Set<string>>(new Set());

  // 저장된 세션 목록 불러오기
  const loadSessionList = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/sessions`);
      const data = await res.json();
      setSavedSessions(data.sessions || []);
      setSelectedFolders(new Set());
      setShowSessionBrowser(true);
    } catch { alert("세션 목록 로드 실패"); }
  };

  // 세션 복원
  const restoreSession = async (folders: string[]) => {
    try {
      // 기존 상태 초기화
      setChannelPreviews({});
      setPreviewData(null);
      setEditedScripts({});
      setEditedScriptsMap({});
      setRegeneratingCut(null);
      const newPreviews: Record<string, PreviewData> = {};
      let lastTitle = "";
      for (const folder of folders) {
        const res = await fetch(`${API_BASE}/api/sessions/load`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ folder }),
        });
        if (!res.ok) { console.error(`세션 로드 실패 (${folder}):`, res.status, await res.text().catch(() => "")); continue; }
        const data = await res.json();
        const channel = data.channel || folder;
        newPreviews[channel] = { sessionId: data.sessionId, title: data.title, channel, cuts: data.cuts };
        lastTitle = data.title;
      }
      if (Object.keys(newPreviews).length === 0) { alert("세션 복원 실패"); return; }
      if (Object.keys(newPreviews).length === 1 && !Object.values(newPreviews)[0].channel) {
        setPreviewData(Object.values(newPreviews)[0]);
      } else {
        // 채널 순서 고정: askanything → wonderdrop → exploratodo → prismtale
        const channelOrder = ["askanything", "wonderdrop", "exploratodo", "prismtale"];
        const sorted: Record<string, PreviewData> = {};
        for (const ch of channelOrder) { if (newPreviews[ch]) sorted[ch] = newPreviews[ch]; }
        for (const ch of Object.keys(newPreviews)) { if (!sorted[ch]) sorted[ch] = newPreviews[ch]; }
        setChannelPreviews(sorted);
        setActivePreviewTab(Object.keys(sorted)[0]);
      }
      setTopic(lastTitle);
      setPreviewMode(true);
      setShowSessionBrowser(false);
    } catch (e) { console.error("세션 복원 오류:", e); alert("세션 복원 중 오류: " + (e instanceof Error ? e.message : String(e))); }
  };

  // 이미지 재생성 핸들러 (모델 선택 가능)
  const regenerateImage = async (cutIndex: number, sessionId: string, model: string, channel?: string) => {
    setRegeneratingCut(cutIndex);
    try {
      const res = await fetch(`${API_BASE}/api/regenerate-image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId, cutIndex, model }),
      });
      let json: Record<string, unknown>;
      try { json = await res.json(); } catch { json = { error: "서버 응답 파싱 실패" }; }
      if (!res.ok) { alert((json.error as string) || "이미지 재생성 실패"); return; }
      const newUrl = (json.image_url as string) + `?t=${Date.now()}`;
      if (channel) {
        setChannelPreviews(prev => {
          const cp = { ...prev };
          if (cp[channel]) {
            cp[channel] = { ...cp[channel], cuts: cp[channel].cuts.map(c => c.index === cutIndex ? { ...c, image_url: newUrl } : c) };
          }
          return cp;
        });
      } else {
        setPreviewData(prev => prev ? { ...prev, cuts: prev.cuts.map(c => c.index === cutIndex ? { ...c, image_url: newUrl } : c) } : prev);
      }
    } catch { alert("이미지 재생성 중 오류 발생"); }
    finally { setRegeneratingCut(null); }
  };

  // 이미지 교체 핸들러
  const replaceImage = async (file: File, cutIndex: number, sessionId: string, channel?: string) => {
    const ALLOWED = ["image/png", "image/jpeg", "image/webp"];
    if (!ALLOWED.includes(file.type)) { alert("PNG, JPG, WEBP 파일만 가능합니다."); return; }
    if (file.size > 20 * 1024 * 1024) { alert("파일 크기가 20MB를 초과합니다."); return; }
    setReplacingCut(cutIndex);
    try {
      const fd = new FormData();
      fd.append("sessionId", sessionId);
      fd.append("cutIndex", String(cutIndex));
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/api/replace-image`, { method: "POST", body: fd });
      const json = await res.json();
      if (!res.ok) { alert(json.error || "이미지 교체 실패"); return; }
      // 미리보기 데이터 업데이트
      const newUrl = json.image_url + `?t=${Date.now()}`;
      if (channel) {
        setChannelPreviews(prev => {
          const cp = { ...prev };
          if (cp[channel]) {
            cp[channel] = { ...cp[channel], cuts: cp[channel].cuts.map(c => c.index === cutIndex ? { ...c, image_url: newUrl } : c) };
          }
          return cp;
        });
      } else {
        setPreviewData(prev => prev ? { ...prev, cuts: prev.cuts.map(c => c.index === cutIndex ? { ...c, image_url: newUrl } : c) } : prev);
      }
    } catch (e) { alert("이미지 교체 중 오류 발생"); }
    finally { setReplacingCut(null); }
  };

  // 멀티채널 렌더 진행률
  const [renderResults, setRenderResults] = useState<Record<string, { progress: number; logs: string[]; status: 'rendering' | 'done' | 'error'; videoUrl?: string; errorMsg?: string }>>({});
  const [activeRenderTab, setActiveRenderTab] = useState<string>("");

  // AbortController (생성 취소용)
  const abortControllerRef = useRef<AbortController | null>(null);
  const cancelledRef = useRef(false);

  const fetchKeyStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      if (res.ok) {
        const data = await res.json();
        setServerKeyStatus(data.keys || null);
        if (data.google_key_count) setGoogleKeyCount(data.google_key_count);
        if (data.masked_keys) setServerMaskedKeys(data.masked_keys);
      }
    } catch {
      // 서버 미실행 시 무시
    }
  }, []);

  useEffect(() => {
    fetchKeyStatus();
  }, [fetchKeyStatus]);

  // localStorage 영속화
  useEffect(() => {
    try { localStorage.setItem("askanything_keys", JSON.stringify(savedKeys)); } catch {}
  }, [savedKeys]);
  useEffect(() => {
    try { localStorage.setItem("askanything_output_path", outputPath); } catch {}
  }, [outputPath]);

  const fetchKeyUsage = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/key-usage`);
      if (res.ok) {
        const data = await res.json();
        setKeyUsageStats(data);
      }
    } catch {
      // 서버 미실행 시 무시
    }
  }, []);

  const fetchModelLimits = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/model-limits`);
      if (res.ok) setModelLimits(await res.json());
    } catch {}
  }, []);

  // 초기 로드 + 모달 열릴 때마다 최신 상태 조회
  useEffect(() => { fetchModelLimits(); }, [fetchModelLimits]);
  useEffect(() => {
    if (isSettingsOpen) {
      fetchKeyStatus();
      fetchKeyUsage();
      fetchModelLimits();
    }
  }, [isSettingsOpen, fetchKeyStatus, fetchKeyUsage, fetchModelLimits]);

  const addKey = (configId: string) => {
    const value = (inputValues[configId] || "").trim();
    if (!value) return;
    setSavedKeys((prev) => {
      const existing = prev[configId] || [];
      if (existing.includes(value)) return prev;
      return { ...prev, [configId]: [...existing, value] };
    });
    setInputValues((prev) => ({ ...prev, [configId]: "" }));
  };

  const removeKey = (configId: string, index: number) => {
    setSavedKeys((prev) => {
      const existing = [...(prev[configId] || [])];
      existing.splice(index, 1);
      return { ...prev, [configId]: existing };
    });
  };

  // 키 랜덤 선택 (멀티키 로테이션)
  // 잔여 호출 표시 헬퍼
  const remainLabel = (modelId: string): string => {
    if (!modelLimits || !modelLimits[modelId]) return "";
    const m = modelLimits[modelId];
    return ` [${m.remaining}/${m.total_rpd}회]`;
  };

  // LLM 프로바이더별 모델 옵션
  const LLM_MODELS: Record<string, { value: string; label: string }[]> = {
    gemini: [
      { value: "", label: `Gemini 2.5 Pro (기본)${remainLabel("gemini-2.5-pro")}` },
      { value: "gemini-2.5-flash", label: `Gemini 2.5 Flash${remainLabel("gemini-2.5-flash")}` },
      { value: "gemini-2.0-flash", label: `Gemini 2.0 Flash${remainLabel("gemini-2.0-flash")}` },
    ],
    openai: [
      { value: "", label: `GPT-4o (기본)${remainLabel("gpt-4o")}` },
      { value: "gpt-4o-mini", label: `GPT-4o Mini${remainLabel("gpt-4o-mini")}` },
      { value: "gpt-4.1", label: `GPT-4.1${remainLabel("gpt-4.1")}` },
      { value: "gpt-4.1-mini", label: `GPT-4.1 Mini${remainLabel("gpt-4.1-mini")}` },
    ],
    claude: [
      { value: "", label: `Claude Sonnet 4 (기본)${remainLabel("claude-sonnet-4-20250514")}` },
      { value: "claude-opus-4-20250514", label: `Claude Opus 4${remainLabel("claude-opus-4-20250514")}` },
      { value: "claude-haiku-4-5-20251001", label: `Claude Haiku 3.5${remainLabel("claude-haiku-4-5-20251001")}` },
    ],
  };

  const IMAGE_MODELS: Record<string, { value: string; label: string }[]> = {
    imagen: [
      { value: "", label: `Imagen 4 Standard (기본)${remainLabel("imagen-4.0-generate-001")}` },
      { value: "imagen-4.0-fast-generate-001", label: `Imagen 4 Fast${remainLabel("imagen-4.0-fast-generate-001")}` },
    ],
    nano_banana: [
      { value: "", label: "Gemini Flash Image (기본)" },
    ],
    dalle: [
      { value: "", label: `DALL-E 3 (기본)${remainLabel("dall-e-3")}` },
    ],
  };

  const VIDEO_MODELS: Record<string, { value: string; label: string }[]> = {
    veo3: [
      { value: "", label: `Veo 3 Standard (기본)${remainLabel("veo-3.0-generate-001")}` },
      { value: "veo-3.0-fast-generate-001", label: `Veo 3 Fast${remainLabel("veo-3.0-fast-generate-001")}` },
    ],
    sora2: [{ value: "", label: "Sora 2 (기본)" }],
    kling: [{ value: "", label: "Kling v1 (기본)" }],
    none: [],
  };

  const applyPreset = (preset: string) => {
    setQualityPreset(preset);
    switch (preset) {
      case "best":
        setLlmProvider("gemini"); setLlmModel("");
        setImageEngine("imagen"); setImageModel("");
        setVideoEngine("none"); setVideoModel("");
        break;
      case "balanced":
        setLlmProvider("gemini"); setLlmModel("gemini-2.5-flash");
        setImageEngine("imagen"); setImageModel("");
        setVideoEngine("none"); setVideoModel("");
        break;
      case "fast":
        setLlmProvider("gemini"); setLlmModel("gemini-2.5-flash");
        setImageEngine("imagen"); setImageModel("imagen-4.0-fast-generate-001");
        setVideoEngine("none"); setVideoModel("");
        break;
      case "manual":
        // 수동 모드: 현재 설정 유지, 아무것도 변경하지 않음
        break;
    }
  };

  const pickKey = (configId: string): string | undefined => {
    const keys = savedKeys[configId];
    if (!keys || keys.length === 0) return undefined;
    return keys[Math.floor(Math.random() * keys.length)];
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;

    // 멀티채널 모드: selectedChannels가 2개 이상이면 병렬 생성
    if (selectedChannels.length >= 2) {
      return handleMultiGenerate(e);
    }

    setIsGenerating(true);
    setProgress(0);
    setSuccessMessage(null);
    setErrorMessage(null);
    setLogs([]);
    setGeneratedVideoUrl(null);

    const selectedOpenaiKey = pickKey("openai");
    const selectedElevenlabsKey = pickKey("elevenlabs");

    // LLM 프로바이더별 키 선택 (단일)
    let llmKeyOverride: string | undefined;
    if (llmProvider === "gemini") {
      llmKeyOverride = pickKey("gemini");
    } else if (llmProvider === "claude") {
      llmKeyOverride = pickKey("claude_key");
    }

    // Google 멀티키 전체 전달 (백엔드 로테이션용)
    const geminiKeys = savedKeys["gemini"] || [];
    const geminiKeysStr = geminiKeys.length > 0 ? geminiKeys.join(",") : undefined;

    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    cancelledRef.current = false;
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;

    try {
      const response = await fetch(`${API_BASE}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortController.signal,
        body: JSON.stringify({
          topic,
          apiKey: selectedOpenaiKey || undefined,
          elevenlabsKey: selectedElevenlabsKey || undefined,
          videoEngine,
          imageEngine,
          llmProvider,
          llmModel: llmModel || undefined,
          imageModel: imageModel || undefined,
          videoModel: videoModel || undefined,
          language,
          llmKey: llmKeyOverride || undefined,
          geminiKeys: geminiKeysStr,
          outputPath: outputPath.trim() || undefined,
          cameraStyle,
          bgmTheme,
          channel: channel || undefined,
          platforms,
          ttsSpeed,
          voiceId,
          captionSize,
          captionY,
          referenceUrl: detectedRefUrl,
          publishMode,
          scheduledTime: publishMode === "scheduled" ? scheduledTime : undefined,
          maxCuts: testMode ? 3 : undefined,
        }),
      });

      if (!response.body) throw new Error("No response body");

      reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";  // chunk 경계에서 잘린 메시지 버퍼

      const processLine = (line: string) => {
        if (!line.startsWith("data:")) return;
        const rawData = line.slice(5).trim();
        if (!rawData) return;

        if (rawData.startsWith("DONE|")) {
          const parts = rawData.slice(5).split("|");
          const videoPath = parts[0].trim().replace(/\\/g, '/');
          const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
          const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
          const downloadUrl = `${API_BASE}${normalizedPath}`;

          // YouTube 업로드용 경로 저장 + 인라인 재생용 URL
          setGeneratedVideoPath(videoPath);
          setGeneratedVideoUrl(downloadUrl);

          setSuccessMessage(channel ? "비디오 생성 + 업로드 완료!" : "비디오 생성 성공!");
          setIsGenerating(false);
          checkPlatformStatus();
        } else if (rawData.startsWith("UPLOAD_DONE|")) {
          const uploadParts = rawData.slice(12).split("|");
          const platform = uploadParts[0];
          const info = uploadParts.slice(1).join("|");
          setLogs(prev => [...prev.slice(-99), `✅ ${platform.toUpperCase()} 업로드 완료 ${info}`]);
        } else if (rawData.startsWith("ERROR|")) {
          const errMsg = rawData.slice(6);
          setLogs(prev => [...prev.slice(-99), `ERROR:${errMsg}`]);
          setErrorMessage(errMsg);
          setIsGenerating(false);
        } else if (rawData.startsWith("WARN|")) {
          const warnMsg = rawData.slice(5);
          setLogs(prev => [...prev.slice(-99), `WARN:${warnMsg}`]);
        } else if (rawData.startsWith("PROG|")) {
          const p = parseInt(rawData.slice(5), 10);
          if (!isNaN(p)) setProgress(p);
        } else {
          setLogs(prev => [...prev.slice(-99), rawData]);
        }
      };

      while (true) {
        if (cancelledRef.current) break;

        const { value, done } = await reader.read();
        if (done) {
          // 스트림 종료 시 버퍼에 남은 데이터 처리
          if (buffer.trim()) processLine(buffer);
          break;
        }

        if (cancelledRef.current) break;

        // stream: true → 멀티바이트 문자(한글) chunk 경계 깨짐 방지
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // 마지막 줄은 불완전할 수 있으므로 버퍼에 보관
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (cancelledRef.current) break;
          processLine(line);
        }
      }
    } catch (error) {
      if (abortController.signal.aborted) {
        setLogs(prev => [...prev.slice(-99), "WARN:사용자에 의해 생성이 취소되었습니다."]);
        return;
      }
      console.error(error);
      const message = error instanceof Error ? error.message : "Unknown error";
      const userMsg = message === "Failed to fetch"
        ? "[연결 실패] 백엔드 서버(localhost:8003)에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요."
        : `[네트워크 오류] ${message}`;
      setLogs(prev => [...prev.slice(-99), `ERROR:${userMsg}`]);
      setErrorMessage(userMsg);
    } finally {
      reader?.cancel().catch(() => {});
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancel = () => {
    cancelledRef.current = true;
    abortControllerRef.current?.abort();
    // 멀티채널 모드: 각 채널별 abort
    for (const ac of Object.values(multiAbortRefs.current)) ac.abort();
    multiAbortRefs.current = {};
    setIsGenerating(false);
    // 백엔드에도 전체 취소 요청 (fire-and-forget)
    fetch(`${API_BASE}/api/cancel`, { method: "POST" }).catch(() => {});
  };

  const handleClearError = () => {
    setErrorMessage(null);
    setLogs([]);
  };

  // ── 멀티채널 병렬 생성 ──
  const generateForChannel = async (ch: string) => {
    const preset = CHANNEL_PRESETS[ch];
    if (!preset) return;

    const ac = new AbortController();
    multiAbortRefs.current[ch] = ac;

    setChannelResults(prev => ({ ...prev, [ch]: { progress: 0, logs: [], status: 'generating' } }));

    const selectedOpenaiKey = pickKey("openai");
    const selectedElevenlabsKey = pickKey("elevenlabs");
    let llmKeyOverride: string | undefined;
    if (llmProvider === "gemini") llmKeyOverride = pickKey("gemini");
    else if (llmProvider === "claude") llmKeyOverride = pickKey("claude_key");
    const geminiKeys = savedKeys["gemini"] || [];
    const geminiKeysStr = geminiKeys.length > 0 ? geminiKeys.join(",") : undefined;

    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
      const response = await fetch(`${API_BASE}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ac.signal,
        body: JSON.stringify({
          topic,
          apiKey: selectedOpenaiKey || undefined,
          elevenlabsKey: selectedElevenlabsKey || undefined,
          videoEngine, imageEngine, llmProvider,
          llmModel: llmModel || undefined,
          imageModel: imageModel || undefined,
          videoModel: videoModel || undefined,
          language: preset.language,
          llmKey: llmKeyOverride || undefined,
          geminiKeys: geminiKeysStr,
          outputPath: outputPath.trim() || undefined,
          cameraStyle, bgmTheme,
          channel: ch,
          platforms: preset.platforms,
          ttsSpeed: preset.ttsSpeed,
          voiceId: "auto",
          captionSize: preset.captionSize,
          captionY: preset.captionY,
          referenceUrl: detectedRefUrl,
          publishMode,
          scheduledTime: publishMode === "scheduled" ? scheduledTime : undefined,
          maxCuts: testMode ? 3 : undefined,
        }),
      });

      if (!response.body) throw new Error("No response body");
      reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) { if (buffer.trim()) processMultiLine(ch, buffer); break; }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) processMultiLine(ch, line);
      }
    } catch (error) {
      if (ac.signal.aborted) return;
      const msg = error instanceof Error ? error.message : "Unknown error";
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'error', errorMsg: msg } }));
    } finally {
      reader?.cancel().catch(() => {});
    }
  };

  const processMultiLine = (ch: string, line: string) => {
    if (!line.startsWith("data:")) return;
    const rawData = line.slice(5).trim();
    if (!rawData) return;

    if (rawData.startsWith("DONE|")) {
      const videoPath = rawData.slice(5).split("|")[0].trim().replace(/\\/g, '/');
      const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
      const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
      const downloadUrl = `${API_BASE}${normalizedPath}`;
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'done', progress: 100, videoUrl: downloadUrl } }));
    } else if (rawData.startsWith("UPLOAD_DONE|")) {
      const uploadParts = rawData.slice(12).split("|");
      const platform = uploadParts[0];
      const info = uploadParts.slice(1).join("|");
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], logs: [...(prev[ch]?.logs || []).slice(-49), `✅ ${platform.toUpperCase()} 업로드 완료 ${info}`] } }));
    } else if (rawData.startsWith("ERROR|")) {
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'error', errorMsg: rawData.slice(6), logs: [...(prev[ch]?.logs || []).slice(-49), rawData.slice(6)] } }));
    } else if (rawData.startsWith("PROG|")) {
      const p = parseInt(rawData.slice(5), 10);
      if (!isNaN(p)) setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], progress: p } }));
    } else if (rawData.startsWith("GEN_ID|")) {
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], genId: rawData.slice(7) } }));
    } else {
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], logs: [...(prev[ch]?.logs || []).slice(-49), rawData] } }));
    }
  };

  const handleMultiGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim() || selectedChannels.length === 0) return;

    setIsGenerating(true);
    setSuccessMessage(null);
    setErrorMessage(null);
    setChannelResults({});

    const promises = selectedChannels.map(ch => generateForChannel(ch));
    await Promise.allSettled(promises);

    // 모든 채널 완료 — 최신 state는 setState callback으로 읽기
    setIsGenerating(false);
    setChannelResults(prev => {
      const doneCount = Object.values(prev).filter(r => r.status === 'done').length;
      if (doneCount > 0) {
        setSuccessMessage(`${doneCount}/${selectedChannels.length} 채널 영상 생성 완료!`);
      }
      return prev;
    });
  };

  // ── 미리보기 모드: prepare → preview → render ──

  const readSSE = async (response: Response, onPreview?: (data: string) => void) => {
    if (!response.body) throw new Error("No response body");
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    const processLine = (line: string) => {
      if (!line.startsWith("data:")) return;
      const rawData = line.slice(5).trim();
      if (!rawData) return;

      if (rawData.startsWith("DONE|")) {
        const parts = rawData.slice(5).split("|");
        const videoPath = parts[0].trim().replace(/\\/g, '/');
        const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
        const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
        const downloadUrl = `${API_BASE}${normalizedPath}`;
        setGeneratedVideoPath(videoPath);
        setGeneratedVideoUrl(downloadUrl);
        // cross-origin fetch blob 다운로드 (fire-and-forget)
        fetch(downloadUrl).then(res => {
          if (!res.ok) return;
          return res.blob();
        }).then(blob => {
          if (!blob) return;
          const blobUrl = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = blobUrl;
          a.download = `${channel || "shorts"}_${(topic || "video").slice(0, 50)}.mp4`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(blobUrl);
        }).catch(() => { /* 인라인 플레이어로 대체 */ });
        setSuccessMessage("비디오 생성 성공!");
        setIsGenerating(false);
        setPreviewData(null);
        checkPlatformStatus();
      } else if (rawData.startsWith("PREVIEW|")) {
        onPreview?.(rawData.slice(8));
      } else if (rawData.startsWith("ERROR|")) {
        setLogs(prev => [...prev.slice(-99), `ERROR:${rawData.slice(6)}`]);
        setErrorMessage(prev => prev ? `${prev}\n${rawData.slice(6)}` : rawData.slice(6));
        setIsGenerating(false);
      } else if (rawData.startsWith("WARN|")) {
        setLogs(prev => [...prev.slice(-99), `WARN:${rawData.slice(5)}`]);
      } else if (rawData.startsWith("PROG|")) {
        const p = parseInt(rawData.slice(5), 10);
        if (!isNaN(p)) setProgress(p);
      } else {
        setLogs(prev => [...prev.slice(-99), rawData]);
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) { if (buffer.trim()) processLine(buffer); break; }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) processLine(line);
    }
  };

  const prepareForChannel = async (ch: string, abortSignal: AbortSignal): Promise<PreviewData | null> => {
    const preset = CHANNEL_PRESETS[ch];
    if (!preset) return null;
    return new Promise<PreviewData | null>((resolve) => {
      fetch(`${API_BASE}/api/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortSignal,
        body: JSON.stringify({
          topic,
          apiKey: pickKey("openai") || undefined,
          llmProvider,
          llmKey: llmProvider === "gemini" ? pickKey("gemini") : llmProvider === "claude" ? pickKey("claude_key") : undefined,
          geminiKeys: (savedKeys["gemini"] || []).length > 0 ? savedKeys["gemini"].join(",") : undefined,
          imageEngine,
          language: preset.language,
          channel: ch,
          referenceUrl: detectedRefUrl,
          maxCuts: testMode ? 3 : undefined,
        }),
      }).then(async (response) => {
        await readSSE(response, (previewJson) => {
          try {
            const data: PreviewData = { ...JSON.parse(previewJson), channel: ch };
            resolve(data);
          } catch (err) {
            console.error("Preview parse error:", err);
            resolve(null);
          }
        });
        resolve(null); // SSE ended without PREVIEW
      }).catch(() => resolve(null));
    });
  };

  const handlePrepare = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;

    // ── Day 파일 스크립트가 있으면 API 호출 없이 바로 배정 ──
    if (todayCuts) {
      setIsGenerating(false);
      setProgress(0);
      setSuccessMessage(null);
      setErrorMessage(null);
      setLogs([]);
      setPreviewData(null);
      setEditedScripts({});
      setChannelPreviews({});
      setEditedScriptsMap({});
      setRenderResults({});

      // todayCuts에서 직접 채널 목록 가져오기 (selectedChannels 타이밍 이슈 방지)
      const cutsChannels = Object.keys(todayCuts);
      const channels = cutsChannels.length >= 1 ? cutsChannels : (channel ? [channel] : ["default"]);

      if (channels.length >= 2) {
        // 멀티채널: todayCuts에서 각 채널 스크립트 배정
        const previews: Record<string, PreviewData> = {};
        for (const ch of channels) {
          const chCuts = todayCuts[ch] || todayCuts[channels[0]] || [];
          if (chCuts.length > 0) {
            const data: PreviewData = {
              sessionId: `today_${topic.replace(/\s+/g, '_')}_${ch}`,
              channel: ch,
              title: topic,
              cuts: chCuts.map((c: any, i: number) => ({
                index: i,
                script: c.script || "",
                prompt: c.image_prompt || "",
                image_url: null, // 이미지 없음 — 별도 생성 필요
              })),
            };
            previews[ch] = data;
          }
        }
        setChannelPreviews(previews);
        if (Object.keys(previews).length > 0) {
          setActivePreviewTab(channels[0]);
          setPreviewMode(true);
          // 백엔드 세션 등록 (이미지 생성용) + 기존 이미지 반영
          for (const [ch, pv] of Object.entries(previews)) {
            fetch(`${API_BASE}/api/register-day-session`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                sessionId: pv.sessionId,
                topic: topic,
                channel: ch,
                cuts: pv.cuts.map((c: any) => ({ script: c.script, prompt: c.prompt })),
              }),
            }).then(r => r.json()).then(data => {
              if (data.image_urls) {
                setChannelPreviews(prev => {
                  const updated = { ...prev };
                  if (updated[ch]) {
                    const newCuts = updated[ch].cuts.map((c: any, i: number) => ({
                      ...c,
                      image_url: data.image_urls[i] || c.image_url,
                    }));
                    updated[ch] = { ...updated[ch], cuts: newCuts };
                  }
                  return updated;
                });
              }
            }).catch(() => {});
          }
        }
        setLogs(["✅ Day 파일 스크립트 배정 완료 — 이미지는 '전체 이미지 생성' 버튼으로 생성"]);
      } else {
        // 싱글채널
        const ch = channels[0];
        const chCuts = todayCuts[ch] || Object.values(todayCuts)[0] || [];
        if (chCuts.length > 0) {
          const data: PreviewData = {
            sessionId: `today_${topic.replace(/\s+/g, '_')}_${ch}`,
            title: topic,
            channel: ch,
            cuts: chCuts.map((c: any, i: number) => ({
              index: i,
              script: c.script || "",
              prompt: c.image_prompt || "",
              image_url: null,
            })),
          };
          setPreviewData(data);
          setPreviewMode(true);
          // 백엔드 세션 등록
          fetch(`${API_BASE}/api/register-day-session`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              sessionId: data.sessionId,
              topic: topic,
              channel: ch,
              cuts: data.cuts.map((c: any) => ({ script: c.script, prompt: c.prompt })),
            }),
          }).catch(() => {});
        }
        setLogs(["✅ Day 파일 스크립트 배정 완료 — 이미지는 '전체 이미지 생성' 버튼으로 생성"]);
      }
      return;
    }
    // ── Day 파일 스크립트 없음 → 기존 API 호출 ──

    setIsGenerating(true);
    setProgress(0);
    setSuccessMessage(null);
    setErrorMessage(null);
    setLogs([]);
    setPreviewData(null);
    setEditedScripts({});
    setChannelPreviews({});
    setEditedScriptsMap({});
    setRenderResults({});

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const channels = selectedChannels.length >= 2 ? selectedChannels : (channel ? [channel] : ["default"]);
    const isMulti = channels.length >= 2;

    try {
      if (isMulti) {
        // 멀티채널: 순차 prepare (이미지 API 쿼터 보호)
        const previews: Record<string, PreviewData> = {};
        for (const ch of channels) {
          setLogs(prev => [...prev.slice(-99), `[${CHANNEL_PRESETS[ch]?.flag || ""} ${CHANNEL_PRESETS[ch]?.label || ch}] 미리보기 준비 중...`]);
          const result = await prepareForChannel(ch, abortController.signal);
          if (result) {
            previews[ch] = result;
            setChannelPreviews(prev => ({ ...prev, [ch]: result }));
          }
        }
        if (Object.keys(previews).length > 0) {
          setActivePreviewTab(channels[0]);
          setPreviewMode(true);
        }
      } else {
        // 싱글 채널: 기존 로직
        const response = await fetch(`${API_BASE}/api/prepare`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: abortController.signal,
          body: JSON.stringify({
            topic,
            apiKey: pickKey("openai") || undefined,
            llmProvider,
            llmKey: llmProvider === "gemini" ? pickKey("gemini") : llmProvider === "claude" ? pickKey("claude_key") : undefined,
            geminiKeys: (savedKeys["gemini"] || []).length > 0 ? savedKeys["gemini"].join(",") : undefined,
            imageEngine,
            language,
            channel: channel || undefined,
            referenceUrl: detectedRefUrl,
            maxCuts: testMode ? 3 : undefined,
          }),
        });
        await readSSE(response, (previewJson) => {
          try {
            const data = JSON.parse(previewJson);
            setPreviewData(data);
            setPreviewMode(true);
            setIsGenerating(false);
          } catch (err) {
            console.error("Preview parse error:", err);
          }
        });
      }
    } catch (error) {
      if (abortController.signal.aborted) {
        setLogs(prev => [...prev.slice(-99), "WARN:사용자에 의해 생성이 취소되었습니다."]);
      } else {
        console.error(error);
        setErrorMessage("[연결 실패] 백엔드 서버에 연결할 수 없습니다.");
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  };

  const renderForChannel = async (ch: string, preview: PreviewData, scripts: Record<number, string>, abortSignal: AbortSignal) => {
    const preset = CHANNEL_PRESETS[ch];
    const updatedCuts = preview.cuts.map((cut) => ({
      index: cut.index,
      script: scripts[cut.index] ?? cut.script,
    }));
    setRenderResults(prev => ({ ...prev, [ch]: { progress: 0, logs: [], status: 'rendering' } }));
    try {
      const response = await fetch(`${API_BASE}/api/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortSignal,
        body: JSON.stringify({
          sessionId: preview.sessionId,
          cuts: updatedCuts,
          elevenlabsKey: pickKey("elevenlabs") || undefined,
          ttsSpeed: preset?.ttsSpeed ?? ttsSpeed,
          videoEngine,
          cameraStyle,
          bgmTheme,
          channel: ch,
          platforms: preset?.platforms ?? platforms,
          captionSize: preset?.captionSize ?? captionSize,
          captionY: preset?.captionY ?? captionY,
          outputPath: outputPath.trim() || undefined,
        }),
      });
      if (!response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) { if (buffer.trim()) processRenderLine(ch, buffer); break; }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) processRenderLine(ch, line);
      }
    } catch (error) {
      if (!abortSignal.aborted) {
        setRenderResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'error', errorMsg: '렌더 연결 실패' } }));
      }
    }
  };

  const processRenderLine = (ch: string, line: string) => {
    if (!line.startsWith("data:")) return;
    const rawData = line.slice(5).trim();
    if (!rawData) return;
    if (rawData.startsWith("DONE|")) {
      const videoPath = rawData.slice(5).split("|")[0].trim().replace(/\\/g, '/');
      const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
      const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
      setRenderResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'done', progress: 100, videoUrl: `${API_BASE}${normalizedPath}` } }));
    } else if (rawData.startsWith("ERROR|")) {
      setRenderResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'error', errorMsg: rawData.slice(6) } }));
    } else if (rawData.startsWith("PROG|")) {
      const p = parseInt(rawData.slice(5), 10);
      if (!isNaN(p)) setRenderResults(prev => ({ ...prev, [ch]: { ...prev[ch], progress: p } }));
    } else {
      setRenderResults(prev => ({ ...prev, [ch]: { ...prev[ch], logs: [...(prev[ch]?.logs || []).slice(-49), rawData] } }));
    }
  };

  // 스크립트 생성 (불러온 세션에 스크립트 없을 때)
  const handleGenerateScripts = async () => {
    const tab = activePreviewTab || activeRenderTab;
    if (!tab || !channelPreviews[tab]) {
      console.error("handleGenerateScripts: no active tab", { activePreviewTab, activeRenderTab });
      return;
    }
    const preview = channelPreviews[tab];
    // 폴더명 추출
    const firstImg = preview.cuts[0]?.image_url || "";
    const folderMatch = firstImg.match(/\/assets\/([^/]+)\//);
    if (!folderMatch) {
      console.error("handleGenerateScripts: no folderMatch from", firstImg);
      return;
    }
    const folder = folderMatch[1];
    const langMap: Record<string, string> = { askanything: "ko", wonderdrop: "en", exploratodo: "es", prismtale: "es" };
    const lang = langMap[tab] || "ko";

    setGeneratingScripts(true);
    try {
      const res = await fetch(`${API_BASE}/api/sessions/generate-scripts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder, topic: topic || preview.title, lang, channel: tab }),
      });
      const data = await res.json();
      if (data.error) { alert(data.error); return; }
      // 프리뷰 업데이트
      const updatedCuts = preview.cuts.map((cut: any, i: number) => ({
        ...cut,
        script: data.cuts[i]?.script || cut.script,
        prompt: data.cuts[i]?.prompt || cut.prompt,
        description: data.cuts[i]?.description || cut.description,
      }));
      setChannelPreviews(prev => ({
        ...prev,
        [tab]: { ...preview, title: data.title || preview.title, cuts: updatedCuts },
      }));
    } catch (e) {
      alert("스크립트 생성 중 오류");
    } finally {
      setGeneratingScripts(false);
    }
  };

  const handleRender = async () => {
    const isMultiPreview = Object.keys(channelPreviews).length >= 1;

    if (!isMultiPreview && !previewData) return;

    setIsGenerating(true);
    setProgress(0);
    setLogs([]);
    setErrorMessage(null);
    setSuccessMessage(null);
    setGeneratedVideoUrl(null);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      if (isMultiPreview) {
        // 멀티채널 렌더: 순차 렌더 (동시 Remotion 실행 방지)
        setRenderResults({});
        const channels = Object.keys(channelPreviews);
        setActiveRenderTab(channels[0]);
        for (const ch of channels) {
          await renderForChannel(ch, channelPreviews[ch], editedScriptsMap[ch] || {}, abortController.signal);
        }
        const results = Object.values(renderResults);
        const doneCount = results.filter(r => r.status === 'done').length;
        if (doneCount > 0) setSuccessMessage(`${doneCount}/${channels.length} 채널 렌더링 완료!`);
        setPreviewMode(false);
        setChannelPreviews({});
      } else {
        // 싱글 채널 렌더: 기존 로직
        const updatedCuts = previewData!.cuts.map((cut) => ({
          index: cut.index,
          script: editedScripts[cut.index] ?? cut.script,
        }));
        const response = await fetch(`${API_BASE}/api/render`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: abortController.signal,
          body: JSON.stringify({
            sessionId: previewData!.sessionId,
            cuts: updatedCuts,
            elevenlabsKey: pickKey("elevenlabs") || undefined,
            ttsSpeed,
            videoEngine,
            cameraStyle,
            bgmTheme,
            channel: channel || undefined,
            platforms,
            captionSize,
            captionY,
            outputPath: outputPath.trim() || undefined,
          }),
        });
        await readSSE(response);
      }
    } catch (error) {
      if (abortController.signal.aborted) {
        setLogs(prev => [...prev.slice(-99), "WARN:사용자에 의해 렌더링이 취소되었습니다."]);
      } else {
        console.error(error);
        setErrorMessage("[연결 실패] 렌더 서버에 연결할 수 없습니다.");
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  };

  // 전체 플랫폼 연동 상태 확인
  const checkPlatformStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/upload/platforms`);
      if (res.ok) {
        const data = await res.json();
        // YouTube
        if (data.youtube) {
          setYtConnected(data.youtube.connected === true);
          if (data.youtube.channels) {
            setYtChannels(data.youtube.channels);
            if (!ytSelectedChannel && data.youtube.channels.length > 0) {
              setYtSelectedChannel(data.youtube.channels[0].id);
            }
          }
          // 채널별 연동 상태 가져오기
          try {
            const ytStatusRes = await fetch(`${API_BASE}/api/youtube/status`);
            if (ytStatusRes.ok) {
              const ytStatusData = await ytStatusRes.json();
              if (ytStatusData.channel_status) setYtChannelStatus(ytStatusData.channel_status);
            }
          } catch {}
        }
        // TikTok
        if (data.tiktok) {
          setTtConnected(data.tiktok.connected === true);
        }
        // Instagram
        if (data.instagram) {
          setIgConnected(data.instagram.connected === true);
        }
      }
    } catch {}
  }, [ytSelectedChannel]);

  // 플랫폼별 OAuth 인증 시작
  const handlePlatformAuth = async (platform: "youtube" | "tiktok" | "instagram") => {
    try {
      const body: Record<string, string> = {};
      if (uploadChannel) body.channel = uploadChannel;
      const res = await fetch(`${API_BASE}/api/${platform}/auth`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.auth_url) {
        window.open(data.auth_url, `${platform}_auth`, "width=600,height=700");
        const poll = setInterval(async () => {
          try {
            const check = await fetch(`${API_BASE}/api/${platform}/status`);
            const status = await check.json();
            if (status.connected) {
              if (platform === "youtube") setYtConnected(true);
              else if (platform === "tiktok") setTtConnected(true);
              else if (platform === "instagram") setIgConnected(true);
              clearInterval(poll);
              clearTimeout(timeout);
            }
          } catch {
            // 연결 실패 시 폴링 중단
            clearInterval(poll);
            clearTimeout(timeout);
          }
        }, 2000);
        const timeout = setTimeout(() => clearInterval(poll), 120000);
      } else if (data.error) {
        setUploadResult({ success: false, error: data.error });
      }
    } catch {
      setUploadResult({ success: false, error: `${platform} 인증 서버에 연결할 수 없습니다.` });
    }
  };

  // 통합 업로드 실행
  const handleUpload = async () => {
    if (!generatedVideoPath) return;
    setUploading(true);
    setUploadResult(null);
    try {
      let body: Record<string, unknown>;
      let endpoint: string;

      if (uploadPlatform === "youtube") {
        endpoint = "/api/youtube/upload";
        // description에서 #해시태그 자동 추출 + tags 입력란 합산
        const hashtagsInDesc = (uploadDescription.match(/#[^\s#]+/g) || []).map(t => t.slice(1));
        const manualTags = uploadTags.split(",").map(t => t.trim()).filter(Boolean);
        const allTags = [...new Set([...hashtagsInDesc, ...manualTags])];
        // description에 이미 해시태그가 있으면 그대로, 없으면 tags에서 추가
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
          channel_id: ytSelectedChannel || undefined,
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
        if (data.need_auth) {
          if (uploadPlatform === "youtube") setYtConnected(false);
          else if (uploadPlatform === "tiktok") setTtConnected(false);
          else setIgConnected(false);
        }
        setUploadResult({ success: false, error: data.error });
      }
    } catch {
      setUploadResult({ success: false, error: "업로드 요청 실패" });
    } finally {
      setUploading(false);
    }
  };

  // 설정된 키 개수 계산
  const totalSavedKeys = Object.values(savedKeys).reduce((sum, arr) => sum + arr.length, 0);
  const totalServerKeys = serverKeyStatus ? Object.values(serverKeyStatus).filter(Boolean).length : 0;

  // 필수 키 상태 판정: 초록(전체) / 노랑(일부) / 회색(없음)
  const hasOpenai = !!(serverKeyStatus?.openai || (savedKeys["openai"]?.length ?? 0) > 0);
  const hasElevenlabs = !!(serverKeyStatus?.elevenlabs || (savedKeys["elevenlabs"]?.length ?? 0) > 0);
  const requiredAllSet = hasOpenai && hasElevenlabs;
  const requiredSomeSet = hasOpenai || hasElevenlabs || totalServerKeys > 0 || totalSavedKeys > 0;

  const iconStyle = requiredAllSet
    ? "border-green-500/40 bg-green-500/10 text-green-400 hover:bg-green-500/20"
    : requiredSomeSet
      ? "border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
      : "border-white/20 bg-white/5 text-gray-400 hover:bg-white/10";

  return (
    <main className="min-h-screen relative flex flex-col items-center justify-center p-6 sm:p-24 bg-black overflow-hidden">

      {/* 우측 상단 설정 버튼 */}
      <button
        onClick={() => setIsSettingsOpen(true)}
        className={`absolute top-6 right-6 z-50 w-11 h-11 rounded-full border backdrop-blur-md flex items-center justify-center transition-all duration-300 hover:scale-110 ${iconStyle}`}
        title="API 키 설정"
        aria-label="API 키 설정"
      >
        <Settings className="w-5 h-5" />
      </button>

      {/* 설정 모달 */}
      <AnimatePresence>
        {isSettingsOpen && (
          <SettingsModal
            serverKeyStatus={serverKeyStatus}
            savedKeys={savedKeys}
            inputValues={inputValues}
            visibleKeys={visibleKeys}
            outputPath={outputPath}
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
            onOutputPathChange={setOutputPath}
          />
        )}
      </AnimatePresence>

      {/* 백그라운드 앰비언트 라이트 */}
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
            <span>프리미엄 AI 비디오 스튜디오</span>
          </motion.div>
          <h1 className="text-5xl sm:text-7xl font-bold tracking-tight text-gradient">
            당신의 상상을<br />영상으로.
          </h1>
          <p className="text-gray-400 text-lg sm:text-xl">
            단 하나의 주제만 입력하세요. 기획, 디자인, 편집을 AI 전문가들이 알아서 완성합니다.
          </p>
        </div>

        <form onSubmit={handleGenerate} className="relative max-w-xl mx-auto mt-12 space-y-4">
          <div className="relative flex items-center">
            <input
              type="text"
              value={topic}
              onChange={(e) => { setTopic(e.target.value); setTodayCuts(null); setTodayMeta(null); }}
              disabled={isGenerating}
              placeholder="주제 또는 YouTube URL — 예: 블랙홀에 떨어지면 어떻게 될까?"
              className="w-full bg-white/5 border border-white/10 rounded-2xl py-5 pl-6 pr-6 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all text-lg backdrop-blur-md"
            />
          </div>

          {/* 액션 버튼 행 */}
          <div className="flex items-center justify-center gap-2 flex-wrap">
            {isGenerating ? (
              <button
                type="button"
                onClick={handleCancel}
                aria-label="생성 취소"
                className="bg-red-600 text-white hover:bg-red-500 font-semibold px-6 py-2.5 rounded-xl transition-colors flex items-center gap-2 text-sm"
              >
                <Square className="w-4 h-4 fill-current" />
                취소
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={loadSessionList}
                  className="bg-blue-600 text-white hover:bg-blue-500 font-semibold px-4 py-2.5 rounded-xl transition-colors text-sm"
                >
                  불러오기
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const res = await fetch(`${API_BASE}/api/batch/today-topics`);
                      const data = await res.json();
                      if (data.success && data.topics?.length > 0) {
                        setTodayTopics(data.topics);
                        setTodayFile(data.file || "");
                        setShowTodayModal(true);
                      } else {
                        alert(`⚠️ ${data.message || "오늘 주제를 찾을 수 없습니다"}`);
                      }
                    } catch (e) {
                      alert("오늘 할 일 불러오기 실패: 서버 연결을 확인하세요.");
                    }
                  }}
                  className="bg-emerald-600 text-white hover:bg-emerald-500 font-semibold px-4 py-2.5 rounded-xl transition-colors text-sm flex items-center gap-1.5"
                >
                  <Download className="w-3.5 h-3.5" />
                  오늘 할 일
                </button>
                <button
                  type="button"
                  onClick={handlePrepare}
                  disabled={!topic.trim()}
                  className="bg-purple-600 text-white hover:bg-purple-500 disabled:bg-gray-700 disabled:text-gray-400 font-semibold px-4 py-2.5 rounded-xl transition-colors text-sm"
                >
                  미리보기
                </button>
                <button
                  type="submit"
                  disabled={!topic.trim()}
                  className="bg-orange-500 text-white hover:bg-orange-400 disabled:bg-gray-700 disabled:text-gray-400 font-semibold px-4 py-2.5 rounded-xl transition-colors text-sm"
                >
                  바로생성
                </button>
              </>
            )}
          </div>

          {/* YouTube URL 감지 안내 */}
          <AnimatePresence>
            {detectedRefUrl && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="w-full max-w-2xl mx-auto"
              >
                <div className="flex items-center gap-2 px-3 py-2 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-xs text-indigo-300">
                  <Youtube className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>YouTube URL 감지 — 이 영상을 레퍼런스로 분석하여 비슷한 스타일의 영상을 생성합니다</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* 컨트롤 패널 */}
          <div className="w-full max-w-2xl mx-auto space-y-3">

            {/* 글로벌 설정 — 품질 · 언어 */}
            <div className="bg-white/[0.04] border border-white/[0.08] rounded-2xl p-3">
              <div className="flex items-center justify-center gap-1.5">
                <div className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-full px-3 py-1.5">
                  <Crown className="w-3.5 h-3.5 text-amber-400" />
                  <select value={qualityPreset} onChange={(e) => applyPreset(e.target.value)} disabled={isGenerating} aria-label="품질 선택" className="bg-transparent text-xs text-gray-200 focus:outline-none cursor-pointer appearance-none pr-3">
                    <option value="best" className="bg-gray-900">최고 품질</option>
                    <option value="balanced" className="bg-gray-900">합리적</option>
                    <option value="fast" className="bg-gray-900">빠른 생성</option>
                    <option value="manual" className="bg-gray-900">수동</option>
                  </select>
                </div>
                <div className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-full px-3 py-1.5">
                  <Globe className="w-3.5 h-3.5 text-blue-400" />
                  <select value={selectedChannels.length >= 2 ? "auto" : language} onChange={(e) => setLanguage(e.target.value)} disabled={isGenerating || selectedChannels.length >= 2} aria-label="언어 선택" className={`bg-transparent text-xs focus:outline-none appearance-none pr-3 ${selectedChannels.length >= 2 ? "text-gray-500 cursor-not-allowed" : "text-gray-200 cursor-pointer"}`}>
                    <option value="auto" className="bg-gray-900">Auto (채널별)</option>
                    <option value="ko" className="bg-gray-900">한국어</option>
                    <option value="en" className="bg-gray-900">English</option>
                    <option value="ja" className="bg-gray-900">日本語</option>
                    <option value="zh" className="bg-gray-900">中文</option>
                    <option value="es" className="bg-gray-900">Español</option>
                    <option value="fr" className="bg-gray-900">Français</option>
                    <option value="de" className="bg-gray-900">Deutsch</option>
                    <option value="pt" className="bg-gray-900">Português</option>
                    <option value="ar" className="bg-gray-900">العربية</option>
                    <option value="ru" className="bg-gray-900">Русский</option>
                    <option value="hi" className="bg-gray-900">हिन्दी</option>
                    <option value="it" className="bg-gray-900">Italiano</option>
                    <option value="sv" className="bg-gray-900">Svenska</option>
                    <option value="da" className="bg-gray-900">Dansk</option>
                    <option value="no" className="bg-gray-900">Norsk</option>
                    <option value="nl" className="bg-gray-900">Nederlands</option>
                    <option value="tr" className="bg-gray-900">Türkçe</option>
                  </select>
                </div>
                <div
                  className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-full px-3 py-1.5 cursor-pointer hover:bg-white/10 transition-colors"
                  onClick={() => {
                    const path = prompt("영상 저장 경로 (비우면 기본 assets/ 사용):", outputPath);
                    if (path !== null) setOutputPath(path);
                  }}
                  title={outputPath || "기본 경로 (assets/)"}
                >
                  <FolderOpen className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-xs text-gray-400 max-w-[80px] truncate">
                    {outputPath ? outputPath.split(/[\\/]/).pop() : "기본"}
                  </span>
                </div>
                <label className={`flex items-center gap-1 border rounded-full px-3 py-1.5 text-xs cursor-pointer transition-colors ${testMode ? "bg-red-500/20 border-red-500/50 text-red-300" : "bg-white/5 border-white/10 text-gray-500 hover:bg-white/10"}`}>
                  <input type="checkbox" checked={testMode} onChange={(e) => setTestMode(e.target.checked)} className="sr-only" />
                  <FlaskConical className="w-3.5 h-3.5" />
                  <span>{testMode ? "3컷" : "TEST"}</span>
                </label>
              </div>
            </div>

            {/* 채널 선택 (별도 행) */}
            <div className="bg-white/[0.04] border border-white/[0.08] rounded-2xl p-3">
              <div className="flex items-center justify-center gap-1.5 flex-wrap">
                <Tv className="w-3.5 h-3.5 text-purple-400" />
                {Object.entries(CHANNEL_PRESETS).map(([key, preset]) => {
                  const isSelected = selectedChannels.includes(key);
                  return (
                    <button
                      key={key}
                      type="button"
                      disabled={isGenerating}
                      onClick={() => {
                        const newSelected = isSelected
                          ? selectedChannels.filter(k => k !== key)
                          : [...selectedChannels, key];
                        setSelectedChannels(newSelected);
                        // 1개 선택: 채널 설정으로 UI 값 변경 (사용자가 오버라이드 가능)
                        // 2개+: 잠금되므로 UI 값 변경 불필요 (각 채널 설정 자동 적용)
                        if (newSelected.length === 1) {
                          const ch = CHANNEL_PRESETS[newSelected[0]];
                          if (ch) {
                            setChannel(newSelected[0]);
                            setLanguage(ch.language);
                            setTtsSpeed(ch.ttsSpeed);
                            setPlatforms(ch.platforms);
                            setCaptionSize(ch.captionSize);
                            setCaptionY(ch.captionY);
                            setCameraStyle(ch.cameraStyle);
                            setVoiceId("auto");
                          }
                        } else if (newSelected.length === 0) {
                          setChannel("");
                        }
                      }}
                      className={`flex items-center gap-1.5 border rounded-full px-3 py-1.5 text-xs transition-colors ${
                        isSelected
                          ? "bg-purple-500/20 border-purple-500/50 text-purple-300"
                          : "bg-white/5 border-white/10 text-gray-400 hover:bg-white/10"
                      }`}
                    >
                      <span className="text-[10px] font-bold uppercase opacity-60">{preset.language}</span>
                      <span>{preset.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* AI 엔진 — 수동 모드에서만 표시 */}
            {qualityPreset === "manual" && <div className="bg-white/[0.04] border border-white/[0.08] rounded-2xl p-3">
              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <Brain className="w-3.5 h-3.5 text-violet-400" />
                    <span className="text-[10px] font-medium text-gray-400">기획</span>
                  </div>
                  <select value={llmProvider} onChange={(e) => { setLlmProvider(e.target.value); setLlmModel(""); setQualityPreset("custom"); }} disabled={isGenerating} aria-label="LLM 엔진 선택" className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-violet-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
                    <option value="gemini" className="bg-gray-900">Gemini</option>
                    <option value="openai" className="bg-gray-900">GPT</option>
                    <option value="claude" className="bg-gray-900">Claude</option>
                  </select>
                  {LLM_MODELS[llmProvider]?.length > 1 && (
                    <select value={llmModel} onChange={(e) => { setLlmModel(e.target.value); setQualityPreset("custom"); }} disabled={isGenerating} aria-label="LLM 모델 선택" className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-[10px] text-gray-500 focus:outline-none focus:border-violet-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
                      {LLM_MODELS[llmProvider].map((m) => (<option key={m.value} value={m.value} className="bg-gray-900">{m.label}</option>))}
                    </select>
                  )}
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <ImageIcon className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-[10px] font-medium text-gray-400">이미지</span>
                  </div>
                  <select value={imageEngine} onChange={(e) => { setImageEngine(e.target.value); setImageModel(""); setQualityPreset("custom"); }} disabled={isGenerating} aria-label="이미지 엔진 선택" className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-emerald-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
                    <option value="imagen" className="bg-gray-900">Imagen</option>
                    <option value="nano_banana" className="bg-gray-900">Nano Banana</option>
                    <option value="dalle" className="bg-gray-900">DALL-E</option>
                  </select>
                  {IMAGE_MODELS[imageEngine]?.length > 1 && (
                    <select value={imageModel} onChange={(e) => { setImageModel(e.target.value); setQualityPreset("custom"); }} disabled={isGenerating} aria-label="이미지 모델 선택" className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-[10px] text-gray-500 focus:outline-none focus:border-emerald-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
                      {IMAGE_MODELS[imageEngine].map((m) => (<option key={m.value} value={m.value} className="bg-gray-900">{m.label}</option>))}
                    </select>
                  )}
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <Film className="w-3.5 h-3.5 text-rose-400" />
                    <span className="text-[10px] font-medium text-gray-400">비디오</span>
                  </div>
                  <select value={videoEngine} onChange={(e) => { setVideoEngine(e.target.value); setVideoModel(""); setQualityPreset("custom"); }} disabled={isGenerating} aria-label="비디오 엔진 선택" className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-rose-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
                    <option value="veo3" className="bg-gray-900">Veo 3</option>
                    <option value="sora2" className="bg-gray-900">Sora 2</option>
                    <option value="kling" className="bg-gray-900">Kling</option>
                    <option value="none" className="bg-gray-900">없음</option>
                  </select>
                  {VIDEO_MODELS[videoEngine]?.length > 1 && (
                    <select value={videoModel} onChange={(e) => { setVideoModel(e.target.value); setQualityPreset("custom"); }} disabled={isGenerating} aria-label="비디오 모델 선택" className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-[10px] text-gray-500 focus:outline-none focus:border-rose-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
                      {VIDEO_MODELS[videoEngine].map((m) => (<option key={m.value} value={m.value} className="bg-gray-900">{m.label}</option>))}
                    </select>
                  )}
                </div>
              </div>
            </div>}

            {/* 연출 — 카메라 · BGM · 음성 */}
            <div className="bg-white/[0.04] border border-white/[0.08] rounded-2xl p-3">
              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <Video className="w-3.5 h-3.5 text-sky-400" />
                    <span className="text-[10px] font-medium text-gray-400">카메라</span>
                  </div>
                  <select value={cameraStyle} onChange={(e) => setCameraStyle(e.target.value)} disabled={isGenerating} aria-label="카메라 스타일 선택" className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-sky-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
                    <option value="auto" className="bg-gray-900">자동 (감정 기반)</option>
                    <option value="dynamic" className="bg-gray-900">역동적</option>
                    <option value="gentle" className="bg-gray-900">부드러운</option>
                    <option value="static" className="bg-gray-900">고정</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <Music className="w-3.5 h-3.5 text-orange-400" />
                    <span className="text-[10px] font-medium text-gray-400">BGM</span>
                  </div>
                  <select value={bgmTheme} onChange={(e) => setBgmTheme(e.target.value)} disabled={isGenerating} aria-label="BGM 테마 선택" className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-orange-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
                    <option value="random" className="bg-gray-900">랜덤</option>
                    <option value="none" className="bg-gray-900">없음</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <Mic className="w-3.5 h-3.5 text-pink-400" />
                    <span className="text-[10px] font-medium text-gray-400">음성</span>
                  </div>
                  <select value={selectedChannels.length >= 2 ? "auto" : voiceId} onChange={(e) => setVoiceId(e.target.value)} disabled={isGenerating || selectedChannels.length >= 2} aria-label="음성 선택" className={`w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none appearance-none transition-colors ${selectedChannels.length >= 2 ? "text-gray-500 cursor-not-allowed opacity-50" : "text-gray-200 cursor-pointer hover:bg-white/10 focus:border-pink-500/50"}`}>
                    <option value="auto" className="bg-gray-900">자동</option>
                    <option value="cjVigY5qzO86Huf0OWal" className="bg-gray-900">Eric (차분)</option>
                    <option value="pNInz6obpgDQGcFmaJgB" className="bg-gray-900">Adam (권위)</option>
                    <option value="nPczCjzI2devNBz1zQrb" className="bg-gray-900">Brian (내레이션)</option>
                    <option value="pqHfZKP75CvOlQylNhV4" className="bg-gray-900">Bill (다큐)</option>
                    <option value="onwK4e9ZLuTAKqWW03F9" className="bg-gray-900">Daniel (뉴스)</option>
                    <option value="21m00Tcm4TlvDq8ikWAM" className="bg-gray-900">Rachel (여성)</option>
                    <option value="EXAVITQu4vr4xnSDxMaL" className="bg-gray-900">Sarah (부드러운)</option>
                    <option value="XrExE9yKIg1WjnnlVkGX" className="bg-gray-900">Matilda (따뜻한)</option>
                    <option value="IKne3meq5aSn9XLyUdCD" className="bg-gray-900">Charlie (유머)</option>
                    <option value="ErXwobaYiN019PkySvjV" className="bg-gray-900">Antoni (만능)</option>
                    <option value="JBFqnCBsd6RMkjVDRZzb" className="bg-gray-900">George (공포)</option>
                  </select>
                </div>
              </div>
            </div>

            {/* 자막 설정 — 슬라이더 */}
            <div className="bg-white/[0.04] border border-white/[0.08] rounded-2xl p-3">
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Zap className="w-3 h-3 text-indigo-400" />
                      <span className="text-[10px] font-medium text-gray-400">속도</span>
                    </div>
                    <span className="text-[10px] text-indigo-400/70 tabular-nums">{ttsSpeed}x</span>
                  </div>
                  <input type="range" min="0.7" max="1.2" step="0.05" value={ttsSpeed} onChange={(e) => setTtsSpeed(parseFloat(e.target.value))} disabled={isGenerating || selectedChannels.length >= 2} className={`w-full h-1 accent-indigo-500 ${selectedChannels.length >= 2 ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`} />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Type className="w-3 h-3 text-indigo-400" />
                      <span className="text-[10px] font-medium text-gray-400">자막</span>
                    </div>
                    <span className="text-[10px] text-indigo-400/70 tabular-nums">{captionSize}px</span>
                  </div>
                  <input type="range" min="32" max="72" step="4" value={captionSize} onChange={(e) => setCaptionSize(parseInt(e.target.value))} disabled={isGenerating || selectedChannels.length >= 2} className={`w-full h-1 accent-indigo-500 ${selectedChannels.length >= 2 ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`} />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <MoveVertical className="w-3 h-3 text-indigo-400" />
                      <span className="text-[10px] font-medium text-gray-400">위치</span>
                    </div>
                    <span className="text-[10px] text-indigo-400/70 tabular-nums">{captionY}%</span>
                  </div>
                  <input type="range" min="10" max="50" step="2" value={captionY} onChange={(e) => setCaptionY(parseInt(e.target.value))} disabled={isGenerating || selectedChannels.length >= 2} className={`w-full h-1 accent-indigo-500 ${selectedChannels.length >= 2 ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`} />
                </div>
              </div>
            </div>

            {/* 플랫폼은 채널 프리셋에서 자동 결정, 업로드는 모달에서 수동 */}
          </div>
        </form>
      </motion.div>

      {/* 진행률 + 로그 패널 (단일 채널) */}
      <AnimatePresence>
        {isGenerating && Object.keys(renderResults).length === 0 && (selectedChannels.length < 2 || previewMode || !channelResults || Object.keys(channelResults).length === 0) && (
          <ProgressPanel progress={progress} logs={logs} />
        )}
      </AnimatePresence>

      {/* 멀티채널 진행 패널 */}
      <AnimatePresence>
        {(isGenerating && selectedChannels.length >= 2 || Object.values(channelResults).some(r => r.status === 'done')) && Object.keys(channelResults).length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="mt-8 w-full max-w-xl glass-panel p-5 rounded-3xl relative z-10 border border-white/[0.08]"
          >
            <h3 className="text-sm font-semibold text-white mb-3">채널별 생성 현황</h3>
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
                            <Download className="w-3 h-3" /> 다운로드
                          </button>
                          {(() => {
                            const chPlatforms = preset?.platforms || ["youtube"];
                            const openChUpload = (p: "youtube" | "tiktok" | "instagram") => {
                              const videoPath = decodeURIComponent(result.videoUrl!.replace(API_BASE, ''));
                              setGeneratedVideoPath(videoPath);
                              setGeneratedVideoUrl(result.videoUrl!);
                              setUploadChannel(ch);
                              const chPreview = channelPreviews[ch];
                              // Day 파일 메타데이터가 있으면 우선 사용
                              const meta = todayMeta?.[ch];
                              const genTitle = meta?.title || chPreview?.title || topic;
                              const genDesc = meta?.description || (chPreview?.cuts || []).map((c: any) => c.script || "").filter(Boolean).join("\n") || `AI가 생성한 숏폼 영상: ${genTitle}`;
                              const genTags = meta?.hashtags || (chPreview?.cuts?.[0] as any)?.tags?.join(", ") || topic;
                              setUploadTitle(genTitle);
                              setUploadDescription(genDesc);
                              if (p === "youtube") setUploadTags(genTags);
                              setUploadResult(null);
                              setScheduleEnabled(false);
                              setScheduleDate("");
                              setUploadPlatform(p);
                              setShowUploadModal(true);
                              checkPlatformStatus();
                            };
                            return (
                              <>
                                {chPlatforms.includes("youtube") && (
                                  <button onClick={() => openChUpload("youtube")} className="flex items-center gap-1 px-2.5 py-1.5 bg-red-600 hover:bg-red-500 text-white text-[10px] font-semibold rounded-lg transition-colors">
                                    <Youtube className="w-3 h-3" /> YouTube
                                  </button>
                                )}
                                {chPlatforms.includes("tiktok") && (
                                  <button onClick={() => openChUpload("tiktok")} className="flex items-center gap-1 px-2.5 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-[10px] font-semibold rounded-lg transition-colors">
                                    <Send className="w-3 h-3" /> TikTok
                                  </button>
                                )}
                                {chPlatforms.includes("reels") && (
                                  <button onClick={() => openChUpload("instagram")} className="flex items-center gap-1 px-2.5 py-1.5 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400 text-white text-[10px] font-semibold rounded-lg transition-colors">
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
        )}
      </AnimatePresence>

      {/* 멀티채널 렌더 진행 패널 */}
      <AnimatePresence>
        {Object.keys(renderResults).length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="mt-8 w-full max-w-xl glass-panel p-5 rounded-3xl relative z-10 border border-white/[0.08]"
          >
            <h3 className="text-sm font-semibold text-white mb-3">채널별 렌더링 현황</h3>
            {/* 탭 */}
            <div className="flex gap-1.5 mb-3 border-b border-white/[0.06] pb-2">
              {Object.entries(renderResults).map(([ch, result]) => {
                const preset = CHANNEL_PRESETS[ch];
                const isActive = ch === activeRenderTab;
                return (
                  <button key={ch} onClick={() => setActiveRenderTab(ch)}
                    className={`px-3 py-1 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 ${isActive ? "bg-indigo-600/30 text-indigo-300 border border-indigo-500/30" : "text-gray-500 hover:text-gray-300 hover:bg-white/5"}`}>
                    {preset?.flag} {preset?.label}
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                      result.status === 'done' ? 'bg-green-500/20 text-green-400' :
                      result.status === 'error' ? 'bg-red-500/20 text-red-400' :
                      'bg-blue-500/20 text-blue-400'
                    }`}>
                      {result.status === 'done' ? '완료' : result.status === 'error' ? '오류' : `${result.progress}%`}
                    </span>
                  </button>
                );
              })}
            </div>
            {/* 활성 탭 상세 */}
            {renderResults[activeRenderTab] && (() => {
              const result = renderResults[activeRenderTab];
              return (
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
                          <Download className="w-3.5 h-3.5" /> 다운로드
                        </button>
                        {(() => {
                          const renderPreset = CHANNEL_PRESETS[activeRenderTab];
                          const renderPlatforms = renderPreset?.platforms || ["youtube"];
                          const openRenderUpload = (p: "youtube" | "tiktok" | "instagram") => {
                            const videoPath = decodeURIComponent(result.videoUrl!.replace(API_BASE, ''));
                            setGeneratedVideoPath(videoPath);
                            setGeneratedVideoUrl(result.videoUrl!);
                            setUploadChannel(activeRenderTab);
                            // Day 파일 메타데이터 우선 사용 (채널별 제목/설명/해시태그)
                            const chMeta = todayMeta?.[activeRenderTab];
                            setUploadTitle(chMeta?.title || topic);
                            setUploadDescription(chMeta?.description || `AI가 생성한 숏폼 영상: ${topic}`);
                            if (p === "youtube") setUploadTags(chMeta?.hashtags || topic);
                            setUploadResult(null);
                            setScheduleEnabled(false);
                            setScheduleDate("");
                            setUploadPlatform(p);
                            setShowUploadModal(true);
                            checkPlatformStatus();
                          };
                          return (
                            <>
                              {renderPlatforms.includes("youtube") && (
                                <button onClick={() => openRenderUpload("youtube")} className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-xs font-semibold rounded-lg transition-colors">
                                  <Youtube className="w-3.5 h-3.5" /> YouTube
                                </button>
                              )}
                              {renderPlatforms.includes("tiktok") && (
                                <button onClick={() => openRenderUpload("tiktok")} className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs font-semibold rounded-lg transition-colors">
                                  <Send className="w-3.5 h-3.5" /> TikTok
                                </button>
                              )}
                              {renderPlatforms.includes("reels") && (
                                <button onClick={() => openRenderUpload("instagram")} className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400 text-white text-xs font-semibold rounded-lg transition-colors">
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
              );
            })()}
          </motion.div>
        )}
      </AnimatePresence>

      {/* 미리보기 패널 */}
      <AnimatePresence>
        {previewMode && !isGenerating && (() => {
          const isMultiPreview = Object.keys(channelPreviews).length >= 1;
          const currentCh = isMultiPreview ? activePreviewTab : null;
          const currentPreview = isMultiPreview ? channelPreviews[activePreviewTab] : previewData;
          const currentScripts = isMultiPreview ? (editedScriptsMap[activePreviewTab] || {}) : editedScripts;
          const setCurrentScripts = isMultiPreview
            ? (idx: number, val: string) => setEditedScriptsMap(prev => ({ ...prev, [activePreviewTab]: { ...(prev[activePreviewTab] || {}), [idx]: val } }))
            : (idx: number, val: string) => setEditedScripts(prev => ({ ...prev, [idx]: val }));

          if (!currentPreview) return null;

          return (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="mt-8 w-full max-w-3xl glass-panel p-6 rounded-3xl relative z-10 shadow-2xl shadow-indigo-500/20 border border-white/[0.08]"
          >
            {/* 멀티채널 탭 */}
            {isMultiPreview && (
              <div className="flex gap-1.5 mb-4 border-b border-white/[0.06] pb-3">
                {Object.entries(channelPreviews).map(([ch, preview]) => {
                  const preset = CHANNEL_PRESETS[ch];
                  const isActive = ch === activePreviewTab;
                  return (
                    <div key={ch} className={`flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg transition-all cursor-pointer ${isActive ? "bg-indigo-600/30 text-indigo-300 border border-indigo-500/30" : "text-gray-500 hover:text-gray-300 hover:bg-white/5"}`}>
                      <span onClick={() => setActivePreviewTab(ch)}>
                        {preset?.flag} {preset?.label} <span className="text-[10px] opacity-60">({preview.cuts.length}컷)</span>
                      </span>
                      {Object.keys(channelPreviews).length > 1 && (
                        <button onClick={() => { setChannelPreviews(prev => { const next = {...prev}; delete next[ch]; return next; }); if (isActive) setActivePreviewTab(Object.keys(channelPreviews).find(k => k !== ch) || ""); }}
                          className="ml-1 text-gray-500 hover:text-red-400 text-[10px]">&times;</button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* 헤더 */}
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-bold text-white">{currentPreview.title}</h3>
                <span className="text-[11px] text-gray-400 bg-white/5 px-2.5 py-0.5 rounded-full border border-white/10">
                  {currentPreview.cuts.length}컷 · 약 {Math.round(currentPreview.cuts.length * 4)}초
                </span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => { setPreviewMode(false); setPreviewData(null); setChannelPreviews({}); }}
                  className="px-3 py-1.5 text-xs bg-white/10 hover:bg-white/20 text-gray-300 rounded-lg transition-colors"
                >
                  취소
                </button>
                {currentPreview.cuts.every((c: any) => !c.script) && (
                  <button
                    onClick={handleGenerateScripts}
                    disabled={generatingScripts}
                    className="px-3 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-600 text-white rounded-lg transition-colors"
                  >
                    {generatingScripts ? "스크립트 생성 중..." : "✍️ 스크립트 생성"}
                  </button>
                )}
                <button
                  onClick={async () => {
                    // 4채널 전부 이미지 생성
                    const allChannels = Object.keys(channelPreviews);
                    if (allChannels.length === 0 && currentPreview) {
                      // 싱글채널
                      allChannels.push(currentPreview.channel || "default");
                    }
                    const totalChannels = allChannels.length;
                    let totalDone = 0;
                    const totalImages = allChannels.reduce((sum, ch) => sum + (channelPreviews[ch]?.cuts?.length || currentPreview?.cuts?.length || 0), 0);

                    setLogs([`🖼️ 전체 이미지 생성 시작 — ${totalChannels}채널 × ${Math.round(totalImages / totalChannels)}컷 = ${totalImages}장`]);
                    setProgress(1); // 1%로 시작해서 진행률 바 표시

                    for (let ci = 0; ci < allChannels.length; ci++) {
                      const ch = allChannels[ci];
                      const preview = channelPreviews[ch] || currentPreview;
                      if (!preview?.sessionId) continue;

                      setLogs(prev => [...prev.slice(-99), `📸 [${ci + 1}/${totalChannels}] ${ch} 이미지 생성 중...`]);

                      try {
                        const res = await fetch(`${API_BASE}/api/batch-generate-images`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ sessionId: preview.sessionId, model: "standard" }),
                        });
                        const data = await res.json();

                        if (data.ok && data.results) {
                          const updatedCuts = [...preview.cuts];
                          for (const r of data.results) {
                            if (r.ok && r.image_url && updatedCuts[r.index]) {
                              updatedCuts[r.index] = { ...updatedCuts[r.index], image_url: r.image_url };
                            }
                          }
                          setChannelPreviews(prev => ({
                            ...prev,
                            [ch]: { ...prev[ch], cuts: updatedCuts },
                          }));
                          totalDone += data.success || 0;
                          setProgress(Math.round((totalDone / totalImages) * 100));
                          setLogs(prev => [...prev.slice(-99), `✅ ${ch}: ${data.success}/${data.total}장 완료 (전체 ${totalDone}/${totalImages})`]);
                        } else {
                          setLogs(prev => [...prev.slice(-99), `❌ ${ch} 실패: ${data.error || "알 수 없는 오류"}`]);
                        }
                      } catch (err) {
                        setLogs(prev => [...prev.slice(-99), `❌ ${ch} 에러: ${err}`]);
                      }
                    }
                    setProgress(100);
                    setLogs(prev => [...prev.slice(-99), `🎉 전체 이미지 생성 완료! ${totalDone}/${totalImages}장`]);
                  }}
                  className="px-3 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition-colors"
                >
                  🖼️ 전체 이미지 생성
                </button>
                <button
                  onClick={handleRender}
                  className="px-4 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg transition-colors shadow-lg shadow-indigo-500/25"
                >
                  확인 — 영상 만들기
                </button>
              </div>
              {/* 이미지 생성 진행률 바 */}
              {progress > 0 && progress < 100 && (
                <div className="mt-2 px-2">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-amber-400 font-medium">🖼️ 이미지 생성 중...</span>
                    <span className="text-xs text-gray-400">{progress}%</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div className="bg-amber-500 h-2 rounded-full transition-all duration-300" style={{ width: `${progress}%` }} />
                  </div>
                  {logs.length > 0 && (
                    <p className="text-[10px] text-gray-500 mt-1 truncate">{logs[logs.length - 1]}</p>
                  )}
                </div>
              )}
              {progress >= 100 && (
                <div className="mt-2 px-2">
                  <p className="text-xs text-green-400">✅ 이미지 생성 완료!</p>
                </div>
              )}
            </div>

            <div className="space-y-2.5 max-h-[60vh] overflow-y-auto pr-1 custom-scrollbar">
              {currentPreview.cuts.map((cut, i) => {
                const emotionMatch = (cut.description || "").match(/\[(SHOCK|WONDER|TENSION|REVEAL|CALM)\]/);
                const emotion = emotionMatch ? emotionMatch[1] : null;
                const emotionColors: Record<string, { bg: string; text: string; label: string }> = {
                  SHOCK: { bg: "bg-red-500/20", text: "text-red-400", label: "충격" },
                  WONDER: { bg: "bg-amber-500/20", text: "text-amber-400", label: "경이" },
                  TENSION: { bg: "bg-orange-500/20", text: "text-orange-400", label: "긴장" },
                  REVEAL: { bg: "bg-emerald-500/20", text: "text-emerald-400", label: "반전" },
                  CALM: { bg: "bg-sky-500/20", text: "text-sky-400", label: "여운" },
                };
                const eColor = emotion ? emotionColors[emotion] : null;

                return (
                  <motion.div
                    key={`${currentCh || 'single'}-${cut.index}`}
                    initial={{ opacity: 0, x: -12 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05, duration: 0.3 }}
                    className="group flex gap-3 bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.06] hover:border-white/[0.12] rounded-xl p-3 transition-all duration-200"
                  >
                    {/* 썸네일 + 컷 번호 + 이미지 교체 */}
                    <div
                      className={`relative w-24 h-40 flex-shrink-0 rounded-lg overflow-hidden bg-black/40 group-hover:scale-[1.02] transition-transform duration-200 cursor-pointer ${replacingCut === cut.index ? "opacity-50 animate-pulse" : ""}`}
                      onClick={() => {
                        const inp = document.createElement("input");
                        inp.type = "file";
                        inp.accept = "image/png,image/jpeg,image/webp";
                        inp.onchange = (e) => {
                          const f = (e.target as HTMLInputElement).files?.[0];
                          if (f) replaceImage(f, cut.index, currentPreview!.sessionId, currentCh || undefined);
                        };
                        inp.click();
                      }}
                      onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add("ring-2", "ring-indigo-400"); }}
                      onDragLeave={(e) => { e.currentTarget.classList.remove("ring-2", "ring-indigo-400"); }}
                      onDrop={(e) => {
                        e.preventDefault();
                        e.currentTarget.classList.remove("ring-2", "ring-indigo-400");
                        const f = e.dataTransfer.files[0];
                        if (f) replaceImage(f, cut.index, currentPreview!.sessionId, currentCh || undefined);
                      }}
                      title="클릭 또는 드래그하여 이미지 교체"
                    >
                      {cut.image_url ? (
                        <img
                          src={`${API_BASE}${cut.image_url}`}
                          alt={`컷 ${cut.index + 1}`}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-gray-600 text-xs">
                          이미지 없음
                        </div>
                      )}
                      {/* 호버 시 교체 안내 */}
                      <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <span className="text-[10px] text-white/80 text-center leading-tight">클릭/드래그<br/>이미지 교체</span>
                      </div>
                      <div className="absolute top-1.5 left-1.5 w-6 h-6 rounded-full bg-indigo-600/90 backdrop-blur-sm flex items-center justify-center text-[10px] font-bold text-white shadow-md">
                        {cut.index + 1}
                      </div>
                      {eColor && (
                        <div className={`absolute bottom-1.5 left-1.5 px-1.5 py-0.5 rounded text-[9px] font-medium ${eColor.bg} ${eColor.text} backdrop-blur-sm`}>
                          {eColor.label}
                        </div>
                      )}
                    </div>

                    {/* 스크립트 편집 */}
                    <div className="flex-1 flex flex-col gap-1.5 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-gray-500 font-medium">컷 {cut.index + 1}</span>
                        <span className="text-[10px] text-gray-600">
                          {(currentScripts[cut.index] ?? cut.script)?.length || 0}자
                        </span>
                      </div>
                      <textarea
                        value={currentScripts[cut.index] ?? cut.script}
                        onChange={(e) => setCurrentScripts(cut.index, e.target.value)}
                        rows={3}
                        className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-gray-200 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-500/50 focus:border-indigo-500/30 transition-colors"
                      />
                      <div className="flex items-center gap-1.5">
                        <details className="group/prompt flex-1">
                          <summary className="text-[10px] text-gray-600 cursor-pointer hover:text-gray-400 transition-colors select-none">
                            이미지 프롬프트 보기
                          </summary>
                          <p className="text-[10px] text-gray-500 mt-1 leading-relaxed">{cut.prompt}</p>
                        </details>
                        {/* 이미지 재생성 버튼 */}
                        <div className="relative flex-shrink-0">
                          <select
                            className="bg-white/5 border border-white/10 rounded px-1.5 py-0.5 text-[9px] text-gray-400 cursor-pointer hover:bg-white/10 focus:outline-none appearance-none pr-4"
                            defaultValue=""
                            disabled={regeneratingCut === cut.index || replacingCut === cut.index}
                            onChange={(e) => {
                              const model = e.target.value;
                              if (model && currentPreview) {
                                regenerateImage(cut.index, currentPreview.sessionId, model, currentCh || undefined);
                              }
                              e.target.value = "";
                            }}
                          >
                            <option value="" disabled>{regeneratingCut === cut.index ? "생성중..." : "재생성"}</option>
                            <option value="standard">Standard</option>
                            <option value="fast">Fast</option>
                            <option value="ultra">Ultra</option>
                            <option value="nano_banana">Nano Banana</option>
                            <option value="dalle">DALL-E</option>
                          </select>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>

            <p className="text-[10px] text-gray-500 mt-4 text-center">
              스크립트를 수정한 뒤 &quot;확인&quot;을 누르면 수정된 내용으로 음성 녹음 + 영상 렌더링이 시작됩니다.
            </p>
          </motion.div>
          );
        })()}
      </AnimatePresence>

      {/* 성공 패널 — 인라인 비디오 플레이어 + 업로드 */}
      <AnimatePresence>
        {successMessage && !isGenerating && !errorMessage && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="mt-16 w-full max-w-sm glass-panel p-6 rounded-[2.5rem] relative z-10 flex flex-col justify-center items-center shadow-2xl shadow-indigo-500/20 text-center space-y-4"
          >
            {/* 인라인 비디오 플레이어 */}
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
            <h3 className="text-xl text-white font-bold">생성 성공!</h3>
            {generatedVideoPath && (
              <div className="flex flex-col gap-2 w-full">
                {/* 다운로드 버튼 — cross-origin이므로 fetch blob 방식 */}
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
                  {isDownloading ? "다운로드 중..." : "다운로드"}
                </button>
                {/* 업로드 버튼 — 채널 프리셋 플랫폼만 표시 */}
                {(() => {
                  const activeChannel = selectedChannels.length === 1 ? selectedChannels[0] : channel;
                  const preset = activeChannel ? CHANNEL_PRESETS[activeChannel] : null;
                  const channelPlatforms = preset ? preset.platforms : ["youtube", "tiktok", "reels"];
                  const openUpload = (p: "youtube" | "tiktok" | "instagram") => {
                    setUploadChannel(activeChannel || "");
                    const chMeta2 = todayMeta?.[activeChannel || ""];
                    setUploadTitle(chMeta2?.title || topic);
                    setUploadDescription(chMeta2?.description || `AI가 생성한 숏폼 영상: ${topic}`);
                    if (p === "youtube") setUploadTags(chMeta2?.hashtags || topic);
                    setUploadResult(null);
                    setScheduleEnabled(false);
                    setScheduleDate("");
                    setUploadPlatform(p);
                    setShowUploadModal(true);
                    checkPlatformStatus();
                  };
                  const hasYT = channelPlatforms.includes("youtube");
                  const hasTT = channelPlatforms.includes("tiktok");
                  const hasIG = channelPlatforms.includes("reels");
                  return (
                    <>
                      {hasYT && (
                        <button onClick={() => openUpload("youtube")} className="flex items-center justify-center gap-2 px-5 py-2.5 bg-red-600 hover:bg-red-500 text-white font-semibold rounded-xl transition-colors w-full">
                          <Youtube className="w-5 h-5" /> YouTube Shorts
                        </button>
                      )}
                      {(hasTT || hasIG) && (
                        <div className="flex gap-2">
                          {hasTT && (
                            <button onClick={() => openUpload("tiktok")} className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white font-semibold rounded-xl transition-colors text-sm">
                              <Send className="w-4 h-4" /> TikTok
                            </button>
                          )}
                          {hasIG && (
                            <button onClick={() => openUpload("instagram")} className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400 text-white font-semibold rounded-xl transition-colors text-sm">
                              <Instagram className="w-4 h-4" /> Reels
                            </button>
                          )}
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* 오늘 할 일 모달 */}
      <AnimatePresence>
        {showTodayModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
              onClick={() => setShowTodayModal(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-gray-900 border border-white/10 rounded-2xl w-[90vw] max-w-md max-h-[60vh] overflow-hidden z-50 flex flex-col"
            >
              <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
                <h2 className="text-lg font-bold text-white">📋 오늘 할 일 — {todayFile}</h2>
                <button onClick={() => setShowTodayModal(false)} className="text-gray-400 hover:text-white">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {todayTopics.map((t: any, i: number) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => {
                      // 주제를 검색창에 입력
                      const topicName = t.topic_group?.replace(/^[^\s]+\s*/, "") || t.topic_group;
                      setTopic(topicName);
                      // Day 파일 스크립트가 있으면 채널별로 저장 (API 호출 없이 사용)
                      const channelCuts: Record<string, any[]> = {};
                      if (t.channels) {
                        for (const [ch, chData] of Object.entries(t.channels as Record<string, any>)) {
                          if (chData.cuts && chData.cuts.length > 0) {
                            channelCuts[ch] = chData.cuts;
                          }
                        }
                      }
                      setTodayCuts(Object.keys(channelCuts).length > 0 ? channelCuts : null);
                      // Day 파일 메타데이터 저장 (업로드 시 제목/설명/해시태그 사용)
                      const channelMeta: Record<string, {title: string, description: string, hashtags: string}> = {};
                      if (t.channels) {
                        for (const [ch, chData] of Object.entries(t.channels as Record<string, any>)) {
                          channelMeta[ch] = {
                            title: chData.title || topicName,
                            description: chData.description || "",
                            hashtags: chData.hashtags || "",
                          };
                        }
                      }
                      setTodayMeta(Object.keys(channelMeta).length > 0 ? channelMeta : null);
                      // 채널 자동 선택: 이 주제에 해당하는 채널들
                      const topicChannels = Object.keys(t.channels || {});
                      if (topicChannels.length > 0) {
                        setSelectedChannels(topicChannels);
                        // 단일 채널이면 channel도 설정
                        if (topicChannels.length === 1) {
                          setChannel(topicChannels[0]);
                        }
                        // 언어 자동 설정
                        const langMap: Record<string, string> = { askanything: "ko", wonderdrop: "en", exploratodo: "es", prismtale: "es" };
                        if (topicChannels.length === 1) {
                          setLanguage(langMap[topicChannels[0]] || "ko");
                        } else {
                          setLanguage("auto");
                        }
                      }
                      setShowTodayModal(false);
                    }}
                    className="w-full text-left px-4 py-3 rounded-xl bg-white/5 border border-white/10 hover:bg-emerald-500/10 hover:border-emerald-500/30 transition-colors"
                  >
                    <p className="text-white font-medium text-sm">{t.topic_group}</p>
                    <div className="flex gap-2 mt-1.5 flex-wrap">
                      {Object.entries(t.channels || {}).map(([ch, data]: [string, any]) => (
                        <span key={ch} className="text-[10px] px-2 py-0.5 rounded-full bg-white/10 text-gray-400">
                          {ch}
                        </span>
                      ))}
                    </div>
                  </button>
                ))}
                {todayTopics.length === 0 && (
                  <p className="text-gray-500 text-center py-8">오늘 주제가 없습니다</p>
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* 세션 불러오기 모달 */}
      <AnimatePresence>
        {showSessionBrowser && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 pointer-events-auto"
            onMouseDown={() => setShowSessionBrowser(false)}
          >
            <motion.div
              initial={{ scale: 0.95 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.95 }}
              className="relative bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg max-h-[70vh] flex flex-col pointer-events-auto"
              onMouseDown={(e) => e.stopPropagation()}
            >
              <div className="flex justify-between items-center p-4 border-b border-gray-800">
                <h2 className="text-lg font-bold">이전 세션 불러오기</h2>
                <div className="flex items-center gap-2">
                  {selectedFolders.size > 0 && (
                    <button
                      onClick={() => { restoreSession(Array.from(selectedFolders)); }}
                      className="text-sm px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 font-medium"
                    >
                      불러오기 ({selectedFolders.size})
                    </button>
                  )}
                  <button onClick={() => setShowSessionBrowser(false)} className="text-gray-400 hover:text-white text-xl">&times;</button>
                </div>
              </div>
              <div className="overflow-y-auto p-4 space-y-2 flex-1">
              {(() => {
                const grouped: Record<string, typeof savedSessions> = {};
                for (const s of savedSessions) {
                  const base = s.folder.replace(/_(askanything|wonderdrop|exploratodo|prismtale)$/, "");
                  if (!grouped[base]) grouped[base] = [];
                  grouped[base].push(s);
                }
                const groups = Object.entries(grouped);
                if (groups.length === 0) return <p className="text-gray-500 text-center py-8">저장된 세션이 없습니다</p>;
                const toggleFolder = (folder: string) => {
                  setSelectedFolders(prev => {
                    const next = new Set(prev);
                    if (next.has(folder)) next.delete(folder); else next.add(folder);
                    return next;
                  });
                };
                const toggleAll = (folders: string[]) => {
                  setSelectedFolders(prev => {
                    const next = new Set(prev);
                    const allSelected = folders.every(f => next.has(f));
                    if (allSelected) folders.forEach(f => next.delete(f));
                    else folders.forEach(f => next.add(f));
                    return next;
                  });
                };
                return groups.slice(0, 50).map(([base, items]) => (
                  <div key={base} className="rounded-xl bg-gray-800 border border-gray-700 p-3">
                    <div className="font-medium text-sm truncate mb-2">{items[0].title.replace(/_/g, " ")}</div>
                    <div className="flex flex-wrap gap-1">
                      {items.map(s => (
                        <button
                          key={s.folder}
                          onClick={() => toggleFolder(s.folder)}
                          className={`text-xs px-2 py-1 rounded transition-colors cursor-pointer ${selectedFolders.has(s.folder) ? "bg-indigo-600 text-white" : "bg-gray-700 hover:bg-gray-600"}`}
                        >
                          {s.channel || "default"} ({s.image_count}장{s.has_video ? " ✓" : ""})
                        </button>
                      ))}
                      {items.length > 1 && (
                        <button
                          onClick={() => toggleAll(items.map(s => s.folder))}
                          className={`text-xs px-2 py-1 rounded font-medium transition-colors cursor-pointer ${items.every(s => selectedFolders.has(s.folder)) ? "bg-indigo-500 text-white" : "bg-gray-600 hover:bg-gray-500"}`}
                        >
                          전체 ({items.length})
                        </button>
                      )}
                    </div>
                  </div>
                ));
              })()}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 멀티 플랫폼 업로드 모달 */}
      <AnimatePresence>
        {showUploadModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
            onClick={() => !uploading && setShowUploadModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-md glass-panel rounded-2xl border border-white/10 p-6 space-y-5 max-h-[85vh] overflow-y-auto"
            >
              {/* 헤더 + 플랫폼 탭 */}
              <div className="flex items-center justify-between">
                <h3 className="text-lg text-white font-bold">
                  업로드 — <span className="text-indigo-400">{(() => { const p = uploadChannel ? CHANNEL_PRESETS[uploadChannel] : null; return p ? `${p.flag} ${p.label}` : uploadChannel || ""; })()}</span>
                </h3>
                <button
                  onClick={() => !uploading && setShowUploadModal(false)}
                  className="text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* 플랫폼 선택 탭 — 채널 프리셋에 지정된 플랫폼만 표시 */}
              {(() => {
                const preset = uploadChannel ? CHANNEL_PRESETS[uploadChannel] : null;
                const platformMap: Record<string, string> = { youtube: "youtube", tiktok: "tiktok", reels: "instagram" };
                const availablePlatforms = preset
                  ? preset.platforms.map(p => platformMap[p] || p).filter((v, i, a) => a.indexOf(v) === i) as ("youtube" | "tiktok" | "instagram")[]
                  : ["youtube" as const, "tiktok" as const, "instagram" as const];
                return availablePlatforms.length > 1 ? (
                  <div className="flex gap-1 bg-white/5 rounded-xl p-1">
                    {availablePlatforms.includes("youtube") && (
                      <button
                        onClick={() => { setUploadPlatform("youtube"); setUploadResult(null); }}
                        className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-colors ${uploadPlatform === "youtube" ? "bg-red-600 text-white" : "text-gray-400 hover:text-white"}`}
                      >
                        <Youtube className="w-4 h-4" /> YouTube
                      </button>
                    )}
                    {availablePlatforms.includes("tiktok") && (
                      <button
                        onClick={() => { setUploadPlatform("tiktok"); setUploadResult(null); }}
                        className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-colors ${uploadPlatform === "tiktok" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"}`}
                      >
                        <Send className="w-4 h-4" /> TikTok
                      </button>
                    )}
                    {availablePlatforms.includes("instagram") && (
                      <button
                        onClick={() => { setUploadPlatform("instagram"); setUploadResult(null); }}
                        className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-colors ${uploadPlatform === "instagram" ? "bg-gradient-to-r from-purple-600 to-pink-500 text-white" : "text-gray-400 hover:text-white"}`}
                      >
                        <Instagram className="w-4 h-4" /> Reels
                      </button>
                    )}
                  </div>
                ) : null;
              })()}

              {/* 연동 안 된 경우 (채널별 체크 — channels 배열 기반) */}
              {((uploadPlatform === "youtube" && !ytConnected) ||
                (uploadPlatform === "tiktok" && !ttConnected) ||
                (uploadPlatform === "instagram" && !igConnected)) ? (
                <div className="space-y-4 text-center py-4">
                  <p className="text-gray-400 text-sm">
                    {uploadPlatform === "youtube" && "YouTube 계정을 먼저 연동해주세요."}
                    {uploadPlatform === "tiktok" && "TikTok 계정을 먼저 연동해주세요."}
                    {uploadPlatform === "instagram" && "Instagram Business 계정을 먼저 연동해주세요."}
                  </p>
                  <button
                    onClick={() => handlePlatformAuth(uploadPlatform)}
                    className={`px-6 py-3 text-white font-semibold rounded-xl transition-colors flex items-center gap-2 mx-auto ${
                      uploadPlatform === "youtube" ? "bg-red-600 hover:bg-red-500" :
                      uploadPlatform === "tiktok" ? "bg-gray-700 hover:bg-gray-600" :
                      "bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400"
                    }`}
                  >
                    {uploadPlatform === "youtube" && <Youtube className="w-5 h-5" />}
                    {uploadPlatform === "tiktok" && <Send className="w-5 h-5" />}
                    {uploadPlatform === "instagram" && <Instagram className="w-5 h-5" />}
                    계정 연동
                  </button>
                  {uploadResult && !uploadResult.success && (
                    <p className="text-red-400 text-sm">{uploadResult.error}</p>
                  )}
                </div>
              ) : uploadResult?.success ? (
                <div className="space-y-4 text-center py-4">
                  <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto" />
                  <h4 className="text-white font-bold">
                    {uploadResult.scheduled_at ? "예약 업로드 완료!" : "업로드 완료!"}
                  </h4>
                  {uploadResult.scheduled_at && (
                    <p className="text-indigo-300 text-sm">
                      {new Date(typeof uploadResult.scheduled_at === "number" ? uploadResult.scheduled_at * 1000 : uploadResult.scheduled_at).toLocaleString("ko-KR")}에 공개됩니다.
                    </p>
                  )}
                  {uploadResult.url && (
                    <a
                      href={uploadResult.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl transition-colors"
                    >
                      <ExternalLink className="w-4 h-4" />
                      영상 보기
                    </a>
                  )}
                </div>
              ) : (
                <div className="space-y-4">
                  {/* 제목 (모든 플랫폼 공통) */}
                  <div>
                    <label className="text-gray-400 text-xs mb-1 block">제목</label>
                    <input
                      type="text"
                      value={uploadTitle}
                      onChange={(e) => setUploadTitle(e.target.value)}
                      maxLength={uploadPlatform === "tiktok" ? 150 : 100}
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                    />
                  </div>

                  {/* 설명 (YouTube + Instagram) */}
                  {uploadPlatform !== "tiktok" && (
                    <div>
                      <label className="text-gray-400 text-xs mb-1 block">
                        {uploadPlatform === "instagram" ? "캡션" : "설명"}
                      </label>
                      <textarea
                        value={uploadDescription}
                        onChange={(e) => setUploadDescription(e.target.value)}
                        rows={3}
                        maxLength={uploadPlatform === "instagram" ? 2200 : 5000}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 resize-none"
                      />
                    </div>
                  )}

                  {/* 태그 (YouTube만) */}
                  {uploadPlatform === "youtube" && (
                    <div>
                      <label className="text-gray-400 text-xs mb-1 block">태그 (쉼표로 구분)</label>
                      <input
                        type="text"
                        value={uploadTags}
                        onChange={(e) => setUploadTags(e.target.value)}
                        placeholder="AI, 숏폼, 과학"
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                      />
                    </div>
                  )}

                  {/* YouTube 채널 선택 — uploadChannel에 따라 자동 매핑 */}
                  {uploadPlatform === "youtube" && ytChannels.length > 0 && (
                    <div>
                      <label className="text-gray-400 text-xs mb-1 block">채널 선택</label>
                      <select
                        value={(() => {
                          // uploadChannel → YouTube 채널 ID 자동 매핑
                          const channelNameMap: Record<string, string> = {
                            askanything: "AskAnything",
                            wonderdrop: "Wonder Drop",
                            exploratodo: "ExploraTodo",
                            prismtale: "Prism Tale",
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

                  {/* 공개 설정 */}
                  <div>
                    <label className="text-gray-400 text-xs mb-1 block">공개 설정</label>
                    {uploadPlatform === "youtube" ? (
                      <select
                        value={uploadPrivacy}
                        onChange={(e) => setUploadPrivacy(e.target.value)}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 appearance-none cursor-pointer"
                      >
                        <option value="private" className="bg-gray-900">비공개</option>
                        <option value="unlisted" className="bg-gray-900">미등록 (링크 공유)</option>
                        <option value="public" className="bg-gray-900">공개</option>
                      </select>
                    ) : uploadPlatform === "tiktok" ? (
                      <select
                        value={ttPrivacy}
                        onChange={(e) => setTtPrivacy(e.target.value)}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 appearance-none cursor-pointer"
                      >
                        <option value="SELF_ONLY" className="bg-gray-900">본인만</option>
                        <option value="MUTUAL_FOLLOW_FRIENDS" className="bg-gray-900">친구만</option>
                        <option value="FOLLOWER_OF_CREATOR" className="bg-gray-900">팔로워만</option>
                        <option value="PUBLIC_TO_EVERYONE" className="bg-gray-900">전체 공개</option>
                      </select>
                    ) : (
                      <p className="text-gray-500 text-xs">Instagram Reels는 항상 공개로 게시됩니다.</p>
                    )}
                  </div>

                  {/* 예약 업로드 (YouTube / TikTok만) */}
                  {uploadPlatform !== "instagram" && (
                    <div>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={scheduleEnabled}
                          onChange={(e) => { setScheduleEnabled(e.target.checked); if (!e.target.checked) setScheduleDate(""); }}
                          className="w-4 h-4 rounded bg-white/5 border-white/20 text-indigo-500 focus:ring-indigo-500/50"
                        />
                        <span className="text-gray-300 text-sm">예약 업로드</span>
                      </label>
                      {scheduleEnabled && (
                        <div className="mt-2">
                          <input
                            type="datetime-local"
                            value={scheduleDate}
                            onChange={(e) => setScheduleDate(e.target.value)}
                            min={new Date(Date.now() + (uploadPlatform === "tiktok" ? 15 * 60 * 1000 : 60 * 1000)).toISOString().slice(0, 16)}
                            max={uploadPlatform === "tiktok" ? new Date(Date.now() + 75 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16) : undefined}
                            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
                          />
                          <p className="text-gray-500 text-xs mt-1">
                            {uploadPlatform === "youtube"
                              ? "비공개로 업로드 후 예약 시간에 자동 공개됩니다."
                              : "15분 ~ 75일 이내로 설정해주세요."}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Instagram 경고 */}
                  {uploadPlatform === "instagram" && (
                    <div>
                      <p className="text-amber-400/80 text-xs">Instagram은 공개 URL이 필요합니다. PUBLIC_SERVER_URL 또는 ngrok 설정이 필요할 수 있습니다.</p>
                      <p className="text-gray-500 text-xs mt-1">Instagram은 API를 통한 예약 업로드를 지원하지 않습니다.</p>
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
                        업로드 중...
                      </>
                    ) : (
                      <>
                        <Upload className="w-4 h-4" />
                        {scheduleEnabled
                          ? (uploadPlatform === "youtube" ? "YouTube 예약 업로드" : "TikTok 예약 업로드")
                          : (uploadPlatform === "youtube" ? "YouTube 업로드" : uploadPlatform === "tiktok" ? "TikTok 업로드" : "Reels 업로드")
                        }
                      </>
                    )}
                  </button>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 오류 패널 */}
      <AnimatePresence>
        {errorMessage && !isGenerating && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="mt-6 w-full max-w-xl glass-panel p-6 rounded-2xl relative z-10 border border-red-500/30 shadow-2xl shadow-red-500/10"
          >
            <div className="flex items-start gap-3">
              <AlertCircle className="w-6 h-6 text-red-500 shrink-0 mt-0.5" />
              <div className="space-y-2">
                <h3 className="text-lg text-red-400 font-bold">오류 발생</h3>
                <p className="text-gray-300 text-sm whitespace-pre-line">{errorMessage}</p>
                <button
                  onClick={handleClearError}
                  className="mt-2 px-4 py-2 bg-white/10 hover:bg-white/20 text-gray-300 text-sm rounded-xl transition-colors"
                >
                  닫기
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}
