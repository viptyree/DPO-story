#!/usr/bin/env python3
"""story-write: machine-only chapter generation.

Runs the same per-scene generation as story-long-write but advances on deterministic
machine signals only (no per-scene human review JSON). It auto-repairs up to 2 rounds
per scene, auto-merges, runs deterministic punctuation + blocking quality checks, and
stops with a machine report for the author to review the merged draft. No tracking commit.

Reuses story-long-write's modules (scene_handoff, scene_repair, preflight, wordcount)
via a path import so scene splitting/merging stays byte-identical.
"""
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
from pathlib import Path

_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parent
_SKILL_ROOT = _SCRIPTS.parent
_SKILLS_DIR = _SKILL_ROOT.parent
_SRC = _SKILLS_DIR / "story-long-write" / "scripts"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from wordcount_core import count_visible_chars
from preflight_dpo_writer import PIPELINE_VERSION, check_backend
from scene_handoff import load_plan, make_prompt
from scene_repair import requested_repair
from scene_gate import machine_gate
DEFAULT_MODELS = ["qwen3.8-27b-udq4-xuanhuan-dpo", "qwen3.8-27b-udq4-taste"]
DEFAULT_MODEL = ",".join(DEFAULT_MODELS)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                     prefix="sw_", suffix=".tmp", delete=False) as out:
        out.write(content)
        tmp = out.name
    os.replace(tmp, path)


def _request(endpoint, model, system, user, max_tokens, adapters, sampling):
    from generate_dpo_draft import request_scene
    return request_scene(endpoint, model, system, user, max_tokens, adapters, sampling)


def _repeated_prose(text: str) -> bool:
    from generate_dpo_draft import repeated_prose
    return repeated_prose(text)


def _auto_repair(stem, text, meta, request_doc, request_hash, request, write, endpoint):
    """Machine-driven repair: detect a duplicated 80-char window, write a repair JSON
    targeting its second occurrence, run scene_repair.requested_repair once."""
    review_path = stem.with_suffix(".review.json")
    compact = re.sub(r"\s+", "", text)
    seen: dict[str, int] = {}
    dup_window = None
    for off in range(0, len(compact) - 80 + 1):
        sample = compact[off:off + 80]
        prev = seen.get(sample)
        if prev is not None and off - prev >= 80:
            dup_window = sample
            break
        seen.setdefault(sample, off)
    if dup_window is None:
        return None
    # Find the second occurrence of the window in the original (space-bearing) text.
    second = None
    search_from = 0
    probe = dup_window[:20]
    while True:
        pos = text.find(probe, search_from)
        if pos == -1:
            break
        window_text = text[pos:pos + len(dup_window) + 40]
        if re.sub(r"\s+", "", window_text)[:80] == dup_window:
            second = pos
            search_from = pos + 1
        else:
            search_from = pos + 1
    if second is None:
        return None
    before = text[second:second + len(dup_window)]
    review = {"schema_version": 1, "status": "repair", "request_sha256": request_hash,
              "draft_sha256": meta["draft_sha256"], "repairs": [
                  {"before": before,
                   "instruction": "此处与上文重复，用新的具体动作或观察改写，保留剧情推进，不复述。"}]}
    write(review_path, json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    result = requested_repair(stem, text, meta, request_doc, request_hash, request, write, endpoint)
    review_path.unlink(missing_ok=True)
    return result


def run(project: Path, chapter: int, endpoint: str, allowed: list[str],
        max_tokens: int) -> dict:
    work = project.resolve() / ".story" / "work" / f"第{chapter:03d}章"
    prompt_path = work / "dpo_prompt.json"
    prompt_bytes = prompt_path.read_bytes()
    prompt_hash = _digest(prompt_bytes)
    prompt = json.loads(prompt_bytes.decode("utf-8-sig"))
    if not isinstance(prompt.get("system"), str) or not isinstance(prompt.get("user"), str):
        raise ValueError("dpo_prompt.json 缺 system/user")
    actual_model, adapters = check_backend(endpoint, allowed, require_xuanhuan_dpo_lora=False)
    request_model = actual_model

    plan_path = work / "dpo_scene_plan.json"
    if not plan_path.is_file():
        raise ValueError("story-write 需要场景计划 dpo_scene_plan.json（2..6 场）")
    plan = load_plan(plan_path, prompt, prompt_hash)
    if "lora_scale" in plan:
        adapters = [dict(item, scale=plan["lora_scale"]) for item in adapters]
    plan_hash = _digest(plan_path.read_bytes())
    folder = work / "scene_gate" / plan_hash
    folder.mkdir(parents=True, exist_ok=True)
    _atomic_write(folder / "plan.json", plan_path.read_text(encoding="utf-8-sig"))

    ending_m = re.search(r"(?m)^结束动作[：:]\s*(.+)$", prompt["user"])
    ending_text = ending_m.group(1).strip() if ending_m else None
    target_m = re.search(r"全章目标[：:]\s*(\d+)", prompt["user"])
    target_chars = int(target_m.group(1)) if target_m else sum(s["target_chars"] for s in plan["scenes"])

    accepted: list[str] = []
    facts: list[str] = []
    previous_request = ""
    scene_reports: list[dict] = []

    for index, scene in enumerate(plan["scenes"], 1):
        # Rebalance remaining targets exactly like story-long-write's advance().
        if accepted:
            remaining_chars = target_chars - sum(count_visible_chars(t) for t in accepted)
            remaining_weight = sum(s["target_chars"] for s in plan["scenes"][index - 1:])
            scene = dict(scene, target_chars=max(250, min(1600,
                        round(remaining_chars * scene["target_chars"] / remaining_weight))))
        is_last = index == len(plan["scenes"])
        user = make_prompt(prompt, scene, facts, accepted[-1][-320:] if accepted else "")
        request_doc = {"system": prompt["system"], "user": user, "model": request_model,
                       "adapters": adapters, "prompt_sha256": prompt_hash,
                       "plan_sha256": plan_hash, "previous_review_sha256": previous_request,
                       "sampling": plan.get("sampling", {}), "max_tokens": max_tokens}
        request_bytes = (json.dumps(request_doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        request_hash = _digest(request_bytes)
        stem = folder / f"scene_{index:02d}"
        request_path, draft_path = stem.with_suffix(".request.json"), stem.with_suffix(".md")
        meta_path = stem.with_suffix(".result.json")

        if draft_path.exists():
            if not request_path.is_file() or request_path.read_bytes() != request_bytes:
                raise ValueError("本场输入已变化，不能复用旧稿")
            text = draft_path.read_text(encoding="utf-8").strip()
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("draft_sha256") != _digest(draft_path.read_bytes()):
                raise ValueError("场景原文被更改")
        else:
            _atomic_write(request_path, request_bytes.decode("utf-8"))
            text, finish, response_model = _request(endpoint, request_model, prompt["system"],
                                                    user, max_tokens, adapters,
                                                    plan.get("sampling", {}))
            text = text.strip()
            _atomic_write(draft_path, text + "\n")
            meta = {"finish_reason": finish, "model": response_model, "errors": [],
                    "draft_sha256": _digest(draft_path.read_bytes())}
            _atomic_write(meta_path, json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

        # Machine gate + auto-repair (max 2 rounds on mechanical errors).
        repair_doc = request_doc
        repair_rounds = 0
        while True:
            errors, facts_new = machine_gate(index, scene, text, meta, request_doc,
                                             accepted, count_visible_chars,
                                             _repeated_prose, ending_text, is_last)
            mechanical = any(k in e for e in errors for k in ("偏离", "重复"))
            if (mechanical and repair_rounds < 2
                    and meta.get("finish_reason") == "stop"
                    and meta.get("model") == request_doc["model"]):
                result = _auto_repair(stem, text, meta, request_doc, request_hash,
                                      _request, _atomic_write, endpoint)
                if result is None:
                    break
                stem, text, meta, request_hash = result
                repair_rounds += 1
                repair_doc = dict(repair_doc, previous_repair_sha256=request_hash)
                _atomic_write(draft_path, text + "\n")
                continue
            break

        facts.extend(facts_new)
        accepted.append(text)
        previous_request = _digest(draft_path.read_bytes())
        scene_reports.append({"scene": index, "chars": count_visible_chars(text),
                              "repair_rounds": repair_rounds, "errors": errors,
                              "facts": facts_new})
        if errors and not any(k in e for e in errors for k in ("偏离", "重复", "结尾")):
            # Hard errors (model/finish mismatch) that repair cannot fix → stop.
            return {"status": "blocked", "work": str(work), "errors": errors,
                    "scene_reports": scene_reports}

    prose = "\n\n".join(accepted)
    _atomic_write(work / "dpo_raw.md", prose.strip() + "\n")
    target_file = work / "dpo_draft.md"
    _atomic_write(target_file, prose.strip() + "\n")

    reasons = []
    punctuation_normalized = False
    node = shutil.which("node")
    if node:
        before = target_file.read_bytes()
        normalized = subprocess.run([node, str(_SRC / "normalize-punctuation.js"), str(target_file)],
                                    capture_output=True, text=True, encoding="utf-8", timeout=30)
        if normalized.returncode != 0:
            reasons.append("标点归一化失败")
        punctuation_normalized = before != target_file.read_bytes()

    from storyctl import check_blocking_quality
    quality = check_blocking_quality(Path(prompt["source_outline"]), target_file)
    if quality["status"] != "pass":
        reasons.append("确定性正文质量检查未通过")

    actual_chars = count_visible_chars(target_file.read_text(encoding="utf-8"))
    if not target_chars * 0.85 <= actual_chars <= target_chars * 1.15:
        reasons.append(f"全章 {actual_chars} 字，目标 {target_chars} ±15%")

    report = {
        "status": "ready" if not reasons else "blocked",
        "pipeline_version": "2.1.0-dpo",
        "generation_mode": "machine_only_v1",
        "model": request_model,
        "active_adapters": adapters,
        "finish_reason": "stop",
        "characters": actual_chars,
        "scenes": len(accepted),
        "output": str(target_file),
        "errors": reasons,
        "quality": quality,
        "punctuation_normalized": punctuation_normalized,
        "prompt_sha256": prompt_hash,
        "draft_sha256": _digest(target_file.read_bytes()),
        "scene_reports": scene_reports,
        "target_chars": target_chars,
    }
    _atomic_write(work / "dpo_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8088")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=6500)
    args = parser.parse_args()
    allowed = [m.strip() for m in args.model.split(",") if m.strip()]
    if args.chapter < 1 or args.max_tokens < 100:
        parser.error("chapter and max-tokens must be positive")
    try:
        report = run(args.project, args.chapter, args.endpoint, allowed,
                     min(args.max_tokens, 2600))
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "blocked", "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 2 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
