# Eval Report: project-tracker skill vs. no skill (mock MCP server)

- **Model:** claude-haiku-4-5-20251001, 3 trials per task per config, 36 runs total.
- **Setup:** each trial got a freshly seeded SQLite db behind the mock tracker MCP server
  (`mock/mock_server.py`); the with-skill config prepended an instruction to read
  `project-tracker/SKILL.md` first. Graded programmatically by `eval/grade.py` against the
  trial db end-state (and `IDS:` lines for list tasks). No trial hit a session limit,
  timeout, or parse error.

## Pass rates per task

| Task | With skill | Without skill |
|---|---|---|
| list-all-todo | 3/3 | 3/3 |
| close-needs-assignee | 3/3 | 3/3 |
| assign-suspended-fallback | 3/3 | 3/3 |
| create-task-by-key | 3/3 | 3/3 |
| search-title-only | 3/3 | 3/3 |
| triage-urgent-unassigned | 3/3 | 3/3 |
| **TOTAL** | **18/18 (100%)** | **18/18 (100%)** |

## Aggregate efficiency

| Metric | With skill | Without skill |
|---|---|---|
| Pass rate | 1.000 | 1.000 |
| Mean cost (USD) | 0.051 | 0.059 |
| Mean duration (s) | 25.6 | 37.1 |
| Mean turns | 8.4 | 7.1 |

## Conclusion

The generated skill does not improve correctness on this eval: haiku already passes all six
tasks (pagination, the done-requires-assignee hidden rule, the suspended-assignee fallback,
the project-key quirk, the title-only search quirk, and multi-step triage) without it, so
there is no headroom for the skill to demonstrate value on pass rate. The skill does make
runs cheaper (~14% lower mean cost) and faster (~31% lower mean wall time), suggesting it
reduces trial-and-error exploration of the server's quirks, at the cost of slightly more
turns (the extra Read of SKILL.md). To discriminate between configs, the eval would need
harder tasks or a weaker baseline, since the current task set is saturated.
