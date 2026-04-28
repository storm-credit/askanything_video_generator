"""내장 크론 스케줄러 — 외부 의존성 없이 asyncio 기반.

api_server.py 시작 시 자동 등록. Docker 재시작해도 다시 등록.

스케줄:
  매주 목요일 09:00 KST → 주간 토픽 생성 (다음 주 7일분)
  매일 02:00 KST → 당일 Day 파일 자동 배포 (AUTO_DEPLOY_CRON_ENABLED=true일 때)
  매일 23:50 KST → 일일 성과 기록
"""
import asyncio
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Any

KST = timezone(timedelta(hours=9))

# 등록된 작업 목록 — reload 시 중복 방지를 위해 매번 초기화
_jobs: list[dict] = []
_running = False
_thread: threading.Thread | None = None
_started_once = False  # reload 시 이전 스레드 감지용


def _now_kst() -> datetime:
    return datetime.now(KST)


def _next_run(hour: int, minute: int, weekday: int | None = None) -> datetime:
    """다음 실행 시각 계산. weekday=None이면 매일, 0=월~6=일."""
    now = _now_kst()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if weekday is not None:
        # 특정 요일
        days_ahead = weekday - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and now >= target):
            days_ahead += 7
        target += timedelta(days=days_ahead)
    else:
        # 매일
        if now >= target:
            target += timedelta(days=1)

    return target


def add_daily(name: str, hour: int, minute: int, func: Callable):
    """매일 실행 작업 등록. 같은 이름 중복 등록 방지."""
    if any(j["name"] == name for j in _jobs):
        print(f"[크론] 스킵: {name} — 이미 등록됨")
        return
    _jobs.append({
        "name": name,
        "hour": hour,
        "minute": minute,
        "weekday": None,
        "func": func,
        "type": "daily",
    })
    next_t = _next_run(hour, minute)
    print(f"[크론] 등록: {name} — 매일 {hour:02d}:{minute:02d} KST (다음: {next_t.strftime('%m/%d %H:%M')})")


def add_hourly(name: str, minute: int, func: Callable):
    """매시간 실행 작업 등록. 같은 이름 중복 등록 방지."""
    if any(j["name"] == name for j in _jobs):
        print(f"[크론] 스킵: {name} — 이미 등록됨")
        return
    minute = max(0, min(59, int(minute)))
    _jobs.append({
        "name": name,
        "hour": None,
        "minute": minute,
        "weekday": None,
        "func": func,
        "type": "hourly",
    })
    now = _now_kst()
    next_t = now.replace(minute=minute, second=0, microsecond=0)
    if now >= next_t:
        next_t += timedelta(hours=1)
    print(f"[크론] 등록: {name} — 매시간 {minute:02d}분 KST (다음: {next_t.strftime('%m/%d %H:%M')})")


def set_hourly(name: str, minute: int, func: Callable, enabled: bool = True):
    """매시간 작업을 런타임에 추가/수정/비활성화."""
    global _jobs
    minute = max(0, min(59, int(minute)))
    existing = next((j for j in _jobs if j["name"] == name), None)
    if not enabled:
        before = len(_jobs)
        _jobs = [j for j in _jobs if j["name"] != name]
        if before != len(_jobs):
            print(f"[크론] 비활성화: {name}")
        return
    if existing:
        existing.update({
            "hour": None,
            "minute": minute,
            "weekday": None,
            "func": func,
            "type": "hourly",
        })
        print(f"[크론] 수정: {name} — 매시간 {minute:02d}분 KST")
        return
    add_hourly(name, minute, func)


def add_weekly(name: str, weekday: int, hour: int, minute: int, func: Callable):
    """매주 특정 요일 실행 작업 등록. weekday: 0=월~6=일. 같은 이름 중복 방지."""
    if any(j["name"] == name for j in _jobs):
        print(f"[크론] 스킵: {name} — 이미 등록됨")
        return
    day_names = ["월", "화", "수", "목", "금", "토", "일"]
    _jobs.append({
        "name": name,
        "hour": hour,
        "minute": minute,
        "weekday": weekday,
        "func": func,
        "type": "weekly",
    })
    next_t = _next_run(hour, minute, weekday)
    print(f"[크론] 등록: {name} — 매주 {day_names[weekday]} {hour:02d}:{minute:02d} KST (다음: {next_t.strftime('%m/%d %H:%M')})")


async def _run_job(job: dict):
    """작업 실행 (동기/비동기 모두 지원)."""
    name = job["name"]
    print(f"\n[크론] ▶ {name} 시작 ({_now_kst().strftime('%m/%d %H:%M')})")
    try:
        result = job["func"]()
        if asyncio.iscoroutine(result):
            result = await result
        print(f"[크론] ✅ {name} 완료")
        # 텔레그램 알림 (실패 시에만 — 성공은 각 모듈이 자체 알림)
    except Exception as e:
        print(f"[크론] ❌ {name} 실패: {e}")
        try:
            from modules.utils.notify import notify_warning
            notify_warning("크론", f"{name} 실패: {str(e)[:150]}")
        except Exception:
            pass


async def _scheduler_loop():
    """메인 스케줄러 루프 — 1분마다 체크."""
    global _running
    if not _running:
        return  # start()에서 중지 신호를 받은 경우
    print(f"[크론] 스케줄러 시작 ({len(_jobs)}개 작업)")

    # 헬스체크 — 등록된 잡 수 확인 + 텔레그램 알림
    # 기본 상시 작업:
    # - 일일 성과 기록
    # - 재생목록 소급 분류
    # - 일일 비용 결산
    # - 모닝 브리핑
    expected_jobs = 4
    if os.getenv("WEEKLY_TOPICS_CRON_ENABLED", "false").lower() in {"1", "true", "yes", "on"}:
        expected_jobs += 1
    if os.getenv("AUTO_DEPLOY_CRON_ENABLED", "false").lower() in {"1", "true", "yes", "on"}:
        expected_jobs += 1
    if os.getenv("ROLLOUT_EXPANSION_CRON_ENABLED", "true").lower() in {"1", "true", "yes", "on"}:
        expected_jobs += 1
    try:
        from modules.utils.cost_tracker import load_billing_settings
        if load_billing_settings().get("cron_enabled", True):
            expected_jobs += 1
    except Exception:
        expected_jobs += 1
    if len(_jobs) < expected_jobs:
        try:
            from modules.utils.notify import notify_warning
            notify_warning("크론", f"등록된 잡 {len(_jobs)}개 — 예상 {expected_jobs}개. 누락 확인 필요!")
        except Exception:
            pass
    else:
        job_names = ", ".join(j["name"] for j in _jobs)
        print(f"[크론] 헬스체크 OK — {len(_jobs)}개 잡: {job_names}")

    while _running:
        now = _now_kst()
        for job in _jobs:
            # 현재 시각의 시:분이 스케줄과 일치하는지만 체크 (±초 윈도우 제거)
            if job.get("weekday") is not None and now.weekday() != job["weekday"]:
                continue
            if job.get("type") == "hourly":
                if now.minute != job["minute"]:
                    continue
            elif now.hour != job["hour"] or now.minute != job["minute"]:
                continue
            # 이번 분에 이미 실행했으면 스킵 (중복 방지)
            last_run = job.get("_last_run")
            if last_run and (now - last_run).total_seconds() < 120:
                continue
            job["_last_run"] = now
            asyncio.create_task(_run_job(job))

        await asyncio.sleep(30)  # 30초마다 체크


def _run_in_thread():
    """별도 스레드에서 이벤트 루프 실행."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_scheduler_loop())


def start():
    """크론 스케줄러 시작 (백그라운드 스레드). reload 시 이전 스레드 중지."""
    global _thread, _running, _started_once
    # uvicorn reload 시 이전 스레드 정리
    if _started_once:
        _running = False  # 이전 스레드의 루프 중단 신호
        import time
        time.sleep(0.5)  # 이전 루프가 sleep 중이면 빠져나올 시간 확보
    if _thread and _thread.is_alive():
        print("[크론] 이전 스레드 대기 중...")
        _running = False
        _thread.join(timeout=2)
    _started_once = True
    _running = True
    _thread = threading.Thread(target=_run_in_thread, daemon=True)
    _thread.start()


def stop():
    """크론 스케줄러 중지."""
    global _running
    _running = False
    print("[크론] 스케줄러 중지")


def get_status() -> dict[str, Any]:
    """현재 크론 상태 반환."""
    now = _now_kst()
    day_names = ["월", "화", "수", "목", "금", "토", "일"]
    jobs_info = []
    for job in _jobs:
        if job.get("type") == "hourly":
            next_t = now.replace(minute=job["minute"], second=0, microsecond=0)
            if now >= next_t:
                next_t += timedelta(hours=1)
            schedule = f"매시간 {job['minute']:02d}분 KST"
        else:
            next_t = _next_run(job["hour"], job["minute"], job.get("weekday"))
            if job.get("weekday") is not None:
                schedule = f"매주 {day_names[job['weekday']]} {job['hour']:02d}:{job['minute']:02d} KST"
            else:
                schedule = f"{job['hour']:02d}:{job['minute']:02d} KST"
        jobs_info.append({
            "name": job["name"],
            "type": job["type"],
            "schedule": schedule,
            "next_run": next_t.strftime("%Y-%m-%d %H:%M KST"),
            "last_run": job.get("_last_run", "").isoformat() if job.get("_last_run") else None,
        })
    return {"running": _running, "jobs": jobs_info}
