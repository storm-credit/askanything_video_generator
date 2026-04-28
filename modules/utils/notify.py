"""실패/완료 알림 — Telegram Bot API + 인라인 버튼.

사용:
  from modules.utils.notify import notify_success, notify_failure, notify_warning

  notify_success("askanything", "하루가 1년보다 긴 행성", video_url="https://...")
  notify_failure("wonderdrop", "Moon Moving Away", error="429 rate limit")
  notify_warning("전체", "Gemini 키 3개 소진, 1개 남음")
"""
import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from modules.utils.models import describe_video_model

try:
    import requests
except Exception:
    requests = None

_KST = timezone(timedelta(hours=9))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
_LOG_PATH = Path(__file__).resolve().parents[2] / "data" / "telegram_send_log.jsonl"
_SUMMARY_DEDUPE_KINDS = {"morning_briefing", "daily_cost_summary", "deploy_summary"}

# 채널별 이모지
CHANNEL_EMOJI = {
    "askanything": "\U0001f1f0\U0001f1f7",   # 🇰🇷
    "wonderdrop": "\U0001f1fa\U0001f1f8",     # 🇺🇸
    "exploratodo": "\U0001f1f2\U0001f1fd",    # 🇲🇽
    "prismtale": "\U0001f1ea\U0001f1f8",      # 🇪🇸
}

# 서버 주소 (인라인 버튼 콜백용)
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8003")


def _append_send_log(entry: dict) -> None:
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[알림] Telegram 로그 저장 실패: {e}")


def _recent_ok_send_exists(kind: str, meta: dict, window_seconds: int = 600) -> bool:
    """요약 알림 중복 전송 방지. 같은 kind/meta가 최근에 성공했으면 스킵."""
    try:
        if not _LOG_PATH.exists():
            return False
        now = datetime.now(_KST)
        lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()[-300:]
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except Exception:
                continue
            if item.get("kind") != kind or not item.get("ok"):
                continue
            if item.get("meta") != meta:
                continue
            ts_raw = item.get("ts")
            if not ts_raw:
                continue
            sent_at = datetime.fromisoformat(ts_raw)
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=_KST)
            if (now - sent_at.astimezone(_KST)).total_seconds() <= window_seconds:
                return True
        return False
    except Exception:
        return False


def _send(text: str, silent: bool = False, buttons: list = None, *, kind: str = "generic", meta: dict | None = None) -> bool:
    """텔레그램 메시지 전송 (인라인 버튼 지원)."""
    meta = meta or {}
    log_entry = {
        "ts": datetime.now(_KST).isoformat(),
        "kind": kind,
        "silent": bool(silent),
        "has_buttons": bool(buttons),
        "meta": meta,
        "text_preview": text[:200],
        "ok": False,
    }
    if kind in _SUMMARY_DEDUPE_KINDS and _recent_ok_send_exists(kind, meta):
        print(f"[알림] 중복 요약 알림 스킵: {kind} {meta}")
        log_entry["skipped"] = True
        log_entry["error"] = "duplicate_summary_suppressed"
        _append_send_log(log_entry)
        return False
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[알림] Telegram 미설정 — {text[:50]}")
        log_entry["error"] = "telegram_not_configured"
        _append_send_log(log_entry)
        return False
    try:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_notification": silent,
        }
        if buttons:
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": [buttons]
            })
        if requests is not None:
            response = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=10)
            log_entry["ok"] = bool(response.ok)
            log_entry["status_code"] = response.status_code
            _append_send_log(log_entry)
            return response.ok
        else:
            req = urllib.request.Request(
                f"{TELEGRAM_API}/sendMessage",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                log_entry["ok"] = True
                log_entry["status_code"] = 200
                _append_send_log(log_entry)
                return True
    except Exception as e:
        print(f"[알림] Telegram 전송 실패: {e}")
        log_entry["error"] = str(e)
        _append_send_log(log_entry)
        return False


def notify_success(
    channel: str,
    topic: str,
    video_url: str = None,
    *,
    video_engine: str = "",
    video_model: str = "",
):
    """영상 생성+업로드 성공."""
    emoji = CHANNEL_EMOJI.get(channel, "📺")
    url_btn = []
    if video_url:
        url_btn = [{"text": "▶️ YouTube에서 보기", "url": video_url}]
    model_text = ""
    if video_engine or video_model:
        parts = []
        if video_engine:
            parts.append(f"engine={video_engine}")
        if video_model:
            parts.append(f"model={describe_video_model(video_engine, video_model)}")
        model_text = f"\n🎬 {' / '.join(parts)}"

    _send(
        f"━━━━━━━━━━━━━━━\n"
        f"✅ <b>영상 업로드 완료</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{emoji} <b>{channel}</b>\n"
        f"📌 {topic}\n"
        f"{model_text}"
        f"⏰ {datetime.now(_KST).strftime('%Y-%m-%d %H:%M')} KST",
        buttons=url_btn,
        kind="upload_success",
        meta={"channel": channel, "topic": topic, "video_engine": video_engine, "video_model": video_model},
    )


def notify_failure(
    channel: str,
    topic: str,
    error: str = "",
    *,
    video_engine: str = "",
    video_model: str = "",
):
    """영상 생성 실패 — 재수행 버튼 포함."""
    emoji = CHANNEL_EMOJI.get(channel, "📺")
    err = error[:150] if error else "알 수 없는 오류"
    model_text = ""
    if video_engine or video_model:
        parts = []
        if video_engine:
            parts.append(f"engine={video_engine}")
        if video_model:
            parts.append(f"model={describe_video_model(video_engine, video_model)}")
        model_text = f"\n🎬 {' / '.join(parts)}"

    _send(
        f"━━━━━━━━━━━━━━━\n"
        f"❌ <b>생성 실패</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{emoji} <b>{channel}</b>\n"
        f"📌 {topic}\n"
        f"{model_text}\n"
        f"💥 <code>{err}</code>\n"
        f"🔄 웹 UI에서 재수행 가능\n"
        f"⏰ {datetime.now(_KST).strftime('%Y-%m-%d %H:%M')} KST",
        kind="generation_failure",
        meta={"channel": channel, "topic": topic, "error": err, "video_engine": video_engine, "video_model": video_model},
    )


def notify_warning(context: str, message: str):
    """경고 (키 소진, 쿼터 등)."""
    _send(
        f"━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>경고</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📍 {context}\n"
        f"{message}\n"
        f"⏰ {datetime.now(_KST).strftime('%H:%M')} KST",
        silent=True,
        kind="warning",
        meta={"context": context, "message": message[:200]},
    )


def notify_cost(channel: str, title: str, cost_entry: dict, video_url: str = "",
                format_type: str = ""):
    """영상 완료 시 비용 표 (원화) 전송."""
    try:
        from modules.utils.cost_tracker import build_cost_table_text
        text = build_cost_table_text(cost_entry, channel, title)
        if format_type:
            fmt_emoji = {"WHO_WINS": "⚔️", "IF": "🌀", "EMOTIONAL_SCI": "💫", "FACT": "📡", "COUNTDOWN": "🏆", "SCALE": "📏", "PARADOX": "🔄", "MYSTERY": "🔮"}.get(format_type.upper(), "")
            text = f"{fmt_emoji} [{format_type}]\n" + text
        if video_url:
            text += f'\n🔗 <a href="{video_url}">YouTube 보기</a>'
        _send(text, kind="cost_summary_single", meta={"channel": channel, "title": title, "format_type": format_type, "video_url": video_url})
    except Exception as e:
        print(f"[알림] 비용 알림 실패: {e}")


def notify_daily_cost(date: str = ""):
    """일일 결산 비용 표 (원화) 전송."""
    try:
        from modules.utils.cost_tracker import build_daily_summary_text
        text = build_daily_summary_text(date or None)
        _send(text, kind="daily_cost_summary", meta={"date": date or ""})
        _notify_env_billing_threshold()
    except Exception as e:
        print(f"[알림] 일일 결산 알림 실패: {e}")


def _notify_env_billing_threshold():
    """저장된 청구 설정 또는 환경변수 기준으로 40만원 초과 여부 확인."""
    try:
        from modules.utils.cost_tracker import check_configured_billing_threshold
        check_configured_billing_threshold(send_telegram=True)
    except Exception as e:
        print(f"[알림] 청구 임계치 알림 실패: {e}")


def notify_deploy_summary(total: int, completed: int, failed: int, date: str):
    """일일 배포 완료 요약."""
    if failed == 0:
        header = "🎉 <b>전체 성공!</b>"
        bar = "🟩" * completed
    else:
        header = f"📊 <b>배포 완료</b> ({failed}건 실패)"
        bar = "🟩" * completed + "🟥" * failed

    _send(
        f"━━━━━━━━━━━━━━━\n"
        f"{header}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📅 {date}\n"
        f"{bar}\n"
        f"✅ {completed}  ❌ {failed}  📦 {total}\n"
        f"⏰ {datetime.now(_KST).strftime('%H:%M')} KST",
        kind="deploy_summary",
        meta={"date": date, "total": total, "completed": completed, "failed": failed},
    )


def notify_morning_briefing():
    """☀️ 모닝 브리핑 — 어제 배포/비용/실패/성과 종합 리포트."""
    from datetime import timedelta, timezone
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")
    yesterday = (now_kst - timedelta(days=1)).strftime("%Y-%m-%d")

    sections = [
        f"☀️ <b>모닝 브리핑 — {yesterday}</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    # 0. 오늘 새벽 자동배포 결과. 어제 비용 결산과 혼동하지 않도록 맨 위에 분리 표시.
    try:
        state_path = Path("data") / "_deploy_state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("current_date") == today and state.get("finished_at"):
                completed = int(state.get("completed", 0) or 0)
                failed = int(state.get("failed", 0) or 0)
                total = int(state.get("total", completed + failed) or 0)
                label = "전체 성공" if failed == 0 and total and completed >= total else f"{failed}건 실패"
                sections.append(
                    f"<b>🌅 오늘 새벽 배치 — {today}</b>  ✅{completed} ❌{failed} 📦{total} ({label})"
                )
                failed_rows = [
                    f"  - {r.get('channel')}: {r.get('topic')} — {str(r.get('error') or '')[:80]}"
                    for r in state.get("results", [])
                    if r.get("status") == "failed"
                ]
                if failed_rows:
                    sections.append("\n".join(failed_rows[:5]))
    except Exception:
        pass

    # 1. 어제 비용 결산
    try:
        from modules.utils.cost_tracker import get_daily_summary, usd_to_krw
        cost = get_daily_summary(yesterday)
        if cost:
            total_success = total_failed = 0
            grand_usd = 0.0
            ch_lines = []
            for ch, info in cost.items():
                ch_usd = info["llm_usd"] + info["image_usd"] + info["video_usd"] + info["tts_usd"] + info.get("whisper_usd", 0.0)
                em = CHANNEL_EMOJI.get(ch, "📺")
                ch_lines.append(f"  {em} {ch[:10]:<12} ✅{info['success']} ❌{info['failed']}  {usd_to_krw(ch_usd):>6,}원")
                total_success += info["success"]
                total_failed += info["failed"]
                grand_usd += ch_usd
            sections.append(f"\n<b>📦 어제 비용 기록 — {yesterday}</b>  ✅{total_success} ❌{total_failed}  💰{usd_to_krw(grand_usd):,}원")
            sections.extend(ch_lines)
        else:
            sections.append(f"\n📦 어제 비용 기록 없음 — {yesterday}")
    except Exception as e:
        sections.append(f"📦 비용 조회 실패: {e}")

    # 2. 실패 요약
    try:
        from modules.orchestrator.agents.failure_analyzer import get_failure_summary
        fails = get_failure_summary(yesterday)
        if fails["total"] > 0:
            types = ", ".join(f"{k}:{v}" for k, v in fails["by_type"].items())
            sections.append(f"\n<b>💥 실패 {fails['total']}건</b>  ({types})")
        else:
            sections.append("\n💥 실패 0건")
    except Exception:
        pass

    # 3. 성과 트렌드 (3일 vs 7일 평균 조회수)
    try:
        from modules.analytics.performance_tracker import get_daily_trend
        sections.append("\n<b>📈 성과 (3d vs 7d 평균)</b>")
        for ch in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
            trend = get_daily_trend(ch, days=7)
            if len(trend) >= 3:
                avg_7d = sum(t.get("avg_views", 0) for t in trend) / len(trend)
                avg_3d = sum(t.get("avg_views", 0) for t in trend[-3:]) / 3
                delta = ((avg_3d - avg_7d) / avg_7d * 100) if avg_7d > 0 else 0
                arrow = "📈" if delta >= 0 else "📉"
                em = CHANNEL_EMOJI.get(ch, "📺")
                sections.append(f"  {em} {ch[:10]:<12} {avg_3d:,.0f} {arrow}{delta:+.1f}%")
    except Exception:
        pass

    # 4. 알림 이력
    try:
        alert_path = os.path.join("assets", "_analytics", "alerts", "last_run.json")
        if os.path.exists(alert_path):
            with open(alert_path, "r", encoding="utf-8") as f:
                last_alert = json.load(f)
            sent = last_alert.get("alerts_sent", 0)
            if sent > 0:
                sections.append(f"\n🚨 어제 알림 {sent}건 발송됨")
    except Exception:
        pass

    sections.append(f"\n⏰ {datetime.now(KST).strftime('%H:%M')} KST")
    _send("\n".join(sections), kind="morning_briefing", meta={"date": yesterday})
