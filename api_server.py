"""AskAnything Video Generator API — v2 오케스트라 아키텍처.

3,314줄 모놀리식 → 라우터 모듈 분리.
원본 백업: api_server_v1_backup.py
"""

import os
import sys
import io
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv(Path(__file__).resolve().with_name(".env"), override=True)

from routes.shared import cut_executor


# ── Lifespan (크론 스케줄러 + 리소스 관리) ──

@asynccontextmanager
async def _lifespan(app):
    # Vertex runtime sync. Startup should respect the configured backend instead of forcing SA-only.
    try:
        from modules.utils.vertex_sa_manager import refresh_runtime_vertex_env
        vertex_runtime = refresh_runtime_vertex_env(force_backend=False, persist=False)
        print(
            "[Vertex SA] runtime sync "
            f"backend={vertex_runtime.get('backend')} "
            f"sa_only={vertex_runtime.get('sa_only')} "
            f"enabled_accounts={vertex_runtime.get('enabled_count', 0)}"
        )
    except Exception as e:
        print(f"[Vertex SA] 초기화 실패: {e}")

    # ProjectQuotaManager 초기화
    from modules.utils.project_quota import quota_manager, load_project_key_map
    project_map = {k: v for k, v in load_project_key_map().items() if any(ki.get("key") for ki in v)}
    quota_manager.register_projects(project_map)
    total_keys = sum(len(v) for v in project_map.values())
    print(f"[QuotaManager] {len(project_map)}개 프로젝트, {total_keys}개 키 등록")

    # 크론 스케줄러
    from modules.scheduler.cron import add_daily, add_weekly, set_hourly, start as cron_start

    auto_deploy_enabled = os.getenv("AUTO_DEPLOY_CRON_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    if auto_deploy_enabled:
        async def _cron_deploy():
            from modules.scheduler.auto_deploy import run_auto_deploy
            max_per_channel_raw = os.getenv("AUTO_DEPLOY_MAX_PER_CHANNEL", "3").strip()
            max_per_channel = int(max_per_channel_raw) if max_per_channel_raw else None
            return await run_auto_deploy(max_per_channel=max_per_channel)
        deploy_hour = int(os.getenv("AUTO_DEPLOY_CRON_HOUR", "2"))
        deploy_minute = int(os.getenv("AUTO_DEPLOY_CRON_MINUTE", "0"))
        add_daily("자동 배포", deploy_hour, deploy_minute, _cron_deploy)
    else:
        print("[크론] 자동 배포 비활성화 — AUTO_DEPLOY_CRON_ENABLED=true 설정 시 활성화")

    rollout_expansion_enabled = os.getenv("ROLLOUT_EXPANSION_CRON_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    async def _cron_rollout_expansion():
        from modules.scheduler.auto_deploy import process_rollout_expansions
        limit_raw = os.getenv("ROLLOUT_EXPANSION_LIMIT", "6").strip()
        limit = int(limit_raw) if limit_raw else 6
        return await process_rollout_expansions(limit=limit)
    set_hourly(
        "리드채널 자동 확장",
        int(os.getenv("ROLLOUT_EXPANSION_CRON_MINUTE", "20")),
        _cron_rollout_expansion,
        enabled=rollout_expansion_enabled,
    )
    if not rollout_expansion_enabled:
        print("[크론] 리드채널 자동 확장 비활성화")

    weekly_topics_enabled = os.getenv("WEEKLY_TOPICS_CRON_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    if weekly_topics_enabled:
        def _cron_topics():
            from modules.scheduler.topic_generator import generate_weekly_topics
            from datetime import datetime, timedelta, timezone
            _kst = timezone(timedelta(hours=9))
            now = datetime.now(_kst)
            monday = now + timedelta(days=(7 - now.weekday()))
            return generate_weekly_topics(monday, days=7)
        topics_weekday = int(os.getenv("WEEKLY_TOPICS_CRON_WEEKDAY", "3"))  # 0=월 ... 3=목
        topics_hour = int(os.getenv("WEEKLY_TOPICS_CRON_HOUR", "9"))
        topics_minute = int(os.getenv("WEEKLY_TOPICS_CRON_MINUTE", "0"))
        add_weekly("주간 토픽 생성", topics_weekday, topics_hour, topics_minute, _cron_topics)
    else:
        print("[크론] 주간 토픽 생성 비활성화 — 수동 실행만 허용")

    def _cron_record():
        from modules.analytics.performance_tracker import record_daily
        return record_daily()
    add_daily("일일 성과 기록", 23, 50, _cron_record)

    def _cron_playlist_classify():
        from modules.upload.youtube import classify_existing_videos
        import json
        accounts_path = os.path.join("youtube_tokens", "channel_accounts.json")
        if not os.path.exists(accounts_path):
            return
        with open(accounts_path) as f:
            accounts = json.load(f)
        for ch in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
            ch_id = accounts.get(ch, {}).get("youtube")
            if ch_id:
                print(f"[재생목록] {ch} 소급 분류 시작...")
                classify_existing_videos(ch_id, ch)
    add_daily("재생목록 소급 분류", 10, 0, _cron_playlist_classify)

    def _cron_daily_cost():
        from modules.utils.notify import notify_daily_cost
        notify_daily_cost()
    add_daily("일일 비용 결산", 22, 0, _cron_daily_cost)

    def _cron_billing_threshold():
        from modules.utils.cost_tracker import check_configured_billing_threshold
        return check_configured_billing_threshold(send_telegram=True)
    try:
        from modules.utils.cost_tracker import load_billing_settings
        billing_settings = load_billing_settings()
        set_hourly(
            "청구 금액 임계치 확인",
            int(billing_settings.get("cron_minute", 5)),
            _cron_billing_threshold,
            enabled=bool(billing_settings.get("cron_enabled", True)),
        )
        if not billing_settings.get("cron_enabled", True):
            print("[크론] 청구 금액 알림 비활성화 — 설정 화면에서 활성화 가능")
    except Exception as e:
        print(f"[크론] 청구 금액 알림 등록 실패: {e}")

    def _cron_morning_briefing():
        from modules.utils.notify import notify_morning_briefing
        notify_morning_briefing()
    add_daily("모닝 브리핑", 8, 0, _cron_morning_briefing)

    cron_start()
    print(f"[크론] 작업 등록 완료")

    yield
    cut_executor.shutdown(wait=False)


# ── FastAPI 앱 생성 ──

app = FastAPI(lifespan=_lifespan)

# 정적 파일 서빙
os.makedirs("assets", exist_ok=True)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# CORS
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:8080,http://127.0.0.1:3000").split(",")
if any(o.strip() == "*" for o in _cors_origins):
    _cors_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 라우터 등록 ──

from routes.generate import router as generate_router
from routes.prepare import router as prepare_router
from routes.upload import router as upload_router
from routes.batch import router as batch_router
from routes.analytics import router as analytics_router
from routes.scheduler import router as scheduler_router
from routes.settings import router as settings_router

app.include_router(generate_router)
app.include_router(prepare_router)
app.include_router(upload_router)
app.include_router(batch_router)
app.include_router(analytics_router)
app.include_router(scheduler_router)
app.include_router(settings_router)


# ── Legal pages (TikTok/Instagram 앱 등록용) ──

@app.get("/terms", response_class=HTMLResponse)
async def terms_of_service():
    legal_path = os.path.join(os.path.dirname(__file__), "legal", "terms.html")
    with open(legal_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    legal_path = os.path.join(os.path.dirname(__file__), "legal", "privacy.html")
    with open(legal_path, "r", encoding="utf-8") as f:
        return f.read()


# ── 엔트리포인트 ──

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("API_PORT", "8003"))
    reload = os.getenv("UVICORN_RELOAD", "true").lower() == "true"
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=reload)
