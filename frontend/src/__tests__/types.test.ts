import { describe, it, expect } from "vitest";
import { API_BASE, KEY_CONFIGS } from "../components/types";

describe("API_BASE", () => {
  it("defaults to localhost:8003", () => {
    expect(API_BASE).toBe("http://localhost:8003");
  });
});

describe("KEY_CONFIGS", () => {
  it("has correct number of configs", () => {
    expect(KEY_CONFIGS.length).toBe(6);
  });

  it("required keys are openai and elevenlabs", () => {
    const required = KEY_CONFIGS.filter((c) => c.required).map((c) => c.id);
    expect(required).toContain("openai");
    expect(required).toContain("elevenlabs");
    expect(required.length).toBe(2);
  });

  it("all configs have required fields", () => {
    for (const config of KEY_CONFIGS) {
      expect(config.id).toBeTruthy();
      expect(config.label).toBeTruthy();
      expect(config.description).toBeTruthy();
      expect(config.envName).toBeTruthy();
      expect(config.statusKey).toBeTruthy();
      expect(typeof config.required).toBe("boolean");
      expect(typeof config.multiKey).toBe("boolean");
    }
  });

  it("multiKey configs are openai and elevenlabs", () => {
    const multiKey = KEY_CONFIGS.filter((c) => c.multiKey).map((c) => c.id);
    expect(multiKey).toContain("openai");
    expect(multiKey).toContain("elevenlabs");
  });

  it("gemini config exists with correct envName", () => {
    const gemini = KEY_CONFIGS.find((c) => c.id === "gemini");
    expect(gemini).toBeDefined();
    expect(gemini!.envName).toBe("GEMINI_API_KEY");
    expect(gemini!.required).toBe(false);
  });

  it("claude config has correct envName", () => {
    const claude = KEY_CONFIGS.find((c) => c.id === "claude_key");
    expect(claude).toBeDefined();
    expect(claude!.envName).toBe("ANTHROPIC_API_KEY");
  });

  it("kling configs are optional", () => {
    const klingAccess = KEY_CONFIGS.find((c) => c.id === "kling_access");
    const klingSecret = KEY_CONFIGS.find((c) => c.id === "kling_secret");
    expect(klingAccess!.required).toBe(false);
    expect(klingSecret!.required).toBe(false);
  });
});
