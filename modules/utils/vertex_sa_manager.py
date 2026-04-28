"""Vertex AI service-account key management.

Stores uploaded SA json files under data/vertex_sa and exposes only safe metadata.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
MANAGED_DIR = Path(os.getenv("VERTEX_SA_DIR", str(DATA_DIR / "vertex_sa"))).resolve()
SETTINGS_FILE = DATA_DIR / ".vertex_sa_settings.json"


def _load_settings() -> dict[str, Any]:
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"order": [], "disabled": []}


def _save_settings(settings: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return value[:80] or "service-account"


def _mask_email(email: str) -> str:
    if "@" not in email:
        return email[:3] + "***" if email else ""
    name, domain = email.split("@", 1)
    if len(name) <= 4:
        masked = name[:1] + "***"
    else:
        masked = f"{name[:3]}***{name[-2:]}"
    return f"{masked}@{domain}"


def _fingerprint(path: Path, data: dict[str, Any] | None = None) -> str:
    payload = ""
    if data:
        payload = f"{data.get('project_id', '')}:{data.get('client_email', '')}:{data.get('private_key_id', '')}"
    if not payload:
        payload = str(path.resolve())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _read_sa(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("type") != "service_account":
        return None
    if not data.get("project_id") or not data.get("client_email") or not data.get("private_key"):
        return None
    return data


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    MANAGED_DIR.mkdir(parents=True, exist_ok=True)
    paths.extend(Path(p) for p in glob.glob(str(MANAGED_DIR / "*.json")))

    roots = [Path("/app"), PROJECT_ROOT]
    explicit = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if explicit:
        roots.insert(0, Path(explicit).parent)
        paths.append(Path(explicit))

    for root in roots:
        if root.exists():
            paths.extend(Path(p) for p in glob.glob(str(root / "vertex-sa-key*.json")))

    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        try:
            real = str(path.resolve())
        except Exception:
            real = str(path)
        if real in seen or not path.exists():
            continue
        seen.add(real)
        unique.append(path)
    return unique


def list_service_accounts(include_disabled: bool = True) -> list[dict[str, Any]]:
    settings = _load_settings()
    order = [str(x) for x in settings.get("order", [])]
    disabled = set(str(x) for x in settings.get("disabled", []))
    rows: list[dict[str, Any]] = []

    for path in _candidate_paths():
        data = _read_sa(path)
        if not data:
            continue
        source = "managed" if path.resolve().is_relative_to(MANAGED_DIR) else "root"
        item_id = path.name
        enabled = item_id not in disabled
        if not include_disabled and not enabled:
            continue
        rows.append({
            "id": item_id,
            "filename": path.name,
            "path": str(path),
            "source": source,
            "managed": source == "managed",
            "enabled": enabled,
            "project_id": data.get("project_id", ""),
            "client_email": _mask_email(data.get("client_email", "")),
            "fingerprint": _fingerprint(path, data),
        })

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        try:
            pos = order.index(item["id"])
        except ValueError:
            pos = 10_000
        return pos, item["filename"]

    return sorted(rows, key=sort_key)


def get_enabled_sa_paths() -> list[str]:
    return [item["path"] for item in list_service_accounts(include_disabled=False)]


def get_service_account(item_id: str | None = None, path: str | None = None, include_disabled: bool = True) -> dict[str, Any] | None:
    target_id = (item_id or "").strip()
    target_path = str(Path(path).resolve()) if path else ""
    for item in list_service_accounts(include_disabled=include_disabled):
        if target_id and item["id"] == target_id:
            return item
        if target_path and str(Path(item["path"]).resolve()) == target_path:
            return item
    return None


def get_next_service_account() -> dict[str, Any] | None:
    try:
        from modules.utils.gemini_client import peek_next_sa_key

        next_path = peek_next_sa_key()
        if next_path:
            return get_service_account(path=next_path, include_disabled=False)
    except Exception:
        pass
    enabled = list_service_accounts(include_disabled=False)
    return enabled[0] if enabled else None


def upload_service_account(filename: str, raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("JSON 파일을 읽을 수 없습니다") from exc
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise ValueError("Google service_account JSON이 아닙니다")
    for field in ("project_id", "client_email", "private_key"):
        if not data.get(field):
            raise ValueError(f"{field} 필드가 없습니다")

    MANAGED_DIR.mkdir(parents=True, exist_ok=True)
    base = _slug(Path(filename).stem)
    if not base.startswith("vertex-sa-key"):
        base = f"vertex-sa-key-{_slug(data.get('project_id', base))}"
    target = MANAGED_DIR / f"{base}.json"
    if target.exists():
        suffix = _fingerprint(target, data)[:8]
        target = MANAGED_DIR / f"{base}-{suffix}.json"

    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    settings = _load_settings()
    order = [x for x in settings.get("order", []) if x != target.name]
    order.append(target.name)
    settings["order"] = order
    settings["updated_at"] = datetime.now(KST).isoformat()
    _save_settings(settings)
    refresh_runtime_vertex_env()
    return next(item for item in list_service_accounts() if item["id"] == target.name)


def update_service_accounts(items: list[dict[str, Any]]) -> dict[str, Any]:
    existing = {item["id"] for item in list_service_accounts()}
    order: list[str] = []
    disabled: list[str] = []
    for item in items:
        item_id = str(item.get("id") or item.get("filename") or "").strip()
        if item_id not in existing or item_id in order:
            continue
        order.append(item_id)
        if item.get("enabled") is False:
            disabled.append(item_id)
    for item_id in sorted(existing):
        if item_id not in order:
            order.append(item_id)
    settings = _load_settings()
    settings.update({
        "order": order,
        "disabled": disabled,
        "updated_at": datetime.now(KST).isoformat(),
    })
    _save_settings(settings)
    refresh_runtime_vertex_env()
    return {"accounts": list_service_accounts()}


def delete_service_account(item_id: str) -> dict[str, Any]:
    target = (MANAGED_DIR / item_id).resolve()
    if not str(target).startswith(str(MANAGED_DIR)):
        raise ValueError("관리 디렉터리 밖의 파일은 삭제할 수 없습니다")
    if not target.exists():
        raise FileNotFoundError(item_id)
    target.unlink()
    settings = _load_settings()
    settings["order"] = [x for x in settings.get("order", []) if x != item_id]
    settings["disabled"] = [x for x in settings.get("disabled", []) if x != item_id]
    settings["updated_at"] = datetime.now(KST).isoformat()
    _save_settings(settings)
    refresh_runtime_vertex_env()
    return {"accounts": list_service_accounts()}


def _resolve_env_path() -> Path | None:
    for candidate in (Path("/app/.env"), PROJECT_ROOT / ".env", Path.cwd() / ".env"):
        if candidate.exists():
            return candidate
    return PROJECT_ROOT / ".env"


def _upsert_env_values(values: dict[str, str]) -> None:
    env_path = _resolve_env_path()
    if not env_path:
        return
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(values)
    new_lines: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in remaining:
            new_lines.append(f"{key}={remaining.pop(key)}")
        else:
            new_lines.append(line)
    for key, value in remaining.items():
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def refresh_runtime_vertex_env(
    reset_runtime: bool = True,
    *,
    force_backend: bool = True,
    persist: bool = True,
) -> dict[str, Any]:
    """Vertex 런타임 모드를 동기화한다.

    force_backend=True:
        설정창에서 SA 목록을 바꾼 직후 Vertex backend를 활성화한다.
        활성 SA가 있을 때만 SA-only로 전환한다.

    force_backend=False:
        현재 환경변수를 그대로 존중하면서 런타임 캐시만 새로고친다.
    """
    accounts = list_service_accounts(include_disabled=False)
    enabled_count = len(accounts)
    current_backend = os.getenv("GEMINI_BACKEND", "ai_studio").strip().lower() or "ai_studio"
    current_sa_only = os.getenv("VERTEX_SA_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}

    backend = "vertex_ai" if force_backend else current_backend
    sa_only = bool(enabled_count) if force_backend else current_sa_only

    if backend == "vertex_ai":
        os.environ["GEMINI_BACKEND"] = "vertex_ai"
    if sa_only:
        os.environ["VERTEX_SA_ONLY"] = "true"
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    elif force_backend:
        os.environ["VERTEX_SA_ONLY"] = "false"

    if persist:
        values: dict[str, str] = {}
        if force_backend or current_backend == "vertex_ai":
            values["GEMINI_BACKEND"] = backend
        if force_backend or current_sa_only or sa_only:
            values["VERTEX_SA_ONLY"] = "true" if sa_only else "false"
        if sa_only:
            values["GOOGLE_APPLICATION_CREDENTIALS"] = ""
        if values:
            _upsert_env_values(values)

    if reset_runtime:
        try:
            from modules.utils import gemini_client
            gemini_client.refresh_sa_keys()
        except Exception:
            pass
    return {
        "backend": backend,
        "sa_only": sa_only,
        "enabled_count": enabled_count,
        "accounts": list_service_accounts(),
    }


def test_service_account(item_id: str | None = None) -> dict[str, Any]:
    account = get_service_account(item_id=item_id, include_disabled=True) if item_id else get_next_service_account()
    if not account:
        raise ValueError("테스트할 Vertex SA가 없습니다")

    data = _read_sa(Path(account["path"]))
    if not data:
        raise ValueError("SA JSON을 읽을 수 없습니다")

    from google import genai
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    location = os.getenv("VERTEX_LOCATION", "us-central1")
    project_id = data.get("project_id") or os.getenv("VERTEX_PROJECT", "")
    creds = service_account.Credentials.from_service_account_file(
        account["path"],
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    creds.refresh(Request())

    try:
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
            credentials=creds,
        )
        pager = client.models.list(config={"page_size": 1})
        next(iter(pager), None)
    except Exception as exc:
        message = str(exc)
        if "403" in message or "PERMISSION_DENIED" in message:
            reason = "권한 부족 또는 Vertex API 비활성화"
        elif "404" in message or "NOT_FOUND" in message:
            reason = "프로젝트/리전 설정을 찾지 못함"
        else:
            reason = f"Vertex 연결 테스트 실패: {exc}"
        raise ValueError(reason) from exc

    return {
        "ok": True,
        "message": "Vertex 연결 성공",
        "account": {
            "id": account["id"],
            "filename": account["filename"],
            "project_id": account["project_id"],
            "client_email": account["client_email"],
            "source": account["source"],
            "enabled": account["enabled"],
        },
    }
