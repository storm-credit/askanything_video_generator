---
name: key-status
description: Check Google API key states, usage, and blocking status
context: fork
---

Check the current state of all Google API keys (Gemini/Imagen/Veo).

Steps:
1. Run `curl -s http://localhost:8000/api/key-usage` to get key usage stats
2. Run `curl -s http://localhost:8000/api/health` to get overall health
3. For each key, report:
   - **State**: 🟢 active / 🟡 warning / 🔴 blocked
   - **Usage**: per-service breakdown (gemini, imagen, veo3)
   - **Blocked services**: which services are blocked and hours until unblock
4. Summary:
   - Total keys vs available keys
   - Which services have capacity remaining
   - If all keys blocked for a service, estimate when first key unblocks
5. If no keys available for critical services (imagen, veo3), suggest waiting or adding more keys to .env

Key state definitions:
- **active**: Under warning threshold, fully usable
- **warning**: Over threshold (veo3: 3, imagen: 20, gemini: 50), still usable but approaching limit
- **blocked**: Got 429 error, auto-unblocks after 24 hours from block time
