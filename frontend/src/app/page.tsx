"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Loader2, CheckCircle2, Film, AlertCircle, XCircle, Settings, X, Plus, Trash2, Eye, EyeOff, Brain, ImageIcon, BarChart3 } from "lucide-react";

interface KeyStatus {
  openai: boolean;
  elevenlabs: boolean;
  gemini: boolean;
  claude_key: boolean;
  higgsfield_key: boolean;
  higgsfield_account: boolean;
  kling_access: boolean;
  kling_secret: boolean;
}

interface KeyConfig {
  id: string;
  label: string;
  description: string;
  envName: string;
  statusKey: keyof KeyStatus;
  required: boolean;
  multiKey: boolean;
}

const KEY_CONFIGS: KeyConfig[] = [
  {
    id: "openai",
    label: "OpenAI API Key",
    description: "GPT 기획, DALL-E 이미지, Whisper 자막, Sora 2 비디오에 사용",
    envName: "OPENAI_API_KEY",
    statusKey: "openai",
    required: true,
    multiKey: true,
  },
  {
    id: "elevenlabs",
    label: "ElevenLabs API Key",
    description: "TTS 음성 내레이션 생성에 사용",
    envName: "ELEVENLABS_API_KEY",
    statusKey: "elevenlabs",
    required: true,
    multiKey: true,
  },
  {
    id: "gemini",
    label: "Gemini API Key",
    description: "Gemini 기획 엔진에 사용 (Google AI Studio에서 발급)",
    envName: "GEMINI_API_KEY",
    statusKey: "gemini",
    required: false,
    multiKey: false,
  },
  {
    id: "claude_key",
    label: "Claude API Key",
    description: "Claude 기획 엔진에 사용 (Anthropic Console에서 발급)",
    envName: "ANTHROPIC_API_KEY",
    statusKey: "claude_key",
    required: false,
    multiKey: false,
  },
  {
    id: "higgsfield_key",
    label: "Higgsfield API Key",
    description: "Kling, Veo3, Hailuo, Wan 비디오 엔진에 사용",
    envName: "HIGGSFIELD_API_KEY",
    statusKey: "higgsfield_key",
    required: false,
    multiKey: false,
  },
  {
    id: "higgsfield_account",
    label: "Higgsfield Account ID",
    description: "Higgsfield 엔진 계정 식별자",
    envName: "HIGGSFIELD_ACCOUNT_ID",
    statusKey: "higgsfield_account",
    required: false,
    multiKey: false,
  },
  {
    id: "kling_access",
    label: "Kling Access Key",
    description: "Kling AI 직접 연동 (Higgsfield 실패 시 폴백)",
    envName: "KLING_ACCESS_KEY",
    statusKey: "kling_access",
    required: false,
    multiKey: false,
  },
  {
    id: "kling_secret",
    label: "Kling Secret Key",
    description: "Kling AI 시크릿 키",
    envName: "KLING_SECRET_KEY",
    statusKey: "kling_secret",
    required: false,
    multiKey: false,
  },
];

export default function Home() {
  const [topic, setTopic] = useState("");
  const [llmProvider, setLlmProvider] = useState("gemini");
  const [imageEngine, setImageEngine] = useState("imagen");
  const [videoEngine, setVideoEngine] = useState("veo3");
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // 설정 모달
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [serverKeyStatus, setServerKeyStatus] = useState<KeyStatus | null>(null);

  // 멀티키 저장소: { openai: ["sk-..."], elevenlabs: ["sk_..."], ... }
  const [savedKeys, setSavedKeys] = useState<Record<string, string[]>>({});
  // 입력 중인 키 값
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  // 비밀번호 표시 토글
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  // 저장 경로 설정
  const [outputPath, setOutputPath] = useState("");
  // 키 사용량 통계
  const [keyUsageStats, setKeyUsageStats] = useState<{total_keys: number; keys: {key: string; usage: Record<string, number>; total: number; state: string; blocked: boolean; blocked_services: Record<string, number>; unblock_hours: number}[]} | null>(null);

  const fetchKeyStatus = useCallback(async () => {
    try {
      const res = await fetch("http://localhost:8000/api/health");
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

  const fetchKeyUsage = useCallback(async () => {
    try {
      const res = await fetch("http://localhost:8000/api/key-usage");
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
    setVideoUrl(null);
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

    try {
      const response = await fetch("http://localhost:8000/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          apiKey: selectedOpenaiKey || undefined,
          elevenlabsKey: selectedElevenlabsKey || undefined,
          videoEngine,
          imageEngine,
          llmProvider,
          llmKey: llmKeyOverride || undefined,
          outputPath: outputPath.trim() || undefined,
        }),
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("data:")) {
            const rawData = line.slice(5).trim();
            if (!rawData) continue;

            if (rawData.startsWith("DONE|")) {
               const videoPath = rawData.slice(5).trim().replace(/\\/g, '/');
               const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
               const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
               const downloadUrl = `http://localhost:8000${normalizedPath}`;

               const link = document.createElement("a");
               link.href = downloadUrl;
               const fileName = videoPath.split('/').pop() || "AskAnything_Shorts.mp4";
               link.setAttribute("download", fileName);
               document.body.appendChild(link);
               link.click();
               link.parentNode?.removeChild(link);

               setVideoUrl("비디오 생성 성공! 영상이 안전하게 다운로드되었습니다.");
               setIsGenerating(false);
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
          }
        }
      }
    } catch (error) {
      console.error(error);
      const message = error instanceof Error ? error.message : "Unknown error";
      const userMsg = message === "Failed to fetch"
        ? "[연결 실패] 백엔드 서버(localhost:8000)에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요."
        : `[네트워크 오류] ${message}`;
      setLogs(prev => [...prev.slice(-99), `ERROR:${userMsg}`]);
      setErrorMessage(userMsg);
    } finally {
      setIsGenerating(false);
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
      >
        <Settings className="w-5 h-5" />
      </button>

      {/* 설정 모달 */}
      <AnimatePresence>
        {isSettingsOpen && (
          <>
            {/* 오버레이 */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setIsSettingsOpen(false)}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[60]"
            />
            {/* 모달 */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className="fixed inset-4 sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:w-[560px] sm:max-h-[85vh] z-[70] bg-gray-900/95 border border-white/10 rounded-3xl shadow-2xl overflow-hidden flex flex-col"
            >
              {/* 모달 헤더 */}
              <div className="flex items-center justify-between px-6 py-5 border-b border-white/10">
                <div>
                  <h2 className="text-lg font-bold text-white">API 키 설정</h2>
                  <p className="text-xs text-gray-500 mt-1">.env에 설정된 키는 자동 사용됩니다. 브라우저에서 추가 키를 등록하면 로테이션됩니다.</p>
                </div>
                <button
                  onClick={() => setIsSettingsOpen(false)}
                  className="w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* 모달 바디 */}
              <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 custom-scrollbar">
                {/* 필수 키 */}
                <div>
                  <h3 className="text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-3">필수 키</h3>
                  {KEY_CONFIGS.filter((c) => c.required).map((config) => (
                    <KeySection
                      key={config.id}
                      config={config}
                      serverStatus={serverKeyStatus?.[config.statusKey] ?? null}
                      savedKeys={savedKeys[config.id] || []}
                      inputValue={inputValues[config.id] || ""}
                      isVisible={visibleKeys[config.id] || false}
                      onInputChange={(v) => setInputValues((prev) => ({ ...prev, [config.id]: v }))}
                      onAdd={() => addKey(config.id)}
                      onRemove={(idx) => removeKey(config.id, idx)}
                      onToggleVisible={() => setVisibleKeys((prev) => ({ ...prev, [config.id]: !prev[config.id] }))}
                    />
                  ))}
                </div>

                {/* 기획 엔진 키 (Gemini / Claude) */}
                <div>
                  <h3 className="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-3">기획 엔진 키 (LLM)</h3>
                  {KEY_CONFIGS.filter((c) => ["gemini", "claude_key"].includes(c.id)).map((config) => (
                    <KeySection
                      key={config.id}
                      config={config}
                      serverStatus={serverKeyStatus?.[config.statusKey] ?? null}
                      savedKeys={savedKeys[config.id] || []}
                      inputValue={inputValues[config.id] || ""}
                      isVisible={visibleKeys[config.id] || false}
                      onInputChange={(v) => setInputValues((prev) => ({ ...prev, [config.id]: v }))}
                      onAdd={() => addKey(config.id)}
                      onRemove={(idx) => removeKey(config.id, idx)}
                      onToggleVisible={() => setVisibleKeys((prev) => ({ ...prev, [config.id]: !prev[config.id] }))}
                    />
                  ))}
                </div>

                {/* 선택 키 (비디오 엔진) */}
                <div>
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">비디오 엔진 키 (선택)</h3>
                  {KEY_CONFIGS.filter((c) => !c.required && !["gemini", "claude_key"].includes(c.id)).map((config) => (
                    <KeySection
                      key={config.id}
                      config={config}
                      serverStatus={serverKeyStatus?.[config.statusKey] ?? null}
                      savedKeys={savedKeys[config.id] || []}
                      inputValue={inputValues[config.id] || ""}
                      isVisible={visibleKeys[config.id] || false}
                      onInputChange={(v) => setInputValues((prev) => ({ ...prev, [config.id]: v }))}
                      onAdd={() => addKey(config.id)}
                      onRemove={(idx) => removeKey(config.id, idx)}
                      onToggleVisible={() => setVisibleKeys((prev) => ({ ...prev, [config.id]: !prev[config.id] }))}
                    />
                  ))}
                </div>

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
                      onChange={(e) => setOutputPath(e.target.value)}
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
                      {keyUsageStats.keys.map((k, idx) => {
                        const stateStyle = k.state === "blocked"
                          ? "bg-red-500/5 border border-red-500/20"
                          : k.state === "warning"
                            ? "bg-amber-500/5 border border-amber-500/20"
                            : "bg-white/[0.02]";
                        const keyColor = k.state === "blocked" ? "text-red-400" : k.state === "warning" ? "text-amber-400" : "text-gray-400";
                        const totalColor = k.state === "blocked" ? "text-red-400" : k.state === "warning" ? "text-amber-400" : "text-white";
                        return (
                          <div key={idx} className={`flex items-center gap-2 px-3 py-2 rounded-lg ${stateStyle}`}>
                            <div className="flex items-center gap-1.5 w-32 shrink-0">
                              <div className={`w-2 h-2 rounded-full shrink-0 ${k.state === "blocked" ? "bg-red-500" : k.state === "warning" ? "bg-amber-500" : "bg-green-500"}`} />
                              <span className={`text-xs font-mono ${keyColor}`}>{k.key}</span>
                            </div>
                            <div className="flex-1 flex items-center gap-1.5 flex-wrap">
                              {Object.entries(k.blocked_services || {}).map(([svc, hours]) => (
                                <span key={svc} className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 font-medium">
                                  {svc} 🚫 {hours}h
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
              </div>

              {/* 모달 푸터 */}
              <div className="px-6 py-4 border-t border-white/10 flex items-center justify-between">
                <p className="text-xs text-gray-600">
                  서버 키 {totalServerKeys}개 | 브라우저 키 {totalSavedKeys}개
                </p>
                <button
                  onClick={() => setIsSettingsOpen(false)}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-xl transition-colors"
                >
                  완료
                </button>
              </div>
            </motion.div>
          </>
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
            <button
              type="submit"
              disabled={isGenerating || !topic.trim()}
              className="absolute right-2 bg-white text-black hover:bg-gray-200 disabled:bg-gray-700 disabled:text-gray-400 font-semibold px-6 py-3 rounded-xl transition-colors flex items-center gap-2"
            >
              {isGenerating ? <Loader2 className="w-5 h-5 animate-spin" /> : "생성하기"}
            </button>
          </div>

          {/* 엔진 선택 (LLM + 이미지 + 비디오) */}
          <div className="flex items-center justify-center gap-2 flex-wrap">
            {/* LLM 기획 엔진 */}
            <div className="flex items-center gap-1">
              <Brain className="w-3.5 h-3.5 text-gray-500" />
              <select
                value={llmProvider}
                onChange={(e) => setLlmProvider(e.target.value)}
                disabled={isGenerating}
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
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="imagen" className="bg-gray-900">Imagen 4 (Google)</option>
                <option value="dalle" className="bg-gray-900">DALL-E 3 (OpenAI)</option>
              </select>
            </div>

            {/* 비디오 엔진 */}
            <div className="flex items-center gap-1">
              <Film className="w-3.5 h-3.5 text-gray-500" />
              <select
                value={videoEngine}
                onChange={(e) => setVideoEngine(e.target.value)}
                disabled={isGenerating}
                className="bg-white/5 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
              >
                <option value="veo3" className="bg-gray-900">Veo 3 (Google)</option>
                <option value="kling" className="bg-gray-900">Kling 3.0</option>
                <option value="sora2" className="bg-gray-900">Sora 2</option>
                <option value="hailuo" className="bg-gray-900">Hailuo 2.3</option>
                <option value="wan" className="bg-gray-900">Wan 2.5</option>
                <option value="none" className="bg-gray-900">없음</option>
              </select>
            </div>
          </div>
        </form>
      </motion.div>

      <AnimatePresence>
        {(isGenerating || errorMessage) && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="mt-16 w-full max-w-xl space-y-4 z-10"
          >
            {/* 진행률 상태바 */}
            <div className="glass-panel p-4 rounded-2xl">
               <div className="flex justify-between items-center mb-2 text-sm font-medium">
                  <span className="text-gray-300">생성 진행률</span>
                  <span className="text-indigo-400 font-bold">{progress}%</span>
               </div>
               <div className="w-full bg-white/10 rounded-full h-3 overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                    transition={{ ease: "easeInOut", duration: 0.5 }}
                    className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full"
                  />
               </div>
            </div>

            {/* 실시간 로그 패널 */}
            <div className="glass-panel p-6 rounded-2xl space-y-3 max-h-48 overflow-y-auto custom-scrollbar">
              {logs.length === 0 ? (
                 <div className="flex items-center text-indigo-400 gap-3">
                    <Loader2 className="w-4 h-4 animate-spin"/> 서버 응답 대기 중...
                 </div>
              ) : (
                 logs.map((log, idx) => {
                    const isError = log.startsWith("ERROR:");
                    const isWarn = log.startsWith("WARN:");
                    const displayText = isError ? log.slice(6) : isWarn ? log.slice(5) : log;
                    const isLast = idx === logs.length - 1;
                    return (
                      <motion.div
                         key={idx}
                         initial={{ opacity: 0, x: -10 }}
                         animate={{ opacity: 1, x: 0 }}
                         className={`flex items-start text-sm ${
                           isError ? 'text-red-400 font-medium' :
                           isWarn ? 'text-amber-400 font-medium' :
                           isLast ? 'text-indigo-400 font-medium' : 'text-gray-500'
                         }`}
                      >
                         {isError ? <XCircle className="w-4 h-4 mr-2 text-red-500 shrink-0"/> :
                          isWarn ? <AlertCircle className="w-4 h-4 mr-2 text-amber-500 shrink-0"/> :
                          isLast ? <Loader2 className="w-4 h-4 mr-2 animate-spin shrink-0"/> :
                          <CheckCircle2 className="w-4 h-4 mr-2 text-green-500 shrink-0"/>}
                         <span className="break-all">{displayText}</span>
                      </motion.div>
                    );
                 })
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {videoUrl && !isGenerating && !errorMessage && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="mt-16 w-full max-w-sm glass-panel p-6 rounded-[2.5rem] relative z-10 flex flex-col justify-center items-center shadow-2xl shadow-indigo-500/20 text-center space-y-4"
          >
            <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto" />
            <h3 className="text-xl text-white font-bold">생성 성공!</h3>
            <p className="text-gray-400 text-sm">최고 수준의 숏폼 비디오가 성공적으로 기기 다운로드 폴더에 저장되었습니다.</p>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {errorMessage && !isGenerating && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="mt-6 w-full max-w-xl glass-panel p-6 rounded-2xl relative z-10 border border-red-500/30 shadow-2xl shadow-red-500/10"
          >
            <div className="flex items-start gap-3">
              <AlertCircle className="w-6 h-6 text-red-500 shrink-0 mt-0.5" />
              <div className="space-y-2">
                <h3 className="text-lg text-red-400 font-bold">오류 발생</h3>
                <p className="text-gray-300 text-sm">{errorMessage}</p>
                <button
                  onClick={() => { setErrorMessage(null); setLogs([]); }}
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

/* ─── 키 섹션 컴포넌트 ─── */
function KeySection({
  config,
  serverStatus,
  savedKeys,
  inputValue,
  isVisible,
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
  onInputChange: (v: string) => void;
  onAdd: () => void;
  onRemove: (idx: number) => void;
  onToggleVisible: () => void;
}) {
  const maskKey = (key: string) => {
    if (key.length <= 8) return "****";
    return key.slice(0, 4) + "..." + key.slice(-4);
  };

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
        {/* 서버 상태 표시 */}
        <div className="flex items-center gap-1.5 shrink-0 ml-3">
          <div className={`w-2 h-2 rounded-full ${serverStatus === true ? "bg-green-500" : serverStatus === false ? "bg-gray-600" : "bg-gray-700 animate-pulse"}`} />
          <span className="text-[10px] text-gray-500">
            {serverStatus === true ? ".env 설정됨" : serverStatus === false ? "미설정" : "확인 중"}
          </span>
        </div>
      </div>

      {/* 저장된 키 목록 */}
      {savedKeys.length > 0 && (
        <div className="space-y-1.5 mb-2">
          {savedKeys.map((key, idx) => (
            <div key={idx} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <div className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
              <span className="text-xs text-blue-300 font-mono flex-1">
                {isVisible ? key : maskKey(key)}
              </span>
              <button onClick={onToggleVisible} className="text-gray-500 hover:text-gray-300 transition-colors">
                {isVisible ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
              </button>
              <button onClick={() => onRemove(idx)} className="text-gray-500 hover:text-red-400 transition-colors">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 키 입력 */}
      <div className="flex items-center gap-2">
        <input
          type="password"
          value={inputValue}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onAdd()}
          placeholder={`${config.envName} 입력...`}
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
