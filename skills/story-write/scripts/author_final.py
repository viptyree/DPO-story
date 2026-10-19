#!/usr/bin/env python3
"""story-write: author final-review stage (first-class pipeline step).

The author edits the merged draft directly in 正文/第NNN章_章名.md. This command:
  1. Freezes the model's original draft (dpo_draft.md) and the author's final body.
  2. Exports a unified diff (model original vs author final) to
     .story/dpo-evidence/第NNN章/author_diff.md  — the per-chapter trail for later
     statistics on what the author tends to change (feeds outline / DPO preference).
  3. Writes author_final.json baseline {model_original_sha256, author_final_sha256,
     diff_sha256, changed_chars} into the work dir so storyctl's provenance gate can
     accept the author-edited body as byte-identical to the registered baseline.
  4. Re-runs deterministic punctuation + blocking quality checks on the final body.

This is a pipeline stage, not a post-hoc patch: the author's final draft becomes the
provenance baseline for commit, while the frozen dpo_draft.md is archived as evidence.
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
from difflib import unified_diff
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


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                     prefix="af_", suffix=".tmp", delete=False) as out:
        out.write(content)
        tmp = out.name
    os.replace(tmp, path)


def _chapter_body_path(project: Path, chapter: int) -> Path:
    from wordcount_core import find_chapter_file
    return find_chapter_file(project.resolve() / "正文", chapter, outline=False)


def _export_stats(original: str, final: str) -> dict:
    """Lightweight stats on what changed, for later DPO-preference aggregation."""
    orig_lines = original.splitlines()
    final_lines = final.splitlines()
    removed = [l for l in orig_lines if l not in final_lines]
    added = [l for l in final_lines if l not in orig_lines]
    # Rough change categories by punctuation / length heuristic.
    def _category(line: str) -> str:
        if re.search(r"——|--|……|\.\.\.", line):
            return "punctuation_fix"
        if len(line) < 12:
            return "short_trim"
        return "rewrite"
    removed_cats, added_cats = {}, {}
    for l in removed:
        removed_cats[_category(l)] = removed_cats.get(_category(l), 0) + 1
    for l in added:
        added_cats[_category(l)] = added_cats.get(_category(l), 0) + 1
    return {
        "removed_lines": len(removed),
        "added_lines": len(added),
        "removed_categories": removed_cats,
        "added_categories": added_cats,
        "original_chars": count_visible_chars(original),
        "final_chars": count_visible_chars(final),
    }


def run(project: Path, chapter: int, endpoint: str | None = None) -> dict:
    work = project.resolve() / ".story" / "work" / f"第{chapter:03d}章"
    prompt_path = work / "dpo_prompt.json"
    report_path = work / "dpo_report.json"
    if not prompt_path.is_file() or not report_path.is_file():
        return {"status": "blocked", "errors": ["缺 dpo_prompt.json 或 dpo_report.json（先跑 story-write 生成）"]}
    prompt = json.loads(prompt_path.read_text(encoding="utf-8-sig"))
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    if report.get("status") != "ready":
        return {"status": "blocked", "errors": [f"生成报告不是 ready：{report.get('status')}"]}

    draft_path = work / "dpo_draft.md"
    if not draft_path.is_file():
        return {"status": "blocked", "errors": ["缺 dpo_draft.md（模型原稿）"]}
    body_path = _chapter_body_path(project, chapter)
    if not body_path.is_file():
        return {"status": "blocked", "errors": [f"缺正式正文 {body_path.name}（作者应在 正文/ 下编辑）"]}

    original_bytes = draft_path.read_bytes()
    final_bytes = body_path.read_bytes()
    original = original_bytes.decode("utf-8")
    final = final_bytes.decode("utf-8")
    original_sha = _digest(original_bytes)
    final_sha = _digest(final_bytes)

    # The author must have actually changed something vs the model draft.
    if original_sha == final_sha:
        return {"status": "unchanged", "errors": ["正文与模型原稿逐字一致；作者终审应有改动，或确认真实无需改动"]}

    # Export unified diff to the evidence folder (first-class trail).
    evidence_dir = project.resolve() / ".story" / "dpo-evidence" / f"第{chapter:03d}章"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    diff_lines = list(unified_diff(original.splitlines(keepends=True), final.splitlines(keepends=True),
                                   fromfile="dpo_draft.md（模型原稿）", tofile=str(body_path.name) + "（作者终稿）", n=3))
    diff_text = "".join(diff_lines)
    diff_path = evidence_dir / "author_diff.md"
    _atomic_write(diff_path, diff_text if diff_text else "（无差异）\n")
    stats = _export_stats(original, final)
    stats_path = evidence_dir / "author_stats.json"
    _atomic_write(stats_path, json.dumps(stats, ensure_ascii=False, indent=2) + "\n")

    # Register the author-final baseline in the work dir.
    baseline = {
        "schema_version": 1,
        "chapter": chapter,
        "model_original_sha256": original_sha,
        "author_final_sha256": final_sha,
        "diff_sha256": _digest(diff_text.encode("utf-8")),
        "diff_path": diff_path.as_posix(),
        "stats_path": stats_path.as_posix(),
        "stats": stats,
    }
    baseline_path = work / "author_final.json"
    _atomic_write(baseline_path, json.dumps(baseline, ensure_ascii=False, indent=2) + "\n")

    # Re-run deterministic checks on the author's final body.
    reasons = []
    node = shutil.which("node")
    if node:
        normalized = subprocess.run([node, str(_SRC / "normalize-punctuation.js"), str(body_path)],
                                    capture_output=True, text=True, encoding="utf-8", timeout=30)
        if normalized.returncode != 0:
            reasons.append("标点归一化失败")
        if body_path.read_bytes() != final_bytes:
            final_bytes = body_path.read_bytes()
            final = final_bytes.decode("utf-8")
            baseline["author_final_sha256"] = _digest(final_bytes)
            _atomic_write(baseline_path, json.dumps(baseline, ensure_ascii=False, indent=2) + "\n")
    from storyctl import check_blocking_quality
    quality = check_blocking_quality(Path(prompt["source_outline"]), body_path)
    if quality["status"] != "pass":
        reasons.append("确定性正文质量检查未通过")

    target_m = re.search(r"全章目标[：:]\s*(\d+)", prompt["user"])
    final_chars = count_visible_chars(final)
    if target_m:
        target = int(target_m.group(1))
        if not target * 0.85 <= final_chars <= target * 1.15:
            reasons.append(f"终稿 {final_chars} 字，目标 {target} ±15%（作者可接受当前长度时后续 --force）")

    result = {
        "status": "ready" if not reasons else "needs_decision",
        "chapter": chapter,
        "model_original_sha256": original_sha,
        "author_final_sha256": baseline["author_final_sha256"],
        "diff_path": str(diff_path),
        "stats_path": str(stats_path),
        "baseline_path": str(baseline_path),
        "body_path": str(body_path),
        "final_chars": final_chars,
        "quality": quality,
        "errors": reasons,
    }
    _atomic_write(work / "author_final_report.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--chapter", required=True, type=int)
    args = parser.parse_args()
    try:
        result = run(args.project, args.chapter)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "blocked", "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in ("ready", "unchanged") else 2


if __name__ == "__main__":
    raise SystemExit(main())
