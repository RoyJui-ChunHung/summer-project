# Does Execution Feedback Help? A Five-Way Study of Text-to-SQL Agents on Spider

## 1. Introduction

Large language models can translate natural language questions into SQL with impressive fluency, but they fail more often on structurally complex queries — subqueries, set operations, multi-table joins. A common failure mode is silent: the model produces syntactically valid SQL that runs but returns the wrong answer, with no signal that anything went wrong.

One proposed remedy is the execution feedback loop: generate SQL, execute it against the target database, observe the result or error, and revise. If the query raises a runtime error, the error message is a concrete, actionable signal the model can act on. A weaker alternative is blind self-correction: ask the model to review its own output without executing it, in the style of DIN-SQL's self-review pass. This study asks which signal — execution error, blind review, or no feedback at all — translates into measurable accuracy gains on hard queries.

We evaluate five agents on the Spider Hard and Extra Hard subsets using the same model and prompt. The feedback loop raises execution accuracy (EX) by 7.6 percentage points over the single-shot baseline; blind self-correction gains 4.5 percentage points. A verify-and-revise agent nearly matches the feedback loop (70.1% vs 70.5%) at higher cost. A ReActAgent with four tools (function calling) underperforms single-shot (58.0%), suggesting that autonomous tool use does not pay off on clean Spider schemas with this model. The analysis reveals a ceiling: execution feedback eliminates all runtime errors but converts them into silent wrong-result failures, which no agent in this study could fix without richer output-level feedback.

## 2. Related Work

The ReAct framework (Yao et al., 2023) interleaves reasoning and acting — generating an action, observing the environment's response, and updating the plan. Reflexion (Shinn et al., 2023) extends this with verbal self-reflection over past failures. Both suggest that grounding LLM outputs in real environment feedback improves performance on multi-step tasks.

In the text-to-SQL setting, DIN-SQL (Pourreza & Rafiei, 2023) decomposes queries into sub-problems and includes a self-review pass that asks the model to check its own output without execution. Self-debugging approaches (Chen et al., 2024) explicitly use execution traces and error messages as revision signals. Spider 1.0 (Yu et al., 2018) remains the standard benchmark; execution accuracy — whether the predicted query returns the same result set as the gold query — is the primary metric because it is invariant to surface-level SQL differences.

## 3. Method

The agent is structured around three components. `SQLExecutor` (src/tools.py) wraps SQLite execution, returning an `ExecutionResult` that holds either the result rows or an error message. `format_schema` renders a Spider database schema as CREATE TABLE statements, giving the model a compact representation of the available tables and columns. Five agents (src/agents.py) share the same abstract interface:

- **SingleShotAgent** calls the LLM once and returns the SQL as-is.
- **FeedbackLoopAgent** calls the LLM, executes the SQL via `SQLExecutor`, and on error appends the error message to the conversation and retries — up to `max_retries` attempts. Stops early on first successful execution.
- **BlindCorrectionAgent** calls the LLM once to generate SQL, then makes up to `max_retries − 1` additional calls asking the model to review its own output against the schema and question, without executing. Stops early if the revised SQL is identical to the current one (normalised to lowercase and collapsed whitespace).
- **VerifyAndReviseAgent** executes the SQL, then calls a separate verifier LLM to judge whether the result correctly answers the question. If the verifier says NO, it revises and retries. Falls back to the last clean execution if a revision errors.
- **ReActAgent** uses OpenAI function calling to give the LLM autonomous access to four tools: `execute_sql`, `sample_rows`, `describe_table`, and `get_distinct_values`. The model decides which tools to call and when to stop exploring and return SQL.

All five agents use the same model, system prompt, and schema formatter. They differ in whether and how feedback is provided, and whether the LLM can invoke tools autonomously.

## 4. Experimental Setup

**Dataset.** Spider 1.0 development set, filtered to Hard and Extra Hard questions (n = 224: 148 Hard, 76 Extra Hard). Hard questions involve nested subqueries or multi-condition GROUP BY; Extra Hard involves INTERSECT, UNION, or EXCEPT.

**Model.** Qwen3.5-9b via OpenRouter, temperature 0, max_tokens 2048.

**Metric.** Execution accuracy (EX): both gold and predicted SQL are executed against the SQLite database and results are compared as unordered row sets (frozensets). This is insensitive to column aliases and row ordering.

**Conditions.** Single-shot (`max_retries=1`), blind self-correction (`max_retries=3`), feedback loop (`max_retries=3`), verify-and-revise (`max_retries=3`), and ReActAgent (`max_retries=8`; higher budget to allow tool exploration before producing final SQL). The oracle baseline (gold SQL as prediction) verifies the evaluation infrastructure and achieves ~100% EX.

**Implementation note.** An early run with `max_tokens=512` produced 28% EX because Qwen3's internal reasoning tokens consumed the entire token budget, leaving the response content empty. Raising the limit to 2048 eliminated this artifact (0/224 empty predictions across all runs). Qwen3 occasionally prepends reasoning prose before the SQL in its response; the parser extracts the first top-level SELECT or WITH statement to handle this.

## 5. Results

| Agent | Tools | Correct | EX | vs single-shot |
|---|---|---|---|---|
| Single-shot | none | 141/224 | 62.9% | — |
| Blind self-correction | none | 151/224 | 67.4% | +4.5pp |
| Feedback loop | execute_sql | 158/224 | 70.5% | +7.6pp |
| Verify-and-revise | execute_sql | 157/224 | 70.1% | +7.2pp |
| ReActAgent | execute_sql, sample_rows, describe_table, get_distinct_values | 130/224 | 58.0% | −4.9pp |

**By hardness.** Hard questions: single-shot 64.2%, blind 65.5%, feedback 68.9%. Extra Hard questions improve more across the board — single-shot 60.5%, blind 71.1%, feedback 73.7% — consistent with Extra Hard queries more often producing syntax errors that both review and retry loops can address.

**By SQL pattern.** Table 2 shows EX broken down by the structural pattern present in the gold SQL. The fb-delta column shows feedback loop gain over single-shot.

| Pattern | n | Single-shot | Blind | Feedback | fb-delta |
|---|---|---|---|---|---|
| Nested SELECT | 157 | 63.7% | 67.5% | 72.6% | +8.9pp |
| JOIN | 105 | 52.4% | 59.0% | 62.9% | +10.5pp |
| NOT IN | 46 | 82.6% | 80.4% | 91.3% | +8.7pp |
| GROUP BY | 39 | 30.8% | 43.6% | 38.5% | +7.7pp |
| INTERSECT | 38 | 57.9% | 81.6% | 76.3% | +18.4pp |
| EXCEPT | 31 | 71.0% | 71.0% | 77.4% | +6.5pp |
| ORDER BY | 29 | 65.5% | 65.5% | 69.0% | +3.4pp |
| HAVING | 15 | 26.7% | 40.0% | 40.0% | +13.3pp |
| UNION | 11 | 45.5% | 36.4% | 54.5% | +9.1pp |

## 6. Analysis

**Failure breakdown.**

| Reason | Single-shot | Blind | Feedback | Verify | ReAct |
|---|---|---|---|---|---|
| execution_error | 32 | 14 | 0 | 1 | 0 |
| wrong_result | 51 | 59 | 66 | 66 | 94 |
| Total failures | 83 | 73 | 66 | 67 | 94 |

The single-shot run produced 32 execution errors and 51 wrong-result failures (83 total). Blind self-correction reduces execution errors to 14 — catching some syntax mistakes through review alone — while wrong-result rises to 59 (73 total failures). The feedback loop eliminates all 32 execution errors entirely and brings total failures to 66, all wrong-result. Verify-and-revise nearly matches feedback (70.1% vs 70.5%) at higher API cost, with no meaningful reduction in wrong-result. ReActAgent eliminates execution errors (0) but wrong-result jumps to 94 — the model uses tools to explore but returns exploration SQL as its final answer, losing track of the original question.

**Where feedback helps.** Feedback loop shows the largest gains on patterns that frequently produce runtime errors on a first attempt: NOT IN (+8.7pp), Nested SELECT (+8.9pp), JOIN (+10.5pp), and HAVING (+13.3pp). INTERSECT shows the largest fb-delta (+18.4pp over single-shot), consistent with INTERSECT/UNION/EXCEPT syntax being easy to get slightly wrong.

**Blind vs feedback.** Blind self-correction sits between the two: it partially reduces execution errors (32 → 14) and improves wrong-result cases where the model can catch its own mistake through re-reading the schema. Two patterns show blind beating feedback — INTERSECT (81.6% vs 76.3%) and GROUP BY (43.6% vs 38.5%) — but both have n ≈ 38, so a handful of examples separates them; these reversals should be treated as tentative, not structural.

**The ceiling of error-only feedback.** All 66 remaining failures in the feedback loop condition are wrong-result. The model receives no signal that its output is logically incorrect; retrying produces the same mistake. Closing this gap would require richer feedback — showing the model a sample of its returned rows alongside the expected result — which is not possible in a blind evaluation setting. This points to a fundamental limit: execution error feedback is a strong signal for syntactic failures and a silent one for logical failures.

**UNION** is the only pattern where blind self-correction degrades accuracy (45.5% → 36.4%), while feedback loop improves it (45.5% → 54.5%). Both movements are likely noise given the small sample (n = 11).

## 7. Limitations and Future Work

This study evaluates a single model (Qwen3.5-9b) with a fixed prompt. Conclusions may not generalise to larger or differently trained models. The hardness classifier is a simplified reimplementation of Spider's official one; misclassification of boundary cases could shift the Hard/Extra Hard split.

Two Qwen3-specific mitigations were required: the `/no-think` prompt suffix to suppress extended-reasoning mode, and raising `max_tokens` to 2048 to prevent the reasoning budget from consuming the entire response. These may not generalise to other models.

Future work should explore: (1) running the same comparison with a second model (GPT-4o-mini) to test whether stronger models show smaller feedback gains and whether ReAct-style tool use becomes effective at larger scale; (2) result-level feedback — showing the model a sample of its returned rows — to attack wrong-result failures; (3) evaluating on BIRD, where larger and noisier schemas would make schema retrieval and value lookup tools more impactful than on Spider.
