export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface KeyStatus {
  openai: boolean;
  elevenlabs: boolean;
  gemini: boolean;
  claude_key: boolean;
  kling_access: boolean;
  kling_secret: boolean;
}

export interface KeyConfig {
  id: string;
  label: string;
  description: string;
  envName: string;
  statusKey: keyof KeyStatus;
  required: boolean;
  multiKey: boolean;
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
  {
    id: "openai",
    label: "OpenAI API Key",
    description: "GPT 기획, DALL-E 이미지, Whisper 자막, Sora 2 비디오에 사용",
    envName: "OPENAI_API_KEY",
    statusKey: "openai",
    required: true,
    multiKey: true,
  },
  {
    id: "elevenlabs",
    label: "ElevenLabs API Key",
    description: "TTS 음성 내레이션 생성에 사용",
    envName: "ELEVENLABS_API_KEY",
    statusKey: "elevenlabs",
    required: true,
    multiKey: true,
  },
  {
    id: "gemini",
    label: "Gemini API Key",
    description: "Gemini 기획 엔진에 사용 (Google AI Studio에서 발급)",
    envName: "GEMINI_API_KEY",
    statusKey: "gemini",
    required: false,
    multiKey: false,
  },
  {
    id: "claude_key",
    label: "Claude API Key",
    description: "Claude 기획 엔진에 사용 (Anthropic Console에서 발급)",
    envName: "ANTHROPIC_API_KEY",
    statusKey: "claude_key",
    required: false,
    multiKey: false,
  },
  {
    id: "kling_access",
    label: "Kling Access Key",
    description: "Kling AI 직접 연동",
    envName: "KLING_ACCESS_KEY",
    statusKey: "kling_access",
    required: false,
    multiKey: false,
  },
  {
    id: "kling_secret",
    label: "Kling Secret Key",
    description: "Kling AI 시크릿 키",
    envName: "KLING_SECRET_KEY",
    statusKey: "kling_secret",
    required: false,
    multiKey: false,
  },
];
