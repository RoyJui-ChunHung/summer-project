# Week 5 Agentic Method Definition & Reading Notes

Paper 1: MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL (Wang et al., 2023)
Paper 2: CHESS: Contextual Harnessing for Efficient SQL Synthesis (Talaei et al., 2024)

## Reading Notes

### Note 1: MAC-SQL — three agents, one pipeline.

Three agents: a Selector (prunes schema above a token threshold, ≥6 cols/table); a Decomposer (breaks the question into 1–5 chain-of-thought sub-questions, each with its own SQL); a Refiner (runs SQL, reads the SQLite error, retries up to 3×). GPT-4: 59.39% EX on BIRD dev. Ablation: removing the Refiner costs −4.63pp, concentrated on Challenging questions (40.28% → 33.33%, −6.95pp); Simple questions are nearly unaffected.

### Note 2: MAC-SQL's Refiner has the same known limit as my agent.

The Refiner stops as soon as SQL runs without error, even if semantically wrong (Appendix A.3) — the exact gap my Week 4 Q1 identified. Execution feedback covers the 3% invalid-SQL bucket but misses the 37% schema-linking bucket (DIN-SQL). Confirmed by Exp 002: all 66 remaining failures after the feedback loop are wrong-result. This is a field-level open problem, not a shortcut I took.

### Note 3: CHESS — four agents, retrieval-first design.

IR extracts keywords, searches DB values via LSH + embedding, and retrieves column descriptions from a catalog via vector DB (handles mismatches like "directly funded" vs "Directly funded"). SS compresses schemas in three steps (filter_col → select_tables → select_cols). CG generates SQL and revises on error or empty result (same loop as MAC-SQL's Refiner). UT (high-budget): 10 NL unit tests score 20 candidates. Full pipeline: 71.10% EX on BIRD test.

### Note 4: CHESS's ablation pins down what matters.

Largest ablation hits: removing revise −6.80pp; removing select_tables −6.12pp. My +7.6pp (62.9% → 70.5%, Exp 002) sits in this range, now backed by two independent ablations. For ~100-col schemas (BIRD) SS can hurt by over-pruning — they skip it in the high-budget config. Spider (~25 cols) makes it even less justified.

### Note 5: The Unit Tester is creative but expensive and still incomplete.

Scores 20 candidate SQLs against 10 NL unit tests; performance peaks at 10 tests. Reduces but doesn't eliminate wrong-result selection. Cost: ~200 LLM calls/question — not reproducible on a student budget, but the one published mechanism aimed at the wrong-result ceiling both MAC-SQL and my agent leave open.

## Comparing Multi-Agent Collaboration vs. Retrieval/Verification-Oriented Synthesis

| Dimension | MAC-SQL | CHESS |
|---|---|---|
| Core insight | Divide the task across specialist agents | Retrieval quality is the bottleneck, not just generation |
| Agents | 3 (Selector, Decomposer, Refiner) | 4 (IR, SS, CG, UT) |
| Schema filtering | Selector: one LLM call, fires above token threshold | SS: 3-step pipeline (filter col → select tables → select col) |
| Value retrieval | None — model guesses from column name | IR: LSH + embedding search across all DB rows |
| Execution feedback | Refiner: error → retry, max 3× | CG revise: error or empty result → retry, max 3× |
| Verification | None | UT: 10 NL unit tests score 20 candidates (high-budget only) |
| Silent wrong-result | Not handled (known limitation) | Partially mitigated by UT; not eliminated |
| Best BIRD test EX | 59.59% (GPT-4) | 71.10% (Gemini-1.5-pro, high-budget) |
| Reproducible for me | Refiner only: feasible | CG revise only: feasible; rest needs preprocessing + budget |

MAC-SQL's intelligence sits at the input end (decompose the question well, then fix). CHESS adds an output-verification stage MAC-SQL lacks, and shows retrieval quality matters as much as generation quality.

## What Is Practical to Reproduce in a Small Final Project

- **Feasible — execution feedback loop:** already built as `FeedbackLoopAgent`; both ablations confirm it was the right first thing to build.
- **Feasible — blind self-correction:** one extra LLM call, no preprocessing (`BlindCorrectionAgent`).
- **Feasible — one-test verification step:** one NL check over returned rows; cheap, noisy, targets the wrong-result gap.
- **Not feasible — CHESS IR (value retrieval):** needs LSH + vector DB preprocessing; Spider has no catalog.
- **Not feasible — MAC-SQL Decomposer:** 3–5 LLM calls per question; breaks the single-variable comparison.
- **Not feasible — full CHESS Unit Tester:** ~200 LLM calls per question.

## Open Questions

**Q1.** Both papers confirm execution feedback only fires on throwable errors; DIN-SQL puts schema-linking failures (runnable but wrong) at 37%. If my +7.6pp mainly comes from the invalid-SQL bucket, what is the ceiling above 70.5%? Checkable in my failure logs — MAC-SQL shows Hard questions may have more throwable errors than average.

**Q2.** The UT uses the same model that wrote the wrong SQL to judge it. Can Qwen3.5-9b reliably test itself, or does self-verification reproduce the original blind spot? Is there a cheaper semantic proxy — e.g. flagging a suspiciously small result — that doesn't need 20 candidates?

**Q3.** CHESS skips SS at ~100 columns because strong LLMs handle it and SS adds a precision-recall trade-off. At what schema size does SS start helping? Likely model-dependent — for a local Qwen3.5-9b the crossover may be far lower than for Gemini-1.5-pro.

## Final-Project Agentic Method Definition

I propose a **verify-and-revise agent**: the execution-feedback loop plus a lightweight CHESS-inspired self-check — a clean fourth condition: single-shot → blind → feedback → verify-and-revise.

- **Agent tools.** (1) `format_schema`: CREATE TABLE + foreign keys + "no explanation". (2) `SQLExecutor.execute(sql)`: returns `ExecutionResult(rows, error)`. (3) `result_check`: one LLM call given question + schema + returned rows — judges whether the result plausibly answers the question (a minimal single-test Unit Tester).
- **Intermediate traces to collect (per question).** `attempt_number` (1–3), `draft_sql`, execution outcome, `result_check` verdict + rationale, `ex_score`, `pred_empty`, `reason`. Extends the current results-JSON; fields stay stable for `analyze_failures.py`.
- **Retry policy.** `max_retries = 3`. Retry on SQL error, empty result, or failed `result_check`. Feed back the SQLite error message on error; the check's rationale on a failed check.
- **Stopping conditions.** Stop when SQL runs, returns non-empty, and passes `result_check`; or the revised SQL is unchanged from the previous attempt; or `max_retries` is reached — then return the last attempt.
- **Expected advantages.** Adds a signal for logically-wrong-but-runnable SQL (Exp 002: all 66 remaining failures are wrong-result). Should help most on GROUP BY / HAVING, my weakest patterns. Zero preprocessing; single-variable design preserved.
- **Expected failure modes.** (1) Self-verification bias — the model that wrote the wrong SQL judges it (Q2). (2) False negatives on legitimately-empty results. (3) Extra LLM call roughly doubles per-question cost — must show a real EX gain over the plain feedback loop to justify.
