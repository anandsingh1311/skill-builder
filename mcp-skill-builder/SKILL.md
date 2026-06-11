---
name: mcp-skill-builder
description: Build a skill for any MCP server by mocking the server with a database-backed simulator and battle-testing the skill with small-model (Haiku) agent simulations. Use whenever the user wants to create a skill or agent guidance for an MCP server or its tools, wants to mock/simulate an MCP server for safe testing, or wants to measure and improve how reliably models (especially small ones) use an MCP integration — even if they don't say the word "skill" (e.g. "our agents keep misusing the Jira MCP", "make haiku work with our internal tracker").
compatibility: Requires the `claude` CLI and a Python 3.10+ interpreter with the `mcp` package installed (create a venv if the system Python is externally managed).
---

# MCP Skill Builder

Tool names and JSON schemas tell an agent *what it can call*, but not *how to get work done*: which tool to start with, what order operations go in, what an error like `ERR_409` actually means, or that one tool wants a project *key* while every other tool wants an *id*. A skill that captures this behavioral knowledge measurably improves agent reliability — especially for small models.

The problem is iteration: you can't repeatedly test a draft skill against a production MCP server (slow, costly, and write operations are dangerous). So this pipeline builds a **database-backed mock** of the server first. The mock gives you:

- **Safety** — agents can create/update/delete freely; it's a throwaway SQLite file.
- **Determinism** — reset the database to a known seed before every trial.
- **Objective grading** — a task is "done" if the final database state matches expectations. No LLM judge needed.

Then you run **Haiku agents** against the mock, with and without the draft skill, and iterate on the skill until the small model succeeds reliably. Haiku is the stress test: if a small model can drive the server correctly with your skill, the skill genuinely carries the knowledge rather than relying on model intelligence.

## Pipeline

| Step | Action | Artifact |
|---|---|---|
| 0 | Set up workspace + Python with `mcp` | `<server>-skillgen/` |
| 1 | Introspect the target server | `tools.json` |
| 2 | Design the domain database | `schema.sql`, `seed_db.py` |
| 3 | Build the mock server, verify tool parity | `mock_server.py`, `mock-config.json` |
| 4 | Draft the target skill | `<server>-skill/SKILL.md` |
| 5 | Write simulation tasks with DB assertions | `tasks.json` |
| 6 | Simulate Haiku with and without the skill | `runs/` |
| 7 | Read failures, improve the skill, re-run | iterate |
| 8 | Ship the skill (mock stays behind as a test harness) | final skill |

Work in a workspace directory named `<server>-skillgen/` (sibling to wherever the final skill should live). All artifacts above go in it.

## Step 0: Environment

The scripts need a Python that can `import mcp`. Check first:

```bash
python3 -c "import mcp" 2>/dev/null && echo OK
```

If that fails (common on Homebrew/externally-managed Pythons), create a venv in the workspace and use its interpreter **everywhere** — for running the scripts, and as the `command` in the mock's MCP config:

```bash
python3 -m venv <workspace>/.venv && <workspace>/.venv/bin/pip install -q mcp
```

Refer to this interpreter as `$PY` below.

## Step 1: Introspect the target server

Get the server's launch command (or URL) from the user, or from `.mcp.json` / `claude mcp list`. Then dump its tool inventory:

```bash
$PY <skill-dir>/scripts/introspect.py --stdio "npx -y @acme/tracker-mcp" -o tools.json
# or: --url https://example.com/mcp
```

`tools.json` (names, descriptions, input schemas) is the contract everything downstream is built against.

Schemas alone underspecify behavior, so also gather behavioral intel where you can: read the server's source if it's local, read its docs/README, and — only with the user's OK — probe **read-only** tools against the real server to see real response shapes. Never call write tools on a real server.

## Step 2: Design the domain database

Read `references/mock-server-guide.md` before this step and the next — it has the schema-design rules, seeding rules (deterministic data, no `random`/`now()`), and a worked FastMCP example.

In short: infer entities from the nouns in the tool names/schemas (tasks, projects, users → tables), write `schema.sql`, and write `seed_db.py` that builds a fresh database with 20–50 realistic rows per table including the edge cases your tasks will need.

## Step 3: Build the mock and verify parity

Write `mock_server.py` (FastMCP, backed by the SQLite file). The mock must present **exactly the same tool surface** as the real server — same names, same parameters, same required fields, descriptions copied verbatim — so that a skill developed against the mock transfers to the real server unchanged. Verify with the diff mode:

```bash
$PY <skill-dir>/scripts/introspect.py --diff tools.json --stdio "$PY mock_server.py"
```

Fix mismatches until the diff is clean. Then write `mock-config.json`:

```json
{"mcpServers": {"<server_name>": {"command": "<abs path to $PY>", "args": ["<abs path to mock_server.py>"]}}}
```

## Step 4: Draft the target skill

Read `references/target-skill-guide.md`, then write the skill you're actually here to produce. The essence: a tool-selection map, canonical multi-tool workflows with verbatim example calls, the gotchas (what each cryptic error really means and how to recover), and efficiency rules — written explicitly enough for a small model. The generated skill must never mention the mock; it documents the real server.

## Step 5: Write simulation tasks

Read `references/simulation-guide.md` for task-design guidance, then write `tasks.json`:

```json
{
  "server_name": "tracker",
  "mcp_config": "mock-config.json",
  "db": "tracker.db",
  "reset": "/abs/path/to/python seed_db.py",
  "tasks": [
    {
      "id": "close-login-bug",
      "prompt": "Find the task about the login bug and mark it done. If anything blocks you, fix that too.",
      "assertions": [
        {"name": "login task is done", "sql": "SELECT status FROM tasks WHERE id=7", "expect_rows": [["done"]]},
        {"name": "task was assigned first", "sql": "SELECT assignee_id FROM tasks WHERE id=7", "expect_gte": 1}
      ]
    }
  ]
}
```

Aim for 4–8 tasks covering every workflow the skill claims to teach. Paths are relative to `tasks.json`; `reset` runs before each trial.

## Step 6: Simulate

Run Haiku against the mock, without the skill (baseline) and with it. Trials share one database, so run the two configs sequentially, not in parallel:

```bash
$PY <skill-dir>/scripts/run_sim.py tasks.json --trials 3 --out runs/baseline
$PY <skill-dir>/scripts/run_sim.py tasks.json --trials 3 --skill <path-to-drafted-skill-dir> --out runs/with_skill
```

The script resets the DB, runs `claude -p --model haiku` with the mock MCP config (injecting the skill via system prompt when `--skill` is given), grades the final DB state against the assertions, and writes per-trial transcripts plus a `summary.json` with pass rates, turns, and cost. Expect a few minutes per config.

## Step 7: Iterate

For every failed trial, read the transcript (`transcript.jsonl` — the `tool_calls` list in `result.json` is the quick view) and classify the failure: wrong tool chosen, bad argument (id vs name, enum typo), missing prerequisite step, gave up after an error, or falsely claimed success. Fix the *skill*, not the task — unless the task itself is ambiguous. Then re-run Step 6.

You're done when with-skill Haiku passes essentially all tasks and clearly beats baseline. If baseline already passes everything, your tasks are too easy or the server is too simple to need a skill — say so honestly rather than shipping a skill that adds nothing.

## Step 8: Ship

Deliver the generated skill directory, and report the final numbers (pass rates, mean turns, cost per config). Keep the workspace: the mock + tasks are a permanent regression harness for future skill edits. Double-check the shipped SKILL.md contains no references to the mock, mock paths, or the simulation process.
