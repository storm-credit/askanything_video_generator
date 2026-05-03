import os
import sys
import shutil
from pathlib import Path

CHECKS = []


def add_check(status: str, message: str):
    CHECKS.append((status, message))


def load_local_env():
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return
    except Exception:
        env_path = Path(".env")
        if not env_path.exists():
            return

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


def check_python_version():
    if sys.version_info >= (3, 10):
        add_check("PASS", f"Python version: {sys.version.split()[0]}")
    else:
        add_check("FAIL", f"Python 3.10+ required, current: {sys.version.split()[0]}")


def check_commands():
    required = ["ffmpeg", "ffprobe", "npx"]
    for cmd in required:
        path = shutil.which(cmd)
        if path:
            add_check("PASS", f"Command available: {cmd} ({path})")
        else:
            add_check("FAIL", f"Command missing: {cmd}")


def check_python_packages():
    required_imports = {
        "fastapi": "fastapi",
        "sse_starlette": "sse-starlette",
        "openai": "openai",
        "requests": "requests",
        "dotenv": "python-dotenv",
    }
    optional_imports = {
        "tavily": "tavily-python (fact-check optional)",
    }

    for module_name, pkg_name in required_imports.items():
        try:
            __import__(module_name)
            add_check("PASS", f"Python package available: {pkg_name}")
        except Exception:
            add_check("FAIL", f"Python package missing: {pkg_name}")

    for module_name, pkg_name in optional_imports.items():
        try:
            __import__(module_name)
            add_check("PASS", f"Optional package available: {pkg_name}")
        except Exception:
            add_check("WARN", f"Optional package missing: {pkg_name}")


def check_paths():
    assets = Path("assets")
    remotion_dir = Path("remotion")
    remotion_node_modules = remotion_dir / "node_modules"

    if assets.exists():
        add_check("PASS", "assets directory exists")
    else:
        add_check("WARN", "assets directory missing (created at runtime)")

    if remotion_dir.exists() and (remotion_dir / "package.json").exists():
        add_check("PASS", "remotion project found")
    else:
        add_check("FAIL", "remotion project missing or invalid")

    if remotion_node_modules.exists():
        add_check("PASS", "remotion/node_modules exists")
    else:
        add_check("WARN", "remotion/node_modules missing (run: npm --prefix remotion install)")


def check_env_keys():
    from modules.utils.provider_policy import is_openai_api_disabled

    required_keys = ["ELEVENLABS_API_KEY"]
    if not is_openai_api_disabled():
        required_keys.insert(0, "OPENAI_API_KEY")
    optional_keys = ["TAVILY_API_KEY", "KLING_ACCESS_KEY", "KLING_SECRET_KEY", "IMAGEMAGICK_BINARY"]

    for key in required_keys:
        if os.getenv(key):
            add_check("PASS", f"Env set: {key}")
        else:
            add_check("WARN", f"Env missing: {key}")

    for key in optional_keys:
        if os.getenv(key):
            add_check("PASS", f"Env set: {key}")
        else:
            add_check("WARN", f"Env missing: {key}")


def print_report() -> int:
    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    CHECKS.sort(key=lambda x: order[x[0]])

    print("=== AskAnything Preflight Check ===")
    for status, message in CHECKS:
        icon = {"PASS": "OK", "WARN": "WARN", "FAIL": "FAIL"}[status]
        print(f"{icon} [{status}] {message}")

    fail_count = sum(1 for s, _ in CHECKS if s == "FAIL")
    warn_count = sum(1 for s, _ in CHECKS if s == "WARN")
    pass_count = sum(1 for s, _ in CHECKS if s == "PASS")

    print("---")
    print(f"PASS: {pass_count}, WARN: {warn_count}, FAIL: {fail_count}")

    if fail_count:
        print("Preflight result: FAILED")
        return 1

    print("Preflight result: OK")
    return 0


if __name__ == "__main__":
    load_local_env()
    check_python_version()
    check_commands()
    check_python_packages()
    check_paths()
    check_env_keys()
    raise SystemExit(print_report())
