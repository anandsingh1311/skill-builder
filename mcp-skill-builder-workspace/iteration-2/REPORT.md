# Iteration 2 — confirm per-trial DB isolation

**Goal:** verify the iteration-2 change to `mcp-skill-builder` — each simulation trial gets its
own freshly-seeded throwaway database (via a `MOCK_DB` env var) instead of one shared DB reset
in place — works end-to-end with real Haiku runs, and doesn't weaken the safety story.

**Method:** rebuilt the project-tracker mock harness using the *updated* skill conventions
(mock + `seed_db.py` read `$MOCK_DB`; `tasks.json` uses `db_env`/`seed`), verified tool parity
against the production fixture, then ran Haiku against it with and without the generated
`acme-tracker` skill — 4 quirk-crossing tasks × 2 trials × 2 configs = 16 trials.

## Results

| | Baseline (no skill) | With generated skill |
|---|---|---|
| Pass rate | 7/8 (88%) | **8/8 (100%)** |
| Mean turns | 10.1 | 6.8 |
| Mean wall | 28.1s | 17.2s |
| Mean cost | $0.0557 | $0.0455 |

The only baseline failure is `mark-biometric-done` (the `ERR_409` "assign before you can mark
done" trap) — exactly the planted quirk the skill exists to teach. With the skill, Haiku passes
it every time, and is also faster and cheaper across the board (unlike iteration-1, these
time/cost numbers are trustworthy — no session-limit disruption this round).

## Harness invariants (the actual point of this iteration)

1. **Per-trial isolation works.** 16 distinct `runs/<config>/<task>/trial-N/db.sqlite` files,
   each built fresh by `seed_db.py` honoring `$MOCK_DB`, with the path injected into a per-trial
   `mock-config.json`. Two trials of the same task have fully independent final state — proven by
   the same task showing `(in_progress, None)` in one trial's DB and `(done, 1)` in another's.
2. **Production stays untouched.** The fixture `tracker.db` SHA-256 is byte-identical before and
   after all trials. The real tracker is never written to — the core safety guarantee holds.
3. **Plumbing is correct.** `run_sim.py` seeds → injects `$MOCK_DB` → runs Haiku → grades that
   trial's own DB. Legacy `db`+`reset` task files still run (with a deprecation note).

## Bonus finding + fix: agent working-directory leak

One with-skill trial initially failed for an unexpected reason: the inner Haiku agent never
called the MCP tools. It poked around the filesystem (`find`, `curl localhost`, reading
`mock_server.py`/`seed_db.py`), found the SQLite file, and tried to edit it directly with a
Python script — then asked for permission (denied in headless mode, so nothing happened).

- **Safety held anyway:** the bypass was blocked (`Bash`/`Write` aren't in `allowedTools`) and the
  relative path it targeted wasn't production. Production DB stayed identical.
- **But it made the sim unfaithful:** a production agent can't read the server's source, so the
  simulator shouldn't let the inner agent either.
- **Fix (folded into the skill):** `run_sim.py` now runs each trial in an empty `agent_cwd/`
  sandbox, so the agent reaches the server only through MCP and the skill (both passed by absolute
  path). After the fix: 86 MCP tool calls vs 8 (blocked) filesystem attempts, and the previously
  flaky `assign-mob-unassigned` task passes 2/2.

This also surfaced and fixed a latent bug: per-trial config/DB paths are now resolved absolute,
so the harness no longer depends on the caller's working directory.

## Verdict

The per-trial DB isolation change is confirmed correct, safe, and an improvement on every axis
measured (reliability, turns, wall, cost). The cwd-isolation hardening makes the simulation a
more faithful stand-in for production. Both changes are now part of the shipped skill.
