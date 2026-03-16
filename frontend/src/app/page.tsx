"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, CheckCircle2, AlertCircle, Settings, Brain, ImageIcon, Square, Globe, Upload, Youtube, X, ExternalLink, Video, Music, Instagram, Send, Tv, Mic } from "lucide-react";
import { API_BASE, KeyStatus, KeyUsageStats } from "../components/types";
import { SettingsModal } from "../components/SettingsModal";
import { ProgressPanel } from "../components/ProgressPanel";

export default function Home() {
  const [topic, setTopic] = useState("");
  const [llmProvider, setLlmProvider] = useState("gemini");
  const [imageEngine, setImageEngine] = useState("imagen");
  const [videoEngine, setVideoEngine] = useState("none");
  const [language, setLanguage] = useState("ko");
  const [cameraStyle, setCameraStyle] = useState("dynamic");
  const [bgmTheme, setBgmTheme] = useState("random");
  const [channel, setChannel] = useState("");
  const [platforms, setPlatforms] = useState<string[]>(["youtube"]);
  const [ttsSpeed, setTtsSpeed] = useState(0.9);
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // 설정 모달
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [serverKeyStatus, setServerKeyStatus] = useState<KeyStatus | null>(null);

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
  // 업로드 (멀티 플랫폼)
  const [generatedVideoPath, setGeneratedVideoPath] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadPlatform, setUploadPlatform] = useState<"youtube" | "tiktok" | "instagram">("youtube");
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadDescription, setUploadDescription] = useState("");
  const [uploadTags, setUploadTags] = useState("");
  const [uploadPrivacy, setUploadPrivacy] = useState("private");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ success: boolean; url?: string; error?: string } | null>(null);
  // YouTube
  const [ytConnected, setYtConnected] = useState(false);
  const [ytChannels, setYtChannels] = useState<{ id: string; title: string; connected: boolean }[]>([]);
  const [ytSelectedChannel, setYtSelectedChannel] = useState<string>("");
  // TikTok
  const [ttConnected, setTtConnected] = useState(false);
  const [ttPrivacy, setTtPrivacy] = useState("SELF_ONLY");
  // Instagram
  const [igConnected, setIgConnected] = useState(false);

  // AbortController (생성 취소용)
  const abortControllerRef = useRef<AbortController | null>(null);
  const cancelledRef = useRef(false);

  const fetchKeyStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      if (res.ok) {
        const data = await res.json();
        setServerKeyStatus(data.keys || null);
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

  // 모달 열릴 때마다 최신 서버 상태 조회
  useEffect(() => {
    if (isSettingsOpen) {
      fetchKeyStatus();
      fetchKeyUsage();
    }
  }, [isSettingsOpen, fetchKeyStatus, fetchKeyUsage]);

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
  const pickKey = (configId: string): string | undefined => {
    const keys = savedKeys[configId];
    if (!keys || keys.length === 0) return undefined;
    return keys[Math.floor(Math.random() * keys.length)];
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;

    setIsGenerating(true);
    setProgress(0);
    setSuccessMessage(null);
    setErrorMessage(null);
    setLogs([]);

    const selectedOpenaiKey = pickKey("openai");
    const selectedElevenlabsKey = pickKey("elevenlabs");

    // LLM 프로바이더별 키 선택
    let llmKeyOverride: string | undefined;
    if (llmProvider === "gemini") {
      llmKeyOverride = pickKey("gemini");
    } else if (llmProvider === "claude") {
      llmKeyOverride = pickKey("claude_key");
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    cancelledRef.current = false;

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
          language,
          llmKey: llmKeyOverride || undefined,
          outputPath: outputPath.trim() || undefined,
          cameraStyle,
          bgmTheme,
          channel: channel || undefined,
          platforms,
          ttsSpeed,
        }),
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";  // chunk 경계에서 잘린 메시지 버퍼

      const processLine = (line: string) => {
        if (!line.startsWith("data:")) return;
        const rawData = line.slice(5).trim();
        if (!rawData) return;

        if (rawData.startsWith("DONE|")) {
          const videoPath = rawData.slice(5).trim().replace(/\\/g, '/');
          const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
          const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
          const downloadUrl = `${API_BASE}${normalizedPath}`;

          // YouTube 업로드용 경로 저장
          setGeneratedVideoPath(videoPath);

          const link = document.createElement("a");
          link.href = downloadUrl;
          const fileName = videoPath.split('/').pop() || "AskAnything_Shorts.mp4";
          link.setAttribute("download", fileName);
          document.body.appendChild(link);
          link.click();
          link.parentNode?.removeChild(link);

          setSuccessMessage("비디오 생성 성공! 영상이 안전하게 다운로드되었습니다.");
          setIsGenerating(false);
          // YouTube 상태 확인
          checkPlatformStatus();
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
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancel = () => {
    cancelledRef.current = true;
    abortControllerRef.current?.abort();
    setIsGenerating(false);
    // 백엔드에도 취소 요청 (fire-and-forget)
    fetch(`${API_BASE}/api/cancel`, { method: "POST" }).catch(() => {});
  };

  const handleClearError = () => {
    setErrorMessage(null);
    setLogs([]);
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
      const res = await fetch(`${API_BASE}/api/${platform}/auth`, { method: "POST" });
      const data = await res.json();
      if (data.auth_url) {
        window.open(data.auth_url, `${platform}_auth`, "width=600,height=700");
        const poll = setInterval(async () => {
          const check = await fetch(`${API_BASE}/api/${platform}/status`);
          const status = await check.json();
          if (status.connected) {
            if (platform === "youtube") setYtConnected(true);
            else if (platform === "tiktok") setTtConnected(true);
            else if (platform === "instagram") setIgConnected(true);
            clearInterval(poll);
          }
        }, 2000);
        setTimeout(() => clearInterval(poll), 120000);
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
        body = {
          video_path: generatedVideoPath,
          title: uploadTitle || topic,
          description: uploadDescription,
          tags: uploadTags.split(",").map(t => t.trim()).filter(Boolean),
          privacy: uploadPrivacy,
          channel_id: ytSelectedChannel || undefined,
        };
      } else if (uploadPlatform === "tiktok") {
        endpoint = "/api/tiktok/upload";
        body = {
          video_path: generatedVideoPath,
          title: uploadTitle || topic,
          privacy_level: ttPrivacy,
        };
      } else {
        endpoint = "/api/instagram/upload";
        body = {
          video_path: generatedVideoPath,
          caption: `${uploadTitle || topic}\n\n${uploadDescription}`.trim(),
        };
      }

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success) {
        setUploadResult({ success: true, url: data.url });
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
              onChange={(e) => setTopic(e.target.value)}
              disabled={isGenerating}
              placeholder="예: 블랙홀에 떨어지면 어떻게 될까?"
              className="w-full bg-white/5 border border-white/10 rounded-2xl py-5 pl-6 pr-32 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all text-lg backdrop-blur-md"
            />
            {isGenerating ? (
              <button
                type="button"
                onClick={handleCancel}
                aria-label="생성 취소"
                className="absolute right-2 bg-red-600 text-white hover:bg-red-500 font-semibold px-6 py-3 rounded-xl transition-colors flex items-center gap-2"
              >
                <Square className="w-4 h-4 fill-current" />
                취소
              </button>
            ) : (
              <button
                type="submit"
                disabled={!topic.trim()}
                className="absolute right-2 bg-white text-black hover:bg-gray-200 disabled:bg-gray-700 disabled:text-gray-400 font-semibold px-6 py-3 rounded-xl transition-colors flex items-center gap-2"
              >
                생성하기
              </button>
            )}
          </div>

          {/* 엔진 선택 (언어 + LLM + 이미지) */}
          <div className="flex items-center justify-center gap-2 flex-wrap">
            {/* 언어 선택 */}
            <div className="flex items-center gap-1">
              <Globe className="w-3.5 h-3.5 text-gray-500" />
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                disabled={isGenerating}
                aria-label="언어 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="ko" className="bg-gray-900">한국어</option>
                <option value="en" className="bg-gray-900">English</option>
                <option value="de" className="bg-gray-900">Deutsch</option>
                <option value="da" className="bg-gray-900">Dansk</option>
                <option value="no" className="bg-gray-900">Norsk</option>
                <option value="es" className="bg-gray-900">Español</option>
                <option value="fr" className="bg-gray-900">Français</option>
                <option value="pt" className="bg-gray-900">Português</option>
                <option value="it" className="bg-gray-900">Italiano</option>
                <option value="nl" className="bg-gray-900">Nederlands</option>
                <option value="sv" className="bg-gray-900">Svenska</option>
                <option value="ja" className="bg-gray-900">日本語</option>
                <option value="zh" className="bg-gray-900">中文</option>
                <option value="ar" className="bg-gray-900">العربية</option>
                <option value="ru" className="bg-gray-900">Русский</option>
                <option value="tr" className="bg-gray-900">Türkçe</option>
                <option value="hi" className="bg-gray-900">हिन्दी</option>
              </select>
            </div>

            {/* LLM 기획 엔진 */}
            <div className="flex items-center gap-1">
              <Brain className="w-3.5 h-3.5 text-gray-500" />
              <select
                value={llmProvider}
                onChange={(e) => setLlmProvider(e.target.value)}
                disabled={isGenerating}
                aria-label="LLM 기획 엔진 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="gemini" className="bg-gray-900">Gemini 2.5 Pro</option>
                <option value="openai" className="bg-gray-900">GPT-4o</option>
                <option value="claude" className="bg-gray-900">Claude Sonnet 4</option>
              </select>
            </div>

            {/* 이미지 엔진 */}
            <div className="flex items-center gap-1">
              <ImageIcon className="w-3.5 h-3.5 text-gray-500" />
              <select
                value={imageEngine}
                onChange={(e) => setImageEngine(e.target.value)}
                disabled={isGenerating}
                aria-label="이미지 엔진 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="imagen" className="bg-gray-900">Imagen 4 (Google)</option>
                <option value="dalle" className="bg-gray-900">DALL-E 3 (OpenAI)</option>
              </select>
            </div>

            {/* 카메라 무빙 */}
            <div className="flex items-center gap-1">
              <Video className="w-3.5 h-3.5 text-gray-500" />
              <select
                value={cameraStyle}
                onChange={(e) => setCameraStyle(e.target.value)}
                disabled={isGenerating}
                aria-label="카메라 스타일 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="dynamic" className="bg-gray-900">역동적</option>
                <option value="gentle" className="bg-gray-900">부드러움</option>
                <option value="static" className="bg-gray-900">고정</option>
              </select>
            </div>

            {/* BGM */}
            <div className="flex items-center gap-1">
              <Music className="w-3.5 h-3.5 text-gray-500" />
              <select
                value={bgmTheme}
                onChange={(e) => setBgmTheme(e.target.value)}
                disabled={isGenerating}
                aria-label="BGM 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="random" className="bg-gray-900">BGM 랜덤</option>
                <option value="none" className="bg-gray-900">BGM 없음</option>
              </select>
            </div>

            {/* 채널 (인트로/아웃트로) */}
            <div className="flex items-center gap-1">
              <Tv className="w-3.5 h-3.5 text-gray-500" />
              <select
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
                disabled={isGenerating}
                aria-label="채널 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="" className="bg-gray-900">채널 없음</option>
                <option value="askanything" className="bg-gray-900">Ask Anything</option>
                <option value="wonderdrop" className="bg-gray-900">Wonder Drop</option>
              </select>
            </div>

            {/* TTS 속도 */}
            <div className="flex items-center gap-1">
              <Mic className="w-3.5 h-3.5 text-gray-500" />
              <input
                type="range"
                min="0.7"
                max="1.2"
                step="0.05"
                value={ttsSpeed}
                onChange={(e) => setTtsSpeed(parseFloat(e.target.value))}
                disabled={isGenerating}
                className="w-16 h-1 accent-indigo-500 cursor-pointer"
                aria-label="음성 속도"
              />
              <span className="text-[10px] text-gray-500 w-8">{ttsSpeed}x</span>
            </div>
          </div>

          {/* 플랫폼 선택 */}
          <div className="flex items-center gap-3 mt-2">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">플랫폼</span>
            {[
              { id: "youtube", label: "YouTube", icon: Youtube, color: "text-red-400" },
              { id: "tiktok", label: "TikTok", icon: Send, color: "text-cyan-400" },
              { id: "reels", label: "Reels", icon: Instagram, color: "text-pink-400" },
            ].map(({ id, label, icon: Icon, color }) => (
              <label key={id} className="flex items-center gap-1 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={platforms.includes(id)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setPlatforms((prev) => [...prev, id]);
                    } else {
                      setPlatforms((prev) => prev.filter((p) => p !== id) || ["youtube"]);
                    }
                  }}
                  disabled={isGenerating}
                  className="accent-indigo-500 w-3 h-3"
                />
                <Icon className={`w-3 h-3 ${color}`} />
                <span className="text-xs text-gray-400">{label}</span>
              </label>
            ))}
          </div>
        </form>
      </motion.div>

      {/* 진행률 + 로그 패널 (에러 전용 패널과 중복 방지) */}
      <AnimatePresence>
        {isGenerating && (
          <ProgressPanel progress={progress} logs={logs} />
        )}
      </AnimatePresence>

      {/* 성공 패널 */}
      <AnimatePresence>
        {successMessage && !isGenerating && !errorMessage && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="mt-16 w-full max-w-sm glass-panel p-6 rounded-[2.5rem] relative z-10 flex flex-col justify-center items-center shadow-2xl shadow-indigo-500/20 text-center space-y-4"
          >
            <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto" />
            <h3 className="text-xl text-white font-bold">생성 성공!</h3>
            <p className="text-gray-400 text-sm">최고 수준의 숏폼 비디오가 성공적으로 기기 다운로드 폴더에 저장되었습니다.</p>
            {generatedVideoPath && (
              <div className="flex flex-col gap-2 w-full">
                <button
                  onClick={() => {
                    setUploadTitle(topic);
                    setUploadDescription(`AI가 생성한 숏폼 영상: ${topic}`);
                    setUploadTags(topic);
                    setUploadResult(null);
                    setUploadPlatform("youtube");
                    setShowUploadModal(true);
                    checkPlatformStatus();
                  }}
                  className="flex items-center justify-center gap-2 px-5 py-2.5 bg-red-600 hover:bg-red-500 text-white font-semibold rounded-xl transition-colors w-full"
                >
                  <Youtube className="w-5 h-5" />
                  YouTube Shorts
                </button>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setUploadTitle(topic);
                      setUploadDescription(`AI가 생성한 숏폼 영상: ${topic}`);
                      setUploadResult(null);
                      setUploadPlatform("tiktok");
                      setShowUploadModal(true);
                      checkPlatformStatus();
                    }}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white font-semibold rounded-xl transition-colors text-sm"
                  >
                    <Send className="w-4 h-4" />
                    TikTok
                  </button>
                  <button
                    onClick={() => {
                      setUploadTitle(topic);
                      setUploadDescription(`AI가 생성한 숏폼 영상: ${topic}`);
                      setUploadResult(null);
                      setUploadPlatform("instagram");
                      setShowUploadModal(true);
                      checkPlatformStatus();
                    }}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-pink-500 hover:from-purple-500 hover:to-pink-400 text-white font-semibold rounded-xl transition-colors text-sm"
                  >
                    <Instagram className="w-4 h-4" />
                    Reels
                  </button>
                </div>
              </div>
            )}
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
                <h3 className="text-lg text-white font-bold">업로드</h3>
                <button
                  onClick={() => !uploading && setShowUploadModal(false)}
                  className="text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* 플랫폼 선택 탭 */}
              <div className="flex gap-1 bg-white/5 rounded-xl p-1">
                <button
                  onClick={() => { setUploadPlatform("youtube"); setUploadResult(null); }}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-colors ${uploadPlatform === "youtube" ? "bg-red-600 text-white" : "text-gray-400 hover:text-white"}`}
                >
                  <Youtube className="w-4 h-4" /> YouTube
                </button>
                <button
                  onClick={() => { setUploadPlatform("tiktok"); setUploadResult(null); }}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-colors ${uploadPlatform === "tiktok" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"}`}
                >
                  <Send className="w-4 h-4" /> TikTok
                </button>
                <button
                  onClick={() => { setUploadPlatform("instagram"); setUploadResult(null); }}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-colors ${uploadPlatform === "instagram" ? "bg-gradient-to-r from-purple-600 to-pink-500 text-white" : "text-gray-400 hover:text-white"}`}
                >
                  <Instagram className="w-4 h-4" /> Reels
                </button>
              </div>

              {/* 연동 안 된 경우 */}
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
                  <h4 className="text-white font-bold">업로드 완료!</h4>
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

                  {/* YouTube 채널 선택 */}
                  {uploadPlatform === "youtube" && ytChannels.length > 1 && (
                    <div>
                      <label className="text-gray-400 text-xs mb-1 block">채널 선택</label>
                      <select
                        value={ytSelectedChannel}
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

                  {/* Instagram 경고 */}
                  {uploadPlatform === "instagram" && (
                    <p className="text-amber-400/80 text-xs">Instagram은 공개 URL이 필요합니다. PUBLIC_SERVER_URL 또는 ngrok 설정이 필요할 수 있습니다.</p>
                  )}

                  {uploadResult && !uploadResult.success && (
                    <p className="text-red-400 text-sm">{uploadResult.error}</p>
                  )}

                  <button
                    onClick={handleUpload}
                    disabled={uploading || !uploadTitle.trim()}
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
                        {uploadPlatform === "youtube" ? "YouTube 업로드" : uploadPlatform === "tiktok" ? "TikTok 업로드" : "Reels 업로드"}
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
                <p className="text-gray-300 text-sm">{errorMessage}</p>
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
