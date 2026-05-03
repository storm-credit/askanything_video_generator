# Agent Expertise Matrix

목적: 각 에이전트가 이름만 있는지, 실제 전문가 판단 기준과 실행 하네스를 갖췄는지 추적한다.

## Summary

| Agent | Current Depth | Wiring | Status | Priority |
|---|---:|---|---|---|
| Script / Format Expert | 9.0 | `modules/gpt/prompts/formats/*`, `modules/gpt/cutter/generator.py` | strong | keep aligned |
| Topic Planner Orchestra | 8.5 | `modules/scheduler/topic_generator.py` | strong | keep aligned |
| Quality Gate | 7.5 | `modules/gpt/cutter/quality.py`, `modules/orchestrator/agents/quality.py` | good | strengthen prompt/code parity |
| Visual Director | 6.5 | `modules/gpt/cutter/enhancer.py`, `modules/orchestrator/agents/visual.py` | harness added | high |
| Image Expert | 6.5 | `modules/orchestrator/agents/image.py`, `modules/image/*` | harness added, needs shared A/B code | high |
| Polisher | 6.0 | `modules/gpt/cutter/enhancer.py`, `modules/orchestrator/agents/polish.py` | harness added, needs v2 skip parity | high |
| TTS Expert | 5.5 | `modules/tts/elevenlabs.py`, `modules/orchestrator/agents/tts.py` | harness added, settings refreshed | high |
| Subtitle Expert | 5.5 | `remotion/src/Captions.tsx`, `modules/video/remotion.py` | harness added | medium |
| Uploader | 5.0 | `modules/upload/youtube/*`, `modules/orchestrator/agents/upload.py` | harness added, needs metadata code parity | high |
| Hero Cut | 4.5 | `modules/utils/hero_cuts.py`, video agents | harness added, needs fixtures | medium |
| Performance Analyst | 5.0 | `modules/analytics/*`, `modules/scheduler/weekly_stats_update.py` | harness added | medium |
| Fact Checker | 6.5 | `modules/gpt/cutter/verifier.py` | conditionally strong | medium |
| Subject Checker | 6.5 | `modules/gpt/cutter/verifier.py` | good narrow scope | medium |

## Harness Standard

Every agent should expose the same eight sections:

1. Role Contract
2. Inputs
3. Expert Judgment Criteria
4. Hard Fail
5. Auto-Fix Policy
6. Output Contract
7. Code Wiring
8. Verification Harness

## Immediate Standardization Targets

### Visual Director
- Add per-format shot grammar.
- Define subject lock and caption-safe framing as hard fails.
- Share Cut 1 A/B variant policy with ImageAgent.

### TTS Expert
- Replace stale ElevenLabs-only settings with current Qwen3-first policy.
- Add pronunciation normalization criteria for alnum tokens such as `r5`.
- Add speed floor and emotion-speed rules.

### Subtitle Expert
- Split KO/EN/ES-LATAM/ES-US rules instead of CJK vs Latin only.
- Add overflow and mobile safety hard fails.
- Define sentence-level vs word-highlight policy per channel.

### Uploader
- Make metadata a first-class contract: title, description, tags, playlist, schedule.
- Enforce exactly 5 public tags and no `shorts/short/쇼츠`.
- Preserve Day-file metadata through scheduler and auto upload.

### Hero Cut
- Define per-format candidate ranking, cost policy, and fallback.
- Make output a deterministic `hero_cut_index + reason + fallback`.

### Performance Analyst
- Convert reporting into next-week strategy directives.
- Separate outlier detection, decline diagnosis, and topic planning feedback.

## Deepening Pattern

For every weak agent:

```text
specialist role
→ observable criteria
→ hard fail list
→ safe auto-fix
→ fixed output contract
→ code wiring
→ verification sample
```
