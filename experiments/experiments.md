# Experiment Log

## Exp 001 — A/B: Single-shot vs Feedback Loop

**Date:** 2026-07-14  
**Model:** `qwen/qwen3.5-9b` (via OpenRouter)  
**Dataset:** Spider 1.0 dev set — Hard + Extra Hard (224 examples)  
**Script:** `python3 src/eval.py --spider_dir data/spider --max_retries <N> --output results/<file>.json`

### Results

| Run | `max_retries` | Correct | EX | Wrong result | Execution error | Output file |
|-----|--------------|---------|-----|-------------|-----------------|-------------|
| Single-shot | 1 | 138/224 | **61.6%** | 54 | 32 | `run_retries1.json` |
| Feedback loop | 3 | 154/224 | **68.8%** | 70 | 0 | `run_retries3.json` |
| **Delta** | — | +16 | **+7.2pp** | +16 | −32 | — |

### Key Observations

- The feedback loop eliminated all 32 execution errors (syntax/runtime failures). Of those 32, 16 became correct and 16 became wrong_result after retrying.
- The feedback loop does **not** help wrong_result failures — when the model generates valid but logically incorrect SQL, there is no error message to feed back, so retrying produces the same wrong answer.
- Wrong_result count increased from 54 → 70 because the 16 retried execution errors that still failed are now classified as wrong_result instead.

### Bug Found During This Experiment

**Token limit bug:** An earlier buggy run (before this experiment) showed only 28.1%/29.0% EX.  
**Root cause:** `max_tokens=512` was too small. Qwen3's internal reasoning tokens consumed the entire budget, leaving `content: None` (empty prediction). These empty predictions executed as empty SQL, returning `frozenset()` instead of correct results.  
**Fix:** Increased `max_tokens` to 2048 in `agent_predict()`. Zero empty predictions in both runs above.

---

*Add new experiments below this line.*
