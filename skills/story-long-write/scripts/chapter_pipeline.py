#!/usr/bin/env python3
"""Prepare and generate a DPO chapter without depending on Claude agent registration."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import build_dpo_prompt
import tracking_commit
from generate_dpo_draft import atomic_write
from preflight_dpo_writer import PIPELINE_VERSION, check_backend


@contextmanager
def project_lock(project: Path):
    """An OS lock is released even if the tested Claude session is killed."""
    folder = project / ".story"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "dpo-pipeline.lock").open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("本书已有 DPO 管线运行，请等当前调用结束；不能同时覆盖草稿") from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError("本书已有 DPO 管线运行，请等当前调用结束") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def init_shape_errors(document: dict) -> list[str]:
    errors = []
    snapshots = document.get("character_snapshots", {})
    if not isinstance(snapshots, dict):
        return ["character_snapshots 必须是以人物名为键的对象"]
    context = document.get("context", {})
    active = context.get("active_character_names", []) if isinstance(context, dict) else []
    for name in active if isinstance(active, list) else []:
        if name not in snapshots:
            errors.append(f"活跃核心人物 {name} 缺少快照，不能靠删除人物绕过")
    required = {"identity", "location", "goal", "state"}
    lists = {"abilities_resources", "relationships", "knowledge", "open_threads"}
    for name, snapshot in snapshots.items():
        if not isinstance(snapshot, dict):
            errors.append(f"{name} 快照必须是对象")
            continue
        unknown = set(snapshot) - required - lists
        if unknown:
            errors.append(f"{name} 不支持字段：{', '.join(sorted(unknown))}；使用英文 schema")
        for key in sorted(required):
            if not isinstance(snapshot.get(key), str) or not snapshot[key].strip():
                errors.append(f"{name}.{key} 必须是非空文字")
    return errors


def init_template(project: Path, chapter: int) -> Path:
    path = project / ".story" / "work" / "tracking_init.template.json"
    if path.exists():
        return path
    outline = build_dpo_prompt.chapter_file(project / "大纲", chapter).read_text(encoding="utf-8-sig")
    control = build_dpo_prompt.section(outline, "章节控制")
    document = {
        "schema_version": 1, "book_title": project.name, "last_chapter": 0,
        "context": {
            "position": {"volume": build_dpo_prompt.field(control, "所属卷"), "volume_start_chapter": 1,
                         "story_time": "", "scene": ""},
            "long_term_constraints": [], "active_character_names": [], "continuity_risks": [],
            "recent_chapters": [], "next_chapter_commitments": [],
        },
        "character_snapshots": {}, "foreshadow": [], "timeline_events": [],
    }
    # The reference supplies the required shape without inventing any book facts.
    document["character_snapshots"]["请替换为核心人物姓名"] = {
        "identity": "", "location": "", "goal": "", "state": "",
        "abilities_resources": [], "relationships": [], "knowledge": [], "open_threads": [],
    }
    atomic_write(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    return path


def run(args: argparse.Namespace) -> tuple[dict, int]:
    project = args.project.resolve()
    report = {"pipeline_version": PIPELINE_VERSION, "script": str(Path(__file__).resolve()),
              "project": str(project), "chapter": args.chapter, "mode": args.mode, "status": "blocked", "errors": []}
    if not project.is_dir() or args.chapter < 1:
        raise ValueError("书目录必须存在，章号必须为正整数")
    model, adapters = check_backend(args.endpoint, args.model, require_xuanhuan_dpo_lora=False)
    report.update(model=model, active_adapters=adapters, agent_required=True,
                  runtime_registration="由 claudeqwen --agents 注册及实际写手调用确认")
    state_path = project / "追踪" / "_tracking-state.json"
    if not state_path.is_file():
        if args.mode == "revision":
            raise ValueError("修订章节需要现有追踪状态，不能初始化成新书")
        bodies = list((project / "正文").glob("第*章*.md"))
        if bodies:
            report["errors"] = ["已有正文但追踪状态丢失，必须恢复状态，不能按新书初始化"]
            return report, 2
        if args.init_input is None:
            report.update(model=model, stage="tracking_init", init_template=str(init_template(project, args.chapter)),
                          errors=["新书未初始化：按 tracking-initialization.md 填写模板，再用 --init-input 提交；不要猜 schema"])
            return report, 2
        document = json.loads(args.init_input.read_text(encoding="utf-8-sig"))
        errors = init_shape_errors(document)
        if errors:
            report.update(stage="tracking_init", errors=errors)
            return report, 2
        tracking_commit.initialize(project, document)
    state = tracking_commit.check_project(project)
    if args.mode == "append" and args.chapter != state["last_committed_chapter"] + 1:
        raise ValueError(f"追加写作应为第 {state['last_committed_chapter'] + 1} 章；已提交章节重写请使用 --mode revision")
    if args.mode == "revision" and not 1 <= args.chapter <= state["last_committed_chapter"]:
        raise ValueError("不能修订尚未提交的章节")
    report.update(last_committed_chapter=state["last_committed_chapter"], state_revision=state["state_revision"])
    node = shutil.which("node")
    if not node:
        raise ValueError("Node.js 不可用，无法校验细纲")
    validator = Path(__file__).with_name("check-outline-contract.js")
    checked = subprocess.run([node, str(validator), "--json", "--project", str(project), "--chapter", str(args.chapter)],
                             capture_output=True, text=True, encoding="utf-8", timeout=30)
    outline_report = json.loads(checked.stdout)
    if checked.returncode != 0:
        report.update(stage="outline", errors=[outline_report])
        return report, 2
    work = project / ".story" / "work" / f"第{args.chapter:03d}章"
    prompt_path = work / "dpo_prompt.json"
    prepared_path = work / "dpo_prepared.json"
    compiled = build_dpo_prompt.run(project, args.chapter)
    excerpts = compiled.get("controller_facts", {}).get("setting_excerpts", [])
    setting_files = sorted((project / "设定").rglob("*.md"))
    needs_context = bool(setting_files) and not excerpts
    context_path = work / "dpo_context.json"
    context_fingerprint = {
        "chapter": args.chapter, "mode": args.mode, "state_revision": state["state_revision"],
        "outline_sha256": hashlib.sha256(Path(compiled["source_outline"]).read_bytes()).hexdigest(),
        "tracking_sha256": hashlib.sha256(Path(compiled["source_tracking"]).read_bytes()).hexdigest(),
        "context_sha256": hashlib.sha256(context_path.read_bytes()).hexdigest() if context_path.is_file() else None,
        "setting_sources": {row["source"]: row["source_sha256"] for row in excerpts},
    }
    if args.generate_prepared:
        if needs_context:
            raise ValueError("本章必读设定摘录尚未准备；主控须先按 oh-story 写前流程选取时代、制度和资源事实")
        prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
        if prepared != context_fingerprint:
            raise ValueError("细纲或追踪在准备后发生变化，必须重新准备并审核 Prompt")
        prompt = json.loads(prompt_path.read_text(encoding="utf-8"))
        if prompt.get("chapter") != args.chapter or prompt.get("system") != build_dpo_prompt.SYS or prompt.get("source_outline") != compiled["source_outline"]:
            raise ValueError("已审核的 DPO Prompt 与本章不匹配")
        if not isinstance(prompt.get("user"), str) or not all(marker in prompt["user"] for marker in build_dpo_prompt.SECTIONS):
            raise ValueError("已审核 Prompt 缺少四段式正文输入")
    else:
        prompt = compiled
        atomic_write(prompt_path, json.dumps(prompt, ensure_ascii=False, indent=2) + "\n")
        atomic_write(prepared_path, json.dumps(context_fingerprint, ensure_ascii=False, indent=2) + "\n")
    report.update(prompt=str(prompt_path), controller_review=prompt["review_items"])
    report["scene_plan_target"] = str(work / "dpo_scene_plan.json")
    if not (work / "dpo_scene_plan.json").is_file():
        from scene_handoff import plan_template
        template_path = work / "dpo_scene_plan.template.json"
        atomic_write(template_path, json.dumps(plan_template(prompt, hashlib.sha256(prompt_path.read_bytes()).hexdigest()), ensure_ascii=False, indent=2) + "\n")
        report["scene_plan_template"] = str(template_path)
    if args.prepare_only or needs_context:
        if needs_context:
            template = work / "dpo_context.template.json"
            atomic_write(template, json.dumps({"schema_version": 1, "setting_excerpts": []}, ensure_ascii=False, indent=2) + "\n")
            report.update(stage="context_prepare", context_template=str(template),
                          context_target=str(context_path),
                          candidate_sources=[str(path.relative_to(project)) for path in setting_files[:20]],
                          errors=["主控须从必要设定中选取原文，写入 dpo_context.json 的 setting_excerpts；每项只填 source 相对路径和 text 原文，避免转交真名、幕后秘密与未来进展。填写后重跑准备命令。"])
            return report, 2
        report.update(status="ready", stage="prepared")
        return report, 0
    if not (work / "dpo_scene_plan.json").is_file():
        report.update(status="blocked", stage="scene_plan_prepare",
                      errors=["主控须先按 scene-handoff.md 编排 dpo_scene_plan.json；不再自动均分或默认运行整章实验"])
        return report, 2
    gen_cmd = [sys.executable, str(Path(__file__).with_name("generate_dpo_draft.py")),
               "--project", str(project), "--chapter", str(args.chapter), "--endpoint", args.endpoint]
    if getattr(args, "scenes", 1) != 1:
        gen_cmd.extend(["--scenes", str(args.scenes)])
    generated = subprocess.run(gen_cmd,
                               capture_output=True, text=True, encoding="utf-8", timeout=900)
    if not generated.stdout.strip():
        raise ValueError("DPO 生成脚本失败：" + generated.stderr.strip()[-1500:])
    generation = json.loads(generated.stdout.strip().splitlines()[-1])
    report.update(status=generation["status"], stage="generated", generation=generation, errors=generation["errors"])
    atomic_write(work / "pipeline_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report, 0 if report["status"] in ("ready", "awaiting_scene_review") else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--mode", choices=("append", "revision"), default="append")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8088")
    parser.add_argument("--model", default="qwen3.8-27b-udq4-xuanhuan-dpo,qwen3.8-27b-udq4-taste",
                        help="允许的模型别名，多个用逗号分隔")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--generate-prepared", action="store_true", help="写手只消费主控已准备和审核的 Prompt")
    parser.add_argument("--init-input", type=Path)
    parser.add_argument("--scenes", type=int, default=1, help="Number of scenes to split the chapter into (default: 1, experimental: 2-6)")
    args = parser.parse_args()
    if args.prepare_only and args.generate_prepared:
        parser.error("--prepare-only and --generate-prepared are mutually exclusive")
    if isinstance(args.model, str):
        args.model = [item.strip() for item in args.model.split(",") if item.strip()]
    try:
        if not args.project.is_dir():
            raise ValueError("书目录必须存在")
        with project_lock(args.project.resolve()):
            report, code = run(args)
    except (OSError, ValueError, tracking_commit.TrackingError, subprocess.TimeoutExpired) as exc:
        report, code = {"pipeline_version": PIPELINE_VERSION, "script": str(Path(__file__).resolve()),
                        "status": "blocked", "errors": [str(exc)]}, 2
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
