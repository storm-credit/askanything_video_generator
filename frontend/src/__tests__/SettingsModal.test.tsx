import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SettingsModal } from "../components/SettingsModal";
import type { KeyStatus, KeyUsageStats } from "../components/types";

const defaultProps = {
  serverKeyStatus: {
    openai: true,
    elevenlabs: false,
    gemini: true,
    claude_key: false,
    kling_access: false,
    kling_secret: false,
  } as KeyStatus,
  savedKeys: { openai: ["sk-test123456789012"] } as Record<string, string[]>,
  inputValues: {} as Record<string, string>,
  visibleKeys: {} as Record<string, boolean>,
  outputPath: "",
  keyUsageStats: null as KeyUsageStats | null,
  totalServerKeys: 2,
  totalSavedKeys: 1,
  googleKeyCount: 0,
  serverMaskedKeys: {},
  onClose: vi.fn(),
  onInputChange: vi.fn(),
  onAddKey: vi.fn(),
  onRemoveKey: vi.fn(),
  onToggleVisible: vi.fn(),
  onOutputPathChange: vi.fn(),
};

describe("SettingsModal", () => {
  it("renders modal with title", () => {
    render(<SettingsModal {...defaultProps} />);
    expect(screen.getByText("설정")).toBeInTheDocument();
    expect(screen.getByText("API 키, 엔진, 채널 관리")).toBeInTheDocument();
  });

  it("shows required key sections", () => {
    render(<SettingsModal {...defaultProps} />);
    expect(screen.getByText("Google API Key")).toBeInTheDocument();
    expect(screen.getByText("OpenAI API Key")).toBeInTheDocument();
    expect(screen.getByText("ElevenLabs API Key")).toBeInTheDocument();
  });

  it("shows server status indicators", () => {
    render(<SettingsModal {...defaultProps} />);
    expect(screen.getByText("서버 설정됨")).toBeInTheDocument();
    expect(screen.getByText("1키 등록됨")).toBeInTheDocument();
  });

  it("shows footer key counts", () => {
    render(<SettingsModal {...defaultProps} />);
    expect(screen.getByText(/서버 키 2개/)).toBeInTheDocument();
    expect(screen.getByText(/브라우저 키 1개/)).toBeInTheDocument();
  });

  it("calls onClose when close button clicked", () => {
    const onClose = vi.fn();
    render(<SettingsModal {...defaultProps} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText("설정 닫기"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose on Escape key", () => {
    const onClose = vi.fn();
    render(<SettingsModal {...defaultProps} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when 완료 button clicked", () => {
    const onClose = vi.fn();
    render(<SettingsModal {...defaultProps} onClose={onClose} />);
    fireEvent.click(screen.getByText("완료"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows saved key masked by default", () => {
    render(<SettingsModal {...defaultProps} />);
    expect(screen.getByText("sk-t...9012")).toBeInTheDocument();
  });

  it("shows output path section", () => {
    render(<SettingsModal {...defaultProps} />);
    expect(screen.getByText("저장 경로")).toBeInTheDocument();
  });

  it("shows extra engine keys section", () => {
    render(<SettingsModal {...defaultProps} />);
    fireEvent.click(screen.getByText("추가 엔진"));
    expect(screen.getByText("Claude API Key")).toBeInTheDocument();
    expect(screen.getByText("Kling Access Key")).toBeInTheDocument();
  });
});
