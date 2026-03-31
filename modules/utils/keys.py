"""
Google API 키 로테이션 유틸리티 (v3)

3단계 상태 관리:
  🟢 active  — 정상 사용 가능
  🟡 warning — 과다 사용 (우선순위 하락, 사용은 가능)
  🔴 blocked — 429 쿼터 초과 (서비스별 차단)

서비스별 독립 차단:
  Veo 3 쿼터 초과된 키도 Imagen에는 계속 사용 가능

프로젝트 단위 차단:
  할당량은 API 키가 아닌 프로젝트(Project) 단위로 계산됨
  같은 프로젝트의 키는 하나가 차단되면 전부 차단 처리

지수 백오프 + 지터:
  429 발생 시 2^n + random(0,1) 초 대기 후 재시도

자동 전환:
  get_google_key(service=..., exclude=...) 로 실패한 키 제외 후 다른 키 반환
"""

import os
import time
import random
import threading
import hashlib
from collections import defaultdict

_usage_lock = threading.Lock()

# ── 사용량 카운터 ──
_key_usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

# ── 서비스별 429 차단: { api_key: { service: blocked_timestamp } } ──
_blocked_keys: dict[str, dict[str, float]] = defaultdict(dict)
_BLOCK_DURATION_DEFAULT = 2 * 60 * 60  # 2시간 (기본)
_BLOCK_DURATION_BY_SERVICE = {
    "veo3": 2 * 60 * 60,        # Veo3: 2시간
    "veo3:standard": 2 * 60 * 60,
    "veo3:fast": 2 * 60 * 60,
    "imagen": 24 * 60 * 60,     # Imagen: 24시간
    "imagen:standard": 24 * 60 * 60,
    "imagen:fast": 24 * 60 * 60,
    "imagen:ultra": 24 * 60 * 60,
    "imagen:nano-banana": 24 * 60 * 60,
    "imagen:nano-banana-preview": 24 * 60 * 60,
    "gemini": 30 * 60,           # Gemini: 30분
}

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

# ── 프로젝트 그룹핑: 같은 프로젝트 키는 하나 차단 = 전부 차단 ──
_project_groups: dict[str, str] = {}  # { api_key: project_id }

def _get_project_id(api_key: str) -> str:
    """키에서 프로젝트 ID 추출 (키 prefix 기반 추정)."""
    if api_key in _project_groups:
        return _project_groups[api_key]
    # 키의 앞 12자를 프로젝트 그룹 ID로 사용 (같은 프로젝트면 접두사가 비슷)
    # 실제로는 Google API에서 프로젝트 ID를 알 수 없으므로 키별 독립 관리
    return api_key[:12]

def register_project_group(api_keys: list[str], project_id: str):
    """같은 프로젝트의 키들을 그룹으로 등록. 하나 차단되면 전부 차단."""
    for key in api_keys:
        _project_groups[key] = project_id

def mark_project_exhausted(api_key: str, service: str):
    """프로젝트 단위 차단 — 같은 프로젝트의 모든 키를 해당 서비스에서 차단."""
    project_id = _get_project_id(api_key)
    with _usage_lock:
        for key, pid in _project_groups.items():
            if pid == project_id:
                svc = service or "_global"
                _blocked_keys[key][svc] = time.time()
        # 등록 안 된 키도 자기 자신은 차단
        svc = service or "_global"
        _blocked_keys[api_key][svc] = time.time()

# ── 지수 백오프 + 지터 유틸리티 ──
def exponential_backoff_wait(attempt: int, base: float = 2.0, max_wait: float = 60.0) -> float:
    """지수 백오프 + 랜덤 지터. 대기 시간(초) 반환."""
    wait = min(base ** attempt + random.uniform(0, 1), max_wait)
    return wait

# ── RPM 제한 추적 ──
_rpm_tracker: dict[str, list[float]] = defaultdict(list)  # { api_key: [timestamp, ...] }
_RPM_LIMITS = {
    "gemini": 5,       # Gemini 무료: 5 RPM
    "imagen": 10,      # Imagen: ~10 RPM
    "nano_banana": 5,  # Nano Banana: ~5 RPM
}

def check_rpm_available(api_key: str, service: str = "") -> bool:
    """RPM 한도 내인지 확인. False면 잠시 대기 필요."""
    with _usage_lock:
        now = time.time()
        key = f"{api_key}:{service}"
        # 60초 이전 기록 제거
        _rpm_tracker[key] = [t for t in _rpm_tracker[key] if now - t < 60]
        limit = _RPM_LIMITS.get(service.split(":")[0], 15)
        return len(_rpm_tracker[key]) < limit

def record_rpm_usage(api_key: str, service: str = ""):
    """RPM 사용 기록."""
    with _usage_lock:
        key = f"{api_key}:{service}"
        _rpm_tracker[key].append(time.time())


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
        block_dur = _BLOCK_DURATION_BY_SERVICE.get(service, _BLOCK_DURATION_DEFAULT)
        if time.time() - blocked_at >= block_dur:
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
        # 서비스별 경고 여부 개별 확인: 하나라도 경고면 True
        for svc, cnt in _key_usage[key].items():
            threshold = _WARN_THRESHOLD.get(svc, _DEFAULT_WARN_THRESHOLD)
            if cnt >= threshold:
                return True
        return False


def get_key_state(key: str, service: str = None) -> str:
    """키 상태 반환: 'blocked', 'warning', 'active'.

    내부에서 _usage_lock을 획득합니다. 이미 lock 내부에서 호출 시 _get_key_state_unlocked()를 사용하세요.
    """
    with _usage_lock:
        return _get_key_state_unlocked(key, service)


def _get_key_state_unlocked(key: str, service: str = None) -> str:
    """락 없이 키 상태 반환 — 반드시 _usage_lock 내부에서만 호출."""
    if _is_key_blocked(key, service):
        return "blocked"
    if _is_key_warned(key, service):
        return "warning"
    return "active"



# ═══════════════════════ 차단/기록 ═══════════════════════

def mark_key_exhausted(api_key: str, service: str = ""):
    """429 에러로 키를 해당 서비스에 대해 차단합니다.

    프로젝트 단위: 같은 프로젝트 키가 등록되어 있으면 전부 차단.
    할당량은 프로젝트 단위이므로 키만 바꿔도 소용없음.
    """
    if not api_key:
        return
    svc = service or "_global"
    project_id = _get_project_id(api_key)
    with _usage_lock:
        _blocked_keys[api_key][svc] = time.time()
        # 같은 프로젝트의 다른 키도 차단
        blocked_siblings = 0
        for key, pid in _project_groups.items():
            if pid == project_id and key != api_key:
                _blocked_keys[key][svc] = time.time()
                blocked_siblings += 1
        if blocked_siblings > 0:
            print(f"[키 로테이션] {mask_key(api_key)} ({service}) → 429 쿼터 초과. 같은 프로젝트 키 {blocked_siblings}개도 차단.")
        else:
            print(f"[키 로테이션] {mask_key(api_key)} ({service}) → 429 쿼터 초과. 차단됨.")


def record_key_usage(api_key: str, service: str, count: int = 1):
    """API 키 사용을 기록합니다."""
    if not api_key:
        return
    with _usage_lock:
        _key_usage[api_key][service] += count


# ═══════════════════════ 키 선택 ═══════════════════════

def get_google_key(override: str = None, service: str = None, exclude: set = None, extra_keys: str | None = None) -> str | None:
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
        extra_keys: 프론트엔드 멀티키 (쉼표 구분) — os.environ 대신 직접 전달
    """
    if override:
        return override

    exclude = exclude or set()

    multi_keys = extra_keys or os.getenv("GEMINI_API_KEYS", "")
    if multi_keys:
        keys = [k.strip() for k in multi_keys.split(",") if k.strip()]
        if keys:
            with _usage_lock:
                # exclude에 있는 키 제외
                candidates = [k for k in keys if k not in exclude]
                if not candidates:
                    return None  # 모든 키가 소진됨

                # 2단계 분류: 사용 가능(active+warning) vs 차단(blocked)
                available_keys = []
                blocked_keys_list = []

                for k in candidates:
                    state = _get_key_state_unlocked(k, service)
                    svc_usage = _key_usage[k].get(service, 0) if service else sum(_key_usage[k].values())
                    if state in ("active", "warning"):
                        available_keys.append((svc_usage, k))
                    else:
                        blocked_keys_list.append((svc_usage, k))

                # 사용 가능 키 중 전체 최소 사용량 우선, 없으면 차단 키
                pool = available_keys or blocked_keys_list

                pool.sort(key=lambda x: x[0])
                chosen = pool[0][1]  # 최소 사용량 키 (동률 시 첫 번째 = 결정적)

                # 로그 (blocked 키만 남았을 때)
                if not available_keys:
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
                    remaining = _BLOCK_DURATION_BY_SERVICE.get(svc, _BLOCK_DURATION_DEFAULT) - (time.time() - blocked_at)
                    if remaining > 0:
                        blocked_services[svc] = round(remaining / 3600, 1)
                    else:
                        del _blocked_keys[key][svc]
                if not _blocked_keys[key]:
                    del _blocked_keys[key]

            any_blocked = len(blocked_services) > 0
            state = "blocked" if any_blocked else _get_key_state_unlocked(key)
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


def get_service_usage_totals() -> dict[str, int]:
    """서비스별 총 사용량 합산 (모든 키 합계). 예: {"imagen": 15, "veo3": 3, "gemini": 8}"""
    with _usage_lock:
        totals: dict[str, int] = {}
        for key_usage in _key_usage.values():
            for svc, cnt in key_usage.items():
                base_svc = svc.split(":")[0] if ":" in svc else svc
                totals[base_svc] = totals.get(base_svc, 0) + cnt
        return totals


# ═══════════════════════ 유틸 ═══════════════════════

def mask_key(key: str) -> str:
    """API 키 마스킹: AIzaSyB-***7Y"""
    if len(key) <= 12:
        return key[:4] + "***"
    return key[:8] + "***" + key[-2:]


def get_all_google_keys(extra_keys: str | None = None) -> list[str]:
    """등록된 모든 Google API 키 목록."""
    keys = set()
    multi_keys = extra_keys or os.getenv("GEMINI_API_KEYS", "")
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


def count_google_keys(extra_keys: str | None = None) -> int:
    """등록된 Google API 키 개수."""
    return len(get_all_google_keys(extra_keys))


def count_available_keys(service: str = None, extra_keys: str | None = None) -> int:
    """특정 서비스에 대해 차단 안 된 키 개수."""
    all_keys = get_all_google_keys(extra_keys)
    with _usage_lock:
        return sum(1 for k in all_keys if not _is_key_blocked(k, service))
