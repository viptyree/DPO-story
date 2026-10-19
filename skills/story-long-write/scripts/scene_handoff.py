"""Reviewed scene handoff: never infer completion from assigned outline beats."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

CHECKS = ("canon", "continuity", "ending")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan_template(prompt: dict, prompt_hash: str) -> dict:
    events = prompt["user"].split("〖事件骨架〗", 1)[1].split("〖写作要求〗", 1)[0]
    beats = re.findall(r"(?m)^\s*(\d+)[.、．]\s*(.+)$", events)
    target = re.search(r"全章目标[：:]\s*(\d+)", prompt["user"])
    total = int(target.group(1)) if target else 2500
    # Empty state fields deliberately prevent treating a generated template as reviewed.
    return {"schema_version": 1, "prompt_sha256": prompt_hash, "scenes": [
        {"start_state": "", "end_state": "", "target_chars": total // len(beats) + (index < total % len(beats)),
         "character_states": [], "context_quotes": [], "requirements": [],
         "beats": [{"id": int(number), "action": action}]}
        for index, (number, action) in enumerate(beats)]}


def load_plan(path: Path, prompt: dict, prompt_hash: str) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(plan, dict) or plan.get("schema_version") != 1 or plan.get("prompt_sha256") != prompt_hash:
        raise ValueError("场景计划版本或 Prompt 指纹不符，须由主控重新审核计划")
    sampling = plan.get("sampling", {})
    if isinstance(sampling, dict) and "speculative_n_max" in sampling:
        raise ValueError("当前b10643后端不支持单请求设置推测解码；从计划移除 speculative_n_max，不能把请求值当作已生效")
    if (not isinstance(sampling, dict) or set(sampling) - {"temperature", "repeat_penalty"}
            or any(type(value) not in (float, int) for value in sampling.values())
            or not 0 <= sampling.get("temperature", .85) <= 2
            or not 1 <= sampling.get("repeat_penalty", 1.05) <= 1.3):
        raise ValueError("场景采样参数无效")
    if type(plan.get("lora_scale", 1)) not in (int, float) or not .1 <= plan.get("lora_scale", 1) <= 1:
        raise ValueError("本地DPO适配器强度须在0.1..1之间，不能关闭适配器")
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not 2 <= len(scenes) <= 6:
        raise ValueError("场景计划须含2..6场")
    beats = re.findall(r"(?m)^\s*(\d+)[.、．]", prompt["user"].split("〖事件骨架〗", 1)[1].split("〖写作要求〗", 1)[0])
    covered = []
    task_ids = []
    total = 0
    for scene in scenes:
        if not isinstance(scene, dict):
            raise ValueError("每个场景须为对象")
        for key in ("character_states", "context_quotes", "requirements"):
            rows = scene.get(key)
            if rows is not None and (not isinstance(rows, list) or not rows or any(not isinstance(row, str) or not row.strip() for row in rows)):
                raise ValueError("本场 " + key + " 须为非空文字列表")
        for quote in scene.get("context_quotes", []):
            if quote not in prompt["user"]:
                raise ValueError("本场上下文摘句须来自审核后的 Prompt")
        for key in ("start_state", "end_state"):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError("每场须明确 start_state 和 end_state")
        items = scene.get("beats")
        if not isinstance(items, list) or not items:
            raise ValueError("每场须列出 beats（id、action）")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("action"), str) or not item["action"].strip():
                raise ValueError("每个情节点须含 id 和明确 action")
            task_ids.append(str(item.get("id")))
            covered.append(str(item.get("source_id", item.get("id"))))
        target = scene.get("target_chars")
        if type(target) is not int or not 250 <= target <= 1600:
            raise ValueError("每场 target_chars 须为250..1600")
        total += target
    distinct_sources = [value for index, value in enumerate(covered) if index == 0 or covered[index - 1] != value]
    if distinct_sources != beats or len(set(task_ids)) != len(task_ids):
        raise ValueError("场景计划必须按序覆盖全部细纲情节点，不能遗漏或重复")
    target = re.search(r"全章目标[：:]\s*(\d+)", prompt["user"])
    if target and total != int(target.group(1)):
        raise ValueError("分场目标合计必须等于全章目标")
    return plan


def make_prompt(prompt: dict, scene: dict, facts: list[str], previous_tail: str) -> str:
    source = prompt["user"]
    characters, rest = source.split("〖前情〗", 1)
    history = rest.split("〖事件骨架〗", 1)[0].strip()
    if scene.get("character_states"):
        characters = "〖人物状态〗\n" + "\n".join("- " + row for row in scene["character_states"])
    if scene.get("context_quotes"):
        history = "\n".join(scene["context_quotes"])
    requirements = source.split("〖写作要求〗", 1)[1]
    # Keep canon and voice; remove whole-chapter commands from every local request.
    keep = []
    for line in requirements.splitlines():
        if any(term in line for term in ("全章目标", "篇幅安排", "结束动作", "结尾：", "章尾", "允许发生的状态变化")):
            continue
        keep.append(line)
    if scene.get("requirements"):
        keep = ["- " + row for row in scene["requirements"]]
        # Local style choices must not erase the chapter's factual boundaries.
        for line in requirements.splitlines():
            if line.startswith(("- 禁止提前释放：", "- 必须沿用的事实：", "- 本章禁止变动的设定：",
                                "- 连贯性约束：", "- 标点约束：", "- 时代、制度、收入")) and line not in keep:
                keep.append(line)
    if facts:
        history += "\n\n本章已经实际发生且经主控核验的事实（只作承接，不重写）：\n" + "\n".join("- " + fact for fact in facts)
    if previous_tail:
        history += "\n\n上一场最后片段（接在其后，不照抄）：\n" + previous_tail
    events = "\n".join(f"{index}. {item['action']}" for index, item in enumerate(scene["beats"], 1))
    return (characters.strip() + "\n\n〖前情〗\n" + history
            + "\n\n〖事件骨架〗\n" + events
            + "\n\n〖写作要求〗\n" + "\n".join(keep)
            + "\n本场开始状态：" + scene["start_state"]
            + "\n本场结束状态：" + scene["end_state"]
            + f"\n本次只写这一段连续场景，约{scene['target_chars']}字。"
            + "从本场第一个具体动作直接开始，只推进上述事件；结束于指定状态。只输出小说正文。")


def validate_review(review: dict, scene: dict, text: str, request_hash: str, draft_hash: str) -> list[str]:
    if (review.get("schema_version") != 1 or review.get("status") != "pass"
            or review.get("request_sha256") != request_hash or review.get("draft_sha256") != draft_hash):
        raise ValueError("本场审阅未通过或指纹过期，不能生成下一场")
    if review.get("issues") != []:
        raise ValueError("本场仍有未解决问题，不能继续")
    evidence = review.get("completed_beats", [])
    if (not isinstance(evidence, list) or any(not isinstance(row, dict) for row in evidence)
            or [str(row.get("id")) for row in evidence] != [str(row["id"]) for row in scene["beats"]]):
        raise ValueError("审阅须逐项覆盖本场情节点")
    for row in evidence:
        quote = row.get("evidence")
        if not isinstance(quote, str) or not quote.strip() or quote not in text:
            raise ValueError("情节点证据必须是本场原句")
    checks = review.get("checks", {})
    if not isinstance(checks, dict):
        raise ValueError("审阅缺少事实、连续性和结束状态检查")
    for key in CHECKS:
        check = checks.get(key, {})
        if not isinstance(check, dict):
            raise ValueError("审阅检查须为对象：" + key)
        quote = check.get("evidence")
        if check.get("pass") is not True or not isinstance(quote, str) or not quote.strip() or quote not in text:
            raise ValueError("审阅检查须通过并附本场原句：" + key)
    rows = review.get("established_facts")
    if not isinstance(rows, list) or not rows:
        raise ValueError("审阅须提取有原句依据的已发生事实")
    facts = []
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("fact"), str) or not row["fact"].strip()
                or not isinstance(row.get("evidence"), str) or not row["evidence"].strip() or row["evidence"] not in text):
            raise ValueError("每条交接事实须附本场原句，不能把未发生的计划当作事实")
        facts.append(row["fact"])
    return facts


def advance(work: Path, prompt: dict, prompt_hash: str, model: str, adapters: list,
            request, write, repeat, count_chars, endpoint: str, max_tokens: int) -> tuple[list[str], dict | None, str]:
    """Generate at most one scene per invocation; return only reviewed text for assembly."""
    path = work / "dpo_scene_plan.json"
    raw_plan = path.read_bytes()
    plan = load_plan(path, prompt, prompt_hash)
    plan_hash = digest(raw_plan)
    folder = work / "scene_handoff" / plan_hash
    folder.mkdir(parents=True, exist_ok=True)
    write(folder / "plan.json", raw_plan.decode("utf-8-sig"))
    accepted, facts = [], []
    previous_request = ""
    for index, scene in enumerate(plan["scenes"], 1):
        if accepted:
            chapter_goal = sum(row["target_chars"] for row in plan["scenes"])
            remaining_chars = chapter_goal - sum(count_chars(text) for text in accepted)
            remaining_weight = sum(row["target_chars"] for row in plan["scenes"][index - 1:])
            scene = dict(scene, target_chars=max(250, min(1600, round(remaining_chars * scene["target_chars"] / remaining_weight))))
        user = make_prompt(prompt, scene, facts, accepted[-1][-320:] if accepted else "")
        request_doc = {"system": prompt["system"], "user": user, "model": model, "adapters": adapters,
                       "prompt_sha256": prompt_hash, "plan_sha256": plan_hash,
                       "previous_review_sha256": previous_request, "sampling": plan.get("sampling", {}),
                       "max_tokens": max_tokens}
        request_bytes = (json.dumps(request_doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        request_hash = digest(request_bytes)
        stem = folder / f"scene_{index:02d}"
        request_path, draft_path = stem.with_suffix(".request.json"), stem.with_suffix(".md")
        meta_path, review_path = stem.with_suffix(".result.json"), stem.with_suffix(".review.json")
        if draft_path.exists():
            if not request_path.is_file() or request_path.read_bytes() != request_bytes:
                raise ValueError("本场输入已变化，不能复用旧稿；由主控修订计划后再生成")
            text = draft_path.read_text(encoding="utf-8").strip()
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("draft_sha256") != digest(draft_path.read_bytes()):
                raise ValueError("场景原文被更改，不能承接")
        else:
            write(request_path, request_bytes.decode("utf-8"))
            text, finish, response_model = request(endpoint, model, prompt["system"], user, max_tokens, adapters,
                                                   sampling=plan.get("sampling", {}))
            text = text.strip()
            write(draft_path, text + "\n")
            errors = []
            if response_model != model or finish != "stop":
                errors.append("响应模型或结束状态不符")
            if count_chars(text) < max(200, scene["target_chars"] * .65) or count_chars(text) > scene["target_chars"] * 1.5:
                errors.append("本场篇幅偏离计划，请审阅输入与动作密度，不自动扩写")
            if repeat(text) or any(repeat(old + text) for old in accepted):
                errors.append("本场或跨场出现重复段落")
            meta = {"finish_reason": finish, "model": response_model, "errors": errors,
                    "draft_sha256": digest(draft_path.read_bytes())}
            write(meta_path, json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
        from scene_repair import requested_repair
        repaired = None
        repair_rounds = 0
        repair_doc = request_doc
        for _ in range(2):
            result = requested_repair(stem, text, meta, repair_doc, request_hash, request, write, endpoint)
            if result is None:
                break
            repaired = result
            repair_rounds += 1
            stem, text, meta, request_hash = repaired
            draft_path, review_path = stem.with_suffix(".md"), stem.with_suffix(".review.json")
            repair_doc = dict(repair_doc, previous_repair_sha256=request_hash)
        if repaired:
            if repeat(text) or any(repeat(old + text) for old in accepted):
                meta = dict(meta, errors=meta["errors"] + ["修订后出现重复段落"])
            if count_chars(text) < max(200, scene["target_chars"] * .65) or count_chars(text) > scene["target_chars"] * 1.5:
                meta = dict(meta, errors=meta["errors"] + ["修订后篇幅偏离本场计划"])
        report = {"status": "blocked" if meta["errors"] else "awaiting_scene_review",
                  "generation_mode": "reviewed_scenes_v1", "scene": index, "scenes": len(plan["scenes"]),
                  "accepted_scenes": len(accepted), "output": str(draft_path), "review": str(review_path),
                  "scene_plan_sha256": plan_hash, "request_sha256": request_hash,
                  "scene_draft_sha256": meta["draft_sha256"], "errors": meta["errors"],
                  "requested_scene_chars": scene["target_chars"],
                  "scene_characters": count_chars(text),
                  "characters": sum(count_chars(t) for t in accepted) + count_chars(text),
                  "model": model, "finish_reason": meta["finish_reason"], "active_adapters": adapters,
                  "prompt_sha256": prompt_hash, "draft_sha256": None}
        if digest(path.read_bytes()) != plan_hash or digest((work / "dpo_prompt.json").read_bytes()) != prompt_hash:
            raise ValueError("生成期间计划或 Prompt 变化，不能接受本场")
        if meta["errors"]:
            return accepted, report, plan_hash
        if not review_path.is_file():
            template = {"schema_version": 1, "status": "pending", "request_sha256": request_hash,
                        "draft_sha256": meta["draft_sha256"], "issues": [],
                        "completed_beats": [{"id": row["id"], "evidence": ""} for row in scene["beats"]],
                        "checks": {key: {"pass": False, "evidence": "", "reason": ""} for key in CHECKS},
                        "established_facts": [{"fact": "", "evidence": ""}]}
            write(stem.with_suffix(".review.template.json"), json.dumps(template, ensure_ascii=False, indent=2) + "\n")
            return accepted, report, plan_hash
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if repair_rounds == 2 and review.get("status") == "repair":
            report.update(status="blocked", errors=["本场已局部修订两轮，不能继续修订；保留稿件并修正规划"])
            return accepted, report, plan_hash
        try:
            facts.extend(validate_review(review, scene, text, request_hash, meta["draft_sha256"]))
        except ValueError as exc:
            report.update(status="blocked", errors=[str(exc)] + list(review.get("issues", [])))
            return accepted, report, plan_hash
        previous_request = digest(review_path.read_bytes())
        accepted.append(text)
    return accepted, None, plan_hash
