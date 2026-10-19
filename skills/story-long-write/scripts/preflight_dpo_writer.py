#!/usr/bin/env python3
"""Read-only preflight for the Claude Code DPO chapter writer."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PIPELINE_VERSION = "2.1.0-dpo"


def check_backend(endpoint: str, expected_model: str | list[str], require_xuanhuan_dpo_lora: bool = True) -> tuple[str, list[dict]]:
    base = endpoint.removesuffix("/props").rstrip("/")
    allowed = [expected_model] if isinstance(expected_model, str) else list(expected_model)
    with urlopen(base + "/props", timeout=60) as response:
        model = str(json.load(response).get("model_alias", ""))
    if model not in allowed:
        raise ValueError(f"本地服务当前模型是 {model or '未知'}，预期为 {' 或 '.join(allowed)}")
    with urlopen(base + "/lora-adapters", timeout=60) as response:
        adapters = json.load(response)
    if not isinstance(adapters, list):
        raise ValueError("本地服务未返回可核对的 LoRA 列表")
    active = [item for item in adapters if float(item.get("scale", 0)) != 0]
    if require_xuanhuan_dpo_lora:
        if len(active) != 1 or "xuanhuan-novel-writer-dpo" not in str(active[0].get("path", "")).lower():
            raise ValueError("必须且只能启用 Xuanhuan-Novel-Writer-DPO LoRA；当前挂载与要求不符")
    return model, active

def find_agent(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / ".claude" / "agents" / "narrative-writer.md"
        if candidate.is_file():
            return candidate
    return None


def check_agent(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    errors = []
    if not content.startswith("---\n"):
        errors.append("写手文件首行必须是 ---（无 BOM）")
        return errors
    match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", content, re.S)
    if not match:
        return ["写手文件的 YAML frontmatter 未闭合"]
    header = match.group(1)
    for field, expected in (("name", "narrative-writer"), ("model", "inherit")):
        field_match = re.search(rf"(?m)^{field}:\s*(.+?)\s*$", header)
        if not field_match or field_match.group(1).strip("'\"") != expected:
            errors.append(f"写手文件 {field} 应为 {expected}")
    if not re.search(r"(?m)^description:\s*\S", header):
        errors.append("写手文件缺少 description")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path, help="书目录")
    parser.add_argument("--session-cwd", type=Path, default=Path.cwd(), help="启动 Claude Code 时的工作目录")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8088/props")
    parser.add_argument("--expected-model", default="qwen3.8-27b-udq4-xuanhuan-dpo")
    parser.add_argument("--require-agent", action="store_true", help="仅兼容入口需要检查自定义 agent；直接 DPO 管线无需此项")
    args = parser.parse_args()

    project = args.project.resolve()
    cwd = args.session_cwd.resolve()
    errors: list[str] = []
    if not project.is_dir():
        errors.append(f"书目录不存在：{project}")
    agent = find_agent(cwd)
    if agent is None and args.require_agent:
        errors.append(f"从会话启动目录 {cwd} 向上找不到 .claude/agents/narrative-writer.md；请在小说项目根目录启动新的 claudeqwen 会话")
    elif agent is not None and args.require_agent:
        errors.extend(check_agent(agent))
        if not project.is_relative_to(agent.parent.parent.parent):
            errors.append(f"写手所在项目 {agent.parent.parent.parent} 不包含书目录 {project}")
    try:
        model, adapters = check_backend(args.endpoint, args.expected_model)
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        model = None
        adapters = []
        errors.append(f"无法读取本地模型服务：{exc}")

    result = {
        "status": "ready" if not errors else "blocked",
        "pipeline_version": PIPELINE_VERSION,
        "script": str(Path(__file__).resolve()),
        "session_cwd": str(cwd),
        "project": str(project),
        "agent_file": str(agent) if agent else None,
        "model_alias": model,
        "runtime_agent_registered": "仅 --require-agent 兼容模式需要会话注册；直接 DPO 管线不依赖 agent",
        "active_adapters": adapters,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
