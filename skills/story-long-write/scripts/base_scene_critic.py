"""Read-only scene critique using the same model without its prose adapter."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from generate_dpo_draft import atomic_write
from preflight_dpo_writer import check_backend

MODEL = "qwen3.8-27b-udq4-xuanhuan-dpo"


def validate_verdict(verdict, text):
    if not isinstance(verdict, dict) or verdict.get("status") not in ("pass", "fail"):
        raise ValueError("辅助审稿未返回有效JSON判定")
    for key in ("issues", "evidence"):
        if not isinstance(verdict.get(key), list) or any(not isinstance(s, str) or not s.strip() for s in verdict[key]):
            raise ValueError("辅助审稿须返回issues和evidence文字列表")
    if verdict["status"] == "fail" and (not verdict["issues"] or not verdict["evidence"]):
        raise ValueError("辅助审稿报告问题却没有具体说明和原文证据")
    if verdict["status"] == "pass" and verdict["issues"]:
        raise ValueError("辅助审稿状态与问题列表矛盾")
    if any(quote not in text for quote in verdict["evidence"]):
        raise ValueError("辅助审稿引文不在原稿，不能作为事实依据")


def payload(model, adapters, task, text, seed):
    user = ("你是章节连续性审稿员。本次只检查两个方面：物件持有状态和叙述视角。"
            "先按原稿时间顺序核对每次取起、放下、交接之后物件归谁；若已经放下却没有再次取起就又持有，须报告原句。"
            "若指定贴近某人物的第三人称视角，只能其感知，不能直接进入其他人物内心；以任务指定视角为准。"
            "声音大小、说话、可见表情动作都是可感知现象，不能据此认定进入内心；明确陈述他人未说出的思想感受才报告。"
            "普通新增细节不一概判错；未写到下一场不算本场错误。标点由脚本整理，本次不审标点、字数和文风，不写替换正文。"
            "只输出JSON对象：status(pass或fail)、issues(具体问题文字列表)、evidence(原句字符串列表)。"
            "evidence每项须为原稿内一段连续原文，不拼接、不改字、不加解释；说明只放issues。"
            "若没有确定问题，两列表为空。\n写作任务：\n" + task + "\n待审原稿：\n" + text)
    return {"model": model, "messages": [{"role": "system", "content": "你是审稿助手，只检查给定场景，不写小说。"},
                                          {"role": "user", "content": user}],
            "max_tokens": 1800, "temperature": 1., "top_p": .95, "top_k": 20, "min_p": .05,
            "repeat_penalty": 1., "seed": seed, "stream": False, "cache_prompt": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "lora": [{"id": adapter["id"], "scale": 0.} for adapter in adapters]}


def run(args):
    work = args.project.resolve() / '.story' / 'work' / f'第{args.chapter:03d}章'
    report = json.loads((work/'dpo_report.json').read_text(encoding='utf-8'))
    draft = Path(report['output']).resolve()
    if not draft.is_relative_to(work):
        raise ValueError("辅助审稿只读本章工作目录内的生成稿")
    raw = draft.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != (report.get('scene_draft_sha256') or report.get('draft_sha256')):
        raise ValueError("待审原稿指纹与生成报告不符")
    text = raw.decode('utf-8').strip()
    if report.get('scene'):
        source = work/'scene_handoff'/report['scene_plan_sha256']/f"scene_{report['scene']:02d}.request.json"
        task = json.loads(source.read_text(encoding='utf-8'))['user']
    else:
        task = json.loads((work/'dpo_prompt.json').read_text(encoding='utf-8'))['user']
    model, adapters = check_backend(args.endpoint, MODEL)
    body = payload(model, adapters, task, text, args.seed)
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True).encode('utf-8')
    folder = work/'critic'/hashlib.sha256(encoded).hexdigest()
    folder.mkdir(parents=True, exist_ok=True)
    atomic_write(folder/'request.json', encoded.decode('utf-8')+'\n')
    response_path = folder/'response.json'
    if response_path.is_file():
        response = json.loads(response_path.read_text(encoding='utf-8'))
    else:
        req = Request(args.endpoint.rstrip('/')+'/v1/chat/completions',data=encoded,headers={'Content-Type':'application/json'})
        with urlopen(req, timeout=1200) as incoming:
            response = json.load(incoming)
        atomic_write(response_path, json.dumps(response,ensure_ascii=False,indent=2)+'\n')
    choice = response['choices'][0]
    if response.get('model') != model or choice.get('finish_reason') != 'stop':
        raise ValueError("辅助审稿模型或结束状态不符")
    verdict = json.loads(choice['message']['content'])
    validate_verdict(verdict,text)
    if hashlib.sha256(draft.read_bytes()).hexdigest() != digest:
        raise ValueError("辅助审稿期间原稿改变，结果过期")
    result = {"status": 'review_required' if verdict['status']=='fail' else 'advisory_clear',
              "role": 'review_only', "model": model, "lora": body['lora'], "seed": args.seed,
              "draft": str(draft), "draft_sha256": digest, "verdict": verdict,
              "request": str(folder/'request.json'), "response": str(response_path),
              "notice": '辅助意见不替代主控审阅，不能据此自动放行、代写或提交正文。'}
    atomic_write(work/'dpo_scene_critic.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--chapter',required=True,type=int)
    parser.add_argument('--endpoint',default='http://127.0.0.1:8088')
    parser.add_argument('--seed',type=int,default=42813)
    args=parser.parse_args()
    try:
        result=run(args)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result={'status':'tool_unavailable','errors':[str(exc)]}
        work=args.project.resolve()/'.story'/'work'/f'第{args.chapter:03d}章'
        if work.is_dir():
            atomic_write(work/'dpo_scene_critic.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False))
        return 2
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
