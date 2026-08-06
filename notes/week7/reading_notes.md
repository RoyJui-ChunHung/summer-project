# Week 7 Final Benchmark Plan & Reading Notes

Paper 1: Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows (Lei et al., ICLR 2025)
Paper 2: BIRD-INTERACT: Re-imagining Text-to-SQL Evaluation via Dynamic Interactions (Huo et al., ICLR 2026)

## Paper Summaries

**Spider 2.0.** Pushes text-to-SQL to enterprise scale: 632 tasks over real industrial databases (avg 812 columns, terabyte data, BigQuery/Snowflake/DuckDB dialects), where solving a task means navigating a project codebase, reading dialect docs, and writing multi-step SQL often exceeding 100 lines (avg 144 tokens/SQL, 7.1 special functions/SQL). The best o1-preview code agent solves only 21.3%, versus 91.2% on Spider 1.0 and 73.0% on BIRD. Traditional parsers collapse — DAIL-SQL 5.68%, CHESS 3.84%, DIN-SQL 1.46% on Spider 2.0-lite. Error analysis: erroneous data analysis 35.5%, wrong schema linking 27.6%, JOIN errors 8.3%.

**BIRD-INTERACT.** Argues real database use is multi-turn, not single-shot: users are ambiguous, code fails, goals evolve. It wraps each database in an interactive environment — a hierarchical knowledge base, metadata, and a function-driven user simulator — and tests two settings: c-Interact (a fixed conversational protocol) and a-Interact (agentic, ReAct-style, the model decides when to ask/explore/execute). Tasks cover the full CRUD spectrum with executable test cases, ambiguous initial sub-tasks, and state-dependent follow-ups. Even GPT-5 completes only 8.67% (c-Interact) and 17.00% (a-Interact) on the full 600-task set.

## How These Differ from Static Text-to-SQL Datasets

Static datasets (Spider 1.0, BIRD — my setting) give the model a fixed (question, schema) pair and expect one SQL string, scored once against a gold query. These two benchmarks break that mold on different axes:

- **No pre-packaged input.** Spider 2.0 gives a codebase and a live database interface, not a clean schema; the model must *discover* the relevant context. BIRD-INTERACT gives an underspecified request that is unsolvable until the model asks for clarification.
- **No single expected output.** Spider 2.0 tasks may transform the database or return a table/file; BIRD-INTERACT scores functional correctness via executable test cases, not string/result match against one gold SQL.
- **State and multi-step.** Both require sequences of queries; BIRD-INTERACT adds state dependency (a follow-up sub-task reads objects created by the previous one).
- **Evaluation is a process, not a comparison.** Success is measured over an interaction trajectory (BIRD-INTERACT) or a multi-turn agent rollout (Spider 2.0), rewarding *how* the model gets there, not just the final query.

## Enterprise Workflow Challenges (Spider 2.0)

- **Large schemas.** Avg 812 columns vs Spider 1.0's ~27; schema linking becomes the dominant failure (27.6%). Full schema can't fit cleanly in the prompt.
- **SQL dialects.** BigQuery/Snowflake/DuckDB each have unique functions (85.98% of tasks need dialect-specific functions, avg 7.1/query). Providing oracle function docs gave only a *slight* gain — the hard part is using functions to match intent, not knowing them.
- **Metadata & documentation.** Tasks require reading external docs; performance drops sharply when they do (11.5% SR with external docs vs 26.6% without) — models explore correctly but fail to ground doc requirements into SQL.
- **Multi-step / project-level.** 144-token, 100+-line SQL with nested CTEs and set operations; DBT project tasks (12% of set) need whole-codebase understanding and score worst.

## Interactive Evaluation Challenges (BIRD-INTERACT)

- **Ambiguity.** Deliberately injected (vague intent like "urgent care", broken knowledge chains); tasks are unsolvable without clarification, so the model must *recognise* it doesn't know and ask.
- **Clarification & communication.** Memory grafting shows GPT-5's failures are communicative, not generative — given another model's clarification history it succeeds, so knowing *how to ask* is a distinct skill from writing SQL.
- **User simulation.** A reliable simulator is hard: naive LLM simulators leak ground truth (up to 67.4% failure on unanswerable questions); their function-driven two-stage simulator cuts that to 2.7% and correlates 0.84 with real humans.
- **Multi-turn state & budget.** State-dependent follow-ups and a capped interaction budget test whether the model asks the *right* questions efficiently rather than brute-forcing.

## Open Questions

**Q1.** BIRD-INTERACT finds frontier models prefer trial-and-error (`submit`/`ask` = 60.87% of actions) over systematic exploration "due to pre-training biases." My ReAct agent showed exactly this (1.5 tool calls/task, mostly `execute_sql`). Is the under-exploration a fixable prompting/fine-tuning issue, or is exploration simply useless on my clean Spider where the schema is already fully in the prompt? The two explanations predict opposite results on a larger-schema benchmark.

**Q2.** BIRD-INTERACT's Interaction Test-Time Scaling shows accuracy rising with more turns, sometimes matching the idealized single-turn task. My retries show the opposite plateau — extra attempts convert crashes into silent wrong-results without raising EX. Is the difference that each ITS turn injects *new information* (clarifications, exploration) while my retries inject none? That would sharpen my ceiling argument: retries help only when each turn brings new signal.

**Q3.** Schema linking is the #2 error in Spider 2.0 (27.6%) even for o1-preview on 812-column schemas, and recurs across every paper I've read (DIN-SQL 37%, BIRD 41%). Is schema-linking difficulty driven by absolute column count or by ambiguous/similar column names? My clean, well-named Spider columns may be why my schema-linking errors are comparatively rare — which would mean column *naming quality*, not count, is the real lever.

## Final Benchmark Plan

My benchmark is already built and run; this documents its final form.

**Dataset / subset.** Spider 1.0 development set, filtered to Hard + Extra Hard (n = 224: 148 Hard, 76 Extra Hard). Single-turn, clean small schemas (~27 cols) — deliberately the tractable, static end of the difficulty curve, chosen to isolate correction/tool mechanisms rather than chase enterprise or interactive difficulty.

**Methods to compare (5 agents, same model Qwen3.5-9b, same prompt, zero-shot).**
- Single-shot (no correction) — baseline
- Blind self-correction (review without executing) — DIN-SQL-style
- Feedback loop (execute → read error → revise) — the core mechanism
- Verify-and-revise (execute → verify returned rows → revise) — targets the wrong-result ceiling
- ReAct (4 tools via function calling, LLM-driven) — targets the "add tools" question

**Metrics.** Primary: Execution Accuracy (EX), order-independent frozenset match of result rows. Secondary, per agent: execution_error vs wrong_result counts; tool-call counts (ReAct); per-example fixes/regressions vs the feedback loop; verifier precision/recall (verify).

**Expected tables & figures.**
- Table 1 — EX for all 5 agents with tool column and Δ vs single-shot.
- Table 2 — EX by hardness (Hard / Extra Hard) × 5 agents.
- Table 3 — EX by SQL pattern (nested / JOIN / NOT IN / GROUP BY / INTERSECT / EXCEPT / ORDER BY / HAVING / UNION).
- Table 4 — failure breakdown (execution_error vs wrong_result) across 5 agents.
- Figure 1 — the correction-mechanism ladder (single → blind → feedback → verify → ReAct) as a bar chart, showing the rise to feedback and the drop at ReAct.

**Error-analysis categories.**
1. `execution_error` — SQL raised (syntactic/schema).
2. `wrong_result` — ran cleanly but wrong rows (the logical/silent class; my ceiling).
3. By SQL pattern (which structures each mechanism fixes vs. can't touch).
4. Verify-specific: genuine fixes vs false-positive NO calls on already-correct results (3 vs 24).
5. ReAct-specific: exploration-SQL-returned-as-final-answer.

**Risks / scope reductions if time is limited.**
- Single model (Qwen3.5-9b); a second model (GPT-4o-mini) is the first thing to cut/defer.
- Simplified hardness classifier (not Spider's official one) may misclassify boundary cases.
- Run-to-run non-determinism at temperature 0 slightly blurs cross-agent per-example comparisons; report only causal (flagged) differences.
- Out of scope for a solo project: BIRD/Spider 2.0 scale, and any multi-turn/interactive (clarification, user simulation) setting — noted as future work, not attempted.
