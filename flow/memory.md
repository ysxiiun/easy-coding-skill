# MEMORY 与 COMPLETE

> 仅在用户确认 QUALITY 绿色结果后读取。同一轮刚输出 Guard 结果时禁止进入本文件。

## 1. 进入与短期知识

只有主 Agent 进入本阶段。交接恢复返回 MEMORY 时，复核已保存的 QUALITY 结果确认、证据及
当前记忆进度，继续未完成动作，不重新分析、不重复创建已落地的短期记忆。存在交接目录时，
每个已完成记忆动作的真实路径和窗口进度写入该请求的 MEMORY 检查点，以便中断恢复。

输出 `[阶段：MEMORY]`。复用本轮固定 `run_id=ec-skill-<UUIDv7>`，读取
`templates/SHORT_MEMORY.md`，新建一条 schema 2 短期记忆：

- `memory_id=SM-<UUIDv7>`，文件名为 `{memory_id}_{YYYYMMDD}_{smart_name}.md`；
- `source_task` 必须等于 run ID；`workflow_mode: standard` 仅为共享兼容元数据；
- `producer: easy-coding-skill`；
- 正文先写知识主题与检索摘要，说明适用场景、核心结论、业务规则、设计原因、修改入口和
  有依据的排障经验；只保留对下次开发有用的内容，不强行填满分类。
- 复用已经确认的分析、实施回执和审查发现，不重新扫描仓库、重复验证或要求编码 Agent
  另写报告。任务内限制不得擅自提升为永久项目规则。
- 没有新增可复用知识时设 `memory_value: none`、`target_long: NONE`，简述原因和来源，不
  编造经验或重复已有知识；仍完成本轮短期记忆。
- 来源优先使用真实代码入口、Canonical 章节或已有知识。Skill 没有持久任务日志，因此在
  文末保留最小质量追溯：当前 candidate SHA、reviewer 来源、真实验证命令/退出码/结论，
  复用项的原 input SHA 与来源、用户结果确认和必要剩余限制；不复制审批 JSON、执行时间线、
  修复轮次流水、单次测试数量或覆盖率统计，不另写“不沉淀内容”清单。不得只引用即将清理的
  临时文件或交接路径；Canonical 已有持久证据时引用对应事件，不重复正文。

写入后重读校验文件存在、schema、UUIDv7、ID/文件名前缀、三个共享字段和质量证据。单条短期
记忆创建后不修改；旧数字文件名与旧式 ID 只兼容读取，不破坏性重命名。

新规则优先于项目旧模板的过程栏目；不为升级重写历史记忆或用户模板。最小质量追溯仅供
需要追溯时读取，不进入默认知识摘要或长期主题。

## 2. 冻结窗口

- 固定 `short_term_max=10`、`short_term_keep=5`，不读取私有配置覆盖。
- 只统计 schema 2 Markdown；旧 schema 先走 `flow/memory-migration.md`。
- 稳定排序：date → 同日旧式 ID、UUIDv7、其他 ID → id → 文件名。
- 写入本轮检查点后一次性冻结 `short_count`、`action`、`candidate_files`、`kept_files`：
  - 仅当 `short_count > 10` 时 `distill`；候选数为 `short_count - 5`；
  - 否则 `no-op`，不得写长期文件或删除短期记忆。
- 默认第 10 条仍为 no-op；第 11 条写入后归档最旧 6 条、保留最新 5 条。
- 指令冻结后不得因中途文件变化重新分配候选。

## 3. 长期沉淀与架构评估

`distill` 时只读取冻结候选，并先读取 `flow/memory-retirement.md`：

1. 业务事实进入 `BUSINESS.md`，工程事实进入 `TECHNICAL.md`；`memory_value: none` 不产生
   长期主题。从旧记忆中提取有效知识，过滤验收流水、质量摘要、临时日志和一次性数据。
2. 只对候选命中主题执行定向 delete/merge/deprecate，更新 `MEMORY.md` 索引。
3. 做一次有界架构评估。只有候选证据证明发生下列变化之一才更新 `ABSTRACT.md`：
   模块边界、依赖方向、核心数据流、技术栈、构建或部署方式。
4. 更新 ABSTRACT 时只修改受影响章节，并按 `templates/CHANGELOG.md` 创建或追加
   `.easy-coding/CHANGELOG.md`，记录日期、来源 memory ID、变化、受影响章节和证据；普通
   文件增删、测试补充或局部实现调整不得触发。
5. 长期更新、不沉淀审计和架构评估成功后，删除全部 candidate；kept 不得被读取或消费。

## 4. Canonical 完成与校验

- `no-op`：确认本轮检查点仍存在且未修改。
- `distill`：确认 candidate 全部不存在、kept 全部存在，且架构评估结论已记录。
- Canonical 任务重新 `show`，确认 design、integration 和 QUALITY 绑定证据仍成立后，通过 writer
  把已 `verified` 的 task 写为 `completed`。
- 任一校验失败保持 MEMORY 并修复；不得输出 COMPLETE。

MEMORY 回执列出短期文件、run ID、candidate SHA、窗口总数/action；distill 还列候选/保留、
长期主题、不沉淀原因、架构评估与消费校验。

## 5. COMPLETE

全部校验后，存在交接目录时先按协议 checkpoint COMPLETE（含真实 memory_ref），再 cleanup
当前目录；不单独提前删 baseline，以免清理失去绑定。无交接时清理原仓库外 baseline 和本轮
检查存储，再输出：

```markdown
[阶段：COMPLETE]

🎉 任务全部完成！

- 质量候选：{candidate_sha256}
- reviewer 来源：{independent / host-fallback}
- 记忆：{短期检查点与窗口动作}
- Canonical：{不适用或 completed}
```

baseline 清理失败时披露临时路径并继续尝试安全清理；不得删除项目文件。
