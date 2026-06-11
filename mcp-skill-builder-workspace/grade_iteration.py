#!/usr/bin/env python3
"""Grade the four iteration-1 runs against the eval assertions.

Run with the venv python (needs `mcp` for the parity + write-probe checks):
  /Users/anandkumarsingh/skill-builder/.venv/bin/python grade_iteration.py

Writes grading.json into each <eval>/<config>/ directory (viewer schema:
expectations[] with text/passed/evidence).
"""
import asyncio
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

WS = Path("/Users/anandkumarsingh/skill-builder/mcp-skill-builder-workspace")
ITER = WS / "iteration-1"
VENV_PY = "/Users/anandkumarsingh/skill-builder/.venv/bin/python"
INTROSPECT = "/Users/anandkumarsingh/skill-builder/mcp-skill-builder/scripts/introspect.py"
FIXTURE_TOOLS = "/tmp/fixture_tools.json"  # dumped from the real fixture earlier

RUNS = {
    # db_mode "adjacent": mock reads a .db file next to itself (probe a copied dir).
    # db_mode "env": mock reads TRACKER_DB env var; "seed" is (script, how) where how is
    #   "argv" (script takes db path as argv[1]) or "env" (script reads TRACKER_DB).
    # result files: (glob, task_idx, cfg_idx) — negative indices into the path parts.
    ("build-tracker-skill", "with_skill"): {
        "skill_md": "tracker-skill/SKILL.md",
        "mock": "mock_server.py",
        "db_mode": "adjacent",
        "results": ("runs/iter1/*/*/trial-*/result.json", -3, -4),
        "fixture": WS / "fixtures/copies/build-with/project-tracker",
        "quirk_mode": "any2",
    },
    ("build-tracker-skill", "without_skill"): {
        "skill_md": "project-tracker/SKILL.md",
        "mock": "mock/mock_server.py",
        "db_mode": "env",
        "seed": ("mock/seed_mock_db.py", "argv"),
        "results": ("eval/results/*/*/trial*/result.json", -4, -3),
        "fixture": WS / "fixtures/copies/build-base/project-tracker",
        "quirk_mode": "any2",
    },
    ("fix-agent-misuse", "with_skill"): {
        "skill_md": "project-tracker-skill/SKILL.md",
        "mock": "mock/mock_server.py",
        "db_mode": "adjacent",
        "results": ("runs/iter1/*/*/trial-*/result.json", -3, -4),
        "fixture": WS / "fixtures/copies/misuse-with/project-tracker",
        "quirk_mode": "misuse",
    },
    ("fix-agent-misuse", "without_skill"): {
        "skill_md": "skill/project-tracker/SKILL.md",
        "mock": "mock-server/server.py",
        "db_mode": "env",
        "seed": ("mock-server/init_db.py", "env"),
        "results": ("runs/*/trial*/*/stdout.json", -2, -4),
        "fixture": WS / "fixtures/copies/misuse-base/project-tracker",
        "quirk_mode": "misuse",
    },
}

QUIRKS = {
    "project-key-vs-id": r"project[_\s-]?key",
    "err409-done-needs-assignee": r"(ERR_?409|invalid transition)[\s\S]{0,200}?(assign|assignee)|assign[\s\S]{0,200}?(ERR_?409|invalid transition)|(done|close)[\s\S]{0,120}?(requires?|needs?|must have)[\s\S]{0,40}?assignee",
    "err403-suspended-user": r"(ERR_?403|suspended|inactive|active)",
    "title-only-search-or-pagination": r"(title[s]?[\s\S]{0,60}?(only|not description)|only[\s\S]{0,60}?title|next_cursor|paginat|5 (results|per page|tasks))",
}


def frontmatter(md_text):
    m = re.match(r"^---\n(.*?)\n---", md_text, re.S)
    if not m:
        return {}
    out = {}
    for key in ("name", "description"):
        km = re.search(rf"^{key}:\s*(.+)$", m.group(1), re.M)
        if km:
            out[key] = km.group(1).strip()
    return out


def table_dump(db):
    con = sqlite3.connect(db)
    out = {}
    try:
        for t in ("users", "projects", "tasks", "comments"):
            out[t] = con.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
    finally:
        con.close()
    return out


async def write_probe(mock_py: Path, db: Path, env: dict | None):
    """Call a write tool on the mock, return (changed, evidence)."""
    import os
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    def count():
        con = sqlite3.connect(db)
        try:
            return con.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        except sqlite3.Error as e:
            return f"sql error: {e}"
        finally:
            con.close()

    before = count()
    full_env = {**os.environ, **(env or {})}
    params = StdioServerParameters(command=VENV_PY, args=[str(mock_py)], env=full_env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("add_comment", {"task_id": 1, "body": "grading write probe", "author_id": 1})
    after = count()
    changed = isinstance(before, int) and isinstance(after, int) and after == before + 1
    return changed, f"comments rows {before} -> {after} in {db.name} (tool error: {res.isError})"


def prepare_mock_env(out_dir: Path, spec, td: Path):
    """Return (mock_path, env, db_path) ready for probing, per the run's conventions."""
    mock_py = out_dir / spec["mock"]
    if spec["db_mode"] == "adjacent":
        probe_dir = td / "mockcopy"
        shutil.copytree(mock_py.parent, probe_dir,
                        ignore=shutil.ignore_patterns("runs", "results", "__pycache__", "*.jsonl"))
        dbs = sorted(probe_dir.glob("*.db"))
        if not dbs:
            raise RuntimeError("no .db file next to mock server")
        return probe_dir / mock_py.name, None, dbs[0]
    # env mode: seed a throwaway db and point TRACKER_DB at it
    db = td / "probe.db"
    seed_script, how = spec["seed"]
    seed_path = out_dir / seed_script
    if how == "argv":
        subprocess.run([VENV_PY, str(seed_path), str(db)], check=True, capture_output=True, timeout=30)
    else:
        import os
        subprocess.run([VENV_PY, str(seed_path)], check=True, capture_output=True, timeout=30,
                       env={**os.environ, "TRACKER_DB": str(db)})
    return mock_py, {"TRACKER_DB": str(db)}, db


def grade_run(eval_name, config, spec):
    out_dir = ITER / eval_name / config / "outputs"
    exps = []

    def add(text, passed, evidence):
        exps.append({"text": text, "passed": bool(passed), "evidence": str(evidence)[:400]})

    # 1. skill exists with frontmatter
    skill_md = out_dir / spec["skill_md"]
    if skill_md.exists():
        fm = frontmatter(skill_md.read_text())
        add("Generated skill has SKILL.md with valid frontmatter (name + description)",
            "name" in fm and "description" in fm,
            f"{skill_md.relative_to(out_dir)}: name={fm.get('name')!r}, desc={'yes' if fm.get('description') else 'MISSING'}")
        skill_text = skill_md.read_text()
    else:
        found = list(out_dir.rglob("SKILL.md"))
        add("Generated skill has SKILL.md with valid frontmatter (name + description)", False,
            f"expected {spec['skill_md']}; found: {[str(p.relative_to(out_dir)) for p in found][:3]}")
        skill_text = found[0].read_text() if found else ""

    # 2 + 3. mock tool parity, and DB-backed write probe (against a throwaway DB/copy)
    mock_py = out_dir / spec["mock"]
    if mock_py.exists():
        try:
            with tempfile.TemporaryDirectory() as td:
                probe_mock, env, db = prepare_mock_env(out_dir, spec, Path(td))
                cmd = [VENV_PY, INTROSPECT, "--diff", FIXTURE_TOOLS, "--stdio", f"{VENV_PY} {probe_mock}"]
                for k, v in (env or {}).items():
                    cmd += ["--env", f"{k}={v}"]
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                add("Mock MCP server passes tool parity vs real server (introspect --diff)",
                    p.returncode == 0, (p.stdout + p.stderr).strip()[-300:])
                ok, ev = asyncio.run(write_probe(probe_mock, db, env))
                add("Mock is database-backed: write tool call persists to SQLite", ok, ev)
        except Exception as e:
            add("Mock MCP server passes tool parity vs real server (introspect --diff)", False, f"probe setup failed: {e}")
            add("Mock is database-backed: write tool call persists to SQLite", False, f"probe setup failed: {e}")
    else:
        add("Mock MCP server passes tool parity vs real server (introspect --diff)", False,
            f"mock not found at {spec['mock']}")
        add("Mock is database-backed: write tool call persists to SQLite", False, "mock not found")

    # 4. simulations ran for both configs (>=3 distinct tasks each)
    glob_pat, task_idx, cfg_idx = spec["results"]
    run_dirs = sorted(out_dir.glob(glob_pat))
    by_cfg = {}
    for p in run_dirs:
        parts = p.parts
        cfg_raw, task = parts[cfg_idx].lower(), parts[task_idx]
        if "baseline" in cfg_raw or "without" in cfg_raw or "no_skill" in cfg_raw:
            cfg = "baseline"
        elif "with" in cfg_raw:
            cfg = "with_skill"
        else:
            cfg = "unknown"
        by_cfg.setdefault(cfg, set()).add(task)
    n_with = len(by_cfg.get("with_skill", set()))
    n_base = len(by_cfg.get("baseline", set()))
    add("Simulations ran: >=3 distinct tasks in BOTH configs",
        n_with >= 3 and n_base >= 3,
        f"with_skill tasks={n_with}, baseline tasks={n_base}, total result files={len(run_dirs)}")

    # 4b. no session-limit poisoning
    poisoned = 0
    for p in run_dirs:
        try:
            if "session limit" in p.read_text().lower():
                poisoned += 1
        except Exception:
            pass
    add("No trial poisoned by usage-limit errors", poisoned == 0, f"{poisoned}/{len(run_dirs)} poisoned")

    # 5. report with numeric pass rates for both configs
    reports = [p for p in out_dir.glob("**/REPORT*.md") if "fixtures" not in str(p)]
    if reports:
        rt = reports[0].read_text()
        has_nums = bool(re.search(r"\d+\s*/\s*\d+|\d+(\.\d+)?\s*%", rt))
        both = re.search(r"with[\s_-]?skill", rt, re.I) and re.search(r"(baseline|without[\s_-]?skill)", rt, re.I)
        add("Report states numeric pass rates for both configurations", has_nums and bool(both),
            f"{reports[0].name}: numbers={has_nums}, both configs named={bool(both)}")
    else:
        add("Report states numeric pass rates for both configurations", False, "no REPORT*.md found")

    # 6. quirks documented in the generated skill
    hits = {k: bool(re.search(rx, skill_text, re.I)) for k, rx in QUIRKS.items()}
    if spec["quirk_mode"] == "misuse":
        ok = hits["err409-done-needs-assignee"] and bool(
            re.search(r"(user[_\s]?id|list_users|numeric id)", skill_text, re.I))
        add("Skill explains ERR_409 (assign-before-done) and id-vs-name lookup", ok, f"quirk hits: {hits}")
    else:
        ok = sum(hits.values()) >= 2
        add("Skill documents >=2 planted quirks", ok, f"quirk hits: {hits}")

    # 7. 'real' fixture DB untouched
    ref = table_dump("/tmp/ref-tracker/tracker.db")
    cur = table_dump(spec["fixture"] / "tracker.db")
    same = ref == cur
    add("'Real' tracker DB contents unchanged from seed", same,
        "tables match seed" if same else {t: (len(ref[t]), len(cur[t])) for t in ref})

    passed = sum(e["passed"] for e in exps)
    grading = {"run_id": f"{eval_name}-{config}", "passed": passed == len(exps),
               "score": f"{passed}/{len(exps)}", "expectations": exps}
    (ITER / eval_name / config / "grading.json").write_text(json.dumps(grading, indent=2))
    return grading


def main():
    # reference seed for assertion 7
    ref_dir = Path("/tmp/ref-tracker")
    if ref_dir.exists():
        shutil.rmtree(ref_dir)
    ref_dir.mkdir()
    shutil.copy(WS / "fixtures/project-tracker/init_db.py", ref_dir / "init_db.py")
    subprocess.run([sys.executable, str(ref_dir / "init_db.py")], check=True, capture_output=True)

    results = []
    for (eval_name, config), spec in RUNS.items():
        g = grade_run(eval_name, config, spec)
        results.append(g)
        print(f"{g['run_id']}: {g['score']}")
        for e in g["expectations"]:
            print(f"   {'PASS' if e['passed'] else 'FAIL'}  {e['text']}")
    print("\nGrading written to <eval>/<config>/grading.json")


if __name__ == "__main__":
    main()
