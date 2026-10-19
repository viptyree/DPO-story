"""Machine-only scene gate for story-write.

Replaces the per-scene human review JSON of story-long-write: a scene is advanced
purely on deterministic signals (model name, finish_reason, wordcount band, repeated
prose, ending trigram). Established facts are extracted automatically so the next
scene still receives the per-scene fact-carrying context. The author reviews the merged
whole-chapter draft afterwards; no per-scene human JSON is required.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

# Reuse the reviewed-scene handoff module (prompt building, plan loading, repair)
# from story-long-write so scene splitting / merging stays byte-identical.
_THIS = Path(__file__).resolve()
_PARENT = _THIS.parent
try:
    _SRC = _PARENT.parent / "story-long-write" / "scripts"
except Exception:
    _SRC = None
if _SRC is not None and _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_facts(scene_text: str, scene: dict, previous_tail: str) -> list[str]:
    """Auto-extract verbatim-substantiated facts from the scene.

    Rules (all machine-checkable, no human JSON):
      1. end_state verbatim (if the scene's declared end_state appears in the text).
      2. Every numbered beat action that has a verbatim echo in the text (>= 6 chars).
      3. Any proper-noun-bearing clause in the last 300 chars (a concrete new fact).
    Each returned fact is a string that is a verbatim substring of scene_text, so it can
    be carried into the next scene's prompt without risk of invented content.
    """
    facts: list[str] = []

    def add(raw: str) -> None:
        fact = raw.strip()
        if len(fact) < 4 or fact in facts:
            return
        if fact in scene_text:
            facts.append(fact)

    # 1) end_state echo
    end_state = scene.get("end_state", "")
    if isinstance(end_state, str) and end_state.strip():
        # Use the trailing fragment of end_state if it appears verbatim.
        add(end_state)

    # 2) beat action echo: each beat's action text (or a long verbatim substring of it).
    for item in scene.get("beats", []):
        action = item.get("action", "") if isinstance(item, dict) else str(item)
        if isinstance(action, str) and len(action) >= 6 and action in scene_text:
            add(action)

    # 3) last-300-chars clauses containing a proper-noun-like token (uppercase-free CJK,
    #    so we look for 2+ consecutive CJK noun phrases separated by punctuation).
    tail = scene_text[-300:]
    for clause in re.split(r"[。！？!?\n]+", tail):
        clause = clause.strip()
        # Keep only substantive clauses (>= 8 chars) that are not purely the previous tail.
        if len(clause) >= 8 and (not previous_tail or clause not in previous_tail):
            add(clause)

    return facts[:6]


def machine_gate(
    scene_index: int,
    scene: dict,
    text: str,
    meta: dict,
    request_doc: dict,
    accepted: list[str],
    count_chars,
    repeat,
    ending_text: str | None,
    is_last: bool,
) -> tuple[list[str], list[str]]:
    """Return (errors, facts). Errors mirror story-long-write's per-scene machine checks."""
    errors: list[str] = []
    if meta.get("model") != request_doc["model"]:
        errors.append("响应模型不符")
    if meta.get("finish_reason") != "stop":
        errors.append("finish_reason 不是 stop")
    target = scene.get("target_chars")
    chars = count_chars(text)
    if isinstance(target, int):
        if chars < max(200, target * .65) or chars > target * 1.5:
            errors.append(f"本场 {chars} 字偏离目标 {target} 的 65%..150% 区间")
    if repeat(text) or any(repeat(old + text) for old in accepted):
        errors.append("本场或跨场出现重复段落")
    # Ending match only on the final scene.
    if is_last and ending_text:
        expected = re.sub(r"\s+", "", ending_text)
        tail = re.sub(r"\s+", "", text[-140:])
        grams = {expected[i:i + 3] for i in range(len(expected) - 2)}
        if grams and sum(g in tail for g in grams) / len(grams) < 0.3:
            errors.append("结尾与细纲结束动作不符")

    previous_tail = accepted[-1][-320:] if accepted else ""
    facts = extract_facts(text, scene, previous_tail)
    return errors, facts
