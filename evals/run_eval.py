"""Eval runner using execution accuracy.

Reads evals/eval_set.jsonl, calls the agent at AGENT_URL on each question,
then compares the agent's SQL output to the gold SQL by *executed rows*
(canonicalized: sorted, stringified, None-coerced to empty).

Helpers (run_sql / canonicalize / matches) are provided. You implement
eval_one() and summarize().

Run:
    uv run python evals/run_eval.py --out results/eval_baseline.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_FILE = ROOT / "evals" / "eval_set.jsonl"
DEFAULT_OUT_FILE = ROOT / "results" / "eval_baseline.json"
DB_DIR = ROOT / "data" / "bird"
AGENT_URL_DEFAULT = "http://localhost:8001/answer"


# ---------- Helpers (provided) -----------------------------------------

def run_sql(db_id: str, sql: str, timeout: float = 5.0) -> tuple[bool, list[tuple] | None, str | None]:
    """Run sql against db_id in read-only mode. Returns (ok, rows, error)."""
    path = DB_DIR / f"{db_id}.sqlite"
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout) as conn:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            return True, rows, None
    except Exception as e:  # noqa: BLE001
        return False, None, f"{type(e).__name__}: {e}"


def canonicalize(rows: list[tuple] | None) -> list[tuple] | None:
    """Sort rows; coerce cells to str; None -> ''."""
    if rows is None:
        return None
    return sorted(tuple("" if c is None else str(c) for c in row) for row in rows)


def matches(gold_rows: list[tuple] | None, pred_rows: list[tuple] | None) -> bool:
    if gold_rows is None or pred_rows is None:
        return False
    return canonicalize(gold_rows) == canonicalize(pred_rows)


# ---------- Implement these (Phase 5) ----------------------------------

def eval_one(question: dict, agent_url: str) -> dict:
    """Score one question. Return a dict capturing per-iteration correctness."""
    q_text = question["question"]
    db_id = question["db_id"]
    gold_sql = question.get("gold_sql", question.get("SQL", ""))
    
    # Get ground truth rows
    _, gold_rows, _ = run_sql(db_id, gold_sql)

    payload = {
        "question": q_text,
        "db": db_id,
        "tags": {"env": "eval_baseline"}
    }

    # Initialize results tracking (Assuming max 3 iterations based on assignment)
    correct_per_iter = {1: False, 2: False, 3: False}
    agent_failed = False
    history = []

    try:
        response = httpx.post(agent_url, json=payload, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        history = data.get("history", [])
    except Exception as e:
        agent_failed = True
        error_msg = str(e)

    if not agent_failed and history:
        # Evaluate each step in the agent's generation history
        for i in range(1, 4):
            if i <= len(history):
                step_sql = history[i - 1].get("sql", "")
            else:
                # Carry-forward: use the last available SQL if the agent stopped early
                step_sql = history[-1].get("sql", "")
            
            _, pred_rows, _ = run_sql(db_id, step_sql)
            correct_per_iter[i] = matches(gold_rows, pred_rows)

    return {
        "question": q_text,
        "db_id": db_id,
        "error": error_msg if agent_failed else None,
        "correct_per_iteration": correct_per_iter
    }


def summarize(results: list[dict]) -> dict:
    """Aggregate per-question results.

    Per-iteration carry-forward: if the agent terminated at iteration j < k
    (verify said ok at j, or it hit MAX_ITERATIONS at j < k), treat the
    question's iteration-k result as identical to its iteration-j result.
    The agent stopped emitting; whatever it had at termination is what
    would have been served had we polled at iteration k.
    """
    total = len(results)
    if total == 0:
        return {"total": 0}

    pass_counts = {1: 0, 2: 0, 3: 0}

    for r in results:
        correctness = r.get("correct_per_iteration", {})
        for i in [1, 2, 3]:
            # Accommodate integer or string keys
            if correctness.get(i) or correctness.get(str(i)):
                pass_counts[i] += 1

    return {
        "total_questions": total,
        "overall_accuracy": pass_counts[3] / total,
        "pass_rate_iter_1": pass_counts[1] / total,
        "pass_rate_iter_2": pass_counts[2] / total,
        "pass_rate_iter_3": pass_counts[3] / total,
    }


# ---------- Main (provided) --------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_FILE)
    parser.add_argument("--agent-url", default=AGENT_URL_DEFAULT)
    args = parser.parse_args()

    questions = [json.loads(line) for line in args.eval_set.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(questions)} eval questions from {args.eval_set}")

    results: list[dict] = []
    t0 = time.monotonic()
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['db_id']}: {q['question'][:60]}...", flush=True)
        results.append(eval_one(q, args.agent_url))
    elapsed = time.monotonic() - t0

    summary = summarize(results)
    out = {
        "summary": summary,
        "wall_clock_seconds": elapsed,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.out}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()