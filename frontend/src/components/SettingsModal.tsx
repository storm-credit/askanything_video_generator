"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { X, Plus, Trash2, Eye, EyeOff, BarChart3, Key, Puzzle } from "lucide-react";
import { KeyConfig, KeyStatus, KeyUsageStats, KEY_CONFIGS } from "./types";

interface SettingsModalProps {
  serverKeyStatus: KeyStatus | null;
  savedKeys: Record<string, string[]>;
  inputValues: Record<string, string>;
  visibleKeys: Record<string, boolean>;
  outputPath: string;
  keyUsageStats: KeyUsageStats | null;
  totalServerKeys: number;
  totalSavedKeys: number;
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
  onClose,
  onInputChange,
  onAddKey,
  onRemoveKey,
  onToggleVisible,
  onOutputPathChange,
}: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<"core" | "extra">("core");

  // Escape 키로 모달 닫기
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const coreConfigs = KEY_CONFIGS.filter((c) => c.group === "core");
  const extraConfigs = KEY_CONFIGS.filter((c) => c.group === "extra");

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
        aria-label="API 키 설정"
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
        className="fixed inset-4 sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:w-[560px] sm:max-h-[85vh] z-[70] bg-gray-900/95 border border-white/10 rounded-3xl shadow-2xl overflow-hidden flex flex-col"
      >
        {/* 모달 헤더 + 탭 */}
        <div className="px-6 pt-5 pb-0 border-b border-white/10">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-bold text-white">API 키 설정</h2>
              <p className="text-xs text-gray-500 mt-1">.env에 설정된 키는 자동 사용됩니다. 브라우저에서 추가 키를 등록하면 로테이션됩니다.</p>
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
                  onInputChange={(v) => onInputChange(config.id, v)}
                  onAdd={() => onAddKey(config.id)}
                  onRemove={(idx) => onRemoveKey(config.id, idx)}
                  onToggleVisible={() => onToggleVisible(config.id)}
                />
              ))}
            </>
          )}
        </div>

        {/* 모달 푸터 */}
        <div className="px-6 py-4 border-t border-white/10 flex items-center justify-between">
          <p className="text-xs text-gray-600">
            서버 키 {totalServerKeys}개 | 브라우저 키 {totalSavedKeys}개
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
            <div key={key} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <div className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
              <span className="text-xs text-blue-300 font-mono flex-1">
                {isVisible ? key : maskKey(key)}
              </span>
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
