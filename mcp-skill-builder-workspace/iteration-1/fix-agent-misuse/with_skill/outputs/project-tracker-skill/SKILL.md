---
name: project-tracker
description: How to use the Acme project tracker MCP server (tools mcp__tracker__*) correctly. Use whenever working with tracker tasks, projects, users, assignments, or comments — creating tasks, closing/updating tasks, assigning work, reassigning workloads, searching tasks, or adding comments — and whenever a tracker call returns an ERR_4xx error.
---

# Acme Project Tracker

The tracker manages **projects** (id + key like `MOB`), **tasks** (numeric id, status, priority, assignee), **users** (numeric id, may be suspended), and **comments**. Most mistakes come from passing the wrong identifier type or skipping a required prerequisite step. Follow the rules below exactly.

## Identifier rules (most important)

- **Every tool takes numeric ids** for tasks and users: `task_id`, `user_id`, `assignee_id`, `author_id`. NEVER pass a person's name or email where an id goes.
- **Exception:** `create_task` takes `project_key` — the short uppercase string like `"MOB"`, NOT the project id and NOT the project name. Every other tool that filters by project takes the numeric `project_id`.
- You don't know ids in advance. Resolve them first:
  - user name → id: call `list_users`, match the name, use the `id`. Check `active` is `1`.
  - project name → key/id: call `list_projects`, match the name, use `key` for `create_task` and `id` for `search_tasks`.

## Tool selection map

| You need to... | Use | Not |
|---|---|---|
| find a task by words in its title | `search_tasks(query_text="checkout")` | guessing task ids |
| list tasks in a project / by status / by assignee | `search_tasks(project_id=3, status="todo", assignee_id=2)` | fetching everything unfiltered |
| read one task's details/comments | `get_task(task_id=17)` | search |
| look up a user's id | `list_users` | passing a name as an id |
| look up a project's key or id | `list_projects` | guessing |
| make a new task | `create_task(project_key="MOB", title="...", priority="high")` | passing project id/name |
| change status | `update_task_status(task_id=17, status="in_progress")` | |
| set/replace the assignee | `assign_task(task_id=17, user_id=4)` | |
| comment | `add_comment(task_id=17, body="...", author_id=1)` | |
| make a new project | `create_project(name="Customer Portal", key="CP")` | |

Enums (exact lowercase strings):
- status: `todo`, `in_progress`, `blocked`, `done`
- priority: `low`, `medium`, `high`, `urgent`

## Canonical workflows

### Marking a task done
A task can only be set to `done` if it HAS an assignee. Always check first:
1. `get_task(task_id=5)` — look at `assignee_id`.
2. If `assignee_id` is null: `list_users` → pick the right active user → `assign_task(task_id=5, user_id=4)`.
3. `update_task_status(task_id=5, status="done")`.

If the user says who did the work, assign that person before closing so the task is credited correctly.

### Creating a task
1. `list_projects` → find the project the user named → note its `key` (e.g. Mobile App → `"MOB"`).
2. `create_task(project_key="MOB", title="Support passkey sign-in", description="...", priority="high")`.
3. New tasks always start as `todo` with no assignee. If the user wants it assigned or started, follow up with `assign_task` / `update_task_status` using the returned task `id`.

### Assigning work
1. `list_users` → find the user → confirm `active` is `1`.
2. If the requested user has `active: 0` they are suspended and CANNOT be assigned. Tell the user, or if asked for a fallback, pick another active user and explain in a comment.
3. `assign_task(task_id=18, user_id=4)`. This replaces any previous assignee.

### Reassigning someone's tasks
1. `list_users` → ids of both people.
2. `search_tasks(assignee_id=2)` — page through ALL results first (see pagination below).
3. Keep only the tasks matching the user's criteria (e.g. `priority == "urgent"`).
4. `assign_task(...)` for each one.

### Creating a project
- `key` must be 2–5 UPPERCASE letters, unique. Derive one from the name: "Customer Portal" → `"CP"` or `"PORT"`.
- `create_project(name="Customer Portal", key="CP")`, then use that `key` for any `create_task` calls.

## Searching: quirks that matter

- `query_text` matches the **title only**, never the description, and it's a plain substring match. Search with ONE short distinctive word (`"checkout"`, not `"Stripe webhook failures"`). If you get zero results, retry with a different single word from the user's phrasing before concluding the task doesn't exist.
- Results come in pages of 5. If the response has a non-null `next_cursor`, there ARE more results: call again with `cursor=<next_cursor>` and repeat until `next_cursor` is null.
- **Collect every page BEFORE making any updates.** Updating tasks changes what the filtered search returns, which shifts the cursor and silently skips rows. Gather the full id list first, then do the writes.

## Error decoder

| Error | Actually means | Do this |
|---|---|---|
| `ERR_409: invalid transition` | the task has no assignee; `done` requires one | `assign_task` an active user, then retry `update_task_status` |
| `ERR_409: key already exists` | that project key is taken | pick a different 2–5 uppercase-letter key and retry |
| `ERR_403: user suspended` | that user's `active` flag is 0 | choose an active user from `list_users` |
| `ERR_404: unknown project key` | you passed a project id or name to `create_task` | call `list_projects`, use the `key` string (e.g. `"MOB"`) |
| `ERR_404: task not found` / `user not found` | wrong numeric id | re-resolve the id via search/list tools |
| `ERR_422: invalid status value` / `invalid priority` | not one of the exact enum strings | use the exact lowercase values listed above |
| `ERR_422: invalid project key format` | key isn't 2–5 uppercase letters | shorten/uppercase the key |

Never retry the identical call after an error — the decoder above tells you what to change. If the same error happens twice, re-read this table.

## Efficiency rules

- Use `search_tasks` filters (`project_id`, `status`, `assignee_id`) instead of paging through everything.
- Call `list_users` / `list_projects` at most once each; remember the ids.
- After your final write, verify with one `get_task` read-back that the state matches what the user asked for before reporting success.
