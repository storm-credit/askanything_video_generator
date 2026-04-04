"""주간 성과 자동 반영 — YouTube 통계 → 프롬프트/cutter 채널 데이터 업데이트.

매주 1회 실행:
  1. YouTube API로 4채널 통계 수집
  2. Top 5, 평균 조회, 카테고리별 성과 분석
  3. 프롬프트 템플릿 + cutter.py 채널 데이터 자동 업데이트
  4. 리포트 생성

사용: POST /api/scheduler/update-stats
"""
import os
import json
from datetime import datetime
from typing import Any

from modules.utils.youtube_stats import fetch_all_channels_stats, get_cached_stats


def collect_and_analyze() -> dict[str, Any]:
    """전 채널 통계 수집 + 분석 요약."""
    print("[주간 분석] 4채널 YouTube 통계 수집 중...")
    all_stats = fetch_all_channels_stats()

    summary = {}
    for ch, data in all_stats.items():
        s = data.get("summary", {})
        videos = data.get("videos", [])

        # 카테고리 분류는 제목 키워드 기반 (간이)
        categories = {
            "우주/행성": 0, "공룡/고생물": 0, "심해/바다": 0,
            "인체/심리": 0, "동물": 0, "지구/자연": 0, "역사": 0, "기타": 0,
        }
        category_views = {k: [] for k in categories}

        for v in videos:
            title = v.get("title", "").lower()
            views = v.get("views", 0)
            cat = "기타"
            if any(w in title for w in ["planet", "star", "space", "행성", "별", "우주", "sun", "moon", "saturn", "jupiter", "venus", "mars", "sol", "luna", "estrella"]):
                cat = "우주/행성"
            elif any(w in title for w in ["dinosaur", "공룡", "fossil", "rex", "dragon", "fósil", "dinosaurio"]):
                cat = "공룡/고생물"
            elif any(w in title for w in ["ocean", "sea", "deep", "바다", "심해", "해구", "mar", "océano"]):
                cat = "심해/바다"
            elif any(w in title for w in ["body", "brain", "heart", "뇌", "심장", "인체", "blood", "cuerpo", "cerebro"]):
                cat = "인체/심리"
            elif any(w in title for w in ["animal", "동물", "shark", "whale", "상어", "고래", "tiburón", "ballena", "penguin"]):
                cat = "동물"
            elif any(w in title for w in ["earth", "지구", "volcano", "지진", "tierra", "volcán"]):
                cat = "지구/자연"

            categories[cat] += 1
            category_views[cat].append(views)

        # 카테고리별 평균 조회
        cat_avg = {}
        for cat, view_list in category_views.items():
            if view_list:
                cat_avg[cat] = round(sum(view_list) / len(view_list))

        summary[ch] = {
            "total_videos": s.get("total_videos", 0),
            "total_views": s.get("total_views", 0),
            "avg_views": s.get("avg_views", 0),
            "top_5": s.get("top_5", []),
            "category_avg": cat_avg,
            "recent_7d_views": s.get("recent_7d_views", 0),
        }

    return summary


def generate_report(summary: dict[str, Any]) -> str:
    """분석 리포트 마크다운 생성."""
    lines = [f"# 채널 성과 분석 리포트 ({datetime.now().strftime('%Y-%m-%d')})"]

    for ch, data in summary.items():
        lines.append(f"\n## {ch}")
        lines.append(f"- 총 영상: {data['total_videos']}개")
        lines.append(f"- 총 조회: {data['total_views']:,}")
        lines.append(f"- 평균 조회: {data['avg_views']:,}")
        lines.append(f"- 최근 7일: {data['recent_7d_views']:,}")

        if data["top_5"]:
            lines.append("\n### Top 5")
            for i, v in enumerate(data["top_5"]):
                lines.append(f"{i+1}. {v['title']} — {v['views']:,}")

        if data["category_avg"]:
            lines.append("\n### 카테고리별 평균 조회")
            sorted_cats = sorted(data["category_avg"].items(), key=lambda x: x[1], reverse=True)
            for cat, avg in sorted_cats:
                if avg > 0:
                    lines.append(f"- {cat}: {avg:,}")

    return "\n".join(lines)


def run_weekly_update() -> dict[str, Any]:
    """주간 업데이트 실행 — 수집 + 분석 + 리포트 저장."""
    summary = collect_and_analyze()
    report = generate_report(summary)

    # 리포트 저장
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "/app/obsidian")
    if not os.path.exists(vault_path):
        vault_path = r"C:\Users\Storm Credit\Desktop\쇼츠\askanything"

    report_path = os.path.join(vault_path, "성과_분석_리포트.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[주간 분석] 리포트 저장: {report_path}")
    return {"success": True, "summary": summary, "report_path": report_path}
