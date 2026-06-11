# Iteration 1 — tracker skill evaluation

Model: `claude-haiku-4-5-20251001`, 6 tasks x 3 trials per config (18 trials each).
Runs: `runs/iter1/baseline/` and `runs/iter1/with_skill/` (aggregated from per-trial `grading.json`).

## Pass rates per task

| Task | Baseline | With skill |
|---|---|---|
| close-cookie-banner | 3/3 | 3/3 |
| reassign-marcus-urgent | 0/3 | 3/3 |
| create-backfill-task | 3/3 | 3/3 |
| count-todo-tasks | 3/3 | 3/3 |
| unblock-etl | 1/3 | 3/3 |
| assign-devon-fallback | 3/3 | 3/3 |
| **Overall** | **13/18 (72%)** | **18/18 (100%)** |

## Turns and wall time (mean over 18 trials)

| Metric | Baseline | With skill |
|---|---|---|
| num_turns | 7.8 | 8.0 |
| wall_seconds | 25.5 | 22.0 |

Turns are essentially flat; with-skill runs are slightly faster on the wall clock despite doing strictly more correct work (the skill spends a couple of extra turns on `list_users`/`get_task`/pagination but avoids dead-end retries and clarification stalls).

## Conclusion

The skill clearly helps: it lifts the overall pass rate from 72% to 100% by fixing the two tasks baseline reliably failed, at no turn/time cost. On `unblock-etl`, baseline tripped on the title-only-search quirk — `search_tasks(query_text="warehouse sync")` returned nothing because those words only appear in the task description, and the agent gave up and asked the user for a task ID (e.g. `runs/iter1/baseline/unblock-etl/trial-2`); the skill's "drop query_text, filter then get_task to read descriptions" workflow resolves this. On `reassign-marcus-urgent`, baseline never engaged the tracker tools at all — it drifted into unavailable `bash`/echo placeholder calls and ended by asking which tracker system was in use (trials 1 and 2), whereas the skill's reassignment workflow (list_users → search_tasks by assignee_id with pagination → assign_task) made all three trials succeed.
