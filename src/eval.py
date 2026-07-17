#!/usr/bin/env python3
"""
eval.py — Evaluate a text-to-SQL agent on Spider Hard/Extra Hard questions.

Usage:
    python3 src/eval.py --spider_dir data/spider

Expected directory layout (download from https://yale-lily.github.io/spider):
    data/spider/
        dev.json
        tables.json
        database/
            concert_singer/
                concert_singer.sqlite
            ...

The script:
  1. Loads dev.json and filters to Hard + Extra Hard questions.
  2. Executes the gold SQL to get the ground-truth result.
  3. Calls agent.predict() to get a predicted SQL.
  4. Executes the predicted SQL and compares results.
  5. Reports Execution Accuracy (EX).

Pass --oracle to use the gold SQL as the prediction (pipeline sanity check,
should give ~100% EX). Otherwise an Agent from agents.py calls the LLM.
"""

import argparse
import json
from pathlib import Path
from typing import Optional

from agents import Agent, FeedbackLoopAgent, SingleShotAgent
from tools import SQLExecutor


# Hardness classification

def classify_hardness(sql_dict: dict) -> str:
    """
    Classify a SQL query using Spider's parsed SQL dict (the 'sql' field in dev.json).
    Returns: 'easy' | 'medium' | 'hard' | 'extra'

    This is a simplified version of Spider's official hardness classifier.
    For exact replication, use evaluation.py from the Spider repository.
    """
    if sql_dict.get("intersect") or sql_dict.get("union") or sql_dict.get("except"):
        return "extra"

    def has_nested(cond_list):
        for i, item in enumerate(cond_list):
            if i % 2 == 0 and isinstance(item, list) and len(item) > 3:
                if isinstance(item[3], dict):
                    return True
        return False

    nested_in_where  = has_nested(sql_dict.get("where", []))
    nested_in_having = has_nested(sql_dict.get("having", []))

    num_select  = len(sql_dict.get("select", [False, []])[1])
    num_where   = len([c for i, c in enumerate(sql_dict.get("where", [])) if i % 2 == 0])
    has_group_by = bool(sql_dict.get("groupBy"))
    has_having   = bool(sql_dict.get("having"))
    has_order_by = bool(sql_dict.get("orderBy"))

    if nested_in_where or nested_in_having:
        return "hard"
    if num_select > 2 or num_where > 2 or (has_group_by and num_where > 1):
        return "hard"
    if num_select > 1 or num_where > 1 or has_group_by or has_having or has_order_by:
        return "medium"

    return "easy"


# Schema loading

def load_schema(spider_dir: Path) -> dict:
    """Load tables.json and index by db_id."""
    with open(spider_dir / "tables.json") as f:
        tables = json.load(f)
    return {t["db_id"]: t for t in tables}


# Evaluation loop

def evaluate(
    spider_dir:  Path,
    split:       str            = "dev",
    oracle:      bool           = False,
    limit:       int            = 0,
    agent:       Optional[Agent] = None,
    output_file: Optional[Path] = None,
) -> None:
    dev_file = spider_dir / f"{split}.json"
    db_root  = spider_dir / "database"

    print(f"Loading {dev_file} ...")
    with open(dev_file) as f:
        examples = json.load(f)

    schema_index = load_schema(spider_dir)

    hard_examples = [
        ex for ex in examples
        if classify_hardness(ex["sql"]) in ("hard", "extra")
    ]
    if limit:
        hard_examples = hard_examples[:limit]

    print(f"Total dev examples : {len(examples)}")
    print(f"Hard + Extra Hard  : {len(hard_examples)}")
    print()

    total, correct = 0, 0
    failures = []
    results  = []

    for i, ex in enumerate(hard_examples):
        question = ex["question"]
        gold_sql = ex["query"]
        db_id    = ex["db_id"]
        db_path  = db_root / db_id / f"{db_id}.sqlite"

        print(f"[{i+1}/{len(hard_examples)}] {db_id}: {question[:70]}")

        if not db_path.exists():
            print(f"  [SKIP] database not found: {db_path}")
            continue

        executor    = SQLExecutor(db_path)
        gold_result = executor.execute(gold_sql)
        if not gold_result.ok:
            print(f"  [SKIP] gold SQL failed for db={db_id}: {gold_sql[:60]}")
            continue

        if oracle:
            pred_sql = gold_sql
        else:
            schema   = schema_index.get(db_id, {})
            pred_sql = agent.predict(question, db_id, executor, schema)

        pred_result = executor.execute(pred_sql)
        ex_score    = int(pred_result.ok and pred_result.rows == gold_result.rows)

        total   += 1
        correct += ex_score

        record = {
            "index":      i,
            "question":   question,
            "db_id":      db_id,
            "hardness":   classify_hardness(ex["sql"]),
            "gold_sql":   gold_sql,
            "pred_sql":   pred_sql,
            "pred_empty": pred_sql.strip() == "",
            "ex_score":   ex_score,
            "reason":     "correct" if ex_score else (
                              "execution_error" if not pred_result.ok else "wrong_result"
                          ),
        }
        results.append(record)

        if ex_score == 0:
            failures.append(record)

        if (i + 1) % 50 == 0:
            pct = correct / total if total else 0
            print(f"  [{i+1:4d}/{len(hard_examples)}]  EX so far: {correct}/{total} ({pct:.1%})")

    # Summary
    if oracle:
        mode = "oracle"
    elif isinstance(agent, SingleShotAgent):
        mode = "single-shot (max_retries=1)"
    else:
        mode = f"feedback-loop (max_retries={agent.max_retries})"

    print("=" * 55)
    print(f"Spider Hard — Execution Accuracy ({split} set, {mode})")
    print(f"  Correct : {correct}")
    print(f"  Total   : {total}")
    if total > 0:
        print(f"  EX      : {correct / total:.1%}")
    print("=" * 55)

    if failures:
        empty_count = sum(1 for r in results if r["pred_empty"])
        print(f"\nEmpty predictions : {empty_count}/{total} ({empty_count/total:.1%})")
        print(f"\nSample failures (first 3 of {len(failures)}):")
        for f in failures[:3]:
            print(f"  [{f['index']}] {f['question']}")
            print(f"       db    : {f['db_id']}")
            print(f"       gold  : {f['gold_sql'][:80]}")
            print(f"       pred  : {f['pred_sql'].strip()[:80]}")
            print(f"       reason: {f['reason']}")
            print()

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "model":       agent.model if agent else "oracle",
            "split":       split,
            "max_retries": agent.max_retries if agent else None,
            "oracle":      oracle,
            "total":       total,
            "correct":     correct,
            "ex":          correct / total if total else 0,
            "results":     results,
        }
        with open(output_file, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\nResults saved to {output_file}")


# Entry point

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate on Spider Hard subset.")
    parser.add_argument(
        "--spider_dir", type=Path, default=Path("data/spider"),
        help="Path to the Spider dataset directory (default: data/spider)",
    )
    parser.add_argument(
        "--split", default="dev", choices=["dev", "train_spider"],
        help="Which split to evaluate (default: dev)",
    )
    parser.add_argument(
        "--oracle", action="store_true",
        help="Run oracle baseline: use gold SQL as prediction (should give ~100%% EX)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Only evaluate the first N Hard examples (0 = all)",
    )
    parser.add_argument(
        "--max_retries", type=int, default=3,
        help="Max LLM attempts per question (1 = single-shot, no feedback loop)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Save per-example results to this JSON file (e.g. experiments/run1.json)",
    )
    args = parser.parse_args()

    if not (args.spider_dir / "dev.json").exists():
        print(f"ERROR: {args.spider_dir / 'dev.json'} not found.")
        print("Download Spider 1.0 from https://yale-lily.github.io/spider")
        print(f"and unzip it into {args.spider_dir}/")
        raise SystemExit(1)

    if args.oracle:
        agent = None
    elif args.max_retries == 1:
        agent = SingleShotAgent()
    else:
        agent = FeedbackLoopAgent(max_retries=args.max_retries)

    evaluate(args.spider_dir, args.split, args.oracle, args.limit, agent, args.output)
