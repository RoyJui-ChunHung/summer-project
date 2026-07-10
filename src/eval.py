#!/usr/bin/env python3
"""
eval.py — Evaluate a text-to-SQL agent on Spider Hard/Extra Hard questions.

Usage:
    python src/eval.py --spider_dir data/spider

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
  3. Calls agent_predict() to get a predicted SQL.
  4. Executes the predicted SQL and compares results.
  5. Reports Execution Accuracy (EX).

Right now agent_predict() is a stub that returns the gold SQL (oracle baseline,
should give 100% EX). Replace it with your actual agent once implemented.
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional


# Hardness classification
def classify_hardness(sql_dict: dict) -> str:
    """
    Classify a SQL query using Spider's parsed SQL dict (the 'sql' field in dev.json).
    Returns: 'easy' | 'medium' | 'hard' | 'extra'

    This is a simplified version of Spider's official hardness classifier.
    For exact replication, use evaluation.py from the Spider repository.
    """
    # Extra Hard: INTERSECT / UNION / EXCEPT at the top level
    if sql_dict.get("intersect") or sql_dict.get("union") or sql_dict.get("except"):
        return "extra"

    # Check for nested SELECT inside WHERE or HAVING conditions
    def has_nested(cond_list):
        for i, item in enumerate(cond_list):
            if i % 2 == 0 and isinstance(item, list) and len(item) > 3:
                if isinstance(item[3], dict):   # nested SQL dict
                    return True
        return False

    nested_in_where = has_nested(sql_dict.get("where", []))
    nested_in_having = has_nested(sql_dict.get("having", []))

    num_select = len(sql_dict.get("select", [False, []])[1])
    num_where = len([c for i, c in enumerate(sql_dict.get("where", [])) if i % 2 == 0])
    has_group_by = bool(sql_dict.get("groupBy"))
    has_having = bool(sql_dict.get("having"))
    has_order_by = bool(sql_dict.get("orderBy"))

    # Hard: any nested subquery, or complex multi-condition GROUP BY
    if nested_in_where or nested_in_having:
        return "hard"
    if num_select > 2 or num_where > 2 or (has_group_by and num_where > 1):
        return "hard"

    # Medium: aggregation, ordering, or multiple conditions
    if num_select > 1 or num_where > 1 or has_group_by or has_having or has_order_by:
        return "medium"

    return "easy"


# SQL execution
def execute_sql(db_path: Path, sql: str) -> Optional[frozenset]:
    """
    Run SQL against a SQLite database.

    Returns a frozenset of row tuples so comparison is order-independent,
    or None if the query raises an exception.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return frozenset(rows)
    except Exception:
        return None


# Agent (replace this once implemented)

def agent_predict(question: str, db_id: str, db_path: Path, schema: dict) -> str:
    """
    Given a natural language question and database info, return a predicted SQL.

    Args:
        question:  the natural language question
        db_id:     database name (e.g. "concert_singer")
        db_path:   path to the .sqlite file
        schema:    the tables dict entry for this db_id (from tables.json)

    Returns:
        A SQL string.

    TODO: replace this stub with the actual ReAct-style agent.
    For now it raises NotImplementedError so the eval loop falls back to
    oracle mode (gold SQL) and we can verify the infrastructure works.
    """
    raise NotImplementedError


# Evaluation loop

def load_schema(spider_dir: Path) -> dict:
    """Load tables.json and index by db_id."""
    with open(spider_dir / "tables.json") as f:
        tables = json.load(f)
    return {t["db_id"]: t for t in tables}


def evaluate(spider_dir: Path, split: str = "dev", oracle: bool = False) -> None:
    dev_file = spider_dir / f"{split}.json"
    db_root  = spider_dir / "database"

    print(f"Loading {dev_file} ...")
    with open(dev_file) as f:
        examples = json.load(f)

    schema_index = load_schema(spider_dir)

    # Filter to Hard + Extra Hard
    hard_examples = [
        ex for ex in examples
        if classify_hardness(ex["sql"]) in ("hard", "extra")
    ]

    print(f"Total dev examples : {len(examples)}")
    print(f"Hard + Extra Hard  : {len(hard_examples)}")
    print()

    total, correct = 0, 0
    failures = []

    for i, ex in enumerate(hard_examples):
        question = ex["question"]
        gold_sql = ex["query"]
        db_id    = ex["db_id"]
        db_path  = db_root / db_id / f"{db_id}.sqlite"

        if not db_path.exists():
            print(f"[SKIP] database not found: {db_path}")
            continue

        gold_result = execute_sql(db_path, gold_sql)
        if gold_result is None:
            print(f"[SKIP] gold SQL failed for db={db_id}: {gold_sql[:60]}")
            continue

        # Get predicted SQL (fall back to oracle if agent not implemented)
        if oracle:
            pred_sql = gold_sql
        else:
            try:
                schema = schema_index.get(db_id, {})
                pred_sql = agent_predict(question, db_id, db_path, schema)
            except NotImplementedError:
                print("agent_predict() not implemented — running in oracle mode.")
                print("To test the pipeline, we use gold SQL as the prediction.")
                print("Replace agent_predict() in src/agent.py when ready.\n")
                pred_sql = gold_sql
                oracle = True   # suppress message for remaining examples

        pred_result = execute_sql(db_path, pred_sql)
        ex_score    = int(pred_result is not None and pred_result == gold_result)

        total   += 1
        correct += ex_score

        if ex_score == 0:
            failures.append({
                "index":    i,
                "question": question,
                "db_id":    db_id,
                "gold_sql": gold_sql,
                "pred_sql": pred_sql,
                "reason":   "execution_error" if pred_result is None else "wrong_result",
            })

        if (i + 1) % 50 == 0:
            pct = correct / total if total else 0
            print(f"  [{i+1:4d}/{len(hard_examples)}]  EX so far: {correct}/{total} ({pct:.1%})")

    # Summary
    print("=" * 55)
    print(f"Spider Hard — Execution Accuracy ({split} set)")
    print(f"  Correct : {correct}")
    print(f"  Total   : {total}")
    if total > 0:
        print(f"  EX      : {correct / total:.1%}")
    print("=" * 55)

    if failures:
        print(f"\nSample failures (first 3 of {len(failures)}):")
        for f in failures[:3]:
            print(f"  [{f['index']}] {f['question']}")
            print(f"       db    : {f['db_id']}")
            print(f"       gold  : {f['gold_sql'][:80]}")
            print(f"       pred  : {f['pred_sql'][:80]}")
            print(f"       reason: {f['reason']}")
            print()


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
        help="Run oracle baseline: use gold SQL as prediction (should give ~100% EX)",
    )
    args = parser.parse_args()

    if not (args.spider_dir / "dev.json").exists():
        print(f"ERROR: {args.spider_dir / 'dev.json'} not found.")
        print("Download Spider 1.0 from https://yale-lily.github.io/spider")
        print(f"and unzip it into {args.spider_dir}/")
        raise SystemExit(1)

    evaluate(args.spider_dir, args.split, args.oracle)
