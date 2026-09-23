---
memory_schema: 2
id: {memory_id}
source_task: ec-skill-{UUIDv7}
workflow_mode: standard
producer: easy-coding-skill
date: YYYY-MM-DD
task_type: feature | bugfix | refactor | perf | frontend | doc | workflow
project_mode: startup | iteration
domain:
  - "{业务域或模块}"
tags:
  - "{关键词}"
related_files:
  - "{关键文件或模块}"
memory_value: business | technical | both | none
target_long: BUSINESS | TECHNICAL | BOTH | NONE
---

# {可复用知识主题}

> 本模板用于 `.easy-coding/memory/short/` 下的单次任务记忆。
> 文件名规则：`{memory_id}_{YYYYMMDD}_{smart_name}.md`
> `memory_id` 使用 `SM-<UUIDv7>`，并与本文件 frontmatter `id` 完全一致；新记忆不得扫描目录计算数字序号。
> 单条短期记忆创建后不修改；短期记忆是“近期细节滑动窗口 + 待沉淀缓冲区”。
> 默认窗口为 max 10 / keep 5；只有短期记忆超过 max 时才归档，因此第 11 条写入后最旧 6 条成为候选，最新 5 条保留。
> 排序依次使用 frontmatter `date`、ID 类型、`id`、文件名；同日旧 `SM-YYYYMMDD-NNN` ID 排在 UUIDv7 ID 前。
> 旧数字文件名和 `SM-YYYYMMDD-NNN` ID 保持兼容读取，不做破坏性重命名。

## 知识摘要

{说明什么场景应读取这条知识，以及未来开发最需要知道的结论。}

## 可复用知识

{只写已确认、未来有用的业务语义、设计原因、修改入口、适用边界或真实踩坑与解法。
采用自然段或必要列表，不适用的分类直接省略，不把单次任务限制变成永久规则。}

## 来源

- {真实代码路径/符号、Canonical 章节、已确认设计或关联知识；引用必要定位，不复制原文。}

## 最小质量追溯

{简洁保留当前 candidate_sha256、reviewer 来源、必要验证命令/退出码/结论、真实用户结果确认
和剩余限制。复用检查列原 input SHA 与来源；Canonical 已有持久证据时引用对应事件。
来源不能只指向完成后删除的 checks.json、baseline 或交接文件。}

> 写作指引，不进入记忆正文：删除模板说明和未使用占位。无新增知识时设置
> `memory_value: none` / `target_long: NONE`，在知识摘要说明原因，省略“可复用知识”。
> 不写执行流水、审批 JSON、单次测试数量、覆盖率统计或“不沉淀内容”清单。
> 验证命令只有对未来有指导价值时才进入知识正文；质量追溯不参与默认检索或长期沉淀。
