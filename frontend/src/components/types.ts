export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8004";

export interface KeyStatus {
  openai: boolean;
  elevenlabs: boolean;
  gemini: boolean;
  claude_key: boolean;
  kling_access: boolean;
  kling_secret: boolean;
  tavily: boolean;
}

export interface KeyConfig {
  id: string;
  label: string;
  description: string;
  envName: string;
  statusKey: keyof KeyStatus;
  required: boolean;
  multiKey: boolean;
  group: "core" | "extra";
}

export interface KeyUsageEntry {
  key: string;
  usage: Record<string, number>;
  total: number;
  state: string;
  blocked: boolean;
  blocked_services: Record<string, number>;
  unblock_hours: number;
}

export interface KeyUsageStats {
  total_keys: number;
  keys: KeyUsageEntry[];
}

export const KEY_CONFIGS: KeyConfig[] = [
  // ── 핵심 키 (Google 또는 OpenAI 중 하나 + ElevenLabs = 최소 구성) ──
  {
    id: "gemini",
    label: "Google API Key",
    description: "Gemini 기획 + Imagen 이미지 + Veo3 비디오 (Google AI Studio 발급)",
    envName: "GEMINI_API_KEY",
    statusKey: "gemini",
    required: false,
    multiKey: true,
    group: "core",
  },
  {
    id: "openai",
    label: "OpenAI API Key",
    description: "GPT 기획 + DALL-E 이미지 + Whisper 자막 + Sora2 비디오",
    envName: "OPENAI_API_KEY",
    statusKey: "openai",
    required: false,
    multiKey: true,
    group: "core",
  },
  {
    id: "elevenlabs",
    label: "ElevenLabs API Key",
    description: "TTS 음성 내레이션 (대체 없음, 필수)",
    envName: "ELEVENLABS_API_KEY",
    statusKey: "elevenlabs",
    required: true,
    multiKey: true,
    group: "core",
  },
  // ── 추가 엔진 ──
  {
    id: "claude_key",
    label: "Claude API Key",
    description: "기획 엔진 대안 (Anthropic Console 발급)",
    envName: "ANTHROPIC_API_KEY",
    statusKey: "claude_key",
    required: false,
    multiKey: false,
    group: "extra",
  },
  {
    id: "kling_access",
    label: "Kling Access Key",
    description: "Kling AI 비디오 엔진 (Access Key)",
    envName: "KLING_ACCESS_KEY",
    statusKey: "kling_access",
    required: false,
    multiKey: false,
    group: "extra",
  },
  {
    id: "kling_secret",
    label: "Kling Secret Key",
    description: "Kling AI 비디오 엔진 (Secret Key)",
    envName: "KLING_SECRET_KEY",
    statusKey: "kling_secret",
    required: false,
    multiKey: false,
    group: "extra",
  },
  {
    id: "tavily",
    label: "Tavily API Key",
    description: "팩트체크 웹 검색 (선택사항)",
    envName: "TAVILY_API_KEY",
    statusKey: "tavily",
    required: false,
    multiKey: false,
    group: "extra",
  },
];
