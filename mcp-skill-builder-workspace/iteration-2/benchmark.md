# Iteration 2 — per-trial DB isolation: confirmation

Inner agent: **Haiku** · 2 trials/task · domain: project-tracker fixture (the same 9 quirk-laden tools as iteration 1)

## Pass rate (Haiku driving the mocked tracker)

| Task | Quirk it crosses | Baseline | With generated skill |
|---|---|---|---|
| `mark-biometric-done` | ERR_409 — must assign before `done` | 1/2 | 2/2 |
| `find-warehouse-task` | title-only search (term is in description) | 2/2 | 2/2 |
| `create-data-task` | `create_task` wants project **key**, not id | 2/2 | 2/2 |
| `assign-mob-unassigned` | name→id, filtering, no-suspended, pagination | 2/2 | 2/2 |
| **Overall** | | **7/8 (88%)** | **8/8 (100%)** |

## Cost / efficiency (means)

| | Baseline | With skill |
|---|---|---|
| mean turns | 10.1 | 6.8 |
| mean wall (s) | 28.1 | 17.2 |
| mean cost (USD) | 0.0557 | 0.0455 |

## Harness invariants verified

- **Production DB untouched** — fixture `tracker.db` SHA-256 identical before/after all 16 trials.
- **Per-trial isolation** — 16 distinct `db.sqlite` files, one per trial, each freshly seeded; same-task trials have independent final state (no bleed).
- **Agent cwd isolated** — every `agent_cwd/` empty; the inner agent cannot read the mock's source.
- **Faithful tool use** — 86 MCP tool calls vs 8 (blocked) filesystem-bypass attempts.
