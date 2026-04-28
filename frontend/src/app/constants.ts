export { API_BASE } from "../components/types";

// Channel presets
export const CHANNEL_PRESETS: Record<string, { label: string; flag: string; language: string; ttsSpeed: number; platforms: string[]; captionSize: number; captionY: number; cameraStyle: string }> = {
  askanything: { label: "AskAnything", flag: "\ud83c\uddf0\ud83c\uddf7", language: "ko", ttsSpeed: 1.3, platforms: ["youtube"], captionSize: 58, captionY: 38, cameraStyle: "cinematic" },
  wonderdrop: { label: "WonderDrop", flag: "\ud83c\uddfa\ud83c\uddf8", language: "en", ttsSpeed: 1.05, platforms: ["youtube"], captionSize: 54, captionY: 38, cameraStyle: "cinematic" },
  exploratodo: { label: "ExploraTodo", flag: "\ud83c\uddea\ud83c\uddf8", language: "es", ttsSpeed: 1.05, platforms: ["youtube"], captionSize: 54, captionY: 38, cameraStyle: "cinematic" },
  prismtale: { label: "Prism Tale", flag: "\ud83c\uddea\ud83c\uddf8", language: "es", ttsSpeed: 1.05, platforms: ["youtube"], captionSize: 54, captionY: 38, cameraStyle: "cinematic" },
};

// localStorage helpers
let _hydrated = false;
export const setHydrated = (v: boolean) => { _hydrated = v; };
export const isHydrated = () => _hydrated;

export const loadSetting = <T,>(key: string, fallback: T): T => {
  if (!_hydrated || typeof window === "undefined") return fallback;
  try { const v = localStorage.getItem(`aa_${key}`); return v !== null ? JSON.parse(v) : fallback; } catch { return fallback; }
};

export const saveSetting = (key: string, value: unknown) => {
  if (typeof window === "undefined") return;
  try { localStorage.setItem(`aa_${key}`, JSON.stringify(value)); } catch { /* quota exceeded */ }
};

// Shared types
export type PreviewData = {
  sessionId: string;
  title: string;
  channel?: string;
  description?: string;
  tags?: string[];
  cuts: { index: number; script: string; prompt: string; description?: string; image_url: string | null; ab_variants?: string[] }[];
};

export type ChannelStatus = {
  progress: number;
  logs: string[];
  status: 'idle' | 'generating' | 'done' | 'error';
  videoUrl?: string;
  errorMsg?: string;
  genId?: string;
};

export type RenderResult = {
  progress: number;
  logs: string[];
  status: 'rendering' | 'done' | 'error';
  videoUrl?: string;
  errorMsg?: string;
};

export const VIDEO_MODEL_LABELS: Record<string, string> = {
  "hero-only": "Hero Only",
  "veo-3.1-fast-generate-001": "Veo 3.1 Fast",
  "veo-3.1-generate-001": "Veo 3.1 Standard",
  "veo-3.0-fast-generate-001": "Veo 3 Fast",
  "veo-3.0-generate-001": "Veo 3 Standard",
};

// LLM/Image/Video model options (requires remainLabel function from caller)
export const getLLM_MODELS = (remainLabel: (id: string) => string): Record<string, { value: string; label: string }[]> => ({
  gemini: [
    { value: "", label: `Gemini 2.5 Pro (\uae30\ubcf8)${remainLabel("gemini-2.5-pro")}` },
    { value: "gemini-2.5-flash", label: `Gemini 2.5 Flash${remainLabel("gemini-2.5-flash")}` },
    { value: "gemini-2.0-flash", label: `Gemini 2.0 Flash${remainLabel("gemini-2.0-flash")}` },
  ],
  openai: [
    { value: "", label: `GPT-4o (\uae30\ubcf8)${remainLabel("gpt-4o")}` },
    { value: "gpt-4o-mini", label: `GPT-4o Mini${remainLabel("gpt-4o-mini")}` },
    { value: "gpt-4.1", label: `GPT-4.1${remainLabel("gpt-4.1")}` },
    { value: "gpt-4.1-mini", label: `GPT-4.1 Mini${remainLabel("gpt-4.1-mini")}` },
  ],
  claude: [
    { value: "", label: `Claude Sonnet 4 (\uae30\ubcf8)${remainLabel("claude-sonnet-4-20250514")}` },
    { value: "claude-opus-4-20250514", label: `Claude Opus 4${remainLabel("claude-opus-4-20250514")}` },
    { value: "claude-haiku-4-5-20251001", label: `Claude Haiku 3.5${remainLabel("claude-haiku-4-5-20251001")}` },
  ],
});

export const getIMAGE_MODELS = (remainLabel: (id: string) => string): Record<string, { value: string; label: string }[]> => ({
  imagen: [
    { value: "", label: `Imagen 4 Standard (\uae30\ubcf8)${remainLabel("imagen-4.0-generate-001")}` },
    { value: "imagen-4.0-fast-generate-001", label: `Imagen 4 Fast${remainLabel("imagen-4.0-fast-generate-001")}` },
  ],
  nano_banana: [
    { value: "", label: "Gemini Flash Image (\uae30\ubcf8)" },
  ],
  dalle: [
    { value: "", label: `DALL-E 3 (\uae30\ubcf8)${remainLabel("dall-e-3")}` },
  ],
});

export const getVIDEO_MODELS = (remainLabel: (id: string) => string): Record<string, { value: string; label: string }[]> => ({
  veo3: [
    { value: "", label: `Veo 3.1 Fast (\uae30\ubcf8)${remainLabel("veo-3.1-fast-generate-001")}` },
    { value: "veo-3.1-fast-generate-001", label: `Veo 3.1 Fast${remainLabel("veo-3.1-fast-generate-001")}` },
    { value: "veo-3.1-generate-001", label: `Veo 3.1 Standard${remainLabel("veo-3.1-generate-001")}` },
    { value: "veo-3.0-fast-generate-001", label: `Veo 3 Fast${remainLabel("veo-3.0-fast-generate-001")}` },
    { value: "veo-3.0-generate-001", label: `Veo 3 Standard${remainLabel("veo-3.0-generate-001")}` },
    { value: "hero-only", label: "Hero Only (SHOCK/REVEAL\ub9cc \uc601\uc0c1)" },
  ],
  sora2: [{ value: "", label: "Sora 2 (\uae30\ubcf8)" }],
  kling: [{ value: "", label: "Kling v1 (\uae30\ubcf8)" }],
  blender: [
    { value: "solar_system", label: "\ud0dc\uc591\uacc4 \ud06c\uae30 \ube44\uad50" },
    { value: "giant_stars", label: "\ubcc4 \ud06c\uae30 \ube44\uad50" },
  ],
  none: [],
});
