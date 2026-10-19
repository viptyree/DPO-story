# 本地 DPO 逐场交接

沿用 oh-story 主控、narrative-writer、审查和追踪。主控负责计划与验收，本地模型写正文；不增加显存要求。

## 准备计划

完成章节准备和设定摘录，在本章工作目录写 dpo_scene_plan.json。schema_version 为1；prompt_sha256 为审核后 dpo_prompt.json 完整文件的 SHA256；scenes 为2至6项，每项包含：

- beats：列表，各项含任务 id、具体动作 action；默认 id 对应细纲编号。细分同一情节点时用唯一 id（如1a、1b）及 source_id 标明原编号，相邻子场依次完成不同动作；全计划按序覆盖全部原编号，不遗漏或跳回。可合并相邻情节点。
- start_state：谁在何处、物件归谁、已发生什么。
- end_state：必须实际达到的状态；不用“收章”等术语，不要求照抄句子。
- target_chars：本场可见字符目标，250至1600；合计等于全章目标，按动作与冲突分配。
- character_states：只列本场出场人物；context_quotes 从已审核 Prompt 原文选取本场所需事实；requirements 只列本场文风和必要边界。三者为可选文字列表，建议明确填写，避免未来人物和全章规则干扰当前动作。

动作可细化已有情节，不增设关键设定。人物状态只写本场所需信息，不预告下一场才取出的物件。后场伤口、工具或位置须沿用已核验事实，不能写死尚未确定的细节。计划变化后旧场景不复用。本场要求不覆盖整章的真名、设定及连续性禁区。

计划可含 sampling：temperature（0至2）、repeat_penalty（1至1.3）。可选 lora_scale 为0.1至1，默认保持挂载强度，只在单次请求调整同一适配器。调参记入输入指纹，不改全局后端。b10643 不支持请求级推测解码开关，禁止用 speculative_n_max 声称已关闭MTP。这些参数不构成质量保证。

## 每场生成与审阅

写手运行同一条 `chapter_pipeline.py --project "{书目录}" --chapter N --generate-prepared` 命令。发现计划时，每次最多生成一场，返回 awaiting_scene_review；这是等待主控工作，不是请求作者批准。

主控完整读取报告 output 所指场景。核对情节点完成、人物关系、物件来源、时间与衣物伤口、结束状态；不得放过新编规章、价格、地名或重复段落。参考同目录 review.template.json，另存为报告 review 指定文件：

- status 只在内容通过时填 pass，issues 必须为空；保留 request_sha256、draft_sha256。
- completed_beats 为每个 id 提供本场原句 evidence。
- checks 的 canon、continuity、ending 均含 pass:true 和 evidence（一段连续原文，逐字引用）；说明放 reason，不在 evidence 加解释或拼接多段。引用存在不等于语义正确。
- established_facts 各项含 fact、evidence；只提取本场实际发生且不违背设定的事实，不把计划冒充事实。

审阅文件尚不存在属正常，按 review.template.json 创建，不据此判定路径有错。通过后再调用写手；下一场收到核验事实和上一场末320字符，目标按剩余字数与未写权重调整，限制250至1600字，全章范围不变。局部错误按 scene-repair.md 交同一模型，最多两轮、每轮重审。其他失败保留原文并停止，修正计划后再生成；不改正文凑通过。

所有场景通过后原样拼接，确定性整理标点，检查全章字数及原版正文规则；主控仍须通读整章。只有最终 ready 且内容通过才提交正式正文和追踪。无计划的整章生成只保留兼容实验，数字均分已停用。
