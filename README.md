# LLM Database Agent: Execution Feedback and Self-Correction

An 8-week independent study on how large language model agents interact with databases. The final project builds a self-correcting SQL agent that generates queries, executes them against a live database, reads error messages, and revises its output — tested on Spider Hard questions using an open-source model.

## Motivation

Traditional text-to-SQL systems generate SQL in a single shot. When the query fails — wrong table name, syntax error, mismatched column — the system has no way to recover. This project investigates whether a simple execution feedback loop can close that gap: run the query, observe the error, and try again.

## Final Project Scope

- **Agent loop:** generate SQL → execute → read error → revise → retry
- **Dataset:** Spider (Hard difficulty subset)
- **Model:** Qwen3.5-9b via OpenRouter
- **Evaluation:** execution accuracy with vs. without the feedback loop

## Repository Structure

```
.
├── notes/          # Weekly reading notes and memos
├── src/            # Agent implementation (weeks 5–7)
├── experiments/    # Benchmark scripts and results (week 8)
└── report/         # Final research report
```

## Course Schedule

| Week | Topic |
|------|-------|
| 1 | Introduction — text-to-SQL, database assistants, and data agents |
| 2 | Foundational agent and tool-use methods |
| 3 | Core benchmarks: Spider and BIRD |
| 4 | Representative LLM text-to-SQL methods |
| 5 | Agentic SQL systems with execution feedback |
| 6 | Schema grounding and retrieval |
| 7 | Enterprise and interactive benchmarks |
| 8 | Experiments and final report |

## Key References

- Hong et al. (2025). *A Survey of LLM-based Text-to-SQL.* arXiv:2406.08426
- Luo et al. (2026). *Data Agents: Levels, State of the Art, and Open Problems.* SIGMOD '26
- Pourreza & Rafiei (2023). *DIN-SQL.* NeurIPS '23
- Chen et al. (2024). *Teaching LLMs to Self-Debug.* ICLR '24

## Progress

- [x] Week 1 — reading notes complete → [`notes/week1/`](notes/week1/)
- [x] Week 2 — reading notes + agent loop sketch complete → [`notes/week2/`](notes/week2/)
- [x] Week 3 — reading notes complete → [`notes/week3/`](notes/week3/)
- [x] Week 4 — baseline selection reading notes (DIN-SQL, DAIL-SQL) → [`notes/week4/`](notes/week4/)
- [x] Week 5 — agentic-methods reading notes (MAC-SQL, CHESS) → [`notes/week5/`](notes/week5/)
- [x] OOP refactor: three-agent harness (`tools.py` / `agents.py` / `eval.py`) → [`src/`](src/)
- [x] Six-configuration experiment (Qwen3.5-9b, Spider Hard/Extra Hard, n=224): single-shot **62.9%** / blind **67.4%** / feedback loop **70.5%** / verify-and-revise **70.1%** / ReAct **58.0%** / pipeline **72.3%** → [`experiments/`](experiments/)
- [x] Verify-and-revise agent (Exp 003): execute → verify rows → revise if wrong; **70.1% EX**, net ≈ 0 new correct answers over feedback loop → [`experiments/run_verify.json`](experiments/run_verify.json)
- [x] ReActAgent with function calling (Exp 004): four tools, LLM decides when to call; **58.0% EX** — underperforms single-shot on Qwen3.5-9b → [`experiments/run_react.json`](experiments/run_react.json)
- [x] Pipeline agent (Exp 005): chains error feedback → blind review → verify; **72.3% EX** — best overall, +1.8pp over feedback loop → [`experiments/run_pipeline.json`](experiments/run_pipeline.json)
