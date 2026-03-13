"""
Google API 키 로테이션 유틸리티
GEMINI_API_KEYS (쉼표 구분)에서 사용량이 적은 키를 선택합니다.
Gemini, Imagen 4, Veo 3 모두 같은 키풀을 공유합니다.
"""

import os
import threading
from collections import defaultdict

# 키별 사용 카운터 (서버 메모리 내 추적)
_key_usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_usage_lock = threading.Lock()


def get_google_key(override: str = None) -> str | None:
    """
    Google API 키를 반환합니다 (사용량 최소인 키 우선).
    우선순위:
    1. override (프론트엔드에서 전달된 키)
    2. GEMINI_API_KEYS (쉼표 구분 - 최소 사용량 로테이션)
    3. GEMINI_API_KEY (단일 키)
    4. GOOGLE_API_KEY (폴백)
    """
    if override:
        return override

    # 멀티키 로테이션 (사용량 최소 키 선택)
    multi_keys = os.getenv("GEMINI_API_KEYS", "")
    if multi_keys:
        keys = [k.strip() for k in multi_keys.split(",") if k.strip()]
        if keys:
            with _usage_lock:
                # 총 사용량이 가장 적은 키 선택
                usage_totals = []
                for k in keys:
                    total = sum(_key_usage[k].values())
                    usage_totals.append((total, k))
                usage_totals.sort(key=lambda x: x[0])
                min_usage = usage_totals[0][0]
                # 동일 최소 사용량인 키들 중 랜덤 선택
                min_keys = [k for u, k in usage_totals if u == min_usage]
                import random
                return random.choice(min_keys)

    # 단일 키 폴백
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def record_key_usage(api_key: str, service: str, count: int = 1):
    """API 키 사용을 기록합니다. service: 'veo3', 'imagen', 'gemini' 등."""
    if not api_key:
        return
    with _usage_lock:
        _key_usage[api_key][service] += count


def get_key_usage_stats() -> list[dict]:
    """
    모든 등록된 키의 사용량 통계를 반환합니다.
    키는 마스킹 처리 (앞 8자 + *** + 뒤 4자).
    """
    all_keys = get_all_google_keys()
    stats = []
    with _usage_lock:
        for key in all_keys:
            masked = _mask_key(key)
            usage = dict(_key_usage[key]) if key in _key_usage else {}
            total = sum(usage.values())
            stats.append({
                "key": masked,
                "usage": usage,
                "total": total,
            })
    return stats


def _mask_key(key: str) -> str:
    """API 키를 마스킹합니다: AIzaSyB-***7Y"""
    if len(key) <= 12:
        return key[:4] + "***"
    return key[:8] + "***" + key[-2:]


def get_all_google_keys() -> list[str]:
    """등록된 모든 Google API 키 목록을 반환합니다."""
    keys = set()

    multi_keys = os.getenv("GEMINI_API_KEYS", "")
    if multi_keys:
        for k in multi_keys.split(","):
            k = k.strip()
            if k:
                keys.add(k)

    single = os.getenv("GEMINI_API_KEY", "")
    if single:
        keys.add(single)

    google = os.getenv("GOOGLE_API_KEY", "")
    if google:
        keys.add(google)

    return list(keys)


def count_google_keys() -> int:
    """등록된 Google API 키 개수를 반환합니다."""
    return len(get_all_google_keys())
