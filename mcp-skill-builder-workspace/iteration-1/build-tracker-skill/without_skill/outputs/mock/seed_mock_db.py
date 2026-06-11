#!/usr/bin/env python3
"""Seed a fake tracker database for the mock MCP server.

Same schema as production, similar fake data, plus two extra unassigned
urgent tasks (ids 15, 16) so that triage scenarios and >1-page pagination
are exercised. Usage: seed_mock_db.py <db_path>
"""
import sqlite3
import sys
from pathlib import Path

SCHEMA = """
DROP TABLE IF EXISTS comments;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    priority TEXT NOT NULL DEFAULT 'medium',
    assignee_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE comments (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    author_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

USERS = [
    (1, "Priya Raman", "priya@acme.dev", 1),
    (2, "Marcus Webb", "marcus@acme.dev", 1),
    (3, "Devon Cole", "devon@acme.dev", 0),   # suspended
    (4, "Sara Ito", "sara@acme.dev", 1),
]

PROJECTS = [
    (1, "MOB", "Mobile App"),
    (2, "DATA", "Data Platform"),
    (3, "WEB", "Website Redesign"),
]

TASKS = [
    (1, 1, "Fix login redirect loop on Safari", "Users on Safari 17 get stuck in a redirect loop after OAuth.", "in_progress", "urgent", 2, "2026-05-02"),
    (2, 1, "Add biometric unlock", "Support FaceID/TouchID for app unlock.", "todo", "high", None, "2026-05-03"),
    (3, 1, "Crash on photo upload over cellular", "Intermittent crash uploading >10MB photos on LTE.", "todo", "urgent", 2, "2026-05-04"),
    (4, 1, "Update onboarding illustrations", "Swap in the new brand illustrations.", "todo", "low", None, "2026-05-06"),
    (5, 2, "Nightly ETL job timing out", "The 02:00 UTC warehouse sync exceeds its 2h window.", "blocked", "urgent", 2, "2026-05-07"),
    (6, 2, "Add dbt tests for revenue models", "Coverage for the finance-critical models.", "todo", "medium", None, "2026-05-08"),
    (7, 2, "Deduplicate customer records", "~3% of customer rows are dupes from the CRM import.", "in_progress", "high", 1, "2026-05-10"),
    (8, 2, "Document the events schema", "Producers keep guessing field semantics.", "todo", "low", None, "2026-05-11"),
    (9, 3, "Homepage hero LCP regression", "LCP went from 1.9s to 4.2s after the video header.", "in_progress", "high", 4, "2026-05-12"),
    (10, 3, "Broken anchor links in docs", "Section anchors 404 after the slug change.", "todo", "medium", None, "2026-05-13"),
    (11, 3, "Migrate blog to new CMS", "Move 240 posts, keep redirects.", "todo", "high", 4, "2026-05-14"),
    (12, 3, "Cookie banner shows twice", "Banner re-appears after accepting on subdomains.", "todo", "medium", None, "2026-05-15"),
    (13, 1, "Localize push notifications", "DE/FR/JA translations for push templates.", "todo", "medium", None, "2026-05-16"),
    (14, 2, "Grant analysts read access to staging", "Snowflake role updates for the analyst group.", "done", "medium", 1, "2026-05-17"),
    # extra rows only in the mock fixture:
    (15, 3, "Checkout page 500s under load", "p99 errors spike past 200 rps on the checkout endpoint.", "todo", "urgent", None, "2026-05-18"),
    (16, 1, "Battery drain from background sync", "Sync wakes the radio every 30s; users report 20%/hr drain.", "todo", "urgent", None, "2026-05-19"),
]

COMMENTS = [
    (1, 1, 2, "Repro'd on Safari 17.4 — looks like the state param gets dropped.", "2026-05-03"),
    (2, 5, 2, "Blocked on the warehouse vendor ticket #4821.", "2026-05-08"),
    (3, 9, 4, "Preload + poster image gets us back under 2.5s locally.", "2026-05-13"),
]


def main():
    db = Path(sys.argv[1])
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO users VALUES (?,?,?,?)", USERS)
    con.executemany("INSERT INTO projects VALUES (?,?,?)", PROJECTS)
    con.executemany("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)", TASKS)
    con.executemany("INSERT INTO comments VALUES (?,?,?,?,?)", COMMENTS)
    con.commit()
    con.close()
    print(f"Seeded {db}")


if __name__ == "__main__":
    main()
