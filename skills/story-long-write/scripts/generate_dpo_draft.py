#!/usr/bin/env python3
"""Generate one chapter through the local DPO server without a tool-call text payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from urllib.request import Request, urlopen

from wordcount_core import count_visible_chars
from preflight_dpo_writer import PIPELINE_VERSION, check_backend


DEFAULT_MODELS = ["qwen3.8-27b-udq4-xuanhuan-dpo", "qwen3.8-27b-udq4-taste"]
DEFAULT_MODEL = ",".join(DEFAULT_MODELS)


def repeated_prose(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    sentences = re.split(r"[。！？!?\n]+", text)
    long_sentences = [re.sub(r"\s+", "", sentence) for sentence in sentences]
    seen_sentences = set()
    for sentence in long_sentences:
        if len(sentence) >= 24:
            if sentence in seen_sentences:
                return True
            seen_sentences.add(sentence)
    if len(compact) < 160:
        return False
    seen: dict[str, int] = {}
    for offset in range(0, len(compact) - 80 + 1):
        sample = compact[offset:offset + 80]
        previous = seen.get(sample)
        if previous is not None and offset - previous >= 80:
            return True
        seen.setdefault(sample, offset)
    return False


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, prefix="dpo_", suffix=".tmp", delete=False) as output:
        temp_name = output.name
        output.write(content)
    os.replace(temp_name, path)


def ending_matches(ending: str, scene: str) -> bool:
    """Check that the final image reflects the outline without book-specific nouns."""
    expected = re.sub(r"\s+", "", ending)
    tail = re.sub(r"\s+", "", scene[-140:])
    grams = {expected[index:index + 3] for index in range(len(expected) - 2)}
    return bool(grams) and sum(gram in tail for gram in grams) / len(grams) >= 0.3


def scene_prompts(user_prompt: str, scene_count: int) -> list[str]:
    marker_events = "〖事件骨架〗"
    marker_requirements = "〖写作要求〗"
    if marker_events not in user_prompt or marker_requirements not in user_prompt:
        raise ValueError("DPO prompt is missing event or writing sections")
    prefix, remainder = user_prompt.split(marker_events, 1)
    event_text, requirements = remainder.split(marker_requirements, 1)
    beats = [line.strip() for line in event_text.splitlines() if re.match(r"^\s*\d+[.、．]", line)]
    if not beats:
        raise ValueError("DPO prompt contains no numbered event beats")
    if scene_count != 1:
        raise ValueError("自动均分已停用，请准备经主控审核的场景计划")
    return [user_prompt]


def request_scene(endpoint: str, model: str, system: str, user: str, max_tokens: int, adapters: list[dict] | None = None, sampling: dict | None = None) -> tuple[str, str | None, str | None]:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": 0.85,
        "top_p": 0.90,
        "top_k": 40,
        "min_p": 0.0,
        "repeat_penalty": 1.05,
        "chat_template_kwargs": {"enable_thinking": False},
        "stream": False,
    }
    if adapters is not None:
        payload["lora"] = [{"id": item["id"], "scale": item["scale"]} for item in adapters]
    if sampling:
        if set(sampling) - {"temperature", "repeat_penalty"}:
            raise ValueError("分场采样配置含不支持字段")
        payload.update(sampling)
    request = Request(endpoint.rstrip("/") + "/v1/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=1800) as response:
        result = json.load(response)
    choice = result["choices"][0]
    return choice["message"].get("content") or "", choice.get("finish_reason"), result.get("model")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8088")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="允许的模型别名，多个用逗号分隔")
    parser.add_argument("--max-tokens", type=int, default=6500)
    parser.add_argument("--scenes", type=int, default=1, help="default: one continuous chapter; splitting is experimental")
    args = parser.parse_args()
    args.allowed_models = [item.strip() for item in args.model.split(",") if item.strip()]
    if args.chapter < 1 or args.max_tokens < 100 or args.scenes < 1 or args.scenes > 6:
        parser.error("chapter and max-tokens must be positive; scenes must be 1..6")
    work = args.project.resolve() / ".story" / "work" / f"第{args.chapter:03d}章"
    prompt_path = work / "dpo_prompt.json"
    prompt_bytes = prompt_path.read_bytes()
    prompt_hash = hashlib.sha256(prompt_bytes).hexdigest()
    prompt = json.loads(prompt_bytes.decode("utf-8-sig"))
    if not isinstance(prompt.get("system"), str) or not isinstance(prompt.get("user"), str):
        parser.error("dpo_prompt.json must contain system and user strings")
    actual_model, adapters = check_backend(args.endpoint, args.allowed_models, require_xuanhuan_dpo_lora=False)
    request_model = actual_model
    planned = (work / "dpo_scene_plan.json").is_file()
    if args.scenes != 1 and not planned:
        parser.error("自动均分已停用：主控须先准备 dpo_scene_plan.json，再逐场生成和审阅")
    prompts = scene_prompts(prompt["user"], 1)
    atomic_write(work / "dpo_report.json", json.dumps({
        "status": "running", "model": actual_model,
        "prompt_sha256": prompt_hash,
        "draft_sha256": None,
    }, ensure_ascii=False, indent=2) + "\n")
    scenes = []
    reasons = []
    response_model = None
    finish = None
    rejected_scene = ""
    scene_plan_hash = None
    if planned:
        from scene_handoff import advance, load_plan
        try:
            plan = load_plan(work / "dpo_scene_plan.json", prompt, prompt_hash)
            if "lora_scale" in plan:
                adapters = [dict(item, scale=plan["lora_scale"]) for item in adapters]
            scenes, pending, scene_plan_hash = advance(
                work, prompt, prompt_hash, request_model, adapters, request_scene, atomic_write,
                repeated_prose, count_visible_chars, args.endpoint, min(args.max_tokens, 2600))
        except (ValueError, OSError) as exc:
            pending = {"status": "blocked", "generation_mode": "reviewed_scenes_v1", "errors": [str(exc)],
                       "work_dir": str(work), "model": args.model, "prompt_sha256": prompt_hash, "draft_sha256": None}
        if pending:
            pending["pipeline_version"] = PIPELINE_VERSION
            atomic_write(work / "dpo_report.json", json.dumps(pending, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(pending, ensure_ascii=False))
            return 0 if pending["status"] == "awaiting_scene_review" else 2
        response_model, finish = request_model, "stop"
    for index, scene_prompt in enumerate([] if planned else prompts, 1):
        scene_reasons = []
        scene, finish, response_model = request_scene(args.endpoint, request_model, prompt["system"], scene_prompt, args.max_tokens, adapters)
        scene = scene.strip()
        if response_model not in args.allowed_models:
            scene_reasons.append(f"response model was {response_model!r}")
        if finish != "stop":
            scene_reasons.append(f"finish_reason was {finish!r}")
        if len(scene) < 400:
            scene_reasons.append("scene is shorter than 400 characters")
        if repeated_prose(scene):
            scene_reasons.append("scene repeats an 80-character passage")
        if any(SequenceMatcher(None, previous, scene, autojunk=False).find_longest_match().size >= 80 for previous in scenes):
            scene_reasons.append("scene repeats at least 80 characters from an earlier scene")
        ending = re.search(r"(?m)^结束动作[：:]\s*(.+)$", prompt["user"])
        if index == len(prompts) and ending and not ending_matches(ending.group(1), scene):
            scene_reasons.append("final 140 characters do not match the outline ending")
        atomic_write(work / f"dpo_scene_{index:02d}_attempt1.md", scene + "\n")
        if scene_reasons:
            reasons.extend(f"scene {index}: {reason}" for reason in scene_reasons)
            rejected_scene = scene
            break
        atomic_write(work / f"dpo_scene_{index:02d}.md", scene + "\n")
        scenes.append(scene)
    prose = "\n\n".join(scenes + ([rejected_scene] if rejected_scene else []))
    actual_chars = count_visible_chars(prose)
    target_match = re.search(r"全章目标[：:]\s*(\d+)\s*字", prompt["user"])
    if target_match:
        target_chars = int(target_match.group(1))
        if actual_chars < target_chars * 0.85 or actual_chars > target_chars * 1.15:
            reasons.append(f"draft has {actual_chars} visible characters; target is {target_chars} ±15%")
    if repeated_prose(prose):
        reasons.append("draft contains repeated 80-character prose windows")
    if hashlib.sha256(prompt_path.read_bytes()).hexdigest() != prompt_hash:
        reasons.append("prompt changed during generation; draft cannot be accepted")
    target = work / ("dpo_draft_failed.md" if reasons else "dpo_draft.md")
    atomic_write(target, prose.strip() + "\n")
    quality = None
    punctuation_normalized = False
    if not reasons:
        atomic_write(work / "dpo_raw.md", prose.strip() + "\n")
        node = shutil.which("node")
        if node:
            before = target.read_bytes()
            normalized = subprocess.run([node, str(Path(__file__).with_name("normalize-punctuation.js")), str(target)],
                                        capture_output=True, text=True, encoding="utf-8", timeout=30)
            if normalized.returncode != 0:
                reasons.append("deterministic punctuation normalization failed")
            punctuation_normalized = before != target.read_bytes()
            actual_chars = count_visible_chars(target.read_text(encoding="utf-8"))
            if target_match and not target_chars * 0.85 <= actual_chars <= target_chars * 1.15:
                reasons.append(f"normalized draft has {actual_chars} visible characters; outside target band")
        from storyctl import check_blocking_quality
        quality = check_blocking_quality(Path(prompt["source_outline"]), target)
        if quality["status"] != "pass":
            reasons.append("deterministic prose quality checks did not pass")
        if reasons:
            failed = work / "dpo_draft_failed.md"
            os.replace(target, failed)
            target = failed
    report = {"status": "blocked" if reasons else "ready", "pipeline_version": PIPELINE_VERSION, "model": response_model, "active_adapters": adapters, "finish_reason": finish, "characters": actual_chars, "scenes": len(scenes) + bool(rejected_scene), "accepted_scenes": len(scenes), "output": str(target), "errors": reasons,
              "quality": quality, "punctuation_normalized": punctuation_normalized, "prompt_sha256": prompt_hash,
              "draft_sha256": hashlib.sha256(target.read_bytes()).hexdigest() if not reasons else None}
    if scene_plan_hash:
        report.update(generation_mode="reviewed_scenes_v1", scene_plan_sha256=scene_plan_hash)
    atomic_write(work / "dpo_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 2 if reasons else 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
