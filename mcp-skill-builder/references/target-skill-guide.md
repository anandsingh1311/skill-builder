# Writing the Target Skill

This is the deliverable: a skill that makes agents use the target MCP server well. You're writing it for the *weakest* model that will plausibly use it — assume Haiku. Small models follow explicit, concrete instructions reliably; they do not infer well from abstractions. Every sentence should either tell the model what to do in a specific situation or save it from a known failure mode.

## What goes in it

Structure that works (adapt as needed):

```
<server>-skill/
└── SKILL.md
    ├── frontmatter: name + description (pushy — list the user phrasings that should trigger it)
    ├── One paragraph: what this server is, what state it manages
    ├── Tool selection map
    ├── Canonical workflows
    ├── Errors and what they actually mean
    └── Efficiency rules
```

Keep it in one SKILL.md unless it genuinely exceeds ~300 lines; small models benefit from having everything in context. The exception is large servers (roughly 30+ tools): one file would bury the workflow the agent actually needs under twenty it doesn't. Split by domain area — SKILL.md keeps the frontmatter, the tool selection map, and a router ("issue/PR work → read `references/issues.md`; CI and workflows → `references/actions.md`"), and each reference file carries that area's workflows and error decoder. The agent then loads only the slice it needs.

**Tool selection map** — for each intent, the right starting tool:

```markdown
| You need to... | Use | Not |
|---|---|---|
| find a task by words in its title | search_tasks(query=...) | listing everything and scanning |
| look up a user's id | list_users | guessing or passing a name |
```

**Canonical workflows** — the multi-tool sequences with *verbatim* example calls and realistic arguments. This is the highest-value section. Write the sequence the way the server demands it, including the non-obvious prerequisite steps:

```markdown
### Closing a task
1. `get_task(task_id=7)` — check it has an assignee. Unassigned tasks cannot be closed.
2. If unassigned: `list_users` → pick an active user → `assign_task(task_id=7, user_id=2)`
3. `update_task_status(task_id=7, status="done")`
```

**Error decoder** — the cryptic errors, their real meaning, and the recovery action:

```markdown
| Error | Actually means | Do this |
|---|---|---|
| ERR_409: invalid transition | task has no assignee; "done" requires one | assign_task first, then retry |
```

**Efficiency rules** — what burns turns: use filters instead of paginating everything, batch reads before writes, don't re-fetch what you already have. Small models loop; tell them when to stop (e.g. "if the same error occurs twice, re-read the error decoder rather than retrying a third time").

## When to bundle scripts

Default to **no scripts** — a simple CRUD surface needs a selection map and workflows, nothing more. But first understand the constraint that shapes everything: **bundled scripts cannot call MCP tools.** Scripts run through Bash; the tools belong to the agent. So a script never replaces a tool call — it handles the deterministic work *around* the calls, which is exactly where small models lose trials:

- **Payload construction/validation** — a tool takes deep nested JSON (a query DSL, a config blob). Small models make structural mistakes under pressure; a script that emits or validates the exact payload turns a flaky retry loop into a copy-paste.
- **Transforms over tool output** — the workflow needs aggregation, dedup, or reconciliation no server tool provides. The agent saves responses to a file; the script computes ("which ids are in export A but not B").
- **Encoding chores** — base64 for uploads, CSV→JSON for bulk imports, hashes, timezone/ISO-date math. Classic small-model fumbles, trivially deterministic in a script.
- **Bulk-call prep** — for "do X to 200 items", the agent still makes every call, but a script can generate the validated argument list so each call is mechanical.
- **A sibling API, only with the user's explicit OK** — if the server fronts a REST API or CLI, a script can do in one request what would take 200 tool calls. This bypasses MCP, so it goes in the skill only when the user authorizes it and the skill says plainly that it does.

How you *know* a script is warranted: the simulation transcripts tell you. If Haiku rebuilds the same computation across several trials — or keeps fumbling the same transform — that repeated work is a script waiting to be written. Write it once, put it in the skill's `scripts/`, and reference it from the workflow that needs it (see failure class 7 in `simulation-guide.md`).

## Where the content comes from

Everything you learned building the mock: the schemas (`tools.json`), the quirks you reproduced (id-vs-key inconsistencies, enum values, error strings, pagination), and — most importantly — the simulation failures. Every failed baseline transcript is a section of this skill waiting to be written: if Haiku passed a user name where an id was required, that's a row in the selection map; if it gave up on `ERR_409`, that's a row in the error decoder.

## What stays out

- **Any mention of the mock.** The skill documents the real server; the mock is scaffolding. Before shipping, grep the skill for the mock's filenames and the word "mock".
- Generalities the model already knows ("read errors carefully", "be helpful").
- Information visible in tool descriptions, *unless* agents demonstrably ignore it — repetition is justified only by an observed failure.
- Server internals the agent can't act on.

## Style

Imperative, concrete, short. Prefer a table or numbered sequence over prose. Use real example values from the server's domain, not `foo`/`bar` — small models copy examples literally, so make the examples correct to copy.

Attach the one-line *why* to each rule: "check `assignee_id` first — unassigned tasks cannot be moved to done (the server rejects it with ERR_409)" beats a bare "always check the assignee". A rule with its reason lets the model generalize when reality deviates from the script (a new error variant, a slightly different workflow); a bare imperative only covers the exact case you wrote. Keep the reason to a clause — this is a why, not an essay.
