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

_DAILY_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", ".daily_cost.json")
_BILLING_ALERT_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", ".billing_alert_state.json")
_BILLING_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", ".billing_settings.json")
_lock = threading.Lock()

DEFAULT_BILLING_THRESHOLD_KRW = int(os.getenv("BILLING_ALERT_THRESHOLD_KRW", "400000"))
DEFAULT_BILLING_CRON_MINUTE = int(os.getenv("BILLING_ALERT_CRON_MINUTE", "5"))


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


def _load_billing_alert_state() -> dict:
    try:
        path = os.path.abspath(_BILLING_ALERT_FILE)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_billing_alert_state(data: dict) -> None:
    try:
        path = os.path.abspath(_BILLING_ALERT_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[BillingAlert] 저장 실패: {e}")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _load_billing_settings_file() -> dict:
    try:
        path = os.path.abspath(_BILLING_SETTINGS_FILE)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_billing_settings_file(data: dict) -> None:
    try:
        path = os.path.abspath(_BILLING_SETTINGS_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[BillingSettings] 저장 실패: {e}")


def parse_krw(value: str | int | float | None) -> int:
    """'₩453,008' 같은 표시 금액을 정수 원화로 변환."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits or 0)


def load_billing_settings() -> dict:
    """청구 금액 알림 설정을 파일 + 환경변수 기본값으로 로드."""
    saved = _load_billing_settings_file()
    current = saved.get("current_krw", os.getenv("BILLING_CURRENT_KRW", "0"))
    total = saved.get("total_krw", os.getenv("BILLING_TOTAL_KRW", "0"))
    threshold = saved.get("threshold_krw", os.getenv("BILLING_ALERT_THRESHOLD_KRW", str(DEFAULT_BILLING_THRESHOLD_KRW)))
    cron_minute = saved.get("cron_minute", os.getenv("BILLING_ALERT_CRON_MINUTE", str(DEFAULT_BILLING_CRON_MINUTE)))
    return {
        "current_krw": parse_krw(current),
        "total_krw": parse_krw(total),
        "threshold_krw": parse_krw(threshold),
        "cron_enabled": _coerce_bool(saved.get("cron_enabled"), _env_flag("BILLING_ALERT_CRON_ENABLED", True)),
        "cron_minute": max(0, min(59, parse_krw(cron_minute))),
        "alert_key": str(saved.get("alert_key") or os.getenv("BILLING_ALERT_KEY", "billing-settings")),
        "updated_at": saved.get("updated_at"),
    }


def save_billing_settings(settings: dict) -> dict:
    """프론트 설정 화면에서 받은 청구 금액 알림 설정 저장."""
    previous = load_billing_settings()
    updated = {
        **previous,
        "current_krw": parse_krw(settings.get("current_krw", previous["current_krw"])),
        "total_krw": parse_krw(settings.get("total_krw", previous["total_krw"])),
        "threshold_krw": parse_krw(settings.get("threshold_krw", previous["threshold_krw"])),
        "cron_enabled": _coerce_bool(settings.get("cron_enabled"), previous["cron_enabled"]),
        "cron_minute": max(0, min(59, parse_krw(settings.get("cron_minute", previous["cron_minute"])))),
        "alert_key": str(settings.get("alert_key") or previous["alert_key"] or "billing-settings"),
        "updated_at": datetime.now(KST).isoformat(),
    }
    if updated["threshold_krw"] > 0 and updated["total_krw"] >= updated["threshold_krw"]:
        updated["cron_enabled"] = False
        updated["disabled_reason"] = "threshold_crossed"
        updated["disabled_at"] = datetime.now(KST).isoformat()
    _save_billing_settings_file(updated)
    os.environ["BILLING_CURRENT_KRW"] = str(updated["current_krw"])
    os.environ["BILLING_TOTAL_KRW"] = str(updated["total_krw"])
    os.environ["BILLING_ALERT_THRESHOLD_KRW"] = str(updated["threshold_krw"])
    os.environ["BILLING_ALERT_CRON_ENABLED"] = "true" if updated["cron_enabled"] else "false"
    os.environ["BILLING_ALERT_CRON_MINUTE"] = str(updated["cron_minute"])
    return updated


def disable_billing_cron(reason: str = "") -> dict:
    """비용 임계치 초과 후 청구 알림 크론을 끕니다."""
    settings = load_billing_settings()
    if not settings.get("cron_enabled"):
        return settings
    settings["cron_enabled"] = False
    settings["disabled_reason"] = reason or "threshold_crossed"
    settings["disabled_at"] = datetime.now(KST).isoformat()
    _save_billing_settings_file(settings)
    os.environ["BILLING_ALERT_CRON_ENABLED"] = "false"
    return settings


def check_configured_billing_threshold(send_telegram: bool = True) -> dict:
    """저장된 청구 설정 기준으로 임계치 알림 확인."""
    settings = load_billing_settings()
    if not settings["cron_enabled"]:
        return {"skipped": True, "reason": "disabled", **settings}
    if settings["total_krw"] <= 0:
        return {"skipped": True, "reason": "missing_total_krw", **settings}
    result = check_billing_threshold(
        current_krw=settings["current_krw"],
        total_krw=settings["total_krw"],
        threshold_krw=settings["threshold_krw"],
        alert_key=settings["alert_key"],
        send_telegram=send_telegram,
    )
    if result.get("crossed"):
        disabled = disable_billing_cron("threshold_crossed")
        result["cron_disabled"] = True
        result["cron_enabled"] = disabled.get("cron_enabled", False)
        try:
            from modules.scheduler.cron import set_hourly

            def _cron_billing_threshold():
                from modules.utils.cost_tracker import check_configured_billing_threshold
                return check_configured_billing_threshold(send_telegram=True)

            set_hourly(
                "청구 금액 임계치 확인",
                int(settings.get("cron_minute", 5)),
                _cron_billing_threshold,
                enabled=False,
            )
        except Exception as e:
            result["cron_disable_error"] = str(e)
    return {**settings, **result}


def build_billing_threshold_message(
    *,
    current_krw: int,
    total_krw: int,
    threshold_krw: int = DEFAULT_BILLING_THRESHOLD_KRW,
) -> str:
    over_krw = max(0, total_krw - threshold_krw)
    remaining_to_total = max(0, total_krw - current_krw)
    ratio = (total_krw / threshold_krw * 100) if threshold_krw else 0
    return "\n".join([
        f"🚨 <b>비용 경고 — {threshold_krw:,}원 초과</b>",
        "─────────────────────",
        f"현재 표시: {current_krw:,}원 / {total_krw:,}원",
        f"기준선: {threshold_krw:,}원",
        f"초과액: {over_krw:,}원",
        f"기준 대비: {ratio:.1f}%",
        f"현재값에서 총액까지 차이: {remaining_to_total:,}원",
    ])


def check_billing_threshold(
    *,
    current_krw: int | str,
    total_krw: int | str,
    threshold_krw: int | str = DEFAULT_BILLING_THRESHOLD_KRW,
    alert_key: str = "default",
    send_telegram: bool = True,
) -> dict:
    """외부 결제 화면 금액을 받아 임계치 초과 시 1회 텔레그램 알림.

    current_krw: 화면 왼쪽 금액(예: 오늘/현재 사용액)
    total_krw: 화면 오른쪽 금액(예: 총 청구/예산 사용액)
    threshold_krw: 기본 400,000원
    """
    current = parse_krw(current_krw)
    total = parse_krw(total_krw)
    threshold = parse_krw(threshold_krw)
    crossed = total >= threshold if threshold else False
    over = max(0, total - threshold)

    result = {
        "current_krw": current,
        "total_krw": total,
        "threshold_krw": threshold,
        "crossed": crossed,
        "over_krw": over,
        "sent": False,
    }

    state = _load_billing_alert_state()
    key = f"{alert_key}:{threshold}"
    if not crossed:
        if key in state:
            state[key] = {
                "crossed": False,
                "sent": False,
                "last_total_krw": total,
                "last_current_krw": current,
                "threshold_krw": threshold,
                "reset_at": datetime.now(KST).isoformat(),
            }
            _save_billing_alert_state(state)
        return result

    previous = state.get(key, {})
    if previous.get("crossed") and previous.get("sent") and int(previous.get("last_total_krw", 0)) >= threshold:
        result["deduped"] = True
        return result

    message = build_billing_threshold_message(
        current_krw=current,
        total_krw=total,
        threshold_krw=threshold,
    )
    if send_telegram:
        try:
            from modules.utils.notify import _send
            result["sent"] = bool(_send(message))
        except Exception as e:
            result["error"] = str(e)

    state[key] = {
        "crossed": True,
        "sent": result.get("sent", False),
        "last_total_krw": total,
        "last_current_krw": current,
        "threshold_krw": threshold,
        "sent_at": datetime.now(KST).isoformat(),
    }
    _save_billing_alert_state(state)
    return result


# ── 단가 조회 ──

_LLM_PRICE_EXTRA = {
    "gpt-4o":          {"input": 2.50 / 1_000_000, "output": 10.0 / 1_000_000},
    "gpt-4o-mini":     {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "claude-opus":     {"input": 15.0 / 1_000_000, "output": 75.0 / 1_000_000},
    "claude-sonnet":   {"input": 3.0 / 1_000_000,  "output": 15.0 / 1_000_000},
    "claude-haiku":    {"input": 0.80 / 1_000_000, "output": 4.0 / 1_000_000},
}


def _llm_price(model: str) -> dict:
    """모델명 prefix로 단가 반환. Gemini/GPT/Claude 지원. 없으면 Flash 기준."""
    m = model.lower()
    for key in PRICE:
        if key.startswith("gemini") and m.startswith(key):
            return PRICE[key]
    for key, val in _LLM_PRICE_EXTRA.items():
        if m.startswith(key):
            return val
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
                "llm_usd": 0.0, "image_usd": 0.0, "video_usd": 0.0, "tts_usd": 0.0, "whisper_usd": 0.0,
                "image_count": 0, "video_count": 0, "tts_chars": 0, "whisper_secs": 0.0,
            }
        ch = self.channels[channel]
        ch["success"] += entry.get("success", 0)
        ch["failed"] += entry.get("failed", 0)
        ch["llm_usd"] += entry.get("llm_usd", 0.0)
        ch["image_usd"] += entry.get("image_usd", 0.0)
        ch["video_usd"] += entry.get("video_usd", 0.0)
        ch["tts_usd"] += entry.get("tts_usd", 0.0)
        ch["whisper_usd"] += entry.get("whisper_usd", 0.0)
        ch["image_count"] += entry.get("image_count", 0)
        ch["video_count"] += entry.get("video_count", 0)
        ch["tts_chars"] += entry.get("tts_chars", 0)
        ch["whisper_secs"] = ch.get("whisper_secs", 0.0) + entry.get("whisper_secs", 0.0)

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


def record_asset_cost(
    channel: str,
    llm_usd: float = 0.0,
    image_count: int = 0,
    video_count: int = 0,
    tts_chars: int = 0,
    whisper_secs: float = 0.0,
) -> dict:
    """실제 생성된 자산 비용만 일별 집계에 저장. 영상 성공/실패 카운트는 바꾸지 않는다."""
    image_usd = calc_image_cost(image_count)
    video_usd = calc_video_cost(video_count)
    tts_usd = calc_tts_cost(tts_chars)
    whisper_usd = whisper_secs * PRICE["whisper"]
    total_usd = llm_usd + image_usd + video_usd + tts_usd + whisper_usd

    entry = {
        "success": 0,
        "failed": 0,
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
        for k in ("image_count", "video_count", "tts_chars"):
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
    llm_krw   = usd_to_krw(entry["llm_usd"])
    img_krw   = usd_to_krw(entry["image_usd"])
    vid_krw   = usd_to_krw(entry["video_usd"])
    tts_krw   = usd_to_krw(entry["tts_usd"])
    whisper_krw = usd_to_krw(entry.get("whisper_usd", 0.0))
    total_krw = usd_to_krw(entry["total_usd"])

    img_cnt = entry["image_count"]
    vid_cnt = entry["video_count"]
    tts_c   = entry["tts_chars"]
    wh_secs = entry.get("whisper_secs", 0.0)

    lines = [
        f"<b>💰 생성 비용 — {channel}</b>",
        f"📌 {title}",
        "─────────────────────",
        f"{'항목':<10}{'수량':<8}{'비용':>8}",
        "─────────────────────",
        f"{'LLM':<10}{'':<8}{llm_krw:>6,}원",
        f"{'Imagen4':<10}{img_cnt}장{'':<4}{img_krw:>6,}원",
        f"{'Veo3':<10}{vid_cnt}클립{'':<3}{vid_krw:>6,}원",
        f"{'ElevenLabs':<10}{tts_c}자{'':<3}{tts_krw:>6,}원",
        f"{'Whisper':<10}{wh_secs:.0f}초{'':<3}{whisper_krw:>6,}원",
        "─────────────────────",
        f"{'합계':<10}{'':<8}{total_krw:>6,}원",
        f"환율 기준: $1 = {EXCHANGE_RATE:,}원",
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
