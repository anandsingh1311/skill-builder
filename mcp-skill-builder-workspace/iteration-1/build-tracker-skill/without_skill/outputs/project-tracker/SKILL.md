---
name: project-tracker
description: How to use the Acme project-tracker MCP tools (tracker) correctly for triage work — searching tasks, updating statuses, assigning people, creating tasks, adding comments. Use this skill whenever the user asks to find, list, triage, update, assign, close, or create tasks in the tracker, or mentions projects like Mobile App / Data Platform / Website Redesign, even if they don't name the tracker explicitly. The tracker API has hidden rules (pagination, title-only search, assignee-before-done) that cause silent wrong answers if you skip this skill.
---

# Acme Project Tracker — triage guide

The tracker API has quirks that silently produce wrong answers if you don't know them. Follow these rules exactly.

## The 5 rules that prevent most mistakes

1. **search_tasks is paginated: 5 results per page.** The response has `results` and `next_cursor`. If `next_cursor` is not null, you have NOT seen all matches — call `search_tasks` again with `cursor=<next_cursor>` and repeat until `next_cursor` is null. Never answer a "find/list/count all" question from the first page alone.
2. **search_tasks matches TITLES only.** Words that appear only in a task's description (e.g. "OAuth", error details) return zero results. If a search comes up empty, retry with a different word likely to be in the title, or list the project's tasks (`search_tasks` with just `project_id`) and pick the right one yourself.
3. **There is no priority filter.** `search_tasks` filters by `query_text`, `project_id`, `status`, `assignee_id` only. To find e.g. "urgent" tasks, page through all candidate tasks and filter by `priority` yourself from the results.
4. **A task can only be set to `done` if it has an assignee.** If you need to close a task, first check/assign the assignee (`assign_task`), then call `update_task_status(..., "done")`. Otherwise you get `ERR_409: invalid transition`.
5. **`create_task` takes the project KEY (a string like "MOB"), not the numeric project id.** Every other tool uses numeric ids. Call `list_projects` to map names → keys: Mobile App = MOB, Data Platform = DATA, Website Redesign = WEB.

## Tool cheat sheet

| Tool | Parameters | Notes |
|---|---|---|
| `list_projects` | – | id, key, name. Keys are strings like "MOB". |
| `list_users` | – | id, name, email, `active`. Only `active=1` users can be assigned. |
| `get_task` | `task_id` (int) | Full details + comments. |
| `search_tasks` | `query_text`, `project_id`, `status`, `assignee_id`, `cursor` | All optional. Title-only match; 5/page; follow `next_cursor`. |
| `create_task` | `project_key` (str!), `title`, `description`, `priority` | New tasks start as `todo`, unassigned. |
| `update_task_status` | `task_id`, `status` | `done` requires an assignee (rule 4). |
| `assign_task` | `task_id`, `user_id` | Fails for inactive users (`ERR_403`). |
| `add_comment` | `task_id`, `body`, `author_id` | `author_id` is a user id. |
| `create_project` | `name`, `key` | Key must be 2–5 UPPERCASE letters, unique. |

Allowed `status` values: `todo`, `in_progress`, `blocked`, `done`.
Allowed `priority` values: `low`, `medium`, `high`, `urgent`.

## Error decoder

| Error | Real meaning | Fix |
|---|---|---|
| `ERR_409: invalid transition` | You set `done` on a task with no assignee | Assign someone first, then retry |
| `ERR_403: user suspended` | That user is inactive (`active=0`) | Check `list_users`; pick an active user (ask or use the stated fallback) |
| `ERR_404: unknown project key` | You passed a project name or numeric id to `create_task` | Use the short uppercase key from `list_projects` |
| `ERR_422: invalid status value` / `invalid priority` | Typo or value outside the allowed lists above | Use an exact allowed value |
| `ERR_404: task not found` / `user not found` | Bad numeric id | Re-look-up the id via `search_tasks` / `list_users` |

An error never means "impossible" — it means one precondition is unmet. Fix the precondition and retry instead of giving up.

## Recipes

**Find ALL tasks matching a condition (count/list/triage):**
1. `search_tasks` with the narrowest supported filters (`status`, `project_id` — remember: no priority filter).
2. Loop: while `next_cursor` is not null, call again with `cursor=next_cursor`, accumulating `results`.
3. Apply any remaining conditions (priority, unassigned ⇒ `assignee_id` is null) to the accumulated list yourself.

**Close a task as done:**
1. `get_task` → check `assignee_id`.
2. If null, `assign_task` to the person who did the work (look up their id in `list_users`).
3. `update_task_status(task_id, "done")`.

**Assign a task to a person by name:**
1. `list_users` → find the id AND check `active=1`.
2. If the person is inactive, don't try anyway — use the fallback the user gave, or report it back.
3. `assign_task(task_id, user_id)`.

**Find a task described loosely ("the OAuth bug", "the cookie thing"):**
1. Try `search_tasks(query_text=<a distinctive word likely in the TITLE>)`.
2. Empty? Try other words, or list the likely project's tasks and use `get_task` to check descriptions.
3. Confirm you have the right task (title matches intent) before mutating it.

Before reporting completion, verify each write actually happened (the tool's return value shows the new state).
