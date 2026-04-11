"use client";

import { Tv } from "lucide-react";
import { CHANNEL_PRESETS } from "../constants";
import type { LocalSettings } from "../hooks/useLocalSettings";

interface ChannelSelectorProps {
  settings: LocalSettings;
  isGenerating: boolean;
}

export function ChannelSelector({ settings, isGenerating }: ChannelSelectorProps) {
  const { selectedChannels, setSelectedChannels, setChannel, formatType, setFormatType } = settings;

  return (
    <div className="bg-white/[0.04] border border-white/[0.08] rounded-2xl p-3 space-y-2.5">
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
                if (newSelected.length === 1) {
                  settings.applyChannelPreset(newSelected[0]);
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
      {/* Format selection */}
      <div className="flex items-center justify-center gap-1.5 flex-wrap">
        {[
          { value: "auto", label: "\uc790\ub3d9" },
          { value: "WHO_WINS", label: "WHO WINS" },
          { value: "COUNTDOWN", label: "COUNTDOWN" },
          { value: "SCALE", label: "SCALE" },
          { value: "IF", label: "IF" },
          { value: "FACT", label: "FACT" },
          { value: "MYSTERY", label: "MYSTERY" },
          { value: "PARADOX", label: "PARADOX" },
          { value: "EMOTIONAL_SCI", label: "EMOTIONAL" },
        ].map((fmt) => (
          <button
            type="button"
            key={fmt.value}
            onClick={() => setFormatType(fmt.value)}
            disabled={isGenerating}
            className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors ${
              formatType === fmt.value
                ? "bg-orange-500/20 border-orange-500/50 text-orange-300"
                : "bg-white/5 border-white/10 text-gray-400 hover:bg-white/10"
            }`}
          >
            {fmt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
