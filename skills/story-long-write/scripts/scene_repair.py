"""One local-model repair round with immutable source and review evidence."""
from __future__ import annotations

import hashlib
import json


def sha(data):
    return hashlib.sha256(data).hexdigest()


def requested_repair(stem, text, meta, request_doc, request_hash, request, write, endpoint):
    review_path = stem.with_suffix(".review.json")
    if not review_path.is_file():
        return None
    raw_review = review_path.read_bytes()
    review = json.loads(raw_review.decode("utf-8"))
    if review.get("status") != "repair":
        return None
    if (review.get("schema_version") != 1 or review.get("request_sha256") != request_hash
            or review.get("draft_sha256") != meta["draft_sha256"]):
        raise ValueError("局部修订依据的输入或原稿指纹不符")
    if meta.get("model") != request_doc["model"] or meta.get("finish_reason") != "stop":
        raise ValueError("模型或截断错误不能用局部修订绕过")
    edits = review.get("repairs")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 3:
        raise ValueError("一轮局部修订只接收1..3个明确原段")
    spans = []
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {"before", "instruction"}:
            raise ValueError("局部修订只收 before 原句与 instruction 事实要求；主控不能提供替换正文")
        before, instruction = edit["before"], edit["instruction"]
        if (not isinstance(before, str) or not 1 <= len(before) <= 500 or text.count(before) != 1
                or not isinstance(instruction, str) or not instruction.strip()):
            raise ValueError("修订原段必须在原稿中唯一出现，长度1..500，且说明具体问题")
        start = text.index(before)
        spans.append((start, start + len(before)))
    ordered = sorted(spans)
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("局部修订原段不能相互重叠")
    if sum(end - start for start, end in spans) > min(750, max(150, len(text) * .5)):
        raise ValueError("局部修订范围过大，应修正计划后重新生成本场")
    repaired_stem = stem.parent / (stem.name + "_repaired")
    request_path = repaired_stem.with_suffix(".request.json")
    draft_path = repaired_stem.with_suffix(".md")
    result_path = repaired_stem.with_suffix(".result.json")
    manifest = {"source_request": request_doc, "source_draft_sha256": meta["draft_sha256"],
                "review_sha256": sha(raw_review), "repairs": edits, "strategy": "positive_facts_v2"}
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if draft_path.is_file():
        if request_path.read_bytes() != encoded:
            raise ValueError("本轮局部修订要求已变化；不能覆盖已生成的修订稿")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("draft_sha256") != sha(draft_path.read_bytes()):
            raise ValueError("本地修订稿被手动更改，不能继续")
        repaired = draft_path.read_text(encoding="utf-8").strip()
    else:
        write(request_path, encoded.decode("utf-8"))
        repaired, records, errors = text, [], []
        for edit, (start, end) in zip(edits, spans):
            before = edit["before"]
            prefix = request_doc["user"].split("〖事件骨架〗", 1)[0]
            left = text[max(0, start - 100):start]
            right = text[end:end + 100]
            user = (prefix + "\n\n〖事件骨架〗\n1. 为指定位置写一小段小说，必须满足：" + edit["instruction"]
                    + "\n\n〖写作要求〗\n前接原文（不能重写或复述）：\n" + left
                    + "\n后接原文（不能重写或复述）：\n" + right
                    + f"\n只输出填入两段之间的小说文字，约{len(before)}字。"
                    + "直接完成指定动作，不输出整场、不解释、不加代码围栏，不重复前后已有动作。")
            after, finish, model = request(endpoint, request_doc["model"], request_doc["system"], user,
                                            min(1000, len(before) * 3 + 200), request_doc["adapters"],
                                            sampling=request_doc.get("sampling", {}))
            after = after.strip()
            records.append({"user": user, "before": before, "after": after, "model": model, "finish_reason": finish})
            if model != request_doc["model"] or finish != "stop":
                errors.append("局部修订模型或结束状态不符")
            if not after or after == before or len(after) > len(before) * 2 + 60 or after.startswith("```"):
                errors.append("局部修订未修改或超出指定范围")
        # Apply exact original offsets from right to left; replacement text never comes from the controller.
        for (start, end), record in sorted(zip(spans, records), reverse=True):
            repaired = repaired[:start] + record["after"] + repaired[end:]
        write(draft_path, repaired + "\n")
        result = {"model": request_doc["model"], "finish_reason": records[-1]["finish_reason"],
                  "errors": errors, "draft_sha256": sha(draft_path.read_bytes()), "replacements": records}
        write(result_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return repaired_stem, repaired, result, sha(encoded)
