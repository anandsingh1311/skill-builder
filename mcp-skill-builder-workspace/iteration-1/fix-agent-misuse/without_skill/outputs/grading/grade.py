#!/usr/bin/env python3
"""Grade simulation runs by inspecting each run's fake DB (ground truth) and,
for the read-only task, the agent's final answer text."""
import json
import re
import sqlite3
import statistics
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent
RUNS = OUT / "runs"
CONFIGS = ("with_skill", "without_skill")
TRIALS = (1, 2, 3)


def q(db, sql, args=()):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def result_text(run_dir):
    f = run_dir / "stdout.json"
    if not f.exists() or not f.read_text().strip():
        return ""
    try:
        return json.loads(f.read_text()).get("result") or ""
    except json.JSONDecodeError:
        return ""


def grade_create_task(db, text):
    rows = q(db, "SELECT * FROM tasks WHERE title LIKE '%dark mode toggle%'")
    if not rows:
        return False, "no matching task created"
    t = rows[0]
    ok = t["project_id"] == 1 and t["priority"] == "high"
    return ok, f"task created: project_id={t['project_id']} (want 1), priority={t['priority']} (want high)"


def grade_done_assignee(db, text):
    t = q(db, "SELECT status, assignee_id FROM tasks WHERE id = 4")[0]
    ok = t["status"] == "done" and t["assignee_id"] == 4
    return ok, f"task 4: status={t['status']} (want done), assignee_id={t['assignee_id']} (want 4=Sara)"


def grade_suspended(db, text):
    t = q(db, "SELECT assignee_id FROM tasks WHERE id = 5")[0]
    comments = q(db, "SELECT author_id, body FROM comments WHERE task_id = 5 AND id > 2")
    has_priya_comment = any(c["author_id"] == 1 for c in comments)
    ok = t["assignee_id"] == 4 and has_priya_comment
    return ok, (f"task 5: assignee_id={t['assignee_id']} (want 4=Sara), "
                f"new comment by Priya(id=1)={has_priya_comment}")


def grade_comment(db, text):
    comments = q(db, "SELECT author_id, body FROM comments WHERE task_id = 12")
    ok = any(c["author_id"] == 2 and "investigating" in c["body"].lower() for c in comments)
    return ok, f"comments on task 12: {comments!r}"


def grade_count(db, text):
    # ground truth: 9 todo tasks (no writes expected). Accept '9' / 'nine' as the
    # stated total; reject if the agent says 5 (single page) or another number.
    # the answer must state 9 as the total (and not be a 5-only first-page answer)
    ok = bool(re.search(r"\b9\b|\bnine\b", text, re.I))
    return ok, f"answer text: {text[:160]!r}"


def grade_dup_key(db, text):
    projects = q(db, "SELECT id, key, name FROM projects WHERE id > 3")
    if not projects:
        return False, "no new project created"
    p = projects[0]
    key_ok = bool(re.fullmatch(r"[A-Z]{2,5}", p["key"])) and p["key"] != "MOB"
    tasks = q(db, "SELECT priority, project_id FROM tasks WHERE title LIKE '%Launch tracking audit%'")
    task_ok = any(t["project_id"] == p["id"] and t["priority"] == "urgent" for t in tasks)
    return key_ok and task_ok, (f"new project {p['key']!r} ({p['name']!r}), key_ok={key_ok}, "
                                f"urgent task in it={task_ok}")


GRADERS = {
    "create-task-project-key": grade_create_task,
    "done-requires-assignee": grade_done_assignee,
    "suspended-user-fallback": grade_suspended,
    "comment-author-id": grade_comment,
    "paginated-count": grade_count,
    "duplicate-project-key": grade_dup_key,
}


def main():
    rows = []
    for cfg in CONFIGS:
        for trial in TRIALS:
            for task_id, fn in GRADERS.items():
                run_dir = RUNS / cfg / f"trial{trial}" / task_id
                db = run_dir / "tracker.db"
                text = result_text(run_dir)
                if not db.exists():
                    rows.append({"config": cfg, "trial": trial, "task": task_id,
                                 "passed": False, "evidence": "run missing"})
                    continue
                passed, evidence = fn(str(db), text)
                rows.append({"config": cfg, "trial": trial, "task": task_id,
                             "passed": bool(passed), "evidence": evidence})

    summary = {}
    for cfg in CONFIGS:
        cfg_rows = [r for r in rows if r["config"] == cfg]
        per_task = {}
        for task_id in GRADERS:
            t = [r["passed"] for r in cfg_rows if r["task"] == task_id]
            per_task[task_id] = {"passed": sum(t), "trials": len(t)}
        total = sum(r["passed"] for r in cfg_rows)
        summary[cfg] = {
            "pass_rate": round(total / len(cfg_rows), 3),
            "passed": total, "total": len(cfg_rows),
            "per_task": per_task,
        }

    out = {"runs": rows, "summary": summary}
    (OUT / "grading" / "grading.json").write_text(json.dumps(out, indent=2))
    for cfg, s in summary.items():
        print(f"{cfg}: {s['passed']}/{s['total']} = {s['pass_rate']:.0%}")
        for tid, pt in s["per_task"].items():
            print(f"   {tid}: {pt['passed']}/{pt['trials']}")


if __name__ == "__main__":
    main()
