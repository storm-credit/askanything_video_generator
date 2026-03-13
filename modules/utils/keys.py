"""
Google API 키 로테이션 유틸리티
GEMINI_API_KEYS (쉼표 구분)에서 사용량이 적은 키를 선택합니다.
Gemini, Imagen 4, Veo 3 모두 같은 키풀을 공유합니다.

429 에러 발생 시 해당 키를 24시간 동안 차단하고, 자동 복구합니다.
"""

import os
import time
import random
import threading
from collections import defaultdict

# 키별 사용 카운터 (서버 메모리 내 추적)
_key_usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
_usage_lock = threading.Lock()

# 429 차단 관리: { api_key: blocked_timestamp }
_blocked_keys: dict[str, float] = {}
_BLOCK_DURATION = 24 * 60 * 60  # 24시간 (초)


def _is_key_blocked(key: str) -> bool:
    """키가 429 차단 상태인지 확인. 24시간 경과 시 자동 해제."""
    if key not in _blocked_keys:
        return False
    blocked_at = _blocked_keys[key]
    if time.time() - blocked_at >= _BLOCK_DURATION:
        # 24시간 경과 → 자동 해제
        del _blocked_keys[key]
        return False
    return True


def _get_block_remaining(key: str) -> float:
    """차단 잔여 시간(초) 반환. 차단 안 됐으면 0."""
    if key not in _blocked_keys:
        return 0
    elapsed = time.time() - _blocked_keys[key]
    remaining = _BLOCK_DURATION - elapsed
    return max(0, remaining)


def mark_key_exhausted(api_key: str, service: str = ""):
    """429 에러로 키를 24시간 차단합니다."""
    if not api_key:
        return
    with _usage_lock:
        _blocked_keys[api_key] = time.time()
        svc_label = f" ({service})" if service else ""
        print(f"[키 로테이션] {_mask_key(api_key)}{svc_label} → 429 쿼터 초과. 24시간 차단됨.")


def get_google_key(override: str = None) -> str | None:
    """
    Google API 키를 반환합니다 (차단 안 된 키 중 사용량 최소).
    우선순위:
    1. override (프론트엔드에서 전달된 키) — 차단 여부 무시
    2. GEMINI_API_KEYS (쉼표 구분 - 차단 안 된 키 중 최소 사용량 로테이션)
    3. GEMINI_API_KEY (단일 키)
    4. GOOGLE_API_KEY (폴백)
    """
    if override:
        return override

    # 멀티키 로테이션 (차단 안 된 키 중 사용량 최소 선택)
    multi_keys = os.getenv("GEMINI_API_KEYS", "")
    if multi_keys:
        keys = [k.strip() for k in multi_keys.split(",") if k.strip()]
        if keys:
            with _usage_lock:
                # 차단 안 된 키만 필터
                available = [k for k in keys if not _is_key_blocked(k)]
                if not available:
                    # 모든 키 차단됨 → 가장 빨리 해제될 키 반환
                    earliest = min(keys, key=lambda k: _blocked_keys.get(k, 0))
                    blocked_count = len(keys)
                    print(f"[키 로테이션 경고] 모든 {blocked_count}개 키가 차단됨. 가장 빠른 해제 키 사용: {_mask_key(earliest)}")
                    return earliest

                # 사용량이 가장 적은 키 선택
                usage_totals = []
                for k in available:
                    total = sum(_key_usage[k].values())
                    usage_totals.append((total, k))
                usage_totals.sort(key=lambda x: x[0])
                min_usage = usage_totals[0][0]
                min_keys = [k for u, k in usage_totals if u == min_usage]
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
    키는 마스킹 처리 + 차단 상태 포함.
    """
    all_keys = get_all_google_keys()
    stats = []
    with _usage_lock:
        for key in all_keys:
            masked = _mask_key(key)
            usage = dict(_key_usage[key]) if key in _key_usage else {}
            total = sum(usage.values())
            blocked = _is_key_blocked(key)
            remaining_sec = _get_block_remaining(key)
            remaining_hr = remaining_sec / 3600 if remaining_sec > 0 else 0
            stats.append({
                "key": masked,
                "usage": usage,
                "total": total,
                "blocked": blocked,
                "unblock_hours": round(remaining_hr, 1) if blocked else 0,
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


def count_available_keys() -> int:
    """차단 안 된 사용 가능한 키 개수를 반환합니다."""
    all_keys = get_all_google_keys()
    with _usage_lock:
        return sum(1 for k in all_keys if not _is_key_blocked(k))
