"""주간 토픽 자동 생성 — 성과 분석 기반 + LLM 전문가 프롬프트.

흐름:
  1. 성과 데이터 수집 (카테고리별 평균, 훅 패턴별 성과)
  2. 기존 Day 파일에서 사용한 토픽 추출 (중복 방지)
  3. LLM 토픽 전문가가 7일분 토픽 생성
  4. Day 파일로 저장
  5. 텔레그램으로 검수 요청 알림

사용:
  POST /api/scheduler/generate-topics?start_date=2026-04-16&days=7
"""
import os
import json
import re
from datetime import datetime, timedelta
from typing import Any

# Day 파일 저장 경로
DAY_FILES_DIR = os.getenv(
    "DAY_FILES_DIR",
    r"C:\Users\Storm Credit\Desktop\쇼츠\askanything",
)


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

        # 훅 패턴 성과
        lines.append("\n## 훅 패턴별 평균 조회")
        for ch, patterns in hooks.items():
            lines.append(f"\n### {ch}")
            for pname, pdata in patterns.items():
                lines.append(f"  - {pname}: avg {pdata['avg_views']:,} ({pdata['count']}건)")

        return "\n".join(lines)
    except Exception as e:
        print(f"[토픽 생성] 성과 데이터 로드 실패: {e}")
        return "성과 데이터 없음 — 일반적 바이럴 쇼츠 토픽 전략 사용"


def _get_used_topics() -> list[str]:
    """기존 Day 파일에서 사용된 토픽 목록 추출 (중복 방지)."""
    used = []
    try:
        for fname in os.listdir(DAY_FILES_DIR):
            if fname.startswith("Day") and fname.endswith(".md"):
                path = os.path.join(DAY_FILES_DIR, fname)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                # ## 1. 🌋 하와이섬 성장속도 [공통] 형태에서 토픽 추출
                for m in re.finditer(r"## \d+\.\s+.+?\s+(.+?)\s+\[", content):
                    topic = m.group(1).strip()
                    if topic:
                        used.append(topic)
    except Exception as e:
        print(f"[토픽 생성] 기존 토픽 로드 실패: {e}")
    return used


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
                patterns.append(f"- [{ch}] \"{title}\" ({views:,}뷰) → 훅: {', '.join(hooks)}")

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


TOPIC_EXPERT_PROMPT = """너는 YouTube Shorts 4채널 시스템의 주간 토픽 기획 전문가다.

## 너의 역할
성과 데이터를 분석하고, 다음 주 7일분 토픽(하루 3개 × 7일 = 21개)을 기획한다.

## 채널 정보
- askanything (KO): 한국어, 빠른 반말, 호기심 자극
- wonderdrop (EN): 영어, confident authority 다큐, 시네마틱
- exploratodo (ES-LATAM): 스페인어 LATAM, 에너지 넘침, 빠른 리듬
- prismtale (ES-US): 스페인어 US, 다크 미스터리, 시네마틱

## 토픽 배분 규칙 (채널당 2-3개/일 — 업계 스위트 스팟)
1. 하루 3개 토픽: 공통 2개 + 트렌딩/전용 1개 (교대)
   - 홀수일: 트렌딩 1개 (공통 — 최신 뉴스)
   - 짝수일: 전용 1개 (매일 다른 채널 돌아가며)
2. 채널당 하루 최대 3개 (공통2 + 트렌딩/전용1)
3. 카테고리 배분 (주간 기준):
   - 성과 상위 카테고리: 50% (성과 데이터 참조)
   - 히트 패턴 복제: 20% (아래 규칙 참조)
   - 새 카테고리 테스트: 15% (역사/문화, 기술, 물리 등)
   - 채널 강점 카테고리: 15%

## ★ 히트 패턴 복제 규칙
성과 데이터에서 Top 5 영상을 분석하고, 그 영상이 터진 이유(카테고리 + 훅 유형 + 프레임)를 복제한다.
- 같은 토픽 재사용 ❌ 절대 금지
- 같은 카테고리 + 같은 훅 패턴 + 다른 소재 ✅
예시:
  Top: "하루가 1년보다 긴 행성" (20K views) = 우주/행성 + 숫자비교 훅
  복제: "비가 다이아몬드인 행성" = 같은 카테고리 + 같은 훅 유형 + 다른 팩트 ✅
  복제: "하루가 10분인 별" = 같은 프레임("하루가 X인") + 다른 대상 ✅
  금지: "하루가 1년보다 긴 행성" 다시 사용 ❌

## 토픽 품질 기준
- 팩트 기반: 검증 가능한 출처가 있는 토픽만
- 훅 가능성: "이건 존재하면 안 돼" 수준의 충격/호기심 유발
- 비주얼: AI 이미지로 만들었을 때 시각적으로 강렬한 토픽
- 중복 금지: 아래 기존 토픽 목록과 겹치면 안 됨
- 트렌딩: 최신 뉴스 토픽은 [트렌딩]으로 표시

## 훅 패턴 7가지 (균등 배분)
① 불가능 ② 숫자 앵커 ③ 비교 ④ 카운트다운 ⑤ 도전 ⑥ 부정 ⑦ 감각

## 출력 포맷
각 Day를 아래 형식으로 출력:

# Day NN (M-D)

## 1. 🎯이모지 토픽제목 [공통]
> 근거: 출처명 — 핵심 팩트 1~2문장
> 채널: askanything, wonderdrop, exploratodo, prismtale
> 핵심 훅: 1문장 훅

### askanything (ko)
제목: 한국어 제목 (12자 이내)
설명: 2~3문장
해시태그: #태그1 #태그2 #태그3 #태그4

### wonderdrop (en)
Title: English title (8 words max)
Description: 2-3 sentences
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4

### exploratodo (es-LATAM)
Titulo: Titulo en español (10 palabras max)
Descripcion: 2-3 oraciones
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4

### prismtale (es-US)
Titulo: Titulo oscuro/misterioso (10 palabras max)
Descripcion: 2-3 oraciones con tono cinematico
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4

---

[전용 토픽은 해당 채널 섹션만 작성]
"""


def generate_weekly_topics(start_date: datetime, days: int = 7,
                           llm_provider: str = "gemini") -> dict[str, Any]:
    """주간 토픽 생성 — 성과 분석 + LLM 전문가."""
    from modules.gpt.cutter import _request_gemini_freeform
    from modules.utils.keys import get_google_key

    # 1. 컨텍스트 수집
    performance = _get_performance_context()
    used_topics = _get_used_topics()

    # 2. LLM 프롬프트 구성
    date_range = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        day_num = 16 + i  # Day 16부터 (기존 15일분 이후)
        # 기존 Day 파일에서 마지막 번호 자동 감지
        date_range.append(f"Day {day_num} ({d.month}-{d.day})")

    # 히트 패턴 분석
    hit_patterns = _analyze_hit_patterns()

    # Day 번호 자동 감지 (기존 파일에서 마지막 번호)
    last_day = _get_last_day_number()

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

## 이미 사용된 토픽 (중복 금지)
{chr(10).join(f'- {t}' for t in used_topics[-50:])}

## 요청
- 하루 3개 토픽 × {days}일 = {3 * days}개
- 공통 2개 + 트렌딩/전용 1개 (홀수일=트렌딩, 짝수일=채널전용)
- 히트 패턴 복제 토픽: 주당 4-5개 (Top 영상과 같은 카테고리+훅, 다른 소재)
- 역사/문화 토픽 주당 최소 3개 포함
- 트렌딩 토픽은 [트렌딩]으로 표시
- 모든 토픽에 검증 가능한 출처 포함
"""

    full_prompt = TOPIC_EXPERT_PROMPT + "\n\n" + user_prompt

    # 3. LLM 호출
    print(f"[토픽 생성] {days}일분 토픽 생성 중...")
    api_key = get_google_key(None, service="gemini")

    try:
        # Gemini freeform은 JSON이 아닌 마크다운 반환
        from google.genai import types
        from modules.utils.gemini_client import create_gemini_client

        client = create_gemini_client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config={
                "temperature": 0.8,  # 창의성 높게
                "max_output_tokens": 30000,
                "http_options": types.HttpOptions(timeout=120_000),
            },
        )
        raw_content = (response.text or "").strip()
    except Exception as e:
        return {"success": False, "error": f"LLM 호출 실패: {e}"}

    if not raw_content:
        return {"success": False, "error": "LLM 응답 비어있음"}

    # 4. Day 파일로 분할 저장
    saved_files = []
    day_blocks = re.split(r"(?=# Day \d+)", raw_content)
    for block in day_blocks:
        block = block.strip()
        if not block.startswith("# Day"):
            continue

        # Day 번호, 날짜 추출
        header_match = re.match(r"# Day (\d+) \((\d+-\d+)\)", block)
        if not header_match:
            continue

        day_num = header_match.group(1)
        date_str = header_match.group(2)
        filename = f"Day {day_num} ({date_str}).md"
        filepath = os.path.join(DAY_FILES_DIR, filename)

        # 저장
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(block)
        saved_files.append(filename)
        print(f"  [토픽 생성] {filename} 저장 완료")

    # 5. 텔레그램 알림
    try:
        from modules.utils.notify import _send
        topic_count = raw_content.count("## ")
        file_list = "\n".join(f"  📄 {f}" for f in saved_files)
        _send(
            f"━━━━━━━━━━━━━━━\n"
            f"📝 <b>주간 토픽 생성 완료</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 {days}일분 / 약 {topic_count}개 토픽\n"
            f"{file_list}\n\n"
            f"🔍 <b>검수 필요</b> — 팩트 확인 후 배포 진행\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
    except Exception:
        pass

    return {
        "success": True,
        "days": days,
        "files": saved_files,
        "topic_count": raw_content.count("## "),
    }
