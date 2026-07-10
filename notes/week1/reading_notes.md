# Week 1 Reading Notes

**Topic:** Introduction and Field Overview


## Paper 1: Data Agents: Levels, State of the Art, and Open Problems
*Luo et al., SIGMOD '26*

### Summary
Proposes a six-level autonomy taxonomy (L0–L5) for data agents, inspired by the SAE J3016 driving automation standard. At L0, all tasks are manual. L1 agents operate in a stateless prompt-response mode (e.g., suggest SQL). L2 agents perceive and interact with the environment — they can execute queries, read results, and catch errors. L3 agents autonomously orchestrate end-to-end workflows while humans act as supervisors. L4 and L5 are visionary: proactive self-governing agents and fully generative data scientists.

A key concept is **cascading error**: in L3+ systems, an early mistake propagates through the pipeline and corrupts final results.

### Main Taxonomy

| Level | Name | Who is in charge | Agent role |
|-------|------|-----------------|------------|
| L0 | No Autonomy | Human | None |
| L1 | Assistance | Human | Responder |
| L2 | Partial Autonomy | Human | Executor |
| L3 | Conditional Autonomy | Agent (supervised) | Orchestrator |
| L4 | High Autonomy | Agent | Proactive |
| L5 | Full Autonomy | Agent | Generative |

---

## Paper 2: A Survey of LLM-based Text-to-SQL
*Hong et al., arXiv:2406.08426, Nov 2025*

### Summary
Comprehensive review of text-to-SQL research from rule-based methods through deep learning to LLMs. Modern LLM-based systems use either **In-Context Learning (ICL)** — prompting a frozen model like GPT-4 — or **Fine-Tuning (FT)** — training an open-source model like LLaMA or Qwen. ICL achieves higher accuracy but requires API access and raises privacy concerns. FT keeps data local but underperforms ICL at the same model scale.

### ICL Method Categories (C1–C4)

| Category | What it does | Example |
|----------|-------------|---------|
| C1 Decomposition | Breaks complex questions into sub-problems | DIN-SQL (4-stage pipeline) |
| C2 Prompt Optimization | Improves input via better example selection or schema filtering | DAIL-SQL, CHESS |
| C3 Reasoning Enhancement | Guides model to reason before generating SQL | ACT-SQL, CHASE-SQL |
| C4 Execution Refinement | Runs SQL, reads error, revises | Self-Debugging, LEVER |

**C4 is the most relevant to this project** — it is the only category that actually interacts with the database rather than treating SQL generation as a closed-loop text task.

### FT Method Categories
- Enhanced Architecture (CLLMs — faster decoding)
- Pre-training (CodeS — SQL-specific pretraining)
- Data Augmentation (XiYan-SQL, SHARE)
- Multi-task Tuning (DTS-SQL, ROUTE)

---

## Comparison: Text-to-SQL vs. Database Assistants vs. Data Agents

| Dimension | Text-to-SQL (L1) | Database Assistants (L2) | Data Agents (L3+) |
|-----------|-----------------|--------------------------|-------------------|
| Scope | NL → SQL only | Query + limited DB interaction | DB management, preparation, analysis |
| Environment | Stateless | Execution-aware | Perceives and operates across systems |
| Human role | Problem definer | Pipeline designer | Supervisor |
| Failure mode | Localized error | Caught locally | Cascading across stages |

---

## Benchmark Ideas

**Idea 1 — Schema Linking Accuracy**
Given a question and a database with many irrelevant tables, test whether the model selects the correct tables and columns — without generating SQL. This isolates schema linking from query generation. Could be built by adding distractor tables to existing Spider schemas.

**Idea 2 — Error Recovery from Execution Feedback**
Give the model a deliberately broken SQL (derived from Spider ground-truth with injected errors) and measure fix rate by error type: syntax errors, wrong table names, type mismatches, ambiguous columns. Spider already provides ground-truth SQL, so error variants can be generated programmatically.

---

## Open Questions

**Q1 — Local deployment gap**
GPT-4 leads on SQL accuracy but company data cannot be sent to external APIs. Local open-source models lag significantly. Best strategies: (a) domain-specific fine-tuning on company schema + query history, (b) schema compression so small models waste less context, (c) ensemble voting across multiple small models.

**Q2 — Backtracking in decomposition pipelines**
If step 1 (schema linking) picks the wrong table, all downstream steps inherit the error. Standard decomposition systems cannot backtrack. Agentic systems (L3) like Spider-Agent and ReFoRCE maintain action history and can re-plan, but at significant API cost. CHASE-SQL takes a parallel approach: generate multiple independent paths and compare results.

**Q3 — Regression risk in execution refinement**
A model that misreads an error message may corrupt a SQL that was syntactically correct. LEVER mitigates this with a separate verifier. Simpler safeguard: after each revision, execute and check — if the revised SQL still errors, retry; if it now executes, lock it and stop revising. This prevents revision from making a working query worse.

---

## Final Project Direction

**Chosen direction:** Self-correcting SQL agent with execution feedback loop.

The agent implements a minimal generate → execute → revise cycle, targeting Spider Hard questions with a locally-deployed open-source model. The core contribution is a controlled comparison: does one round of execution feedback reliably improve accuracy on hard queries, and which error types are most recoverable?

This is scoped within L2 autonomy (execution-aware, human-designed pipeline) with one L3-style capability: reading and acting on database error messages.
