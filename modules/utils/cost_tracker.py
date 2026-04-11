"""비용 추적기 — 영상 생성 비용 원화 환산 + 일별 집계.

단가 기준 (USD):
  Gemini 2.5 Pro:   $1.25/M input,  $10.0/M output
  Gemini 2.5 Flash: $0.15/M input,  $0.60/M output
  Gemini 2.0 Flash: $0.10/M input,  $0.40/M output
  Imagen 4 Std:     $0.04/image
  Veo3:             $0.50/clip  (Vertex AI 추정)
  ElevenLabs:       $0.30/1K chars

환율: 1 USD = EXCHANGE_RATE KRW (고정)
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

KST = timezone(timedelta(hours=9))
EXCHANGE_RATE = int(os.getenv("EXCHANGE_RATE", "1380"))  # KRW per USD

# ── 단가 테이블 (USD) ──
PRICE = {
    # LLM — 모델명 prefix 매칭
    "gemini-2.5-pro":   {"input": 1.25 / 1_000_000, "output": 10.0 / 1_000_000},
    "gemini-2.5-flash": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gemini-2.0-flash": {"input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000},
    # 이미지/비디오/TTS
    "imagen4":          0.04,   # per image
    "veo3":             0.50,   # per clip
    "elevenlabs":       0.30 / 1_000,  # per char
    "whisper":          0.006 / 60,   # per second ($0.006/min)
}

_DAILY_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "assets", ".daily_cost.json")
_lock = threading.Lock()


def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _load_daily() -> dict:
    try:
        path = os.path.abspath(_DAILY_FILE)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_daily(data: dict):
    try:
        path = os.path.abspath(_DAILY_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CostTracker] 저장 실패: {e}")


# ── 단가 조회 ──

def _llm_price(model: str) -> dict:
    """모델명 prefix로 단가 반환. 없으면 Flash 기준."""
    m = model.lower()
    for key in PRICE:
        if key.startswith("gemini") and m.startswith(key):
            return PRICE[key]
    # GPT/Claude 폴백
    if m.startswith("gpt-4o") or m.startswith("gpt-4.1"):
        return {"input": 2.50 / 1_000_000, "output": 10.0 / 1_000_000}
    if m.startswith("claude"):
        return {"input": 3.00 / 1_000_000, "output": 15.0 / 1_000_000}
    return PRICE["gemini-2.5-flash"]


def usd_to_krw(usd: float) -> int:
    return round(usd * EXCHANGE_RATE)


def calc_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """LLM 호출 비용 (USD)."""
    p = _llm_price(model)
    return p["input"] * input_tokens + p["output"] * output_tokens


def calc_image_cost(count: int) -> float:
    return PRICE["imagen4"] * count


def calc_video_cost(count: int) -> float:
    return PRICE["veo3"] * count


def calc_tts_cost(chars: int) -> float:
    return PRICE["elevenlabs"] * chars


# ── 일별 집계 ──

@dataclass
class DailyCost:
    date: str
    channels: dict = field(default_factory=dict)  # channel → CostEntry dict

    def add(self, channel: str, entry: dict):
        if channel not in self.channels:
            self.channels[channel] = {
                "success": 0, "failed": 0,
                "llm_usd": 0.0, "image_usd": 0.0, "video_usd": 0.0, "tts_usd": 0.0,
                "image_count": 0, "video_count": 0, "tts_chars": 0,
            }
        ch = self.channels[channel]
        ch["success"] += entry.get("success", 0)
        ch["failed"] += entry.get("failed", 0)
        ch["llm_usd"] += entry.get("llm_usd", 0.0)
        ch["image_usd"] += entry.get("image_usd", 0.0)
        ch["video_usd"] += entry.get("video_usd", 0.0)
        ch["tts_usd"] += entry.get("tts_usd", 0.0)
        ch["image_count"] += entry.get("image_count", 0)
        ch["video_count"] += entry.get("video_count", 0)
        ch["tts_chars"] += entry.get("tts_chars", 0)

    def total_usd(self) -> float:
        return sum(
            ch["llm_usd"] + ch["image_usd"] + ch["video_usd"] + ch["tts_usd"] + ch.get("whisper_usd", 0.0)
            for ch in self.channels.values()
        )


def record_generation_cost(
    channel: str,
    success: bool,
    llm_usd: float = 0.0,
    image_count: int = 0,
    video_count: int = 0,
    tts_chars: int = 0,
    whisper_secs: float = 0.0,
) -> dict:
    """한 영상 생성 결과를 일별 집계에 저장. 해당 영상의 비용 dict 반환."""
    image_usd = calc_image_cost(image_count)
    video_usd = calc_video_cost(video_count)
    tts_usd = calc_tts_cost(tts_chars)
    whisper_usd = whisper_secs * PRICE["whisper"]
    total_usd = llm_usd + image_usd + video_usd + tts_usd + whisper_usd

    entry = {
        "success": 1 if success else 0,
        "failed": 0 if success else 1,
        "llm_usd": llm_usd,
        "image_usd": image_usd,
        "video_usd": video_usd,
        "tts_usd": tts_usd,
        "whisper_usd": whisper_usd,
        "image_count": image_count,
        "video_count": video_count,
        "tts_chars": tts_chars,
        "whisper_secs": whisper_secs,
        "total_usd": total_usd,
    }

    today = _today_kst()
    with _lock:
        data = _load_daily()
        if today not in data:
            data[today] = {}
        if channel not in data[today]:
            data[today][channel] = {
                "success": 0, "failed": 0,
                "llm_usd": 0.0, "image_usd": 0.0, "video_usd": 0.0, "tts_usd": 0.0, "whisper_usd": 0.0,
                "image_count": 0, "video_count": 0, "tts_chars": 0, "whisper_secs": 0.0,
            }
        ch = data[today][channel]
        for k in ("success", "failed", "image_count", "video_count", "tts_chars"):
            ch[k] += entry[k]
        ch["whisper_secs"] = ch.get("whisper_secs", 0.0) + entry["whisper_secs"]
        for k in ("llm_usd", "image_usd", "video_usd", "tts_usd", "whisper_usd"):
            ch[k] += entry.get(k, 0.0)
        _save_daily(data)

    return entry


def get_daily_summary(date: Optional[str] = None) -> Optional[dict]:
    """특정 날짜(YYYY-MM-DD) 또는 오늘의 집계 반환."""
    target = date or _today_kst()
    with _lock:
        data = _load_daily()
    return data.get(target)


def build_cost_table_text(entry: dict, channel: str, title: str) -> str:
    """단일 영상 완료 시 텔레그램 메시지 (원화 표)."""
    llm_krw     = usd_to_krw(entry["llm_usd"])
    img_krw     = usd_to_krw(entry["image_usd"])
    vid_krw     = usd_to_krw(entry["video_usd"])
    tts_krw     = usd_to_krw(entry["tts_usd"])
    whisper_krw = usd_to_krw(entry.get("whisper_usd", 0.0))
    total_krw   = usd_to_krw(entry["total_usd"])

    img_cnt = entry["image_count"]
    vid_cnt = entry["video_count"]
    tts_c   = entry["tts_chars"]

    lines = [
        f"<b>💰 생성 비용 — {channel}</b>",
        f"📌 {title}",
        "─────────────────────",
        f"{'항목':<10}{'수량':<8}{'비용':>8}",
        "─────────────────────",
        f"{'LLM':<10}{'':<8}{llm_krw:>6,}원",
        f"{'Imagen4':<10}{img_cnt}장{'':<4}{img_krw:>6,}원",
        f"{'Veo3':<10}{vid_cnt}클립{'':<3}{vid_krw:>6,}원",
        f"{'TTS':<10}{tts_c}자{'':<3}{tts_krw:>6,}원",
        f"{'Whisper':<10}{'':<8}{whisper_krw:>6,}원",
        "─────────────────────",
        f"{'합계':<10}{'':<8}{total_krw:>6,}원",
    ]
    return "\n".join(lines)


def build_daily_summary_text(date: Optional[str] = None) -> str:
    """일일 결산 텔레그램 메시지."""
    target = date or _today_kst()
    data = get_daily_summary(target)

    if not data:
        return f"📊 <b>일일 결산 {target}</b>\n데이터 없음"

    EMOJI = {
        "askanything": "🇰🇷", "wonderdrop": "🇺🇸",
        "exploratodo": "🇲🇽", "prismtale": "🇪🇸",
    }

    rows = []
    total_success = total_failed = 0
    grand_usd = 0.0

    for ch, info in data.items():
        ch_usd = info["llm_usd"] + info["image_usd"] + info["video_usd"] + info["tts_usd"] + info.get("whisper_usd", 0.0)
        ch_krw = usd_to_krw(ch_usd)
        em = EMOJI.get(ch, "📺")
        rows.append(
            f"{em} {ch[:8]:<10} ✅{info['success']} ❌{info['failed']}  {ch_krw:>7,}원"
        )
        total_success += info["success"]
        total_failed  += info["failed"]
        grand_usd     += ch_usd

    grand_krw = usd_to_krw(grand_usd)
    rows_text = "\n".join(rows)

    lines = [
        f"📊 <b>일일 결산 {target}</b>",
        "─────────────────────────",
        rows_text,
        "─────────────────────────",
        f"{'합계':<14} ✅{total_success} ❌{total_failed}  {grand_krw:>7,}원",
        f"⏰ {datetime.now(KST).strftime('%H:%M')} KST",
    ]
    return "\n".join(lines)
