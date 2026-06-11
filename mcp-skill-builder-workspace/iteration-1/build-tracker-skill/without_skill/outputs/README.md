# Project-tracker skill build — outputs

| Path | What it is |
|---|---|
| `project-tracker/SKILL.md` | The deliverable: skill teaching small models to use the tracker MCP server reliably |
| `mock/mock_server.py` | Behaviorally-identical mock of the production server; DB path comes from `TRACKER_DB` env var, so tests never touch the real `tracker.db` |
| `mock/seed_mock_db.py` | Seeds a fake database (production-like data + 2 extra unassigned urgent tasks, ids 15–16, to exercise pagination/triage) |
| `eval/tasks.json` | 6 triage simulation tasks, each targeting a server quirk |
| `eval/run_eval.py` | Runs the with-skill vs without-skill matrix (3 trials each) on `claude-haiku-4-5-20251001`, one fresh DB per trial |
| `eval/grade.py` | Programmatic grading: inspects each trial DB's end state, writes `grading.json` per run + `summary.json` |
| `eval/results/<task>/<config>/trialN/` | Per-run artifacts: `tracker.db` (end state), `mcp.json`, `result.json` (agent output/cost/turns), `grading.json` |
| `REPORT.md` | Final numbers and conclusions |

## Reproduce

```bash
PY=/Users/anandkumarsingh/skill-builder/.venv/bin/python
$PY eval/run_eval.py     # runs anything missing; ~36 claude -p haiku runs
$PY eval/grade.py        # regrades and prints the summary table
```

## Using the skill against the real server

Install `project-tracker/` into `~/.claude/skills/` (or pass its SKILL.md to the agent). The skill is written against the production server's behavior; the mock exists only for testing.
