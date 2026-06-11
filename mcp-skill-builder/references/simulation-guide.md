# Designing and Running Simulations

The point of simulation is to measure whether the skill transfers knowledge a small model lacks. Design tasks accordingly: each task should be something Haiku *plausibly fumbles without the skill* and *reliably completes with it*.

## Task design

A good task:

- **Ends in verifiable state.** Prefer write tasks — the final database state either matches the assertions or it doesn't. For read-only tasks, use `answer_contains` with a fact that can only come from the right tool calls (an exact id, count, or name from the seed data).
- **Is phrased like a user, not like an API call.** "Marcus is overloaded — move his urgent tasks to Sara" exercises lookup → filter → reassign. "Call assign_task(4, 3)" exercises nothing.
- **Crosses a quirk.** At least half the tasks should pass through the server's tricky paths: the prerequisite step, the cryptic error, the id-vs-name trap, the pagination boundary. Tasks that any model aces tell you nothing about the skill.
- **Doesn't depend on a previous task.** The DB resets between trials; every task starts from the same seed.

4–8 tasks is the sweet spot: enough coverage to trust the numbers, cheap enough to re-run on every skill edit. Cover every workflow the skill documents — an undocumented task type is fine too (tests generalization), but a documented workflow with no task is an untested claim.

Write assertions against the *seed you control*, with exact ids: you wrote the seed, so you know "the login bug" is task 7. Assert the essential end state, not the path — if the user asked to close a task, assert `status='done'`, don't assert which search tool found it.

## Running

Baseline first, then with-skill (sequentially — they share the mock's database file):

```bash
$PY scripts/run_sim.py tasks.json --trials 3 --out runs/iter1/baseline
$PY scripts/run_sim.py tasks.json --trials 3 --skill <skill-dir> --out runs/iter1/with_skill
```

3 trials per task is the floor for seeing flakiness; use more if a result looks suspicious. Each trial is a full Haiku agent run — expect ~30–90s per trial, a few cents each. Keep iteration directories (`runs/iter1`, `runs/iter2`, ...) so you can see whether edits actually moved the numbers.

## Reading the results

`summary.json` gives the headline: pass rate, mean wall time, mean cost per config. The comparison you're after:

| Signal | Interpretation |
|---|---|
| with-skill ≫ baseline pass rate | the skill carries real knowledge — ship it |
| both high | tasks too easy or server self-explanatory; either add harder tasks or report honestly that a skill isn't needed |
| both low | task ambiguity, mock bug, or harness problem — read transcripts before touching the skill |
| with-skill *lower* | the skill is misleading or bloating context; find the section that sent the agent sideways |
| same passes, fewer turns/cost with skill | the skill helps efficiency, not correctness — still valuable, report it as such |

## Diagnosing failures

For each failed trial, open `result.json` first — the `tool_calls` list shows the agent's whole plan at a glance — then `transcript.jsonl` for the agent's reasoning and the error texts it saw. Classify each failure:

1. **Wrong tool** — never found the right entry point → improve the tool selection map.
2. **Bad argument** — name where id belongs, invalid enum, wrong id → add/fix the verbatim example in the workflow.
3. **Missing prerequisite** — skipped the required earlier step → make the workflow's step order explicit and say why.
4. **Error abandonment** — hit a cryptic error, retried the same thing or quit → add it to the error decoder.
5. **False success** — claimed done, DB says otherwise → tell the skill to verify with a read-back call before finishing.
6. **Harness/mock bug** — tool crashed, no tools available, assertion checks the wrong row → fix the mock or task, not the skill, and treat the trial as void.

Fix the skill (or mock) and re-run. Two clean iterations in a row with high with-skill pass rate = done.

## Honest reporting

Report both configs' numbers, the trial count, and any tasks you changed between iterations (changing tasks resets comparability). If the skill only helps marginally, say so — a 9/9 vs 8/9 result on 3 trials is noise, not a win.
