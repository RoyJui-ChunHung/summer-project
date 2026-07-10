# Week 2 Reading Notes & Database-Agent Loop Sketch

**Topic:** Foundational Agent and Tool-Use Methods
**Required Readings:**
1. Yao et al. — *ReAct: Synergizing Reasoning and Acting in Language Models* (ICLR 2023)
2. Schick et al. — *Toolformer: Language Models Can Teach Themselves to Use Tools* (Meta AI, 2023)

---

## Paper Summaries

### Paper 1 — Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models"

ReAct interleaves verbal reasoning ("thoughts") with task-specific actions, letting each inform the other: reasoning helps the model plan, track progress, and recover from exceptions, while acting lets it pull in fresh information from an external environment to ground that reasoning. The augmented action space is simply A = A ∪ L, where L is free-form language — a "thought" doesn't touch the environment but updates the context for the next step.

The paper compares four prompting setups: Standard (direct answer), CoT (reasoning only, no environment access), Act-only (actions without reasoning), and ReAct (both, interleaved). On knowledge-intensive QA (HotpotQA, Fever) using a Wikipedia search/lookup API, ReAct reduces hallucination relative to CoT (6% vs. 14% false-positive rate) because answers are grounded in retrieved text rather than purely the model's internal knowledge. On interactive decision-making tasks (ALFWorld, WebShop), ReAct substantially outperforms Act-only (71% vs. 45% success rate on ALFWorld) because without reasoning, the model loses track of state and repeats failed actions.

A key failure mode analysis categorizes errors into reasoning errors (wrong plan, including repetitive loops), search result errors (uninformative retrieval), hallucination, and label ambiguity. The authors also show a human-in-the-loop variant: a person can edit just the *thoughts* in a trajectory (not the actions) and redirect the agent's entire subsequent behavior — a cheap form of correction compared to relabeling actions directly.

### Paper 2 — Schick et al., "Toolformer: Language Models Can Teach Themselves to Use Tools"

Toolformer addresses a different problem: not how to interleave reasoning and acting at inference time, but how a model can learn, in a self-supervised way, when a tool call would actually help. The method has three steps: (1) sample candidate API call positions and arguments using a few in-context examples per tool; (2) execute the calls to get real results; (3) keep only the calls that measurably reduce the model's loss on the following tokens, compared to not calling the tool at all or calling it without using the result. The filtering criterion is `L⁻ - L⁺ ≥ τ`: a call is kept only if providing the tool's output reduces cross-entropy loss by at least threshold τ. The surviving calls are spliced into the original training text, and the model is fine-tuned on this augmented corpus.

Five tools are tested: a QA system, a calculator, Wikipedia search, a machine translator, and a calendar. After fine-tuning, a 6.7B GPT-J model with tool access outperforms a much larger GPT-3 (175B) on several benchmarks (e.g., math word problems), because it learns to call the calculator instead of guessing arithmetic internally. Crucially, the model decides *for itself* whether and when to invoke each tool — there's no hardcoded trigger condition.

The authors are explicit about limitations: Toolformer cannot chain tool calls (use one tool's output as another tool's input), cannot interact with a tool iteratively (e.g., refine a search query based on bad results), and is sample-inefficient (processing over a million documents yields only a few thousand useful calculator examples).

---

## Key Mechanism: How Each Paper Connects LMs to Actions/Tools

**ReAct's mechanism** is purely a *prompting and inference-time* strategy. There is no training involved in the base method — few-shot exemplars in the prompt show the model what a thought-action-observation trajectory looks like, and the model continues that pattern at inference time. The connection to tools is loose: "acting" just means emitting a structured string (e.g., `Search[entity]`) that an external controller parses and executes, then feeds the result back as the next observation. The mechanism that makes this work is the *interleaving itself*: thoughts are sparse but strategically placed to decompose goals, track subgoal completion, and decide what to do when something unexpected happens.

**Toolformer's mechanism** is a *data-construction and fine-tuning* strategy. The connection to tools is learned into the model's weights, not just demonstrated in a prompt. The critical design choice is the filtering criterion: an API call is kept only if `L⁻ - L⁺ ≥ τ`, i.e., providing the tool's output measurably helps predict the rest of the text better than not calling the tool (or calling it without showing the result). This turns tool-use learning into a self-supervised perplexity-reduction problem, requiring no human judgment about which calls are "good."

The two mechanisms are complementary rather than competing: ReAct is about *how to sequence* reasoning and acting within a single trajectory; Toolformer is about *how to decide whether a given tool call is worth making* in the first place, baked into model behavior via fine-tuning rather than prompting.

---

## Comparison: ReAct-style Traces vs. Toolformer-style Tool-Use Learning

| Dimension | ReAct | Toolformer |
|---|---|---|
| When the skill is acquired | Inference time, via few-shot prompting | Training time, via fine-tuning |
| Supervision needed | A handful of hand-written trajectories per task | A handful of examples per API, then self-supervised filtering |
| What's learned | A *sequencing pattern* (when to think vs. act) | A *calibration* of when a specific tool call helps |
| Multi-step / multi-tool chains | Yes — explicit, since the trajectory is the unit of design | No — tool calls are sampled independently, can't chain |
| Interactivity with tool output | Yes — next thought reacts to the observation | Limited — no iterative refinement of a single call |
| Generalizes to new inputs without retraining | Yes (new prompt) | Yes — new inputs generalize normally |
| Generalizes to new tools without retraining | Yes (new prompt) | No — new tools require re-running the fine-tuning pipeline |
| Cost model awareness | Not modeled | Not modeled (explicitly noted as a limitation) |

The practical takeaway: ReAct is better suited to *open-ended, multi-step problem solving* where the agent must adapt its plan as new information arrives — exactly the situation a database agent faces when a query fails and the next step depends on *why* it failed. Toolformer is better suited to *calibrating when a single, well-defined tool call is worth the cost* — closer to deciding whether to call `validate_result` at all, rather than how to recover from a bad query.

---

## Application to Database Interaction

Both papers map cleanly onto the L1→L2 transition discussed in Week 1 (Luo et al.) and the C4 execution-refinement category from Hong et al.'s text-to-SQL survey.

A pure L1 text-to-SQL system is structurally identical to ReAct's Standard or CoT baseline: it reasons (maybe) and then emits a final SQL string, with no observation step and no chance to revise. The moment a system executes the SQL, reads the error or result, and reasons about what to do next, it is running the ReAct loop with the database as the environment: `Thought → Act (run_sql) → Observation (result or error) → Thought (revise) → ...`. This is precisely the structure DIN-SQL, MAC-SQL, and CHESS implement, even though none of them cite ReAct directly — Hong et al.'s "execution refinement" category is a database-specific instance of the ReAct pattern.

Toolformer's contribution maps onto a narrower but practically important question: not all tool calls are equally worth making. A database agent has multiple available tools (schema lookup, query execution, result validation), and naively calling all of them on every turn is wasteful and can even introduce noise (per Toolformer's own finding that uninformative search results derail reasoning 23% of the time in ReAct's HotpotQA error analysis). Toolformer's filtering criterion suggests a database agent could, in principle, learn from its own trajectories which situations actually warrant a schema lookup versus when the agent already has enough context to write correct SQL directly — reducing unnecessary tool calls and the latency they add.

---

## Open Questions and Concerns

**Q1 — ReAct's repetitive-loop failure mode is exactly the risk in SQL error recovery.**
The ReAct paper shows that 47% of its failures on HotpotQA are reasoning errors, including a specific pattern where the model repeats the same failed thought-action sequence without realizing it's stuck. For a database agent that catches a SQL execution error and tries to fix it, this is a serious risk: if the fix doesn't address the root cause (e.g., misreading which column is ambiguous), the agent could loop — regenerate, fail the same way, regenerate again — without a built-in mechanism to detect and break the cycle. Neither paper proposes a robust solution beyond noting the problem; what would a concrete stopping criterion look like for a database agent (e.g., cap on retries, detecting near-identical SQL across attempts)?

**Q2 — Toolformer cannot chain tool calls, but a database agent loop intrinsically requires chaining.**
A realistic database task often needs `list_tables → describe_schema → run_sql → validate_result` in sequence, where the output of one tool determines the input to the next. Toolformer explicitly states this is outside its scope, since API calls are sampled and filtered independently in training. If a database agent were to use a Toolformer-style self-supervised approach to learn *when* to call each tool, would it need a fundamentally different training signal that accounts for dependencies between calls, or could independent per-tool filtering still work in practice if the tools are naturally sequential (e.g., the model rarely calls `run_sql` before `describe_schema` even without being told to chain them)?

**Q3 — Neither paper accounts for the cost or risk asymmetry between tool calls.**
In a database setting, `list_tables` and `describe_schema` are cheap, read-only, and low-risk. `run_sql` could be expensive (a slow query against a large table) or, in some real-world systems, have side effects if it's not a read-only connection. Toolformer's filtering criterion only considers whether a call helps predict future tokens — it doesn't weigh how expensive or risky the call is. For a final project benchmark on error recovery, should "successfully fixed the query" be the only metric, or should the number of `run_sql` attempts also count against a system, given that each failed attempt has a real cost in a production database?

---

## Database-Agent Loop Sketch

This sketch describes a minimal agent loop, structured as a ReAct-style thought-action-observation cycle, for the error-recovery direction outlined in the Week 1 scope memo.

**Tools:**
- `list_tables()` — returns the names of all tables in the connected database. Called at the start of a task when the agent has no prior context about the schema, to narrow down which tables are even relevant before requesting full schema detail.
- `describe_schema(table)` — returns column names, types, and keys for a specific table. Called once the agent has a candidate table from `list_tables` (or from the question itself) and needs column-level detail to write a correct SQL query, particularly to resolve ambiguous column names or check foreign key relationships before a join.
- `run_sql(query)` — executes a SQL query against the database and returns either a result set or an error message (syntax error, unknown column, type mismatch, etc.). Called once the agent has drafted a SQL query it believes is ready to execute; this is the step that produces the observation the agent reasons over next.
- `validate_result(result, question)` — a lightweight check (e.g., is the result set empty when it plausibly shouldn't be, does the result type match what the question implies) used after a successful execution, to catch cases where the SQL ran without error but is still semantically wrong. Called only after `run_sql` returns successfully, since there's nothing to validate if execution failed outright.

**Worked example** — question: *"Find the names of the top 3 customers by total spending this year."*

```
1. Thought: I need customer names and spending totals, but I don't know
   the schema yet. Let me check what tables exist.
   Act: list_tables()
   Observation: ["users", "orders", "products"]

2. Thought: Spending is probably in orders, names in users. I need their
   columns and how they join.
   Act: describe_schema("users"), describe_schema("orders")
   Observation:
     - users: [id (PK), name, email]
     - orders: [id, user_id (FK), total_amount, order_date]

3. Thought: I'll join users to orders on user_id, filter order_date to
   this year, sum total_amount per user, order descending, limit 3.
   Act: run_sql("SELECT u.name, SUM(o.total_amount) ...")
   Observation: Error — "column o.order_year does not exist"

4. Thought: I referenced a column that doesn't exist; the schema shows
   order_date, not order_year. I need to filter using order_date with
   a date function instead.
   Act: run_sql("SELECT u.name, SUM(o.total_amount) FROM users u
        JOIN orders o ON u.id = o.user_id
        WHERE strftime('%Y', o.order_date) = '2026'
        GROUP BY u.name ORDER BY SUM(o.total_amount) DESC LIMIT 3")
   Observation: [{"name": "Roy", "total": 5000}, ...]  (3 rows)

5. Thought: Execution succeeded. Before returning this, check whether
   the result actually answers the question.
   Act: validate_result(Observation, question)
   Observation: VALID — 3 rows, contains name and total as expected

Final Answer: "The top 3 customers by spending this year are: 1. Roy
($5,000) ..."
```

**Retry cap:** if step 4 fails again with a different error, the agent gets one more attempt referencing that specific error. If the regenerated SQL is near-identical to a prior failed attempt (a proxy for the repetitive-loop failure mode identified in ReAct's error analysis), or if the total `run_sql` call count reaches 3, the agent stops and reports the failure rather than continuing to retry. This caps the loop at a fixed maximum of 3 `run_sql` attempts per question.

This loop deliberately keeps scope narrow — a fixed retry cap rather than open-ended multi-step planning — consistent with the Week 1 plan to focus on making one error-recovery cycle work reliably before considering broader orchestration.
