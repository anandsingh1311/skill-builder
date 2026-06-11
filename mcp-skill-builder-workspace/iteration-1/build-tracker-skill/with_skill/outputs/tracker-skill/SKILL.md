---
name: acme-tracker
description: Use the Acme project tracker MCP server (tracker) correctly for triage work — finding tasks, updating statuses, assigning people, creating tasks/projects, and commenting. Use whenever the user mentions the project tracker, tickets/tasks/issues, triage, assigning work, marking things done, or any tracker tool (search_tasks, update_task_status, assign_task, create_task, add_comment, list_projects, list_users, get_task, create_project).
---

# Acme Project Tracker

The `tracker` MCP server manages projects, tasks, users, and comments. Statuses: `todo`, `in_progress`, `blocked`, `done`. Priorities: `low`, `medium`, `high`, `urgent`. The server has strict rules and cryptic errors — follow the workflows below exactly.

## Tool selection map

| You need to... | Use | Not |
|---|---|---|
| find tasks by words in the **title** | `search_tasks(query_text="login")` | get_task with a guessed id |
| find a task described by its **content/symptoms** (words not in the title) | `search_tasks` with filters (project_id/status), then `get_task` on candidates to read descriptions | `search_tasks(query_text=...)` — it matches **titles only**, never descriptions |
| list a person's tasks | `list_users` first to get their id, then `search_tasks(assignee_id=<id>)` | passing a name anywhere |
| get a project's id or key | `list_projects` | guessing |
| read a task's description/comments/assignee | `get_task(task_id=5)` | search results (they omit description and comments) |
| change status | `update_task_status(task_id=5, status="in_progress")` | inventing statuses like "open"/"closed" |
| assign/reassign | `assign_task(task_id=5, user_id=4)` (numeric user id) | user names or emails |
| create a task | `create_task(project_key="MOB", ...)` — takes the project **KEY** (e.g. "MOB"), not the numeric id | passing project_id |
| comment | `add_comment(task_id=5, body="...", author_id=1)` (numeric author id) | author names |

**Critical inconsistency:** `create_task` takes `project_key` (the short uppercase code like `"DATA"`). Every other tool takes numeric ids. Get keys/ids from `list_projects`.

## Canonical workflows

### Find a task by topic
1. `search_tasks(query_text="<1-2 distinctive words>")` — fewer words match better; it is a substring match on **title only**.
2. No results? The words are probably only in the description. Drop `query_text`; instead `search_tasks(project_id=..., status=...)` to narrow, then `get_task(task_id=...)` on likely candidates to read full descriptions.
3. **Pagination:** results come 5 per page. If the response has `"next_cursor": 5`, you have NOT seen everything — call again with `cursor=5` (then `cursor=10`, ...) until `next_cursor` is `null`. Never count or conclude from page 1 alone.

### Mark a task done
1. `get_task(task_id=12)` — check `assignee_id`. **A task with `assignee_id: null` cannot be moved to done** (server rejects it with `ERR_409`).
2. If unassigned: `list_users` → pick an appropriate user with `"active": 1` → `assign_task(task_id=12, user_id=4)`.
3. `update_task_status(task_id=12, status="done")`.

### Assign work to a person
1. `list_users` — find the person's numeric `id` and check `active`.
2. If `"active": 0` the server will refuse (`ERR_403: user suspended`) — do not retry; pick the fallback the user named, or an active teammate, and say what you did.
3. `assign_task(task_id=3, user_id=4)`.

### Reassign all of a person's tasks (e.g. "move Marcus's urgent tasks to Sara")
1. `list_users` → Marcus's id and Sara's id.
2. `search_tasks(assignee_id=2, ...)` — page through with `cursor` until `next_cursor` is null; collect ALL matching task ids.
3. `assign_task(task_id=..., user_id=<Sara's id>)` for each.

### Create a task
1. `list_projects` → find the project's **key** (e.g. Data Platform → `"DATA"`).
2. `create_task(project_key="DATA", title="...", description="...", priority="high")`. New tasks start as `todo`, unassigned.
3. Need it assigned or in another status? Follow up with `assign_task` / `update_task_status` using the `id` from the create response.

## Error decoder

| Error | Actually means | Do this |
|---|---|---|
| `ERR_409: invalid transition` | you set status `done` on a task with no assignee | `assign_task` to an active user first, then retry the status update |
| `ERR_403: user suspended` | that user has `active: 0`; they can never be assigned | choose an active user instead; never retry the same user |
| `ERR_404: unknown project key` | you passed a project id or name to `create_task` | call `list_projects`, use the `key` field (e.g. `"MOB"`) |
| `ERR_422: invalid status value` | status not in `todo, in_progress, blocked, done` | map user wording: "open"→`todo`, "started/working"→`in_progress`, "stuck/waiting"→`blocked`, "closed/finished/complete"→`done` |
| `ERR_422: invalid priority` | priority not in `low, medium, high, urgent` | map "critical/P0"→`urgent`, "P1"→`high` |
| `ERR_404: task not found` / `user not found` | wrong numeric id | re-look-up via `search_tasks` / `list_users`; don't guess ids |

## Efficiency rules

- Start triage with `list_users` and/or `list_projects` when names are involved — one call each, then you have every id you need.
- Always page through `next_cursor` before reporting counts or "all tasks" answers.
- After writes, the tool response echoes the updated row — read it to confirm; no extra verification call needed. But never claim success if the tool returned an error.
- If the same error occurs twice, stop retrying and re-read the error decoder above.
