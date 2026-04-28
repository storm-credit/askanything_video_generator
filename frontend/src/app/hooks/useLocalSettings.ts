"use client";

import { useState, useEffect } from "react";
import { loadSetting, saveSetting, setHydrated, CHANNEL_PRESETS } from "../constants";

const LEGACY_VIDEO_MODEL_MAP: Record<string, string> = {
  "veo-3.1-generate-preview": "veo-3.1-generate-001",
  "veo-3.1-fast-generate-preview": "veo-3.1-fast-generate-001",
  "veo-3.0-generate-preview": "veo-3.0-generate-001",
  "veo-3.0-fast-generate-preview": "veo-3.0-fast-generate-001",
};

const normalizeVideoModel = (value: string): string => LEGACY_VIDEO_MODEL_MAP[value] || value;

export function useLocalSettings() {
  const [qualityPreset, setQualityPreset] = useState(() => loadSetting("qualityPreset", "best"));
  const [llmProvider, setLlmProvider] = useState(() => loadSetting("llmProvider", "gemini"));
  const [llmModel, setLlmModel] = useState(() => loadSetting("llmModel", ""));
  const [imageEngine, setImageEngine] = useState(() => loadSetting("imageEngine", "imagen"));
  const [imageModel, setImageModel] = useState(() => loadSetting("imageModel", ""));
  const [videoEngine, setVideoEngine] = useState(() => loadSetting("videoEngine", "veo3"));
  const [videoModel, setVideoModelState] = useState(() => normalizeVideoModel(loadSetting("videoModel", "hero-only")));
  const [testMode, setTestMode] = useState(() => loadSetting("testMode", false));
  const [language, setLanguage] = useState(() => loadSetting("language", "ko"));
  const [cameraStyle, setCameraStyle] = useState(() => loadSetting("cameraStyle", "auto"));
  const [bgmTheme, setBgmTheme] = useState(() => loadSetting("bgmTheme", "random"));
  const [formatType, setFormatType] = useState(() => loadSetting("formatType", "auto"));
  const [channel, setChannel] = useState(() => loadSetting("channel", ""));
  const [selectedChannels, setSelectedChannels] = useState<string[]>(() => loadSetting("selectedChannels", []));
  const [platforms, setPlatforms] = useState<string[]>(() => loadSetting("platforms", ["youtube"]));
  const [ttsSpeed, setTtsSpeed] = useState(() => loadSetting("ttsSpeed", 1.3));
  const [voiceId, setVoiceId] = useState(() => loadSetting("voiceId", "auto"));
  const [captionSize, setCaptionSize] = useState(() => loadSetting("captionSize", 54));
  const [captionY, setCaptionY] = useState(() => loadSetting("captionY", 38));
  const [outputPath, setOutputPath] = useState("");

  // localStorage → state restore (hydration, runs once)
  useEffect(() => {
    setHydrated(true);
    const _load = <T,>(key: string, fallback: T): T => {
      try { const v = localStorage.getItem(`aa_${key}`); return v !== null ? JSON.parse(v) : fallback; } catch { return fallback; }
    };
    setQualityPreset(_load("qualityPreset", "best"));
    setLlmProvider(_load("llmProvider", "gemini"));
    setLlmModel(_load("llmModel", ""));
    setImageEngine(_load("imageEngine", "imagen"));
    setImageModel(_load("imageModel", ""));
    setVideoEngine(_load("videoEngine", "veo3"));
    setVideoModelState(normalizeVideoModel(_load("videoModel", "hero-only")));
    setTestMode(_load("testMode", false));
    setLanguage(_load("language", "ko"));
    setCameraStyle(_load("cameraStyle", "auto"));
    setBgmTheme(_load("bgmTheme", "random"));
    setFormatType(_load("formatType", "auto"));
    setChannel(_load("channel", ""));
    setSelectedChannels(_load("selectedChannels", []));
    setPlatforms(_load("platforms", ["youtube"]));
    setTtsSpeed(_load("ttsSpeed", 1.3));
    setVoiceId(_load("voiceId", "auto"));
    setCaptionSize(_load("captionSize", 54));
    setCaptionY(_load("captionY", 38));
    try { setOutputPath(localStorage.getItem("askanything_output_path") || ""); } catch {}
  }, []);

  // Auto-save settings to localStorage
  useEffect(() => {
    saveSetting("qualityPreset", qualityPreset);
    saveSetting("llmProvider", llmProvider);
    saveSetting("llmModel", llmModel);
    saveSetting("imageEngine", imageEngine);
    saveSetting("imageModel", imageModel);
    saveSetting("videoEngine", videoEngine);
    saveSetting("videoModel", videoModel);
    saveSetting("testMode", testMode);
    saveSetting("language", language);
    saveSetting("cameraStyle", cameraStyle);
    saveSetting("bgmTheme", bgmTheme);
    saveSetting("formatType", formatType);
    saveSetting("channel", channel);
    saveSetting("selectedChannels", selectedChannels);
    saveSetting("platforms", platforms);
    saveSetting("ttsSpeed", ttsSpeed);
    saveSetting("voiceId", voiceId);
    saveSetting("captionSize", captionSize);
    saveSetting("captionY", captionY);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qualityPreset, llmProvider, llmModel, imageEngine, imageModel, videoEngine, videoModel, testMode, language, cameraStyle, bgmTheme, formatType, channel, selectedChannels, platforms, ttsSpeed, voiceId, captionSize, captionY]);

  useEffect(() => {
    try { localStorage.setItem("askanything_output_path", outputPath); } catch {}
  }, [outputPath]);

  const setVideoModel = (value: string) => {
    setVideoModelState(normalizeVideoModel(value));
  };

  const applyPreset = (preset: string) => {
    setQualityPreset(preset);
    switch (preset) {
      case "best":
        setLlmProvider("gemini"); setLlmModel("");
        setImageEngine("imagen"); setImageModel("");
        setVideoEngine("veo3"); setVideoModel("hero-only");
        break;
      case "balanced":
        setLlmProvider("gemini"); setLlmModel("gemini-2.5-flash");
        setImageEngine("imagen"); setImageModel("");
        setVideoEngine("veo3"); setVideoModel("hero-only");
        break;
      case "fast":
        setLlmProvider("gemini"); setLlmModel("gemini-2.5-flash");
        setImageEngine("imagen"); setImageModel("imagen-4.0-fast-generate-001");
        setVideoEngine("none"); setVideoModel("");
        break;
      case "manual":
        break;
    }
  };

  const applyChannelPreset = (channelKey: string) => {
    const ch = CHANNEL_PRESETS[channelKey];
    if (ch) {
      setChannel(channelKey);
      setLanguage(ch.language);
      setTtsSpeed(ch.ttsSpeed);
      setPlatforms(ch.platforms);
      setCaptionSize(ch.captionSize);
      setCaptionY(ch.captionY);
      if (ch.cameraStyle) setCameraStyle(ch.cameraStyle);
      setVoiceId("auto");
    }
  };

  return {
    qualityPreset, setQualityPreset,
    llmProvider, setLlmProvider,
    llmModel, setLlmModel,
    imageEngine, setImageEngine,
    imageModel, setImageModel,
    videoEngine, setVideoEngine,
    videoModel, setVideoModel,
    testMode, setTestMode,
    language, setLanguage,
    cameraStyle, setCameraStyle,
    bgmTheme, setBgmTheme,
    formatType, setFormatType,
    channel, setChannel,
    selectedChannels, setSelectedChannels,
    platforms, setPlatforms,
    ttsSpeed, setTtsSpeed,
    voiceId, setVoiceId,
    captionSize, setCaptionSize,
    captionY, setCaptionY,
    outputPath, setOutputPath,
    applyPreset,
    applyChannelPreset,
  };
}

export type LocalSettings = ReturnType<typeof useLocalSettings>;
