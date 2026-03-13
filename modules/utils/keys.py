"""
Google API 키 로테이션 유틸리티 (v2)

3단계 상태 관리:
  🟢 active  — 정상 사용 가능
  🟡 warning — 과다 사용 (우선순위 하락, 사용은 가능)
  🔴 blocked — 429 쿼터 초과 (서비스별 24시간 차단)

서비스별 독립 차단:
  Veo 3 쿼터 초과된 키도 Imagen에는 계속 사용 가능

자동 전환:
  get_google_key(service=..., exclude=...) 로 실패한 키 제외 후 다른 키 반환
"""

import os
import time
import random
import threading
from collections import defaultdict

_usage_lock = threading.Lock()

# ── 사용량 카운터 ──
_key_usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

# ── 서비스별 429 차단: { api_key: { service: blocked_timestamp } } ──
_blocked_keys: dict[str, dict[str, float]] = defaultdict(dict)
_BLOCK_DURATION = 24 * 60 * 60  # 24시간

# ── 경고 임계값 (하루 기준) ──
_WARN_THRESHOLD = {
    "veo3": 3,      # Veo 3: 키당 ~3회/일 → 넘으면 경고
    "veo3:standard": 3,
    "veo3:fast": 3,
    "imagen": 20,    # Imagen 4: 키당 ~20회/일 → 넘으면 경고
    "imagen:standard": 20,
    "imagen:fast": 20,
    "gemini": 50,    # Gemini: 키당 ~50회/일 → 넘으면 경고
}
_DEFAULT_WARN_THRESHOLD = 10


# ═══════════════════════ 상태 조회 ═══════════════════════

def _is_key_blocked(key: str, service: str = None) -> bool:
    """키가 특정 서비스에 대해 차단 상태인지 확인. 반드시 _usage_lock 내부에서 호출할 것."""
    if key not in _blocked_keys:
        return False

    if service:
        # 서비스별 차단 확인
        blocked_at = _blocked_keys[key].get(service)
        if blocked_at is None:
            return False
        if time.time() - blocked_at >= _BLOCK_DURATION:
            del _blocked_keys[key][service]
            if not _blocked_keys[key]:
                del _blocked_keys[key]
            return False
        return True
    else:
        # 전체 서비스 중 하나라도 차단이면 True (하위 호환)
        return any(_is_key_blocked(key, svc) for svc in list(_blocked_keys[key].keys()))


def _is_key_warned(key: str, service: str = None) -> bool:
    """키가 경고 상태인지 확인 (임계값 초과)."""
    if service:
        used = _key_usage[key].get(service, 0)
        threshold = _WARN_THRESHOLD.get(service, _DEFAULT_WARN_THRESHOLD)
        return used >= threshold
    else:
        total = sum(_key_usage[key].values())
        return total >= sum(_WARN_THRESHOLD.values())


def get_key_state(key: str, service: str = None) -> str:
    """키 상태 반환: 'blocked', 'warning', 'active'. 반드시 _usage_lock 내부에서 호출할 것."""
    if _is_key_blocked(key, service):
        return "blocked"
    if _is_key_warned(key, service):
        return "warning"
    return "active"



# ═══════════════════════ 차단/기록 ═══════════════════════

def mark_key_exhausted(api_key: str, service: str = ""):
    """429 에러로 키를 해당 서비스에 대해 24시간 차단합니다."""
    if not api_key:
        return
    svc = service or "_global"
    with _usage_lock:
        _blocked_keys[api_key][svc] = time.time()
        print(f"[키 로테이션] {mask_key(api_key)} ({service}) → 429 쿼터 초과. 24시간 차단. (다른 서비스는 사용 가능)")


def record_key_usage(api_key: str, service: str, count: int = 1):
    """API 키 사용을 기록합니다."""
    if not api_key:
        return
    with _usage_lock:
        _key_usage[api_key][service] += count


# ═══════════════════════ 키 선택 ═══════════════════════

def get_google_key(override: str = None, service: str = None, exclude: set = None) -> str | None:
    """
    최적의 Google API 키를 반환합니다.

    선택 우선순위:
    1. override (프론트엔드 전달 키) — 무조건 반환
    2. active 키 중 사용량 최소
    3. warning 키 중 사용량 최소 (active 없을 때)
    4. blocked 키 중 가장 빨리 해제될 키 (전부 차단 시)

    Args:
        override: 프론트엔드에서 전달한 키 (최우선)
        service: 'veo3', 'imagen', 'gemini' 등 — 서비스별 차단 확인
        exclude: 이번 요청에서 이미 실패한 키 집합 (자동 전환용)
    """
    if override:
        return override

    exclude = exclude or set()

    multi_keys = os.getenv("GEMINI_API_KEYS", "")
    if multi_keys:
        keys = [k.strip() for k in multi_keys.split(",") if k.strip()]
        if keys:
            with _usage_lock:
                # exclude에 있는 키 제외
                candidates = [k for k in keys if k not in exclude]
                if not candidates:
                    return None  # 모든 키가 소진됨

                # 3단계 분류
                active_keys = []
                warning_keys = []
                blocked_keys_list = []

                for k in candidates:
                    state = get_key_state(k, service)
                    svc_usage = _key_usage[k].get(service, 0) if service else sum(_key_usage[k].values())
                    if state == "active":
                        active_keys.append((svc_usage, k))
                    elif state == "warning":
                        warning_keys.append((svc_usage, k))
                    else:
                        blocked_keys_list.append((svc_usage, k))

                # 우선순위: active → warning → blocked (반드시 하나 이상 존재)
                pool = active_keys or warning_keys or blocked_keys_list

                pool.sort(key=lambda x: x[0])
                min_usage = pool[0][0]
                min_keys = [k for u, k in pool if u == min_usage]
                chosen = random.choice(min_keys)

                # 로그 (warning/blocked 사용 시)
                if not active_keys and warning_keys:
                    print(f"[키 로테이션] active 키 없음 → warning 키 사용: {mask_key(chosen)} ({service})")
                elif not active_keys and not warning_keys:
                    print(f"[키 로테이션 경고] 모든 키 차단됨 → 최소 사용 키 강제 사용: {mask_key(chosen)} ({service})")

                return chosen

    # 단일 키 폴백
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


# ═══════════════════════ 통계 ═══════════════════════

def get_key_usage_stats() -> list[dict]:
    """모든 키의 상태/사용량 통계를 반환합니다."""
    all_keys = get_all_google_keys()
    stats = []
    with _usage_lock:
        for key in all_keys:
            masked = mask_key(key)
            raw_usage = dict(_key_usage[key]) if key in _key_usage else {}
            # 모델 변형 태그 집계: "imagen:standard" + "imagen:fast" → "imagen"
            usage: dict[str, int] = {}
            for svc, cnt in raw_usage.items():
                base_svc = svc.split(":")[0] if ":" in svc else svc
                usage[base_svc] = usage.get(base_svc, 0) + cnt
            total = sum(usage.values())

            # 서비스별 차단 상태
            blocked_services = {}
            if key in _blocked_keys:
                for svc, blocked_at in list(_blocked_keys[key].items()):
                    remaining = _BLOCK_DURATION - (time.time() - blocked_at)
                    if remaining > 0:
                        blocked_services[svc] = round(remaining / 3600, 1)
                    else:
                        del _blocked_keys[key][svc]
                if not _blocked_keys[key]:
                    del _blocked_keys[key]

            any_blocked = len(blocked_services) > 0
            state = "blocked" if any_blocked else ("warning" if _is_key_warned(key) else "active")
            remaining_hr = max(blocked_services.values()) if blocked_services else 0

            stats.append({
                "key": masked,
                "usage": usage,
                "total": total,
                "state": state,  # "active" | "warning" | "blocked"
                "blocked": any_blocked,
                "blocked_services": blocked_services,  # {"veo3": 23.5, "imagen": 12.1}
                "unblock_hours": remaining_hr,
            })
    return stats


# ═══════════════════════ 유틸 ═══════════════════════

def mask_key(key: str) -> str:
    """API 키 마스킹: AIzaSyB-***7Y"""
    if len(key) <= 12:
        return key[:4] + "***"
    return key[:8] + "***" + key[-2:]


def get_all_google_keys() -> list[str]:
    """등록된 모든 Google API 키 목록."""
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
    """등록된 Google API 키 개수."""
    return len(get_all_google_keys())


def count_available_keys(service: str = None) -> int:
    """특정 서비스에 대해 차단 안 된 키 개수."""
    all_keys = get_all_google_keys()
    with _usage_lock:
        return sum(1 for k in all_keys if not _is_key_blocked(k, service))
