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
from datetime import datetime, timedelta
from typing import Any

# Day 파일 저장 경로
DAY_FILES_DIR = os.getenv(
    "DAY_FILES_DIR",
    r"C:\Users\Storm Credit\Desktop\쇼츠\askanything",
)

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
    return errors


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

## 카테고리 목록 (성과 데이터 기반)
★ 성과 검증됨 (우선 배정):
  심해/바다 (전 채널 1-2위), 우주/행성 (KO 최강), 공룡/고생물 (ES 강세),
  지구/자연 (안정적 중위), 동물 (KO 강세)
☆ 신규 테스트 (15% 할당):
  역사/문명, 물리/화학, 기술/공학, 인체/심리

## 카테고리 분산 규칙
- 주간 21토픽 중 성과 검증 카테고리 70% + 신규 테스트 15% + 히트 복제 15%
- 같은 카테고리 연속 2일 금지
- 하루 3개 토픽 내 카테고리 겹침 금지
- 인체/심리는 EN에서 약세 — EMOTIONAL_SCI 포맷으로만 사용

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
- 5-6개
- 구성: 대형태그 2개 + 중형 2개 + 토픽고유 1-2개
- 채널 언어만 사용 (언어 혼용 금지)
- KO 예: #쇼츠 #과학 #우주미스터리 #명왕성 #행성비밀
- EN 예: #Shorts #Science #SpaceFacts #PlutoHeart #SpaceMystery

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
- 대신 시의성 있는 에버그린 토픽을 사용:
  예: 계절 관련(봄 알레르기 과학), 반복 뉴스 사이클(화산, 지진, 우주 발사 일정)
- [시의성]으로 표시 ([트렌딩] 아님)

## ★ 콘텐츠 포맷 자동 판단 규칙 (11종)
주제를 선정한 뒤, 주제 성격을 보고 포맷을 결정한다. 포맷을 먼저 정하고 주제를 끼워맞추지 마라.

포맷 판단 기준:
- [포맷:WHO_WINS]: 두 대상 비교가 자연스러운 주제 (11컷 대결)
  → 신호: "vs", "더 강한", "누가", "이길까", 두 개체 대결 구도
  → 예: "태양 vs 블랙홀", "공룡 vs 현대 탱크", "번개 vs 화산"
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

- [포맷:FUTURE_VISION]: 미래 예측/기술 전망 주제 (8-10컷 미래예측)
  → 신호: "미래", "2050년", "앞으로", "기술 발전", "언젠가"
  → 예: "2050년 인류", "AI가 의사를 대체하면", "화성 이주 타임라인"
  → 주간 1-2개

- [포맷:TIMELAPSE_HISTORY]: 시간 흐름/역사 변천 주제 (8-10컷 역사)
  → 신호: "역사", "변천", "진화", "~년 전", "과거부터 현재"
  → 예: "지구 46억년 역사", "인류 식량의 진화", "의학 5000년"
  → 주간 1-2개

- [포맷:PARADOX]: 통념 뒤집기/역설 주제 (7-8컷 역설)
  → 신호: "사실은", "반대로", "알고 보면", "역설", "진짜 이유"
  → 예: "물이 사실 독인 이유", "어둠은 존재하지 않는다", "뜨거운 물이 먼저 어는 이유"
  → 주간 1-2개

- [포맷:MYSTERY]: 미스터리/미해결 주제 (8-9컷 미스터리)
  → 신호: "미스터리", "설명 불가", "아직도 모른다", "비밀", "수수께끼"
  → 예: "바다 심해 미확인 소리", "보이니치 문서", "나스카 라인의 비밀"
  → 주간 1-2개

- [포맷:RANKING_DEBATE]: 논쟁형 랭킹/토론 주제 (9-10컷 논쟁)
  → 신호: "진짜 1위는", "최강", "논란", "의견 갈림", "결국 누가"
  → 예: "역대 최강 공룡 진짜 1위", "가장 위험한 화산 논쟁", "최고의 발명품 랭킹"
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

## 1. 이모지 토픽제목 [공통] [포맷:WHO_WINS] [시리즈:시리즈명(선택)]
> 근거: [카테고리: 교과서] — 핵심 팩트
> 검색 키워드: "english search terms"
> 채널: askanything, wonderdrop, exploratodo, prismtale
> 핵심 훅: 1문장 훅 (주제 성격에 맞게)
> 훅 패턴: ①~⑦ 중 선택

### askanything (ko)
제목: 한국어 제목
설명: 2~3문장 (검색 키워드 포함)
해시태그: #태그1 #태그2 #태그3 #태그4 #태그5

### wonderdrop (en)
Title: English title
Description: 2-3 sentences with searchable keywords
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4 #Tag5

### exploratodo (es-LATAM)
Titulo: Titulo en español
Descripcion: 2-3 oraciones con palabras clave
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4 #Tag5

### prismtale (es-US)
Titulo: Titulo oscuro/misterioso
Descripcion: 2-3 oraciones con tono cinematico
Hashtags: #Tag1 #Tag2 #Tag3 #Tag4 #Tag5

---

[전용 토픽은 해당 채널 섹션만 작성]
"""


def generate_weekly_topics(start_date: datetime, days: int = 7,
                           llm_provider: str = "gemini") -> dict[str, Any]:
    """주간 토픽 생성 — 성과 분석 + LLM 전문가."""
    from modules.utils.keys import get_google_key

    # 1. 컨텍스트 수집
    performance = _get_performance_context()
    used_topics = _get_used_topics()
    hit_patterns = _analyze_hit_patterns()
    last_day = _get_last_day_number()

    # 2. LLM 프롬프트 구성
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

## 이미 사용된 토픽 (중복 금지 — 제목이 다르더라도 같은 팩트면 중복)
{chr(10).join(f'- {t}' for t in used_topics)}

## 요청
- 하루 3개 토픽 × {days}일 = {3 * days}개 (전부 [공통])
- 모든 주제에 [포맷:XXX] 태그 필수 — 주제 성격 보고 자동 판단 (11종)
- 하루 3토픽은 서로 다른 포맷 사용 (같은 포맷 2개 연속 금지)
- WHO_WINS: 자연스러운 대결 구도 주제만, 억지 비교 금지
- EMOTIONAL_SCI: 인체/심리/감성 주제만 (우주/자연 팩트에 강제 적용 금지)
- COUNTDOWN/RANKING_DEBATE: 순위 주제는 둘 중 더 맞는 포맷 선택 (논쟁형→RANKING_DEBATE, 순수 리스트→COUNTDOWN)
- PARADOX: 통념 뒤집기 주제만, 일반 팩트에 억지 적용 금지
- 히트 패턴 복제 토픽: 주당 3-4개
- 역사/문화 토픽 주당 최소 2개 포함
- 출처에 논문명 지어내지 말 것 — 검색 키워드로 검증 가능하게
- 카테고리 분산: 하루 3토픽 내 겹침 금지, 주간 최소 6개 카테고리
"""

    full_prompt = TOPIC_EXPERT_PROMPT + "\n\n" + user_prompt

    # 3. LLM 호출
    print(f"[토픽 생성] {days}일분 토픽 생성 중...")
    api_key = get_google_key(None, service="gemini")

    try:
        from google.genai import types
        from modules.utils.gemini_client import create_gemini_client

        client = create_gemini_client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config={
                "temperature": 0.5,  # 팩트 정확도 우선 (0.8→0.5)
                "max_output_tokens": 30000,
                "http_options": types.HttpOptions(timeout=120_000),
            },
        )
        raw_content = (response.text or "").strip()
    except Exception as e:
        return {"success": False, "error": f"LLM 호출 실패: {e}"}

    if not raw_content:
        return {"success": False, "error": "LLM 응답 비어있음"}

    # 4. 출력 검증 + Day 파일 저장
    saved_files = []
    validation_errors = []
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
        date_str = header_match.group(2)

        # 블록 검증
        block_errors = _validate_day_block(block, day_num)
        if block_errors:
            validation_errors.extend([f"Day {day_num}: {e}" for e in block_errors])
            print(f"  ⚠️ Day {day_num} 검증 경고: {block_errors}")
            # 경고만 — 저장은 진행 (사람이 검수)

        filename = f"Day {day_num} ({date_str}).md"
        filepath = os.path.join(DAY_FILES_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(block)
        saved_files.append(filename)
        print(f"  [토픽 생성] {filename} 저장 완료")

    # 5. 텔레그램 알림
    try:
        from modules.utils.notify import _send
        topic_count = raw_content.count("## ")
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
        "topic_count": raw_content.count("## "),
        "validation_errors": validation_errors,
    }
