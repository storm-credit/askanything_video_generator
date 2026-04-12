"use client";

import { useState, useRef, useCallback } from "react";
import { API_BASE, CHANNEL_PRESETS, type PreviewData, type ChannelStatus, type RenderResult } from "../constants";
import type { LocalSettings } from "./useLocalSettings";

interface UseSSEGenerateParams {
  settings: LocalSettings;
  savedKeys: Record<string, string[]>;
  topic: string;
  todayCuts: Record<string, any[]> | null;
  todayMeta: Record<string, { title: string; description: string; hashtags: string }> | null;
  checkPlatformStatus: () => void;
}

export function useSSEGenerate({ settings, savedKeys, topic, todayCuts, todayMeta, checkPlatformStatus }: UseSSEGenerateParams) {
  const {
    llmProvider, llmModel, imageEngine, imageModel, videoEngine, videoModel,
    testMode, language, cameraStyle, bgmTheme, formatType, channel,
    selectedChannels, platforms, ttsSpeed, voiceId, captionSize, captionY,
    outputPath, setVideoEngine, setVideoModel,
  } = settings;

  const [isGenerating, setIsGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState<string[]>([]);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [generatedVideoPath, setGeneratedVideoPath] = useState<string | null>(null);
  const [generatedVideoUrl, setGeneratedVideoUrl] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  // Preview mode
  const [previewMode, setPreviewMode] = useState(false);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [editedScripts, setEditedScripts] = useState<Record<number, string>>({});
  const [channelPreviews, setChannelPreviews] = useState<Record<string, PreviewData>>({});
  const [activePreviewTab, setActivePreviewTab] = useState<string>("");
  const [editedScriptsMap, setEditedScriptsMap] = useState<Record<string, Record<number, string>>>({});
  const [replacingCut, setReplacingCut] = useState<number | null>(null);
  const [regeneratingCut, setRegeneratingCut] = useState<number | null>(null);
  const [generatingScripts, setGeneratingScripts] = useState(false);

  // Multi-channel generation
  const [channelResults, setChannelResults] = useState<Record<string, ChannelStatus>>({});
  const multiAbortRefs = useRef<Record<string, AbortController>>({});

  // Render results
  const [renderResults, setRenderResults] = useState<Record<string, RenderResult>>({});
  const [activeRenderTab, setActiveRenderTab] = useState<string>("");

  // Abort
  const abortControllerRef = useRef<AbortController | null>(null);
  const cancelledRef = useRef(false);

  const publishMode = "local" as const;
  const scheduledTime = "";

  // YouTube URL detection
  const isYouTubeUrl = (text: string) => /(?:youtube\.com\/(?:shorts\/|watch\?v=)|youtu\.be\/)/.test(text.trim());
  const detectedRefUrl = isYouTubeUrl(topic) ? topic.trim() : undefined;

  const pickKey = (configId: string): string | undefined => {
    const keys = savedKeys[configId];
    if (!keys || keys.length === 0) return undefined;
    return keys[Math.floor(Math.random() * keys.length)];
  };

  // ── Single channel SSE generate ──
  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;

    if (selectedChannels.length >= 2) {
      return handleMultiGenerate(e);
    }

    setIsGenerating(true);
    setProgress(0);
    setSuccessMessage(null);
    setErrorMessage(null);
    setLogs([]);
    setGeneratedVideoUrl(null);

    const selectedOpenaiKey = pickKey("openai");
    const selectedElevenlabsKey = pickKey("elevenlabs");

    let llmKeyOverride: string | undefined;
    if (llmProvider === "gemini") llmKeyOverride = pickKey("gemini");
    else if (llmProvider === "claude") llmKeyOverride = pickKey("claude_key");

    const geminiKeys = savedKeys["gemini"] || [];
    const geminiKeysStr = geminiKeys.length > 0 ? geminiKeys.join(",") : undefined;

    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    cancelledRef.current = false;
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;

    try {
      const response = await fetch(`${API_BASE}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortController.signal,
        body: JSON.stringify({
          topic, apiKey: selectedOpenaiKey || undefined, elevenlabsKey: selectedElevenlabsKey || undefined,
          videoEngine, imageEngine, llmProvider,
          llmModel: llmModel || undefined, imageModel: imageModel || undefined, videoModel: videoModel || undefined,
          language: language === "auto" ? "ko" : language, llmKey: llmKeyOverride || undefined, geminiKeys: geminiKeysStr,
          outputPath: outputPath.trim() || undefined, cameraStyle, bgmTheme,
          formatType: formatType !== "auto" ? formatType : undefined,
          channel: channel || undefined, platforms, ttsSpeed, voiceId, captionSize, captionY,
          referenceUrl: detectedRefUrl, publishMode,
          scheduledTime: publishMode === "scheduled" ? scheduledTime : undefined,
          maxCuts: testMode ? 3 : undefined,
        }),
      });

      if (!response.body) throw new Error("No response body");
      reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      const processLine = (line: string) => {
        if (!line.startsWith("data:")) return;
        const rawData = line.slice(5).trim();
        if (!rawData) return;

        if (rawData.startsWith("DONE|")) {
          const parts = rawData.slice(5).split("|");
          const videoPath = parts[0].trim().replace(/\\/g, '/');
          const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
          const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
          const downloadUrl = `${API_BASE}${normalizedPath}`;
          setGeneratedVideoPath(videoPath);
          setGeneratedVideoUrl(downloadUrl);
          setSuccessMessage(channel ? "\ube44\ub514\uc624 \uc0dd\uc131 + \uc5c5\ub85c\ub4dc \uc644\ub8cc!" : "\ube44\ub514\uc624 \uc0dd\uc131 \uc131\uacf5!");
          setIsGenerating(false);
          checkPlatformStatus();
        } else if (rawData.startsWith("UPLOAD_DONE|")) {
          const uploadParts = rawData.slice(12).split("|");
          const platform = uploadParts[0];
          const info = uploadParts.slice(1).join("|");
          setLogs(prev => [...prev.slice(-99), `\u2705 ${platform.toUpperCase()} \uc5c5\ub85c\ub4dc \uc644\ub8cc ${info}`]);
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
        if (done) { if (buffer.trim()) processLine(buffer); break; }
        if (cancelledRef.current) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (cancelledRef.current) break;
          processLine(line);
        }
      }
    } catch (error) {
      if (abortController.signal.aborted) {
        setLogs(prev => [...prev.slice(-99), "WARN:\uc0ac\uc6a9\uc790\uc5d0 \uc758\ud574 \uc0dd\uc131\uc774 \ucde8\uc18c\ub418\uc5c8\uc2b5\ub2c8\ub2e4."]);
        return;
      }
      console.error(error);
      const message = error instanceof Error ? error.message : "Unknown error";
      const userMsg = message === "Failed to fetch"
        ? "[\uc5f0\uacb0 \uc2e4\ud328] \ubc31\uc5d4\ub4dc \uc11c\ubc84(localhost:8003)\uc5d0 \uc5f0\uacb0\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \uc11c\ubc84\uac00 \uc2e4\ud589 \uc911\uc778\uc9c0 \ud655\uc778\ud574\uc8fc\uc138\uc694."
        : `[\ub124\ud2b8\uc6cc\ud06c \uc624\ub958] ${message}`;
      setLogs(prev => [...prev.slice(-99), `ERROR:${userMsg}`]);
      setErrorMessage(userMsg);
    } finally {
      reader?.cancel().catch(() => {});
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancel = () => {
    cancelledRef.current = true;
    abortControllerRef.current?.abort();
    for (const ac of Object.values(multiAbortRefs.current)) ac.abort();
    multiAbortRefs.current = {};
    setIsGenerating(false);
    fetch(`${API_BASE}/api/cancel`, { method: "POST" }).catch(() => {});
  };

  const handleClearError = () => {
    setErrorMessage(null);
    setLogs([]);
  };

  // ── Multi-channel parallel generation ──
  const processMultiLine = (ch: string, line: string) => {
    if (!line.startsWith("data:")) return;
    const rawData = line.slice(5).trim();
    if (!rawData) return;

    if (rawData.startsWith("DONE|")) {
      const videoPath = rawData.slice(5).split("|")[0].trim().replace(/\\/g, '/');
      const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
      const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
      const downloadUrl = `${API_BASE}${normalizedPath}`;
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'done', progress: 100, videoUrl: downloadUrl } }));
    } else if (rawData.startsWith("UPLOAD_DONE|")) {
      const uploadParts = rawData.slice(12).split("|");
      const platform = uploadParts[0];
      const info = uploadParts.slice(1).join("|");
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], logs: [...(prev[ch]?.logs || []).slice(-49), `\u2705 ${platform.toUpperCase()} \uc5c5\ub85c\ub4dc \uc644\ub8cc ${info}`] } }));
    } else if (rawData.startsWith("ERROR|")) {
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'error', errorMsg: rawData.slice(6), logs: [...(prev[ch]?.logs || []).slice(-49), rawData.slice(6)] } }));
    } else if (rawData.startsWith("PROG|")) {
      const p = parseInt(rawData.slice(5), 10);
      if (!isNaN(p)) setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], progress: p } }));
    } else if (rawData.startsWith("GEN_ID|")) {
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], genId: rawData.slice(7) } }));
    } else {
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], logs: [...(prev[ch]?.logs || []).slice(-49), rawData] } }));
    }
  };

  const generateForChannel = async (ch: string) => {
    const preset = CHANNEL_PRESETS[ch];
    if (!preset) return;

    const ac = new AbortController();
    multiAbortRefs.current[ch] = ac;
    setChannelResults(prev => ({ ...prev, [ch]: { progress: 0, logs: [], status: 'generating' } }));

    const selectedOpenaiKey = pickKey("openai");
    const selectedElevenlabsKey = pickKey("elevenlabs");
    let llmKeyOverride: string | undefined;
    if (llmProvider === "gemini") llmKeyOverride = pickKey("gemini");
    else if (llmProvider === "claude") llmKeyOverride = pickKey("claude_key");
    const geminiKeys = savedKeys["gemini"] || [];
    const geminiKeysStr = geminiKeys.length > 0 ? geminiKeys.join(",") : undefined;

    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
      const response = await fetch(`${API_BASE}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ac.signal,
        body: JSON.stringify({
          topic, apiKey: selectedOpenaiKey || undefined, elevenlabsKey: selectedElevenlabsKey || undefined,
          videoEngine, imageEngine, llmProvider,
          llmModel: llmModel || undefined, imageModel: imageModel || undefined, videoModel: videoModel || undefined,
          language: preset.language, llmKey: llmKeyOverride || undefined, geminiKeys: geminiKeysStr,
          outputPath: outputPath.trim() || undefined, cameraStyle, bgmTheme,
          formatType: formatType !== "auto" ? formatType : undefined,
          channel: ch, platforms: preset.platforms,
          ttsSpeed: preset.ttsSpeed, voiceId: "auto",
          captionSize: preset.captionSize, captionY: preset.captionY,
          referenceUrl: detectedRefUrl, publishMode,
          scheduledTime: publishMode === "scheduled" ? scheduledTime : undefined,
          maxCuts: testMode ? 3 : undefined,
        }),
      });

      if (!response.body) throw new Error("No response body");
      reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) { if (buffer.trim()) processMultiLine(ch, buffer); break; }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) processMultiLine(ch, line);
      }
    } catch (error) {
      if (ac.signal.aborted) return;
      const msg = error instanceof Error ? error.message : "Unknown error";
      setChannelResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'error', errorMsg: msg } }));
    } finally {
      reader?.cancel().catch(() => {});
    }
  };

  const handleMultiGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim() || selectedChannels.length === 0) return;

    setIsGenerating(true);
    setSuccessMessage(null);
    setErrorMessage(null);
    setChannelResults({});
    setRenderResults({});
    setChannelPreviews({});
    setPreviewData(null);
    setProgress(0);

    const promises = selectedChannels.map(ch => generateForChannel(ch));
    await Promise.allSettled(promises);

    setIsGenerating(false);
    setChannelResults(prev => {
      const doneCount = Object.values(prev).filter(r => r.status === 'done').length;
      if (doneCount > 0) setSuccessMessage(`${doneCount}/${selectedChannels.length} \ucc44\ub110 \uc601\uc0c1 \uc0dd\uc131 \uc644\ub8cc!`);
      return prev;
    });
  };

  // ── Preview mode: prepare → preview → render ──
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
        const parts = rawData.slice(5).split("|");
        const videoPath = parts[0].trim().replace(/\\/g, '/');
        const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
        const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
        const downloadUrl = `${API_BASE}${normalizedPath}`;
        setGeneratedVideoPath(videoPath);
        setGeneratedVideoUrl(downloadUrl);
        setSuccessMessage("\ube44\ub514\uc624 \uc0dd\uc131 \uc131\uacf5!");
        setIsGenerating(false);
        setPreviewData(null);
        checkPlatformStatus();
      } else if (rawData.startsWith("PREVIEW|")) {
        onPreview?.(rawData.slice(8));
      } else if (rawData.startsWith("ERROR|")) {
        setLogs(prev => [...prev.slice(-99), `ERROR:${rawData.slice(6)}`]);
        setErrorMessage(prev => prev ? `${prev}\n${rawData.slice(6)}` : rawData.slice(6));
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

  const prepareForChannel = async (ch: string, abortSignal: AbortSignal): Promise<PreviewData | null> => {
    const preset = CHANNEL_PRESETS[ch];
    if (!preset) return null;
    return new Promise<PreviewData | null>((resolve) => {
      fetch(`${API_BASE}/api/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortSignal,
        body: JSON.stringify({
          topic, apiKey: pickKey("openai") || undefined,
          llmProvider,
          llmKey: llmProvider === "gemini" ? pickKey("gemini") : llmProvider === "claude" ? pickKey("claude_key") : undefined,
          geminiKeys: (savedKeys["gemini"] || []).length > 0 ? savedKeys["gemini"].join(",") : undefined,
          imageEngine, language: preset.language, channel: ch,
          formatType: formatType !== "auto" ? formatType : undefined,
          referenceUrl: detectedRefUrl, maxCuts: testMode ? 3 : undefined,
        }),
      }).then(async (response) => {
        await readSSE(response, (previewJson) => {
          try {
            const data: PreviewData = { ...JSON.parse(previewJson), channel: ch };
            resolve(data);
          } catch (err) {
            console.error("Preview parse error:", err);
            resolve(null);
          }
        });
        resolve(null);
      }).catch(() => resolve(null));
    });
  };

  const handlePrepare = async (e?: React.SyntheticEvent) => {
    e?.preventDefault();
    if (!topic.trim()) return;

    if (Object.keys(channelPreviews).length > 0 || previewData) {
      setPreviewMode(true);
      return;
    }

    // Day file scripts → direct assignment
    if (todayCuts) {
      setIsGenerating(false);
      setProgress(0);
      setSuccessMessage(null);
      setErrorMessage(null);
      setLogs([]);
      setPreviewData(null);
      setEditedScripts({});
      setChannelPreviews({});
      setEditedScriptsMap({});
      setRenderResults({});

      const cutsChannels = Object.keys(todayCuts);
      const channels = cutsChannels.length >= 1 ? cutsChannels : (channel ? [channel] : ["default"]);

      if (channels.length >= 2) {
        const previews: Record<string, PreviewData> = {};
        for (const ch of channels) {
          const chCuts = todayCuts[ch] || todayCuts[channels[0]] || [];
          if (chCuts.length > 0) {
            const data: PreviewData = {
              sessionId: `today_${topic.replace(/\s+/g, '_')}_${ch}`,
              channel: ch, title: topic,
              cuts: chCuts.map((c: any, i: number) => ({ index: i, script: c.script || "", prompt: c.image_prompt || "", image_url: null })),
            };
            previews[ch] = data;
          }
        }
        setChannelPreviews(previews);
        if (Object.keys(previews).length > 0) {
          setActivePreviewTab(channels[0]);
          setPreviewMode(true);
          for (const [ch, pv] of Object.entries(previews)) {
            fetch(`${API_BASE}/api/register-day-session`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ sessionId: pv.sessionId, topic, channel: ch, cuts: pv.cuts.map((c: any) => ({ script: c.script, prompt: c.prompt })) }),
            }).then(r => r.json()).then(data => {
              if (data.image_urls) {
                setChannelPreviews(prev => {
                  const updated = { ...prev };
                  if (updated[ch]) {
                    const newCuts = updated[ch].cuts.map((c: any, i: number) => ({ ...c, image_url: data.image_urls[i] || c.image_url }));
                    updated[ch] = { ...updated[ch], cuts: newCuts };
                  }
                  return updated;
                });
              }
            }).catch(() => {});
          }
        }
        setLogs(["\u2705 Day \ud30c\uc77c \uc2a4\ud06c\ub9bd\ud2b8 \ubc30\uc815 \uc644\ub8cc \u2014 \uc774\ubbf8\uc9c0\ub294 '\uc804\uccb4 \uc774\ubbf8\uc9c0 \uc0dd\uc131' \ubc84\ud2bc\uc73c\ub85c \uc0dd\uc131"]);
      } else {
        const ch = channels[0];
        const chCuts = todayCuts[ch] || Object.values(todayCuts)[0] || [];
        if (chCuts.length > 0) {
          const data: PreviewData = {
            sessionId: `today_${topic.replace(/\s+/g, '_')}_${ch}`,
            title: topic, channel: ch,
            cuts: chCuts.map((c: any, i: number) => ({ index: i, script: c.script || "", prompt: c.image_prompt || "", image_url: null })),
          };
          setPreviewData(data);
          setPreviewMode(true);
          fetch(`${API_BASE}/api/register-day-session`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sessionId: data.sessionId, topic, channel: ch, cuts: data.cuts.map((c: any) => ({ script: c.script, prompt: c.prompt })) }),
          }).catch(() => {});
        }
        setLogs(["\u2705 Day \ud30c\uc77c \uc2a4\ud06c\ub9bd\ud2b8 \ubc30\uc815 \uc644\ub8cc \u2014 \uc774\ubbf8\uc9c0\ub294 '\uc804\uccb4 \uc774\ubbf8\uc9c0 \uc0dd\uc131' \ubc84\ud2bc\uc73c\ub85c \uc0dd\uc131"]);
      }
      return;
    }

    // No Day file scripts → API call
    setIsGenerating(true);
    setProgress(0);
    setSuccessMessage(null);
    setErrorMessage(null);
    setLogs([]);
    setPreviewData(null);
    setEditedScripts({});
    setChannelPreviews({});
    setEditedScriptsMap({});
    setRenderResults({});

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const channels = selectedChannels.length >= 2 ? selectedChannels : (channel ? [channel] : ["default"]);
    const isMulti = channels.length >= 2;

    try {
      if (isMulti) {
        const previews: Record<string, PreviewData> = {};
        for (const ch of channels) {
          setLogs(prev => [...prev.slice(-99), `[${CHANNEL_PRESETS[ch]?.flag || ""} ${CHANNEL_PRESETS[ch]?.label || ch}] \ubbf8\ub9ac\ubcf4\uae30 \uc900\ube44 \uc911...`]);
          const result = await prepareForChannel(ch, abortController.signal);
          if (result) {
            previews[ch] = result;
            setChannelPreviews(prev => ({ ...prev, [ch]: result }));
          }
        }
        if (Object.keys(previews).length > 0) {
          setActivePreviewTab(channels[0]);
          setPreviewMode(true);
        }
      } else {
        const response = await fetch(`${API_BASE}/api/prepare`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: abortController.signal,
          body: JSON.stringify({
            topic, apiKey: pickKey("openai") || undefined, llmProvider,
            llmKey: llmProvider === "gemini" ? pickKey("gemini") : llmProvider === "claude" ? pickKey("claude_key") : undefined,
            geminiKeys: (savedKeys["gemini"] || []).length > 0 ? savedKeys["gemini"].join(",") : undefined,
            imageEngine, language, channel: channel || undefined,
            formatType: formatType !== "auto" ? formatType : undefined,
            referenceUrl: detectedRefUrl, maxCuts: testMode ? 3 : undefined,
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
      }
    } catch (error) {
      if (abortController.signal.aborted) {
        setLogs(prev => [...prev.slice(-99), "WARN:\uc0ac\uc6a9\uc790\uc5d0 \uc758\ud574 \uc0dd\uc131\uc774 \ucde8\uc18c\ub418\uc5c8\uc2b5\ub2c8\ub2e4."]);
      } else {
        console.error(error);
        setErrorMessage("[\uc5f0\uacb0 \uc2e4\ud328] \ubc31\uc5d4\ub4dc \uc11c\ubc84\uc5d0 \uc5f0\uacb0\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  };

  // ── Render ──
  const processRenderLine = (ch: string, line: string) => {
    if (!line.startsWith("data:")) return;
    const rawData = line.slice(5).trim();
    if (!rawData) return;
    if (rawData.startsWith("DONE|")) {
      const videoPath = rawData.slice(5).split("|")[0].trim().replace(/\\/g, '/');
      const encodedPath = videoPath.split('/').map(encodeURIComponent).join('/');
      const normalizedPath = encodedPath.startsWith('/') ? encodedPath : `/${encodedPath}`;
      setRenderResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'done', progress: 100, videoUrl: `${API_BASE}${normalizedPath}` } }));
    } else if (rawData.startsWith("ERROR|")) {
      setRenderResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'error', errorMsg: rawData.slice(6) } }));
    } else if (rawData.startsWith("PROG|")) {
      const p = parseInt(rawData.slice(5), 10);
      if (!isNaN(p)) setRenderResults(prev => ({ ...prev, [ch]: { ...prev[ch], progress: p } }));
    } else {
      setRenderResults(prev => ({ ...prev, [ch]: { ...prev[ch], logs: [...(prev[ch]?.logs || []).slice(-49), rawData] } }));
    }
  };

  const renderForChannel = async (ch: string, preview: PreviewData, scripts: Record<number, string>, abortSignal: AbortSignal) => {
    const preset = CHANNEL_PRESETS[ch];
    const updatedCuts = preview.cuts.map((cut) => ({ index: cut.index, script: scripts[cut.index] ?? cut.script }));
    setRenderResults(prev => ({ ...prev, [ch]: { progress: 0, logs: [], status: 'rendering' } }));
    try {
      const response = await fetch(`${API_BASE}/api/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortSignal,
        body: JSON.stringify({
          sessionId: preview.sessionId, cuts: updatedCuts,
          elevenlabsKey: pickKey("elevenlabs") || undefined,
          ttsSpeed: preset?.ttsSpeed ?? ttsSpeed, videoEngine, cameraStyle, bgmTheme,
          formatType: formatType !== "auto" ? formatType : undefined,
          channel: ch, platforms: preset?.platforms ?? platforms,
          captionSize: preset?.captionSize ?? captionSize,
          captionY: preset?.captionY ?? captionY,
          outputPath: outputPath.trim() || undefined,
        }),
      });
      if (!response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) { if (buffer.trim()) processRenderLine(ch, buffer); break; }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) processRenderLine(ch, line);
      }
    } catch (error) {
      if (!abortSignal.aborted) {
        setRenderResults(prev => ({ ...prev, [ch]: { ...prev[ch], status: 'error', errorMsg: '\ub80c\ub354 \uc5f0\uacb0 \uc2e4\ud328' } }));
      }
    }
  };

  const handleGenerateScripts = async () => {
    const tab = activePreviewTab || activeRenderTab;
    if (!tab || !channelPreviews[tab]) return;
    const preview = channelPreviews[tab];
    const firstImg = preview.cuts[0]?.image_url || "";
    const folderMatch = firstImg.match(/\/assets\/([^/]+)\//);
    if (!folderMatch) return;
    const folder = folderMatch[1];
    const langMap: Record<string, string> = { askanything: "ko", wonderdrop: "en", exploratodo: "es", prismtale: "es" };
    const lang = langMap[tab] || "ko";

    setGeneratingScripts(true);
    try {
      const res = await fetch(`${API_BASE}/api/sessions/generate-scripts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder, topic: topic || preview.title, lang, channel: tab }),
      });
      const data = await res.json();
      if (data.error) { setErrorMessage(data.error); return; }
      const updatedCuts = preview.cuts.map((cut: any, i: number) => ({
        ...cut,
        script: data.cuts[i]?.script || cut.script,
        prompt: data.cuts[i]?.prompt || cut.prompt,
        description: data.cuts[i]?.description || cut.description,
      }));
      setChannelPreviews(prev => ({
        ...prev,
        [tab]: { ...preview, title: data.title || preview.title, cuts: updatedCuts },
      }));
    } catch {
      setErrorMessage("\uc2a4\ud06c\ub9bd\ud2b8 \uc0dd\uc131 \uc911 \uc624\ub958");
    } finally {
      setGeneratingScripts(false);
    }
  };

  const handleRender = async () => {
    const isMultiPreview = Object.keys(channelPreviews).length >= 1;
    if (!isMultiPreview && !previewData) return;

    setIsGenerating(true);
    setProgress(0);
    setLogs([]);
    setErrorMessage(null);
    setSuccessMessage(null);
    setGeneratedVideoUrl(null);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      if (isMultiPreview) {
        setRenderResults({});
        const channels = Object.keys(channelPreviews);
        setActiveRenderTab(channels[0]);
        for (const ch of channels) {
          await renderForChannel(ch, channelPreviews[ch], editedScriptsMap[ch] || {}, abortController.signal);
        }
        setRenderResults(prev => {
          const results = Object.values(prev);
          const doneCount = results.filter(r => r.status === 'done').length;
          if (doneCount > 0) setSuccessMessage(`${doneCount}/${channels.length} \ucc44\ub110 \ub80c\ub354\ub9c1 \uc644\ub8cc!`);
          return prev;
        });
        setPreviewMode(false);
        setChannelPreviews({});
      } else {
        const updatedCuts = previewData!.cuts.map((cut) => ({ index: cut.index, script: editedScripts[cut.index] ?? cut.script }));
        const response = await fetch(`${API_BASE}/api/render`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: abortController.signal,
          body: JSON.stringify({
            sessionId: previewData!.sessionId, cuts: updatedCuts,
            elevenlabsKey: pickKey("elevenlabs") || undefined,
            ttsSpeed, videoEngine, cameraStyle, bgmTheme,
            formatType: formatType !== "auto" ? formatType : undefined,
            channel: channel || undefined, platforms, captionSize, captionY,
            outputPath: outputPath.trim() || undefined,
          }),
        });
        await readSSE(response);
      }
    } catch (error) {
      if (abortController.signal.aborted) {
        setLogs(prev => [...prev.slice(-99), "WARN:\uc0ac\uc6a9\uc790\uc5d0 \uc758\ud574 \ub80c\ub354\ub9c1\uc774 \ucde8\uc18c\ub418\uc5c8\uc2b5\ub2c8\ub2e4."]);
      } else {
        console.error(error);
        setErrorMessage("[\uc5f0\uacb0 \uc2e4\ud328] \ub80c\ub354 \uc11c\ubc84\uc5d0 \uc5f0\uacb0\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  };

  // Image regenerate
  const regenerateImage = async (cutIndex: number, sessionId: string, model: string, channel?: string) => {
    setRegeneratingCut(cutIndex);
    try {
      const res = await fetch(`${API_BASE}/api/regenerate-image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId, cutIndex, model }),
      });
      let json: Record<string, unknown>;
      try { json = await res.json(); } catch { json = { error: "\uc11c\ubc84 \uc751\ub2f5 \ud30c\uc2f1 \uc2e4\ud328" }; }
      if (!res.ok) { setErrorMessage((json.error as string) || "\uc774\ubbf8\uc9c0 \uc7ac\uc0dd\uc131 \uc2e4\ud328"); return; }
      const newUrl = (json.image_url as string) + `?t=${Date.now()}`;
      if (channel) {
        setChannelPreviews(prev => {
          const cp = { ...prev };
          if (cp[channel]) {
            cp[channel] = { ...cp[channel], cuts: cp[channel].cuts.map(c => c.index === cutIndex ? { ...c, image_url: newUrl } : c) };
          }
          return cp;
        });
      } else {
        setPreviewData(prev => prev ? { ...prev, cuts: prev.cuts.map(c => c.index === cutIndex ? { ...c, image_url: newUrl } : c) } : prev);
      }
    } catch { setErrorMessage("\uc774\ubbf8\uc9c0 \uc7ac\uc0dd\uc131 \uc911 \uc624\ub958 \ubc1c\uc0dd"); }
    finally { setRegeneratingCut(null); }
  };

  // Image replace
  const replaceImage = async (file: File, cutIndex: number, sessionId: string, channel?: string) => {
    const ALLOWED = ["image/png", "image/jpeg", "image/webp"];
    if (!ALLOWED.includes(file.type)) { setErrorMessage("PNG, JPG, WEBP \ud30c\uc77c\ub9cc \uac00\ub2a5\ud569\ub2c8\ub2e4."); return; }
    if (file.size > 20 * 1024 * 1024) { setErrorMessage("\ud30c\uc77c \ud06c\uae30\uac00 20MB\ub97c \ucd08\uacfc\ud569\ub2c8\ub2e4."); return; }
    setReplacingCut(cutIndex);
    try {
      const fd = new FormData();
      fd.append("sessionId", sessionId);
      fd.append("cutIndex", String(cutIndex));
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/api/replace-image`, { method: "POST", body: fd });
      const json = await res.json();
      if (!res.ok) { setErrorMessage(json.error || "\uc774\ubbf8\uc9c0 \uad50\uccb4 \uc2e4\ud328"); return; }
      const newUrl = json.image_url + `?t=${Date.now()}`;
      if (channel) {
        setChannelPreviews(prev => {
          const cp = { ...prev };
          if (cp[channel]) {
            cp[channel] = { ...cp[channel], cuts: cp[channel].cuts.map(c => c.index === cutIndex ? { ...c, image_url: newUrl } : c) };
          }
          return cp;
        });
      } else {
        setPreviewData(prev => prev ? { ...prev, cuts: prev.cuts.map(c => c.index === cutIndex ? { ...c, image_url: newUrl } : c) } : prev);
      }
    } catch { setErrorMessage("\uc774\ubbf8\uc9c0 \uad50\uccb4 \uc911 \uc624\ub958 \ubc1c\uc0dd"); }
    finally { setReplacingCut(null); }
  };

  // Session management
  const loadSessionList = async (
    setSavedSessions: (s: any[]) => void,
    setShowSessionBrowser: (s: boolean) => void,
  ) => {
    try {
      const res = await fetch(`${API_BASE}/api/sessions`);
      const data = await res.json();
      setSavedSessions(data.sessions || []);
      setShowSessionBrowser(true);
    } catch { setErrorMessage("\uc138\uc158 \ubaa9\ub85d \ub85c\ub4dc \uc2e4\ud328"); }
  };

  const restoreSession = async (
    folders: string[],
    setTopicFn: (s: string) => void,
    setShowSessionBrowser: (s: boolean) => void,
  ) => {
    try {
      setChannelPreviews({});
      setPreviewData(null);
      setEditedScripts({});
      setEditedScriptsMap({});
      setRegeneratingCut(null);
      setRenderResults({});
      setSuccessMessage(null);
      setErrorMessage(null);
      setProgress(0);
      const newPreviews: Record<string, PreviewData> = {};
      let lastTitle = "";
      for (const folder of folders) {
        const res = await fetch(`${API_BASE}/api/sessions/load`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ folder }),
        });
        if (!res.ok) { console.error(`\uc138\uc158 \ub85c\ub4dc \uc2e4\ud328 (${folder}):`, res.status, await res.text().catch(() => "")); continue; }
        const data = await res.json();
        const channel = data.channel || folder;
        newPreviews[channel] = { sessionId: data.sessionId, title: data.title, channel, cuts: data.cuts };
        lastTitle = data.title;
        if (data.recommendedVideoEngine) {
          setVideoEngine(data.recommendedVideoEngine);
          if (data.recommendedVideoModel) setVideoModel(data.recommendedVideoModel);
        }
      }
      if (Object.keys(newPreviews).length === 0) { setErrorMessage("\uc138\uc158 \ubcf5\uc6d0 \uc2e4\ud328"); return; }
      if (Object.keys(newPreviews).length === 1 && !Object.values(newPreviews)[0].channel) {
        setPreviewData(Object.values(newPreviews)[0]);
      } else {
        const channelOrder = ["askanything", "wonderdrop", "exploratodo", "prismtale"];
        const sorted: Record<string, PreviewData> = {};
        for (const ch of channelOrder) { if (newPreviews[ch]) sorted[ch] = newPreviews[ch]; }
        for (const ch of Object.keys(newPreviews)) { if (!sorted[ch]) sorted[ch] = newPreviews[ch]; }
        setChannelPreviews(sorted);
        setActivePreviewTab(Object.keys(sorted)[0]);
      }
      setTopicFn(lastTitle);
      setPreviewMode(true);
      setShowSessionBrowser(false);
    } catch (e) {
      console.error("\uc138\uc158 \ubcf5\uc6d0 \uc624\ub958:", e);
      setErrorMessage("\uc138\uc158 \ubcf5\uc6d0 \uc911 \uc624\ub958: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  // Batch generate images
  const handleBatchGenerateImages = async (currentPreview: PreviewData | null) => {
    const allChannels = Object.keys(channelPreviews);
    if (allChannels.length === 0 && currentPreview) {
      allChannels.push(currentPreview.channel || "default");
    }
    const totalChannels = allChannels.length;
    let totalDone = 0;
    const totalImages = allChannels.reduce((sum, ch) => sum + (channelPreviews[ch]?.cuts?.length || currentPreview?.cuts?.length || 0), 0);

    setLogs([`\ud83d\uddbc\ufe0f \uc804\uccb4 \uc774\ubbf8\uc9c0 \uc0dd\uc131 \uc2dc\uc791 \u2014 ${totalChannels}\ucc44\ub110 \u00d7 ${Math.round(totalImages / totalChannels)}\ucef7 = ${totalImages}\uc7a5`]);
    setProgress(1);

    for (let ci = 0; ci < allChannels.length; ci++) {
      const ch = allChannels[ci];
      const preview = channelPreviews[ch] || currentPreview;
      if (!preview?.sessionId) continue;

      setLogs(prev => [...prev.slice(-99), `\ud83d\udcf8 [${ci + 1}/${totalChannels}] ${ch} \uc774\ubbf8\uc9c0 \uc0dd\uc131 \uc911...`]);

      try {
        const res = await fetch(`${API_BASE}/api/batch-generate-images`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sessionId: preview.sessionId, model: "standard" }),
        });
        const data = await res.json();

        if (data.ok && data.results) {
          const updatedCuts = [...preview.cuts];
          for (const r of data.results) {
            if (r.ok && r.image_url && updatedCuts[r.index]) {
              updatedCuts[r.index] = { ...updatedCuts[r.index], image_url: r.image_url };
            }
          }
          setChannelPreviews(prev => ({ ...prev, [ch]: { ...prev[ch], cuts: updatedCuts } }));
          totalDone += data.success || 0;
          setProgress(Math.round((totalDone / totalImages) * 100));
          setLogs(prev => [...prev.slice(-99), `\u2705 ${ch}: ${data.success}/${data.total}\uc7a5 \uc644\ub8cc (\uc804\uccb4 ${totalDone}/${totalImages})`]);
        } else {
          setLogs(prev => [...prev.slice(-99), `\u274c ${ch} \uc2e4\ud328: ${data.error || "\uc54c \uc218 \uc5c6\ub294 \uc624\ub958"}`]);
        }
      } catch (err) {
        setLogs(prev => [...prev.slice(-99), `\u274c ${ch} \uc5d0\ub7ec: ${err}`]);
      }
    }
    setProgress(100);
    setLogs(prev => [...prev.slice(-99), `\ud83c\udf89 \uc804\uccb4 \uc774\ubbf8\uc9c0 \uc0dd\uc131 \uc644\ub8cc! ${totalDone}/${totalImages}\uc7a5`]);
  };

  return {
    isGenerating, progress, logs, successMessage, errorMessage,
    generatedVideoPath, generatedVideoUrl, isDownloading, setIsDownloading,
    setGeneratedVideoPath, setGeneratedVideoUrl,
    previewMode, setPreviewMode,
    previewData, setPreviewData,
    editedScripts, setEditedScripts,
    channelPreviews, setChannelPreviews,
    activePreviewTab, setActivePreviewTab,
    editedScriptsMap, setEditedScriptsMap,
    replacingCut, regeneratingCut, generatingScripts,
    channelResults, setChannelResults,
    renderResults, setRenderResults,
    activeRenderTab, setActiveRenderTab,
    setSuccessMessage, setErrorMessage, setProgress, setLogs,
    handleGenerate, handleCancel, handleClearError,
    handlePrepare, handleRender,
    handleGenerateScripts,
    regenerateImage, replaceImage,
    loadSessionList, restoreSession,
    handleBatchGenerateImages,
    detectedRefUrl,
  };
}

export type SSEGenerate = ReturnType<typeof useSSEGenerate>;
