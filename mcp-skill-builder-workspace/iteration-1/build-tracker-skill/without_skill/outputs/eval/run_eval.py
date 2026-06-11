#!/usr/bin/env python3
"""Run the with-skill vs without-skill simulation matrix against the MOCK tracker.

Every trial gets its own freshly-seeded SQLite db; the mock MCP server is
pointed at it via TRACKER_DB, so the real tracker.db is never touched.

Usage: python3 run_eval.py            # runs everything not yet run
"""
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
VENV_PY = "/Users/anandkumarsingh/skill-builder/.venv/bin/python"
MOCK_SERVER = OUT / "mock" / "mock_server.py"
SEEDER = OUT / "mock" / "seed_mock_db.py"
SKILL_MD = OUT / "project-tracker" / "SKILL.md"
RESULTS = HERE / "results"

CFG = json.loads((HERE / "tasks.json").read_text())
MODEL = CFG["model"]
TRIALS = CFG["trials_per_config"]

SKILL_PREFIX = (
    f"You have a skill that documents how to use the project tracker correctly. "
    f"Before doing anything else, read it with the Read tool: {SKILL_MD}\n"
    f"Follow its guidance exactly.\n\n"
)


def run_one(task, config, trial):
    run_dir = RESULTS / task["id"] / config / f"trial{trial}"
    result_file = run_dir / "result.json"
    if result_file.exists():
        return f"skip {run_dir}"
    run_dir.mkdir(parents=True, exist_ok=True)
    db = run_dir / "tracker.db"
    subprocess.run([VENV_PY, str(SEEDER), str(db)], check=True, capture_output=True)

    mcp_cfg = run_dir / "mcp.json"
    mcp_cfg.write_text(json.dumps({
        "mcpServers": {
            "tracker": {
                "command": VENV_PY,
                "args": [str(MOCK_SERVER)],
                "env": {"TRACKER_DB": str(db)},
            }
        }
    }))

    prompt = task["prompt"]
    if config == "with_skill":
        prompt = SKILL_PREFIX + prompt

    cmd = [
        "claude", "-p", prompt,
        "--model", MODEL,
        "--mcp-config", str(mcp_cfg),
        "--strict-mcp-config",
        "--setting-sources", "project",       # ignore user-level CLAUDE.md/skills
        "--allowedTools", "Read", "mcp__tracker",
        "--output-format", "json",
        "--max-turns", "50",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=run_dir)
        out = proc.stdout.strip()
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            data = {"result": out, "parse_error": True, "stderr": proc.stderr[-2000:]}
        data["_returncode"] = proc.returncode
    except subprocess.TimeoutExpired:
        data = {"result": "", "timeout": True}
    result_file.write_text(json.dumps(data, indent=2))
    return f"done {task['id']}/{config}/trial{trial} (cost=${data.get('total_cost_usd', '?')})"


def main():
    # Optional chunking: run_eval.py [task_id] [config]
    task_filter = sys.argv[1] if len(sys.argv) > 1 else None
    cfg_filter = sys.argv[2] if len(sys.argv) > 2 else None
    jobs = [(t, c, n) for t in CFG["tasks"] for c in ("with_skill", "without_skill")
            for n in range(1, TRIALS + 1)
            if (task_filter is None or t["id"] == task_filter)
            and (cfg_filter is None or c == cfg_filter)]
    print(f"{len(jobs)} runs, model={MODEL}")
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(run_one, t, c, n): (t["id"], c, n) for t, c, n in jobs}
        for f in as_completed(futs):
            try:
                print(f.result(), flush=True)
            except Exception as e:
                print(f"FAIL {futs[f]}: {e}", flush=True)


if __name__ == "__main__":
    main()
