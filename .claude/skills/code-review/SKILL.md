---
name: code-review
description: Review changed files for bugs, security issues, and best practices
context: fork
---

Review code changes in the current branch for quality issues.

Steps:
1. Run `git diff main...HEAD` to see all changes
2. For each changed file, check:
   - **Security**: No command injection, no hardcoded secrets, proper input validation
   - **Correctness**: Logic errors, off-by-one, null handling, async/await correctness
   - **Python**: No bare except, proper type hints, no deprecated APIs, no dead code (unreachable returns)
   - **TypeScript/React**: No side-effects in render, proper key props, no memory leaks, Remotion-compatible (no CSS transitions)
   - **Performance**: No unnecessary network calls, proper timeout values, thread safety (shared state needs locks)
   - **Pipeline**: language parameter flow (ko/en), BGM/brand assets auto-copy, title overlay rendering
3. Report issues by severity: CRITICAL > WARNING > INFO
4. For each issue: file:line, description, suggested fix

Focus on real bugs, not style preferences. Skip files that haven't changed.
