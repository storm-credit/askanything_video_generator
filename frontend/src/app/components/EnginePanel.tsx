"use client";

import { Brain, ImageIcon, Film } from "lucide-react";
import { getLLM_MODELS, getIMAGE_MODELS, getVIDEO_MODELS } from "../constants";
import type { LocalSettings } from "../hooks/useLocalSettings";

interface EnginePanelProps {
  settings: LocalSettings;
  isGenerating: boolean;
  remainLabel: (modelId: string) => string;
}

export function EnginePanel({ settings, isGenerating, remainLabel }: EnginePanelProps) {
  const {
    llmProvider, setLlmProvider, llmModel, setLlmModel,
    imageEngine, setImageEngine, imageModel, setImageModel,
    videoEngine, setVideoEngine, videoModel, setVideoModel,
    setQualityPreset,
  } = settings;

  const LLM_MODELS = getLLM_MODELS(remainLabel);
  const IMAGE_MODELS = getIMAGE_MODELS(remainLabel);
  const VIDEO_MODELS = getVIDEO_MODELS(remainLabel);

  return (
    <div className="bg-white/[0.04] border border-white/[0.08] rounded-2xl p-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Brain className="w-3.5 h-3.5 text-violet-400" />
            <span className="text-[10px] font-medium text-gray-400">\uae30\ud68d</span>
          </div>
          <select value={llmProvider} onChange={(e) => { setLlmProvider(e.target.value); setLlmModel(""); setQualityPreset("manual"); }} disabled={isGenerating} aria-label="LLM \uc5d4\uc9c4 \uc120\ud0dd" className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-violet-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
            <option value="gemini" className="bg-gray-900">Gemini</option>
            <option value="claude" className="bg-gray-900">Claude</option>
          </select>
          {LLM_MODELS[llmProvider]?.length > 1 && (
            <select value={llmModel} onChange={(e) => { setLlmModel(e.target.value); setQualityPreset("manual"); }} disabled={isGenerating} aria-label="LLM \ubaa8\ub378 \uc120\ud0dd" className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-[10px] text-gray-500 focus:outline-none focus:border-violet-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
              {LLM_MODELS[llmProvider].map((m) => (<option key={m.value} value={m.value} className="bg-gray-900">{m.label}</option>))}
            </select>
          )}
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <ImageIcon className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-[10px] font-medium text-gray-400">\uc774\ubbf8\uc9c0</span>
          </div>
          <select value={imageEngine} onChange={(e) => { setImageEngine(e.target.value); setImageModel(""); setQualityPreset("manual"); }} disabled={isGenerating} aria-label="\uc774\ubbf8\uc9c0 \uc5d4\uc9c4 \uc120\ud0dd" className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-emerald-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
            <option value="imagen" className="bg-gray-900">Imagen</option>
            <option value="nano_banana" className="bg-gray-900">Nano Banana</option>
          </select>
          {IMAGE_MODELS[imageEngine]?.length > 1 && (
            <select value={imageModel} onChange={(e) => { setImageModel(e.target.value); setQualityPreset("manual"); }} disabled={isGenerating} aria-label="\uc774\ubbf8\uc9c0 \ubaa8\ub378 \uc120\ud0dd" className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-[10px] text-gray-500 focus:outline-none focus:border-emerald-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
              {IMAGE_MODELS[imageEngine].map((m) => (<option key={m.value} value={m.value} className="bg-gray-900">{m.label}</option>))}
            </select>
          )}
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Film className="w-3.5 h-3.5 text-rose-400" />
            <span className="text-[10px] font-medium text-gray-400">\ube44\ub514\uc624</span>
          </div>
          <select value={videoEngine} onChange={(e) => { setVideoEngine(e.target.value); setVideoModel(""); setQualityPreset("manual"); }} disabled={isGenerating} aria-label="\ube44\ub514\uc624 \uc5d4\uc9c4 \uc120\ud0dd" className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-rose-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
            <option value="veo3" className="bg-gray-900">Veo 3</option>
            <option value="kling" className="bg-gray-900">Kling</option>
            <option value="blender" className="bg-gray-900">Blender 3D</option>
            <option value="none" className="bg-gray-900">\uc5c6\uc74c</option>
          </select>
          {VIDEO_MODELS[videoEngine]?.length > 1 && (
            <select value={videoModel} onChange={(e) => { setVideoModel(e.target.value); setQualityPreset("manual"); }} disabled={isGenerating} aria-label="\ube44\ub514\uc624 \ubaa8\ub378 \uc120\ud0dd" className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1 text-[10px] text-gray-500 focus:outline-none focus:border-rose-500/50 appearance-none cursor-pointer hover:bg-white/10 transition-colors">
              {VIDEO_MODELS[videoEngine].map((m) => (<option key={m.value} value={m.value} className="bg-gray-900">{m.label}</option>))}
            </select>
          )}
        </div>
      </div>
    </div>
  );
}
