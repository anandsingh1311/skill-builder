#!/usr/bin/env python3
"""Run haiku simulations against the MOCKED tracker MCP server, with and without the skill.

Each run gets its own freshly seeded throwaway sqlite DB (TRACKER_DB env var) —
the real tracker.db is never touched.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

OUT = Path(__file__).resolve().parent
VENV_PY = "/Users/anandkumarsingh/skill-builder/.venv/bin/python"
MOCK = OUT / "mock-server"
SKILL_MD = OUT / "skill" / "project-tracker" / "SKILL.md"
MODEL = "claude-haiku-4-5-20251001"
TRIALS = 3
TIMEOUT = 360

TASKS = json.loads((OUT / "grading" / "tasks.json").read_text())["tasks"]

DISALLOWED = "Bash Edit Write NotebookEdit WebFetch WebSearch Task TodoWrite Read Glob Grep"


def one_run(config: str, trial: int, task: dict) -> dict:
    run_dir = OUT / "runs" / config / f"trial{trial}" / task["id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    db = run_dir / "tracker.db"
    # seed a fresh fake DB
    subprocess.run([VENV_PY, str(MOCK / "init_db.py")],
                   env={"TRACKER_DB": str(db), "PATH": "/usr/bin:/bin"},
                   check=True, capture_output=True)
    mcp_cfg = run_dir / "mcp.json"
    mcp_cfg.write_text(json.dumps({
        "mcpServers": {
            "tracker": {
                "command": VENV_PY,
                "args": [str(MOCK / "server.py")],
                "env": {"TRACKER_DB": str(db)},
            }
        }
    }))
    cmd = [
        "claude", "-p", task["prompt"],
        "--model", MODEL,
        "--output-format", "json",
        "--mcp-config", str(mcp_cfg),
        "--strict-mcp-config",
        "--dangerously-skip-permissions",
        "--disallowedTools", DISALLOWED,
        "--max-turns", "30",
    ]
    if config == "with_skill":
        cmd += ["--append-system-prompt",
                "You have the following skill for working with the tracker MCP server. Follow it.\n\n"
                + SKILL_MD.read_text()]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=TIMEOUT, cwd=str(run_dir))
        (run_dir / "stdout.json").write_text(proc.stdout)
        if proc.stderr:
            (run_dir / "stderr.txt").write_text(proc.stderr)
        status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
    except subprocess.TimeoutExpired:
        status = "timeout"
        (run_dir / "stdout.json").write_text("")
    return {"config": config, "trial": trial, "task": task["id"], "status": status}


def main():
    # optional chunking: run_sims.py [config] [trial]
    cfg_filter = sys.argv[1] if len(sys.argv) > 1 else None
    trial_filter = int(sys.argv[2]) if len(sys.argv) > 2 else None
    jobs = [(cfg, t, task)
            for cfg in ("with_skill", "without_skill")
            for t in range(1, TRIALS + 1)
            for task in TASKS
            if (cfg_filter is None or cfg == cfg_filter)
            and (trial_filter is None or t == trial_filter)]
    print(f"{len(jobs)} runs, model={MODEL}")
    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(one_run, *j): j for j in jobs}
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            print(f"[{len(results)}/{len(jobs)}] {r['config']}/trial{r['trial']}/{r['task']}: {r['status']}",
                  flush=True)
    log = OUT / "runs" / "run_log.json"
    prev = json.loads(log.read_text()) if log.exists() else []
    keys = {(r["config"], r["trial"], r["task"]) for r in results}
    prev = [r for r in prev if (r["config"], r["trial"], r["task"]) not in keys]
    log.write_text(json.dumps(prev + results, indent=2))
    print("done")


if __name__ == "__main__":
    sys.exit(main())
