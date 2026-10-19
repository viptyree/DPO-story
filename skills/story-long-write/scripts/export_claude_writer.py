#!/usr/bin/env python3
"""Export the project narrative-writer for Claude Code's explicit --agents registration."""
import argparse
import json
import re
import sys
from pathlib import Path

from preflight_dpo_writer import check_agent, find_agent


def definition(agent: Path) -> dict:
    errors = check_agent(agent)
    if errors:
        raise ValueError("；".join(errors))
    content = agent.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n?(.*)", content, re.S)
    header, prompt = match.groups()
    def field(name, default=""):
        found = re.search(rf"(?m)^{name}:\s*(.+?)\s*$", header)
        return found.group(1).strip().strip("\"'") if found else default
    tools = [item.strip().strip("\"'") for item in field("tools").strip("[]").split(",") if item.strip()]
    if sys.platform == "win32":
        tools = list(dict.fromkeys("PowerShell" if tool == "Bash" else tool for tool in tools))
    return {"narrative-writer": {
        "description": field("description"), "prompt": prompt.strip(),
        "model": "inherit", "tools": tools, "maxTurns": int(field("maxTurns", "8")),
    }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    agent = find_agent(args.cwd.resolve())
    if agent is None:
        return 3  # Ordinary non-story sessions retain their existing launcher behavior.
    try:
        payload = definition(agent)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
