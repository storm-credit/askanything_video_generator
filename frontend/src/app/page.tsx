"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, CheckCircle2, AlertCircle, Settings, Brain, ImageIcon, Square, Globe, Upload, Youtube, X, ExternalLink, Video, Music, Instagram, Send, Tv, Mic, Type, MoveVertical, Zap, Crown, Film } from "lucide-react";
import { API_BASE, KeyStatus, KeyUsageStats } from "../components/types";
import { SettingsModal } from "../components/SettingsModal";
import { ProgressPanel } from "../components/ProgressPanel";

export default function Home() {
  const [topic, setTopic] = useState("");
  const [qualityPreset, setQualityPreset] = useState("best");
  const [llmProvider, setLlmProvider] = useState("gemini");
  const [llmModel, setLlmModel] = useState("");
  const [imageEngine, setImageEngine] = useState("imagen");
  const [imageModel, setImageModel] = useState("");
  const [videoEngine, setVideoEngine] = useState("none");
  const [videoModel, setVideoModel] = useState("");
  const [language, setLanguage] = useState("ko");
  const [cameraStyle, setCameraStyle] = useState("dynamic");
  const [bgmTheme, setBgmTheme] = useState("random");
  const [channel, setChannel] = useState("");
  const [platforms, setPlatforms] = useState<string[]>(["youtube"]);
  const [ttsSpeed, setTtsSpeed] = useState(0.9);
  const [captionSize, setCaptionSize] = useState(48);
  const [captionY, setCaptionY] = useState(28);
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
  // 모델별 잔여 호출 수
  const [modelLimits, setModelLimits] = useState<Record<string, { rpm: number; rpd: number; used: number; total_rpd: number; remaining: number }> | null>(null);
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

  // 미리보기 모드
  const [previewMode, setPreviewMode] = useState(false);
  const [previewData, setPreviewData] = useState<{
    sessionId: string;
    title: string;
    cuts: { index: number; script: string; prompt: string; image_url: string | null }[];
  } | null>(null);
  const [editedScripts, setEditedScripts] = useState<Record<number, string>>({});

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
        setLlmProvider("gemini"); setLlmModel("");
        setImageEngine("imagen"); setImageModel("imagen-4.0-fast-generate-001");
        setVideoEngine("none"); setVideoModel("");
        break;
      case "fast":
        setLlmProvider("gemini"); setLlmModel("gemini-2.5-flash");
        setImageEngine("imagen"); setImageModel("imagen-4.0-fast-generate-001");
        setVideoEngine("none"); setVideoModel("");
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
          llmModel: llmModel || undefined,
          imageModel: imageModel || undefined,
          videoModel: videoModel || undefined,
          language,
          llmKey: llmKeyOverride || undefined,
          outputPath: outputPath.trim() || undefined,
          cameraStyle,
          bgmTheme,
          channel: channel || undefined,
          platforms,
          ttsSpeed,
          captionSize,
          captionY,
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
        const videoPath = rawData.slice(5).trim().replace(/\\/g, '/');
        const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
        const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
        const downloadUrl = `${API_BASE}${normalizedPath}`;
        setGeneratedVideoPath(videoPath);
        const link = document.createElement("a");
        link.href = downloadUrl;
        link.setAttribute("download", videoPath.split('/').pop() || "AskAnything_Shorts.mp4");
        document.body.appendChild(link);
        link.click();
        link.parentNode?.removeChild(link);
        setSuccessMessage("비디오 생성 성공!");
        setIsGenerating(false);
        setPreviewData(null);
        checkPlatformStatus();
      } else if (rawData.startsWith("PREVIEW|")) {
        onPreview?.(rawData.slice(8));
      } else if (rawData.startsWith("ERROR|")) {
        setLogs(prev => [...prev.slice(-99), `ERROR:${rawData.slice(6)}`]);
        setErrorMessage(rawData.slice(6));
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

  const handlePrepare = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;

    setIsGenerating(true);
    setProgress(0);
    setSuccessMessage(null);
    setErrorMessage(null);
    setLogs([]);
    setPreviewData(null);
    setEditedScripts({});

    try {
      const response = await fetch(`${API_BASE}/api/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          apiKey: pickKey("openai") || undefined,
          llmProvider,
          llmKey: llmProvider === "gemini" ? pickKey("gemini") : llmProvider === "claude" ? pickKey("claude_key") : undefined,
          imageEngine,
          language,
          channel: channel || undefined,
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
    } catch (error) {
      console.error(error);
      setErrorMessage("[연결 실패] 백엔드 서버에 연결할 수 없습니다.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleRender = async () => {
    if (!previewData) return;

    setIsGenerating(true);
    setProgress(0);
    setLogs([]);
    setErrorMessage(null);
    setSuccessMessage(null);

    const updatedCuts = previewData.cuts.map((cut) => ({
      index: cut.index,
      script: editedScripts[cut.index] ?? cut.script,
    }));

    try {
      const response = await fetch(`${API_BASE}/api/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId: previewData.sessionId,
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
    } catch (error) {
      console.error(error);
      setErrorMessage("[연결 실패] 렌더 서버에 연결할 수 없습니다.");
    } finally {
      setIsGenerating(false);
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
              <div className="absolute right-2 flex gap-1">
                <button
                  type="button"
                  onClick={handlePrepare}
                  disabled={!topic.trim()}
                  className="bg-indigo-600 text-white hover:bg-indigo-500 disabled:bg-gray-700 disabled:text-gray-400 font-semibold px-4 py-3 rounded-xl transition-colors text-sm"
                >
                  미리보기
                </button>
                <button
                  type="submit"
                  disabled={!topic.trim()}
                  className="bg-white text-black hover:bg-gray-200 disabled:bg-gray-700 disabled:text-gray-400 font-semibold px-4 py-3 rounded-xl transition-colors text-sm"
                >
                  바로생성
                </button>
              </div>
            )}
          </div>

          {/* Row 1: 엔진 선택 (언어 + LLM + 이미지 + 카메라) */}
          <div className="flex items-center justify-center gap-3">
            <div className="flex items-center gap-1.5">
              <Globe className="w-3.5 h-3.5 text-gray-500 shrink-0" />
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

            <div className="flex items-center gap-1.5">
              <Crown className="w-3.5 h-3.5 text-gray-500 shrink-0" />
              <select
                value={qualityPreset}
                onChange={(e) => applyPreset(e.target.value)}
                disabled={isGenerating}
                aria-label="품질 모드 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="best" className="bg-gray-900">최고 품질</option>
                <option value="balanced" className="bg-gray-900">합리적</option>
                <option value="fast" className="bg-gray-900">빠른 생성</option>
              </select>
            </div>

            <div className="flex items-center gap-1.5">
              <Brain className="w-3.5 h-3.5 text-gray-500 shrink-0" />
              <select
                value={llmProvider}
                onChange={(e) => { setLlmProvider(e.target.value); setLlmModel(""); setQualityPreset("custom"); }}
                disabled={isGenerating}
                aria-label="LLM 기획 엔진 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="gemini" className="bg-gray-900">Gemini</option>
                <option value="openai" className="bg-gray-900">GPT</option>
                <option value="claude" className="bg-gray-900">Claude</option>
              </select>
              {LLM_MODELS[llmProvider]?.length > 1 && (
                <select
                  value={llmModel}
                  onChange={(e) => { setLlmModel(e.target.value); setQualityPreset("custom"); }}
                  disabled={isGenerating}
                  aria-label="LLM 모델 버전 선택"
                  className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
                >
                  {LLM_MODELS[llmProvider].map((m) => (
                    <option key={m.value} value={m.value} className="bg-gray-900">{m.label}</option>
                  ))}
                </select>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              <ImageIcon className="w-3.5 h-3.5 text-gray-500 shrink-0" />
              <select
                value={imageEngine}
                onChange={(e) => { setImageEngine(e.target.value); setImageModel(""); setQualityPreset("custom"); }}
                disabled={isGenerating}
                aria-label="이미지 엔진 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="imagen" className="bg-gray-900">Imagen</option>
                <option value="dalle" className="bg-gray-900">DALL-E</option>
              </select>
              {IMAGE_MODELS[imageEngine]?.length > 1 && (
                <select
                  value={imageModel}
                  onChange={(e) => { setImageModel(e.target.value); setQualityPreset("custom"); }}
                  disabled={isGenerating}
                  aria-label="이미지 모델 버전 선택"
                  className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
                >
                  {IMAGE_MODELS[imageEngine].map((m) => (
                    <option key={m.value} value={m.value} className="bg-gray-900">{m.label}</option>
                  ))}
                </select>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              <Film className="w-3.5 h-3.5 text-gray-500 shrink-0" />
              <select
                value={videoEngine}
                onChange={(e) => { setVideoEngine(e.target.value); setVideoModel(""); setQualityPreset("custom"); }}
                disabled={isGenerating}
                aria-label="비디오 엔진 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="veo3" className="bg-gray-900">Veo 3</option>
                <option value="sora2" className="bg-gray-900">Sora 2</option>
                <option value="kling" className="bg-gray-900">Kling</option>
                <option value="none" className="bg-gray-900">없음</option>
              </select>
              {VIDEO_MODELS[videoEngine]?.length > 1 && (
                <select
                  value={videoModel}
                  onChange={(e) => { setVideoModel(e.target.value); setQualityPreset("custom"); }}
                  disabled={isGenerating}
                  aria-label="비디오 모델 버전 선택"
                  className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
                >
                  {VIDEO_MODELS[videoEngine].map((m) => (
                    <option key={m.value} value={m.value} className="bg-gray-900">{m.label}</option>
                  ))}
                </select>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              <Video className="w-3.5 h-3.5 text-gray-500 shrink-0" />
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
          </div>

          {/* Row 2: 설정 (BGM + 채널 | 슬라이더) */}
          <div className="flex items-center justify-center gap-3">
            <div className="flex items-center gap-1.5">
              <Music className="w-3.5 h-3.5 text-gray-500 shrink-0" />
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

            <div className="flex items-center gap-1.5">
              <Tv className="w-3.5 h-3.5 text-gray-500 shrink-0" />
              <select
                value={channel}
                onChange={(e) => {
                  const ch = e.target.value;
                  setChannel(ch);
                  const presets: Record<string, { language: string; ttsSpeed: number; platforms: string[]; captionSize: number; captionY: number }> = {
                    askanything: { language: "ko", ttsSpeed: 0.85, platforms: ["youtube"], captionSize: 48, captionY: 28 },
                    wonderdrop: { language: "en", ttsSpeed: 0.9, platforms: ["youtube", "tiktok"], captionSize: 44, captionY: 28 },
                  };
                  if (ch && presets[ch]) {
                    const p = presets[ch];
                    setLanguage(p.language);
                    setTtsSpeed(p.ttsSpeed);
                    setPlatforms(p.platforms);
                    setCaptionSize(p.captionSize);
                    setCaptionY(p.captionY);
                  }
                }}
                disabled={isGenerating}
                aria-label="채널 선택"
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="" className="bg-gray-900">채널 없음</option>
                <option value="askanything" className="bg-gray-900">AskAnything 🇰🇷</option>
                <option value="wonderdrop" className="bg-gray-900">WonderDrop 🇺🇸</option>
              </select>
            </div>

            <div className="w-px h-4 bg-white/10" />

            <div className="flex items-center gap-1.5">
              <Mic className="w-3.5 h-3.5 text-gray-500 shrink-0" />
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
              <span className="text-[10px] text-gray-500 tabular-nums w-7 text-right">{ttsSpeed}x</span>
            </div>

            <div className="flex items-center gap-1.5">
              <Type className="w-3.5 h-3.5 text-gray-500 shrink-0" />
              <input
                type="range"
                min="32"
                max="72"
                step="4"
                value={captionSize}
                onChange={(e) => setCaptionSize(parseInt(e.target.value))}
                disabled={isGenerating}
                className="w-16 h-1 accent-indigo-500 cursor-pointer"
                aria-label="자막 크기"
              />
              <span className="text-[10px] text-gray-500 tabular-nums w-7 text-right">{captionSize}px</span>
            </div>

            <div className="flex items-center gap-1.5">
              <MoveVertical className="w-3.5 h-3.5 text-gray-500 shrink-0" />
              <input
                type="range"
                min="10"
                max="50"
                step="2"
                value={captionY}
                onChange={(e) => setCaptionY(parseInt(e.target.value))}
                disabled={isGenerating}
                className="w-16 h-1 accent-indigo-500 cursor-pointer"
                aria-label="자막 높이"
              />
              <span className="text-[10px] text-gray-500 tabular-nums w-7 text-right">{captionY}%</span>
            </div>
          </div>

          {/* Row 3: 플랫폼 선택 */}
          <div className="flex items-center justify-center gap-4">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">플랫폼</span>
            {[
              { id: "youtube", label: "YouTube", icon: Youtube, color: "text-red-400" },
              { id: "tiktok", label: "TikTok", icon: Send, color: "text-cyan-400" },
              { id: "reels", label: "Reels", icon: Instagram, color: "text-pink-400" },
            ].map(({ id, label, icon: Icon, color }) => (
              <label key={id} className="flex items-center gap-1.5 cursor-pointer select-none">
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
                <Icon className={`w-3.5 h-3.5 ${color}`} />
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

      {/* 미리보기 패널 */}
      <AnimatePresence>
        {previewMode && previewData && !isGenerating && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="mt-8 w-full max-w-2xl glass-panel p-6 rounded-3xl relative z-10 shadow-2xl shadow-indigo-500/20"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white">{previewData.title}</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => { setPreviewMode(false); setPreviewData(null); }}
                  className="px-3 py-1.5 text-xs bg-white/10 hover:bg-white/20 text-gray-300 rounded-lg transition-colors"
                >
                  취소
                </button>
                <button
                  onClick={handleRender}
                  className="px-4 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg transition-colors"
                >
                  확인 — 영상 만들기
                </button>
              </div>
            </div>

            <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
              {previewData.cuts.map((cut) => (
                <div key={cut.index} className="flex gap-3 bg-white/5 rounded-xl p-3">
                  {/* 이미지 미리보기 */}
                  <div className="w-20 h-36 flex-shrink-0 rounded-lg overflow-hidden bg-black/30">
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
                  </div>

                  {/* 스크립트 편집 */}
                  <div className="flex-1 flex flex-col gap-1">
                    <span className="text-[10px] text-gray-500 uppercase">컷 {cut.index + 1}</span>
                    <textarea
                      value={editedScripts[cut.index] ?? cut.script}
                      onChange={(e) => setEditedScripts(prev => ({ ...prev, [cut.index]: e.target.value }))}
                      rows={3}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-500/50"
                    />
                    <span className="text-[10px] text-gray-600 truncate">{cut.prompt}</span>
                  </div>
                </div>
              ))}
            </div>

            <p className="text-[10px] text-gray-500 mt-3 text-center">
              스크립트를 수정한 뒤 &quot;확인&quot;을 누르면 수정된 내용으로 음성 녹음 + 영상 렌더링이 시작됩니다.
            </p>
          </motion.div>
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
