---
name: python-patterns
description: Python coding standards and patterns for this project
---

# Python Patterns — AskAnything

## Required Patterns

### 1. Atomic File Writes
All file downloads/saves MUST use atomic write:
```python
import tempfile, os
with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), suffix=".tmp", delete=False) as tmp:
    tmp.write(data)
    tmp_path = tmp.name
os.replace(tmp_path, path)
```

### 2. API Key Rotation
Use `modules/utils/keys.py` for all multi-key services:
```python
from modules.utils.keys import get_next_key, report_key_error
key = get_next_key("SERVICE_NAME")
# on failure:
report_key_error("SERVICE_NAME", key, error)
```
States: active → warning → blocked (24h cooldown)

### 3. Async Polling Pattern (Video APIs)
```python
async def poll_result(task_id, timeout=450, interval=10):
    deadline = time.time() + timeout
    first = True
    while time.time() < deadline:
        if not first:
            await asyncio.sleep(interval)
        first = False
        status = await check_status(task_id)
        if status == "completed":
            return result
    raise TimeoutError(f"Polling timeout: {task_id}")
```

### 4. Error Handling
- Never bare `except:` — always `except Exception as e:`
- Log with Korean messages for user-facing, English for debug
- Retry with exponential backoff for transient errors:
```python
for attempt in range(max_retries):
    try:
        return await api_call()
    except TransientError:
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)
        else:
            raise
```

### 5. Type Hints
```python
def generate_image(prompt: str, size: str = "1024x1792") -> str | None:
```
Use `str | None` (Python 3.10+), not `Optional[str]`.

### 6. Import Order
1. stdlib (`os, json, time, asyncio`)
2. third-party (`fastapi, openai, google`)
3. local (`modules.utils.keys, modules.utils.constants`)

### 7. Session Data
Always deepcopy mutable session data:
```python
import copy
cuts = copy.deepcopy(session["cuts"])
```

## Anti-Patterns (Do NOT)
- `from module import *`
- Mutable default arguments (`def f(items=[])`)
- `get_event_loop()` — use `get_running_loop()`
- Global state mutation without semaphore
- `os.environ` writes outside semaphore block
