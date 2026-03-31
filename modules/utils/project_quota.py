"""
프로젝트 단위 쿨다운 매니저 (v2)

핵심:
  - 키가 아니라 프로젝트를 상태 관리
  - 같은 프로젝트의 키 중 하나가 429면 프로젝트 전체 잠금
  - 429 종류 구분: RPM성(짧은 쿨다운) vs RPD성(리셋까지)
  - 선택은 사용 가능한 프로젝트 중 가장 건강한 것 우선
  - 환경변수로 키 관리 (코드에 키 노출 금지)

사용:
  from modules.utils.project_quota import quota_manager
  project, key, alias = quota_manager.acquire()
"""

from __future__ import annotations

import os
import json
import random
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

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

    success_count: int = 0
    fail_count: int = 0
    consecutive_failures: int = 0

    last_used_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_reason: Optional[str] = None

    rr_index: int = 0

    def is_available(self, now: datetime) -> bool:
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

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.projects: Dict[str, ProjectState] = {}

    def register_projects(self, project_to_keys: Dict[str, List[dict]]) -> None:
        """프로젝트-키 매핑 등록.

        project_to_keys 형식:
        {
            "Default Gemini Project": [
                {"key": "AIza...", "alias": "...IF9"},
            ],
        }
        """
        with self._lock:
            self.projects.clear()
            for project_name, keys in project_to_keys.items():
                valid_keys = [k for k in keys if k.get("key")]
                if valid_keys:
                    self.projects[project_name] = ProjectState(
                        name=project_name,
                        keys=[ApiKeyInfo(key=k["key"], alias=k["alias"]) for k in valid_keys],
                    )
            print(f"[QuotaManager] {len(self.projects)}개 프로젝트 등록")
            for pname, pstate in self.projects.items():
                aliases = [k.alias for k in pstate.keys]
                print(f"  {pname}: {aliases}")

    # ─── 공개 메서드 ───

    def acquire(self) -> tuple[str, str, str]:
        """사용 가능한 프로젝트/키 선택.

        Returns: (project_name, api_key, key_alias)
        Raises: RuntimeError if no project available
        """
        with self._lock:
            now = self._now()
            candidates = [p for p in self.projects.values() if p.is_available(now)]

            if not candidates:
                raise RuntimeError(self._format_no_available(now))

            project = self._pick_best(candidates, now)
            key_info = project.next_key()
            project.last_used_at = now

            return project.name, key_info.key, key_info.alias

    def mark_success(self, project_name: str) -> None:
        """성공 기록."""
        with self._lock:
            now = self._now()
            p = self.projects.get(project_name)
            if not p:
                return
            p.success_count += 1
            p.consecutive_failures = 0
            p.last_success_at = now
            p.last_error_reason = None

    def mark_rate_limited(
        self,
        project_name: str,
        reason: str = "429",
        retry_after_seconds: Optional[int] = None,
        mode: str = "auto",
    ) -> None:
        """429 발생 시 프로젝트 쿨다운.

        mode:
          "short" — RPM/IPM 성격 (몇 초~몇 분)
          "daily" — RPD 소진 (다음 리셋까지)
          "auto"  — reason 텍스트로 자동 판별
        """
        with self._lock:
            now = self._now()
            p = self.projects.get(project_name)
            if not p:
                return

            p.fail_count += 1
            p.consecutive_failures += 1
            p.last_error_at = now
            p.last_error_reason = reason

            detected = self._detect_limit_mode(reason, mode)

            if detected == "daily":
                p.daily_exhausted_until = self._next_daily_reset(now)
                p.blocked_until = None
                print(f"[QuotaManager] {project_name} RPD 소진 → {p.daily_exhausted_until.astimezone(KST).strftime('%H:%M')} KST까지 제외")
            else:
                cooldown = self._compute_short_cooldown(
                    p.consecutive_failures, retry_after_seconds
                )
                until = now + timedelta(seconds=cooldown)
                if p.blocked_until is None or until > p.blocked_until:
                    p.blocked_until = until
                print(f"[QuotaManager] {project_name} RPM 제한 → {cooldown}초 쿨다운")

    def mark_paid_only(self, project_name: str) -> None:
        """'유료 플랜만 가능' → 영구 제외."""
        with self._lock:
            p = self.projects.get(project_name)
            if not p:
                return
            p.daily_exhausted_until = self._now() + timedelta(days=365)
            print(f"[QuotaManager] {project_name} 유료 플랜 전용 → 영구 제외")

    def mark_error(self, project_name: str, reason: str = "") -> None:
        """일반 에러 (5xx, 네트워크 등)."""
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
        """전체 프로젝트 상태 반환."""
        with self._lock:
            now = self._now()
            rows = []
            for p in self.projects.values():
                rows.append({
                    "project": p.name,
                    "available": p.is_available(now),
                    "blocked_until": self._fmt(p.blocked_until),
                    "daily_exhausted_until": self._fmt(p.daily_exhausted_until),
                    "success_count": p.success_count,
                    "fail_count": p.fail_count,
                    "consecutive_failures": p.consecutive_failures,
                    "last_used_at": self._fmt(p.last_used_at),
                    "last_success_at": self._fmt(p.last_success_at),
                    "last_error_at": self._fmt(p.last_error_at),
                    "last_error_reason": p.last_error_reason,
                    "aliases": [k.alias for k in p.keys],
                })
            rows.sort(key=lambda x: (not x["available"], x["project"]))
            return rows

    def reset_project(self, project_name: str) -> None:
        """수동 차단 해제."""
        with self._lock:
            p = self.projects.get(project_name)
            if not p:
                return
            p.blocked_until = None
            p.daily_exhausted_until = None
            p.consecutive_failures = 0
            p.last_error_reason = None

    # ─── 내부 로직 ───

    def _pick_best(self, candidates: List[ProjectState], now: datetime) -> ProjectState:
        """헬스 기반 프로젝트 선택."""
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

    def _detect_limit_mode(self, reason: str, mode: str) -> str:
        if mode in ("short", "daily"):
            return mode
        text = (reason or "").lower()
        daily_signals = ["per day", "daily limit", "rpd", "quota exceeded",
                         "spending cap", "지출 한도"]
        if any(s in text for s in daily_signals):
            return "daily"
        return "short"

    def _compute_short_cooldown(self, consecutive: int, retry_after: Optional[int]) -> int:
        if retry_after and retry_after > 0:
            return retry_after
        base = min(15 * (2 ** max(0, consecutive - 1)), 240)
        return base + random.randint(0, 5)

    def _next_daily_reset(self, now: datetime) -> datetime:
        """RPD 리셋: 태평양시 자정 ≈ KST 17:10."""
        local = now.astimezone(KST)
        target = local.replace(hour=17, minute=10, second=0, microsecond=0)
        if local < target:
            return target
        return target + timedelta(days=1)

    def _format_no_available(self, now: datetime) -> str:
        soonest = None
        for p in self.projects.values():
            for dt in (p.blocked_until, p.daily_exhausted_until):
                if dt and (soonest is None or dt < soonest):
                    soonest = dt
        if soonest:
            return f"사용 가능한 프로젝트 없음. 복구: {soonest.astimezone(KST).strftime('%H:%M')} KST"
        return "사용 가능한 프로젝트 없음."

    @staticmethod
    def _fmt(dt: Optional[datetime]) -> Optional[str]:
        return dt.astimezone(KST).isoformat() if dt else None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


# ── 환경변수에서 프로젝트-키 매핑 로드 ──

def load_project_key_map() -> Dict[str, List[dict]]:
    """환경변수에서 프로젝트별 키 로드.

    방법 1: PROJECT_GROUPS JSON + 개별 환경변수
    방법 2: GEMINI_API_KEYS 쉼표 구분 (레거시 호환)
    """
    result: Dict[str, List[dict]] = {}

    # 방법 1: 개별 환경변수
    env_map = {
        "default_gemini_1": ("GEMINI_KEY_DEFAULT_1", "Default Gemini Project"),
        "default_gemini_2": ("GEMINI_KEY_DEFAULT_2", "Default Gemini Project"),
        "gemini": ("GEMINI_KEY_GEMINI", "gemini"),
        "sraino": ("GEMINI_KEY_SRAINO", "sraino"),
        "hs1103": ("GEMINI_KEY_HS1103", "askanything_hs1103"),
        "ys0404": ("GEMINI_KEY_YS0404", "ys0404"),
        "kh0505": ("GEMINI_KEY_KH0505", "kh0505"),
        "sskwon": ("GEMINI_KEY_SSKWON", "sskwon"),
        "induck": ("GEMINI_KEY_INDUCK", "induck"),
        "hl0209": ("GEMINI_KEY_HL0209", "hl0209"),
        "stormcredit": ("GEMINI_KEY_STORMCREDIT", "stormcredit"),
        "sillious": ("GEMINI_KEY_SILLIOUS", "sillious"),
    }

    for _, (env_var, project_name) in env_map.items():
        key = os.getenv(env_var, "")
        if key:
            alias = f"...{key[-4:]}"
            result.setdefault(project_name, []).append({"key": key, "alias": alias})

    # 방법 2: 레거시 GEMINI_API_KEYS (개별 환경변수 없을 때)
    if not result:
        keys_str = os.getenv("GEMINI_API_KEYS", "")
        all_keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        # PROJECT_GROUPS JSON으로 그룹핑
        groups_json = os.getenv("PROJECT_GROUPS", "")
        known_groups: Dict[str, List[str]] = {}
        if groups_json:
            try:
                known_groups = json.loads(groups_json)
            except Exception:
                pass

        grouped = set()
        for project_name, group_keys in known_groups.items():
            matched = [k for k in all_keys if k in group_keys]
            if matched:
                result[project_name] = [{"key": k, "alias": f"...{k[-4:]}"} for k in matched]
                grouped.update(matched)

        for k in all_keys:
            if k not in grouped:
                result[f"proj_{k[:8]}"] = [{"key": k, "alias": f"...{k[-4:]}"}]

    return result


# ── 싱글톤 ──
quota_manager = ProjectQuotaManager()
