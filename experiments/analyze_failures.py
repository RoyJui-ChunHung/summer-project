#!/usr/bin/env python3
"""
analyze_failures.py — Break down eval results by SQL pattern.

Usage:
    python3 experiments/analyze_failures.py
"""

import json
import re
from pathlib import Path


# SQL pattern detectors (applied to gold_sql)

def has_intersect(sql):   return bool(re.search(r'\bINTERSECT\b', sql, re.I))
def has_union(sql):       return bool(re.search(r'\bUNION\b', sql, re.I))
def has_except(sql):      return bool(re.search(r'\bEXCEPT\b', sql, re.I))
def has_not_in(sql):      return bool(re.search(r'\bNOT\s+IN\b', sql, re.I))
def has_nested(sql):      return sql.upper().count('SELECT') > 1
def has_having(sql):      return bool(re.search(r'\bHAVING\b', sql, re.I))
def has_group_by(sql):    return bool(re.search(r'\bGROUP\s+BY\b', sql, re.I))
def has_join(sql):        return bool(re.search(r'\bJOIN\b', sql, re.I))
def has_order_by(sql):    return bool(re.search(r'\bORDER\s+BY\b', sql, re.I))

PATTERNS = {
    "INTERSECT":  has_intersect,
    "UNION":      has_union,
    "EXCEPT":     has_except,
    "NOT IN":     has_not_in,
    "Nested SELECT": has_nested,
    "HAVING":     has_having,
    "GROUP BY":   has_group_by,
    "JOIN":       has_join,
    "ORDER BY":   has_order_by,
}


def accuracy_by_pattern(results):
    stats = {}
    for name, fn in PATTERNS.items():
        subset = [r for r in results if fn(r["gold_sql"])]
        if not subset:
            continue
        correct = sum(r["ex_score"] for r in subset)
        stats[name] = {"correct": correct, "total": len(subset), "ex": correct / len(subset)}
    return stats


def load(path):
    with open(path) as f:
        return json.load(f)


def print_table(r1_stats, r3_stats, rb_stats, title):
    patterns = sorted(r1_stats.keys(), key=lambda k: -r1_stats[k]["total"])
    print(f"\n### {title}")
    print(f"{'Pattern':<18} {'n':>4}  {'1-shot':>7}  {'blind':>7}  {'feedback':>9}  {'fb-delta':>9}")
    print("-" * 65)
    for p in patterns:
        s1 = r1_stats[p]
        sb = rb_stats.get(p, s1)
        s3 = r3_stats.get(p, s1)
        delta = s3["ex"] - s1["ex"]
        sign = "+" if delta >= 0 else ""
        print(f"{p:<18} {s1['total']:>4}  {s1['ex']:>6.1%}  {sb['ex']:>6.1%}  {s3['ex']:>8.1%}  {sign}{delta:.1%}")


def main():
    r1 = load("experiments/run_retries1.json")
    r3 = load("experiments/run_retries3.json")
    rb = load("experiments/run_blind.json")

    results1 = r1["results"]
    results3 = r3["results"]
    resultsb = rb["results"]

    print("=" * 60)
    print("Failure Pattern Analysis")
    print(f"Model   : {r1['model']}")
    print(f"Dataset : Spider Hard+Extra Hard (n={r1['total']})")
    print("=" * 60)

    # Overall
    print(f"\n### Overall")
    print(f"  Single-shot   (max_retries=1): {r1['correct']}/{r1['total']} = {r1['ex']:.1%}")
    print(f"  Blind         (max_retries=3): {rb['correct']}/{rb['total']} = {rb['ex']:.1%}  delta +{rb['ex']-r1['ex']:.1%}")
    print(f"  Feedback loop (max_retries=3): {r3['correct']}/{r3['total']} = {r3['ex']:.1%}  delta +{r3['ex']-r1['ex']:.1%}")
    print(f"  Blind vs feedback: {rb['ex']-r3['ex']:+.1%}")

    # By hardness
    print(f"\n### By hardness")
    for label in ("hard", "extra"):
        s1 = [r for r in results1 if r["hardness"] == label]
        s3 = [r for r in results3 if r["hardness"] == label]
        sb = [r for r in resultsb if r["hardness"] == label]
        c1 = sum(r["ex_score"] for r in s1)
        c3 = sum(r["ex_score"] for r in s3)
        cb = sum(r["ex_score"] for r in sb)
        print(f"  {label:6s}  1-shot {c1}/{len(s1)} ({c1/len(s1):.1%})   "
              f"blind {cb}/{len(sb)} ({cb/len(sb):.1%})   "
              f"feedback {c3}/{len(s3)} ({c3/len(s3):.1%})")

    # By SQL pattern
    r1_stats = accuracy_by_pattern(results1)
    r3_stats = accuracy_by_pattern(results3)
    rb_stats = accuracy_by_pattern(resultsb)
    print_table(r1_stats, r3_stats, rb_stats, "Accuracy by SQL pattern (gold SQL)")

    # Failure reasons
    print(f"\n### Failure reasons")
    for label, results in [("1-shot", results1), ("blind", resultsb), ("feedback", results3)]:
        reasons = {}
        for r in results:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        print(f"  {label:10s}  " + "  ".join(f"{k}: {v}" for k, v in sorted(reasons.items())))

    # Patterns with worst accuracy (single-shot)
    print(f"\n### Hardest patterns (single-shot EX < 50%)")
    hard_patterns = [(p, s) for p, s in r1_stats.items() if s["ex"] < 0.5]
    hard_patterns.sort(key=lambda x: x[1]["ex"])
    for p, s in hard_patterns:
        sb = rb_stats.get(p, s)
        s3 = r3_stats.get(p, s)
        print(f"  {p:<18}  n={s['total']:>3}  1-shot {s['ex']:.1%}  blind {sb['ex']:.1%}  feedback {s3['ex']:.1%}")


if __name__ == "__main__":
    main()
