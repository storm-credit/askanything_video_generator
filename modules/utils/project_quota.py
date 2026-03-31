"""
프로젝트 단위 쿨다운 매니저 (v1)

핵심 원칙:
  - 할당량은 API 키가 아닌 프로젝트(Project) 단위로 계산
  - 같은 프로젝트의 키는 quota 공유 → 하나 429면 전부 잠금
  - 429 종류 구분: RPM성(짧은 쿨다운) vs RPD성(다음 리셋까지)
  - 선택은 "사용 가능한 프로젝트 → 가장 건강한 것 → 키 선택" 순서

사용:
  from modules.utils.project_quota import quota_manager
  project, key, alias = quota_manager.acquire(service="imagen")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import random
import threading
import os
import json


KST = timezone(timedelta(hours=9))


@dataclass
class ApiKeyInfo:
    key: str
    alias: str  # 로그용. 예: "...9O1p"


@dataclass
class ProjectState:
    name: str
    keys: List[ApiKeyInfo]

    blocked_until: Optional[datetime] = None
    daily_exhausted_until: Optional[datetime] = None

    # 서비스별 차단 (imagen, gemini, nano_banana 등)
    service_blocked: Dict[str, datetime] = field(default_factory=dict)
    service_daily_exhausted: Dict[str, datetime] = field(default_factory=dict)

    success_count: int = 0
    fail_count: int = 0
    consecutive_failures: int = 0

    last_used_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_reason: Optional[str] = None

    rr_index: int = 0

    def is_available(self, now: datetime, service: str = "") -> bool:
        # 서비스별 체크
        if service:
            svc_daily = self.service_daily_exhausted.get(service)
            if svc_daily and now < svc_daily:
                return False
            svc_blocked = self.service_blocked.get(service)
            if svc_blocked and now < svc_blocked:
                return False
        # 전체 체크
        if self.daily_exhausted_until and now < self.daily_exhausted_until:
            return False
        if self.blocked_until and now < self.blocked_until:
            return False
        return True

    def next_key(self) -> ApiKeyInfo:
        key_info = self.keys[self.rr_index % len(self.keys)]
        self.rr_index = (self.rr_index + 1) % len(self.keys)
        return key_info


class ProjectQuotaManager:
    """프로젝트 단위로 Gemini/Imagen 호출 상태를 관리."""

    def __init__(self):
        self._lock = threading.RLock()
        self.projects: Dict[str, ProjectState] = {}
        self._initialized = False

    def initialize(self, project_to_keys: Dict[str, List[Tuple[str, str]]]):
        """프로젝트-키 매핑 등록."""
        with self._lock:
            for project_name, keys in project_to_keys.items():
                self.projects[project_name] = ProjectState(
                    name=project_name,
                    keys=[ApiKeyInfo(key=k, alias=a) for k, a in keys],
                )
            self._initialized = True
            print(f"[QuotaManager] {len(self.projects)}개 프로젝트 등록 완료")

    def initialize_from_env(self):
        """GEMINI_API_KEYS 환경변수 + PROJECT_GROUPS 설정에서 자동 초기화."""
        keys_str = os.getenv("GEMINI_API_KEYS", "")
        all_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        if not all_keys:
            return

        # 프로젝트 그룹 설정 (JSON 환경변수 또는 하드코딩)
        groups_json = os.getenv("PROJECT_GROUPS", "")
        known_groups: Dict[str, List[str]] = {}
        if groups_json:
            try:
                known_groups = json.loads(groups_json)
            except Exception:
                pass

        # 알려진 그룹에 속한 키 모으기
        grouped_keys = set()
        project_to_keys: Dict[str, List[Tuple[str, str]]] = {}
        for project_name, group_keys in known_groups.items():
            matched = [(k, f"...{k[-4:]}") for k in all_keys if k in group_keys]
            if matched:
                project_to_keys[project_name] = matched
                grouped_keys.update(k for k, _ in matched)

        # 나머지 키는 개별 프로젝트로
        for k in all_keys:
            if k not in grouped_keys:
                alias = f"...{k[-4:]}"
                project_to_keys[f"proj_{k[:8]}"] = [(k, alias)]

        self.initialize(project_to_keys)

    # ─── 공개 메서드 ───

    def acquire(self, service: str = "") -> Tuple[str, str, str]:
        """사용 가능한 프로젝트/키 선택. 반환: (project_name, api_key, key_alias)"""
        with self._lock:
            if not self._initialized:
                self.initialize_from_env()

            now = self._now()
            candidates = [p for p in self.projects.values() if p.is_available(now, service)]

            if not candidates:
                raise RuntimeError(self._format_no_available(now, service))

            project = self._pick_best(candidates, now)
            key_info = project.next_key()
            project.last_used_at = now

            return project.name, key_info.key, key_info.alias

    def mark_success(self, project_name: str, service: str = "") -> None:
        with self._lock:
            now = self._now()
            p = self.projects.get(project_name)
            if not p:
                return
            p.success_count += 1
            p.consecutive_failures = 0
            p.last_success_at = now
            p.last_error_reason = None
            # 서비스별 차단 해제 (성공했으니)
            if service:
                p.service_blocked.pop(service, None)

    def mark_rate_limited(self, project_name: str, reason: str = "429",
                          service: str = "", retry_after: int = 0,
                          mode: str = "auto") -> None:
        """429 발생 시 프로젝트 쿨다운."""
        with self._lock:
            now = self._now()
            p = self.projects.get(project_name)
            if not p:
                return

            p.fail_count += 1
            p.consecutive_failures += 1
            p.last_error_at = now
            p.last_error_reason = reason

            resolved_mode = self._detect_mode(reason, mode)

            if resolved_mode == "daily":
                reset_at = self._next_daily_reset(now)
                if service:
                    p.service_daily_exhausted[service] = reset_at
                else:
                    p.daily_exhausted_until = reset_at
                print(f"[QuotaManager] {project_name} ({service or 'all'}) RPD 소진 → {reset_at.astimezone(KST).strftime('%H:%M')} KST까지 제외")
            else:
                cooldown = self._compute_cooldown(p.consecutive_failures, retry_after)
                until = now + timedelta(seconds=cooldown)
                if service:
                    old = p.service_blocked.get(service)
                    if old is None or until > old:
                        p.service_blocked[service] = until
                else:
                    if p.blocked_until is None or until > p.blocked_until:
                        p.blocked_until = until
                print(f"[QuotaManager] {project_name} ({service or 'all'}) RPM 제한 → {cooldown}초 쿨다운")

    def mark_paid_only(self, project_name: str, service: str = "") -> None:
        """'유료 플랜만 가능' 에러 → 해당 서비스 영구 차단."""
        with self._lock:
            p = self.projects.get(project_name)
            if not p:
                return
            # 아주 먼 미래로 차단 (사실상 영구)
            far_future = self._now() + timedelta(days=365)
            if service:
                p.service_daily_exhausted[service] = far_future
            else:
                p.daily_exhausted_until = far_future
            print(f"[QuotaManager] {project_name} ({service or 'all'}) 유료 플랜 전용 → 영구 제외")

    def mark_error(self, project_name: str, reason: str = "") -> None:
        with self._lock:
            now = self._now()
            p = self.projects.get(project_name)
            if not p:
                return
            p.fail_count += 1
            p.consecutive_failures += 1
            p.last_error_at = now
            p.last_error_reason = reason
            cooldown = min(10 * p.consecutive_failures, 60)
            until = now + timedelta(seconds=cooldown)
            if p.blocked_until is None or until > p.blocked_until:
                p.blocked_until = until

    def get_status(self) -> List[dict]:
        with self._lock:
            now = self._now()
            rows = []
            for p in self.projects.values():
                rows.append({
                    "project": p.name,
                    "available": p.is_available(now),
                    "keys": len(p.keys),
                    "aliases": [k.alias for k in p.keys],
                    "success": p.success_count,
                    "fail": p.fail_count,
                    "consecutive_fail": p.consecutive_failures,
                    "blocked_until": self._fmt(p.blocked_until),
                    "daily_exhausted": self._fmt(p.daily_exhausted_until),
                    "service_blocked": {s: self._fmt(t) for s, t in p.service_blocked.items()},
                    "last_error": p.last_error_reason,
                })
            rows.sort(key=lambda x: (not x["available"], x["project"]))
            return rows

    def reset_project(self, project_name: str) -> None:
        with self._lock:
            p = self.projects.get(project_name)
            if p:
                p.blocked_until = None
                p.daily_exhausted_until = None
                p.service_blocked.clear()
                p.service_daily_exhausted.clear()
                p.consecutive_failures = 0

    def get_key_for_project(self, project_name: str) -> Optional[str]:
        """특정 프로젝트의 키 반환 (외부 호환용)."""
        with self._lock:
            p = self.projects.get(project_name)
            if p:
                return p.next_key().key
        return None

    # ─── 내부 로직 ───

    def _pick_best(self, candidates: List[ProjectState], now: datetime) -> ProjectState:
        scored = []
        for p in candidates:
            score = 0.0
            score += p.success_count * 0.3
            score -= p.fail_count * 0.2
            score -= p.consecutive_failures * 2.0
            if p.last_success_at:
                age = (now - p.last_success_at).total_seconds()
                score += max(0, 30 - age) * 0.05
            if p.last_used_at:
                used_age = (now - p.last_used_at).total_seconds()
                if used_age < 5:
                    score -= 1.5
            score += random.uniform(0, 0.01)
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _detect_mode(self, reason: str, mode: str) -> str:
        if mode in ("short", "daily"):
            return mode
        text = (reason or "").lower()
        daily_signals = ["per day", "daily limit", "rpd", "quota exceeded", "spending cap",
                         "지출 한도", "exceeded your current quota"]
        if any(s in text for s in daily_signals):
            return "daily"
        return "short"

    def _compute_cooldown(self, consecutive: int, retry_after: int) -> int:
        if retry_after > 0:
            return retry_after
        base = min(15 * (2 ** max(0, consecutive - 1)), 240)
        return base + random.randint(0, 5)

    def _next_daily_reset(self, now: datetime) -> datetime:
        local = now.astimezone(KST)
        target = local.replace(hour=17, minute=10, second=0, microsecond=0)
        if local < target:
            return target
        return target + timedelta(days=1)

    def _format_no_available(self, now: datetime, service: str) -> str:
        soonest = None
        for p in self.projects.values():
            for dt in [p.blocked_until, p.daily_exhausted_until] + list(p.service_blocked.values()) + list(p.service_daily_exhausted.values()):
                if dt and (soonest is None or dt < soonest):
                    soonest = dt
        svc_str = f" ({service})" if service else ""
        if soonest:
            return f"[QuotaManager] 사용 가능한 프로젝트 없음{svc_str}. 복구: {soonest.astimezone(KST).strftime('%H:%M')} KST"
        return f"[QuotaManager] 사용 가능한 프로젝트 없음{svc_str}."

    @staticmethod
    def _fmt(dt: Optional[datetime]) -> Optional[str]:
        return dt.astimezone(KST).isoformat() if dt else None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


# ── 싱글톤 인스턴스 ──
quota_manager = ProjectQuotaManager()
