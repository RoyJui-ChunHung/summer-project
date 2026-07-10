# Week 1 Scope Memo

## Project Direction

Building a self-correcting SQL agent tested on Spider Hard questions with an open-source model.

**Agent loop:**
1. Receive natural language question + database schema
2. Generate SQL query
3. Execute against SQLite database
4. If error → read error message → revise SQL → retry (once)
5. Return final SQL and execution result

**Evaluation metric:** Execution Accuracy (EX) on Spider Hard dev set
**Baseline:** same model, same questions, no feedback loop (single-shot)
**Model:** Llama-3-8B-Instruct or Qwen2.5-Coder-7B (TBD based on local availability)

## What This Is Not

- Not a full agentic system (no schema exploration tools, no multi-step planning)
- Not fine-tuned (zero-shot or few-shot prompting only)
- Not tested on BIRD or Spider 2.0 (out of scope for 8 weeks)

## Open Decisions

- [ ] Which open-source model to use (depends on local GPU availability)
- [ ] How many retry attempts to allow (starting with 1)
- [ ] Whether to try schema filtering before generation
