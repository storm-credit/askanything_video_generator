"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Loader2, CheckCircle2, KeyRound, Film, AlertCircle, XCircle } from "lucide-react";

export default function Home() {
  const [topic, setTopic] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [isKeySaved, setIsKeySaved] = useState(false);
  const [videoEngine, setVideoEngine] = useState("kling");
  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleKeySave = () => {
    if (apiKey.trim().length > 0) {
      setIsKeySaved(true);
    }
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;
    
    setIsGenerating(true);
    setProgress(0);
    setVideoUrl(null);
    setErrorMessage(null);
    setLogs([]);

    try {
      const response = await fetch("http://localhost:8000/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, apiKey: apiKey.trim(), videoEngine }),
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
               
               // 브라우저 404 방지 및 네이티브 다운로드를 위해 Blob으로 처리
               try {
                 const vidRes = await fetch(downloadUrl);
                 if (!vidRes.ok) throw new Error("Video not found");
                 const blob = await vidRes.blob();
                 const url = window.URL.createObjectURL(blob);
                 const link = document.createElement("a");
                 link.href = url;
                 link.setAttribute("download", "AskAnything_Shorts.mp4");
                 document.body.appendChild(link);
                 link.click();
                 link.parentNode?.removeChild(link);
                 window.URL.revokeObjectURL(url);
               } catch (e) {
                 console.error("Download failed, using fallback:", e);
                 // Fallback
                 const link = document.createElement("a");
                 link.href = downloadUrl;
                 link.setAttribute("download", "AskAnything_Shorts.mp4");
                 document.body.appendChild(link);
                 link.click();
                 link.parentNode?.removeChild(link);
               }

               setVideoUrl("비디오 생성 성공! 영상이 안전하게 다운로드되었습니다.");
               setIsGenerating(false);
            } else if (rawData.startsWith("ERROR|")) {
               const errMsg = rawData.slice(6);
               setLogs(prev => [...prev, `ERROR:${errMsg}`]);
               setErrorMessage(errMsg);
               setIsGenerating(false);
            } else if (rawData.startsWith("PROG|")) {
               const p = parseInt(rawData.slice(5), 10);
               if (!isNaN(p)) setProgress(p);
            } else {
               setLogs(prev => [...prev, rawData]);
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
      setLogs(prev => [...prev, `ERROR:${userMsg}`]);
      setErrorMessage(userMsg);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <main className="min-h-screen relative flex flex-col items-center justify-center p-6 sm:p-24 bg-black overflow-hidden">
      
      {/* 우측 상단 API Key 세팅 패널 (Apple Style 미니멀리즘) */}
      <div className="absolute top-6 right-6 z-50">
        <div 
          className={`flex items-center gap-2 p-1.5 rounded-full border transition-all duration-500 ease-[cubic-bezier(0.23,1,0.32,1)] backdrop-blur-md 
          ${isKeySaved 
            ? 'border-green-500/40 bg-green-500/10 w-[44px] cursor-pointer hover:bg-green-500/20 hover:scale-105' 
            : 'border-white/10 bg-white/5 w-64 shadow-2xl'}`}
          onClick={() => {
            if (isKeySaved) setIsKeySaved(false);
          }}
          title={isKeySaved ? "API Key Saved. Click to edit." : ""}
        >
          {isKeySaved ? (
            <div className="w-full h-[32px] flex items-center justify-center text-green-400">
              <KeyRound className="w-4 h-4" />
            </div>
          ) : (
            <>
              <div className="pl-3 text-gray-400 flex-shrink-0">
                <KeyRound className="w-4 h-4" />
              </div>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                onBlur={handleKeySave}
                onKeyDown={(e) => e.key === 'Enter' && handleKeySave()}
                placeholder="OpenAI API Key"
                autoFocus
                className="bg-transparent border-none text-white text-sm focus:outline-none w-full placeholder-gray-500"
              />
            </>
          )}
        </div>
      </div>

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

          {/* 비디오 엔진 선택 */}
          <div className="flex items-center justify-center gap-2">
            <Film className="w-4 h-4 text-gray-500" />
            <select
              value={videoEngine}
              onChange={(e) => setVideoEngine(e.target.value)}
              disabled={isGenerating}
              className="bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 backdrop-blur-md appearance-none cursor-pointer"
            >
              <option value="kling" className="bg-gray-900">Kling 3.0 - 시네마틱 모션 (기본)</option>
              <option value="sora2" className="bg-gray-900">Sora 2 - 최고 품질 (OpenAI)</option>
              <option value="veo3" className="bg-gray-900">Veo 3.1 - 4K 시네마틱 (Google)</option>
              <option value="hailuo" className="bg-gray-900">Hailuo 2.3 - 가성비 (Minimax)</option>
              <option value="wan" className="bg-gray-900">Wan 2.5 - 빠른 생성 (Alibaba)</option>
              <option value="none" className="bg-gray-900">비디오 없음 - 정지 이미지만</option>
            </select>
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
            {/* 진행률 상태바 (Apple Style) */}
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
                    const displayText = isError ? log.slice(6) : log;
                    const isLast = idx === logs.length - 1;
                    return (
                      <motion.div
                         key={idx}
                         initial={{ opacity: 0, x: -10 }}
                         animate={{ opacity: 1, x: 0 }}
                         className={`flex items-start text-sm ${
                           isError ? 'text-red-400 font-medium' :
                           isLast ? 'text-indigo-400 font-medium' : 'text-gray-500'
                         }`}
                      >
                         {isError ? <XCircle className="w-4 h-4 mr-2 text-red-500 shrink-0"/> :
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
