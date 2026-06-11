#!/usr/bin/env python3
"""Grade every run programmatically: inspect the trial's mock db end-state
(and, for list tasks, the IDS: line in the agent's final answer).
Writes grading.json per run and an aggregate summary.json + markdown table."""
import json
import re
import sqlite3
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def q(db, sql, args=()):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def task_row(db, tid):
    r = q(db, "SELECT status, priority, assignee_id FROM tasks WHERE id=?", (tid,))
    return r[0] if r else None


def ids_from_answer(text):
    """Parse the last 'IDS:' line into a set of ints."""
    matches = re.findall(r"IDS:\s*([0-9,\s]+)", text or "")
    if not matches:
        return None
    return {int(x) for x in re.findall(r"\d+", matches[-1])}


def check(name, ok, evidence):
    return {"text": name, "passed": bool(ok), "evidence": evidence}


def grade_list_all_todo(db, answer):
    expected = {2, 3, 4, 6, 8, 10, 11, 12, 13, 15, 16}
    got = ids_from_answer(answer)
    return [check("final answer lists exactly the 11 todo task ids (requires 3 pages)",
                  got == expected, f"expected {sorted(expected)}, got {sorted(got) if got else got}")]


def grade_close_needs_assignee(db, answer):
    row = task_row(db, 2)
    return [
        check("task 2 status is done", row and row[0] == "done", f"row={row}"),
        check("task 2 assigned to Sara Ito (user 4)", row and row[2] == 4, f"row={row}"),
    ]


def grade_assign_suspended_fallback(db, answer):
    row = task_row(db, 12)
    return [check("task 12 assigned to Marcus Webb (user 2) after Devon (suspended) fails",
                  row and row[2] == 2, f"row={row}")]


def grade_create_task_by_key(db, answer):
    rows = q(db, "SELECT project_id, priority, status FROM tasks WHERE title=?",
             ("Backfill missing event timestamps",))
    ok = any(r[0] == 2 and r[1] == "high" for r in rows)
    return [check("task 'Backfill missing event timestamps' exists in Data Platform (project 2) with priority high",
                  ok, f"matching rows={rows}")]


def grade_search_title_only(db, answer):
    row = task_row(db, 1)
    others = q(db, "SELECT id FROM tasks WHERE status='blocked' AND id NOT IN (1,5)")
    return [
        check("task 1 (Safari redirect loop) status is blocked", row and row[0] == "blocked", f"row={row}"),
        check("no other task wrongly set to blocked", not others, f"unexpected blocked ids={others}"),
    ]


def grade_triage_urgent_unassigned(db, answer):
    r15, r16 = task_row(db, 15), task_row(db, 16)
    untouched = all(task_row(db, t) == exp for t, exp in [
        (1, ("in_progress", "urgent", 2)),
        (3, ("todo", "urgent", 2)),
        (5, ("blocked", "urgent", 2)),
        (2, ("todo", "high", None)),
        (4, ("todo", "low", None)),
    ])
    return [
        check("task 15 assigned to Priya (1) and in_progress",
              r15 == ("in_progress", "urgent", 1), f"row={r15}"),
        check("task 16 assigned to Priya (1) and in_progress",
              r16 == ("in_progress", "urgent", 1), f"row={r16}"),
        check("already-assigned urgent tasks and non-urgent tasks left untouched",
              untouched, "checked tasks 1,3,5 (urgent, assigned) and 2,4 (unassigned, not urgent)"),
    ]


GRADERS = {
    "list-all-todo": grade_list_all_todo,
    "close-needs-assignee": grade_close_needs_assignee,
    "assign-suspended-fallback": grade_assign_suspended_fallback,
    "create-task-by-key": grade_create_task_by_key,
    "search-title-only": grade_search_title_only,
    "triage-urgent-unassigned": grade_triage_urgent_unassigned,
}


def main():
    summary = {}
    for task_id, grader in GRADERS.items():
        summary[task_id] = {}
        for config in ("with_skill", "without_skill"):
            trials = []
            for trial_dir in sorted((RESULTS / task_id / config).glob("trial*")):
                res = json.loads((trial_dir / "result.json").read_text())
                answer = res.get("result", "")
                exps = grader(trial_dir / "tracker.db", answer)
                passed = all(e["passed"] for e in exps)
                (trial_dir / "grading.json").write_text(json.dumps(
                    {"passed": passed, "expectations": exps}, indent=2))
                trials.append({
                    "trial": trial_dir.name, "passed": passed,
                    "cost_usd": res.get("total_cost_usd"),
                    "duration_s": round((res.get("duration_ms") or 0) / 1000, 1),
                    "turns": res.get("num_turns"),
                })
            summary[task_id][config] = {
                "pass": sum(t["passed"] for t in trials),
                "n": len(trials),
                "trials": trials,
            }

    # aggregate
    lines = ["| Task | With skill | Without skill |", "|---|---|---|"]
    tot = {"with_skill": [0, 0], "without_skill": [0, 0]}
    for task_id, cfgs in summary.items():
        cells = []
        for cfg in ("with_skill", "without_skill"):
            c = cfgs[cfg]
            tot[cfg][0] += c["pass"]
            tot[cfg][1] += c["n"]
            cells.append(f"{c['pass']}/{c['n']}")
        lines.append(f"| {task_id} | {cells[0]} | {cells[1]} |")
    lines.append(f"| **TOTAL** | **{tot['with_skill'][0]}/{tot['with_skill'][1]}** | "
                 f"**{tot['without_skill'][0]}/{tot['without_skill'][1]}** |")

    def agg(cfg, field):
        vals = [t[field] for tk in summary.values() for t in tk[cfg]["trials"] if t[field]]
        return round(statistics.mean(vals), 3) if vals else None

    stats = {cfg: {"pass_rate": round(tot[cfg][0] / tot[cfg][1], 3),
                   "mean_cost_usd": agg(cfg, "cost_usd"),
                   "mean_duration_s": agg(cfg, "duration_s"),
                   "mean_turns": agg(cfg, "turns")} for cfg in tot}

    (HERE / "summary.json").write_text(json.dumps({"per_task": summary, "aggregate": stats}, indent=2))
    print("\n".join(lines))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
