"use client";

import { motion } from "framer-motion";
import { API_BASE, CHANNEL_PRESETS, type PreviewData } from "../constants";

interface PreviewPanelProps {
  previewMode: boolean;
  isGenerating: boolean;
  previewData: PreviewData | null;
  channelPreviews: Record<string, PreviewData>;
  activePreviewTab: string;
  setActivePreviewTab: (tab: string) => void;
  editedScripts: Record<number, string>;
  setEditedScripts: (prev: Record<number, string> | ((prev: Record<number, string>) => Record<number, string>)) => void;
  editedScriptsMap: Record<string, Record<number, string>>;
  setEditedScriptsMap: (prev: Record<string, Record<number, string>> | ((prev: Record<string, Record<number, string>>) => Record<string, Record<number, string>>)) => void;
  replacingCut: number | null;
  regeneratingCut: number | null;
  generatingScripts: boolean;
  progress: number;
  logs: string[];
  setPreviewMode: (v: boolean) => void;
  setPreviewData: (v: PreviewData | null) => void;
  setChannelPreviews: (v: Record<string, PreviewData> | ((prev: Record<string, PreviewData>) => Record<string, PreviewData>)) => void;
  onRender: () => void;
  onGenerateScripts: () => void;
  onBatchGenerateImages: (currentPreview: PreviewData | null) => void;
  onRegenerateImage: (cutIndex: number, sessionId: string, model: string, channel?: string) => void;
  onReplaceImage: (file: File, cutIndex: number, sessionId: string, channel?: string) => void;
}

export function PreviewPanel({
  previewMode, isGenerating, previewData, channelPreviews,
  activePreviewTab, setActivePreviewTab,
  editedScripts, setEditedScripts,
  editedScriptsMap, setEditedScriptsMap,
  replacingCut, regeneratingCut, generatingScripts,
  progress, logs,
  setPreviewMode, setPreviewData, setChannelPreviews,
  onRender, onGenerateScripts, onBatchGenerateImages,
  onRegenerateImage, onReplaceImage,
}: PreviewPanelProps) {
  if (!previewMode || isGenerating) return null;

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
      {/* Multi-channel tabs */}
      {isMultiPreview && (
        <div className="flex gap-1.5 mb-4 border-b border-white/[0.06] pb-3">
          {Object.entries(channelPreviews).map(([ch, preview]) => {
            const preset = CHANNEL_PRESETS[ch];
            const isActive = ch === activePreviewTab;
            return (
              <div key={ch} className={`flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg transition-all cursor-pointer ${isActive ? "bg-indigo-600/30 text-indigo-300 border border-indigo-500/30" : "text-gray-500 hover:text-gray-300 hover:bg-white/5"}`}>
                <span onClick={() => setActivePreviewTab(ch)}>
                  {preset?.flag} {preset?.label} <span className="text-[10px] opacity-60">({preview.cuts.length}{"\ucef7"})</span>
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

      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-bold text-white">{currentPreview.title}</h3>
          <span className="text-[11px] text-gray-400 bg-white/5 px-2.5 py-0.5 rounded-full border border-white/10">
            {currentPreview.cuts.length}{"\ucef7"} {"\u00b7"} {"\uc57d"} {Math.round(currentPreview.cuts.length * 4)}{"\ucd08"}
          </span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => { setPreviewMode(false); setPreviewData(null); setChannelPreviews({}); }}
            className="px-3 py-1.5 text-xs bg-white/10 hover:bg-white/20 text-gray-300 rounded-lg transition-colors"
          >
            {"\ucde8\uc18c"}
          </button>
          {currentPreview.cuts.every((c: any) => !c.script) && (
            <button
              onClick={onGenerateScripts}
              disabled={generatingScripts}
              className="px-3 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-600 text-white rounded-lg transition-colors"
            >
              {generatingScripts ? "\uc2a4\ud06c\ub9bd\ud2b8 \uc0dd\uc131 \uc911..." : "\u270d\ufe0f \uc2a4\ud06c\ub9bd\ud2b8 \uc0dd\uc131"}
            </button>
          )}
          <button
            onClick={() => onBatchGenerateImages(currentPreview)}
            className="px-3 py-1.5 text-xs bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition-colors"
          >
            {"\ud83d\uddbc\ufe0f \uc804\uccb4 \uc774\ubbf8\uc9c0 \uc0dd\uc131"}
          </button>
          <button
            onClick={onRender}
            className="px-4 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg transition-colors shadow-lg shadow-indigo-500/25"
          >
            {"\ud655\uc778 \u2014 \uc601\uc0c1 \ub9cc\ub4e4\uae30"}
          </button>
        </div>
        {/* Image generation progress */}
        {progress > 0 && progress < 100 && (
          <div className="mt-2 px-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs text-amber-400 font-medium">{"\ud83d\uddbc\ufe0f \uc774\ubbf8\uc9c0 \uc0dd\uc131 \uc911..."}</span>
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
            <p className="text-xs text-green-400">{"\u2705 \uc774\ubbf8\uc9c0 \uc0dd\uc131 \uc644\ub8cc!"}</p>
          </div>
        )}
      </div>

      <div className="space-y-2.5 max-h-[60vh] overflow-y-auto pr-1 custom-scrollbar">
        {currentPreview.cuts.map((cut, i) => {
          const emotionMatch = (cut.description || "").match(/\[(SHOCK|WONDER|TENSION|REVEAL|URGENCY|DISBELIEF|IDENTITY|CALM|LOOP)\]/);
          const emotion = emotionMatch ? emotionMatch[1] : null;
          const emotionColors: Record<string, { bg: string; text: string; label: string }> = {
            SHOCK: { bg: "bg-red-500/20", text: "text-red-400", label: "\ucda9\uaca9" },
            WONDER: { bg: "bg-amber-500/20", text: "text-amber-400", label: "\uacbd\uc774" },
            TENSION: { bg: "bg-orange-500/20", text: "text-orange-400", label: "\uae34\uc7a5" },
            REVEAL: { bg: "bg-emerald-500/20", text: "text-emerald-400", label: "\ubc18\uc804" },
            URGENCY: { bg: "bg-rose-500/20", text: "text-rose-400", label: "\uae34\ubc15" },
            DISBELIEF: { bg: "bg-red-500/20", text: "text-red-300", label: "\ubd88\uc2e0" },
            IDENTITY: { bg: "bg-green-500/20", text: "text-green-400", label: "\uacf5\uac10" },
            CALM: { bg: "bg-sky-500/20", text: "text-sky-400", label: "\uc5ec\uc6b4" },
            LOOP: { bg: "bg-purple-500/20", text: "text-purple-400", label: "\ub8e8\ud504" },
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
              {/* Thumbnail + cut number + image replace */}
              <div
                className={`relative w-24 h-40 flex-shrink-0 rounded-lg overflow-hidden bg-black/40 group-hover:scale-[1.02] transition-transform duration-200 cursor-pointer ${replacingCut === cut.index ? "opacity-50 animate-pulse" : ""}`}
                onClick={() => {
                  const inp = document.createElement("input");
                  inp.type = "file";
                  inp.accept = "image/png,image/jpeg,image/webp";
                  inp.onchange = (e) => {
                    const f = (e.target as HTMLInputElement).files?.[0];
                    if (f) onReplaceImage(f, cut.index, currentPreview!.sessionId, currentCh || undefined);
                  };
                  inp.click();
                }}
                onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add("ring-2", "ring-indigo-400"); }}
                onDragLeave={(e) => { e.currentTarget.classList.remove("ring-2", "ring-indigo-400"); }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.currentTarget.classList.remove("ring-2", "ring-indigo-400");
                  const f = e.dataTransfer.files[0];
                  if (f) onReplaceImage(f, cut.index, currentPreview!.sessionId, currentCh || undefined);
                }}
                title={"\ud074\ub9ad \ub610\ub294 \ub4dc\ub798\uadf8\ud558\uc5ec \uc774\ubbf8\uc9c0 \uad50\uccb4"}
              >
                {cut.image_url ? (
                  <img
                    src={`${API_BASE}${cut.image_url}`}
                    alt={`\ucef7 ${cut.index + 1}`}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-600 text-xs">
                    {"\uc774\ubbf8\uc9c0 \uc5c6\uc74c"}
                  </div>
                )}
                <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                  <span className="text-[10px] text-white/80 text-center leading-tight">{"\ud074\ub9ad/\ub4dc\ub798\uadf8"}<br/>{"\uc774\ubbf8\uc9c0 \uad50\uccb4"}</span>
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
              {/* A/B variants for cut 1 */}
              {cut.index === 0 && cut.ab_variants && cut.ab_variants.length > 0 && (
                <div className="flex gap-1 mt-1">
                  <span className="text-[9px] text-gray-500 self-center mr-1">A/B:</span>
                  {cut.ab_variants.map((varUrl: string, vi: number) => (
                    <button
                      key={vi}
                      type="button"
                      onClick={() => {
                        const oldUrl = cut.image_url;
                        if (currentCh && channelPreviews[currentCh]) {
                          setChannelPreviews(prev => {
                            const cp = { ...prev };
                            if (cp[currentCh!]) {
                              cp[currentCh!] = { ...cp[currentCh!], cuts: cp[currentCh!].cuts.map(c =>
                                c.index === 0 ? { ...c, image_url: varUrl, ab_variants: [...(c.ab_variants || []).filter(v => v !== varUrl), ...(oldUrl ? [oldUrl] : [])] } : c
                              )};
                            }
                            return cp;
                          });
                        }
                      }}
                      className="w-12 h-16 rounded border border-white/20 overflow-hidden hover:border-emerald-400 transition-colors"
                    >
                      <img src={`${API_BASE}${varUrl}`} alt={`\ubcc0\ud615 ${vi + 1}`} className="w-full h-full object-cover" />
                    </button>
                  ))}
                </div>
              )}

              {/* Script editing */}
              <div className="flex-1 flex flex-col gap-1.5 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-500 font-medium">{"\ucef7"} {cut.index + 1}</span>
                  <span className="text-[10px] text-gray-600">
                    {(currentScripts[cut.index] ?? cut.script)?.length || 0}{"\uc790"}
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
                      {"\uc774\ubbf8\uc9c0 \ud504\ub86c\ud504\ud2b8 \ubcf4\uae30"}
                    </summary>
                    <p className="text-[10px] text-gray-500 mt-1 leading-relaxed">{cut.prompt}</p>
                  </details>
                  {/* Regenerate button */}
                  <div className="relative flex-shrink-0">
                    <select
                      className="bg-white/5 border border-white/10 rounded px-1.5 py-0.5 text-[9px] text-gray-400 cursor-pointer hover:bg-white/10 focus:outline-none appearance-none pr-4"
                      defaultValue=""
                      disabled={regeneratingCut === cut.index || replacingCut === cut.index}
                      onChange={(e) => {
                        const model = e.target.value;
                        if (model && currentPreview) {
                          onRegenerateImage(cut.index, currentPreview.sessionId, model, currentCh || undefined);
                        }
                        e.target.value = "";
                      }}
                    >
                      <option value="" disabled>{regeneratingCut === cut.index ? "\uc0dd\uc131\uc911..." : "\uc7ac\uc0dd\uc131"}</option>
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
        {"\uc2a4\ud06c\ub9bd\ud2b8\ub97c \uc218\uc815\ud55c \ub4a4 \u0022\ud655\uc778\u0022\uc744 \ub204\ub974\uba74 \uc218\uc815\ub41c \ub0b4\uc6a9\uc73c\ub85c \uc74c\uc131 \ub179\uc74c + \uc601\uc0c1 \ub80c\ub354\ub9c1\uc774 \uc2dc\uc791\ub429\ub2c8\ub2e4."}
      </p>
    </motion.div>
  );
}
