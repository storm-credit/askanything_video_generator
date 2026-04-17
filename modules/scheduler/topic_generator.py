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


def _get_used_topics() -> list[str]:
    """기존 Day 파일에서 사용된 토픽 목록 전체 추출 (중복 방지)."""
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
    except Exception as e:
        print(f"[토픽 생성] 기존 토픽 로드 실패: {e}")
    return list(set(used))  # 중복 제거


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
    ("frankfurt_roman_sanctuary", [r"프랑크푸르트", r"frankfurt", r"로마\s*성역", r"roman\s+sanctuary"]),
    ("deep_sea_new_species", [r"심해.*(?:신종|종\s*발견|산호초)", r"아르헨티나.*심해", r"deep\s*sea.*(?:species|coral)"]),
    ("earth_like_exoplanet", [r"hd\s*137010", r"지구\s*(?:닮은|형).*외계", r"earth\s*like.*exoplanet"]),
    ("egypt_animal_tomb", [r"이집트.*(?:800구|동물\s*무덤|동물\s*묘지)", r"egypt.*animal.*(?:tomb|cemetery)"]),
    ("mantle_ocean_660km", [r"맨틀.*바다", r"660\s*km.*(?:지하|물|바다)", r"지하\s*660", r"mantle.*ocean"]),
    ("ancient_ice_air", [r"80만\s*년.*공기", r"빙하.*공기", r"ancient.*air.*ice"]),
    ("deep_sea_10000m", [r"심해\s*(?:1만|10000|10,000)\s*미터", r"deep\s*sea\s*(?:10000|10,000)"]),
]


def _semantic_duplicate_key(topic: str) -> str | None:
    """반복 표현을 바꿔도 같은 소재면 같은 키로 묶는다."""
    compact = re.sub(r"\s+", " ", topic.lower())
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
        for topic in _extract_day_topics(block):
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


def _get_hard_validation_errors(block: str, expected_day: int) -> list[str]:
    """자동 저장을 막아야 하는 구조 오류."""
    errors = []
    topic_count = len(re.findall(r"^## \d+\.", block, re.MULTILINE))
    if topic_count != 3:
        errors.append(f"토픽 {topic_count}개 — 정확히 3개 필요")
    common_topics = re.findall(r"(## \d+\..+?\[공통\].*?)(?=^## \d+\.|\Z)", block, re.DOTALL | re.MULTILINE)
    for ct in common_topics:
        topic_title = re.search(r"^## \d+\.\s+(.+?)(?:\s+\[|$)", ct, re.MULTILINE)
        title = (topic_title.group(1) if topic_title else "?").strip()
        for ch in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
            if f"### {ch}" not in ct:
                errors.append(f"공통 토픽 '{title}'에 {ch} 섹션 누락")
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
        if len(tags) > 5:
            errors.append(f"해시태그 라인 {idx}: {len(tags)}개 — 최대 5개만 허용")
        banned_found = [t for t in tags if t.lower() in banned_tags]
        if banned_found:
            errors.append(f"해시태그 라인 {idx}: shorts류 금지 태그 포함 ({', '.join(banned_found)})")
    description_lines = re.findall(r"^\s*(?:설명(?:\s*\(본문\))?|Description|Descripcion|Descripción):\s*(.+)$", block, re.MULTILINE)
    for idx, line in enumerate(description_lines, start=1):
        if "#" in line:
            errors.append(f"설명 라인 {idx}: 본문 설명에 #해시태그 금지")
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
) -> tuple[list[str], list[str]]:
    """전체 생성 결과의 경고/하드 오류를 모은다."""
    validation_errors: list[str] = []
    hard_errors = _validate_requested_day_headers(raw_content, date_range)
    hard_errors.extend(_validate_topic_uniqueness(raw_content, used_topics))
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
            "## 3. ... [공통] [포맷:XXX]",
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

반드시 아래 섹션으로만 답해라:
## Winning Thesis
## Push Hard
## Underweight / Avoid
## Hook Directives
## Explosive Bets
## Duplicate Red Flags

규칙:
- 주간 21개 전체를 바라보는 메모를 써라.
- "왜 이 방향이 조회수에 유리한지"를 데이터 언어로 설명하라.
- 중복 위험, 약한 카테고리, 최근 약세 포맷은 명확히 경고하라.
- 하루 3개 중 [시의성] 발견형 슬롯은 1~2개만 배치하는 전략을 제시하라.
"""


TOPIC_WEEKLY_STRATEGIST_PROMPT = """너는 Weekly Strategist다.

역할:
- Signal Analyst 메모를 바탕으로 다음 7일치 주제 초안을 짠다.
- 목표는 평균형이 아니라 '이번 주에 최소 2~3개는 크게 터질 수 있는 주간 편성'이다.
- 하루 3개 모두 무난하게 만들지 말고, 매일 1개는 반드시 공격형 토픽으로 뽑아라.

출력 형식:
## Day Plan
### Day N (M-D)
- [score:10][category:우주/행성][hook:② 숫자 앵커][format:IF] 토픽명 :: 왜 터질지 1문장

## Reserve Ideas
- 후보 :: 이유

규칙:
- 총 7일 × 3개 = 21개 본선 토픽
- 각 줄은 반드시 score/category/hook/format 태그 포함
- 약한 교과서형 제목, 기존 주제 재탕, 같은 카테고리 과밀 편성 금지
- WonderDrop/PrismTale/ExploraTodo/AskAnything 모두 공통으로 먹힐 토픽만 우선
- 하루 3개 중 [시의성] 발견형 토픽은 1~2개만 허용한다.
"""


TOPIC_QUALITY_CRITIC_PROMPT = """너는 Quality Critic이다.

역할:
- Weekly Strategist 초안을 냉정하게 검수한다.
- 약한 제목, 중복 위험, 카테고리 쏠림, 포맷 과밀, 너무 안전한 토픽을 잘라낸다.
- "재작성 없이 통과", "수정 후 통과", "반려"를 분리해라.

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
- score 8 미만 감각의 토픽은 가능한 한 보정하거나 교체하라.
- "문어 피는 파랗다" 같은 교과서형 표현은 더 공격적으로 바꾸라고 지시하라.
"""


def _build_topic_generation_request(
    start_date: datetime,
    days: int,
    performance: str,
    used_topics: list[str],
    hit_patterns: str,
    last_day: int,
    fresh_discovery_context: str = "",
) -> tuple[str, list[str]]:
    """주간 토픽 생성 공통 요청문과 날짜 범위를 만든다."""
    date_range = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        day_num = last_day + 1 + i
        date_range.append(f"Day {day_num} ({d.month}-{d.day})")

    user_prompt = f"""다음 {days}일분 토픽을 생성해줘.

## 날짜 범위
{chr(10).join(date_range)}

## 성과 분석 데이터
{performance}

## 히트 패턴 (이 패턴으로 새 토픽 복제)
{hit_patterns}

## 최신성 후보 / 발견형 후보
{fresh_discovery_context or "실시간 발견형 후보 없음 — 최근 발견형 패턴을 모사하되 가짜 최신 뉴스는 금지"}

## 이미 사용된 토픽 (중복 금지 — 제목이 다르더라도 같은 팩트면 중복)
{chr(10).join(f'- {t}' for t in used_topics)}

## 코드 하드게이트가 막는 반복 소재 클러스터
{_build_semantic_duplicate_brief(used_topics)}

## 최종 출력 필수 뼈대
아래 Day 헤더와 토픽 3개 구조를 정확히 채워라. Day 헤더 누락/추가/접미사 금지.
{_build_required_day_skeleton(date_range)}

## 요청
- 하루 3개 토픽 × {days}일 = {3 * days}개 (전부 [공통])
- 요청된 날짜 범위에 있는 Day만 출력. "추가 토픽", 보충 Day, Reserve 후보를 최종 출력에 섞으면 실패
- 각 Day는 정확히 3개 토픽만 포함. 하루 2개/4개 이상이면 저장 실패
- 모든 주제에 [포맷:XXX] 태그 필수 — 주제 성격 보고 자동 판단 (8종)
- 하루 3토픽은 서로 다른 포맷 사용 (같은 포맷 2개 연속 금지)
- WHO_WINS: 자연스러운 대결 구도 주제만, 억지 비교 금지
- EMOTIONAL_SCI: 인체/심리/감성 주제만 (우주/자연 팩트에 강제 적용 금지)
- COUNTDOWN: 순위/리스트 주제에 사용 (순수 리스트형)
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
    if llm_provider == "openai":
        import openai

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY 미설정")
        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model_name,
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
        model=model_name,
        contents=f"{system_prompt}\n\n{user_prompt}",
        config={
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "http_options": types.HttpOptions(timeout=120_000),
        },
    )
    return (response.text or "").strip()


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
    }
    _write_json_atomic(log_dir / "00_run_meta.json", meta)
    _write_text_atomic(log_dir / "00_request.md", user_prompt)
    _write_text_atomic(log_dir / "00_fresh_discovery_input.md", fresh_discovery_context)

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
주제를 먼저 선정하고, 주제 성격에 맞는 포맷을 자동 판단해서 태그를 붙인다.

## 채널 정보
- askanything (KO): 한국어, 빠른 반말, 호기심 자극
- wonderdrop (EN): 영어, confident authority 다큐, 시네마틱
- exploratodo (ES-LATAM): 스페인어 LATAM, 에너지 넘침, 빠른 리듬
- prismtale (ES-US): 스페인어 US, 다크 미스터리, 시네마틱

## 토픽 배분 규칙 (채널당 3개/일)
1. 하루 3개 토픽 (전부 공통 — 4채널 동시 제작)
2. 카테고리 배분 (주간 기준):
   - 성과 상위 카테고리: 50%
   - 히트 패턴 복제: 20%
   - 새 카테고리 테스트: 15%
   - 채널 강점 카테고리: 15%

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
- [포맷:WHO_WINS] 주제: 반드시 "vs" 포함
  KO: "태양 vs 블랙홀" / EN: "Sun vs Black Hole" / ES: "Sol vs Agujero Negro"
  → "vs" 없는 WHO_WINS 제목 절대 금지

- [포맷:IF] 주제: 가정 조건 명시 필수
  KO: "달이 사라진다면?" / EN: "What If the Moon Disappeared?" / ES: "¿Qué pasaría si desaparece la Luna?"
  → KO: "~면?", "~다면?", "~없다면?" 중 하나 포함
  → EN: "What If" 또는 "If" 로 시작
  → ES: "¿Qué pasaría si" 또는 "¿Y si" 로 시작

- [포맷:EMOTIONAL_SCI]: 질문형/감성형 제목
  KO: "엄마 몸속에 아이 세포가 산다" / EN: "Your Body Never Forgets You" / ES: "Tu cuerpo te recuerda siempre"
  → 충격형/대결형 제목 금지

- [포맷:FACT]: 자유형 (기존 규칙 유지)

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
- ⚠️ 설명에 해시태그(#) 절대 금지 — 해시태그는 해시태그 필드에만
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
포맷은 "가장 안전한 포맷"이 아니라 "가장 강한 전달 포맷"을 선택해야 한다.

판단 기준:
- 같은 주제라도 더 강한 훅이 가능하면 더 공격적인 포맷을 선택하라.
- 단순 설명으로 끝나는 FACT보다, 반전이 강하면 PARADOX를 우선한다.
- 생존/파멸 상상이 강하면 FACT보다 IF를 우선한다.
- 논쟁성과 편가르기가 강하면 FACT보다 WHO_WINS를 우선한다.
- 열린 결말과 댓글 유도가 강하면 FACT보다 MYSTERY를 우선한다.
- 숫자/규모 체감이 핵심이면 SCALE 또는 COUNTDOWN을 우선한다.
- 안전하다는 이유만으로 FACT에 과도하게 몰아넣지 마라.

금지:
- 애매하면 가장 무난한 포맷 선택하기
- 강한 훅이 가능한데도 설명형 포맷으로 약화시키기
- 형식만 안정적이고 클릭 욕구가 약한 포맷을 우선하기

## ★ 콘텐츠 포맷 자동 판단 규칙 (8종)
주제를 선정한 뒤, 주제 성격을 보고 포맷을 결정한다. 포맷을 먼저 정하고 주제를 끼워맞추지 마라.

포맷 판단 기준:
- [포맷:WHO_WINS]: 두 대상 비교가 자연스러운 주제 (11컷 대결)
  → 신호: "vs", "더 강한", "누가", "이길까", 두 개체 대결 구도
  → ⚠️ 반드시 구체적 종명/대상명 사용. 추상적 표현 금지.
    ❌ "공룡 vs 악어" (LLM이 제멋대로 종을 바꿈)
    ✅ "티라노사우루스 vs 악어", "백상아리 vs 범고래"
  → 예: "태양 vs 블랙홀", "티라노사우루스 vs 악어", "번개 vs 화산"
  → 주간 3-4개

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

- [포맷:COUNTDOWN]: TOP N 순위 나열 주제 (8-10컷 카운트다운)
  → 신호: "TOP", "가장 ~한", "순위", "최고", "1위", 숫자 리스트
  → 예: "가장 깊은 바다 TOP 5", "가장 뜨거운 행성 5선", "최강 독 동물 랭킹"
  → 주간 2-3개

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
- 반드시 [공통] 태그 뒤에 [포맷:XXX] 함께 표기
- 같은 포맷 하루 최대 1개 권장 (같은 포맷 2개 연속 금지)
- 하루 3토픽은 서로 다른 포맷으로 배분 (다양성 극대화)

## 시리즈 토픽 규칙
WHO_WINS 포맷은 토너먼트 시리즈로 연속 대결 가능:
- [시리즈:시리즈명] 태그 추가 (예: [포맷:WHO_WINS] [시리즈:공룡대전])
- 같은 시리즈의 다음 에피소드에는 이전 승자 언급 + 다음 도전자 예고
- 시리즈 첫 화: "EP1" 느낌의 시작 — 최강 후보 2명 등장
- 시리즈 후속: 이전 승자 vs 새 도전자 구도
- 주간 1-2개 시리즈 토픽 권장 (연속 2일 같은 시리즈 금지)

## 출력 포맷
각 Day를 아래 형식으로 출력:

# Day NN (M-D)

## 1. 이모지 토픽제목 [공통] [시의성(선택)] [포맷:WHO_WINS] [시리즈:시리즈명(선택)]
> 근거: [카테고리: 교과서] — 핵심 팩트
> 검색 키워드: "english search terms"
> 채널: askanything, wonderdrop, exploratodo, prismtale
> 핵심 훅: 1문장 훅 (주제 성격에 맞게)
> 훅 패턴: ①~⑦ 중 선택

### askanything (ko)
제목: 한국어 제목
설명: 2~3문장 순수 텍스트 (해시태그 금지, 검색 키워드 자연 포함)
해시태그: #태그1 #태그2 #태그3 #태그4 #태그5

### wonderdrop (en)
Title: English title
Description: 2-3 sentences plain text (NO hashtags, include search keywords naturally)
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4 #Tag5

### exploratodo (es-LATAM)
Titulo: Titulo en español
Descripcion: 2-3 oraciones texto puro (SIN hashtags, incluir palabras clave)
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4 #Tag5

### prismtale (es-US)
Titulo: Titulo oscuro/misterioso
Descripcion: 2-3 oraciones texto puro (SIN hashtags, tono cinematico)
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4 #Tag5

---

[전용 토픽은 해당 채널 섹션만 작성]
"""


def generate_weekly_topics(start_date: datetime, days: int = 7,
                           llm_provider: str | None = None) -> dict[str, Any]:
    """주간 토픽 생성 — 성과 분석 + LLM 전문가.

    llm_provider: "openai" | "gemini" | None (자동 — OPENAI_API_KEY 있으면 openai, 없으면 gemini)
    env TOPIC_LLM_MODEL: 모델 오버라이드 (예: gpt-5.4, gemini-2.5-pro)
    """
    # 프로바이더 자동 결정
    if llm_provider is None:
        llm_provider = "openai" if os.getenv("OPENAI_API_KEY") else "gemini"

    # 1. 컨텍스트 수집
    performance = _get_performance_context()
    used_topics = _get_used_topics()
    hit_patterns = _analyze_hit_patterns()
    last_day = _get_last_day_number()
    fresh_discovery_context = _get_fresh_discovery_context()

    # 2. LLM 프롬프트 구성
    user_prompt, date_range = _build_topic_generation_request(
        start_date,
        days,
        performance,
        used_topics,
        hit_patterns,
        last_day,
        fresh_discovery_context=fresh_discovery_context,
    )

    # 3. LLM 호출
    _topic_model = os.getenv(
        "TOPIC_LLM_MODEL",
        "gpt-5.4" if llm_provider == "openai" else "gemini-2.5-flash",
    )
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

    # 4. 출력 검증 + 하드게이트 자동 수리 + Day 파일 저장
    repair_attempts = int(os.getenv("TOPIC_HARD_REPAIR_ATTEMPTS", "3"))
    repair_model = os.getenv("TOPIC_REPAIR_LLM_MODEL", _topic_model)
    validation_errors, hard_errors = _collect_generation_validation(raw_content, used_topics, date_range)
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
- 하드게이트 실패 목록에 등장하지 않은 유효한 토픽은 가능한 한 그대로 유지하라.
- 중복으로 지목된 토픽만 완전히 새 소재로 교체하라.
- "추가 토픽" 섹션을 만들지 말고, 중복 소재는 완전히 다른 소재로 교체하라.
- 시의성 0개인 Day는 실제 발견/관측/연구 발표형 토픽 1개를 새로 넣거나, 이미 발견형 근거가 있는 토픽 1개에만 [시의성] 태그를 붙여라.
- 하루 [시의성] 태그는 1~2개만 허용한다.
- 하루 3개 전부 [시의성]이면 최소 1개는 에버그린/교과서형 강한 훅으로 바꾸거나 [시의성] 태그를 제거하라.
- 기존 사용 토픽/소재와 같은 팩트는 제목을 바꿔도 실패다.
- 각 Hashtags/해시태그 라인은 최대 5개만 쓰고, shorts/short/쇼츠 태그는 절대 쓰지 마라.
- Description/설명 본문에는 # 문자를 절대 넣지 마라. 해시태그는 해시태그 필드에만 둔다.
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
            validation_errors, hard_errors = _collect_generation_validation(raw_content, used_topics, date_range)
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

        filename = f"Day {day_num} ({date_str}).md"
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
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
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
