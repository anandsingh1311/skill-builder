---
name: project-tracker
description: How to correctly use the Acme "tracker" MCP server (list_projects, list_users, get_task, search_tasks, create_task, update_task_status, assign_task, add_comment, create_project). Use this skill whenever a task involves the tracker — creating or finding tasks, assigning people, changing status, commenting, or creating projects — even for simple-looking requests. It explains the server's id-vs-key conventions, its ERR_4xx error codes and how to recover from them, and its search/pagination quirks.
---

# Acme project tracker MCP server

The tracker API is quirky. Tool parameters are inconsistent (some want numeric
ids, one wants a string key), errors are terse codes, and there are hidden
business rules. Follow the conventions below and most errors never happen; when
they do, every one of them has a known recovery.

## Golden rule: resolve names to ids first

Users speak in names ("Sara Ito", "the Mobile App project"). The API speaks in
numeric ids — except `create_task`, which wants the project **key**. Never pass
a person's name or a project's name where an id is expected; it will fail or,
worse, silently match nothing.

Start almost every job with one or both of these cheap calls and keep the
results around:

- `list_projects` → `[{id, key, name}]` — e.g. `{id: 1, key: "MOB", name: "Mobile App"}`
- `list_users` → `[{id, name, email, active}]`

## Which identifier does each tool want?

| Tool | Identifier it takes |
|---|---|
| `create_task` | `project_key` — the short uppercase **key** (e.g. `"MOB"`), NOT the project id and NOT the project name |
| `assign_task` | `task_id` (int) + `user_id` (int) |
| `add_comment` | `task_id` (int) + `author_id` (int, the commenting user's id) |
| `update_task_status`, `get_task` | `task_id` (int) |
| `search_tasks` | optional `project_id` (int) and `assignee_id` (int) |

Enums (anything else → ERR_422):
- status: `todo`, `in_progress`, `blocked`, `done`
- priority: `low`, `medium`, `high`, `urgent`

## Hidden business rules (the source of "weird" errors)

1. **A task can only be marked `done` if it has an assignee.** Calling
   `update_task_status(task_id, "done")` on an unassigned task returns
   `ERR_409: invalid transition`. Recovery: `assign_task` to the appropriate
   user first (ask the data: who completed it / who is mentioned?), then
   retry the status update. Do not give up on ERR_409 — it is always fixable.
2. **Inactive (suspended) users cannot be assigned tasks.** `assign_task`
   returns `ERR_403: user suspended`. Check the `active` flag in `list_users`.
   If the requested assignee is suspended, fall back to whatever the user's
   instructions say (or report it clearly) — don't retry the same call.
3. **Project keys must be unique and match `[A-Z]{2,5}`.** `create_project`
   returns `ERR_409: key already exists` for a taken key (pick a different
   2-5 uppercase-letter key and retry) and `ERR_422: invalid project key
   format` for anything not 2-5 uppercase letters.

## Error code cheat sheet

| Code | Meaning | What to do |
|---|---|---|
| ERR_404 | id/key doesn't exist | You probably passed a name, a wrong id, or a project id where a key belongs. Re-resolve via `list_projects` / `list_users` / `search_tasks`. |
| ERR_403 | user suspended | Pick an active user or report back; never assignable. |
| ERR_409 | business-rule conflict | `done` without assignee → assign first, retry. Duplicate project key → choose another key, retry. |
| ERR_422 | bad enum / key format | Fix the value to one of the valid enums / key pattern. |

## Search and pagination quirks

- `search_tasks(query_text=...)` matches the **title only**, not descriptions.
  If a title search misses, try shorter/different title words, or filter by
  `project_id`/`status` and scan the results instead.
- Results come **5 per page**. The response is `{results, next_cursor}`;
  when `next_cursor` is not null there are more pages — call again with
  `cursor=next_cursor` until it is null. Never count or summarize from the
  first page alone.

## Worked example

"Sara finished the onboarding illustrations task — mark it done."

1. `list_users` → Sara Ito has id 4 (and is active).
2. `search_tasks(query_text="onboarding illustrations")` → task id 4, `assignee_id: null`.
3. Task is unassigned, so going straight to `done` would hit ERR_409.
   `assign_task(task_id=4, user_id=4)` first.
4. `update_task_status(task_id=4, status="done")` → success.
