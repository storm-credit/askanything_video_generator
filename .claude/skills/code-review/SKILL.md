---
name: code-review
description: Review changed files for bugs, security issues, and best practices
disable-model-invocation: true
context: fork
---

Review code changes in the current branch for quality issues.

Steps:
1. Run `git diff main...HEAD` to see all changes
2. For each changed file, check:
   - **Security**: No command injection, no hardcoded secrets, proper input validation
   - **Correctness**: Logic errors, off-by-one, null handling, async/await correctness
   - **Python**: No bare except, proper type hints, no deprecated APIs
   - **TypeScript/React**: No side-effects in render, proper key props, no memory leaks
   - **Performance**: No unnecessary network calls, proper timeout values
3. Report issues by severity: CRITICAL > WARNING > INFO
4. For each issue: file:line, description, suggested fix

Focus on real bugs, not style preferences. Skip files that haven't changed.
