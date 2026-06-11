# Building the Database-Backed Mock

The mock is a real MCP server (FastMCP + SQLite) that impersonates the target server. Agents talking to it can't tell the difference at the protocol level — same tool names, same parameters, same response shapes — but every call hits a local throwaway database instead of production.

**One throwaway DB per trial.** The mock reads its database path from an environment variable (`MOCK_DB` by convention) rather than hardcoding one file. The simulator seeds a fresh DB at a unique path before each trial and injects that path into the mock — so trials never share mutable state, a trial can't be polluted by a previous one, and the baseline and with-skill configs can run at the same time. This is cleaner than resetting one shared file in place: there's nothing to reset, and a crashed trial leaves its own DB behind for inspection instead of corrupting the next run.

## Designing the schema

Infer entities from the tool surface. Nouns in tool names and parameters are tables (`list_projects` → `projects`; `assign_task(task_id, user_id)` → `tasks`, `users`, and a foreign key between them). Enum values mentioned in descriptions become CHECK constraints or just documented valid values. Keep it minimal: model only what the tools can read or write — you're not rebuilding their backend, just enough state for the tools to behave consistently.

Write it as `schema.sql` so it's reviewable, and a `seed_db.py` that recreates the database from scratch (drop + create + insert). The simulator runs this before **every trial** to build that trial's private DB, so it must be fast and idempotent, and it must write to the path the simulator hands it:

```python
#!/usr/bin/env python3
import os, sqlite3
from pathlib import Path

# The simulator sets $MOCK_DB to a unique per-trial path. Fall back to a local
# file for manual smoke-testing.
DB = Path(os.environ.get("MOCK_DB", Path(__file__).resolve().parent / "tracker.db"))
DB.parent.mkdir(parents=True, exist_ok=True)
if DB.exists():
    DB.unlink()                      # fresh DB every time

con = sqlite3.connect(DB)
con.executescript(Path(__file__).resolve().parent.joinpath("schema.sql").read_text())
con.executemany("INSERT INTO users(id, name, active) VALUES (?,?,?)", [
    (1, "Ava Reyes", 1), (2, "Ben Olu", 1), (3, "Devon Cole", 0),  # id 3 is suspended
    # ... hardcoded, deterministic rows
])
con.commit()
con.close()
```

## Seeding rules

Deterministic data is what makes trials comparable, so:

- No `random`, no `datetime.now()` — hardcode ids, names, and timestamp strings.
- 20–50 rows per main table: enough that "find X" requires actual searching/filtering rather than reading one page of output.
- Plant the edge cases your simulation tasks will need: an unassigned task, a suspended user, a name that appears in two projects, enough rows to force pagination.
- Make rows realistic (real-looking titles, names, dates). Agents behave differently on `"Fix login redirect loop on Safari"` than on `"task 1"`.

## The mock server

Template (adapt to the real server's tools):

```python
#!/usr/bin/env python3
import json, os, sqlite3
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# The simulator injects a unique per-trial DB path via $MOCK_DB. Fall back to a
# local file so the mock still runs when launched by hand. Resolve at call time
# is fine too, but reading it once at startup is simplest.
DB = Path(os.environ.get("MOCK_DB", Path(__file__).resolve().parent / "tracker.db"))
mcp = FastMCP("tracker")                              # MUST match the real server's name

def query(sql, args=()):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(sql, args).fetchall()]
        con.commit()
        return rows
    finally:
        con.close()

@mcp.tool()
def update_task_status(task_id: int, status: str) -> str:
    """Update a task's status. Status must be one of: todo, in_progress, blocked, done."""
    if status not in ("todo", "in_progress", "blocked", "done"):
        raise ValueError("ERR_422: invalid status value")     # mirror the REAL error string
    ...

if __name__ == "__main__":
    mcp.run()
```

Rules that matter:

1. **Tool parity is non-negotiable.** Same tool names, same parameter names, same required/optional split, descriptions copied verbatim from `tools.json`. A skill tuned against a divergent mock teaches the wrong API. Prove it: `introspect.py --diff tools.json --stdio "$PY mock_server.py"` must pass before any simulation.
2. **Reproduce behavior, not just shape.** Copy the real server's error strings (especially the cryptic ones — those are exactly what the skill must explain), its pagination mechanics (page size, cursor field names), and its inconsistencies (if one tool takes a key where others take an id, the mock must too). The quirks are the whole reason the skill will be valuable.
3. **Writes must persist** to the SQLite file — grading inspects the database after the agent finishes. Don't keep state in memory.
4. **Never print to stdout.** Stdio MCP servers speak JSON-RPC on stdout; a stray `print()` corrupts the protocol. Use `sys.stderr` for debugging.
5. **Errors via `raise ValueError("...")`** — FastMCP converts exceptions into tool-error results the agent sees as text.
6. **Response shapes**: return dicts/lists and let FastMCP serialize them, shaped like the real server's responses (same field names). If you captured real read-only responses in Step 1, match them.

## The MCP config

`mock-config.json` is the *base* config, with absolute paths (the simulator reads it, then writes a per-trial copy that adds the trial's `MOCK_DB` to the `env` block before passing it to `claude -p --mcp-config`):

```json
{
  "mcpServers": {
    "tracker": {
      "command": "/abs/path/to/.venv/bin/python",
      "args": ["/abs/path/to/mock_server.py"]
    }
  }
}
```

You don't put `MOCK_DB` here — the simulator injects it per trial. (If you add an `env` block of your own for other variables, the simulator merges into it rather than overwriting.) The key under `mcpServers` is the `server_name` in `tasks.json` — tool permissions are derived from it (`mcp__tracker__*`), so keep it consistent.

## Smoke-test before simulating

Two checks save you from debugging through agent transcripts later:

```bash
MOCK_DB=/tmp/smoke.db $PY seed_db.py && \
  MOCK_DB=/tmp/smoke.db $PY introspect.py --diff tools.json --stdio "$PY mock_server.py"
```

(Setting `MOCK_DB` here mirrors what the simulator does per trial; without it both scripts fall back to their local default file, which also works for a quick check.)

Then one manual end-to-end write: run a single cheap trial (`run_sim.py tasks.json --tasks <one-id> --trials 1 --out /tmp/smoke`) and confirm the trial's `db.sqlite` actually changed. If the mock crashes on startup, `claude` reports no tools available — check for stdout pollution or a wrong DB path first.
