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

### Objective

The goal of this benchmark is not to top a leaderboard but to isolate a single question: on clean, small database schemas, how much does each correction or tool-use mechanism actually contribute to text-to-SQL accuracy, and where does each one stop helping? Because every method is run on the same questions, the same schema, the same model, and the same prompt, any difference in accuracy is attributable to the mechanism alone rather than to prompt engineering, model choice, or dataset difficulty. In particular the study aims to measure the value of execution feedback — running the query and feeding back the database's error — and to test whether layering verification or autonomous tool use on top of that feedback buys anything further.

### Dataset

Evaluation uses the Spider 1.0 development set restricted to the Hard and Extra Hard subsets (n = 224: 148 Hard, 76 Extra Hard). Spider is chosen for its clean, small, synthetic schemas (~27 columns per database), which keep failures structural rather than value-interpretation noise and let the full schema fit in the prompt. The Hard subset is chosen because easy questions are already solved by a single call and carry no diagnostic signal, whereas the hard structures — nested subqueries, GROUP BY, HAVING, joins, and set operations — are exactly where correction mechanisms are expected to differ. This is deliberately the static, tractable end of the difficulty curve; enterprise scale (Spider 2.0) and interactive settings (BIRD-INTERACT) are out of scope.

### Baselines

Two conditions serve as baselines that never touch the database. The **single-shot** agent generates one query and returns it, establishing the floor against which every other method is measured. **Blind self-correction** generates a query and then reviews and revises it against the schema and question without ever executing it, in the style of DIN-SQL's self-review pass; it isolates how far a model can improve on pure self-inspection, with no execution signal.

### Proposed Methods

Three methods extend the baselines by giving the agent access to the database or to tools — the element the baselines lack. The **feedback loop** executes the query, and on a runtime error feeds the error message back and retries; this is the core mechanism the study is built around. **Verify-and-revise** goes one step further: after a clean execution it asks a separate verifier call whether the returned rows actually answer the question, targeting the logical errors that error-only feedback cannot see. **ReAct** gives the model four tools through function calling (`execute_sql`, `sample_rows`, `describe_table`, `get_distinct_values`) and lets it decide autonomously when to call them, testing whether autonomous tool use adds value on clean schemas. Finally, a **pipeline** chains three of these mechanisms into one explicit flow — error feedback, then a blind review pass, then result verification — with each stage given its own budget so they do not compete for a single shared retry counter. This directly tests whether combining the mechanisms recovers more than the strongest one alone.

### Metrics

The primary metric is execution accuracy (EX): predicted and gold SQL are executed and their result rows compared as order-independent sets. Secondary, per-agent measures characterise *how* each method succeeds or fails: the split between execution errors and wrong-result failures, average API/tool calls per example (to weigh cost against accuracy), per-example fixes and regressions relative to the feedback loop, and verifier precision and recall for the verify agent. Results are reported overall, by hardness level, and by SQL pattern, and summarised in a bar chart of EX across all conditions (Figure 1).

### Error Analysis

Failures are categorised first by type — `execution_error` (the query raised, i.e. syntactic or schema errors) versus `wrong_result` (the query ran cleanly but returned the wrong rows, the silent logical class that forms the accuracy ceiling) — and then by SQL pattern, to show which structures each mechanism can and cannot fix. Two method-specific categories capture the most informative failures: for verify-and-revise, the split between genuine fixes and false-positive flags on already-correct results (3 versus 24); and for ReAct, cases where the agent returns an exploration query as its final answer instead of one that answers the question. Re-executing the 66 wrong-result cases left by the feedback loop reveals a further split: 13 are false negatives where the predicted result is correct but its columns are returned in a different order than the gold query, so the strict set-based match scores them wrong; the remaining 53 are genuine logical errors, dominated by wrong-table joins and incorrect subquery logic. This matters for the pipeline decision: none of the available tools (which inspect values and column names) can fix wrong-table joins or subquery logic, so the pipeline combines feedback, blind review, and verification rather than adding tools — and even so it only narrows the ceiling slightly (66 to 61 wrong-result), confirming that the remaining errors are logical, not mechanical.

### Risks and Scope Reductions

The main limitation is that all results come from a single model (Qwen3.5-9b); repeating the comparison on a second model such as GPT-4o-mini would be the first extension if time allowed, and is the first thing to defer if not. The hardness labels come from a simplified reimplementation of Spider's classifier, so boundary cases may be misclassified. Because temperature-0 decoding is not perfectly deterministic across runs, per-example cross-agent comparisons are blurred slightly, so only causally attributable differences are emphasised. Enterprise scale and any multi-turn or interactive setting are out of scope for a solo project and are noted as future work rather than attempted.
