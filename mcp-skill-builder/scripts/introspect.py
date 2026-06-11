#!/usr/bin/env python3
"""Dump an MCP server's tool inventory (names, descriptions, input schemas) to JSON,
or diff a live server against a previously saved inventory to verify tool parity.

Run with a Python that has the `mcp` package installed.

Usage:
  introspect.py --stdio "npx -y @acme/tracker-mcp --flag" [--env KEY=VAL ...] [-o tools.json]
  introspect.py --url https://example.com/mcp [-o tools.json]
  introspect.py --diff tools.json --stdio "python mock_server.py"

--diff compares tool names, parameter names, and required parameters against the
saved inventory and exits 1 on any mismatch. Use it to prove mock/real parity.
"""
import argparse
import asyncio
import json
import os
import shlex
import sys


async def introspect_stdio(command_line: str, env_pairs: list[str]):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    parts = shlex.split(command_line)
    env = dict(os.environ)
    for pair in env_pairs:
        key, _, val = pair.partition("=")
        env[key] = val
    params = StdioServerParameters(command=parts[0], args=parts[1:], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [t.model_dump(include={"name", "description", "inputSchema"}, mode="json")
                    for t in result.tools]


async def introspect_url(url: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [t.model_dump(include={"name", "description", "inputSchema"}, mode="json")
                    for t in result.tools]


def schema_surface(schema):
    """The parts of an input schema that matter for parity: param names + required set."""
    if not isinstance(schema, dict):
        return {"properties": [], "required": []}
    return {
        "properties": sorted((schema.get("properties") or {}).keys()),
        "required": sorted(schema.get("required") or []),
    }


def diff_tools(baseline: list[dict], live: list[dict]) -> list[str]:
    problems = []
    base = {t["name"]: t for t in baseline}
    cur = {t["name"]: t for t in live}
    for name in sorted(set(base) - set(cur)):
        problems.append(f"MISSING tool: {name}")
    for name in sorted(set(cur) - set(base)):
        problems.append(f"EXTRA tool: {name}")
    for name in sorted(set(base) & set(cur)):
        b, c = schema_surface(base[name].get("inputSchema")), schema_surface(cur[name].get("inputSchema"))
        if b["properties"] != c["properties"]:
            problems.append(f"{name}: params differ — expected {b['properties']}, got {c['properties']}")
        if b["required"] != c["required"]:
            problems.append(f"{name}: required differ — expected {b['required']}, got {c['required']}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--stdio", help="command line that launches the server over stdio")
    src.add_argument("--url", help="streamable-HTTP endpoint of the server")
    ap.add_argument("--env", action="append", default=[], metavar="KEY=VAL",
                    help="extra env var for the stdio server (repeatable)")
    ap.add_argument("-o", "--out", help="write tools JSON here (default: stdout)")
    ap.add_argument("--diff", metavar="TOOLS_JSON",
                    help="compare the live server against this saved inventory instead of dumping")
    args = ap.parse_args()

    tools = asyncio.run(introspect_stdio(args.stdio, args.env) if args.stdio else introspect_url(args.url))

    if args.diff:
        baseline = json.loads(open(args.diff).read())
        problems = diff_tools(baseline, tools)
        if problems:
            print(f"PARITY FAILED ({len(problems)} problems):")
            for p in problems:
                print(f"  - {p}")
            sys.exit(1)
        print(f"PARITY OK: {len(tools)} tools match {args.diff}")
        return

    payload = json.dumps(tools, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(payload + "\n")
        print(f"Wrote {len(tools)} tools to {args.out}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
