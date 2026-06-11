#!/usr/bin/env python3
"""Seed the MOCK tracker database with deterministic fake data.

This is a throwaway test database — it never touches the production tracker.db.
Run before every simulation trial to reset state.
"""
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "tracker.db"
SCHEMA = (HERE / "schema.sql").read_text()

USERS = [
    # id, name, email, active
    (1, "Priya Raman", "priya@acme.dev", 1),
    (2, "Marcus Webb", "marcus@acme.dev", 1),
    (3, "Devon Cole", "devon@acme.dev", 0),    # suspended
    (4, "Sara Ito", "sara@acme.dev", 1),
    (5, "Tomas Rivera", "tomas@acme.dev", 1),
    (6, "Hannah Birch", "hannah@acme.dev", 0),  # suspended
]

PROJECTS = [
    (1, "MOB", "Mobile App"),
    (2, "DATA", "Data Platform"),
    (3, "WEB", "Website Redesign"),
    (4, "OPS", "Internal Ops"),
]

TASKS = [
    # id, project, title, description, status, priority, assignee, created
    (1, 1, "Fix login redirect loop on Safari", "Users on Safari 17 get stuck in a redirect loop after OAuth.", "in_progress", "urgent", 2, "2026-05-02"),
    (2, 1, "Add biometric unlock", "Support FaceID/TouchID for app unlock.", "todo", "high", None, "2026-05-03"),
    (3, 1, "Crash on photo upload over cellular", "Intermittent crash uploading >10MB photos on LTE.", "todo", "urgent", 2, "2026-05-04"),
    (4, 1, "Update onboarding illustrations", "Swap in the new brand illustrations.", "todo", "low", None, "2026-05-06"),
    (5, 1, "Payment webhook retries dropped", "PSP retry callbacks are acked but never re-queued, so refunds stall.", "todo", "urgent", None, "2026-05-07"),
    (6, 1, "Localize push notifications", "DE/FR/JA translations for push templates.", "todo", "medium", None, "2026-05-08"),
    (7, 2, "Nightly ETL job timing out", "The 02:00 UTC warehouse sync exceeds its 2h window.", "blocked", "urgent", 2, "2026-05-09"),
    (8, 2, "Add dbt tests for revenue models", "Coverage for the finance-critical models.", "todo", "medium", None, "2026-05-10"),
    (9, 2, "Deduplicate customer records", "~3% of customer rows are dupes from the CRM import.", "in_progress", "high", 1, "2026-05-11"),
    (10, 2, "Document the events schema", "Producers keep guessing field semantics.", "todo", "low", None, "2026-05-12"),
    (11, 2, "Backfill currency conversion rates", "Historical FX rates for 2024 invoices.", "todo", "medium", 5, "2026-05-13"),
    (12, 2, "Grant analysts read access to staging", "Snowflake role updates for the analyst group.", "done", "medium", 1, "2026-05-14"),
    (13, 3, "Homepage hero LCP regression", "LCP went from 1.9s to 4.2s after the video header.", "in_progress", "high", 4, "2026-05-15"),
    (14, 3, "Broken anchor links in docs", "Section anchors 404 after the slug change.", "todo", "medium", None, "2026-05-16"),
    (15, 3, "Migrate blog to new CMS", "Move 240 posts, keep redirects.", "todo", "high", 4, "2026-05-17"),
    (16, 3, "Cookie banner shows twice", "Banner re-appears after accepting on subdomains.", "todo", "medium", None, "2026-05-18"),
    (17, 3, "Checkout orders stuck in pending", "Stripe webhook failures leave paid orders in pending; support queue is filling up.", "todo", "high", None, "2026-05-19"),
    (18, 3, "Rotate TLS certificates for subdomains", "Wildcard cert expires 2026-07-01; rotate across all subdomains.", "todo", "medium", None, "2026-05-20"),
    (19, 4, "Renew SOC2 evidence collection", "Quarterly evidence pull for the auditors.", "todo", "medium", None, "2026-05-21"),
    (20, 4, "Upgrade CI runners to Ubuntu 24.04", "20.04 images go EOL in September.", "todo", "medium", None, "2026-05-22"),
    (21, 4, "Consolidate Slack alert channels", "We have 14 overlapping alert channels.", "todo", "low", None, "2026-05-23"),
    (22, 4, "Rotate AWS access keys", "Quarterly key rotation for service accounts.", "todo", "high", None, "2026-05-24"),
    (23, 4, "Archive stale Confluence spaces", "37 spaces untouched for >18 months.", "todo", "low", None, "2026-05-25"),
    (24, 4, "Migrate cron jobs to scheduler service", "Move the remaining 11 crontabs.", "todo", "medium", None, "2026-05-26"),
    (25, 4, "Patch bastion hosts", "Apply the May kernel security updates.", "todo", "high", None, "2026-05-27"),
    (26, 4, "Decommission legacy VPN", "Cut over the last 9 users to the new mesh.", "in_progress", "medium", 5, "2026-05-28"),
    (27, 1, "Offline mode for reading list", "Cache articles for airplane mode.", "todo", "low", None, "2026-05-29"),
    (28, 2, "Alert on schema drift", "Page when producers add unregistered fields.", "todo", "medium", 2, "2026-05-30"),
    (29, 1, "Reduce app cold start time", "Cold start is 3.8s on mid-tier Android.", "in_progress", "high", 5, "2026-05-31"),
    (30, 3, "Add sitemap.xml generation", "Regenerate on publish.", "todo", "low", None, "2026-06-01"),
]

COMMENTS = [
    (1, 1, 2, "Repro'd on Safari 17.4 — looks like the state param gets dropped.", "2026-05-03"),
    (2, 7, 2, "Blocked on the warehouse vendor ticket #4821.", "2026-05-10"),
    (3, 13, 4, "Preload + poster image gets us back under 2.5s locally.", "2026-05-16"),
    (4, 22, 1, "Coordinate with platform team before rotating the CI keys.", "2026-05-25"),
]


def main():
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO users VALUES (?,?,?,?)", USERS)
    con.executemany("INSERT INTO projects VALUES (?,?,?)", PROJECTS)
    con.executemany("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)", TASKS)
    con.executemany("INSERT INTO comments VALUES (?,?,?,?,?)", COMMENTS)
    con.commit()
    con.close()
    print(f"Seeded mock DB at {DB}")


if __name__ == "__main__":
    main()
