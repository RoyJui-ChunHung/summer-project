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

## Exp 002 — Three-way comparison: Single-shot vs Feedback Loop vs Blind Correction

**Date:** 2026-07-21  
**Model:** `qwen/qwen3.5-9b` (via OpenRouter)  
**Dataset:** Spider 1.0 dev set — Hard + Extra Hard (224 examples)  
**Commands:**
```
python3 src/eval.py --max_retries 1 --output experiments/run_retries1.json
python3 src/eval.py --max_retries 3 --output experiments/run_retries3.json
python3 src/eval.py --agent blind --flavor generic --output experiments/run_blind.json
```

**Note:** All three runs use the updated `_parse_response` (reasoning-preamble extraction) and `_chat` (retry + timeout). Exp 001 numbers are not directly comparable; Exp 002 is the clean baseline.

### Results

| Agent | `max_retries` | Correct | EX | vs single-shot | Output file |
|---|---|---|---|---|---|
| Single-shot | 1 | 141/224 | **62.9%** | — | `run_retries1.json` |
| Blind correction | 3 | 151/224 | **67.4%** | +4.5pp | `run_blind.json` |
| Feedback loop | 3 | 158/224 | **70.5%** | +7.6pp | `run_retries3.json` |

**Blind vs feedback gap: −3.1pp** (blind trails feedback loop).

### Key Observations

- **Exp 002 supersedes Exp 001.** The `_parse_response` parser was updated between runs (now extracts the first top-level SQL statement from responses that mix reasoning prose before the query). The Exp 001 numbers (61.6% / 68.8%) are not comparable; use Exp 002 (62.9% / 70.5%) as the authoritative baseline.
- Feedback loop eliminates all 32 execution errors, but wrong_result rises from 51 → 66: those crashes are converted into silent wrong answers. The agent never knows the result is wrong, so extra retries produce the same logical mistake.
- Blind correction partially reduces execution errors (32 → 14) without any execution signal — the self-review pass catches some syntax mistakes. But it cannot match feedback's complete elimination of runtime failures.
- INTERSECT shows blind (81.6%) beating feedback (76.3%), and GROUP BY shows blind (43.6%) beating feedback (38.5%). Treat these as tentative: both patterns have n ≈ 38, so a handful of examples separates the two agents and random variation could explain the reversal.
- Feedback loop is the strongest agent overall (+7.6pp vs single-shot). Blind is useful when execution is unavailable but is less efficient (3 calls/example for +4.5pp vs feedback's adaptive 1–3 calls for +7.6pp).

### Engineering Notes

- Added `timeout=60` to all API calls (httpx was hanging indefinitely on stalled connections).
- Added per-example checkpoint (`.ckpt` JSONL) so crashes are resumable without redoing work.
- Added `_is_sql()` guard in `BlindCorrectionAgent` to prevent a non-SQL review response from overwriting a good prediction.
- Added `_parse_response` reasoning-preamble extraction: finds first `^SELECT|^WITH` line when model outputs prose before SQL.

---

*Add new experiments below this line.*
