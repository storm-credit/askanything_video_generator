---
name: preflight
description: Run environment preflight checks and report results
context: fork
---

Run the AskAnything preflight check and analyze the results.

Steps:
1. Run `python preflight_check.py` from the project root
2. Run `curl -s http://localhost:8000/api/health` to check server status
3. Run `curl -s http://localhost:8000/api/key-usage` to check key states
4. Analyze the output for FAIL and WARN items
5. For each FAIL: suggest the exact fix command
6. For each WARN: explain impact and whether it blocks the pipeline
7. Summarize: ready to run or blocked

If remotion/node_modules is missing, suggest: `npm --prefix remotion install`
If .env keys are missing, list which API features will be unavailable.
Check Google key count and blocked status.
