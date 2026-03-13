"use client";

import { useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { Loader2, CheckCircle2, AlertCircle, XCircle } from "lucide-react";

interface ProgressPanelProps {
  progress: number;
  logs: string[];
}

export function ProgressPanel({ progress, logs }: ProgressPanelProps) {
  const logsEndRef = useRef<HTMLDivElement>(null);

  // 로그 추가 시 자동 스크롤
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  return (
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
              <div
                key={idx}
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
              </div>
            );
          })
        )}
        <div ref={logsEndRef} />
      </div>
    </motion.div>
  );
}
