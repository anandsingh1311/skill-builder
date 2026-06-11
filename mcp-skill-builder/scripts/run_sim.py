#!/usr/bin/env python3
"""Simulate small-model agents against a mock MCP server and grade by database state.

For each task in tasks.json, for each trial:
  1. run the `reset` command (re-seeds the mock's SQLite DB to a known state)
  2. run `claude -p <prompt>` headlessly with the mock MCP config
     (if --skill is given, the skill's SKILL.md body is injected via --append-system-prompt)
  3. grade the final DB state (and final answer text) against the task's assertions
  4. write transcript.jsonl, result.json, grading.json into the trial directory

Writes <out>/summary.json and prints a pass-rate table at the end.

Assertion forms (each entry needs a "name"):
  {"sql": "...", "expect_rows": [[...], ...]}   exact result rows
  {"sql": "...", "expect_scalar": <value>}      first cell equals value
  {"sql": "...", "expect_gte": <number>}        first cell >= number
  {"sql": "...", "expect_empty": true}          query returns no rows
  {"sql": "..."}                                query returns at least one row
  {"answer_contains": "substring"}              final answer contains substring (case-insensitive)

Usage:
  run_sim.py tasks.json --out runs/baseline --trials 3
  run_sim.py tasks.json --out runs/with_skill --trials 3 --skill path/to/skill-dir
"""
import argparse
import json
import re
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def load_skill_prompt(skill_dir: Path) -> str:
    text = (skill_dir / "SKILL.md").read_text()
    name = skill_dir.name
    body = text
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        body = text[m.end():]
        nm = re.search(r"^name:\s*(.+)$", m.group(1), re.M)
        if nm:
            name = nm.group(1).strip()
    return (
        f"# Loaded skill: {name}\n"
        f"The user has this skill installed; its instructions are loaded below. "
        f"Follow them when working on the task. If they reference bundled files, "
        f"read them from the skill directory: {skill_dir.resolve()}\n\n{body}"
    )


def run_claude(prompt: str, server_name: str, mcp_config: Path, model: str,
               max_turns: int, timeout: int, system_extra: str | None):
    allowed = f"mcp__{server_name},mcp__{server_name}__*,Read,Glob,Grep"
    cmd = ["claude", "-p", prompt,
           "--model", model,
           "--mcp-config", str(mcp_config),
           "--strict-mcp-config",
           "--allowedTools", allowed,
           "--output-format", "stream-json", "--verbose",
           "--max-turns", str(max_turns)]
    if system_extra:
        cmd += ["--append-system-prompt", system_extra]

    started = time.time()
    timed_out = False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        returncode, timed_out = -1, True
    wall_seconds = time.time() - started

    events, tool_calls, final = [], [], None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(evt)
        if evt.get("type") == "assistant":
            for block in (evt.get("message") or {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_calls.append({"name": block.get("name"), "input": block.get("input")})
        elif evt.get("type") == "result":
            final = evt

    result = {
        "model": model,
        "returncode": returncode,
        "timed_out": timed_out,
        "wall_seconds": round(wall_seconds, 1),
        "num_turns": (final or {}).get("num_turns"),
        "duration_ms": (final or {}).get("duration_ms"),
        "total_cost_usd": (final or {}).get("total_cost_usd"),
        "usage": (final or {}).get("usage"),
        "is_error": (final or {}).get("is_error", returncode != 0),
        "tool_calls": tool_calls,
        "final_text": (final or {}).get("result", ""),
        "stderr_tail": stderr[-2000:],
    }
    return result, events


def grade(db_path: Path, task: dict, final_text: str) -> list[dict]:
    expectations = []
    con = sqlite3.connect(db_path)
    try:
        for a in task.get("assertions", []):
            name = a.get("name") or a.get("sql") or a.get("answer_contains") or "assertion"
            passed, evidence = False, ""
            try:
                if "sql" in a:
                    rows = [list(r) for r in con.execute(a["sql"]).fetchall()]
                    if "expect_rows" in a:
                        passed = rows == a["expect_rows"]
                    elif "expect_scalar" in a:
                        passed = bool(rows) and rows[0][0] == a["expect_scalar"]
                    elif "expect_gte" in a:
                        passed = bool(rows) and rows[0][0] is not None and rows[0][0] >= a["expect_gte"]
                    elif a.get("expect_empty"):
                        passed = rows == []
                    else:
                        passed = bool(rows)
                    evidence = f"sql returned {rows[:5]!r}" + (" (truncated)" if len(rows) > 5 else "")
                elif "answer_contains" in a:
                    passed = a["answer_contains"].lower() in (final_text or "").lower()
                    evidence = f"final answer {'contains' if passed else 'missing'} {a['answer_contains']!r}"
                else:
                    evidence = "unrecognized assertion form"
            except Exception as exc:
                evidence = f"assertion error: {exc}"
            expectations.append({"text": name, "passed": passed, "evidence": evidence})
    finally:
        con.close()
    return expectations


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks_file", help="tasks.json (see SKILL.md for schema)")
    ap.add_argument("--out", required=True, help="output directory for this configuration's runs")
    ap.add_argument("--skill", help="skill directory to inject (omit for the baseline config)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--tasks", help="comma-separated task ids to run (default: all)")
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--timeout", type=int, default=420, help="seconds per trial")
    args = ap.parse_args()

    tasks_path = Path(args.tasks_file).resolve()
    base = tasks_path.parent
    cfg = json.loads(tasks_path.read_text())
    db_path = (base / cfg["db"]).resolve()
    mcp_config = (base / cfg["mcp_config"]).resolve()
    server_name = cfg["server_name"]
    reset_cmd = cfg.get("reset")

    system_extra = load_skill_prompt(Path(args.skill).resolve()) if args.skill else None
    selected = cfg["tasks"]
    if args.tasks:
        wanted = set(args.tasks.split(","))
        selected = [t for t in selected if t["id"] in wanted]

    out_root = Path(args.out)
    label = "with_skill" if args.skill else "baseline"
    summary = {"label": label, "model": args.model, "trials": args.trials, "tasks": []}

    for task in selected:
        task_stats = {"id": task["id"], "passes": 0, "trials": [], }
        for trial_n in range(1, args.trials + 1):
            trial_dir = out_root / task["id"] / f"trial-{trial_n}"
            trial_dir.mkdir(parents=True, exist_ok=True)

            if reset_cmd:
                rs = subprocess.run(reset_cmd, shell=True, cwd=base, capture_output=True, text=True)
                if rs.returncode != 0:
                    print(f"FATAL: reset command failed: {rs.stderr[-500:]}", file=sys.stderr)
                    sys.exit(1)

            print(f"[{label}] {task['id']} trial {trial_n}/{args.trials} ...", flush=True)
            result, events = run_claude(task["prompt"], server_name, mcp_config, args.model,
                                        task.get("max_turns", args.max_turns), args.timeout, system_extra)
            expectations = grade(db_path, task, result["final_text"])
            passed = bool(expectations) and all(e["passed"] for e in expectations)

            (trial_dir / "transcript.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
            (trial_dir / "result.json").write_text(json.dumps(result, indent=2))
            (trial_dir / "grading.json").write_text(json.dumps(
                {"task": task["id"], "trial": trial_n, "passed": passed, "expectations": expectations}, indent=2))

            task_stats["passes"] += passed
            task_stats["trials"].append({
                "trial": trial_n, "passed": passed,
                "num_turns": result["num_turns"], "wall_seconds": result["wall_seconds"],
                "cost_usd": result["total_cost_usd"], "tool_calls": len(result["tool_calls"]),
                "failed_assertions": [e["text"] for e in expectations if not e["passed"]],
            })
            print(f"    -> {'PASS' if passed else 'FAIL'} "
                  f"({result['num_turns']} turns, {result['wall_seconds']}s)", flush=True)
        summary["tasks"].append(task_stats)

    total = sum(len(t["trials"]) for t in summary["tasks"])
    passes = sum(t["passes"] for t in summary["tasks"])
    walls = [tr["wall_seconds"] for t in summary["tasks"] for tr in t["trials"] if tr["wall_seconds"]]
    costs = [tr["cost_usd"] for t in summary["tasks"] for tr in t["trials"] if tr["cost_usd"]]
    summary["pass_rate"] = round(passes / total, 3) if total else 0.0
    summary["mean_wall_seconds"] = round(statistics.mean(walls), 1) if walls else None
    summary["mean_cost_usd"] = round(statistics.mean(costs), 4) if costs else None

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n=== {label}: {passes}/{total} trials passed ({summary['pass_rate']:.0%}) ===")
    print(f"{'task':30} {'passes':>8}")
    for t in summary["tasks"]:
        print(f"{t['id']:30} {t['passes']}/{len(t['trials']):>4}")
    print(f"\nSummary written to {out_root / 'summary.json'}")


if __name__ == "__main__":
    main()
