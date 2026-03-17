---
name: security-review
description: Security checklist for API keys, file operations, and input validation
---

# Security Review Checklist — AskAnything

## 1. API Key Protection
- [ ] Keys loaded from `os.environ`, never hardcoded
- [ ] Health endpoint masks keys (last 4 chars only)
- [ ] `.env` in `.gitignore`
- [ ] `client_secret*.json`, `token*.json`, `*.credentials` in `.gitignore`
- [ ] No keys in error messages or SSE responses
- [ ] Key rotation: blocked keys auto-recover after 24h

## 2. Path Traversal Prevention
All user-influenced file paths must be validated:
```python
real = os.path.abspath(os.path.realpath(user_path))
if not real.startswith(ALLOWED_BASE_DIR):
    raise ValueError("Invalid path")
```
Check: `api_server.py` render endpoint, batch download paths

## 3. SQL Injection (SQLite)
- [ ] All queries use parameterized `?` placeholders
- [ ] Column names validated against `ALLOWED_COLS` whitelist
- [ ] No f-string or `.format()` in SQL queries

## 4. Input Validation
- [ ] Pydantic models validate all request fields
- [ ] Language restricted to known list (18 languages)
- [ ] Platform values validated
- [ ] Camera style is `Literal` type
- [ ] Numeric fields have reasonable bounds

## 5. Race Conditions
- [ ] `os.environ` writes only inside `_generate_semaphore`
- [ ] Session reads use `copy.deepcopy()`
- [ ] Batch queue uses lock for check+insert (TOCTOU prevention)
- [ ] Atomic file writes prevent partial reads

## 6. Network Security
- [ ] CORS: explicit origin list, no `*`
- [ ] SSE endpoints: no sensitive data in progress messages
- [ ] External API timeouts set (no hanging connections)
- [ ] File downloads have size limits or timeouts

## 7. Dependency Security
- [ ] `requirements.txt` has pinned versions for critical packages
- [ ] No unused dependencies
- [ ] Regular update check for known CVEs

## When to Run
- Before any PR that touches: auth, file I/O, database, API endpoints
- After adding new external API integrations
- Periodic review (monthly)
