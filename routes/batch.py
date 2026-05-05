"""배치 생성 큐 API 라우터."""

import os
import json
import asyncio
import threading
import re
import traceback

from pydantic import BaseModel, Field
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/batch", tags=["batch"])

# ── Pydantic models ──

class BatchJobRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    language: str = "ko"
    cameraStyle: str = "auto"
    bgmTheme: str = "random"
    llmProvider: str = "gemini"
    videoEngine: str = "veo3"
    imageEngine: str = "imagen"
    channel: str | None = None

class BatchBulkRequest(BaseModel):
    jobs: list[BatchJobRequest]

# ── 배치 전용 모듈 변수 ──

_batch_running = False
_batch_stop = threading.Event()


def _load_deploy_success_map(target_date_str: str) -> set[str]:
    """auto_deploy 성공 결과를 topic/channel 키 집합으로 읽는다."""
    try:
        from modules.scheduler.auto_deploy import STATE_FILE

        if not os.path.exists(STATE_FILE):
            return set()
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        if state.get("current_date") != target_date_str:
            return set()
        completed: set[str] = set()
        for row in state.get("results", []):
            if row.get("status") != "success":
                continue
            channel = str(row.get("channel", "")).strip()
            topic_group = str(row.get("topic_group") or row.get("topic") or "").strip()
            if channel and topic_group:
                completed.add(f"{topic_group}::{channel}")
        return completed
    except Exception:
        return set()


def _load_task_completion_map(target_date_str: str) -> set[str]:
    try:
        from modules.utils.today_tasks import get_completed_keys

        return get_completed_keys(target_date_str)
    except Exception:
        return set()


def _is_topic_header_marked(file_path: str, topic_group: str) -> bool:
    """Day 헤더가 ✅/☑️/✔️ 처리되어 있는지 확인."""
    if not file_path or not os.path.exists(file_path):
        return False
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return False

    for match in re.finditer(r"^## \d+\.\s*(.+)$", content, re.MULTILINE):
        header = match.group(1).strip()
        normalized = re.sub(r"^(?:✅|☑️|✔️)\s*", "", header).strip()
        normalized = re.sub(r"\s+\[[^\]]+\]", "", normalized).strip()
        if normalized == topic_group.strip():
            return bool(re.match(r"^(?:✅|☑️|✔️)\s*", header))
    return False


def _has_generated_output(topic_name: str, channel: str) -> bool:
    """토픽/채널 폴더에 실제 렌더 영상 산출물이 있는지 확인."""
    slug = re.sub(r"[^\w\s-]", "", topic_name or "", flags=re.UNICODE).strip()
    slug = re.sub(r"\s+", "_", slug).strip("_")
    if not slug:
        return False

    folder_path = os.path.join("assets", f"{slug}_{channel}")
    if not os.path.isdir(folder_path):
        return False

    candidate_dirs = [
        os.path.join(folder_path, "video"),
        os.path.join(folder_path, "video_clips"),
    ]
    for path in candidate_dirs:
        if os.path.isdir(path):
            try:
                if any(
                    entry.is_file() and entry.name.lower().endswith((".mp4", ".mov", ".webm"))
                    for entry in os.scandir(path)
                ):
                    return True
            except Exception:
                continue

    try:
        return any(
            entry.is_file() and entry.name.lower().endswith((".mp4", ".mov", ".webm"))
            for entry in os.scandir(folder_path)
        )
    except Exception:
        return False


@router.post("/add")
async def batch_add(req: BatchJobRequest):
    from modules.utils.batch import add_job
    job_id = add_job(req.topic, req.language, req.cameraStyle, req.bgmTheme, req.llmProvider, req.videoEngine, req.imageEngine, req.channel)
    return {"id": job_id, "message": f"작업 #{job_id} 큐에 추가됨"}


@router.post("/add-bulk")
async def batch_add_bulk(req: BatchBulkRequest):
    from modules.utils.batch import add_jobs_bulk
    topics = [j.model_dump() for j in req.jobs]
    ids = add_jobs_bulk(topics)
    return {"ids": ids, "message": f"{len(ids)}개 작업 큐에 추가됨"}


@router.get("/queue")
async def batch_queue():
    from modules.utils.batch import get_queue, get_stats
    return {"jobs": get_queue(), "stats": get_stats()}


@router.get("/stats")
async def batch_stats():
    from modules.utils.batch import get_stats
    return get_stats()


@router.post("/start")
async def batch_start():
    """배치 큐의 대기 작업을 순차 실행합니다."""
    global _batch_running
    if os.getenv("ENABLE_LEGACY_BATCH_EXECUTION", "false").lower() not in {"1", "true", "yes", "on"}:
        return JSONResponse(
            status_code=409,
            content={
                "running": False,
                "message": "레거시 배치 실행은 안전장치 우회를 막기 위해 비활성화되었습니다. 오늘 할 일/auto_deploy 경로를 사용하세요.",
            },
        )
    if _batch_running:
        return {"message": "배치가 이미 실행 중입니다", "running": True}
    _batch_stop.clear()
    _batch_running = True

    async def _run_batch():
        global _batch_running
        from modules.utils.batch import get_next_pending, update_job, get_job
        from modules.gpt.cutter import generate_cuts
        from modules.image.dalle import generate_image as generate_image_dalle
        from modules.image.imagen import generate_image_imagen
        from modules.tts.elevenlabs import generate_tts
        from modules.transcription.whisper import align_words_with_script, generate_word_timestamps
        from modules.video.remotion import create_remotion_video
        from modules.utils.audio import normalize_audio_lufs
        from modules.utils.keys import get_google_key, count_google_keys
        from modules.utils.channel_config import get_channel_preset
        from routes.shared import cut_executor
        from datetime import datetime
        loop = asyncio.get_running_loop()
        try:
            while not _batch_stop.is_set():
                job = get_next_pending()
                if not job:
                    print("[배치] 대기 작업 없음 — 배치 완료")
                    break
                job_id = job["id"]
                print(f"[배치] 작업 #{job_id} 시작: {job['topic']}")
                update_job(job_id, status="running", started_at=datetime.now().isoformat())

                try:
                    # 기획 (Gemini 키 로테이션 재시도 — 메인 생성과 동일 패턴)
                    cuts, topic_folder, title = None, None, None
                    _excluded = set()
                    for _attempt in range(max(count_google_keys(), 1)):
                        llm_key = get_google_key(None, service="gemini", exclude=_excluded) if job["llm_provider"] == "gemini" else None
                        try:
                            cuts, topic_folder, title, _tags, _desc, _fact_ctx = await loop.run_in_executor(
                                None,
                                lambda k=llm_key: generate_cuts(
                                    job["topic"],
                                    lang=job["language"],
                                    llm_provider=job["llm_provider"],
                                    llm_key_override=k,
                                    channel=job.get("channel"),
                                    format_type=job.get("format_type"),
                                    series_title=job.get("series_title"),
                                ),
                            )
                            break
                        except Exception as _e:
                            if "429" in str(_e) and llm_key:
                                from modules.utils.keys import mark_key_exhausted
                                mark_key_exhausted(llm_key, "gemini")
                                _excluded.add(llm_key)
                                print(f"[배치] 작업 #{job_id} Gemini 키 재시도 ({_attempt+1})")
                                continue
                            raise
                    if cuts is None:
                        raise RuntimeError("기획 생성 실패 — 모든 키 소진")

                    # 이미지 + TTS + Whisper (순차)
                    visual_paths, audio_paths, scripts, word_ts_list = [], [], [], []
                    for i, cut in enumerate(cuts):
                        if job["image_engine"] == "imagen":
                            img = await loop.run_in_executor(None, lambda idx=i, c=cut: generate_image_imagen(c["prompt"], idx, topic_folder))
                        else:
                            img = await loop.run_in_executor(None, lambda idx=i, c=cut: generate_image_dalle(c["prompt"], idx, topic_folder))
                        visual_paths.append(img)

                        _batch_vs = None
                        _batch_preset = get_channel_preset(job.get("channel"))
                        if _batch_preset:
                            _batch_vs = _batch_preset.get("voice_settings")
                        _batch_emotion = None
                        _batch_desc = cut.get("description", cut.get("text", ""))
                        for _tag in ["SHOCK", "WONDER", "TENSION", "REVEAL", "URGENCY", "DISBELIEF", "IDENTITY", "CALM", "LOOP"]:
                            if f"[{_tag}]" in _batch_desc:
                                _batch_emotion = _tag
                                break
                        aud = await loop.run_in_executor(
                            None,
                            lambda idx=i, c=cut, e=_batch_emotion: generate_tts(
                                c["script"],
                                idx,
                                topic_folder,
                                language=job["language"],
                                voice_settings=_batch_vs,
                                emotion=e,
                                channel=job.get("channel"),
                            ),
                        )
                        if aud:
                            aud = normalize_audio_lufs(aud)
                        audio_paths.append(aud)

                        words = []
                        if aud:
                            _aud, _lang = aud, job["language"]
                            _script_for_align = cut.get("script", "")
                            try:
                                words = await loop.run_in_executor(None, lambda a=_aud, l=_lang: generate_word_timestamps(a, language=l))
                                words = align_words_with_script(words, _script_for_align, lang=_lang)
                            except Exception as _ts_exc:
                                print(f"[배치] 컷 {i+1} 타임스탬프 실패 — 렌더 폴백 사용: {_ts_exc}")
                        word_ts_list.append(words)
                        scripts.append(cut["script"])

                    # ── 렌더 전 가드: 승인 안 된 항목은 draft로 멈춤 ──
                    # 배치 자동 실행 시: 생성 완료 후 draft 상태로 저장하고 렌더 건너뜀
                    # 수동 승인(mark_approved) 후에만 렌더 진행
                    _job_fresh = get_job(job_id)
                    _prompt_st = (_job_fresh or {}).get("prompt_status", "draft")
                    _fact_st = (_job_fresh or {}).get("fact_check_status", "pending")

                    if _prompt_st != "approved" or _fact_st != "verified":
                        # 생성은 완료됐지만 검수 미완 → draft 상태로 대기
                        update_job(job_id, status="draft", completed_at=datetime.now().isoformat())
                        print(f"[배치] 작업 #{job_id} 생성 완료 → 검수 대기 (prompt={_prompt_st}, fact={_fact_st})")
                        continue  # 렌더 건너뛰고 다음 작업으로

                    # 렌더링 (승인된 항목만 도달)
                    video_path = await loop.run_in_executor(
                        None, lambda: create_remotion_video(
                            visual_paths, audio_paths, scripts, word_ts_list, topic_folder,
                            title=title, camera_style=job["camera_style"], bgm_theme=job["bgm_theme"],
                            channel=job.get("channel"),
                            descriptions=[c.get("description", "") for c in cuts],
                        )
                    )

                    if video_path:
                        update_job(job_id, status="completed", video_path=video_path, completed_at=datetime.now().isoformat())
                        print(f"OK [배치] 작업 #{job_id} 완료: {video_path}")
                    else:
                        update_job(job_id, status="failed", error="Remotion 렌더링 실패", completed_at=datetime.now().isoformat())

                except Exception as e:
                    from datetime import datetime as _dt
                    update_job(job_id, status="failed", error=str(e)[:500], completed_at=_dt.now().isoformat())
                    print(f"[배치 오류] 작업 #{job_id}: {e}")

        finally:
            _batch_running = False
            print("[배치] 배치 프로세스 종료")

    asyncio.create_task(_run_batch())
    return {"message": "배치 실행 시작", "running": True}


@router.post("/stop")
async def batch_stop():
    global _batch_running
    _batch_stop.set()
    return {"message": "배치 중지 요청됨 (현재 작업 완료 후 중지)", "running": _batch_running}


@router.delete("/job/{job_id}")
async def batch_delete(job_id: int):
    from modules.utils.batch import delete_job
    ok = delete_job(job_id)
    return {"success": ok, "message": f"작업 #{job_id} {'삭제됨' if ok else '삭제 불가 (실행 중이거나 존재하지 않음)'}"}


@router.post("/clear")
async def batch_clear():
    from modules.utils.batch import clear_completed
    count = clear_completed()
    return {"cleared": count, "message": f"완료/실패 작업 {count}건 정리됨"}


# ── 검수 워크플로우 API ──────────────────────────────────────────

@router.post("/job/{job_id}/approve")
async def batch_approve(job_id: int):
    """팩트체크 + 검수 완료된 작업을 최종 승인합니다."""
    from modules.utils.batch import get_job, mark_approved
    job = get_job(job_id)
    if not job:
        return {"success": False, "message": f"작업 #{job_id} 없음"}
    ok = mark_approved(job_id)
    if not ok:
        return {"success": False, "message": f"작업 #{job_id}은 현재 상태에서 승인할 수 없습니다 (running/completed)"}
    return {"success": True, "message": f"작업 #{job_id} 승인 완료 — 렌더 가능"}


@router.post("/job/{job_id}/verify")
async def batch_verify(job_id: int):
    """팩트체크 통과 표시."""
    from modules.utils.batch import get_job, mark_verified
    job = get_job(job_id)
    if not job:
        return {"success": False, "message": f"작업 #{job_id} 없음"}
    mark_verified(job_id)
    return {"success": True, "message": f"작업 #{job_id} 팩트체크 통과"}


@router.post("/job/{job_id}/review")
async def batch_review(job_id: int, notes: str = ""):
    """검토 완료 표시 (코멘트 포함 가능)."""
    from modules.utils.batch import get_job, mark_reviewed
    job = get_job(job_id)
    if not job:
        return {"success": False, "message": f"작업 #{job_id} 없음"}
    mark_reviewed(job_id, notes=notes or None)
    return {"success": True, "message": f"작업 #{job_id} 검토 완료"}


@router.post("/job/{job_id}/flag-risky")
async def batch_flag_risky(job_id: int, notes: str = ""):
    """팩트체크 위험 표시."""
    from modules.utils.batch import get_job, mark_risky
    job = get_job(job_id)
    if not job:
        return {"success": False, "message": f"작업 #{job_id} 없음"}
    mark_risky(job_id, notes=notes or None)
    return {"success": True, "message": f"작업 #{job_id} 위험 표시됨"}


# ── 옵시디언 Day 파일 연계 API ───────────────────────────────────

@router.post("/import-day")
async def batch_import_day(file_path: str = None, date: str = None):
    """옵시디언 Day 파일을 파싱하여 batch 큐에 등록합니다.

    Args:
        file_path: Day 파일 직접 경로 (예: "Day 01 (3-25).md")
        date: 날짜 문자열 (예: "2026-03-25") — file_path 없으면 날짜로 검색
    """
    from modules.utils.obsidian_parser import parse_day_file, find_day_file_by_date, DEFAULT_VAULT_PATH
    from modules.utils.batch import add_job, update_job
    import json as _json

    # 파일 경로 결정
    if file_path:
        # 절대경로가 아니면 볼트 경로 기준으로
        if not os.path.isabs(file_path):
            file_path = os.path.join(DEFAULT_VAULT_PATH, file_path)
    elif date:
        from datetime import datetime as _dt
        target = _dt.strptime(date, "%Y-%m-%d")
        file_path = find_day_file_by_date(target)
    else:
        return {"success": False, "message": "file_path 또는 date를 입력해주세요"}

    if not file_path or not os.path.exists(file_path):
        return {"success": False, "message": f"파일을 찾을 수 없습니다: {file_path}"}

    try:
        jobs = parse_day_file(file_path)
    except Exception as e:
        return {"success": False, "message": f"파싱 오류: {e}"}

    if not jobs:
        return {"success": False, "message": "파싱된 주제가 없습니다"}

    # batch 큐에 등록 (topic + channel 기준 중복 체크)
    created_ids = []
    skipped = 0
    for job in jobs:
        # 중복 체크: 같은 topic + channel이 이미 active 상태면 스킵
        from modules.utils.batch import _get_conn, _lock
        with _lock:
            conn = _get_conn()
            try:
                dup = conn.execute(
                    "SELECT COUNT(*) as cnt FROM batch_jobs WHERE topic = ? AND channel = ? AND status IN ('pending', 'draft', 'running', 'reviewed', 'approved')",
                    (job["topic"], job["channel"]),
                ).fetchone()
                if dup["cnt"] > 0:
                    skipped += 1
                    continue
            finally:
                conn.close()

        job_id = add_job(
            topic=job["topic"],
            language=job["language"],
            channel=job["channel"],
        )
        # Day 파일의 메타데이터를 draft에 저장
        update_job(job_id,
            draft_title=job["title"],
            draft_tags=job.get("hashtags", ""),
            series_title=job.get("series_title"),
            obsidian_uri=job.get("obsidian_uri"),
            format_type=job.get("format_type"),
            review_notes=f"Imported from {job.get('source_file', 'Obsidian')}",
        )
        created_ids.append(job_id)

    return {
        "success": True,
        "message": f"{os.path.basename(file_path)}에서 {len(created_ids)}개 작업 등록 (스킵: {skipped})",
        "job_ids": created_ids,
        "file": os.path.basename(file_path),
        "total_jobs": len(created_ids),
    }


@router.post("/import-today")
async def batch_import_today():
    """오늘 날짜의 Day 파일을 자동 감지하여 batch 큐에 등록합니다."""
    from modules.utils.obsidian_parser import find_today_file
    path = find_today_file()
    if not path:
        from datetime import datetime as _dt
        today = _dt.now()
        return {"success": False, "message": f"오늘({today.month}-{today.day}) Day 파일을 찾을 수 없습니다"}
    return await batch_import_day(file_path=path)


@router.get("/today-topics")
async def batch_today_topics(channel: str | None = None, date: str | None = None):
    """Day 파일의 주제 목록을 반환합니다. 완료 상태 + Day 네비게이션 포함.

    Args:
        channel: 특정 채널만 필터. None이면 전체.
        date: YYYY-MM-DD 형식. None이면 오늘.
    """
    from modules.utils.obsidian_parser import get_today_topics, find_day_file_by_date, list_day_files
    from datetime import datetime as _dt, timedelta

    # 날짜 파싱 (KST 기준)
    from datetime import timezone
    KST = timezone(timedelta(hours=9))
    if date:
        try:
            target_date = _dt.strptime(date, "%Y-%m-%d")
        except ValueError:
            target_date = _dt.now(KST)
    else:
        target_date = _dt.now(KST)

    result = get_today_topics(channel=channel, target_date=target_date)
    if not result.get("file"):
        return {"success": False, "message": f"{target_date.month}-{target_date.day} Day 파일을 찾을 수 없습니다", "topics": [], "current_date": target_date.strftime("%Y-%m-%d")}

    # 완료 상태 체크: Day 헤더 ✅ + auto_deploy 성공 상태 + 실제 생성 산출물
    target_date_str = target_date.strftime("%Y-%m-%d")
    deploy_success = _load_deploy_success_map(target_date_str)
    task_completed = _load_task_completion_map(target_date_str)
    for topic in result["topics"]:
        topic_name = topic.get("topic_group", "")
        header_marked = _is_topic_header_marked(result.get("file_path", ""), topic_name)
        topic_channels = list((topic.get("channels") or {}).keys())
        completed_channels = []
        for ch in topic_channels:
            state_key = f"{topic_name}::{ch}"
            if ch in completed_channels:
                continue
            if state_key in task_completed or state_key in deploy_success or _has_generated_output(topic_name, ch):
                completed_channels.append(ch)
        topic["header_marked"] = header_marked
        topic["completed_channels"] = completed_channels
        topic["is_completed"] = header_marked or (
            len(completed_channels) >= len(topic_channels) and len(completed_channels) > 0
        )

    # 이전/다음 Day 파일 찾기
    day_files = sorted(list_day_files())
    current_file = result["file"]
    current_idx = -1
    for i, f in enumerate(day_files):
        if os.path.basename(f) == current_file:
            current_idx = i
            break

    prev_date = None
    next_date = None
    if current_idx > 0:
        # 이전 파일에서 날짜 추출: Day XX (M-DD).md
        prev_name = os.path.basename(day_files[current_idx - 1])
        m = re.search(r"\((\d+)-(\d+)\)", prev_name)
        if m:
            prev_date = f"{target_date.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    if current_idx >= 0 and current_idx < len(day_files) - 1:
        next_name = os.path.basename(day_files[current_idx + 1])
        m = re.search(r"\((\d+)-(\d+)\)", next_name)
        if m:
            next_date = f"{target_date.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

    return {
        "success": True,
        "file": result["file"],
        "topics": result["topics"],
        "total": len(result["topics"]),
        "current_date": target_date.strftime("%Y-%m-%d"),
        "prev_date": prev_date,
        "next_date": next_date,
    }


@router.get("/task-history")
async def batch_task_history(
    search: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 300,
):
    """오늘 할 일 실행/완료 DB 목록. 검색/채널/날짜 필터 지원."""
    from modules.utils.today_tasks import list_task_history

    tasks = list_task_history(
        search=search,
        channel=channel,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    return {"success": True, "tasks": tasks, "total": len(tasks)}


@router.get("/day-files")
async def batch_list_day_files():
    """볼트의 모든 Day 파일 목록을 반환합니다."""
    from modules.utils.obsidian_parser import list_day_files
    files = list_day_files()
    return {
        "files": [os.path.basename(f) for f in files],
        "total": len(files),
    }
