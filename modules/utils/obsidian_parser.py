"""옵시디언 Day 파일 파서 — Day 마크다운을 batch job 리스트로 변환

Day 파일 구조:
  ## 1. 🌌 주제명
  ### askanything (ko)
  - **제목**: ...
  - **설명**: ...
  - **해시태그**: ...
  ### wonderdrop (en)
  - **Title**: ...
  ...

파싱 결과: 주제별 4채널 → batch job dict 리스트
"""
import os
import re
import glob
from datetime import datetime, timedelta
from typing import Any


# 채널 → 언어 매핑
CHANNEL_LANG_MAP = {
    "askanything": "ko",
    "wonderdrop": "en",
    "exploratodo": "es",
    "prismtale": "es",
}

# 태그 → 대상 채널 매핑
TAG_CHANNEL_MAP = {
    "공통": ["askanything", "wonderdrop", "exploratodo", "prismtale"],
    "KO전용": ["askanything"],
    "EN전용": ["wonderdrop"],
    "ES전용": ["exploratodo", "prismtale"],
    "ES-US전용": ["prismtale"],
    "ES-LATAM전용": ["exploratodo"],
}

# 태그 추출 정규식
TAG_RE = re.compile(r"\[(공통|KO전용|EN전용|ES전용|ES-US전용|ES-LATAM전용)\]")

# 포맷 태그 추출 정규식: [포맷:WHO_WINS], [포맷:IF], [포맷:EMOTIONAL_SCI], [포맷:FACT] 등 11종
FORMAT_TAG_RE = re.compile(r"\[포맷:([A-Z_]+)\]")
# 시리즈 태그 추출 정규식: [시리즈:공룡대전], [시리즈:심해탐험] 등
SERIES_TAG_RE = re.compile(r"\[시리즈:([^\]]+)\]")

# Day 파일 기본 경로 (도커: /app/obsidian, 로컬: Windows 경로)
DEFAULT_VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH", "/app/obsidian")
if not os.path.exists(DEFAULT_VAULT_PATH):
    DEFAULT_VAULT_PATH = r"C:\Users\Storm Credit\Desktop\쇼츠\askanything"


def _extract_cuts(lines: list[str]) -> list[dict[str, str]]:
    """라인 리스트에서 8컷 스크립트+이미지 프롬프트를 추출합니다.
    포맷: 컷1 / script: ... / image_prompt: ... 또는 Cut1 / Corte1
    """
    cuts = []
    current_cut: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        # 컷 시작 감지: 컷1, Cut1, Corte1 등
        if re.match(r"^(컷|Cut|Corte)\s*\d+", stripped, re.IGNORECASE):
            if current_cut.get("script"):
                cuts.append(current_cut)
            current_cut = {}
            continue
        # script 라인
        m = re.match(r"^script:\s*(.+)", stripped, re.IGNORECASE)
        if m:
            current_cut["script"] = m.group(1).strip()
            continue
        # image_prompt 라인
        m = re.match(r"^image_prompt:\s*(.+)", stripped, re.IGNORECASE)
        if m:
            current_cut["image_prompt"] = m.group(1).strip()
            continue
    # 마지막 컷
    if current_cut.get("script"):
        cuts.append(current_cut)
    return cuts


def _extract_field(lines: list[str], field_names: list[str]) -> str:
    """라인 리스트에서 특정 필드 값을 추출합니다.
    두 가지 포맷 지원:
      - **제목**: 값  (볼드 마크다운)
      제목: 값         (플레인 텍스트)
    """
    for line in lines:
        for name in field_names:
            # 포맷 1: - **필드명**: 값
            pattern1 = rf"^\s*-\s*\*\*{re.escape(name)}\*\*:\s*(.+)"
            m = re.match(pattern1, line)
            if m:
                return m.group(1).strip()
            # 포맷 2: 필드명: 값 (볼드 없이)
            pattern2 = rf"^\s*{re.escape(name)}:\s*(.+)"
            m = re.match(pattern2, line)
            if m:
                return m.group(1).strip()
    return ""


def parse_day_file(file_path: str) -> list[dict[str, Any]]:
    """Day 마크다운 파일을 파싱하여 batch job 리스트로 반환합니다.

    Args:
        file_path: Day XX (M-DD).md 파일 경로

    Returns:
        list of dicts, 각각 batch job 포맷:
        {
            "topic": str,          # 채널별 제목 (topic으로 사용)
            "language": str,       # ko/en/es
            "channel": str,        # askanything/wonderdrop/exploratodo/prismtale
            "title": str,          # Day 파일의 제목
            "description": str,    # Day 파일의 설명
            "hashtags": str,       # Day 파일의 해시태그
            "topic_group": str,    # 원본 주제명 (4채널 그룹핑용)
            "day_file": str,       # 원본 파일명
        }
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Day 파일을 찾을 수 없습니다: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    jobs = []
    day_filename = os.path.basename(file_path)

    # 주제별 섹션 분리: ## 1. ~ ## 2. ~ ...
    topic_sections = re.split(r"(?=^## \d+\.)", content, flags=re.MULTILINE)

    for section in topic_sections:
        # 주제 헤더 추출
        topic_match = re.match(r"^## (\d+)\.\s*(.+)", section)
        if not topic_match:
            continue

        topic_num = topic_match.group(1)
        topic_name_raw = topic_match.group(2).strip()

        # 태그 추출: [공통], [KO전용] 등
        tag_match = TAG_RE.search(topic_name_raw)
        topic_tag = tag_match.group(1) if tag_match else "공통"
        # 포맷 태그 추출: [포맷:WHO_WINS] 등
        format_match = FORMAT_TAG_RE.search(topic_name_raw)
        format_type = format_match.group(1) if format_match else "FACT"
        # 시리즈 태그 추출: [시리즈:공룡대전] 등
        series_match = SERIES_TAG_RE.search(topic_name_raw)
        series_title = series_match.group(1) if series_match else None
        # 태그 제거 후 순수 주제명
        topic_name = TAG_RE.sub("", topic_name_raw)
        topic_name = FORMAT_TAG_RE.sub("", topic_name)
        topic_name = SERIES_TAG_RE.sub("", topic_name).strip()
        allowed_channels = TAG_CHANNEL_MAP.get(topic_tag, TAG_CHANNEL_MAP["공통"])

        # 뉴스 주제(5번)는 스킵 — "직접 입력" 플레이스홀더
        if "직접 입력" in section or "Enter news" in section or "Ingresa tema" in section:
            continue

        # 채널별 섹션 분리
        channel_sections = re.split(r"(?=^### )", section, flags=re.MULTILINE)

        has_channel_sections = any(
            re.match(r"^### (\w+)\s*\(([^)]+)\)", cs) for cs in channel_sections
        )

        if has_channel_sections:
            # 풀 Day 파일: 채널별 스크립트+이미지 포함
            for ch_section in channel_sections:
                ch_match = re.match(r"^### (\w+)\s*\(([^)]+)\)", ch_section)
                if not ch_match:
                    continue

                channel_name = ch_match.group(1).strip().lower()

                if channel_name not in CHANNEL_LANG_MAP:
                    continue

                if channel_name not in allowed_channels:
                    continue

                language = CHANNEL_LANG_MAP[channel_name]
                lines = ch_section.split("\n")

                title = _extract_field(lines, ["제목", "Title", "Título", "Titulo"])
                description = _extract_field(lines, ["설명", "Description", "Descripción", "Descripcion"])
                hashtags = _extract_field(lines, ["해시태그", "Hashtags"])

                if not title:
                    continue

                cuts = _extract_cuts(lines)

                jobs.append({
                    "topic": title,
                    "language": language,
                    "channel": channel_name,
                    "title": title,
                    "description": description,
                    "hashtags": hashtags,
                    "cuts": cuts,
                    "topic_group": topic_name,
                    "topic_tag": topic_tag,
                    "format_type": format_type,
                    "series_title": series_title,
                    "day_file": day_filename,
                    "source_file": day_filename,
                    "source_section": f"Topic {topic_num}",
                    "source_channel_block": f"{channel_name} ({language})",
                    "imported_at": datetime.now().isoformat(),
                })
        else:
            # 주제 전용 Day 파일 (v6): 채널 섹션 없음, 주제명+훅만 있음
            # → 태그 기반으로 대상 채널 자동 배정, 스크립트는 cutter.py가 생성
            lines = section.split("\n")
            # "핵심 훅" 추출
            hook = ""
            for line in lines:
                m = re.match(r">\s*핵심 훅:\s*(.+)", line)
                if m:
                    hook = m.group(1).strip()
                    break

            for channel_name in allowed_channels:
                language = CHANNEL_LANG_MAP[channel_name]
                jobs.append({
                    "topic": topic_name,  # 주제명을 topic으로
                    "language": language,
                    "channel": channel_name,
                    "title": topic_name,
                    "description": hook,
                    "hashtags": "",
                    "cuts": [],  # 스크립트 없음 → cutter.py가 생성
                    "topic_group": topic_name,
                    "topic_tag": topic_tag,
                    "format_type": format_type,
                    "series_title": series_title,
                    "day_file": day_filename,
                    "source_file": day_filename,
                    "source_section": f"Topic {topic_num}",
                    "source_channel_block": f"auto ({topic_tag})",
                    "imported_at": datetime.now().isoformat(),
                })

    return jobs


def find_day_file_by_date(target_date: datetime | None = None,
                          vault_path: str = DEFAULT_VAULT_PATH) -> str | None:
    """날짜로 Day 파일을 찾습니다.

    Args:
        target_date: 찾을 날짜 (None이면 오늘 KST)
        vault_path: 옵시디언 볼트 경로

    Returns:
        파일 경로 또는 None
    """
    if target_date is None:
        # Docker UTC → KST 보정 (UTC+9)
        from datetime import timezone, timedelta
        KST = timezone(timedelta(hours=9))
        target_date = datetime.now(KST)

    # Day 파일명 패턴: Day XX (M-DD).md
    month = target_date.month
    day = target_date.day
    date_pattern = f"({month}-{day})"

    for f in glob.glob(os.path.join(vault_path, "Day *.md")):
        if date_pattern in f:
            return f

    return None


def find_today_file(vault_path: str = DEFAULT_VAULT_PATH) -> str | None:
    """오늘 날짜의 Day 파일을 찾습니다 (KST 기준)."""
    return find_day_file_by_date(None, vault_path)  # None이면 KST 자동


def parse_today(vault_path: str = DEFAULT_VAULT_PATH) -> list[dict[str, Any]]:
    """오늘의 Day 파일을 파싱합니다."""
    path = find_today_file(vault_path)
    if not path:
        return []
    return parse_day_file(path)


def get_today_topics(channel: str | None = None,
                     vault_path: str = DEFAULT_VAULT_PATH,
                     target_date: Any = None) -> dict[str, Any]:
    """Day 파일에서 채널별 주제를 반환합니다.

    Args:
        channel: 특정 채널만 필터 (None이면 전체)
        vault_path: 옵시디언 볼트 경로
        target_date: 특정 날짜 (None이면 오늘)

    Returns:
        {"file": str, "topics": list[dict]} — 주제 그룹별 채널 데이터
    """
    if target_date:
        path = find_day_file_by_date(target_date, vault_path)
    else:
        path = find_today_file(vault_path)
    if not path:
        return {"file": None, "file_path": None, "topics": []}

    jobs = parse_day_file(path)

    if channel:
        jobs = [j for j in jobs if j["channel"] == channel]

    # topic_group별로 그룹핑
    groups: dict[str, dict] = {}
    for j in jobs:
        key = j["topic_group"]
        if key not in groups:
            groups[key] = {
                "topic_group": key,
                "topic_tag": j.get("topic_tag", "공통"),
                "format_type": j.get("format_type", "FACT"),
                "series_title": j.get("series_title"),
                "channels": {},
            }
        groups[key]["channels"][j["channel"]] = {
            "title": j["title"],
            "description": j["description"],
            "hashtags": j["hashtags"],
            "cuts": j.get("cuts", []),
        }

    return {
        "file": os.path.basename(path),
        "file_path": path,
        "topics": list(groups.values()),
    }


def list_day_files(vault_path: str = DEFAULT_VAULT_PATH) -> list[str]:
    """볼트의 모든 Day 파일 목록을 반환합니다."""
    files = glob.glob(os.path.join(vault_path, "Day *.md"))
    return sorted(files)


def tick_topic_done(file_path: str, topic_group: str) -> bool:
    """Day 파일에서 topic_group 섹션 헤더에 ✅ 마크 추가.

    ## N. 주제명  →  ## N. ✅ 주제명

    Args:
        file_path: Day 파일 전체 경로
        topic_group: topic_group 명 (순수 주제명, 태그 제외)

    Returns:
        True if updated, False if already marked or not found
    """
    if not os.path.exists(file_path):
        return False
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # topic_group을 포함하는 ## N. ... 헤더 찾기 (이미 ✅ 있으면 스킵)
    pattern = re.compile(
        r"^(## \d+\.\s*)(?!✅)([^\n]*" + re.escape(topic_group[:20]) + r"[^\n]*)",
        re.MULTILINE,
    )
    match = pattern.search(content)
    if not match:
        return False

    updated = content[:match.start()] + match.group(1) + "✅ " + match.group(2) + content[match.end():]
    import tempfile
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(file_path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(updated)
    os.replace(tmp_path, file_path)
    return True
