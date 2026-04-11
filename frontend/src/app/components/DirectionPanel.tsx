"use client";

import { Video, Music, Mic, Zap, Type, MoveVertical } from "lucide-react";
import type { LocalSettings } from "../hooks/useLocalSettings";

interface DirectionPanelProps {
  settings: LocalSettings;
  isGenerating: boolean;
}

export function DirectionPanel({ settings, isGenerating }: DirectionPanelProps) {
  const {
    cameraStyle, setCameraStyle, bgmTheme, setBgmTheme,
    voiceId, setVoiceId, ttsSpeed, setTtsSpeed,
    captionSize, setCaptionSize, captionY, setCaptionY,
    selectedChannels,
  } = settings;

  const isMultiLocked = selectedChannels.length >= 2;

  return (
    <>
      {/* Camera / BGM / Voice */}
      <div className="bg-white/[0.04] border border-white/[0.08] rounded-2xl p-3">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
              <Video className="w-3.5 h-3.5 text-sky-400" />
              <span className="text-[10px] font-medium text-gray-400">{"\uce74\uba54\ub77c"}</span>
            </div>
            <select value={cameraStyle} onChange={(e) => setCameraStyle(e.target.value)} disabled={isGenerating} aria-label={"\uce74\uba54\ub77c \uc2a4\ud0c0\uc77c \uc120\ud0dd"} className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-sky-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
              <option value="cinematic" className="bg-gray-900">{"\uc2dc\ub124\ub9c8\ud2f1"}</option>
              <option value="auto" className="bg-gray-900">{"\uc790\ub3d9 (\uac10\uc815 \uae30\ubc18)"}</option>
              <option value="dynamic" className="bg-gray-900">{"\uc5ed\ub3d9\uc801"}</option>
              <option value="gentle" className="bg-gray-900">{"\ubd80\ub4dc\ub7ec\uc6b4"}</option>
              <option value="static" className="bg-gray-900">{"\uace0\uc815"}</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
              <Music className="w-3.5 h-3.5 text-orange-400" />
              <span className="text-[10px] font-medium text-gray-400">BGM</span>
            </div>
            <select value={bgmTheme} onChange={(e) => setBgmTheme(e.target.value)} disabled={isGenerating} aria-label="BGM \ud14c\ub9c8 \uc120\ud0dd" className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-orange-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
              <option value="random" className="bg-gray-900">{"\ub79c\ub364"}</option>
              <option value="none" className="bg-gray-900">{"\uc5c6\uc74c"}</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center gap-1.5">
              <Mic className="w-3.5 h-3.5 text-pink-400" />
              <span className="text-[10px] font-medium text-gray-400">{"\uc74c\uc131"}</span>
            </div>
            <select value={isMultiLocked ? "auto" : voiceId} onChange={(e) => setVoiceId(e.target.value)} disabled={isGenerating || isMultiLocked} aria-label={"\uc74c\uc131 \uc120\ud0dd"} className={`w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none appearance-none transition-colors ${isMultiLocked ? "text-gray-500 cursor-not-allowed opacity-50" : "text-gray-200 cursor-pointer hover:bg-white/10 focus:border-pink-500/50"}`}>
              <option value="auto" className="bg-gray-900">{"\uc790\ub3d9"}</option>
              <option value="cjVigY5qzO86Huf0OWal" className="bg-gray-900">Eric ({"\ucc28\ubd84"})</option>
              <option value="pNInz6obpgDQGcFmaJgB" className="bg-gray-900">Adam ({"\uad8c\uc704"})</option>
              <option value="nPczCjzI2devNBz1zQrb" className="bg-gray-900">Brian ({"\ub0b4\ub808\uc774\uc158"})</option>
              <option value="pqHfZKP75CvOlQylNhV4" className="bg-gray-900">Bill ({"\ub2e4\ud050"})</option>
              <option value="onwK4e9ZLuTAKqWW03F9" className="bg-gray-900">Daniel ({"\ub274\uc2a4"})</option>
              <option value="21m00Tcm4TlvDq8ikWAM" className="bg-gray-900">Rachel ({"\uc5ec\uc131"})</option>
              <option value="EXAVITQu4vr4xnSDxMaL" className="bg-gray-900">Sarah ({"\ubd80\ub4dc\ub7ec\uc6b4"})</option>
              <option value="XrExE9yKIg1WjnnlVkGX" className="bg-gray-900">Matilda ({"\ub530\ub73b\ud55c"})</option>
              <option value="IKne3meq5aSn9XLyUdCD" className="bg-gray-900">Charlie ({"\uc720\uba38"})</option>
              <option value="ErXwobaYiN019PkySvjV" className="bg-gray-900">Antoni ({"\ub9cc\ub2a5"})</option>
              <option value="JBFqnCBsd6RMkjVDRZzb" className="bg-gray-900">George ({"\uacf5\ud3ec"})</option>
            </select>
          </div>
        </div>
      </div>

      {/* Caption sliders */}
      <div className="bg-white/[0.04] border border-white/[0.08] rounded-2xl p-3">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Zap className="w-3 h-3 text-indigo-400" />
                <span className="text-[10px] font-medium text-gray-400">{"\uc18d\ub3c4"}</span>
              </div>
              <span className="text-[10px] text-indigo-400/70 tabular-nums">{ttsSpeed}x</span>
            </div>
            <input type="range" min="0.7" max="1.5" step="0.05" value={ttsSpeed} onChange={(e) => setTtsSpeed(parseFloat(e.target.value))} disabled={isGenerating || isMultiLocked} className={`w-full h-1 accent-indigo-500 ${isMultiLocked ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`} />
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Type className="w-3 h-3 text-indigo-400" />
                <span className="text-[10px] font-medium text-gray-400">{"\uc790\ub9c9"}</span>
              </div>
              <span className="text-[10px] text-indigo-400/70 tabular-nums">{captionSize}px</span>
            </div>
            <input type="range" min="32" max="72" step="4" value={captionSize} onChange={(e) => setCaptionSize(parseInt(e.target.value))} disabled={isGenerating || isMultiLocked} className={`w-full h-1 accent-indigo-500 ${isMultiLocked ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`} />
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <MoveVertical className="w-3 h-3 text-indigo-400" />
                <span className="text-[10px] font-medium text-gray-400">{"\uc704\uce58"}</span>
              </div>
              <span className="text-[10px] text-indigo-400/70 tabular-nums">{captionY}%</span>
            </div>
            <input type="range" min="10" max="50" step="2" value={captionY} onChange={(e) => setCaptionY(parseInt(e.target.value))} disabled={isGenerating || isMultiLocked} className={`w-full h-1 accent-indigo-500 ${isMultiLocked ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`} />
          </div>
        </div>
      </div>
    </>
  );
}
