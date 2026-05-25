# Easy Coding With Claude 场景回归

> 本文件用于人工或 agent 演练联合模式，不作为运行时强制加载内容。

## 触发矩阵

| 场景 | 输入 | 期望 |
|---|---|---|
| 仅 Easy Coding | 用户只显式引用 `$easy-coding` | 进入普通 Easy-Coding 七阶段，不展示联合模式文案，不调用 Claude |
| 仅 With Claude | 用户只显式引用 `$with-claude` | 不进入 Easy-Coding 阶段流程 |
| 双显式触发 | 同一轮同时引用 `$easy-coding` 与 `$with-claude` | 展示 `已启动: Easy Coding With Claude 模式`，按需加载 `flow/with-claude.md` |
| 双触发 + `#no-coding` | 用户消息开头包含 `#no-coding` | 跳过 Easy-Coding 与联合模式全部阶段约束 |

## 阶段场景

| 场景 | 前置/输入 | 期望 |
|---|---|---|
| INIT 联合 | 联合模式命中且需要初始化 | Claude 只读草拟 SOUL / RULES / ABSTRACT；host 合并、说明采纳情况并负责写入 |
| ANALYSIS 联合 | 联合模式进入 ANALYSIS | 固定使用 `readonly_analysis` + `phase=analysis` + `expected_output_type=analysis`；技术方案包含 `### Claude 协作`，写明 Claude 状态、观点、采纳情况与冲突点 |
| ANALYSIS 等待 Claude | Claude 未返回最终 worker contract | 用户可见输出仍为 `[阶段：ANALYSIS]`，只汇报协作进展和已读证据，不输出正式方案，不进入 `WAITING_CONFIRM` |
| ANALYSIS Claude done | Claude 返回 done | host 合并 Claude 结论后，按 `SKILL.md` 2.5 完整模板输出技术方案，并进入 `WAITING_CONFIRM` |
| ANALYSIS Claude blocked | Claude 返回 blocked | host 继续输出完整技术方案，`### Claude 协作` 标注 `Claude pass unavailable` |
| IMPLEMENT 联合 | 用户已确认方案 | 不调用 Claude；host 按已确认方案独立实施 |
| PLAN 阶段误用 | With Claude task packet 含 `phase` / `workflow_type` | Easy Coding 不存在 `[阶段：PLAN]`；With Claude 的 `workflow_type` / `phase` 不得作为 Easy Coding 阶段输出 |
| 非法阶段误用 | 验证、测试、自检或完成汇报 | 不得输出 `[阶段：VERIFY]` / `[阶段：TEST]` / `[阶段：DONE]` / `[阶段：REVIEW_BLOCKED]`；验证和自检仍用 `[阶段：IMPLEMENT]`，完成只能用 `[阶段：COMPLETE]` |
| REVIEW 调用证据 | IMPLEMENT 完成且进入 REVIEW | 必须调用或尝试调用 `run_claude_worker.py`，使用 `post_implementation_review`，并展示 wrapper path、final contract、worker status 和 verdict 来源 |
| REVIEW 未调用 Claude | 只做了 host 自检、未启动 Claude、启动失败或未收到 final contract | 不得输出 Claude `accept` 或“Claude 已 review 通过”；只能映射为 `blocked` 并标注 `Claude review unavailable` |
| REVIEW accept | Claude verdict 为 accept | 结束 review，实施结果报告说明 review 已通过 |
| REVIEW fix | Claude verdict 为 fix | host 在已确认范围内修复，最多重新 review 3 轮 |
| REVIEW 3 轮未收敛 | REVIEW 已执行 3 轮仍未收敛 | 结束 review，在实施结果报告中说明剩余问题、已修复内容和风险，等待用户指令 |
| REVIEW replan | Claude verdict 为 replan | 不自动重走方案分析，在实施结果报告中说明 Claude 建议重新规划，等待用户决定 |
| Claude blocked | Claude worker blocked 或不可用 | 降级为 host-only，并标注 `Claude pass unavailable` 或 `Claude review unavailable` |
| REVIEW 后等待确认结果 | REVIEW accept / 测试通过 / host 自检通过后输出实施结果报告 | 必须停在 `[阶段：IMPLEMENT]` 等待用户确认；同一轮不得进入记忆 |
| REVIEW 后确认结果 | 上一轮已输出实施结果报告；用户点选“确认结果”或回复确认词 | 不要求再次显式触发 Easy Coding；迭代项目进入 `[阶段：MEMORY_SHORT]`，初创项目先执行初始化资产回补再进入 `[阶段：MEMORY_SHORT]` |
| 初创项目确认结果 | 联合模式 REVIEW 已结束，且首次任务跳过前置 INIT | 用户确认后执行 `post_v1_auto_init` 初始化资产回补，再进入 `MEMORY_SHORT → MEMORY_LONG → COMPLETE` |
| 迭代项目确认结果 | 联合模式 REVIEW 已结束 | 用户确认后直接进入 `MEMORY_SHORT → MEMORY_LONG → COMPLETE` |
| 原生确认可用 | 当前 agent 暴露 `request_user_input` 或等价工具 | 必须调用原生选择工具等待“确认结果”，不能只输出文本提示 |
| 原生确认选项瘦身 | 等待方案确认或实施结果确认 | 选项必须是真实下游分支；修改意见、反馈意见和补充说明由客户端 free-form Other 承接，不手写成按钮 |
| 原生确认不可用 | 当前 agent 未暴露原生选择工具 | 使用文本兜底，不得声称已展示原生选择框 |

## 安全检查

- Claude 任务包的 `add_read_dirs` 不得使用 `/`、`$HOME`、`/Users`、`/Users/<user>` 等宽目录。
- Claude 只允许只读分析，不允许编辑、patch、格式化、提交、推送、发布。
- REVIEW 只能在 IMPLEMENT 完成，并具备变更清单、验证结果和 host 自检结论后出现。
- REVIEW verdict 必须来自 Claude final worker contract；没有 `executed + final contract received` 证据时只能降级为 `Claude review unavailable`。
- REVIEW 修复不得扩大已确认改动范围；超出范围时停止自动修复，等待用户指令。
- REVIEW 结束后的“确认结果”属于 Easy Coding 已激活流程续流，不属于普通新请求，也不要求用户再次写 `$easy-coding`。
- Claude review accept、测试通过、host 自检通过都不等于用户确认结果。
