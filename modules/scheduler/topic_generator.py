"""주간 토픽 자동 생성 — 성과 분석 기반 + LLM 전문가 프롬프트.

흐름:
  1. 성과 데이터 수집 (카테고리별 평균, 훅 패턴별 성과)
  2. 기존 Day 파일에서 사용한 토픽 추출 (중복 방지)
  3. LLM 토픽 전문가가 7일분 토픽 생성
  4. 출력 검증 (포맷/채널/토픽수)
  5. Day 파일로 저장
  6. 텔레그램으로 검수 요청 알림

사용:
  POST /api/scheduler/generate-topics?start_date=2026-04-16&days=7
"""
import os
import json
import re
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

# Day 파일 저장 경로
DAY_FILES_DIR = os.getenv(
    "DAY_FILES_DIR",
    r"C:\Users\Storm Credit\Desktop\쇼츠\askanything",
)
TOPIC_LOG_DIR = os.getenv("TOPIC_LOG_DIR", os.path.join("assets", "_topic_logs"))
YOUTUBE_STATS_DIR = os.getenv("YOUTUBE_STATS_DIR", os.path.join("assets", "_stats"))

# ── 카테고리 정의 (분석 엔진과 이름 통일) ──
CATEGORIES_PROVEN = ["심해/바다", "우주/행성", "공룡/고생물", "지구/자연", "동물"]  # 성과 검증됨
CATEGORIES_TEST = ["역사/문명", "물리/화학", "기술/공학", "인체/심리"]  # 신규 테스트

# ── 훅 패턴 이름 매핑 (분석 엔진 ↔ 프롬프트 통일) ──
HOOK_NAME_MAP = {
    "question": "① 불가능/의문",
    "number_shock": "② 숫자 앵커",
    "negation_reveal": "③ 부정 반전",
    "hidden_secret": "④ 숨겨진/미스터리",
    "superlative": "⑤ 비교/최상급",
    "comparison": "⑥ 대비/비교",
    "sensory": "⑦ 감각/체험",
}


def _get_tracked_channels() -> list[str]:
    """주제 중복 검사에 포함할 운영 채널 목록."""
    try:
        from modules.utils.channel_config import get_channel_names

        channels = [str(name).strip() for name in get_channel_names() if str(name).strip()]
        if channels:
            return channels
    except Exception:
        pass
    return ["askanything", "wonderdrop", "exploratodo", "prismtale"]


def _get_performance_context() -> str:
    """성과 분석 데이터를 LLM 컨텍스트용 텍스트로 변환."""
    try:
        from modules.analytics.performance_tracker import analyze_hook_patterns
        from modules.scheduler.weekly_stats_update import collect_and_analyze

        summary = collect_and_analyze()
        hooks = analyze_hook_patterns()

        lines = ["## 채널 성과 데이터 (최근)"]
        for ch, data in summary.items():
            lines.append(f"\n### {ch}")
            lines.append(f"- 평균 조회: {data.get('avg_views', 0):,}")
            lines.append(f"- 최근 7일: {data.get('recent_7d_views', 0):,}")
            if data.get("top_5"):
                lines.append("- Top 5:")
                for v in data["top_5"]:
                    lines.append(f"  - {v['title']} — {v['views']:,}")
            if data.get("category_avg"):
                lines.append("- 카테고리별 평균:")
                for cat, avg in sorted(data["category_avg"].items(), key=lambda x: -x[1]):
                    if avg > 0:
                        lines.append(f"  - {cat}: {avg:,}")

        # 훅 패턴 성과 (통일된 이름으로)
        lines.append("\n## 훅 패턴별 평균 조회")
        for ch, patterns in hooks.items():
            lines.append(f"\n### {ch}")
            for pname, pdata in patterns.items():
                display_name = HOOK_NAME_MAP.get(pname, pname)
                lines.append(f"  - {display_name}: avg {pdata['avg_views']:,} ({pdata['count']}건)")

        return "\n".join(lines)
    except Exception as e:
        print(f"[토픽 생성] 성과 데이터 로드 실패: {e}")
        return "성과 데이터 없음 — 일반적 바이럴 쇼츠 토픽 전략 사용"


def _get_recent_uploaded_topics(channel: str = "askanything", limit: int = 100) -> list[str]:
    """최근 실업로드 제목을 중복 금지 목록으로 불러온다."""
    history_titles = _get_uploaded_history_topics(channel, limit=limit)
    if history_titles:
        return history_titles[:limit]

    path = Path(YOUTUBE_STATS_DIR) / f"{channel}_stats.json"
    cached_titles: list[str] = []
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            videos = payload.get("videos", [])[:limit]
            cached_titles = [str(v.get("title", "")).strip() for v in videos if str(v.get("title", "")).strip()]
        except Exception as e:
            print(f"[토픽 생성] 업로드 이력 캐시 로드 실패 ({channel}): {e}")

    if len(cached_titles) >= limit:
        return cached_titles[:limit]

    try:
        from modules.utils.youtube_stats import fetch_channel_stats

        payload = fetch_channel_stats(channel, max_results=limit)
        videos = payload.get("videos", [])[:limit]
        fresh_titles = [str(v.get("title", "")).strip() for v in videos if str(v.get("title", "")).strip()]
        if fresh_titles:
            return fresh_titles[:limit]
    except Exception as e:
        print(f"[토픽 생성] 업로드 이력 실조회 실패 ({channel}): {e}")

    return cached_titles[:limit]


def _get_uploaded_history_topics(channel: str = "askanything", limit: int | None = None) -> list[str]:
    """누적 업로드 이력을 DB에서 읽고, 비어 있으면 YouTube API로 보강한다."""
    sync_limit = max(int(os.getenv("TOPIC_UPLOAD_HISTORY_SYNC_LIMIT", "1000")), limit or 0)
    try:
        from modules.utils.upload_history import (
            count_uploaded_records,
            get_uploaded_titles,
            sync_channel_history,
            upsert_videos,
        )

        record_count = count_uploaded_records(channel)
        titles = get_uploaded_titles(channel=channel, limit=limit)

        if not titles:
            path = Path(YOUTUBE_STATS_DIR) / f"{channel}_stats.json"
            if path.exists():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    cached_videos = payload.get("videos", [])
                    if cached_videos:
                        upsert_videos(channel, cached_videos, source="stats_cache")
                        titles = get_uploaded_titles(channel=channel, limit=limit)
                        record_count = count_uploaded_records(channel)
                except Exception as cache_error:
                    print(f"[토픽 생성] 업로드 이력 캐시→DB 시드 실패 ({channel}): {cache_error}")

        needs_sync = record_count == 0
        if limit is None and record_count < sync_limit:
            needs_sync = True
        if limit is not None and len(titles) < min(limit, sync_limit):
            needs_sync = True

        if needs_sync:
            synced_count = sync_channel_history(channel, max_results=sync_limit)
            if synced_count:
                titles = get_uploaded_titles(channel=channel, limit=limit)

        return titles[:limit] if limit else titles
    except Exception as e:
        print(f"[토픽 생성] 업로드 이력 DB 조회 실패 ({channel}): {e}")
        return []


def _get_all_uploaded_history_topics(limit_per_channel: int | None = None) -> list[str]:
    """운영 채널 전체의 실업로드 제목을 모아 반환한다."""
    all_titles: list[str] = []
    for channel in _get_tracked_channels():
        titles = _get_uploaded_history_topics(channel, limit=limit_per_channel)
        if not titles and limit_per_channel:
            titles = _get_recent_uploaded_topics(channel, limit=limit_per_channel)
        all_titles.extend(titles)

    deduped: list[str] = []
    seen: set[str] = set()
    for title in all_titles:
        key = title.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def _get_used_topics() -> list[str]:
    """기존 Day 파일 + 최근 실업로드 제목 전체 추출 (중복 방지)."""
    used = []
    try:
        for fname in sorted(os.listdir(DAY_FILES_DIR)):
            if fname.startswith("Day") and fname.endswith(".md"):
                path = os.path.join(DAY_FILES_DIR, fname)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                # 토픽 제목 추출 (여러 패턴 지원)
                for m in re.finditer(r"## \d+\.\s+\S+\s+(.+?)\s+\[", content):
                    topic = m.group(1).strip()
                    if topic:
                        used.append(topic)
                # 제목 라인에서도 추출 (패턴 2)
                for m in re.finditer(r"(?:제목|Title|Titulo):\s*(.+)", content):
                    title = m.group(1).strip()
                    if title and len(title) > 3:
                        used.append(title)
                for m in re.finditer(
                    r"^\s*(?:원본주제|Source Topic|Tema Base|Tema Fuente):\s*(.+)$",
                    content,
                    re.MULTILINE,
                ):
                    source_topic = m.group(1).strip()
                    if source_topic and len(source_topic) > 3:
                        used.append(source_topic)
    except Exception as e:
        print(f"[토픽 생성] 기존 토픽 로드 실패: {e}")
    uploaded_titles = _get_all_uploaded_history_topics(limit_per_channel=None)
    if not uploaded_titles:
        uploaded_titles = _get_all_uploaded_history_topics(limit_per_channel=100)
    used.extend(uploaded_titles)
    return list(set(used))  # 중복 제거


def _find_existing_day_number_for_date(date_str: str) -> int | None:
    """같은 월-일 Day 파일이 이미 있으면 그 번호를 재사용한다."""
    try:
        pattern = re.compile(rf"^Day (\d+) \({re.escape(date_str)}\)\.md$")
        matches: list[int] = []
        for fname in os.listdir(DAY_FILES_DIR):
            match = pattern.match(fname)
            if match:
                matches.append(int(match.group(1)))
        return min(matches) if matches else None
    except Exception:
        return None


def _normalize_topic_for_duplicate(text: str) -> str:
    """중복 비교용 토픽 정규화.

    이 검사는 LLM에게 맡긴 중복 금지를 코드 레벨에서 한 번 더 막기 위한 안전장치다.
    """
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"^(?:✅\s*)?[\W_]*", " ", text, flags=re.UNICODE)
    text = re.sub(r"^(?:제목|Title|Titulo|Título)\s*:\s*", " ", text, flags=re.IGNORECASE)
    text = text.lower()
    text = re.sub(r"[^0-9a-z가-힣áéíóúüñ¿?]+", "", text)
    return text.strip()


_SEMANTIC_DUPLICATE_PATTERNS: list[tuple[str, list[str]]] = [
    ("black_hole_time", [r"블랙홀", r"black\s*hole"]),
    ("saturn_moon_ring_cycle", [
        r"토성.*(?:고리|달|위성)",
        r"토성.*(?:녹|부서|사라지|비|강|호수)",
        r"고리.*달",
        r"saturn.*(?:ring|moon|titan)",
        r"titan.*(?:rain|river|lake)",
    ]),
    ("frankfurt_roman_sanctuary", [
        r"프랑크푸르트",
        r"frankfurt",
        r"로마\s*(?:성역|성소)",
        r"roman\s+(?:sanctuary|shrine)",
        r"(?:도시|독일|지하).*(?:로마\s*(?:성역|성소)|금지된\s*의식)",
    ]),
    ("deep_sea_new_species", [r"심해.*(?:신종|종\s*발견|산호초)", r"아르헨티나.*심해", r"deep\s*sea.*(?:species|coral)"]),
    ("deep_sea_24_species", [r"심해.*24\s*종", r"24\s*종.*(?:생명체|신종|종)", r"deep\s*sea.*24\s*(?:species|life)"]),
    ("undersea_river_brine", [
        r"바다\s*밑.*강",
        r"바닷속.*강",
        r"해저.*강",
        r"죽은\s*강",
        r"바닷속.*폭포",
        r"undersea.*river",
        r"brine.*pool",
    ]),
    ("earth_like_exoplanet", [
        r"hd\s*137010",
        r"지구\s*(?:닮은|형).*(?:외계|행성)",
        r"화성보다\s*추운.*행성",
        r"earth\s*like.*(?:exoplanet|planet)",
        r"colder\s+than\s+mars",
    ]),
    ("egypt_animal_tomb", [r"이집트.*(?:800구|동물\s*무덤|동물\s*묘지)", r"egypt.*animal.*(?:tomb|cemetery)"]),
    ("mantle_ocean_660km", [r"맨틀.*바다", r"660\s*km.*(?:지하|물|바다)", r"지하\s*660", r"mantle.*ocean"]),
    ("ancient_ice_air", [r"80만\s*년.*공기", r"빙하.*공기", r"ancient.*air.*ice"]),
    ("deep_sea_10000m", [r"심해\s*(?:1만|10000|10,000)\s*미터", r"deep\s*sea\s*(?:10000|10,000)"]),
]


def _semantic_duplicate_key(topic: str) -> str | None:
    """반복 표현을 바꿔도 같은 소재면 같은 키로 묶는다."""
    compact = re.sub(r"\s+", " ", topic.lower())
    try:
        from modules.utils.topic_memory import extract_topic_key

        canonical_key = extract_topic_key(compact)
        if canonical_key:
            return canonical_key
    except Exception:
        pass
    for key, patterns in _SEMANTIC_DUPLICATE_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, compact, re.IGNORECASE):
                return key
    return None


def _extract_day_topics(block: str) -> list[str]:
    """Day 블록에서 주제 헤더만 추출."""
    topics: list[str] = []
    for m in re.finditer(r"^## \d+\.\s+(.+?)(?:\s+\[|$)", block, re.MULTILINE):
        topic = m.group(1).strip()
        if topic:
            topics.append(topic)
    return topics


def _extract_day_topic_candidates(block: str) -> list[str]:
    """중복 검사용 주제 후보: 헤더 + 채널별 실제 생성 앵커."""
    topics = _extract_day_topics(block)
    for m in re.finditer(
        r"^\s*(?:원본주제|Source Topic|Tema Base|Tema Fuente):\s*(.+)$",
        block,
        re.MULTILINE,
    ):
        topic = m.group(1).strip()
        if topic:
            topics.append(topic)
    return topics


def find_day_file_topic_conflicts(file_path: str, day_files_dir: str = DAY_FILES_DIR) -> list[str]:
    """특정 Day 파일이 다른 Day 파일들과 겹치는지 검사한다.

    주제 생성기를 거치지 않고 Day 파일이 수동/다른 경로로 교체되어도
    배포 직전에 전체 볼트를 다시 스캔해 중복을 잡기 위한 안전장치다.
    """
    target_path = os.path.abspath(file_path)
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            target_content = f.read()
    except Exception as e:
        return [f"{os.path.basename(file_path)} 로드 실패: {e}"]

    scan_dir = day_files_dir
    if not os.path.isdir(scan_dir):
        scan_dir = os.path.dirname(target_path)

    target_topics = _extract_day_topic_candidates(target_content)
    existing_exact: dict[str, tuple[str, str]] = {}
    existing_semantic: dict[str, tuple[str, str]] = {}

    try:
        for fname in sorted(os.listdir(scan_dir)):
            if not (fname.startswith("Day") and fname.endswith(".md")):
                continue
            other_path = os.path.abspath(os.path.join(scan_dir, fname))
            if other_path == target_path:
                continue
            try:
                with open(other_path, "r", encoding="utf-8") as f:
                    other_content = f.read()
            except Exception:
                continue
            for topic in _extract_day_topic_candidates(other_content):
                norm = _normalize_topic_for_duplicate(topic)
                if len(norm) >= 4:
                    existing_exact.setdefault(norm, (fname, topic))
                semantic_key = _semantic_duplicate_key(topic)
                if semantic_key:
                    existing_semantic.setdefault(semantic_key, (fname, topic))
    except Exception as e:
        return [f"Day 파일 중복 스캔 실패: {e}"]

    for channel in _get_tracked_channels():
        for topic in _get_uploaded_history_topics(channel, limit=None):
            norm = _normalize_topic_for_duplicate(topic)
            if len(norm) >= 4:
                existing_exact.setdefault(norm, (f"YouTube uploads:{channel}", topic))
            semantic_key = _semantic_duplicate_key(topic)
            if semantic_key:
                existing_semantic.setdefault(semantic_key, (f"YouTube uploads:{channel}", topic))

    errors: list[str] = []
    seen_error_keys: set[str] = set()
    for topic in target_topics:
        norm = _normalize_topic_for_duplicate(topic)
        if len(norm) >= 4 and norm in existing_exact:
            other_file, other_topic = existing_exact[norm]
            key = f"exact::{norm}"
            if key not in seen_error_keys:
                errors.append(
                    f"{os.path.basename(file_path)}: '{topic}' ≈ '{other_topic}' ({other_file})"
                )
                seen_error_keys.add(key)
        semantic_key = _semantic_duplicate_key(topic)
        if semantic_key and semantic_key in existing_semantic:
            other_file, other_topic = existing_semantic[semantic_key]
            key = f"semantic::{semantic_key}"
            if key not in seen_error_keys:
                errors.append(
                    f"{os.path.basename(file_path)}: '{topic}' ≈ '{other_topic}' ({other_file})"
                )
                seen_error_keys.add(key)
    return errors


def _validate_topic_uniqueness(raw_content: str, used_topics: list[str]) -> list[str]:
    """기존 Day 파일 및 같은 생성 결과 안의 토픽 중복을 하드 검증."""
    errors: list[str] = []
    existing: dict[str, str] = {}
    existing_semantic: dict[str, str] = {}
    for topic in used_topics:
        norm = _normalize_topic_for_duplicate(topic)
        if len(norm) >= 4:
            existing.setdefault(norm, topic)
        semantic_key = _semantic_duplicate_key(topic)
        if semantic_key:
            existing_semantic.setdefault(semantic_key, topic)

    generated_seen: dict[str, str] = {}
    generated_semantic_seen: dict[str, str] = {}
    for block in re.split(r"(?=# Day \d+)", raw_content):
        if not block.strip().startswith("# Day"):
            continue
        day_match = re.match(r"# Day (\d+)", block.strip())
        day_label = f"Day {day_match.group(1)}" if day_match else "Day ?"
        for topic in _extract_day_topic_candidates(block):
            norm = _normalize_topic_for_duplicate(topic)
            if len(norm) < 4:
                continue
            if norm in existing:
                errors.append(f"{day_label}: 기존 사용 토픽 중복 — '{topic}' ≈ '{existing[norm]}'")
            if norm in generated_seen:
                errors.append(f"{day_label}: 같은 생성 결과 내 토픽 중복 — '{topic}' ≈ '{generated_seen[norm]}'")
            semantic_key = _semantic_duplicate_key(topic)
            if semantic_key and semantic_key in existing_semantic:
                errors.append(f"{day_label}: 기존 사용 소재 반복 — '{topic}' ≈ '{existing_semantic[semantic_key]}'")
            if semantic_key and semantic_key in generated_semantic_seen:
                errors.append(f"{day_label}: 같은 생성 결과 내 소재 반복 — '{topic}' ≈ '{generated_semantic_seen[semantic_key]}'")
            generated_seen.setdefault(norm, topic)
            if semantic_key:
                generated_semantic_seen.setdefault(semantic_key, topic)
    return errors


_PAYOFF_HARD_FAIL_PATTERNS: list[tuple[str, str]] = [
    (r"^(?!.*(?:나노티라누스|nanotyrannus)).*(?:아니었다|아니야|아니다)(?:\??)?$", "반전만 있고 정체 공개가 없는 제목"),
    (r"^(?!.*(?:나노티라누스|nanotyrannus)).*(?:어린|새끼|아기|젊은)\s*티라노.*(?:아니었다|아니야|아니다).*", "나노티라누스처럼 정답 생물명이 빠진 제목"),
    (r".*(?:뒤집었다|바꿨다|바꾸었다|바꾼다|바뀌었다)$", "무엇을 바꿨는지 없는 제목"),
    (r".*(?:의\s*)?(?:끝|시작|비밀|정체)$", "명사형 떡밥만 있고 payoff가 없는 제목"),
    (r".*왜\s*못\s*자나\??$", "질문은 있지만 이미 소모된 축이고 답의 새 정보가 약한 제목"),
    (r".*1년보다\s*길면\??$", "조건만 있고 결과 payoff가 약한 제목"),
    (r".*시작될까\??$", "무엇이 어떻게 시작되는지 불명확한 제목"),
    (r".*(?:해구\s*밑|바다\s*밑).*(?:바다|물).*(?:내려간|내려간다|감)$", "해양판 섭입/맨틀처럼 메커니즘 앵커가 빠진 제목"),
]

_PAYOFF_GENERIC_ONLY_WORDS = {
    "괴물",
    "무언가",
    "이것",
    "그것",
}

_INTEREST_HARD_FAIL_PATTERNS: list[tuple[str, str]] = [
    (
        r".*(?:해구|섭입|해양판|판구조론|맨틀).*(?:내려간|내려간다|끌고\s*간다|순환|구조).*",
        "지질/해양 현상은 화산·지진·마그마·소멸 같은 결과 충격이 없으면 클릭 동기가 약함",
    ),
]

_INTEREST_ESCAPE_ANCHORS = (
    "화산", "지진", "마그마", "폭발", "삼킨", "삼키", "사라", "녹인", "녹여",
    "압력", "붕괴", "재난", "독", "위험", "생존", "죽", "킬러",
)

_PAYOFF_CONCRETE_ANCHORS = (
    "문어", "고래", "상어", "공룡", "티라노", "악어", "새", "행성", "달", "별",
    "태양", "블랙홀", "금성", "유로파", "목성", "토성", "화산", "번개", "심해",
    "바다", "해구", "화석", "신전", "이집트", "원소", "산소", "방사선", "폭풍",
    "초신성", "유적", "공룡", "생물", "동물",
    "나노티라누스", "데이노수쿠스", "섭입", "해양판", "맨틀",
)


def _has_payoff_anchor(title: str) -> bool:
    compact = re.sub(r"\s+", "", title)
    return any(anchor in compact for anchor in _PAYOFF_CONCRETE_ANCHORS)


def _get_topic_payoff_errors(block: str) -> list[str]:
    """제목만 읽고도 '무엇이 답인지' 감이 안 오는 토픽을 하드 실패로 막는다."""
    errors: list[str] = []
    seen: set[str] = set()
    for topic in _extract_day_topics(block):
        plain = re.sub(r"^[^\w가-힣]+", "", topic).strip()
        if not plain:
            continue

        for pattern, reason in _PAYOFF_HARD_FAIL_PATTERNS:
            if re.fullmatch(pattern, plain):
                key = f"{plain}::{reason}"
                if key not in seen:
                    errors.append(f"토픽 '{plain}' — {reason}")
                    seen.add(key)

        compact = re.sub(r"[^0-9a-z가-힣]+", "", plain.lower())
        if any(word in compact for word in _PAYOFF_GENERIC_ONLY_WORDS) and not _has_payoff_anchor(plain):
            key = f"{plain}::generic_only"
            if key not in seen:
                errors.append(f"토픽 '{plain}' — 구체 대상 없이 추상 단어만 남아 있음")
                seen.add(key)

        for pattern, reason in _INTEREST_HARD_FAIL_PATTERNS:
            if re.fullmatch(pattern, plain) and not any(anchor in compact for anchor in _INTEREST_ESCAPE_ANCHORS):
                key = f"{plain}::interest"
                if key not in seen:
                    errors.append(f"토픽 '{plain}' — {reason}")
                    seen.add(key)

    return errors


def _analyze_hit_patterns() -> str:
    """Top 영상에서 히트 패턴(카테고리+훅 유형) 추출."""
    try:
        from modules.utils.youtube_stats import fetch_all_channels_stats
        from modules.analytics.performance_tracker import _classify_hook, _detect_lang

        all_stats = fetch_all_channels_stats()
        patterns = []
        for ch, data in all_stats.items():
            videos = data.get("videos", [])
            lang = _detect_lang(ch)
            top5 = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)[:5]
            for v in top5:
                title = v.get("title", "")
                views = v.get("views", 0)
                hooks = _classify_hook(title, lang)
                hook_names = [HOOK_NAME_MAP.get(h, h) for h in hooks]
                patterns.append(f"- [{ch}] \"{title}\" ({views:,}뷰) → 훅: {', '.join(hook_names)}")

        if patterns:
            return "Top 영상 히트 패턴:\n" + "\n".join(patterns) + "\n\n이 패턴(카테고리+훅유형)으로 새 토픽을 만들어라. 같은 토픽 재사용 금지."
    except Exception as e:
        print(f"[토픽 생성] 히트 패턴 분석 실패: {e}")
    return "히트 패턴 데이터 없음"


def _get_global_topic_signals_context() -> str:
    """외부 나라별/글로벌 벤치마크 신호를 토픽 생성 컨텍스트로 압축한다."""
    try:
        from modules.utils.global_topic_signals import build_topic_signals_context
        from modules.utils.youtube_benchmark import refresh_global_topic_signals

        limit = int(os.getenv("TOPIC_GLOBAL_SIGNALS_LIMIT", "30"))
        refresh_note = ""
        if os.getenv("TOPIC_BENCHMARK_AUTO_REFRESH", "true").lower() in {"1", "true", "yes", "on"}:
            result = refresh_global_topic_signals(force=False)
            if result.get("skipped"):
                refresh_note = f"외부 벤치마크 수집 상태: {result.get('reason')}"
            else:
                refresh_note = (
                    "외부 벤치마크 수집 상태: "
                    f"scanned={result.get('scanned', 0)}, stored={result.get('stored', 0)}, "
                    f"min_views={result.get('min_views', 0)}"
                )
        context = build_topic_signals_context(limit=limit)
        return f"{refresh_note}\n{context}".strip() if refresh_note else context
    except Exception as e:
        print(f"[토픽 생성] 글로벌 토픽 신호 로드 실패: {e}")
        return "외부 나라별/글로벌 벤치마크 신호 로드 실패 — 100만뷰 외부 모티브 수집 상태 점검 필요."


def _get_last_day_number() -> int:
    """기존 Day 파일에서 마지막 번호 추출."""
    last = 0
    try:
        for fname in os.listdir(DAY_FILES_DIR):
            m = re.match(r"Day (\d+)", fname)
            if m:
                last = max(last, int(m.group(1)))
    except Exception:
        pass
    return last


def _validate_day_block(block: str, expected_day: int) -> list[str]:
    """Day 블록 유효성 검증. 오류 목록 반환."""
    errors = []
    # 토픽 수 확인
    topic_count = len(re.findall(r"## \d+\.", block))
    if topic_count < 3:
        errors.append(f"토픽 {topic_count}개 — 최소 3개 필요")
    if topic_count > 6:
        errors.append(f"토픽 {topic_count}개 — 최대 6개 초과")
    # 공통 토픽에 4채널 섹션 있는지
    common_topics = re.findall(r"(## \d+\..+?\[공통\].*?)(?=## \d+\.|\Z)", block, re.DOTALL)
    for ct in common_topics:
        for ch in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
            if f"### {ch}" not in ct:
                topic_title = re.search(r"## \d+\.\s+(.+?)\[", ct)
                errors.append(f"공통 토픽 '{(topic_title.group(1) if topic_title else '?').strip()}'에 {ch} 섹션 누락")
    # 해시태그 존재
    hashtag_count = block.count("해시태그:") + block.count("Hashtags:")
    if hashtag_count < topic_count:
        errors.append(f"해시태그 {hashtag_count}개 — 토픽 수({topic_count}) 미만")
    fresh_count = len(re.findall(r"^## \d+\..*\[시의성\]", block, re.MULTILINE))
    if fresh_count < 1:
        errors.append("시의성 토픽 0개 — 최소 1개 필요")
    return errors


def _get_channel_title_hard_errors(block: str) -> list[str]:
    """채널별 공개 제목의 치명적 언어/구조 오류를 막는다."""
    errors: list[str] = []
    try:
        from modules.utils.channel_config import get_channel_title_quality_errors
    except Exception:
        return errors

    topic_sections = re.findall(r"(^## \d+\..*?)(?=^## \d+\.|\Z)", block, re.DOTALL | re.MULTILINE)
    for section in topic_sections:
        header_match = re.search(r"^## \d+\.\s+(.+?)(?:\s+\[|$)", section, re.MULTILINE)
        topic_label = (header_match.group(1) if header_match else "?").strip()
        fmt_match = re.search(r"^## \d+\..*?\[포맷:([A-Z_]+)\]", section, re.MULTILINE)
        format_type = fmt_match.group(1) if fmt_match else None
        for channel in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
            channel_match = re.search(
                rf"^### {channel}\s*\([^)]+\)(.*?)(?=^### |\Z)",
                section,
                re.DOTALL | re.MULTILINE,
            )
            if not channel_match:
                continue
            body = channel_match.group(1)
            title_match = re.search(
                r"^\s*(?:제목|Title|Titulo|Título):\s*(.+)$",
                body,
                re.MULTILINE,
            )
            if not title_match:
                errors.append(f"{topic_label} / {channel}: 공개 제목 누락")
                continue
            title = title_match.group(1).strip()
            title_errors = get_channel_title_quality_errors(channel, title, format_type, strict=True)
            errors.extend(f"{topic_label} / {channel}: {err}" for err in title_errors)
    return errors


def _get_channel_metadata_hard_errors(block: str) -> list[str]:
    """채널별 공개 메타데이터 필수 필드와 정확히 5개 태그를 검증한다."""
    errors: list[str] = []
    topic_sections = re.findall(r"(^## \d+\..*?)(?=^## \d+\.|\Z)", block, re.DOTALL | re.MULTILINE)
    banned_tags = {"short", "shorts", "쇼츠"}
    for section in topic_sections:
        header_match = re.search(r"^## \d+\.\s+(.+?)(?:\s+\[|$)", section, re.MULTILINE)
        topic_label = (header_match.group(1) if header_match else "?").strip()
        for channel in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
            channel_match = re.search(
                rf"^### {channel}\s*\([^)]+\)(.*?)(?=^### |\Z)",
                section,
                re.DOTALL | re.MULTILINE,
            )
            if not channel_match:
                continue
            body = channel_match.group(1)
            title_match = re.search(r"^\s*(?:제목|Title|Titulo|Título):\s*(.+)$", body, re.MULTILINE)
            desc_match = re.search(r"^\s*(?:설명(?:\s*\(본문\))?|Description|Descripcion|Descripción):\s*(.+)$", body, re.MULTILINE)
            tags_match = re.search(r"^\s*(?:해시태그|Hashtags):\s*(.+)$", body, re.MULTILINE)
            if not title_match or not title_match.group(1).strip():
                errors.append(f"{topic_label} / {channel}: 공개 제목 누락")
            if not desc_match or not desc_match.group(1).strip():
                errors.append(f"{topic_label} / {channel}: Description 누락")
            if not tags_match or not tags_match.group(1).strip():
                errors.append(f"{topic_label} / {channel}: Hashtags 누락")
                continue
            tags = [t.strip().lstrip("#") for t in re.split(r"[\s,]+", tags_match.group(1).strip()) if t.strip()]
            tags = [t for t in tags if t]
            if len(tags) != 5:
                errors.append(f"{topic_label} / {channel}: 해시태그 {len(tags)}개 — 정확히 5개 필요")
            banned_found = [t for t in tags if t.lower() in banned_tags]
            if banned_found:
                errors.append(f"{topic_label} / {channel}: shorts류 금지 태그 포함 ({', '.join(banned_found)})")
            if desc_match and "#" in desc_match.group(1):
                errors.append(f"{topic_label} / {channel}: Description 줄에는 # 금지 — Hashtags 필드를 사용")
    return errors


def _get_hard_validation_errors(block: str, expected_day: int) -> list[str]:
    """자동 저장을 막아야 하는 구조 오류."""
    errors = []
    topic_count = len(re.findall(r"^## \d+\.", block, re.MULTILINE))
    if topic_count != 3:
        errors.append(f"토픽 {topic_count}개 — 정확히 3개 필요")
    format_tags = re.findall(r"^## \d+\..*?\[포맷:([A-Z_]+)\]", block, re.MULTILINE)
    if len(format_tags) != topic_count:
        errors.append(f"포맷 태그 {len(format_tags)}개 — 토픽 수({topic_count})와 일치해야 함")
    duplicate_formats = sorted({fmt for fmt in format_tags if format_tags.count(fmt) > 1})
    if duplicate_formats:
        errors.append(f"하루 안 같은 포맷 중복 금지 — {', '.join(duplicate_formats)}")
    common_topics = re.findall(r"(## \d+\..+?\[공통\].*?)(?=^## \d+\.|\Z)", block, re.DOTALL | re.MULTILINE)
    for ct in common_topics:
        topic_title = re.search(r"^## \d+\.\s+(.+?)(?:\s+\[|$)", ct, re.MULTILINE)
        title = (topic_title.group(1) if topic_title else "?").strip()
        for ch in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
            if f"### {ch}" not in ct:
                errors.append(f"공통 토픽 '{title}'에 {ch} 섹션 누락")
    divergent_topics = re.findall(r"(## 3\..*?\[채널분화\].*?)(?=^## \d+\.|\Z)", block, re.DOTALL | re.MULTILINE)
    if len(divergent_topics) != 1:
        errors.append(f"채널분화 토픽 {len(divergent_topics)}개 — Topic 3에 정확히 1개 필요")
    for dt in divergent_topics:
        for ch in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
            m = re.search(
                rf"### {ch}\s*\([^)]+\)(.*?)(?=^### |\Z)",
                dt,
                re.DOTALL | re.MULTILINE,
            )
            if not m:
                errors.append(f"채널분화 Topic 3에 {ch} 섹션 누락")
                continue
            section_body = m.group(1)
            if not re.search(r"^\s*(?:원본주제|Source Topic|Tema Base|Tema Fuente):\s*.+$", section_body, re.MULTILINE):
                errors.append(f"채널분화 Topic 3의 {ch} 섹션에 원본주제/Source Topic 누락")
    fresh_count = len(re.findall(r"^## \d+\..*\[시의성\]", block, re.MULTILINE))
    if fresh_count < 1:
        errors.append("시의성 토픽 0개 — 하루 최소 1개 필요")
    if fresh_count > 2:
        errors.append(f"시의성 토픽 {fresh_count}개 — 하루 1~2개만 허용")
    hashtag_lines = re.findall(r"^\s*(?:해시태그|Hashtags):\s*(.+)$", block, re.MULTILINE)
    banned_tags = {"short", "shorts", "쇼츠"}
    for idx, line in enumerate(hashtag_lines, start=1):
        tags = [t.strip().lstrip("#") for t in re.split(r"[\s,]+", line.strip()) if t.strip()]
        tags = [t for t in tags if t]
        if len(tags) != 5:
            errors.append(f"해시태그 라인 {idx}: {len(tags)}개 — 정확히 5개 필요")
        banned_found = [t for t in tags if t.lower() in banned_tags]
        if banned_found:
            errors.append(f"해시태그 라인 {idx}: shorts류 금지 태그 포함 ({', '.join(banned_found)})")
    description_lines = re.findall(r"^\s*(?:설명(?:\s*\(본문\))?|Description|Descripcion|Descripción):\s*(.+)$", block, re.MULTILINE)
    for idx, line in enumerate(description_lines, start=1):
        if "#" in line:
            errors.append(f"설명 라인 {idx}: Day 파일 Description 줄에는 # 금지 — 해시태그 필드를 사용")
    errors.extend(_get_channel_title_hard_errors(block))
    errors.extend(_get_channel_metadata_hard_errors(block))
    errors.extend(_get_topic_payoff_errors(block))
    return errors


def _validate_who_wins_series_tags(raw_content: str) -> list[str]:
    """WHO_WINS is only allowed as a tagged, explicit VS series."""
    errors: list[str] = []
    for match in re.finditer(r"^## \d+\..*$", raw_content, re.MULTILINE):
        line = match.group(0).strip()
        if "[포맷:WHO_WINS]" not in line:
            continue
        if "[시리즈:" not in line:
            errors.append(f"WHO_WINS 시리즈 태그 누락: {line[:120]}")
        if not re.search(r"(?i)\bvs\.?\b", line):
            errors.append(f"WHO_WINS 제목 vs 누락: {line[:120]}")
    return errors


def _extract_required_series_followups(active_series_context: str) -> list[tuple[str, str]]:
    """Parse required next-matchup lines from series_state context."""
    followups: list[tuple[str, str]] = []
    if not active_series_context:
        return followups
    in_required_section = False
    for line in active_series_context.splitlines():
        stripped = line.strip()
        if stripped == "[필수 후속 VS]":
            in_required_section = True
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_required_section = False
            continue
        if not in_required_section:
            continue
        if "다음 에피소드" not in line or "[시리즈:" not in line:
            continue
        series_match = re.search(r"\[시리즈:([^\]]+)\]", line)
        matchup_match = re.search(r"다음 에피소드(?:\s+EP[^:：]*)?[:：]\s*([^.\n]+)", line)
        if not series_match or not matchup_match:
            continue
        series = series_match.group(1).strip()
        matchup = matchup_match.group(1).strip()
        if series and matchup:
            followups.append((series, matchup))
    return followups


def _validate_required_series_followups(raw_content: str, active_series_context: str) -> list[str]:
    """Fail generation if a previously teased VS matchup is omitted."""
    errors: list[str] = []
    normalized_output = _normalize_topic_for_duplicate(raw_content)
    for series, matchup in _extract_required_series_followups(active_series_context):
        normalized_matchup = _normalize_topic_for_duplicate(matchup)
        if f"[시리즈:{series}]" not in raw_content:
            errors.append(f"필수 VS 후속 시리즈 누락: [시리즈:{series}] {matchup}")
            continue
        if normalized_matchup and normalized_matchup not in normalized_output:
            errors.append(f"필수 VS 후속 대결 누락: [시리즈:{series}] {matchup}")
    return errors


def _build_category_allocation_rules(days: int) -> str:
    """요청 일수에 맞는 카테고리 최소 할당 문구를 만든다."""
    if days >= 7:
        return """⚠️ 카테고리 최소 할당 반드시 충족:
  우주/행성 최소 4개, 심해/바다 최소 3개, 공룡/고생물 최소 3개,
  지구/자연 최소 2개, 동물 최소 2개, 역사/문명·물리/화학·기술/공학·인체/심리 합산 최소 4개"""

    total_topics = days * 3
    if days <= 1:
        return f"""요청 기간이 {days}일뿐이므로 7일 기준 카테고리 최소 할당을 적용하지 않는다.
  총 {total_topics}개 안에서 하루 3개 카테고리만 서로 다르게 구성한다."""

    scaled_targets = [
        ("우주/행성", max(1, round(days * 4 / 7))),
        ("심해/바다", max(1, round(days * 3 / 7))),
        ("공룡/고생물", max(1, round(days * 3 / 7))),
        ("지구/자연", max(1, round(days * 2 / 7))),
        ("동물", max(1, round(days * 2 / 7))),
        ("역사/문명·물리/화학·기술/공학·인체/심리 합산", max(1, round(days * 4 / 7))),
    ]
    minimum_total = sum(count for _, count in scaled_targets)
    while minimum_total > total_topics:
        name, count = max(scaled_targets, key=lambda item: item[1])
        if count <= 1:
            break
        idx = next(i for i, item in enumerate(scaled_targets) if item[0] == name)
        scaled_targets[idx] = (name, count - 1)
        minimum_total -= 1

    lines = [
        f"요청 기간이 {days}일이므로 7일 기준 카테고리 최소 할당을 아래처럼 축소 적용한다.",
        f"  총 {total_topics}개 중 최소 합산 {minimum_total}개만 강제하고, 남는 슬롯은 성과 상위 카테고리에 자유 배정한다.",
    ]
    lines.extend(f"  {name}: 최소 {count}개" for name, count in scaled_targets)
    return "\n".join(lines)


def _build_format_slate_rules(days: int) -> str:
    """요청 일수에 맞는 8포맷 운영표 규칙."""
    if days >= 7:
        return """8포맷 주간 운영표를 먼저 만든 뒤 토픽을 선발한다.
  권장 주간 배분: WHO_WINS 2-3개(askanything 전용 연속 VS 시리즈 레인), IF 3-4개, PARADOX 3-4개, FACT 4-5개,
  COUNTDOWN 0개(임시 중단), SCALE 2개, MYSTERY 2-3개, EMOTIONAL_SCI 2개.
  WHO_WINS는 가끔 쓰는 예외 포맷이 아니라 askanything에서 이어 달리는 토너먼트 레인이다.
  모든 WHO_WINS는 [시리즈:...] 태그가 필수이며, 이전 승자 vs 새 도전자 또는 EP1 시작 구도가 보여야 한다.
  같은 시리즈는 2-3일 간격으로 이어 배치하고, 단발/고립 VS는 탈락시킨다.
  wonderdrop/exploratodo/prismtale는 PARADOX/FACT/MYSTERY/IF를 우선한다.
  하루 3개는 서로 다른 포맷이어야 하며, 매일 폭발 후보 1개와 시의성/발견형 1개를 포함한다."""

    if days <= 1:
        return """요청 기간이 1일이면 8개 포맷 중 오늘 가장 강한 3개 슬롯을 먼저 고른다.
  하루 3개는 서로 다른 포맷이어야 한다.
  추천 조합: 시의성 PARADOX/MYSTERY/FACT 중 1개 + IF/SCALE/PARADOX 중 1개 + FACT/MYSTERY/EMOTIONAL_SCI 중 1개.
  진행 중인 VS 시리즈가 있거나 주제 요청이 VS를 요구하면 WHO_WINS 1개를 우선 검토한다.
  WHO_WINS를 쓰는 경우 [시리즈:...] 태그와 다음 상대 예고가 필수이며 단발 VS는 금지한다.
  카테고리 채우기용 토픽은 금지하고, 각 포맷 필수 슬롯을 채울 수 있는 토픽만 선발한다."""

    return f"""요청 기간이 {days}일이면 먼저 {days}일 × 3개 포맷 운영표를 작성한 뒤 토픽을 선발한다.
  매일 3개는 서로 다른 포맷이어야 한다.
  전체 기간 동안 8개 포맷을 최대한 분산하되, 성과 강한 카테고리에 맞춰 IF/PARADOX/FACT/MYSTERY를 우선 배치할 수 있다.
  WHO_WINS는 askanything 전용 연속 VS 시리즈로 최소 1개 배치한다. {days}일이 5일 이상이면 2개를 권장한다.
  모든 WHO_WINS는 [시리즈:...] 태그, A vs B, 승부축, 다음 상대 예고가 있어야 하며 단발 VS는 탈락시킨다.
  각 Day는 시의성/발견형 1개와 폭발 후보 1개를 포함한다.
  토픽이 포맷 필수 슬롯을 못 채우면 카테고리가 좋아도 탈락시킨다."""


def _with_dynamic_topic_limits(system_prompt: str, days: int) -> str:
    """하드코딩된 7일/21개 지시보다 현재 요청 범위를 우선시키는 오버라이드."""
    total_topics = days * 3
    return f"""{system_prompt}

## 현재 요청 오버라이드
- 이번 본선 편성은 정확히 {days}일분, 총 {total_topics}개 토픽 기준으로 판단한다.
- 기존 7일/21개 예시, Approved Slate 21개 지시, 주간 최소 할당보다 이 오버라이드가 우선한다.
- 최종 Day 파일을 작성하는 단계에서는 요청된 날짜 범위 안의 Day 헤더만 정확히 {days}개 출력한다.
- 최종 Day 파일의 각 Day는 정확히 3개 토픽만 포함한다. 2개, 4개, "추가 토픽" 섹션은 실패다.
- 최종 출력에는 Reserve Ideas, 추가 후보, 자기평가, 보충 설명을 섞지 않는다.

{_build_category_allocation_rules(days)}

{_build_format_slate_rules(days)}
"""


def _validate_requested_day_headers(raw_content: str, date_range: list[str]) -> list[str]:
    """요청한 Day 헤더만 정확히 한 번씩 출력됐는지 확인한다."""
    expected: dict[int, str] = {}
    for item in date_range:
        match = re.match(r"Day (\d+) \((\d+-\d+)\)", item)
        if match:
            expected[int(match.group(1))] = match.group(2)

    header_matches = list(re.finditer(r"^# Day (\d+) \((\d+-\d+)\)(.*)$", raw_content, re.MULTILINE))
    seen: dict[int, int] = {}
    errors: list[str] = []
    for match in header_matches:
        day_num = int(match.group(1))
        date_str = match.group(2)
        suffix = match.group(3).strip()
        seen[day_num] = seen.get(day_num, 0) + 1
        if day_num not in expected:
            errors.append(f"요청 범위 밖 Day {day_num} 출력")
        elif expected[day_num] != date_str:
            errors.append(f"Day {day_num}: 날짜 {date_str} 출력 — 요청 날짜 {expected[day_num]} 필요")
        if suffix:
            errors.append(f"Day {day_num}: 헤더 뒤 불필요한 문구 '{suffix}' — 추가 토픽 섹션 금지")

    for day_num, date_str in expected.items():
        if seen.get(day_num, 0) == 0:
            errors.append(f"Day {day_num} ({date_str}) 누락")
        elif seen[day_num] > 1:
            errors.append(f"Day {day_num}: Day 헤더 {seen[day_num]}회 출력 — 정확히 1회 필요")

    expected_count = len(expected)
    if len(header_matches) != expected_count:
        errors.append(f"Day 헤더 {len(header_matches)}개 — 요청한 {expected_count}개만 허용")
    return errors


def _collect_generation_validation(
    raw_content: str,
    used_topics: list[str],
    date_range: list[str],
    active_series_context: str = "",
) -> tuple[list[str], list[str]]:
    """전체 생성 결과의 경고/하드 오류를 모은다."""
    validation_errors: list[str] = []
    hard_errors = _validate_requested_day_headers(raw_content, date_range)
    hard_errors.extend(_validate_topic_uniqueness(raw_content, used_topics))
    hard_errors.extend(_validate_who_wins_series_tags(raw_content))
    hard_errors.extend(_validate_required_series_followups(raw_content, active_series_context))
    day_blocks = re.split(r"(?=# Day \d+)", raw_content)

    for block in day_blocks:
        block = block.strip()
        if not block.startswith("# Day"):
            continue

        header_match = re.match(r"# Day (\d+) \((\d+-\d+)\)", block)
        if not header_match:
            validation_errors.append(f"Day 헤더 파싱 실패: {block[:50]}")
            continue

        day_num = int(header_match.group(1))
        block_errors = _validate_day_block(block, day_num)
        if block_errors:
            validation_errors.extend([f"Day {day_num}: {e}" for e in block_errors])
            print(f"  ⚠️ Day {day_num} 검증 경고: {block_errors}")
        block_hard_errors = _get_hard_validation_errors(block, day_num)
        if block_hard_errors:
            hard_errors.extend([f"Day {day_num}: {e}" for e in block_hard_errors])

    return validation_errors, hard_errors


def _build_required_day_skeleton(date_range: list[str]) -> str:
    """LLM이 Day 헤더를 빠뜨리지 않도록 최종 출력 뼈대를 제공한다."""
    lines: list[str] = []
    for item in date_range:
        lines.extend([
            f"# {item}",
            "## 1. ... [공통] [시의성] [포맷:XXX]",
            "## 2. ... [공통] [포맷:XXX]",
            "## 3. ... [공통] [채널분화] [포맷:XXX]",
            "",
        ])
    return "\n".join(lines).strip()


def _build_semantic_duplicate_brief(used_topics: list[str]) -> str:
    """코드가 막는 반복 소재 클러스터를 프롬프트에도 짧게 노출한다."""
    clusters: dict[str, list[str]] = {}
    for topic in used_topics:
        semantic_key = _semantic_duplicate_key(topic)
        if semantic_key:
            clusters.setdefault(semantic_key, [])
            if len(clusters[semantic_key]) < 3:
                clusters[semantic_key].append(topic)

    if not clusters:
        return "코드 등록 반복 소재 클러스터 없음"

    lines = []
    for key, samples in sorted(clusters.items()):
        lines.append(f"- {key}: " + " / ".join(samples))
    return "\n".join(lines)


def _extract_forbidden_phrases_from_errors(hard_errors: list[str]) -> str:
    """하드게이트가 지목한 실패 소재를 재수리 프롬프트용 금지 목록으로 압축한다."""
    phrases: list[str] = []
    seen: set[str] = set()
    for error in hard_errors:
        for phrase in re.findall(r"'([^']+)'", error):
            phrase = phrase.strip()
            if len(phrase) < 4 or phrase in seen:
                continue
            seen.add(phrase)
            phrases.append(phrase)

    if not phrases:
        return "추가 금지 문구 없음 — 하드게이트 실패 목록을 그대로 따른다."
    return "\n".join(f"- {phrase}" for phrase in phrases[:40])


def _build_harness_focus(round_index: int, total_rounds: int) -> str:
    """회차별 하네스 집중 포인트."""
    focus_map = {
        1: "중복/소재 반복 검수: 기존 Day, 업로드 히스토리, 표현만 바꾼 같은 팩트까지 잡아라.",
        2: "재미없음 검수: 논문 요약형, 교과서형, 클릭 이유 없는 설명형 제목을 모두 교체하라.",
        3: "포맷/카테고리/일일 편성 구조 검수: 하루 3개 균형과 포맷 적합성을 점검하라.",
        4: "제목/헤더 명확성 검수: 구체 주어, payoff, 검색 앵커가 없는 제목을 교체하라.",
        5: "최종 강도 검수: 이번 주 21개 중 약한 축을 버리고 가장 강한 21개만 남겨라.",
    }
    return focus_map.get(round_index, f"{round_index}/{total_rounds}차 종합 검수")


def _run_topic_quality_harness(
    *,
    llm_provider: str,
    model_name: str,
    user_prompt: str,
    raw_content: str,
    used_topics: list[str],
    days: int,
    date_range: list[str],
    log_dir: Path | None,
    rounds: int,
    stage_prefix: str = "Harness",
) -> str:
    """생성 후 중복/재미/구조를 여러 차례 재검수하는 후처리 하네스."""
    content = raw_content.strip()
    if rounds <= 0 or not content:
        return content

    duplicate_brief = _build_semantic_duplicate_brief(used_topics)
    used_topic_sample = "\n".join(f"- {t}" for t in used_topics[:400])
    skeleton = _build_required_day_skeleton(date_range)

    for idx in range(1, rounds + 1):
        focus = _build_harness_focus(idx, rounds)
        previous_content = content
        harness_prompt = f"""{user_prompt}

## 현재 Day 파일 초안
{content}

## 기존 사용 토픽 샘플
{used_topic_sample}

## 코드가 아는 반복 소재 클러스터
{duplicate_brief}

## 이번 하네스 집중 포인트
{focus}

## 하네스 체크리스트
- 기존과 같은 팩트/소재면 제목이 달라도 반려
- 시청자가 "아 그래서?" 할 제목, 논문 요약형 제목, 설명형 제목 반려
- 각 Day는 3개 모두 다른 포맷이어야 한다
- 각 Day는 최소 1개 [시의성]을 유지하되 3개 전부 [시의성]이면 실패
- 헤더는 구체 주어 + payoff + 검색 앵커가 있어야 한다
- WHO_WINS/IF/COUNTDOWN/SCALE/MYSTERY/EMOTIONAL_SCI/FACT/PARADOX 포맷 적합성을 엄격히 본다
- 약한 토픽 1개가 보여도 "그냥 두지 말고" 완전히 더 강한 새 소재로 교체한다
- 특히 아래 타입은 반드시 교체:
  * 수면/기억 정리형 일반 뇌과학
  * 외계행성 생명신호 착시처럼 논문 요약형 우주 제목
  * 공룡 시대 시간차/스테고 vs 티라노처럼 이미 너무 많이 쓴 대표 팩트
  * 해구/맨틀/섭입/기후처럼 결과 장면이 안 떠오르는 교과서형 제목

## 출력 규칙
- 수정된 최종 Day 파일만 다시 출력하라.
- 중간 설명, 체크리스트, 메모, 자기평가 금지.
- 약한 토픽이 없다고 판단되면 원문을 그대로 다시 출력하라.
- 반드시 완전한 Day 파일 형식으로 출력하라.
- 각 토픽마다 아래 요소를 모두 유지하거나 다시 써라:
  * `## N. ... [공통] [포맷:XXX]`
  * `> 근거:`
  * `> 검색 키워드:`
  * `> 채널:`
  * `> 핵심 훅:`
  * `> 훅 패턴:`
  * `### askanything (ko)` + 제목/설명/해시태그
  * `### wonderdrop (en)` + Title/Description/Hashtags
  * `### exploratodo (es-LATAM)` + Titulo/Descripcion/Hashtags
  * `### prismtale (es-US)` + Titulo/Descripcion/Hashtags
- 채널 4개 섹션이나 해시태그 줄 하나라도 빠지면 실패다.
- 헤더만 쓰고 채널 메타를 생략하는 출력은 절대 금지다.
- Day 헤더는 아래 뼈대를 그대로 유지하라.
{skeleton}
"""
        candidate = _call_topic_llm(
            llm_provider=llm_provider,
            model_name=model_name,
            system_prompt=_with_dynamic_topic_limits(TOPIC_HARNESS_REVIEWER_PROMPT, days),
            user_prompt=harness_prompt,
            stage_name=f"{stage_prefix}{idx}",
            temperature=0.2,
            max_tokens=30000,
        ).strip() or previous_content

        candidate_validation_errors, candidate_hard_errors = _collect_generation_validation(
            candidate,
            used_topics,
            date_range,
        )
        structure_break = any(
            ("섹션 누락" in err) or ("해시태그" in err)
            for err in [*candidate_validation_errors, *candidate_hard_errors]
        )
        if structure_break:
            print(f"[토픽 생성] 하네스 {idx}회차 출력 폐기 — 채널 섹션/해시태그 구조 붕괴")
            content = previous_content
        else:
            content = candidate

        if log_dir:
            safe_prefix = re.sub(r"[^0-9A-Za-z_]+", "_", stage_prefix).strip("_") or "Harness"
            _write_text_atomic(log_dir / f"05_{safe_prefix}_{idx}.md", candidate)
            if structure_break:
                _write_text_atomic(log_dir / f"05_{safe_prefix}_{idx}_rejected.txt", "\n".join([
                    "HARNESS OUTPUT REJECTED",
                    *candidate_validation_errors[:120],
                    *candidate_hard_errors[:120],
                ]))
    return content


TOPIC_DISCOVERY_SCOUT_PROMPT = """너는 Discovery Scout다.

역할:
- 최근 발견/관측/발표/신규 화석/신규 행성/신규 해양 발견 후보를 읽고
  실제로 쇼츠 클릭을 부를 만한 '발견형 주제'만 압축한다.
- 최신성이 약하거나 너무 전문 논문 요약 같은 소재는 버린다.

반드시 아래 섹션으로만 답해라:
## Fresh Discovery Candidates
- [category:우주/행성][freshness:high|medium][hook:발견형] 제목 후보 :: 왜 지금 클릭할지

## Avoid
- 버릴 후보 :: 이유

## Search Keywords
- 제목 후보 :: 검증 검색어
"""


TOPIC_SIGNAL_ANALYST_PROMPT = """너는 4채널 쇼츠 시스템의 Signal Analyst다.

역할:
- 최근 성과 데이터, 훅 패턴, 기존 사용 주제를 압축해서 "이번 주 무엇을 세게 밀고 무엇을 버릴지" 전략 메모를 쓴다.
- 안전한 평균형보다 상위 1개 히트를 만들 확률이 높은 방향을 우선한다.
- 교과서형/설명형/익숙한 소재는 가차 없이 감점한다.
- 외부 100만뷰 benchmark의 orchestra expert directives를 채널별 push/test/avoid 지시로 번역한다.

반드시 아래 섹션으로만 답해라:
## Winning Thesis
## Channel Expert Directives
## Push Hard
## Underweight / Avoid
## Hook Directives
## Explosive Bets
## Duplicate Red Flags

규칙:
- 주간 21개 전체를 바라보는 메모를 써라.
- "왜 이 방향이 조회수에 유리한지"를 데이터 언어로 설명하라.
- Channel Expert Directives는 askanything/wonderdrop/exploratodo/prismtale 각각 push/test/avoid를 반드시 포함한다.
- exact market 100만뷰 근거가 적은 채널은 승리 확정이 아니라 candidate/test로 낮춰라.
- 중복 위험, 약한 카테고리, 최근 약세 포맷은 명확히 경고하라.
- 하루 3개 중 [시의성] 발견형 슬롯은 1~2개만 배치하는 전략을 제시하라.
- 표현은 다르지만 같은 팩트인 축도 Duplicate Red Flags에 적어라.
- "정확하지만 재미없는 토픽"은 Underweight / Avoid로 명시적으로 내려라.
"""


TOPIC_WEEKLY_STRATEGIST_PROMPT = """너는 Weekly Strategist다.

역할:
- Signal Analyst 메모를 바탕으로 다음 7일치 주제 초안을 짠다.
- 주제를 뽑기 전에 먼저 8개 포맷 운영표를 짠다.
- 목표는 평균형이 아니라 '이번 주에 최소 2~3개는 크게 터질 수 있는 주간 편성'이다.
- 하루 3개 모두 무난하게 만들지 말고, 매일 1개는 반드시 공격형 토픽으로 뽑아라.

출력 형식:
## Orchestra Decision Log
- [channel:askanything|wonderdrop|exploratodo|prismtale][expert:...] push/test/avoid를 어떻게 편성에 반영했는지

## Format Slate
### Day N (M-D)
- SLOT 1: [format:PARADOX][role:fresh|explosive|stable] 왜 이 포맷이 오늘 필요한지
- SLOT 2: [format:IF][role:fresh|explosive|stable] 왜 이 포맷이 오늘 필요한지
- SLOT 3: [format:FACT][role:fresh|explosive|stable] 왜 이 포맷이 오늘 필요한지

## Day Plan
### Day N (M-D)
- [score:10][category:우주/행성][hook:② 숫자 앵커][format:IF] 토픽명 :: 왜 터질지 1문장

## Reserve Ideas
- 후보 :: 이유

규칙:
- 총 7일 × 3개 = 21개 본선 토픽
- Orchestra Decision Log 없이 Day Plan부터 쓰면 실패다.
- 각 채널 expert directive가 적어도 하나의 공통 토픽 또는 Topic 3 채널분화 소재에 반영되어야 한다.
- Format Slate를 먼저 만들고, Day Plan은 그 슬롯을 채우는 방식으로 작성한다.
- 각 줄은 반드시 score/category/hook/format 태그 포함
- 하루 3개 포맷은 전부 달라야 한다.
- 토픽이 포맷 필수 슬롯을 못 채우면 카테고리가 좋아도 버린다.
- 약한 교과서형 제목, 기존 주제 재탕, 같은 카테고리 과밀 편성 금지
- Topic 1-2는 4채널 공통으로 먹힐 토픽을 우선하되, Topic 3는 채널별 전용 승리 패턴을 따로 태워도 된다.
- 하루 3개 중 [시의성] 발견형 토픽은 1~2개만 허용한다.
"""


TOPIC_QUALITY_CRITIC_PROMPT = """너는 Quality Critic이다.

역할:
- Weekly Strategist 초안을 냉정하게 검수한다.
- 약한 제목, 중복 위험, 카테고리 쏠림, 포맷 과밀, 포맷-토픽 불일치, 너무 안전한 토픽을 잘라낸다.
- "재작성 없이 통과", "수정 후 통과", "반려"를 분리해라.
- 오케스트라 expert directive를 어긴 초안은 성과 카테고리가 좋아도 반려한다.

반드시 아래 섹션으로만 답해라:
## Approved Slate
- [day:Day N][decision:keep|revise] 원안 -> 보정안 (필요 시) :: 이유

## Rejected
- 원안 :: 반려 이유

## Weekly Risks
- 주간 차원의 리스크

## Final Directives
- 최종 편집 지시

규칙:
- Approved Slate는 정확히 21개가 되게 유지하라.
- 각 Day는 서로 다른 포맷 3개여야 한다. 같은 포맷이 하루에 2개 이상이면 반려하라.
- 포맷 운영표가 없는 초안은 반려하라.
- Orchestra Decision Log가 없거나 채널별 market directive를 섞은 초안은 반려하라.
- KO에 KR 근거 없는 일반 잡지식, EN에 약한 casual question/vs, ES에 영어식 직역 제목이 들어오면 교체 우선이다.
- 카테고리만 맞고 포맷 필수 슬롯을 못 채우는 토픽은 반려하라.
- score 8 미만 감각의 토픽은 가능한 한 보정하거나 교체하라.
- "문어 피는 파랗다" 같은 교과서형 표현은 더 공격적으로 바꾸라고 지시하라.
- "잠든 뇌는 기억을 정리한다" 같은 일반 뇌과학 설명형,
  "생명 신호는 착시일 수 있다" 같은 논문 요약형,
  "스테고와 티라노는 8천만 년 차이" 같은 너무 익숙한 대표 팩트는
  보정보다 교체 우선으로 판단하라.
"""


TOPIC_HARNESS_REVIEWER_PROMPT = """너는 Topic Harness Reviewer다.

역할:
- 이미 작성된 Day 파일 초안을 읽고, 중복/재미없음/구조 약점을 후처리로 걷어낸다.
- 프롬프트 문장만 믿지 말고 결과물을 냉정하게 갈아엎는다.
- "표현만 다른 같은 소재", "논문 요약형 제목", "교과서형 헤더", "포맷만 붙은 약한 주제"를 특히 싫어한다.

핵심 원칙:
- 정확하지만 재미없으면 반려
- 제목이 다르더라도 같은 팩트면 반려
- 오늘/이번 주 편성 안에서 상대적으로 약한 토픽도 반려
- 더 강한 대체안이 있으면 바로 교체

출력 규칙:
- 수정된 Day 파일 최종본만 출력
- 중간 설명, 사과, 검수 메모, bullet, 체크 결과 금지
"""


def _build_topic_orchestra_governance(days: int) -> str:
    """Shared governance rules that force expert outputs into the final topic plan."""
    total_topics = days * 3
    return f"""총괄 오케스트라 실행 방식:
- 총괄 오케스트라는 전문가 의견을 요약하지 않고 최종 선발권을 가진다.
- Signal Analyst: 외부 100만뷰 benchmark를 채널별 push/test/avoid directive로 변환한다.
- Channel Strategist: askanything/wonderdrop/exploratodo/prismtale 각각 market evidence와 내부 성과를 비교한다.
- Format Architect: 먼저 {days}일 × 3개 포맷 슬롯을 잠그고, 토픽은 슬롯을 통과한 후보만 받는다.
- Script/Hook Expert: 각 언어권의 제목 리듬, 첫 컷 훅, 금지 표현을 검수한다.
- Visual Director: Cut 1이 한눈에 읽히는 피사체/장면/스케일인지 판정한다.
- Quality Gate: market directive 위반, 중복 팩트, 교과서형 소재, 약한 제목을 반려한다.
- Final Editor: 최종 Day 파일 {days}개, 총 {total_topics}개 토픽만 남기고 메모를 제거한다.

오케스트라 하드 게이트:
- exact market 100만뷰 evidence가 있는 방향은 일반 카테고리 균형보다 우선한다.
- exact market evidence가 3개 미만이면 "승리 확정"이 아니라 candidate/test로 낮추고, 해당 채널의 공통 슬롯 남발을 금지한다.
- Topic 1-2 공통 토픽도 각 채널 market에서 납득 가능한 소재여야 한다. 특정 market에서 약한 소재는 Topic 3 채널분화로 분리한다.
- askanything: KR 근거가 좁으므로 우주/스케일/상식 반전 중심. KR 근거 없는 일반 인체/동물/역사는 테스트 슬롯만.
- wonderdrop: US 100만뷰 표본이 가장 두꺼우므로 FACT/IF 중심의 concrete declarative 제목으로 강화. casual question/vs/WHO_WINS 남발 금지.
- exploratodo: MX/LATAM Spanish에서 먹힌 우주 IF, 공룡/동물/심해 FACT를 빠르고 구체적인 스페인어로 재작성.
- prismtale: US Hispanic Spanish에서 먹힌 동물/공룡/인체/우주 FACT/IF를 dark concrete mystery로 변환. 빈 secreto/misterio 금지.
"""


def _build_topic_generation_request(
    start_date: datetime,
    days: int,
    performance: str,
    used_topics: list[str],
    hit_patterns: str,
    last_day: int,
    fresh_discovery_context: str = "",
    global_topic_signals_context: str = "",
    active_series_context: str = "",
) -> tuple[str, list[str]]:
    """주간 토픽 생성 공통 요청문과 날짜 범위를 만든다."""
    date_range = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        date_str = f"{d.month}-{d.day}"
        day_num = _find_existing_day_number_for_date(date_str) or (last_day + 1 + i)
        date_range.append(f"Day {day_num} ({d.month}-{d.day})")

    user_prompt = f"""다음 {days}일분 토픽을 생성해줘.

## 날짜 범위
{chr(10).join(date_range)}

## 성과 분석 데이터
{performance}

## 히트 패턴 (이 패턴으로 새 토픽 복제)
{hit_patterns}

## 외부 나라별/글로벌 벤치마크 신호
{global_topic_signals_context or "외부 벤치마크 신호 없음 — 내부 4채널 성과를 우선"}

{active_series_context or "## VS 시리즈 연속성 상태\n[필수 후속 VS]\n- 현재 업로드가 예고한 필수 후속 VS 없음."}

## 오케스트라 전문가 총괄 실행 규칙
{_build_topic_orchestra_governance(days)}

## 최신성 후보 / 발견형 후보
{fresh_discovery_context or "실시간 발견형 후보 없음 — 최근 발견형 패턴을 모사하되 가짜 최신 뉴스는 금지"}

## 이미 사용된 토픽 (중복 금지 — 제목이 다르더라도 같은 팩트면 중복)
{chr(10).join(f'- {t}' for t in used_topics)}

## 코드 하드게이트가 막는 반복 소재 클러스터
{_build_semantic_duplicate_brief(used_topics)}

## 8포맷 운영표 우선 규칙
{_build_format_slate_rules(days)}

## 최종 출력 필수 뼈대
아래 Day 헤더와 토픽 3개 구조를 정확히 채워라. Day 헤더 누락/추가/접미사 금지.
{_build_required_day_skeleton(date_range)}

## 요청
- 하루 3개 토픽 × {days}일 = {3 * days}개
- 각 Day는 `공통 2개 + 채널분화 1개`를 기본값으로 한다. 채널분화 토픽은 `[공통] [채널분화]` 태그를 사용한다.
- 요청된 날짜 범위에 있는 Day만 출력. "추가 토픽", 보충 Day, Reserve 후보를 최종 출력에 섞으면 실패
- 각 Day는 정확히 3개 토픽만 포함. 하루 2개/4개 이상이면 저장 실패
- 모든 주제에 [포맷:XXX] 태그 필수
- 포맷 운영표를 먼저 정하고, 각 슬롯에 맞는 토픽을 선발
- 하루 3토픽은 서로 다른 포맷 사용. 같은 포맷이 하루에 2개 이상이면 저장 실패
- 토픽이 포맷 필수 슬롯을 못 채우면 카테고리/성과가 좋아도 탈락
- WHO_WINS는 askanything 전용 연속 VS 시리즈 레인이다. WHO_WINS를 출력하면 [시리즈:...] 태그, A vs B, 승부축, 다음 상대 예고 가능성이 모두 있어야 한다.
- VS 시리즈 연속성 상태에 [필수 후속 VS]가 있으면 그것은 선택 후보가 아니라 반드시 포함해야 하는 다음 에피소드다.
- VS 시리즈 연속성 상태의 [성과 보류 VS]와 [성과 확인 대기 VS]는 강제 편성하지 않는다. 조회수 게이트를 통과한 것만 연속 편성한다.
- 외부 벤치마크 신호는 channel benchmark market 섹션을 우선한다. askanything=KR, wonderdrop=US, exploratodo=MX/LATAM, prismtale=US_HISPANIC 기준을 섞지 마라.
- 오케스트라 expert directives의 push/test/avoid 판정은 최종 선발 게이트다. 단순 참고로 처리하면 실패
- Signal Analyst → Weekly Strategist → Quality Critic → Final Editor 순서로 전문가 지시가 누락 없이 반영되어야 한다.
- 외부 벤치마크 신호는 canonical topic/fingerprint만 참고하고 원문 제목/전개를 복사하지 말 것
- 같은 canonical topic이라도 나라별 market에서 안 뜬 소재면 해당 채널의 Topic 3 후보로 낮춰라.
- 외부 신호와 이미 사용된 토픽이 같은 팩트면 중복으로 보고 탈락
- WHO_WINS: 자연스러운 대결 구도 주제만, 억지 비교 금지
- EMOTIONAL_SCI: 인체/심리/감성 주제만 (우주/자연 팩트에 강제 적용 금지)
- COUNTDOWN: 현재 운영에서 임시 중단. TOP N/순위형 아이디어는 FACT/SCALE/PARADOX로 재구성한다.
- PARADOX: 통념 뒤집기 주제만, 일반 팩트에 억지 적용 금지
- 히트 패턴 복제 토픽: 주당 3-4개
- {_build_category_allocation_rules(days)}
- 출처에 논문명 지어내지 말 것 — 검색 키워드로 검증 가능하게
- 카테고리 분산: 하루 3토픽 내 겹침 금지, 주간 최소 6개 카테고리
- 하루 3토픽 중 1~2개만 [시의성] 태그를 붙인 발견형/관측형/신규 발표형 토픽
"""
    return user_prompt, date_range


def _sanitize_log_name(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", name).strip("_") or "log"


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    _write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _create_topic_log_dir(start_date: datetime, days: int) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = Path(TOPIC_LOG_DIR) / f"{stamp}_{start_date.strftime('%m%d')}_{days}d"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _get_fresh_discovery_context() -> str:
    """실시간 발견형 후보를 검색해 최신성 슬롯 재료를 만든다."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "TAVILY_API_KEY 없음 — 실시간 검색 없이 기존 발견형 패턴으로 [시의성] 슬롯을 구성"

    try:
        from tavily import TavilyClient
    except ImportError:
        return "tavily 패키지 없음 — 실시간 검색 없이 기존 발견형 패턴으로 [시의성] 슬롯을 구성"

    today = datetime.now().strftime("%Y-%m")
    queries = [
        f"{today} newly discovered earth-like planet exoplanet nasa",
        f"{today} new dinosaur fossil discovered paleontology",
        f"{today} deep sea discovery new species ocean scientists",
        f"{today} archaeology ancient discovery scientists found",
    ]

    lines = []
    try:
        client = TavilyClient(api_key=api_key)
        for query in queries:
            response = client.search(
                query=query,
                search_depth="advanced",
                include_answer=True,
                max_results=3,
                timeout=20,
            )
            if response.get("answer"):
                lines.append(f"- Query: {query}\n  Summary: {response['answer']}")
            for result in response.get("results", [])[:3]:
                title = (result.get("title") or "").strip()
                url = (result.get("url") or "").strip()
                content = (result.get("content") or "").replace("\n", " ").strip()[:220]
                if title:
                    lines.append(f"- Query: {query}\n  Title: {title}\n  URL: {url}\n  Snippet: {content}")
    except Exception as e:
        return f"실시간 발견형 검색 실패: {e}"

    if not lines:
        return "실시간 발견형 후보 없음 — 최근 발견형 패턴을 사용하되 가짜 최신성 금지"
    return "\n".join(lines[:20])


def _call_topic_llm(
    *,
    llm_provider: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    stage_name: str,
    temperature: float = 0.4,
    max_tokens: int = 12000,
) -> str:
    """토픽 기획용 단일 LLM 호출."""
    print(f"[토픽 오케스트라] {stage_name} 호출 중... ({llm_provider}/{model_name})")

    def _is_quota_error(error: Exception) -> bool:
        text = str(error)
        return getattr(error, "status_code", None) == 429 or "RESOURCE_EXHAUSTED" in text or "429 " in text

    def _fallback_model() -> str | None:
        if llm_provider == "openai":
            return os.getenv(f"TOPIC_ORCHESTRA_{stage_name.upper()}_MODEL") or os.getenv("TOPIC_OPENAI_FALLBACK_MODEL")
        return (
            os.getenv(f"TOPIC_ORCHESTRA_{stage_name.upper()}_MODEL")
            or os.getenv("TOPIC_GEMINI_FALLBACK_MODEL")
            or os.getenv("TOPIC_ORCHESTRA_FALLBACK_MODEL")
            or "gemini-2.5-flash"
        )

    def _call(model: str) -> str:
        if llm_provider == "openai":
            import openai
            from modules.utils.provider_policy import get_openai_api_key, require_openai_api_enabled

            require_openai_api_enabled("OpenAI 토픽 생성")
            api_key = get_openai_api_key()
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY 미설정")
            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_completion_tokens=max_tokens,
                timeout=300,
            )
            return (resp.choices[0].message.content or "").strip()

        from google.genai import types
        from modules.utils.gemini_client import create_gemini_client
        from modules.utils.keys import get_google_key

        api_key = get_google_key(None, service="gemini")
        client = create_gemini_client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=f"{system_prompt}\n\n{user_prompt}",
            config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "http_options": types.HttpOptions(timeout=120_000),
            },
        )
        return (response.text or "").strip()

    try:
        return _call(model_name)
    except Exception as e:
        fallback = _fallback_model()
        if not fallback or fallback == model_name or not _is_quota_error(e):
            raise
        print(f"[토픽 오케스트라] {stage_name} 429 감지 → fallback 재시도 ({llm_provider}/{fallback})")
        return _call(fallback)


def _run_topic_single_pass(
    *,
    llm_provider: str,
    model_name: str,
    user_prompt: str,
    days: int,
) -> str:
    """기존 단일 패스 토픽 생성."""
    return _call_topic_llm(
        llm_provider=llm_provider,
        model_name=model_name,
        system_prompt=_with_dynamic_topic_limits(TOPIC_EXPERT_PROMPT, days),
        user_prompt=user_prompt,
        stage_name="SinglePass",
        temperature=0.5,
        max_tokens=30000,
    )


def _run_topic_orchestra(
    *,
    start_date: datetime,
    days: int,
    llm_provider: str,
    model_name: str,
    performance: str,
    used_topics: list[str],
    hit_patterns: str,
    last_day: int,
    user_prompt: str,
    date_range: list[str],
    fresh_discovery_context: str,
    global_topic_signals_context: str,
    strict: bool = False,
) -> dict[str, Any]:
    """분석가 → 전략가 → 비평가 → 편집자 단계로 주간 토픽을 생성한다."""
    log_dir = _create_topic_log_dir(start_date, days)
    meta = {
        "started_at": datetime.now().isoformat(),
        "start_date": start_date.strftime("%Y-%m-%d"),
        "days": days,
        "llm_provider": llm_provider,
        "model_name": model_name,
        "used_topic_count": len(used_topics),
        "top_used_topics_sample": used_topics[:20],
        "has_fresh_discovery_context": bool(fresh_discovery_context.strip()),
        "has_global_topic_signals_context": bool(global_topic_signals_context.strip()),
    }
    _write_json_atomic(log_dir / "00_run_meta.json", meta)
    _write_text_atomic(log_dir / "00_request.md", user_prompt)
    _write_text_atomic(log_dir / "00_fresh_discovery_input.md", fresh_discovery_context)
    _write_text_atomic(log_dir / "00_global_topic_signals.md", global_topic_signals_context)

    try:
        discovery_scout_input = f"""## 최근 발견형 후보 원문
{fresh_discovery_context}

## 지시
- 실제로 클릭 욕구가 생기는 발견형 후보만 남겨라.
- "새로 발견된 지구 같은 행성", "새 화석/신종/관측", "심해에서 새로 확인된 사실" 같은 류를 우선하라.
"""
        discovery_scout_output = _call_topic_llm(
            llm_provider=llm_provider,
            model_name=model_name,
            system_prompt=_with_dynamic_topic_limits(TOPIC_DISCOVERY_SCOUT_PROMPT, days),
            user_prompt=discovery_scout_input,
            stage_name="DiscoveryScout",
            temperature=0.25,
            max_tokens=3500,
        )
        _write_text_atomic(log_dir / "01_discovery_scout.md", discovery_scout_output)

        analyst_input = f"""## 날짜 범위
{chr(10).join(date_range)}

## 최근 성과 데이터
{performance}

## 히트 패턴
{hit_patterns}

## 외부 나라별/글로벌 벤치마크 신호
{global_topic_signals_context}

## 기존 사용 주제
{chr(10).join(f"- {t}" for t in used_topics[:300])}

## Fresh Discovery Scout
{discovery_scout_output}
"""
        analyst_output = _call_topic_llm(
            llm_provider=llm_provider,
            model_name=model_name,
            system_prompt=_with_dynamic_topic_limits(TOPIC_SIGNAL_ANALYST_PROMPT, days),
            user_prompt=analyst_input,
            stage_name="SignalAnalyst",
            temperature=0.3,
            max_tokens=5000,
        )
        _write_text_atomic(log_dir / "02_signal_analyst.md", analyst_output)

        strategist_input = f"""{user_prompt}

## Fresh Discovery Scout
{discovery_scout_output}

## Signal Analyst Memo
{analyst_output}

## 추가 지시
- 이번 주는 80~90점이 아니라 120% 공격성으로 편성하라.
- 매일 1개는 "이건 궁금해서라도 누른다"급 토픽을 배치하라.
- reserve 후보도 함께 만들어서 critic가 갈아끼울 수 있게 하라.
- 최신성 슬롯은 가능하면 새 발견/새 관측/새 화석/새 행성류로 채워라.
- 단, 본선 Day Plan은 정확히 {days}일 × 3개 = {days * 3}개만 작성하라.
"""
        strategist_output = _call_topic_llm(
            llm_provider=llm_provider,
            model_name=model_name,
            system_prompt=_with_dynamic_topic_limits(TOPIC_WEEKLY_STRATEGIST_PROMPT, days),
            user_prompt=strategist_input,
            stage_name="WeeklyStrategist",
            temperature=0.6,
            max_tokens=9000,
        )
        _write_text_atomic(log_dir / "03_weekly_strategist.md", strategist_output)

        critic_input = f"""{user_prompt}

## Fresh Discovery Scout
{discovery_scout_output}

## Signal Analyst Memo
{analyst_output}

## Weekly Strategist Draft
{strategist_output}

## 검수 포인트
- 기존 주제와 같은 팩트면 제목이 달라도 반려
- 교과서형/설명형 표현은 더 공격적으로 바꾸거나 반려
- 카테고리 최소 할당/일일 포맷 다양성/주간 공격성 유지
- Approved Slate는 정확히 {days * 3}개만 유지
"""
        critic_output = _call_topic_llm(
            llm_provider=llm_provider,
            model_name=model_name,
            system_prompt=_with_dynamic_topic_limits(TOPIC_QUALITY_CRITIC_PROMPT, days),
            user_prompt=critic_input,
            stage_name="QualityCritic",
            temperature=0.35,
            max_tokens=7000,
        )
        _write_text_atomic(log_dir / "04_quality_critic.md", critic_output)

        final_editor_prompt = f"""{user_prompt}

## Fresh Discovery Scout
{discovery_scout_output}

## Signal Analyst Memo
{analyst_output}

## Weekly Strategist Draft
{strategist_output}

## Quality Critic Verdict
{critic_output}

## 최종 편집 지시
- Approved Slate와 Final Directives를 최우선으로 반영하라.
- 이번 주 편성은 "안정형 요약"보다 "멈추게 만드는 제목"을 우선한다.
- Day 파일 최종 출력만 작성하라. 중간 설명, 자기평가, 메모 금지.
- 정확히 {days}개 Day, 총 {days * 3}개 토픽만 출력한다. "추가 토픽" 금지.
- Day 번호는 아래 뼈대의 실제 번호를 그대로 유지하라. Day 1~{days}로 다시 시작하면 실패다.
- 허용되는 Day 헤더는 아래 뼈대에 나온 값만이다. 예: {", ".join(date_range[:3])}{' ...' if len(date_range) > 3 else ''}.
"""
        final_output = _call_topic_llm(
            llm_provider=llm_provider,
            model_name=model_name,
            system_prompt=_with_dynamic_topic_limits(TOPIC_EXPERT_PROMPT, days),
            user_prompt=final_editor_prompt,
            stage_name="FinalEditor",
            temperature=0.45,
            max_tokens=30000,
        )
        _write_text_atomic(log_dir / "05_final_weekly.md", final_output)
    except Exception as e:
        error_text = f"토픽 오케스트라 실패: {e}"
        _write_text_atomic(log_dir / "99_error.txt", error_text)
        if strict:
            raise
        return {
            "success": False,
            "error": error_text,
            "log_dir": str(log_dir),
        }

    return {
        "success": True,
        "raw_content": final_output,
        "log_dir": str(log_dir),
        "stages": {
            "discovery_scout": str(log_dir / "01_discovery_scout.md"),
            "signal_analyst": str(log_dir / "02_signal_analyst.md"),
            "weekly_strategist": str(log_dir / "03_weekly_strategist.md"),
            "quality_critic": str(log_dir / "04_quality_critic.md"),
            "final_weekly": str(log_dir / "05_final_weekly.md"),
        },
    }


TOPIC_EXPERT_PROMPT = """너는 YouTube Shorts 4채널 시스템의 주간 토픽 기획 전문가다.

## 너의 역할
성과 데이터를 분석하고, 다음 주 7일분 토픽(하루 3개 × 7일 = 21개)을 기획한다.
먼저 8개 콘텐츠 포맷 운영표를 짜고, 그 포맷 슬롯에 맞는 토픽을 선발한다.
토픽을 먼저 뽑은 뒤 포맷을 억지로 붙이는 방식은 실패다.

## 오케스트라 총괄 구조
- 너는 단일 기획자가 아니라 총괄 오케스트라다. 각 전문가의 판단을 합쳐 최종 승인한다.
- 성과 분석가: 외부 100만뷰 benchmark와 내부 채널 성과를 분리해 push/test/avoid를 낸다.
- 채널 전략가: KO/EN/ES-LATAM/ES-US Hispanic market별로 소재와 제목 리듬을 분리한다.
- 포맷 설계자: Format Slate를 먼저 잠그고 토픽은 그 슬롯에만 넣는다.
- 스크립트/훅 전문가: 첫 줄이 언어권별로 즉시 클릭되는지 검수한다.
- 비주얼 디렉터: Cut 1이 한 장면으로 읽히는지, 피사체가 구체적인지 검수한다.
- 품질 게이트: market directive 위반, 중복 팩트, 교과서형 소재, 약한 제목을 반려한다.
- 최종 편집자: 승인된 토픽만 Day 파일 형식으로 남긴다.
- expert directive는 참고자료가 아니라 선발 게이트다. 충돌 시 exact market 100만뷰 evidence를 일반 균형보다 우선한다.

## 채널 정보
- askanything (KO): 한국어, 빠른 반말, 호기심 자극
- wonderdrop (EN): 영어, confident authority 다큐, 시네마틱
- exploratodo (ES-LATAM): 스페인어 LATAM, 에너지 넘침, 빠른 리듬
- prismtale (ES-US): 스페인어 US, 다크 미스터리, 시네마틱

## 채널별 현재 승리 패턴
- askanything: 질문형 + 구체 피사체 + 비정상 상황이 강하다. 추상 역사/비밀 표현은 약해진다.
- wonderdrop: direct declarative + concrete noun이 강하다. `What If`, `Who Wins`, `vs`는 최근 약하다.
- exploratodo: negation/reveal (`no era`, `nunca existió`)와 직접 질문이 강하다. bare comparison은 약하다.
- prismtale: dark mystery 자체보다 `장소/물체/수치`가 박힌 concrete mystery가 강하다. vague `secreto/misterio`는 약하다.

## 토픽 배분 규칙 (채널당 3개/일)
1. 하루 3개 토픽 유지. 기본 구조는 `2개 공통 + 1개 채널분화 슬롯`이다.
   - Topic 1, 2: 공통 토픽
   - Topic 3: `[공통] [채널분화]` 태그를 유지하되, 채널별 `원본주제/Source Topic/Tema Base`를 따로 써서 실제 생성 앵커를 분리한다.
   - 즉, Day 헤더는 3개만 유지하지만 Topic 3의 채널별 원본소재는 서로 달라도 된다.
2. 포맷 운영표를 먼저 작성:
   - 하루 3개는 서로 다른 포맷
   - 매일 1개는 폭발 후보 포맷
   - 매일 1개는 시의성/발견형에 적합한 포맷
   - 포맷 필수 슬롯을 못 채우는 토픽은 카테고리가 좋아도 탈락
3. 카테고리 배분 (주간 기준):
   - 성과 상위 카테고리: 50%
   - 히트 패턴 복제: 20%
   - 새 카테고리 테스트: 15%
   - 채널 강점 카테고리: 15%

## ★ 8포맷 운영표 우선 원칙
- 최종 토픽을 쓰기 전에 내부적으로 `Format Slate`를 먼저 만든다.
- 포맷은 메뉴판이고, 토픽은 그 슬롯을 통과한 후보만 선발한다.
- 하루 안에서 같은 포맷을 2개 이상 쓰면 실패다.
- 성과 좋은 카테고리라도 포맷성이 약하면 버린다.
- 예: 심해/바다가 강세여도 `해구 밑으로 바다가 내려간다`처럼 장면/결과/반전이 약한 토픽은 버린다.
- 예: PARADOX 슬롯이면 통념과 뒤집는 정답이 모두 있어야 한다.
- 예: IF 슬롯이면 가정 조건과 결과/payoff가 모두 있어야 한다.
- 예: WHO_WINS 슬롯이면 A vs B와 승부축이 모두 있어야 한다.
- 예: COUNTDOWN 슬롯은 현재 비활성이다. TOP N 아이디어가 보이면 단일 reveal/payoff 제목으로 다시 쓴다.
- 예: SCALE 슬롯이면 비교 기준과 수치/규모 앵커가 있어야 한다.
- 예: MYSTERY 슬롯이면 미스터리 대상과 아직 모르는 지점이 있어야 한다.
- 예: EMOTIONAL_SCI 슬롯이면 사람/몸/감정 주어가 있어야 한다.
- 예: FACT 슬롯이면 구체 주어와 놀라운 핵심 사실이 모두 있어야 한다.

## 하루별 바이럴 강도 규칙
매일 3개 토픽 중 반드시 1개는 "폭발 후보 토픽"이어야 한다.

폭발 후보 토픽의 기준:
- 평균 조회를 노리는 안정형 토픽이 아니라, 상위 1개 히트를 노리는 공격형 토픽이어야 한다.
- 제목만 봐도 즉시 클릭 욕구가 생겨야 한다.
- 설명형보다 감각형, 충격형, 생존형, 극한형, 반전형을 우선한다.
- 아래 6개 축 중 최소 1개를 반드시 포함:
  1. 생존 위협
  2. 극한 환경
  3. 우주적 규모
  4. 인체/몸의 충격적 사실
  5. 공포/불길함
  6. 상식 뒤집기
- "흥미롭다" 수준이면 실패다. "이건 꼭 봐야 한다" 수준이어야 한다.
- 하루 3개 전부를 안전한 설명형 토픽으로 구성하면 실패다.

폭발 후보 토픽의 예시 방향:
- 지구 자기장이 사라지면?
- 블랙홀에 손만 넣으면?
- 심해 1만 미터에서 인간은?
- 몸속에 평생 남는 세포
- 우주에서 가장 뜨거운 행성
- 죽기 직전 젊어지는 생물

실패 예시:
- 교과서형 정보 설명 3개
- 클릭 이유가 약한 요약형 제목 3개
- 너무 예측 가능하고 안전한 토픽만 3개

## ★ 흥미성 veto 규칙
- 성과 좋은 카테고리 배분은 "카테고리 채우기"가 아니다. 우주/심해/공룡/지구라도 클릭 장면이 없으면 버려라.
- 모든 토픽은 제목만 보고 아래 질문에 답해야 한다: "그래서 시청자가 왜 지금 누르지?"
- 지질/해양/우주 교과서형 현상은 반드시 결과 충격을 붙여야 한다. 화산, 지진, 마그마, 생존, 소멸, 독성, 압력, 충돌, 폭발, 새 포식자처럼 장면이 떠오르는 결과가 있어야 한다.
- 나쁜 토픽: `해구 밑으로 바다가 내려간다` — 교과서 구조 설명이라 클릭 욕구가 약함
- 보정 가능: `바닷물이 맨틀로 내려가 화산을 깨운다` — 결과 장면이 있음
- 나쁜 토픽: `해양판 섭입이 바닷물을 맨틀로 끌고 간다` — 정확하지만 여전히 학습자료 같음
- 좋은 토픽: `바닷물이 맨틀로 내려가 화산 폭발을 바꾼다`
- 나쁜 토픽: `초신성이 뿌린 철로 행성이 생긴다` — 교과서형이면 약함
- 좋은 토픽: `네 몸의 철은 죽은 별에서 왔다`
- "정확하지만 재미없는 토픽"은 실패다. 정확성은 통과 조건이고, 클릭 욕구는 선발 조건이다.
- 생성 뒤에는 별도 하네스가 5회 돌며 `중복/재미없음/구조 약함`을 다시 검수한다.
- 하네스에서 잘릴 법한 토픽은 처음부터 넣지 마라.
- 특히 `수면이 기억을 정리한다`, `외계행성 생명신호 착시`, `공룡 시간차`, `해구/맨틀 설명형`, `기후 일반론` 같은 교과서형 축은 더 강한 장면/실체가 없으면 탈락시켜라.

## 카테고리 목록 + 주간 최소 할당 (성과 데이터 기반)
★ 성과 검증됨 (우선 배정 — 주간 최소 수량 반드시 충족):
  우주/행성: 최소 4개 (KO 최강, 전 채널 안정 — 가장 중요한 카테고리)
  심해/바다: 최소 3개 (전 채널 1-2위)
  공룡/고생물: 최소 3개 (ES 강세)
  지구/자연: 최소 2개 (안정적 중위)
  동물: 최소 2개 (KO 강세)
☆ 신규 테스트 (나머지 할당):
  역사/문명, 물리/화학, 기술/공학, 인체/심리: 합산 최소 4개

## 카테고리 분산 규칙
- 주간 21토픽 중 위 최소 할당 반드시 충족 (우주4+심해3+공룡3+지구2+동물2+기타4=18, 나머지 3개 자유)
- 같은 카테고리 연속 2일 금지
- 하루 3개 토픽 내 카테고리 겹침 금지
- 인체/심리는 EN에서 약세 — EMOTIONAL_SCI 포맷으로만 사용
- ⚠️ 우주/행성 토픽이 주간 4개 미만이면 HARD FAIL

## 카테고리 유연성 규칙
주간 최소 할당은 반드시 지키되, 최근 성과 데이터에서 압도적으로 우세한 카테고리가 있으면 추가 배정을 허용한다.

허용 규칙:
- 최소 할당 충족 후 남는 슬롯은 최근 평균 조회 상위 카테고리에 우선 배정한다.
- 최근 7일 성과가 다른 카테고리 대비 1.5배 이상인 카테고리는 주간 추가 배정 우선권을 가진다.
- "카테고리 균형"보다 "성과 반영"을 우선하라.
- 단, 하루 3개 토픽 안에서는 같은 카테고리 중복을 금지한다.
- 최근 성과 상위 카테고리는 주간 기준 최소 할당보다 1~3개 더 많아질 수 있다.

## ★ 히트 패턴 복제 규칙
성과 데이터의 Top 5 영상 패턴(카테고리 + 훅 유형)을 복제한다.
- 같은 토픽 재사용 ❌ 절대 금지
- 같은 카테고리 + 같은 훅 패턴 + 다른 소재 ✅
- 제목이 다르더라도 같은 팩트를 다루면 중복 ❌
예시:
  Top: "하루가 1년보다 긴 행성" (20K views) = 우주/천문 + ② 숫자 앵커
  복제: "비가 다이아몬드인 행성" = 같은 카테고리 + 같은 훅 유형 + 다른 팩트 ✅
  금지: "하루가 1년보다 긴 행성" 다시 사용 ❌

## 훅 패턴 7가지 (균등 배분, 주간 각 패턴 3-5회)
① 불가능/의문 — "이게 진짜 존재한다고?" / "This Shouldn't Exist"
② 숫자 앵커 — "1초에 100만번" / "100 Million Times Per Second"
③ 부정 반전 — "이건 물이 아니다" / "This Isn't Water"
④ 숨겨진/미스터리 — "아무도 모르는 비밀" / "The Secret Nobody Knows"
⑤ 비교/최상급 — "태양보다 차가운 별" / "Colder Than the Sun"
⑥ 대비/비교 — "개미 vs 인간 근력" / "Ant vs Human Strength"
⑦ 감각/체험 — "이건 썩은 달걀 냄새가 나" / "It Smells Like Rotten Eggs"

## 제목 규칙
- askanything (ko): 공백 포함 15자 이내
- wonderdrop (en): 8단어 이내, 첫 글자 대문자
- exploratodo (es): 10단어 이내
- prismtale (es): 10단어 이내, 미스터리/다크 어조

## ★ 채널별 공개 제목/생성 앵커 게이트
- 채널 제목은 번역문이 아니다. 각 채널의 네이티브 쇼츠 제목이어야 한다.
- wonderdrop/exploratodo/prismtale 섹션은 모든 토픽에서 `Source Topic`/`Tema Base`를 가능하면 반드시 써라. 공통 토픽이라도 비한국 채널의 실제 생성 앵커는 현지 언어 제목 또는 Source Topic이어야 한다.
- Source Topic/Tema Base가 없으면 시스템은 비한국 채널의 공개 제목을 생성 앵커로 사용한다. 그래서 공개 제목은 짧아도 반드시 구체 명사+payoff를 포함해야 한다.
- wonderdrop: 질문형 번역을 피하고 declarative fact로 쓴다. `What If`, `Who Wins`, `vs` 남발 금지.
- exploratodo: LATAM 독자가 바로 읽는 제목. 영어식 `The Secret`, `What If` 시작 금지. `no era`, `nunca`, `por eso`, `oculto` 같은 반전/긴장감을 구체 명사와 함께 사용.
- prismtale: `secreto/misterio`만 던지지 말고 장소/물체/수치가 박힌 dark concrete mystery로 쓴다.
- 비한국 채널 제목에 한글, 내부 메모, 해시태그, `Title:` 라벨이 섞이면 실패다.

## ★ 토픽 헤더와 채널 제목 분리 규칙
- `## 1. ... [공통]`의 토픽 헤더는 내부 제작용 원본 토픽이다. 짧게 만들지 말고 LLM/검색/검증이 붙잡을 수 있는 구체 실체명과 결론을 반드시 넣어라.
- 채널별 짧은 클릭 제목은 `제목:` / `Title:` / `Titulo:` 줄에서만 압축한다.
- 토픽 헤더에는 반드시 아래 3요소가 보여야 한다:
  1. 구체 주어: 종명, 행성/위성명, 현상명, 유적명, 화학/지질 용어
  2. 결론/payoff: 무엇으로 밝혀졌는지, 무엇이 일어나는지
  3. 제작 앵커: 대본과 이미지가 찾아야 할 핵심 명사
- 나쁜 헤더: `어린 티라노가 아니었다`
- 좋은 헤더: `나노티라누스는 어린 티라노가 아니었다`
- 나쁜 헤더: `해구 밑으로 바다가 내려간다`
- 좋은 헤더: `해양판 섭입이 바닷물을 맨틀로 끌고 간다`
- 나쁜 헤더: `서랍 화석이 뒤집었다`
- 좋은 헤더: `서랍 속 나노티라누스 화석이 티라노 성장설을 뒤집었다`
- 좋은 헤더라도 채널 제목은 짧게 바꿀 수 있다. 예: 헤더 `나노티라누스는 어린 티라노가 아니었다` → askanything 제목 `티라노 새끼가 아니었다`

## 제목 클릭 강도 규칙
모든 제목은 "정리된 설명"보다 "즉시 클릭 욕구"를 먼저 만족해야 한다.
제목은 정보를 요약하는 문장이 아니라, 스크롤을 멈추게 하는 문장이어야 한다.

우선순위:
1. 클릭 욕구
2. 짧은 이해 가능성
3. 포맷 일관성
4. 정보 정확성 표현

제목 작성 원칙:
- 설명형 명사구보다 사건형, 질문형, 충격형, 감각형 제목을 우선하라.
- "원리", "이유", "비밀", "특징" 같은 단어를 기계적으로 반복하지 마라.
- 제목만 보고도 머릿속에 장면이 떠오르면 좋다.
- 약한 교과서 제목보다 강한 호기심 제목을 선택하라.
- 단, 낚시는 금지하고 내용으로 회수 가능한 수준의 강한 표현만 허용한다.

좋은 예:
- 이거 진짜 가능해?
- 지구 아래 660km에 숨겨진 것
- 시간이 멈추는 곳이 있다
- 이 동물은 500년을 산다
- 죽기 직전 더 젊어지는 생물

나쁜 예:
- 블랙홀의 시간 지연 원리
- 심해 압력의 특징
- 가장 오래 사는 동물의 비밀
- 태양보다 큰 별의 크기 비교

## ★ 포맷별 제목 형식 강제 (클릭률 직결)
- 아래 규칙은 채널별 공개 제목뿐 아니라 토픽 헤더에도 적용한다. 단, 토픽 헤더는 더 구체적이어야 한다.

- [포맷:WHO_WINS] 주제: 반드시 "vs" 포함
  KO: "태양 vs 블랙홀" / EN: "Sun vs Black Hole" / ES: "Sol vs Agujero Negro"
  → "vs" 없는 WHO_WINS 제목 절대 금지
  → 토픽 헤더에는 두 대상의 구체명과 승부축이 보여야 한다.

- [포맷:IF] 주제: 가정 조건 명시 필수
  KO: "달이 사라진다면?" / EN: "What If the Moon Disappeared?" / ES: "¿Qué pasaría si desaparece la Luna?"
  → KO: "~면?", "~다면?", "~없다면?" 중 하나 포함
  → EN: "What If" 또는 "If" 로 시작
  → ES: "¿Qué pasaría si" 또는 "¿Y si" 로 시작
  → 토픽 헤더에는 가정 조건과 결과/payoff가 같이 보여야 한다.

- [포맷:EMOTIONAL_SCI]: 질문형/감성형 제목
  KO: "엄마 몸속에 아이 세포가 산다" / EN: "Your Body Never Forgets You" / ES: "Tu cuerpo te recuerda siempre"
  → 충격형/대결형 제목 금지

- [포맷:FACT]: 자유형 (기존 규칙 유지)
  → 토픽 헤더에는 구체 주어와 핵심 사실이 모두 있어야 한다.

- [포맷:PARADOX]: 통념과 뒤집는 결론이 모두 있어야 한다.
  → `아니었다`, `뒤집었다`, `비밀`, `정체`만 쓰고 정답 명사를 숨기면 실패다.
  → 예: `나노티라누스는 어린 티라노가 아니었다`

- [포맷:COUNTDOWN]: TOP N 숫자와 순위 기준, 항목 주체가 보여야 한다.
  → 예: `티라노보다 무서운 공룡 무기 TOP 3`

- [포맷:SCALE]: 비교 기준과 규모/수치 앵커가 보여야 한다.

## 해시태그 규칙
- 정확히 5개 (초과 금지)
- 구성: 대형태그 1개 + 중형 2개 + 토픽고유 2개
- ⚠️ #쇼츠, #Shorts, #shorts 절대 금지 (YouTube가 자동 분류함)
- 채널 언어만 사용 (언어 혼용 금지)
- KO 예: #과학 #우주 #블랙홀 #시간왜곡 #상대성이론
- EN 예: #Science #Space #BlackHole #TimeWarp #Relativity
- ES 예: #Ciencia #Espacio #AgujeroNegro #Tiempo #Relatividad

## 설명(Description) 규칙
- 2~3문장 순수 텍스트만 (검색 키워드 자연스럽게 포함)
- Day 파일 Description 줄에는 해시태그(#) 금지 — Hashtags 줄은 업로드 직전 YouTube 설명 하단에 공개 footer로 붙는다.
- KO 예: "블랙홀의 중력은 상상 초월! 시공간을 휘게 해 시간이 느려진다는데, 과연 얼마나 느려질까?"
- EN 예: "A black hole's gravity bends spacetime itself. Time slows down near one — but by how much?"

## 출처 규칙 (중요)
- 특정 논문 제목이나 기관 보고서를 지어내지 마라
- 이 형식 사용:
  > 근거: [카테고리: 일반 상식 / 교과서 / 전문] — 핵심 팩트 1-2문장
  > 검색 키워드: "pluto heart nitrogen ice" (영어 검색어 — 사람이 5초 내 검증용)
- 확실하지 않은 수치는 "약 ~" 또는 범위로 표현

## 금지 토픽
- 정치/종교/인종 논쟁
- 미확인 음모론 (flat earth, 달착륙 조작 등)
- 의료 조언으로 오해될 수 있는 건강 토픽
- 자해/자살 관련
- 특정 국가 비하
- YouTube 커뮤니티 가이드라인 위반 소지

## 시의성 토픽 규칙
- 너의 학습 데이터 기준 최신이 아닐 수 있으므로 "가짜 최신 뉴스"를 만들지 마라
- 대신 아래 우선순위로 시의성 슬롯을 구성:
  1. 실제 최신 발견/관측/발표 후보가 입력으로 주어졌다면 그것을 최우선 사용
  2. 없으면 최근 1-3개월 내 반복적으로 주목받는 발견형 에버그린을 사용
  3. 그것도 없으면 계절성/반복 뉴스 사이클형 토픽 사용
- 특히 선호하는 발견형 예시:
  - 새로 발견된 지구형/슈퍼지구형 행성
  - 새 공룡/고생물 화석, 새로운 해석이 붙은 고생물
  - 심해 신종/심해에서 새로 확인된 현상
  - 고고학/고인류의 새 발견
- [시의성]으로 표시 ([트렌딩] 아님)
- 하루 3개 중 [시의성] 태그는 1~2개만 붙인다. 3개 전부 [시의성]이면 실패다.

중요: 하루 3개 토픽 중 1개는 반드시 "평균 조회를 노리는 토픽"이 아니라 "상위 1개 히트를 노리는 토픽"이어야 한다.

## 포맷 선택 공격성 규칙
포맷은 "가장 안전한 포맷"이 아니라 "가장 강한 전달 포맷"을 먼저 슬롯으로 선택해야 한다.

판단 기준:
- 같은 주제라도 더 강한 훅이 가능하면 더 공격적인 포맷을 선택하라.
- 단순 설명으로 끝나는 FACT보다, 반전이 강하면 PARADOX를 우선한다.
- 생존/파멸 상상이 강하면 FACT보다 IF를 우선한다.
- WHO_WINS는 askanything 전용 연속 VS 시리즈 레인으로 우선 편성한다. concrete duel, 승부축, [시리즈:...] 태그, 다음 상대 예고가 모두 있어야 한다.
- wonderdrop/exploratodo/prismtale는 기본적으로 FACT/PARADOX/MYSTERY/IF를 우선하고, 명시 테스트가 아니면 WHO_WINS를 공통 슬롯으로 끌고 가지 않는다.
- 열린 결말과 댓글 유도가 강하면 FACT보다 MYSTERY를 우선한다.
- 숫자/규모 체감이 핵심이면 SCALE을 우선하고, COUNTDOWN 대신 single-reveal FACT/PARADOX를 검토한다.
- 안전하다는 이유만으로 FACT에 과도하게 몰아넣지 마라.

금지:
- 애매하면 가장 무난한 포맷 선택하기
- 강한 훅이 가능한데도 설명형 포맷으로 약화시키기
- 형식만 안정적이고 클릭 욕구가 약한 포맷을 우선하기

## ★ 콘텐츠 포맷 자동 판단 규칙 (8종)
8포맷 운영표를 먼저 정하고, 해당 포맷의 필수 조건을 만족하는 토픽만 선발한다.
단, 포맷에 토픽을 억지로 끼워맞추지 말고, 슬롯을 못 채우는 토픽은 교체한다.

포맷 판단 기준:
- [포맷:WHO_WINS]: 두 대상 비교가 자연스러운 주제 (11컷 대결)
  → 신호: "vs", "더 강한", "누가", "이길까", 두 개체 대결 구도
  → ⚠️ 반드시 구체적 종명/대상명 사용. 추상적 표현 금지.
    ❌ "공룡 vs 악어" (LLM이 제멋대로 종을 바꿈)
    ✅ "티라노사우루스 vs 악어", "백상아리 vs 범고래"
  → ⚠️ 반드시 [시리즈:...] 태그를 붙인다. 단발 VS/고립 VS는 실패.
  → ⚠️ 이전 승자 vs 새 도전자, 또는 EP1 최강 후보 2명 구도가 보여야 한다.
  → ⚠️ wonderdrop/exploratodo/prismtale에서는 기본 비추천. askanything에서만 선택 우선권이 있다.
  → 예: "태양 vs 블랙홀", "티라노사우루스 vs 악어", "번개 vs 화산"
  → 주간 2-3개, 2-3일 간격으로 같은 시리즈를 이어간다.

- [포맷:IF]: 가정/시나리오가 자연스러운 주제 (10-11컷 가정)
  → 신호: "만약", "사라진다면", "없어지면", "갑자기", "하루아침에"
  → 예: "달이 사라진다면", "중력이 없어지면", "지구가 멈추면"
  → 주간 3-4개

- [포맷:EMOTIONAL_SCI]: 인체/심리/감성 팩트 주제 (8-9컷 감성)
  → 신호: 인체, 감정, 기억, 관계, 따뜻한 과학
  → 예: "엄마 몸속 아이 세포", "눈물의 성분", "피부가 기억하는 것"
  → 주간 2-3개 (KO/ES 채널 강세)

- [포맷:FACT]: 순수 팩트/다큐 주제 (8-10컷 팩트)
  → 기본값 — 다른 포맷에 해당 안 되면 FACT
  → 주간 3-4개

- [포맷:COUNTDOWN]: 현재 운영에서 사용하지 않는다.
  → TOP N/랭킹 아이디어는 single-reveal FACT, SCALE, PARADOX 중 하나로 재작성
  → 예: "가장 깊은 바다 TOP 5" 대신 "바다에서 가장 깊은 곳은 에베레스트도 삼킨다"
  → 주간 0개

- [포맷:SCALE]: 규모 비교/스케일 충격 주제 (7-9컷 규모비교)
  → 신호: "크기", "비교", "얼마나 큰", "실제 크기", 수치 스케일
  → 예: "블랙홀 실제 크기", "세포 vs 은하", "지구가 모래알이라면"
  → 주간 2개

- [포맷:PARADOX]: 통념 뒤집기/역설 주제 (7-8컷 역설)
  → 신호: "사실은", "반대로", "알고 보면", "역설", "진짜 이유"
  → 예: "물이 사실 독인 이유", "어둠은 존재하지 않는다", "뜨거운 물이 먼저 어는 이유"
  → 주간 1-2개

- [포맷:MYSTERY]: 미스터리/미해결 주제 (8-9컷 미스터리)
  → 신호: "미스터리", "설명 불가", "아직도 모른다", "비밀", "수수께끼"
  → 예: "바다 심해 미확인 소리", "보이니치 문서", "나스카 라인의 비밀"
  → 주간 1-2개

포맷 태그 표기:
- 기본형: [공통] [포맷:XXX]
- 3번째 슬롯은: [공통] [채널분화] [포맷:XXX]
- 같은 포맷 하루 최대 1개 권장 (같은 포맷 2개 연속 금지)
- 하루 3토픽은 서로 다른 포맷으로 배분 (다양성 극대화)

## 3번째 슬롯 분화 규칙
- 하루 3번째 토픽은 반드시 `[채널분화]` 태그를 붙인다.
- Topic 3 헤더는 그룹핑용 umbrella만 맡고, 실제 생성 앵커는 채널 섹션 안 `원본주제:` / `Source Topic:` / `Tema Base:` 줄에 따로 쓴다.
- 이때 채널별 원본주제는 완전히 달라도 된다. 공통 주제의 억지 번역/복제를 금지한다.
- askanything / wonderdrop / exploratodo / prismtale는 각자 가장 잘 먹는 소재를 따로 받는다.
- exploratodo는 negation/paradox, prismtale는 concrete mystery, wonderdrop는 declarative fact, askanything은 question/IF angle을 우선한다.
- Topic 3의 공개 제목은 짧게 써도 되지만, `원본주제` 줄은 반드시 구체적인 실체명+payoff를 포함한 생성 앵커여야 한다.

## 시리즈 토픽 규칙
WHO_WINS 포맷은 토너먼트 시리즈로 연속 대결해야 한다:
- [시리즈:시리즈명] 태그 필수 (예: [포맷:WHO_WINS] [시리즈:공룡대전])
- 같은 시리즈의 다음 에피소드에는 이전 승자 언급 + 다음 도전자 예고
- 시리즈 첫 화: "EP1" 느낌의 시작 — 최강 후보 2명 등장
- 시리즈 후속: 이전 승자 vs 새 도전자 구도
- 주간 2-3개 시리즈 토픽 필수 레인으로 운영 (연속 2일 같은 시리즈 금지, 2-3일 간격 권장)
- WHO_WINS인데 [시리즈:...]가 없거나 컷11 다음 상대 예고가 불가능한 토픽은 다른 포맷으로 바꾸지 말고 교체

## 출력 포맷
각 Day를 아래 형식으로 출력:

# Day NN (M-D)

## 1. 이모지 토픽제목 [공통] [시의성(선택)] [포맷:WHO_WINS] [시리즈:시리즈명(WHO_WINS면 필수)]
> 근거: [카테고리: 교과서] — 핵심 팩트
> 검색 키워드: "english search terms"
> 채널: askanything, wonderdrop, exploratodo, prismtale
> 핵심 훅: 1문장 훅 (주제 성격에 맞게)
> 훅 패턴: ①~⑦ 중 선택

## 3. 이모지 토픽제목 [공통] [채널분화] [포맷:FACT]
> Topic 3는 채널별 원본주제를 따로 써도 된다. 아래 채널 섹션의 `원본주제/Source Topic/Tema Base`가 실제 생성 앵커다.

### askanything (ko)
원본주제: 한국어 생성 앵커 (Topic 3의 [채널분화]일 때 필수, 나머지는 선택)
제목: 한국어 제목
설명: 2~3문장 순수 텍스트 (이 줄에는 해시태그 금지, 검색 키워드 자연 포함)
해시태그: #태그1 #태그2 #태그3 #태그4 #태그5

### wonderdrop (en)
Source Topic: English generation anchor (required for Topic 3 and strongly required for every non-KO topic)
Title: English title
Description: 2-3 sentences plain text (NO hashtags in this line, include search keywords naturally)
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4 #Tag5

### exploratodo (es-LATAM)
Tema Base: ancla generativa en español (obligatorio en Topic 3 y muy recomendado en cada tema no coreano)
Titulo: Titulo en español
Descripcion: 2-3 oraciones texto puro (SIN hashtags en esta linea, incluir palabras clave)
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4 #Tag5

### prismtale (es-US)
Tema Base: ancla generativa en español US (obligatorio en Topic 3 y muy recomendado en cada tema no coreano)
Titulo: Titulo oscuro/misterioso
Descripcion: 2-3 oraciones texto puro (SIN hashtags en esta linea, tono cinematico)
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4 #Tag5

---

[전용 토픽은 해당 채널 섹션만 작성]
"""


def generate_weekly_topics(start_date: datetime, days: int = 7,
                           llm_provider: str | None = None) -> dict[str, Any]:
    """주간 토픽 생성 — 성과 분석 + LLM 전문가.

    llm_provider: "openai" | "gemini" | None (자동 — Vertex/Gemini 우선)
    env TOPIC_LLM_MODEL: 모델 오버라이드 (예: gpt-5.4, gemini-2.5-pro)
    """
    # 프로바이더 자동 결정
    if llm_provider is None:
        from modules.utils.provider_policy import get_openai_api_key, is_openai_api_disabled

        preferred_provider = os.getenv("TOPIC_LLM_PROVIDER", "").strip().lower()
        if preferred_provider == "openai" and is_openai_api_disabled():
            llm_provider = "gemini"
        elif preferred_provider in {"openai", "gemini"}:
            llm_provider = preferred_provider
        elif os.getenv("GEMINI_BACKEND", "").lower() == "vertex_ai" or os.getenv("VERTEX_SA_ONLY", "").lower() in {"1", "true", "yes", "on"}:
            llm_provider = "gemini"
        else:
            llm_provider = "openai" if get_openai_api_key() else "gemini"

    # 1. 컨텍스트 수집
    performance = _get_performance_context()
    used_topics = _get_used_topics()
    hit_patterns = _analyze_hit_patterns()
    last_day = _get_last_day_number()
    fresh_discovery_context = _get_fresh_discovery_context()
    global_topic_signals_context = _get_global_topic_signals_context()
    try:
        from modules.utils.series_state import build_active_series_context

        active_series_context = build_active_series_context()
    except Exception as series_exc:
        print(f"[토픽 생성] VS 시리즈 상태 로드 실패(무시): {series_exc}")
        active_series_context = "## VS 시리즈 연속성 상태\n[필수 후속 VS]\n- 현재 업로드가 예고한 필수 후속 VS 없음."

    # 2. LLM 프롬프트 구성
    user_prompt, date_range = _build_topic_generation_request(
        start_date,
        days,
        performance,
        used_topics,
        hit_patterns,
        last_day,
        fresh_discovery_context=fresh_discovery_context,
        global_topic_signals_context=global_topic_signals_context,
        active_series_context=active_series_context,
    )

    # 3. LLM 호출
    _topic_model = os.getenv(
        "TOPIC_LLM_MODEL",
        "gpt-5.4" if llm_provider == "openai" else "gemini-2.5-pro",
    )
    if llm_provider == "gemini" and _topic_model.lower().startswith(("gpt-", "o")):
        _topic_model = os.getenv("TOPIC_GEMINI_MODEL", "gemini-2.5-pro")
    if llm_provider == "openai" and _topic_model.lower().startswith("gemini-"):
        _topic_model = os.getenv("TOPIC_OPENAI_MODEL", "gpt-5.4")
    orchestra_enabled = os.getenv("TOPIC_ORCHESTRA_ENABLED", "true").lower() not in {"0", "false", "no"}
    orchestra_strict = os.getenv("TOPIC_ORCHESTRA_STRICT", "false").lower() in {"1", "true", "yes"}
    print(f"[토픽 생성] {days}일분 토픽 생성 중... ({llm_provider}/{_topic_model})")

    raw_content = ""
    log_dir = None
    stage_paths: dict[str, str] = {}
    orchestration_mode = "single_pass"

    if orchestra_enabled:
        orchestration_mode = "multi_agent"
        orchestration = _run_topic_orchestra(
            start_date=start_date,
            days=days,
            llm_provider=llm_provider,
            model_name=_topic_model,
            performance=performance,
            used_topics=used_topics,
            hit_patterns=hit_patterns,
            last_day=last_day,
            user_prompt=user_prompt,
            date_range=date_range,
            fresh_discovery_context=fresh_discovery_context,
            global_topic_signals_context=global_topic_signals_context,
            strict=orchestra_strict,
        )
        if orchestration.get("success"):
            raw_content = orchestration.get("raw_content", "").strip()
            log_dir = orchestration.get("log_dir")
            stage_paths = orchestration.get("stages", {})
        else:
            print(f"[토픽 생성] 오케스트라 실패 → 단일 패스로 폴백: {orchestration.get('error')}")
            log_dir = orchestration.get("log_dir")

    if not raw_content:
        try:
            raw_content = _run_topic_single_pass(
                llm_provider=llm_provider,
                model_name=_topic_model,
                user_prompt=user_prompt,
                days=days,
            )
            if log_dir:
                _write_text_atomic(Path(log_dir) / "05_fallback_single_pass.md", raw_content)
                orchestration_mode = "fallback_single_pass"
        except Exception as e:
            return {"success": False, "error": f"LLM 호출 실패 ({llm_provider}): {e}", "log_dir": log_dir}

    if not raw_content:
        return {"success": False, "error": "LLM 응답 비어있음", "log_dir": log_dir}

    harness_rounds = int(os.getenv("TOPIC_HARNESS_ROUNDS", "5"))
    if harness_rounds > 0:
        try:
            raw_content = _run_topic_quality_harness(
                llm_provider=llm_provider,
                model_name=_topic_model,
                user_prompt=user_prompt,
                raw_content=raw_content,
                used_topics=used_topics,
                days=days,
                date_range=date_range,
                log_dir=Path(log_dir) if log_dir else None,
                rounds=harness_rounds,
            )
            if log_dir:
                _write_text_atomic(Path(log_dir) / "05_after_harness.md", raw_content)
        except Exception as e:
            print(f"[토픽 생성] 후처리 하네스 실패(무시): {e}")

    # 4. 출력 검증 + 하드게이트 자동 수리 + Day 파일 저장
    repair_attempts = int(os.getenv("TOPIC_HARD_REPAIR_ATTEMPTS", "3"))
    repair_model = os.getenv("TOPIC_REPAIR_LLM_MODEL", _topic_model)
    validation_errors, hard_errors = _collect_generation_validation(
        raw_content,
        used_topics,
        date_range,
        active_series_context,
    )
    for attempt in range(repair_attempts):
        if not hard_errors:
            break
        if not log_dir:
            log_dir = str(_create_topic_log_dir(start_date, days))
        feedback = "\n".join(f"- {e}" for e in hard_errors[:80])
        forbidden_phrases = _extract_forbidden_phrases_from_errors(hard_errors)
        repair_prompt = f"""{user_prompt}

## 이전 최종 출력
{raw_content}

## 하드게이트 실패 목록
{feedback}

## 이번 수리에서 절대 다시 쓰면 안 되는 실패 소재/문구
{forbidden_phrases}

## 반드시 맞춰야 하는 최종 출력 뼈대
{_build_required_day_skeleton(date_range)}

## 수리 지시
- 위 실패를 모두 제거한 Day 파일 최종 출력만 다시 작성하라.
- 첫 줄은 반드시 "{'# ' + date_range[0] if date_range else '# Day'}"이어야 한다.
- 요청 날짜 범위만 사용하고, 각 Day 정확히 3개 토픽만 남겨라.
- Day 번호를 1부터 다시 시작하지 마라. 아래 뼈대의 Day 번호/날짜를 한 글자도 바꾸지 말고 그대로 써라.
- 허용되는 Day 헤더는 아래 뼈대의 {days}개뿐이다. Day 1~{days} 형식으로 리셋하면 즉시 실패다.
- 하드게이트 실패 목록에 등장하지 않은 유효한 토픽은 가능한 한 그대로 유지하라.
- 중복으로 지목된 토픽만 완전히 새 소재로 교체하라.
- "추가 토픽" 섹션을 만들지 말고, 중복 소재는 완전히 다른 소재로 교체하라.
- 시의성 0개인 Day는 실제 발견/관측/연구 발표형 토픽 1개를 새로 넣거나, 이미 발견형 근거가 있는 토픽 1개에만 [시의성] 태그를 붙여라.
- 하루 [시의성] 태그는 1~2개만 허용한다.
- 하루 3개 전부 [시의성]이면 최소 1개는 에버그린/교과서형 강한 훅으로 바꾸거나 [시의성] 태그를 제거하라.
- 기존 사용 토픽/소재와 같은 팩트는 제목을 바꿔도 실패다.
- 각 Hashtags/해시태그 라인은 최대 5개만 쓰고, shorts/short/쇼츠 태그는 절대 쓰지 마라.
- Day 파일의 Description/설명 줄에는 # 문자를 넣지 마라. Hashtags/해시태그 줄은 업로드 직전 설명 하단 공개 footer로 붙는다.
"""
        print(f"[토픽 생성] 하드게이트 실패 {len(hard_errors)}건 → 자동 수리 {attempt + 1}/{repair_attempts}")
        try:
            raw_content = _call_topic_llm(
                llm_provider=llm_provider,
                model_name=repair_model,
                system_prompt=_with_dynamic_topic_limits(TOPIC_EXPERT_PROMPT, days),
                user_prompt=repair_prompt,
                stage_name=f"HardGateRepair{attempt + 1}",
                temperature=0.25,
                max_tokens=30000,
            )
            _write_text_atomic(Path(log_dir) / f"06_hardgate_repair_{attempt + 1}.md", raw_content)
            repaired_raw_content = raw_content
            if harness_rounds > 0:
                try:
                    raw_content = _run_topic_quality_harness(
                        llm_provider=llm_provider,
                        model_name=repair_model,
                        user_prompt=user_prompt,
                        raw_content=raw_content,
                        used_topics=used_topics,
                        days=days,
                        date_range=date_range,
                        log_dir=Path(log_dir),
                        rounds=min(2, harness_rounds),
                        stage_prefix=f"RepairHarness{attempt + 1}_",
                    )
                except Exception as harness_exc:
                    raw_content = repaired_raw_content
                    print(
                        f"[토픽 생성] RepairHarness {attempt + 1} 실패 → "
                        f"직전 유효 수리본 유지: {harness_exc}"
                    )
            validation_errors, hard_errors = _collect_generation_validation(
                raw_content,
                used_topics,
                date_range,
                active_series_context,
            )
        except Exception as e:
            hard_errors.append(f"하드게이트 자동 수리 실패: {e}")
            break

    if hard_errors:
        if log_dir:
            _write_json_atomic(
                Path(log_dir) / "98_validation.json",
                {
                    "success": False,
                    "mode": orchestration_mode,
                    "validation_errors": validation_errors,
                    "hard_errors": hard_errors,
                },
            )
        return {
            "success": False,
            "error": "토픽 생성 결과가 하드 검증에 실패하여 Day 파일을 저장하지 않았습니다.",
            "hard_errors": hard_errors,
            "validation_errors": validation_errors,
            "log_dir": log_dir,
            "mode": orchestration_mode,
        }

    saved_files = []
    day_blocks = re.split(r"(?=# Day \d+)", raw_content)
    for block in day_blocks:
        block = block.strip()
        if not block.startswith("# Day"):
            continue

        header_match = re.match(r"# Day (\d+) \((\d+-\d+)\)", block)
        if not header_match:
            continue

        day_num = int(header_match.group(1))
        date_str = header_match.group(2)
        existing_day_num = _find_existing_day_number_for_date(date_str)
        target_day_num = existing_day_num or day_num
        if target_day_num != day_num:
            block = re.sub(
                r"^# Day \d+ \(",
                f"# Day {target_day_num} (",
                block,
                count=1,
            )

        filename = f"Day {target_day_num} ({date_str}).md"
        filepath = os.path.join(DAY_FILES_DIR, filename)

        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(filepath), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(block)
        os.replace(tmp_path, filepath)
        saved_files.append(filename)
        print(f"  [토픽 생성] {filename} 저장 완료")

    if log_dir:
        _write_json_atomic(
            Path(log_dir) / "99_result.json",
            {
                "success": True,
                "mode": orchestration_mode,
                "saved_files": saved_files,
                "topic_count": len(re.findall(r"^## \d+\.", raw_content, re.MULTILINE)),
                "validation_errors": validation_errors,
                "stage_paths": stage_paths,
            },
        )

    # 5. 텔레그램 알림
    try:
        from modules.utils.notify import _send
        import re as _re
        topic_count = len(_re.findall(r"^## \d+\.", raw_content, _re.MULTILINE))
        file_list = "\n".join(f"  📄 {f}" for f in saved_files)
        warn_text = ""
        if validation_errors:
            warn_text = f"\n⚠️ 검증 경고 {len(validation_errors)}건:\n" + "\n".join(f"  - {e}" for e in validation_errors[:5])
        _send(
            f"━━━━━━━━━━━━━━━\n"
            f"📝 <b>주간 토픽 생성 완료</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 {days}일분 / {topic_count}개 토픽\n"
            f"{file_list}\n"
            f"{warn_text}\n"
            f"🔍 <b>검수 필요</b> — 검색 키워드로 팩트 확인 후 배포\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            kind="weekly_topics_generated",
            meta={"days": days, "topic_count": topic_count, "files": saved_files[:10]},
        )
    except Exception:
        pass

    return {
        "success": True,
        "days": days,
        "files": saved_files,
        "topic_count": len(re.findall(r"^## \d+\.", raw_content, re.MULTILINE)),
        "validation_errors": validation_errors,
        "log_dir": log_dir,
        "mode": orchestration_mode,
        "stage_paths": stage_paths,
    }
