"""Durable DPO evidence; never infer legacy mode from scratch cleanup."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

MANIFEST = '_evidence_manifest.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',newline='\n',dir=path.parent,delete=False) as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2)
        handle.write('\n')
        temp=handle.name
    os.replace(temp,path)


def root(project, chapter):
    book=project.resolve()
    target=book/'.story'/'dpo-evidence'/f'第{chapter:03d}章'
    if not target.resolve().is_relative_to(book):
        raise ValueError('DPO证据目录不能指向书目录外')
    return target


def verify(folder, manifest):
    if not isinstance(manifest,dict) or manifest.get('schema_version')!=1 or not isinstance(manifest.get('files'),dict):
        raise ValueError('DPO归档清单无效')
    for relative, expected in manifest['files'].items():
        path=folder/relative
        if not path.resolve().is_relative_to(folder.resolve()) or not path.is_file() or sha(path)!=expected:
            raise ValueError('DPO归档文件指纹不符：'+str(relative))


def archive_work(project, chapter, work, body_path):
    if not work.resolve().is_relative_to(project.resolve()/'.story'/'work'):
        raise ValueError('DPO工作证据不能指向本书工作目录外')
    prompt=work/'dpo_prompt.json'
    if not prompt.is_file() or json.loads(prompt.read_text(encoding='utf-8')).get('writer_mode')!='dpo_only':
        return None
    files={}
    for path in sorted(work.rglob('*')):
        if not path.resolve().is_relative_to(work.resolve()):
            raise ValueError('DPO工作目录含指向外部的文件或目录')
        if path.is_file():
            relative=path.relative_to(work).as_posix()
            if relative!=MANIFEST:
                files[relative]=sha(path)
    report=json.loads((work/'dpo_report.json').read_text(encoding='utf-8'))
    body_sha=sha(body_path)
    draft_sha=files.get('dpo_draft.md')
    # Author final-review is a first-class stage: when an author_final baseline exists the
    # committed body is the author's final draft (not the raw model draft). Both are kept as
    # evidence; the body must match the registered author-final hash. Without a baseline the
    # legacy rule (body == frozen model draft) applies.
    author_final=None
    af=work/'author_final.json'
    if af.is_file():
        author_final=json.loads(af.read_text(encoding='utf-8'))
        if author_final.get('schema_version')!=1 or author_final.get('author_final_sha256')!=body_sha:
            raise ValueError('归档前作者终稿基线与正式正文不一致')
        if author_final.get('model_original_sha256')!=draft_sha:
            raise ValueError('归档前作者终稿基线对应的模型原稿已变化')
    elif body_sha!=draft_sha:
        raise ValueError('归档前DPO来源与正式正文不一致')
    if (report.get('status')!='ready' or report.get('finish_reason')!='stop'
            or report.get('model')!='qwen3.8-27b-udq4-xuanhuan-dpo'
            or draft_sha is None or report.get('draft_sha256')!=draft_sha
            or report.get('prompt_sha256')!=files.get('dpo_prompt.json')
            or (report.get('scene_plan_sha256') and report['scene_plan_sha256']!=files.get('dpo_scene_plan.json'))):
        raise ValueError('归档前DPO来源与正式正文不一致')
    target=root(project,chapter)
    target.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='generation-',dir=target))
    for relative in files:
        dest=folder/relative
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(work/relative,dest)
    manifest={'schema_version':1,'files':files,'body_sha256':sha(body_path)}
    verify(folder,manifest)
    write_json(folder/MANIFEST,manifest)
    return {'schema_version':1,'archive':folder.name,'manifest_sha256':sha(folder/MANIFEST)}


def publish(project,chapter,pointer):
    target=root(project,chapter)
    write_json(target/'current.json',pointer)
    return str(target/pointer['archive'])


def archived_work(project,chapter):
    target=root(project,chapter)
    pointer_path=target/'current.json'
    if not pointer_path.is_file():
        return None
    pointer=json.loads(pointer_path.read_text(encoding='utf-8'))
    if not isinstance(pointer,dict):
        raise ValueError('DPO归档指针无效')
    name=pointer.get('archive','')
    if pointer.get('schema_version')!=1 or not isinstance(name,str) or not re.fullmatch(r'generation-[A-Za-z0-9_-]+',name):
        raise ValueError('DPO归档指针无效')
    folder=target/name
    if not folder.resolve().is_relative_to(target.resolve()) or sha(folder/MANIFEST)!=pointer.get('manifest_sha256'):
        raise ValueError('DPO归档清单指纹不符')
    manifest=json.loads((folder/MANIFEST).read_text(encoding='utf-8'))
    verify(folder,manifest)
    return folder
