# Week 3 Reading Notes

**Topic:** Core Database Benchmarks — Spider and BIRD

---

## Paper 1 — Yu et al., "Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task" (EMNLP 2018)

### Summary

Spider introduces the first large-scale, cross-domain text-to-SQL benchmark where the databases in the test set are entirely unseen during training. Prior datasets (ATIS, GeoQuery, WikiSQL) shared one of two fatal flaws: either they used a single database for both train and test (allowing models to memorize SQL templates rather than learn semantic parsing), or they restricted queries to simple single-table SELECT/WHERE patterns with no joins, aggregations, or nesting. Spider addresses both simultaneously.

The dataset contains 10,181 questions and 5,693 unique complex SQL queries across 200 databases spanning 138 domains, written by 11 CS students over ~1,000 man-hours. The annotation protocol enforces full SQL pattern coverage per database (SELECT, WHERE, GROUP BY, HAVING, ORDER BY, LIMIT, JOIN, INTERSECT, EXCEPT, UNION, nested queries) and SQL consistency (annotators converge on a single canonical form for semantically equivalent queries).

The key experimental finding: even the best 2018 model (TypeSQL) achieves only **8.0% Exact Match under the database split**, compared to 34.4% under the example split — a dramatic drop that proves the models were memorizing schemas, not learning to generalize. WHERE clause prediction fails most severely across all models.

### Hardness Criteria

Spider defines four hardness levels based on SQL structural complexity:

| Level | Definition |
|-------|-----------|
| Easy | Single SELECT column, no aggregation, no JOIN |
| Medium | Multiple columns or simple aggregation, one JOIN |
| Hard | 2+ SELECT columns, 2+ WHERE conditions AND GROUP BY 2 cols, or EXCEPT/nested |
| Extra Hard | INTERSECT, UNION, EXCEPT, nested subqueries, multiple of the above |

This is a **syntax-based** difficulty definition — harder SQL structure, harder level — regardless of whether the natural language question is semantically ambiguous.

### Evaluation Metrics

- **Component Matching (F1):** F1 score comparing predicted vs. gold as bags of SQL components (SELECT, WHERE, GROUP BY, ORDER BY, KEYWORDS) — order-insensitive.
- **Exact Match (EM):** All components must match exactly. A query is correct only if every clause is correct.
- **Execution Accuracy (EX):** The predicted SQL executes to the same result as the gold SQL. Can produce false positives (two semantically different queries returning the same value, e.g., `NULL`). Spider's 2018 version provides gold condition values to enable EX.

---

## Paper 2 — Li et al., "Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQL" (NeurIPS 2023)

### Summary

BIRD (BIg bench for laRge-scale Database grounded text-to-SQL) is motivated by the observation that Spider's databases are toy-sized — averaging ~2K rows per database — whereas real-world databases have millions of rows with messy, abbreviated, domain-specific values that a model cannot understand from schema names alone. By 2023, the top Spider leaderboard entry reached 85.3% EX, which might suggest the problem is solved. BIRD demonstrates it is not.

BIRD contains 12,751 text-to-SQL pairs over 95 databases with a total size of **33.4 GB** (averaging 549K rows per database), spanning 37 professional domains sourced from Kaggle and CTU Prague Relational Learning Repository. Three distinct challenges are introduced that Spider does not capture:

1. **Dirty and noisy database values** — salary stored as `"US$57,500.00"` (TEXT), requiring `CAST(REPLACE(SUBSTR(T1.salary, 4), ',', '') AS REAL)` to compute an average. The schema name `salary` alone does not reveal the data type mismatch.

2. **External knowledge grounding** — questions require knowledge not present in the schema. Example: *"What is the winning rate of Boston Celtics in 2000?"* The definition of "winning rate" (`wins / (wins + losses)`) is provided as an evidence sentence but is not in any column name or table. 70.1% of BIRD questions require value illustrations; 23.6% require domain knowledge.

3. **SQL execution efficiency** — BIRD proposes the **Valid Efficiency Score (VES)**, which rewards not just correctness but query speed: `VES = EX × sqrt(E(gold) / E(predicted))`. A correct but slow query (e.g., using a subquery with `IN` instead of a `JOIN`) scores below 1.0 on the relative efficiency component.

GPT-4 achieves only **54.89% EX** on BIRD's test set (with knowledge), far below human performance of **92.96%**. BIRD's error analysis (500 ChatGPT errors) finds: Wrong Schema Linking (41.6%), Misunderstanding Database Content (40.8%), Misunderstanding Knowledge Evidence (17.6%), Syntax Error (3.0%).

---

## Comparison: Spider vs. BIRD

| Dimension | Spider | BIRD |
|-----------|--------|------|
| # Databases | 200 | 95 |
| # Examples | 10,181 | 12,751 |
| Avg rows / DB | ~2K | 549K |
| Total DB size | Small | 33.4 GB |
| SQL complexity | High (nested, multi-join) | Moderate (but with value complexity) |
| Schema complexity | Multi-table, foreign keys | Similar, but with abbreviated names |
| External knowledge required | No | Yes (70.1% of questions) |
| Noisy/dirty values | No | Yes |
| Efficiency metric | No | VES |
| Best model EX (at publication) | 12.4% (2018 models) | 54.89% (GPT-4, 2023) |
| Human EX | Not reported | 92.96% |
| Difficulty definition | Syntax-based (SQL structure) | Multi-dimensional (question, knowledge, data, SQL complexity) |

The two benchmarks are **complementary**, not competing. Spider tests whether a model can generalize SQL structure to unseen schemas; BIRD tests whether a model can handle real-world database contents. A system could score well on Spider by generating correct query skeletons while still completely failing on BIRD because it cannot interpret dirty values or apply domain knowledge.

---

## Application to the Final Project

The final project targets **Spider Hard** questions, which is a meaningful choice for three reasons visible from these papers:

**Why Spider, not BIRD?**
Spider databases are small and clean, so the error-recovery loop can focus on SQL structure errors (wrong column, missing JOIN, incorrect aggregation) rather than value interpretation failures. BIRD's dominant error mode — misunderstanding database content (40.8%) and wrong schema linking (41.6%) — often produces *silently wrong* results: the SQL executes without error but returns wrong data. A ReAct-style error recovery loop that reads execution errors cannot detect or fix a semantically wrong result that executes cleanly. Spider's failure modes are more recoverable.

**Why the Hard subset specifically?**
Spider's hardness levels (defined by SQL structural complexity) directly map to which error types appear. Easy queries (single table, no aggregation) rarely produce syntax errors because the structure is trivial. Hard and Extra Hard queries involve GROUP BY, HAVING, nested subqueries, and multi-table JOINs — exactly the constructs where column references, table aliases, and aggregation scope errors are common and where an error message carries enough information to diagnose and revise.

**What the BIRD error analysis reveals about the validate_result tool:**
BIRD's Wrong Schema Linking errors (41.6%) — selecting `Street, City, Zip` instead of `StreetAbr` — produce SQL that executes successfully but returns wrong columns. These are precisely the cases `validate_result` is designed to catch: execution succeeded, but does the result shape (column names, row count, data type) match what the question implies? The BIRD error examples make this failure mode concrete and suggest what a lightweight validator should check.

---

## Open Questions

**Q1 — Spider's syntax-based hardness vs. BIRD's multi-dimensional difficulty: which predicts error recoverability?**
Spider's Hard/Extra Hard classification is based on SQL structural complexity (number of clauses, nesting depth). But recoverability from an execution error depends not on query complexity per se, but on whether the error message contains enough information to identify and fix the specific mistake. A Hard query that fails with `"no such column: o.order_year"` is easily recoverable (the error names the exact wrong reference). An Extra Hard query that fails with `"ambiguous column name: id"` in a 4-way JOIN may be unrecoverable without schema re-inspection. Neither Spider's nor BIRD's hardness metric captures this "error informativeness" dimension. For the final project, it may be worth categorizing Spider Hard errors not just by hardness level but by error message type, since that predicts whether one retry will succeed.

**Q2 — BIRD's external knowledge highlights a blind spot in execution-based error recovery: silent semantic failures.**
In BIRD, 40.8% of ChatGPT errors involve misunderstanding database content — the model generates SQL that executes without error but queries the wrong table or column. This is precisely the failure mode that the `run_sql → read error → revise` loop cannot detect, because no error is raised. On Spider, this failure mode is less common because column names are human-readable (Spider explicitly normalizes abbreviated column names like `stu_id` to `student_id`). But BIRD's finding is a warning for real deployment: if the project were extended to a production database, silent semantic failures might dominate, making execution-error feedback insufficient. The `validate_result` step in the planned agent loop is specifically the defense against this — but it requires a good definition of what "valid" means for each question type.

**Q3 — BIRD's VES metric raises a question that Spider's EX metric obscures: is a slower correct SQL better than a faster wrong one?**
VES only rewards valid SQLs (those that return the correct result) with an efficiency bonus — an incorrect SQL that executes quickly scores 0 on efficiency regardless. This is a sensible design choice for production systems, but it creates an implicit tension with the error-recovery strategy: should the agent prefer a simpler, faster SQL structure that is less likely to be wrong, or a more precise, potentially slower SQL that more exactly matches the question? For the final project, all evaluation is on Spider's clean databases where query performance is not a bottleneck, so VES is irrelevant. But for future work on BIRD, an agent that generates an efficient correct query on the first attempt is better than one that generates a correct-but-slow query after one retry — the retry cost (latency, compute) needs to be weighed against the efficiency gain.

---

## Benchmark Summary Table

| Property | Spider Easy | Spider Medium | Spider Hard | Spider Extra Hard | BIRD Simple | BIRD Challenging |
|----------|-------------|---------------|-------------|-------------------|-------------|------------------|
| Primary challenge | Schema lookup | Multi-table join | Nested/aggregation | Complex nesting | Value matching | External knowledge |
| Error recovery potential | Low (rarely fails) | Medium | High | Medium (complex to diagnose) | Low (silent failures) | Very low |
| Final project relevance | Baseline | Baseline | **Target** | Stretch | Out of scope | Out of scope |

---

## References

- Yu, T. et al. (2018). Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task. EMNLP 2018.
- Li, J. et al. (2023). Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs. NeurIPS 2023.
