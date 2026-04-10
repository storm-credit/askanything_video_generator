"""성과 분석 엔진 — 톤 변경 A/B 추적, 트렌드 감지, 훅 패턴 분석.

핵심 기능:
  1. 스냅샷: 현재 성과 기준선 저장 (before/after 비교용)
  2. 일별 트렌드: 조회수 추이 → 하락 감지
  3. 훅 패턴 분석: 제목 패턴별 평균 조회
  4. 감정 태그 성과: 태그별 평균 조회
  5. 교차 채널 비교: 같은 토픽의 채널별 성과

사용:
  POST /api/analytics/snapshot — 현재 성과 스냅샷
  GET  /api/analytics/trend/{channel} — 일별 트렌드
  GET  /api/analytics/compare — before/after 비교
  GET  /api/analytics/hooks/{channel} — 훅 패턴 분석
  GET  /api/analytics/cross-channel — 교차 채널 비교
  GET  /api/analytics/tone-report — 톤 변경 영향 리포트
"""
import os
import json
import re
from datetime import datetime, timedelta
from typing import Any

from modules.utils.youtube_stats import fetch_channel_stats, fetch_all_channels_stats, get_cached_stats


# ── 저장 경로 ──
ANALYTICS_DIR = os.path.join("assets", "_analytics")
SNAPSHOTS_DIR = os.path.join(ANALYTICS_DIR, "snapshots")
DAILY_DIR = os.path.join(ANALYTICS_DIR, "daily")


def _ensure_dirs():
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    os.makedirs(DAILY_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# 1. 스냅샷 — 현재 성과 기준선 저장
# ═══════════════════════════════════════════════════════════════

def take_snapshot(label: str = "auto", refresh: bool = True) -> dict[str, Any]:
    """현재 4채널 성과 스냅샷 저장.

    Args:
        label: 스냅샷 라벨 (예: "before_tone_change", "after_tone_v2")
        refresh: True면 YouTube API 호출, False면 캐시 사용
    """
    _ensure_dirs()
    timestamp = datetime.now().isoformat()
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    if refresh:
        all_stats = fetch_all_channels_stats()
    else:
        all_stats = {}
        for ch in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
            cached = get_cached_stats(ch)
            if cached:
                all_stats[ch] = cached
            else:
                all_stats[ch] = fetch_channel_stats(ch)

    snapshot = {
        "label": label,
        "timestamp": timestamp,
        "channels": {},
    }

    for ch, data in all_stats.items():
        s = data.get("summary", {})
        videos = data.get("videos", [])

        # 최근 7일 영상만 분리
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        recent = [v for v in videos if v.get("published_at", "") >= week_ago]

        # 최근 3일 영상 (톤 변경 직후 감지용)
        three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
        very_recent = [v for v in videos if v.get("published_at", "") >= three_days_ago]

        snapshot["channels"][ch] = {
            "total_videos": s.get("total_videos", 0),
            "total_views": s.get("total_views", 0),
            "avg_views": s.get("avg_views", 0),
            "recent_7d_views": s.get("recent_7d_views", 0),
            "recent_7d_count": len(recent),
            "recent_7d_avg": round(sum(v.get("views", 0) for v in recent) / max(len(recent), 1)),
            "recent_3d_views": sum(v.get("views", 0) for v in very_recent),
            "recent_3d_count": len(very_recent),
            "recent_3d_avg": round(sum(v.get("views", 0) for v in very_recent) / max(len(very_recent), 1)),
            "top_5": s.get("top_5", []),
            "videos": videos,
        }

    # 저장
    path = os.path.join(SNAPSHOTS_DIR, f"{date_str}_{label}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"[Analytics] 스냅샷 저장: {path}")
    return snapshot


def list_snapshots() -> list[dict]:
    """저장된 스냅샷 목록."""
    _ensure_dirs()
    results = []
    for fname in sorted(os.listdir(SNAPSHOTS_DIR)):
        if fname.endswith(".json"):
            path = os.path.join(SNAPSHOTS_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append({
                    "file": fname,
                    "label": data.get("label", ""),
                    "timestamp": data.get("timestamp", ""),
                    "channels": list(data.get("channels", {}).keys()),
                })
            except Exception:
                pass
    return results


def compare_snapshots(before_label: str = None, after_label: str = None) -> dict[str, Any]:
    """두 스냅샷 비교. label 미지정 시 가장 오래된 것과 가장 최근 것 비교."""
    _ensure_dirs()
    files = sorted([f for f in os.listdir(SNAPSHOTS_DIR) if f.endswith(".json")])
    if len(files) < 2:
        return {"error": "최소 2개 스냅샷이 필요합니다", "snapshots": len(files)}

    def _load(label_or_idx):
        if isinstance(label_or_idx, int):
            path = os.path.join(SNAPSHOTS_DIR, files[label_or_idx])
        else:
            matches = [f for f in files if label_or_idx in f]
            if not matches:
                return None
            path = os.path.join(SNAPSHOTS_DIR, matches[-1])
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    before = _load(before_label if before_label else 0)
    after = _load(after_label if after_label else -1)

    if not before or not after:
        return {"error": "스냅샷을 찾을 수 없습니다"}

    comparison = {
        "before": {"label": before["label"], "timestamp": before["timestamp"]},
        "after": {"label": after["label"], "timestamp": after["timestamp"]},
        "channels": {},
    }

    for ch in after.get("channels", {}):
        b = before.get("channels", {}).get(ch, {})
        a = after["channels"][ch]

        b_avg = b.get("recent_7d_avg", b.get("avg_views", 0))
        a_avg = a.get("recent_7d_avg", a.get("avg_views", 0))

        change_pct = round((a_avg - b_avg) / max(b_avg, 1) * 100, 1)

        status = "stable"
        if change_pct >= 15:
            status = "growing"
        elif change_pct <= -20:
            status = "dropping"
        elif change_pct <= -10:
            status = "warning"

        comparison["channels"][ch] = {
            "before_7d_avg": b_avg,
            "after_7d_avg": a_avg,
            "change_pct": change_pct,
            "status": status,
            "before_3d_avg": b.get("recent_3d_avg", 0),
            "after_3d_avg": a.get("recent_3d_avg", 0),
        }

    return comparison


# ═══════════════════════════════════════════════════════════════
# 2. 일별 트렌드
# ═══════════════════════════════════════════════════════════════

def record_daily(channel: str = None) -> dict[str, Any]:
    """오늘 날짜 일별 기록 저장."""
    _ensure_dirs()
    today = datetime.now().strftime("%Y-%m-%d")

    channels = [channel] if channel else ["askanything", "wonderdrop", "exploratodo", "prismtale"]
    daily_path = os.path.join(DAILY_DIR, f"{today}.json")

    # 기존 기록 로드
    existing = {}
    if os.path.exists(daily_path):
        with open(daily_path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    for ch in channels:
        stats = fetch_channel_stats(ch)
        s = stats.get("summary", {})
        existing[ch] = {
            "total_views": s.get("total_views", 0),
            "avg_views": s.get("avg_views", 0),
            "recent_7d_views": s.get("recent_7d_views", 0),
            "total_videos": s.get("total_videos", 0),
            "recorded_at": datetime.now().isoformat(),
        }

    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return existing


def get_daily_trend(channel: str, days: int = 14) -> list[dict]:
    """최근 N일간 일별 트렌드."""
    _ensure_dirs()
    trend = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        path = os.path.join(DAILY_DIR, f"{date}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if channel in data:
                trend.append({"date": date, **data[channel]})

    return trend


# ═══════════════════════════════════════════════════════════════
# 3. 훅 패턴 분석 — 제목 패턴별 평균 조회
# ═══════════════════════════════════════════════════════════════

# 훅 패턴 분류 규칙
HOOK_PATTERNS = {
    "question": {
        "ko": [r"\?$", r"있다\?", r"일까\?", r"인가\?", r"한다\?"],
        "en": [r"\?$", r"^Can ", r"^Is ", r"^What ", r"^How ", r"^Why "],
        "es": [r"\?$", r"^¿"],
    },
    "negation_reveal": {
        "ko": [r"아니다", r"아니야", r"없다", r"못한다", r"않는다"],
        "en": [r"Not ", r"Never ", r"Wasn't", r"Can't", r"Don't"],
        "es": [r"No ", r"Nunca ", r"Nadie"],
    },
    "number_shock": {
        "ko": [r"\d+배", r"\d+억", r"\d+만", r"\d+도", r"\d+%"],
        "en": [r"\d+ Times", r"\d+ Million", r"\d+ Billion", r"\d+%", r"\d+,\d+"],
        "es": [r"\d+ veces", r"\d+ millones", r"\d+%"],
    },
    "hidden_secret": {
        "ko": [r"숨겨진", r"비밀", r"정체", r"몰랐", r"사실은"],
        "en": [r"Hidden", r"Secret", r"Actually", r"Truth"],
        "es": [r"[Oo]culto", r"[Ss]ecreto", r"[Mm]isterio", r"[Vv]erdad"],
    },
    "superlative": {
        "ko": [r"가장", r"최초", r"최대", r"최강", r"역대"],
        "en": [r"Most ", r"Largest", r"First ", r"Oldest", r"Biggest"],
        "es": [r"[Mm]ás ", r"[Mm]ayor", r"[Pp]rimero"],
    },
    "comparison": {
        "ko": [r"vs", r" 대 ", r"보다", r"더 [큰작강약]", r"이길까", r"누가"],
        "en": [r"[Vv]s\.?", r"[Cc]ompare", r"[Bb]igger", r"[Ss]tronger", r"[Bb]etter"],
        "es": [r"[Vv]s\.?", r"[Cc]ompara", r"[Mm]ejor", r"[Mm]ás fuerte"],
    },
    "sensory": {
        "ko": [r"냄새", r"소리", r"느낌", r"맛이", r"온도", r"만지면"],
        "en": [r"[Ss]mell", r"[Ss]ound", r"[Ff]eel", r"[Tt]aste", r"[Tt]ouch"],
        "es": [r"[Oo]lor", r"[Ss]onido", r"[Ss]iente", r"[Ss]abor", r"[Tt]ocar"],
    },
}


def _classify_hook(title: str, lang: str) -> list[str]:
    """제목에서 훅 패턴 분류."""
    patterns = []
    for pattern_name, lang_patterns in HOOK_PATTERNS.items():
        regexes = lang_patterns.get(lang, lang_patterns.get("en", []))
        for regex in regexes:
            if re.search(regex, title):
                patterns.append(pattern_name)
                break
    return patterns if patterns else ["other"]


def _detect_lang(channel: str) -> str:
    lang_map = {"askanything": "ko", "wonderdrop": "en", "exploratodo": "es", "prismtale": "es"}
    return lang_map.get(channel, "en")


def analyze_hook_patterns(channel: str = None, refresh: bool = False) -> dict[str, Any]:
    """훅 패턴별 평균 조회수 분석."""
    channels = [channel] if channel else ["askanything", "wonderdrop", "exploratodo", "prismtale"]
    results = {}

    for ch in channels:
        if refresh:
            data = fetch_channel_stats(ch)
        else:
            data = get_cached_stats(ch) or fetch_channel_stats(ch)

        videos = data.get("videos", [])
        lang = _detect_lang(ch)

        pattern_stats: dict[str, list[int]] = {}
        for v in videos:
            title = v.get("title", "")
            views = v.get("views", 0)
            hooks = _classify_hook(title, lang)
            for h in hooks:
                pattern_stats.setdefault(h, []).append(views)

        # 평균 + 영상 수
        pattern_summary = {}
        for pattern, view_list in sorted(pattern_stats.items(), key=lambda x: -sum(x[1]) / max(len(x[1]), 1)):
            avg = round(sum(view_list) / len(view_list))
            pattern_summary[pattern] = {
                "avg_views": avg,
                "count": len(view_list),
                "max_views": max(view_list) if view_list else 0,
                "min_views": min(view_list) if view_list else 0,
            }

        results[ch] = pattern_summary

    return results


# ═══════════════════════════════════════════════════════════════
# 4. 교차 채널 비교 — 같은 토픽의 채널별 성과
# ═══════════════════════════════════════════════════════════════

# 토픽 키워드 정규화 (다국어 제목 → 공통 키워드)
TOPIC_KEYWORDS = {
    "saturn_rings": ["토성 고리", "Saturn's Rings", "Anillos de Saturno"],
    "t_rex_arms": ["티라노 팔", "T. Rex Arms", "T-Rex", "brazos del T-Rex"],
    "deep_sea_pressure": ["심해", "Deep Sea", "Deep Ocean", "profund"],
    "moon_distance": ["달이 멀어", "Moon.*Moving Away", "Luna.*alej"],
    "honey_tomb": ["꿀.*무덤", "Honey.*Tomb", "Miel.*tumba"],
    "sunlight_escape": ["햇빛.*갇", "Sunlight.*Escape", "Luz.*escape", "170,000"],
    "pluto_heart": ["명왕성.*하트", "Pluto.*Heart", "Plutón.*corazón"],
    "magnetic_field": ["자기장", "Magnetic Field", "Campo magnético"],
    "bioluminescence": ["발광", "Bioluminesc", "bioluminiscen"],
}


def _match_topic(title: str) -> str | None:
    """제목에서 공통 토픽 키워드 매칭."""
    for topic_id, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if re.search(kw, title, re.IGNORECASE):
                return topic_id
    return None


def analyze_topic_cross_channel(refresh: bool = False) -> dict[str, Any]:
    """같은 토픽의 채널별 조회수 비교."""
    all_data = {}
    for ch in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
        if refresh:
            data = fetch_channel_stats(ch)
        else:
            data = get_cached_stats(ch) or fetch_channel_stats(ch)
        all_data[ch] = data.get("videos", [])

    # 토픽별 채널 성과 수집
    topic_comparison: dict[str, dict[str, dict]] = {}
    for ch, videos in all_data.items():
        for v in videos:
            topic = _match_topic(v.get("title", ""))
            if topic:
                topic_comparison.setdefault(topic, {})
                topic_comparison[topic][ch] = {
                    "title": v["title"],
                    "views": v.get("views", 0),
                    "published_at": v.get("published_at", ""),
                }

    # 2개 이상 채널에서 나온 토픽만 필터
    cross_topics = {k: v for k, v in topic_comparison.items() if len(v) >= 2}

    return cross_topics


# ═══════════════════════════════════════════════════════════════
# 5. 톤 변경 영향 리포트
# ═══════════════════════════════════════════════════════════════

def get_tone_change_report() -> dict[str, Any]:
    """톤 변경 전후 종합 리포트."""
    snapshots = list_snapshots()
    comparison = compare_snapshots() if len(snapshots) >= 2 else None

    hook_analysis = analyze_hook_patterns()
    cross_channel = analyze_topic_cross_channel()

    # 일별 트렌드 (최근 7일)
    trends = {}
    for ch in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
        trends[ch] = get_daily_trend(ch, days=7)

    report = {
        "generated_at": datetime.now().isoformat(),
        "snapshot_comparison": comparison,
        "hook_patterns": hook_analysis,
        "cross_channel_topics": cross_channel,
        "daily_trends": trends,
        "recommendations": _generate_recommendations(comparison, hook_analysis),
    }

    return report


def _generate_recommendations(comparison: dict | None, hook_analysis: dict) -> list[str]:
    """성과 데이터 기반 자동 추천."""
    recs = []

    if comparison:
        for ch, data in comparison.get("channels", {}).items():
            if data.get("status") == "dropping":
                recs.append(f"⚠️ {ch}: 7일 평균 {data['change_pct']}% 하락 — 톤 변경 롤백 검토")
            elif data.get("status") == "warning":
                recs.append(f"🟡 {ch}: 7일 평균 {data['change_pct']}% 감소 — 모니터링 강화")
            elif data.get("status") == "growing":
                recs.append(f"✅ {ch}: 7일 평균 +{data['change_pct']}% 상승 — 현재 전략 유지")

    # 훅 패턴 추천
    for ch, patterns in hook_analysis.items():
        if patterns:
            best = max(patterns.items(), key=lambda x: x[1].get("avg_views", 0))
            worst = min(patterns.items(), key=lambda x: x[1].get("avg_views", 0))
            if best[1]["avg_views"] > worst[1]["avg_views"] * 2:
                recs.append(f"📊 {ch}: '{best[0]}' 훅이 '{worst[0]}' 대비 {round(best[1]['avg_views']/max(worst[1]['avg_views'],1))}배 성과 → '{best[0]}' 패턴 강화")

    return recs
