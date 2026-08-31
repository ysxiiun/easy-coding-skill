# MEMORY 与 COMPLETE

> 仅在用户确认 QUALITY 绿色结果后读取。同一轮刚输出 Guard 结果时禁止进入本文件。

## 1. 进入与短期检查点

输出 `[阶段：MEMORY]`。复用本轮固定 `run_id=ec-skill-<UUIDv7>`，读取
`templates/SHORT_MEMORY.md`，新建一条 schema 2 短期记忆：

- `memory_id=SM-<UUIDv7>`，文件名为 `{memory_id}_{YYYYMMDD}_{smart_name}.md`；
- `source_task` 必须等于 run ID；`workflow_mode: standard` 仅为共享兼容元数据；
- `producer: easy-coding-skill`；
- 正文记录 candidate SHA、reviewer 来源、发现与 Repair Bundle、验证命令/结果、剩余风险、
  用户确认和 Canonical 状态。

写入后重读校验文件存在、schema、UUIDv7、ID/文件名前缀、三个共享字段和质量证据。单条短期
记忆创建后不修改；旧数字文件名与旧式 ID 只兼容读取，不破坏性重命名。

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

1. 业务事实进入 `BUSINESS.md`，工程事实进入 `TECHNICAL.md`；普通流水、临时日志和一次性
   数据记录为不沉淀。
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

全部校验后清理仓库外 baseline，再输出：

```markdown
[阶段：COMPLETE]

🎉 任务全部完成！

- 质量候选：{candidate_sha256}
- reviewer 来源：{independent / host-fallback}
- 记忆：{短期检查点与窗口动作}
- Canonical：{不适用或 completed}
```

baseline 清理失败时披露临时路径并继续尝试安全清理；不得删除项目文件。
