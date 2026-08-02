# Week 6 Benchmark Input Format & Reading Notes

Paper 1: RSL-SQL: Robust Schema Linking in Text-to-SQL Generation (Cao et al., 2024)
Paper 2: Data Ambiguity Strikes Back: How Documentation Improves GPT's Text-to-SQL (Huang et al., NeurIPS TRL Workshop 2023)

## Paper Summaries

**RSL-SQL.** Schema linking is a two-sided risk: it cuts noise but may drop necessary columns. RSL-SQL hedges this with four stages: (1) BSL — forward linking (LLM picks relevant cols from full schema) + preliminary SQL generation + backward linking (parse which cols the SQL used); union = simplified schema; 94% strict recall, 76→13 avg cols. (2) CIA — pre-generates expected elements, WHERE conditions, SQL keywords as context hints (+2.87pp, DeepSeek). (3) BSS — generates SQL from both full and simplified schema, executes both, LLM picks the better result (+1.63pp). (4) MTSC — syntax error or empty result → retry, +0.26pp (DeepSeek) / +0.78pp (GPT-4o). Final: 67.21% EX on BIRD dev (GPT-4o), 87.9% on Spider test; ~3× cheaper than E-SQL.

**Data Ambiguity.** Spider is clean; real-world databases (KaggleDBQA) have three data ambiguities beyond obscure column names: Value Consistency (format uniformity; "season" = "2009/2010" or "2009"?), Data Coverage (does this table contain all events?), Data Granularity (one row = one event, or can rows repeat?). These need offline documentation — schema or samples don't resolve them. With the query already disambiguated, adding data documentation lifts GPT-4 from 57.8% to 86.7% (+28.9pp, the paper's headline). Name descriptions barely help (+2.2pp) — GPT-4 already infers meanings; value consistency, coverage, and granularity docs provide the real gains.

## The Schema Grounding and Context-Selection Problem

**RSL-SQL's problem:** For large databases (BIRD avg 76 cols), full schema overloads the prompt with noise. Schema linking helps but risks dropping necessary columns. RSL-SQL's bidirectional approach answers: recall what the model actually used (backward) + what looks relevant (forward), then hedge with a full-schema fallback.

**Data Ambiguity's problem:** Even correct schema grounding fails when the data itself is ambiguous. Knowing column names is insufficient — the model needs to know whether "season" means one year or two, whether this table covers all events or a subset, and whether COUNT(*) is safe or needs DISTINCT. This documentation cannot be inferred from schema or samples alone.

## Schema-Only vs. Documentation-Enhanced Context

| Dimension | Schema-only | Documentation-enhanced |
|---|---|---|
| What is provided | Table/column names + foreign keys | + value consistency, data coverage, data granularity docs; or + column descriptions + value samples |
| What it resolves | Structural relationships between tables | Data semantics: format assumptions, scope of tables, row-level meaning |
| Failure mode | Model guesses wrong values, joins wrong tables, uses COUNT(*) when DISTINCT needed | Preparation cost: someone must document each database; impractical at scale |
| KaggleDBQA accuracy | 57.8% (query disambiguated, schema-only) | 86.7% (query + data disambiguation) |
| Spider applicability | Works well — Spider is clean and structured | Less needed; Spider has no catalog and minimal value ambiguity |
| RSL-SQL approach | BSL: full schema as fallback; simplified schema as primary | CIA adds column descriptions + pre-generated SQL components as contextual hints |

Schema-only answers "what columns exist" but not "what the data means". Documentation closes the latter gap. For Spider (clean, synthetic) schema-only is mostly sufficient. For BIRD and real-world databases, documentation or retrieval-augmented context is necessary.

## How Ambiguity Appears in Database Questions and Schemas

**Query ambiguity (term + output schema):** the question "which year has the most matches" doesn't specify whether year means start or end of a season, or whether the output should include the match count. RSL-SQL's CIA pre-generates expected WHERE conditions to partially resolve this.

**Value ambiguity:** "directly funded" in the question vs "Directly funded" in the database. CHESS IR resolves this with LSH value search. RSL-SQL's backward linking can recall the correct column but still leaves the LLM to guess the string format.

**Coverage ambiguity:** two tables may have overlapping or mutually exclusive records. Without documentation, the model might join when it should union, or use one table when both are needed.

**Granularity ambiguity:** COUNT(*) vs COUNT(DISTINCT x). This is the silent wrong-result class — the SQL runs, returns non-empty results, but is logically wrong. Neither execution feedback nor schema linking catches it. This is directly relevant to my 66 wrong-result failures in Exp 002.

**Schema ambiguity:** column names like SOC (School Ownership Code) or bwd (Bet&Win draw odds) carry no meaning from the name alone. Schema descriptions and CIA's column description component address this, but only if the documentation exists.

## Open Questions

**Q1.** RSL-SQL shows MTSC contributes only +0.26pp (DeepSeek) to +0.78pp (GPT-4o) on BIRD — my FeedbackLoopAgent's +7.6pp is much larger. The difference is that my baseline has no BSL or CIA, so the feedback loop is compensating for schema and context gaps that RSL-SQL already closed in earlier steps. Does this mean my +7.6pp is mostly recovering from bad initial SQL due to missing context, rather than demonstrating the value of execution feedback per se? Running FeedbackLoopAgent on top of a CIA-augmented prompt would isolate this.

**Q2.** Data Ambiguity shows name descriptions barely help (+2.2pp) because GPT-4 can infer meanings from column names. But the paper uses GPT-4 (~1.7T parameters). For Qwen3.5-9b, is this still true? A 9B model may rely more on explicit descriptions. The same question applies to RSL-SQL's CIA: the component text generated by the weaker DeepSeek model contributed only +0.46pp for SQL components (vs +1.11pp for GPT-4o). Model capability determines how much contextual augmentation actually helps.

**Q3.** RSL-SQL's backward linking parses the preliminary SQL to find which column names were used. If the preliminary SQL is wrong (wrong table, wrong column), backward linking recalls the wrong columns and the simplified schema will be missing the right ones. The paper acknowledges this and chooses exact column name matching over sqlglot parsing to reduce the damage. But for my 66 wrong-result failures, the preliminary SQL would often be logically wrong while syntactically valid — backward linking would confidently recall the wrong columns. Is there a way to detect that a preliminary SQL is probably wrong before using it for backward linking?

## Final-Project Benchmark Input Format

My benchmark is Spider 1.0 Hard + Extra Hard (n=224). Each example in the evaluation harness contains the following fields:

| Field | Included | Notes |
|---|---|---|
| Natural-language question | Yes | From Spider dev.json; original phrasing, no manual rephrasing or disambiguation |
| Database schema | Yes | Rendered by `format_schema()` as CREATE TABLE statements with column types and foreign keys (Code Representation Prompt format, DAIL-SQL). No column descriptions added. |
| Database values / sample rows | No | Spider databases are clean and small (~2K rows avg). Excluded to keep the input format identical across all four agents — the only variable is the correction mechanism. |
| Optional documentation | No | Spider has no catalog or data documentation. Data Ambiguity's three categories (value consistency, coverage, granularity) are not annotated in Spider. Adding manual documentation is out of scope for a one-person project. |
| Tool access | Yes (some agents) | `SQLExecutor.execute(sql)` — used by `FeedbackLoopAgent` and `VerifyAndReviseAgent`. Not used by `SingleShotAgent` or `BlindCorrectionAgent` by design. |
| Expected SQL | Yes | `gold_sql` from Spider dev.json. Used only for evaluation, never shown to the agent. |
| Expected answer | Yes (derived) | Executed `gold_sql` result stored as a frozenset of rows. EX score = 1 if the pred frozenset matches the gold frozenset (order-independent). |
| Evaluation metadata | Yes | Per example: `index`, `db_id`, `hardness`, `pred_sql`, `pred_empty`, `ex_score`, and `reason` (one of `correct` / `execution_error` / `wrong_result`). Verify runs also store `calls`, `verify_called`, `verify_flagged`. A separate SQL-pattern breakdown (nested / join / groupby / intersect / …) is computed post-hoc by `analyze_failures.py` from `gold_sql`, not stored in the record. |

**Deliberate omissions.** Value samples and documentation are excluded to keep the input format identical across all four agents — the only variable is the correction mechanism. Adding CIA-style hints would confound attribution. My benchmark measures correction-mechanism value given schema-only context: a conservative setting that underestimates what RSL-SQL-style augmentation would achieve.

**Captures well:** whether execution feedback beats blind self-correction, and whether `result_check` adds anything on top — clean because context is fixed.

**Misses:** value consistency and granularity ambiguity. My 66 wrong-result failures (Exp 002) likely include COUNT(*) vs COUNT(DISTINCT) errors and wrong-table joins — no agent has a signal to catch these. Honest ceiling above 70.5%.
