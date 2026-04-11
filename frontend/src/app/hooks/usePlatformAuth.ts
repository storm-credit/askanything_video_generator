"use client";

import { useState, useCallback } from "react";
import { API_BASE } from "../constants";

export function usePlatformAuth() {
  const [ytConnected, setYtConnected] = useState(false);
  const [ytChannelStatus, setYtChannelStatus] = useState<Record<string, boolean>>({});
  const [ytChannels, setYtChannels] = useState<{ id: string; title: string; connected: boolean }[]>([]);
  const [ytSelectedChannel, setYtSelectedChannel] = useState<string>("");
  const [ttConnected, setTtConnected] = useState(false);
  const [igConnected, setIgConnected] = useState(false);

  const checkPlatformStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/upload/platforms`);
      if (res.ok) {
        const data = await res.json();
        if (data.youtube) {
          setYtConnected(data.youtube.connected === true);
          if (data.youtube.channels) {
            setYtChannels(data.youtube.channels);
            setYtSelectedChannel(prev => {
              if (!prev && data.youtube.channels.length > 0) return data.youtube.channels[0].id;
              return prev;
            });
          }
          try {
            const ytStatusRes = await fetch(`${API_BASE}/api/youtube/status`);
            if (ytStatusRes.ok) {
              const ytStatusData = await ytStatusRes.json();
              if (ytStatusData.channel_status) setYtChannelStatus(ytStatusData.channel_status);
            }
          } catch {}
        }
        if (data.tiktok) setTtConnected(data.tiktok.connected === true);
        if (data.instagram) setIgConnected(data.instagram.connected === true);
      }
    } catch {}
  }, []);

  const handlePlatformAuth = async (
    platform: "youtube" | "tiktok" | "instagram",
    uploadChannel: string,
    onError: (msg: string) => void
  ) => {
    try {
      const body: Record<string, string> = {};
      if (uploadChannel) body.channel = uploadChannel;
      const res = await fetch(`${API_BASE}/api/${platform}/auth`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.auth_url) {
        window.open(data.auth_url, `${platform}_auth`, "width=600,height=700");
        let pollId: ReturnType<typeof setInterval> | null = null;
        let timeoutId: ReturnType<typeof setTimeout> | null = null;
        const cleanup = () => { if (pollId) clearInterval(pollId); if (timeoutId) clearTimeout(timeoutId); };
        pollId = setInterval(async () => {
          try {
            const check = await fetch(`${API_BASE}/api/${platform}/status`);
            const status = await check.json();
            if (status.connected) {
              if (platform === "youtube") setYtConnected(true);
              else if (platform === "tiktok") setTtConnected(true);
              else if (platform === "instagram") setIgConnected(true);
              cleanup();
            }
          } catch {
            cleanup();
          }
        }, 2000);
        timeoutId = setTimeout(cleanup, 120000);
      } else if (data.error) {
        onError(data.error);
      }
    } catch {
      onError(`${platform} \uc778\uc99d \uc11c\ubc84\uc5d0 \uc5f0\uacb0\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.`);
    }
  };

  return {
    ytConnected, setYtConnected,
    ytChannelStatus,
    ytChannels,
    ytSelectedChannel, setYtSelectedChannel,
    ttConnected, setTtConnected,
    igConnected, setIgConnected,
    checkPlatformStatus,
    handlePlatformAuth,
  };
}

export type PlatformAuth = ReturnType<typeof usePlatformAuth>;
