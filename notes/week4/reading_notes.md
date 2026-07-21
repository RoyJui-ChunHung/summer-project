# Week 4 Baseline Method Selection & Reading Notes

## Papers I Read This Week

Paper 1: DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction (Pourreza & Rafiei, NeurIPS 2023)

Paper 2: Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation (Gao et al., the DAIL-SQL paper)

## Reading Notes

### Note 1: Where models actually fail (DIN-SQL error analysis)

DIN-SQL hand-labeled 500 few-shot failures on Spider, and schema linking was the biggest bucket at 37%, then JOIN (21%) and GROUP BY (13%) — only 3% were real syntax errors. This kind of confirms my Week 1 Idea 1: the model usually writes SQL that runs, it just grabs the wrong tables or columns. My favorite example: for "average and maximum capacities for all stadiums", it picked a column literally named "average" instead of computing avg(capacity). Exactly the failure I want my agent to catch.

### Note 2: Decomposition works, but schema linking is still the bottleneck

Their pipeline is 4 modules: schema linking, classification & decomposition (easy / non-nested / nested), SQL generation with NatSQL, and self-correction. It hit 85.3% EX on Spider test with GPT-4, beating fine-tuned models. But the interesting part is Figure 4: even WITH a dedicated schema-linking module, schema linking is still the biggest remaining failure — so decomposing helps, but doesn't fix step-one-goes-wrong (my Week 1 Q2).

### Note 3: Self-correction is blind, not execution-based

Something I didn't expect: DIN-SQL's self-correction never actually runs the SQL. It's zero-shot — basically "here's the SQL, fix any bugs" — in two flavors: a generic prompt that assumes the code is buggy, and a gentle one that just asks it to double-check. Generic worked better for CodeX, gentle for GPT-4, and for GPT-4 the generic prompt actually HURT (70.0 vs 74.2). Which is exactly my Week 1 Q3 worry: tell a strong model its correct SQL is buggy and it may break it. My agent uses real execution feedback instead, so this gives me a natural baseline to beat.

### Note 4: Prompt design matters way more than I assumed (DAIL-SQL)

DAIL-SQL systematically benchmarked question representation, example selection, and example organization. Takeaways I'll reuse: Code Representation Prompt (schema as CREATE TABLE) works best for open-source models, probably because it looks like what they were trained on; foreign keys help JOIN prediction; "with no explanation" consistently helps, while "Let's think step by step" is super unstable for text-to-SQL (up to -26% on some models!). Their final recipe hit 86.6% on Spider, beating DIN-SQL with way fewer tokens.

### Note 5: Open-source models + fine-tuning (this one matters most for us)

Since company data can't leave our systems (Week 1 Q1), DAIL-SQL's open-source experiments are the part that matters most for me. Raw open-source models were way behind: even CodeLLaMA-34B only hit 68.5% zero-shot vs ~83% for GPT-4 few-shot. After fine-tuning on Spider's training set, LLaMA-13B jumped to 68.6% EX, on par with TEXT-DAVINCI-003. Two catches though: (1) training corpus beats size — CodeLLaMA-34B beat LLaMA-2-70B by ~20% just from code data; (2) fine-tuned models basically LOSE in-context learning, adding examples makes them worse. So fine-tuning is not free.

## Comparing Direct, Schema-Aware, and Decomposed Prompting

Direct prompting: throw question + schema at the model in one call and take whatever comes out. Schema-aware: still one call, but you engineer the input (CREATE TABLE format, explicit foreign keys, "with no explanation"). Decomposed: split the task into stages, each with its own prompt.

| Strategy | Representative method | Reported EX (Spider) | Split |
|---|---|---|---|
| Direct prompting | Zero-shot GPT-4 (DIN-SQL, Table 1) | 64.9% | dev |
| Schema-aware prompting | DAIL-SQL: CR_P schema + foreign keys + "with no explanation" rule | 86.6% | test |
| Decomposed prompting | DIN-SQL: 4-module pipeline (schema linking, classification, generation, self-correction), GPT-4 | 74.2% / 85.3% | dev / test |

One caveat: these numbers mix dev and test and come from different setups, so treat this table as a rough magnitude reference, not a real comparison (see the fairness rules below). The takeaway I trust: schema representation + decomposition close most of the ~65% to ~86% gap, and DAIL-SQL gets there with way fewer tokens.

## What Makes a Baseline Fair and Useful

The meta-rule: numbers from different papers just aren't comparable — splits differ (DIN-SQL headlines test at 85.3% but ablates on dev), hardness classifiers differ — so published numbers are context, not baselines. Fair comparisons have to be re-run by me, under one harness. Within that: (a) one variable at a time — my baselines share model and prompting setup (zero-shot); only the correction mechanism changes. (b) Report cost, not just accuracy — DAIL-SQL beats DIN-SQL with way fewer tokens, so EX alone can hide a bad trade. (c) Don't mix training regimes — fine-tuned models lose in-context learning, so pitting them against few-shot setups isn't a fair comparison. (d) Tune the correction prompt per model — generic helped CodeX but hurt GPT-4 (70.0 vs 74.2), so I need to find the right flavor for Qwen3.5 first (Q2), or my blind-correction baseline is a strawman.

## Open Questions

Q1: DIN-SQL fixes SQL without ever running it; my agent fixes SQL using real error messages. But execution feedback only tells you about errors that crash. A schema-linking mistake usually runs fine and just silently returns the wrong answer — so my loop might mostly fix the 3% invalid-SQL bucket while missing the 37% schema-linking bucket. Do I need a second signal, like checking whether the result is empty or weirdly shaped, to catch silent failures?

Q2: The generic vs. gentle result depended on the model (generic for CodeX, gentle for GPT-4). I honestly have no idea where Qwen3.5 lands. Feels cheap to test though: run both prompts on the same failed queries and compare — maybe even a mini-experiment inside my benchmark?

Q3: DAIL selection needs a preliminary model to guess an approximate SQL first, then picks examples similar to it. Feels chicken-and-egg: if my local model's first guess is bad, it retrieves examples similar to the wrong query (their Upper Limit numbers show the gap). Is there a cheaper selection signal that doesn't need a decent first guess?

## Updated Project Direction

The Week 1 plan still stands: generate SQL, run it, read the error, fix it. But these two papers changed some details.

First, prompting: I'll go with Code Representation Prompt + foreign keys + "with no explanation" for Qwen3.5 — DAIL-SQL showed that combo is the safest bet for open-source models, no reason to hand-roll my own format and lose free accuracy.

Second, baselines: I'm going with three. All of them share the same model (Qwen3.5), the same prompt (Code Representation + foreign keys + "with no explanation"), and the same databases — rule (a) above — so the only thing that changes is the correction mechanism.

**Baseline 1 — Single-shot direct prompting.** Input: question + CREATE TABLE schema with foreign keys; output: one SQL query, no revision. Schema yes / decomposition no / execution feedback no / self-correction no. This is the floor: whatever the other two gain over it is what correction actually buys.

**Baseline 2 — Blind self-correction (DIN-SQL style).** Input: question + schema + the model's own draft SQL; output: a revised SQL, without ever running the draft. Schema yes / decomposition no / execution feedback no / self-correction yes (gentle vs. generic, picked per Q2). This one isolates whether real execution matters: if blind correction does just as well as my loop, then talking to the database adds nothing.

**Baseline 3 — Execution feedback loop (my agent).** Input: question + schema, with the database's error message appended on failure, up to 3 tries; output: final SQL. Schema yes / decomposition no / execution feedback yes / self-correction yes, grounded in real errors. This is the treatment: 1 vs. 3 is the total effect of the loop, 2 vs. 3 is what the execution signal itself is worth. If it can't beat blind correction, the whole agent idea is in trouble — so that's the first experiment to run.

Third, scope check: the loop stays on one error family for now (syntax / wrong table names — the ones that actually throw). But DIN-SQL's error analysis says the real prize is schema-linking failures that don't throw. If the basic loop works early, the stretch goal becomes "detect silent wrong-result failures" — honestly a harder and more interesting problem.
