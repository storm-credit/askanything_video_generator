"""Scheduler endpoints — 자동 배포, 크론, 토픽 생성."""

import os, json, asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/preview")
async def scheduler_preview(date: str | None = None):
    """스케줄 미리보기 — 영상 생성 없이 시간 배정만."""
    from modules.scheduler.auto_deploy import preview_schedule
    from datetime import datetime as _dt
    target = _dt.strptime(date, "%Y-%m-%d") if date else None
    return preview_schedule(target)


@router.get("/status")
async def scheduler_status():
    """현재 배포 진행 상태."""
    from modules.scheduler.auto_deploy import get_status
    return get_status()


@router.get("/rollout-expansions")
async def scheduler_rollout_expansions(status: str | None = None, limit: int = 50):
    """Lead-channel-first holdback 확장 큐 조회."""
    from modules.scheduler.rollout_queue import get_queue_summary, list_candidates

    return {
        "success": True,
        "queue": get_queue_summary(),
        "items": list_candidates(status=status, limit=limit),
    }


@router.post("/rollout-expansions/run")
async def scheduler_run_rollout_expansions(limit: int = 6):
    """24시간 경과한 holdback 확장을 즉시 실행."""
    from modules.scheduler.auto_deploy import process_rollout_expansions

    return await process_rollout_expansions(limit=limit)


@router.post("/run")
async def scheduler_run(
    date: str | None = None,
    dry_run: bool = False,
    max_per_channel: int | None = None,
    video_engine: str | None = None,
):
    """자동 배포 실행. dry_run=true면 스케줄만 계산."""
    from modules.scheduler.auto_deploy import run_auto_deploy
    from datetime import datetime as _dt
    from modules.scheduler.time_planner import KST
    import asyncio
    target = _dt.strptime(date, "%Y-%m-%d") if date else None

    if dry_run:
        result = await run_auto_deploy(target, dry_run=True, max_per_channel=max_per_channel, video_engine=video_engine)
        return result

    # 비동기 실행 (즉시 응답, 백그라운드에서 진행)
    task = asyncio.create_task(
        run_auto_deploy(target, max_per_channel=max_per_channel, video_engine=video_engine)
    )
    await asyncio.sleep(0)

    if task.done():
        try:
            return task.result()
        except Exception as exc:
            return {"success": False, "message": f"자동 배포 시작 실패: {str(exc)[:200]}"}

    from modules.scheduler.auto_deploy import get_status

    status = get_status()
    if not status.get("running"):
        return {
            "success": False,
            "message": "자동 배포 시작을 확인하지 못했습니다.",
            "status": status,
        }

    return {
        "success": True,
        "accepted": True,
        "message": "자동 배포 시작됨. /api/scheduler/status로 진행 상태 확인",
        "status": {
            "running": True,
            "current_date": status.get("current_date"),
            "started_at": status.get("started_at"),
        },
    }


@router.get("/cron")
async def cron_status():
    """크론 스케줄러 상태 확인."""
    from modules.scheduler.cron import get_status
    return {"success": True, **get_status()}


@router.post("/generate-topics")
async def generate_topics_endpoint(start_date: str = None, days: int = 7):
    """주간 토픽 자동 생성 — 성과 분석 기반."""
    from modules.scheduler.topic_generator import generate_weekly_topics
    from datetime import datetime
    if start_date:
        dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        # 다음 월요일 기준
        dt = datetime.now()
        while dt.weekday() != 0:  # 0=월요일
            dt += timedelta(days=1)
    result = await asyncio.get_running_loop().run_in_executor(
        None, lambda: generate_weekly_topics(dt, days=days)
    )
    return result
