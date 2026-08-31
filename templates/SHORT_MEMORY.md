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
commit: none
verification: passed | partial | not_run
memory_value: business | technical | both | none
target_long: BUSINESS | TECHNICAL | BOTH | NONE
---

# 短期记忆模板

> 本模板用于 `.easy-coding/memory/short/` 下的单次任务记忆。
> 文件名规则：`{memory_id}_{YYYYMMDD}_{smart_name}.md`
> `memory_id` 使用 `SM-<UUIDv7>`，并与本文件 frontmatter `id` 完全一致；新记忆不得扫描目录计算数字序号。
> 单条短期记忆创建后不修改；短期记忆是“近期细节滑动窗口 + 待沉淀缓冲区”。
> 默认窗口为 max 10 / keep 5；只有短期记忆超过 max 时才归档，因此第 11 条写入后最旧 6 条成为候选，最新 5 条保留。
> 排序依次使用 frontmatter `date`、ID 类型、`id`、文件名；同日旧 `SM-YYYYMMDD-NNN` ID 排在 UUIDv7 ID 前。
> 旧数字文件名和 `SM-YYYYMMDD-NNN` ID 保持兼容读取，不做破坏性重命名。

## 任务摘要

- 目标：{本次真正解决的问题}
- 范围：{本次实际涉及的模块、页面、接口或文件}
- 结果：{已完成 / 部分完成 / 未完成，并说明原因}
- 关键约束：{编码、兼容、接口、Spec、Prototype 或用户指定约束；无则写“无”}

## 执行证据

| 类型 | 内容 |
|---|---|
| 候选指纹 | {candidate_sha256} |
| Reviewer 来源 | {independent:<mechanism> / host-fallback:<reason>} |
| 发现与修复 | {分类、Repair Bundle 与结果；无则写“无”} |
| 关键文件 | {文件或模块列表；无则写“无”} |
| 验证命令 | {测试 / 构建 / 静态检查命令与结果；未执行说明原因} |
| 用户确认 | {QUALITY 结果确认及时间/轮次} |
| 剩余风险 | {suggestion、环境边界或“无”} |
| Canonical | {task/Step/integration 状态；不适用写“无”} |
| 提交信息 | {commit hash；未提交写“none”} |

## 业务记忆候选

> 只记录未来可能复用的业务事实。无则写“无”。

- 业务概念 / 字段语义：{概念、字段、枚举、状态含义}
- 业务流程 / 状态流转：{链路步骤、前后置条件、异常分支}
- 业务规则 / 兼容背景：{准入条件、决策依据、灰度或历史兼容原因}
- 上下游契约：{生产方、消费方、接口或消息字段}
- 业务排障经验：{常见误判、优先检查路径}

## 技术记忆候选

> 只记录未来可能复用的工程事实。无则写“无”。

- 架构 / 接口决策：{模块边界、依赖方向、接口契约}
- 工程规则 / 工作流：{编码、提交、发布、全局安装、目录边界}
- 实现模式 / 复用写法：{推荐做法、兜底策略、兼容写法}
- 易错点 / 修复策略：{问题成因、修复方式、验证方式}
- 验证经验：{测试命令、环境限制、验收路径}

## 不沉淀内容

> 记录不进入长期记忆的内容与原因，避免沉淀时误吸收流水账。

- {普通文件清单 / 临时日志 / 一次性数据 / 无复用价值细节；无则写“无”}

## 关联记忆

- 前置：{相关短期记忆 id、长期主题或“无”}
- 后续：{后续关联任务；无则写“无”}
