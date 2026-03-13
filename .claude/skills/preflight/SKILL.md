---
name: preflight
description: Run environment preflight checks and report results
disable-model-invocation: true
---

Run the AskAnything preflight check and analyze the results.

Steps:
1. Run `python preflight_check.py` from the project root
2. Analyze the output for FAIL and WARN items
3. For each FAIL: suggest the exact fix command
4. For each WARN: explain impact and whether it blocks the pipeline
5. Summarize: ready to run or blocked

If remotion/node_modules is missing, suggest: `npm --prefix remotion install`
If .env keys are missing, list which API features will be unavailable.
