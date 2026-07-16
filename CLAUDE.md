# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An 8-week independent study on LLM database agents. The deliverable is a self-correcting text-to-SQL agent (generate SQL → execute → read error → revise → retry) evaluated on Spider 1.0 Hard/Extra Hard questions with Qwen3.5-9b via OpenRouter. For current results, see the Progress section in `README.md` and the experiment log in `experiments/experiments.md` — those are the source of truth, not this file.

## Commands

Run everything from the repo root (scripts use relative paths like `data/spider` and `experiments/run_retries1.json`).

```bash
# Sanity-check the pipeline without API calls (gold SQL as prediction, ~100% EX)
python3 src/eval.py --oracle

# Single-shot baseline (no feedback loop)
python3 src/eval.py --max_retries 1 --output experiments/run_retries1.json

# Feedback loop (default: 3 attempts)
python3 src/eval.py --max_retries 3 --output experiments/run_retries3.json

# Quick iteration on a few examples
python3 src/eval.py --limit 10

# Compare the two runs by SQL pattern / hardness / failure reason
python3 experiments/analyze_failures.py
```

There are no tests, linters, or a dependency file. Python deps: `openai`, `python-dotenv`.

## Setup Requirements

- `OPENROUTER_API_KEY` must be set in `.env` (already gitignored) — LLM calls go through OpenRouter's OpenAI-compatible endpoint.
- `data/spider/` is gitignored; download Spider 1.0 from https://yale-lily.github.io/spider and unzip so that `data/spider/dev.json`, `tables.json`, and `database/<db_id>/<db_id>.sqlite` exist.

## Architecture

The agent and eval harness currently both live in `src/eval.py`:

- `agent_predict()` is the agent: it prompts the model with a formatted schema, executes the returned SQL against the SQLite db, and on `sqlite3.Error` feeds the error message back for another attempt. `max_retries=1` disables the loop — this one flag is the A/B experiment lever.
- `classify_hardness()` is a simplified reimplementation of Spider's hardness classifier, used to filter dev.json to Hard + Extra Hard only.
- Scoring is execution accuracy (EX): both gold and predicted SQL are executed and results compared as `frozenset`s of rows (order-independent). Failures are classified as `execution_error` (SQL raised) vs `wrong_result` (ran but wrong rows).
- `--output` writes a JSON with a `results` array of per-example records; `experiments/analyze_failures.py` consumes exactly that schema, so keep the record fields (`gold_sql`, `pred_sql`, `hardness`, `ex_score`, `reason`) stable when editing.
- To change models, edit the `MODEL` constant at the top of `src/eval.py`; nothing else needs to change.

## Known Gotchas

- `max_tokens` in `agent_predict()` must stay at 2048. An earlier run with 512 scored ~28% EX because Qwen3's internal reasoning tokens consumed the budget, leaving `content: None` and empty predictions (see "Bug Found" in `experiments/experiments.md`). Related mitigations in the code: the `/no-think` suffix in the prompt and the fallback to `msg.reasoning` when `content` is empty.
- Empty predicted SQL executes "successfully" and returns `frozenset()`, which can silently match nothing — the `pred_empty` field in results exists to catch this.

## Conventions

- Log every experiment in `experiments/experiments.md` (append below the marker line): date, model, dataset, exact command, results table, observations.
- Weekly reading notes go in `notes/week<N>/`.
- Keep the Progress checklist in `README.md` up to date when milestones complete.
