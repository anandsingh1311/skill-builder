# Iteration 1 evaluation report — `project-tracker` skill

Model: `claude-haiku-4-5-20251001`, 6 tasks x 3 trials per config (18 trials each).
Graded against final SQLite DB state (`runs/iter1/*/*/trial-*/grading.json`).

## Pass rates per task

| Task | Baseline | With skill |
|---|---|---|
| close-payment-webhook | 2/3 | 3/3 |
| create-passkey-task | 3/3 | 3/3 |
| reassign-marcus-urgent | 3/3 | 3/3 |
| tls-suspended-fallback | 3/3 | 3/3 |
| ops-todo-sweep | 3/3 | 3/3 |
| checkout-stripe | 3/3 | 3/3 |
| **Overall** | **17/18 (94.4%)** | **18/18 (100%)** |

## Efficiency

| Metric (mean over 18 trials) | Baseline | With skill |
|---|---|---|
| num_turns | 8.8 | 7.7 |
| wall_seconds | 29.5 | 18.9 |

## Conclusion

The skill took the suite from 17/18 to 18/18 and made every run faster (-36% mean wall time) and more direct. On the user-reported failure modes: no baseline trial in this run literally passed a name where an id belongs, but the transcripts show the adjacent failure the skill targets — in the one baseline failure (`baseline/close-payment-webhook/trial-2`) the agent never resolved ids at all, flailed with `echo`/`Skill` pseudo-calls, and abandoned the task by asking the user to supply the task id; with the skill loaded, every trial resolved ids up front via `search_tasks`/`list_users` exactly as instructed. ERR_409 abandonment is also addressed: the only ERR_409 in all 36 transcripts occurred in baseline (`baseline/close-payment-webhook/trial-1`, `update_task_status` to `done` on an unassigned task), which that trial recovered from only after extra subagent turns, whereas the with-skill runs never triggered a 409 because the skill's "assign before marking done" workflow removes the invalid transition entirely. Baseline was already strong on this small suite, so the skill's main demonstrated value is eliminating the misuse/abandonment tail and cutting turns and latency.
