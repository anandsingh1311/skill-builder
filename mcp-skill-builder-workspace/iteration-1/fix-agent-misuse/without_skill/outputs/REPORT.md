# Project-Tracker Skill — Simulation Report

- **Model:** claude-haiku-4-5-20251001, 3 trials per task per config (36 runs total)
- **Server:** mocked tracker MCP server (`mock-server/`), fresh seeded sqlite DB per run
- **Grading:** ground-truth DB inspection (`grading/grade.py`); full detail in `grading/grading.json`

## Pass rates per task

| Task | with_skill | without_skill |
|---|---|---|
| create-task-project-key | 3/3 | 3/3 |
| done-requires-assignee | 3/3 | 3/3 |
| suspended-user-fallback | 3/3 | 3/3 |
| comment-author-id | 3/3 | 3/3 |
| paginated-count | 3/3 | 3/3 |
| duplicate-project-key | 3/3 | 3/3 |
| **Overall** | **18/18 = 100%** | **18/18 = 100%** |

## Efficiency (mean agent turns, where the configs differ)

| Task | with_skill | without_skill |
|---|---|---|
| done-requires-assignee (ERR_409 quirk) | 6.0 | 11.0 |
| comment-author-id (numeric author_id quirk) | 5.7 | 7.0 |
| create-task-project-key (project_key quirk) | 4.0 | 5.0 |

## Conclusion

On final outcomes both configurations passed every trial (100% vs 100%), so the skill produced no measurable pass-rate lift in this batch — the mock server's descriptive error messages let haiku recover from its initial mistakes on its own. However, the user-reported failure modes did surface without the skill: the baseline hit ERR_409 / wrong-argument errors and only succeeded after trial-and-error retries (e.g., done-requires-assignee averaged 11 turns vs 6 with the skill), whereas with the skill the agent passed project keys and numeric ids correctly on the first attempt and pre-assigned before closing tasks. The skill therefore does fix the misuse patterns (names where ids belong; ERR_409 handling) at the behavioral level, converting recover-after-error runs into first-try-correct runs; to see a pass-rate gap, the grader would need to penalize error-then-retry trajectories, or the mock server's error messages would need to be as terse as the real server's.
