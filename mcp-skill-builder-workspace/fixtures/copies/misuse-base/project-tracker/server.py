#!/usr/bin/env python3
"""Acme project tracker MCP server.

Plays the role of the 'real' production server in evals. It has the kinds of
quirks real integrations have (inconsistent key-vs-id parameters, cryptic
errors, hidden transition rules, title-only search, pagination) — exactly the
behavioral surface a generated skill should capture.
"""
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB = Path(__file__).resolve().parent / "tracker.db"
mcp = FastMCP("tracker")

VALID_STATUS = ("todo", "in_progress", "blocked", "done")
VALID_PRIORITY = ("low", "medium", "high", "urgent")
PAGE_SIZE = 5


def query(sql, args=()):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(sql, args).fetchall()]
        con.commit()
        return rows
    finally:
        con.close()


@mcp.tool()
def list_projects() -> list:
    """List all projects with their id, key, and name."""
    return query("SELECT id, key, name FROM projects ORDER BY id")


@mcp.tool()
def list_users() -> list:
    """List all users with their id, name, email, and active flag."""
    return query("SELECT id, name, email, active FROM users ORDER BY id")


@mcp.tool()
def get_task(task_id: int) -> dict:
    """Get full details of a task, including its comments."""
    rows = query("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not rows:
        raise ValueError("ERR_404: task not found")
    task = rows[0]
    task["comments"] = query(
        "SELECT id, author_id, body, created_at FROM comments WHERE task_id = ? ORDER BY id", (task_id,))
    return task


@mcp.tool()
def search_tasks(query_text: str = "", project_id: int | None = None,
                 status: str | None = None, assignee_id: int | None = None,
                 cursor: int = 0) -> dict:
    """Search tasks. Returns up to 5 results per page and a next_cursor when more are available."""
    sql = "SELECT id, project_id, title, status, priority, assignee_id FROM tasks WHERE 1=1"
    args = []
    if query_text:
        sql += " AND title LIKE ?"          # quirk: matches title only, not description
        args.append(f"%{query_text}%")
    if project_id is not None:
        sql += " AND project_id = ?"
        args.append(project_id)
    if status is not None:
        if status not in VALID_STATUS:
            raise ValueError("ERR_422: invalid status value")
        sql += " AND status = ?"
        args.append(status)
    if assignee_id is not None:
        sql += " AND assignee_id = ?"
        args.append(assignee_id)
    sql += " ORDER BY id LIMIT ? OFFSET ?"
    args += [PAGE_SIZE + 1, cursor]
    rows = query(sql, args)
    next_cursor = cursor + PAGE_SIZE if len(rows) > PAGE_SIZE else None
    return {"results": rows[:PAGE_SIZE], "next_cursor": next_cursor}


@mcp.tool()
def create_task(project_key: str, title: str, description: str = "",
                priority: str = "medium") -> dict:
    """Create a task in a project. Priority: low, medium, high, or urgent."""
    if priority not in VALID_PRIORITY:
        raise ValueError("ERR_422: invalid priority")
    proj = query("SELECT id FROM projects WHERE key = ?", (project_key,))  # quirk: key, not id
    if not proj:
        raise ValueError("ERR_404: unknown project key")
    query("INSERT INTO tasks (project_id, title, description, status, priority, created_at)"
          " VALUES (?,?,?,?,?,?)",
          (proj[0]["id"], title, description, "todo", priority, "2026-06-10"))
    return query("SELECT id, project_id, title, status, priority FROM tasks ORDER BY id DESC LIMIT 1")[0]


@mcp.tool()
def update_task_status(task_id: int, status: str) -> dict:
    """Update a task's status. Status: todo, in_progress, blocked, or done."""
    if status not in VALID_STATUS:
        raise ValueError("ERR_422: invalid status value")
    rows = query("SELECT id, assignee_id FROM tasks WHERE id = ?", (task_id,))
    if not rows:
        raise ValueError("ERR_404: task not found")
    if status == "done" and rows[0]["assignee_id"] is None:
        raise ValueError("ERR_409: invalid transition")       # quirk: done requires an assignee
    query("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
    return query("SELECT id, title, status, assignee_id FROM tasks WHERE id = ?", (task_id,))[0]


@mcp.tool()
def assign_task(task_id: int, user_id: int) -> dict:
    """Assign a task to a user by user id."""
    if not query("SELECT id FROM tasks WHERE id = ?", (task_id,)):
        raise ValueError("ERR_404: task not found")
    users = query("SELECT id, active FROM users WHERE id = ?", (user_id,))
    if not users:
        raise ValueError("ERR_404: user not found")
    if not users[0]["active"]:
        raise ValueError("ERR_403: user suspended")           # quirk: inactive users can't be assigned
    query("UPDATE tasks SET assignee_id = ? WHERE id = ?", (user_id, task_id))
    return query("SELECT id, title, assignee_id FROM tasks WHERE id = ?", (task_id,))[0]


@mcp.tool()
def add_comment(task_id: int, body: str, author_id: int) -> dict:
    """Add a comment to a task."""
    if not query("SELECT id FROM tasks WHERE id = ?", (task_id,)):
        raise ValueError("ERR_404: task not found")
    if not query("SELECT id FROM users WHERE id = ?", (author_id,)):
        raise ValueError("ERR_404: user not found")
    query("INSERT INTO comments (task_id, author_id, body, created_at) VALUES (?,?,?,?)",
          (task_id, author_id, body, "2026-06-10"))
    return query("SELECT id, task_id, author_id, body FROM comments ORDER BY id DESC LIMIT 1")[0]


@mcp.tool()
def create_project(name: str, key: str) -> dict:
    """Create a project. Key must be 2-5 uppercase letters and unique."""
    import re
    if not re.fullmatch(r"[A-Z]{2,5}", key):
        raise ValueError("ERR_422: invalid project key format")
    if query("SELECT id FROM projects WHERE key = ?", (key,)):
        raise ValueError("ERR_409: key already exists")
    query("INSERT INTO projects (key, name) VALUES (?,?)", (key, name))
    return query("SELECT id, key, name FROM projects WHERE key = ?", (key,))[0]


if __name__ == "__main__":
    mcp.run()
