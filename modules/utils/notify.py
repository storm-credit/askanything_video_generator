"""실패/완료 알림 — Telegram Bot API + 인라인 버튼.

사용:
  from modules.utils.notify import notify_success, notify_failure, notify_warning

  notify_success("askanything", "하루가 1년보다 긴 행성", video_url="https://...")
  notify_failure("wonderdrop", "Moon Moving Away", error="429 rate limit")
  notify_warning("전체", "Gemini 키 3개 소진, 1개 남음")
"""
import os
import json
import requests
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8216083122:AAH1RgfXUGvfDJPSWz7NRjTDwOzNOprfNng")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1703019448")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# 채널별 이모지
CHANNEL_EMOJI = {
    "askanything": "\U0001f1f0\U0001f1f7",   # 🇰🇷
    "wonderdrop": "\U0001f1fa\U0001f1f8",     # 🇺🇸
    "exploratodo": "\U0001f1f2\U0001f1fd",    # 🇲🇽
    "prismtale": "\U0001f1ea\U0001f1f8",      # 🇪🇸
}

# 서버 주소 (인라인 버튼 콜백용)
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8003")


def _send(text: str, silent: bool = False, buttons: list = None):
    """텔레그램 메시지 전송 (인라인 버튼 지원)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[알림] Telegram 미설정 — {text[:50]}")
        return
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
        requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        print(f"[알림] Telegram 전송 실패: {e}")


def notify_success(channel: str, topic: str, video_url: str = None):
    """영상 생성+업로드 성공."""
    emoji = CHANNEL_EMOJI.get(channel, "📺")
    url_btn = []
    if video_url:
        url_btn = [{"text": "▶️ YouTube에서 보기", "url": video_url}]

    _send(
        f"━━━━━━━━━━━━━━━\n"
        f"✅ <b>영상 업로드 완료</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{emoji} <b>{channel}</b>\n"
        f"📌 {topic}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        buttons=url_btn,
    )


def notify_failure(channel: str, topic: str, error: str = ""):
    """영상 생성 실패 — 재수행 버튼 포함."""
    emoji = CHANNEL_EMOJI.get(channel, "📺")
    err = error[:150] if error else "알 수 없는 오류"

    _send(
        f"━━━━━━━━━━━━━━━\n"
        f"❌ <b>생성 실패</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{emoji} <b>{channel}</b>\n"
        f"📌 {topic}\n"
        f"💥 <code>{err}</code>\n"
        f"🔄 웹 UI에서 재수행 가능\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    )


def notify_warning(context: str, message: str):
    """경고 (키 소진, 쿼터 등)."""
    _send(
        f"━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>경고</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📍 {context}\n"
        f"{message}\n"
        f"⏰ {datetime.now().strftime('%H:%M')}",
        silent=True,
    )


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
        f"⏰ {datetime.now().strftime('%H:%M')}",
    )
