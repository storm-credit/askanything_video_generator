import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProgressPanel } from "../components/ProgressPanel";

describe("ProgressPanel", () => {
  it("shows waiting message when no logs", () => {
    render(<ProgressPanel progress={0} logs={[]} />);
    expect(screen.getByText(/서버 응답 대기 중/)).toBeInTheDocument();
  });

  it("displays progress percentage", () => {
    render(<ProgressPanel progress={42} logs={[]} />);
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("renders log messages", () => {
    const logs = ["기획 완료", "이미지 생성 중..."];
    render(<ProgressPanel progress={50} logs={logs} />);
    expect(screen.getByText("기획 완료")).toBeInTheDocument();
    expect(screen.getByText("이미지 생성 중...")).toBeInTheDocument();
  });

  it("renders error logs with stripped prefix", () => {
    render(<ProgressPanel progress={0} logs={["ERROR:서버 오류"]} />);
    expect(screen.getByText("서버 오류")).toBeInTheDocument();
  });

  it("renders warning logs with stripped prefix", () => {
    render(<ProgressPanel progress={0} logs={["WARN:경고 메시지"]} />);
    expect(screen.getByText("경고 메시지")).toBeInTheDocument();
  });

  it("shows 0% progress initially", () => {
    render(<ProgressPanel progress={0} logs={[]} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("shows 100% progress when complete", () => {
    render(<ProgressPanel progress={100} logs={["완료"]} />);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });
});
