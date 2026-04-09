"""FailureAnalyzer — 실패 분류 + 로그 기록 + 텔레그램 상세 알림.

파이프라인 실패 시 자동 호출되어:
1. 에러 메시지에서 실패 유형 분류
2. JSON 로그 파일에 기록
3. 텔레그램에 상세 사유 전송
4. 재시도 가능 여부 판단
"""

from __future__ import annotations

import os
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any

KST = timezone(timedelta(hours=9))

# 실패 유형 분류 규칙
FAILURE_TYPES = {
    "CUT_COUNT": {
        "keywords": ["컷 수", "미달", "HARD FAIL"],
        "label": "컷 수 미달",
        "retryable": True,
        "emoji": "📝",
        "fix": "LLM 재생성 필요 (모델/프롬프트 문제)",
    },
    "REMOTION": {
        "keywords": ["Remotion", "렌더링 실패", "PIPELINE_ERROR"],
        "label": "Remotion 렌더링 실패",
        "retryable": True,
        "emoji": "🎬",
        "fix": "영상 코덱 문제 — 리트라이로 해결 가능",
    },
    "GEMINI_QUOTA": {
        "keywords": ["할당량 초과", "RESOURCE_EXHAUSTED", "429"],
        "label": "Gemini 할당량 초과",
        "retryable": True,
        "emoji": "🔑",
        "fix": "API 쿼터 리셋 대기 또는 키 추가",
    },
    "YOUTUBE_QUOTA": {
        "keywords": ["exceeded your", "youtube.*403", "업로드 실패"],
        "label": "YouTube 쿼터 초과",
        "retryable": True,
        "emoji": "📺",
        "fix": "내일 쿼터 리셋 후 자동 재시도",
    },
    "PERMISSION": {
        "keywords": ["PERMISSION_DENIED", "403"],
        "label": "권한 부족",
        "retryable": False,
        "emoji": "🔒",
        "fix": "Google Cloud IAM 권한 추가 필요",
    },
    "TIMEOUT": {
        "keywords": ["timeout", "타임아웃"],
        "label": "타임아웃",
        "retryable": True,
        "emoji": "⏰",
        "fix": "네트워크/서버 부하 — 리트라이로 해결 가능",
    },
    "UNKNOWN": {
        "keywords": [],
        "label": "알 수 없는 오류",
        "retryable": False,
        "emoji": "❓",
        "fix": "수동 확인 필요",
    },
}

LOG_FILE = os.path.join("assets", "_failure_log.json")


def classify_failure(error_msg: str) -> dict:
    """에러 메시지에서 실패 유형 분류."""
    error_lower = error_msg.lower()
    for type_id, info in FAILURE_TYPES.items():
        if type_id == "UNKNOWN":
            continue
        for kw in info["keywords"]:
            if kw.lower() in error_lower:
                return {"type": type_id, **info}
    return {"type": "UNKNOWN", **FAILURE_TYPES["UNKNOWN"]}


def log_failure(channel: str, topic: str, error_msg: str,
                agent: str = "", extra: dict | None = None) -> dict:
    """실패를 JSON 로그에 기록하고 분류 결과 반환."""
    classification = classify_failure(error_msg)

    entry = {
        "timestamp": datetime.now(KST).isoformat(),
        "channel": channel,
        "topic": topic,
        "agent": agent,
        "error": error_msg[:300],
        "type": classification["type"],
        "label": classification["label"],
        "retryable": classification["retryable"],
        "fix": classification["fix"],
        **(extra or {}),
    }

    # JSON 로그 파일에 추가
    try:
        os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
        logs = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        logs.append(entry)
        # 최근 100건만 유지
        if len(logs) > 100:
            logs = logs[-100:]
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[FailureAnalyzer] 로그 저장 실패: {e}")

    return entry


def send_failure_telegram(entry: dict):
    """텔레그램으로 상세 실패 알림."""
    try:
        from modules.utils.notify import send_telegram
    except ImportError:
        print("[FailureAnalyzer] 텔레그램 모듈 없음")
        return

    classification = FAILURE_TYPES.get(entry["type"], FAILURE_TYPES["UNKNOWN"])
    emoji = classification["emoji"]
    retry_text = "🔄 자동 재시도 가능" if entry["retryable"] else "⛔ 수동 처리 필요"

    msg = (
        f"━━━━━━━━━━━━━━━\n"
        f"{emoji} 실패 분석\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 채널: {entry['channel']}\n"
        f"📝 토픽: {entry['topic']}\n"
        f"🏷️ 유형: {entry['label']}\n"
        f"💡 원인: {entry['error'][:100]}\n"
        f"🔧 조치: {entry['fix']}\n"
        f"{retry_text}\n"
        f"⏰ {entry['timestamp'][:19]}"
    )

    try:
        send_telegram(msg)
    except Exception as e:
        print(f"[FailureAnalyzer] 텔레그램 전송 실패: {e}")


def analyze_and_notify(channel: str, topic: str, error_msg: str,
                       agent: str = "") -> dict:
    """실패 분석 + 로그 기록 + 텔레그램 알림 (통합 함수)."""
    entry = log_failure(channel, topic, error_msg, agent)
    send_failure_telegram(entry)
    return entry


def get_failure_summary(date: str | None = None) -> dict:
    """실패 로그 요약 (날짜별)."""
    if not os.path.exists(LOG_FILE):
        return {"total": 0, "by_type": {}, "entries": []}

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        logs = json.load(f)

    if date:
        logs = [l for l in logs if l["timestamp"][:10] == date]

    by_type: dict[str, int] = {}
    for l in logs:
        t = l.get("type", "UNKNOWN")
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "total": len(logs),
        "by_type": by_type,
        "retryable": sum(1 for l in logs if l.get("retryable")),
        "entries": logs[-20:],  # 최근 20건
    }
