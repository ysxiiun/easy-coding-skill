# Easy Coding With Claude 联合模式

> 本文件由 `SKILL.md` 在用户同时显式引用 Easy Coding 与 With Claude 时按需加载。
> 本文件只负责组合编排；With Claude 的 worker contract、task packet、Claude 只读边界以 With Claude skill 自身文档为准。

---

## 进入条件

必须同时满足：

1. 用户显式触发 Easy Coding：`$easy-coding`、`easy-coding`，或清楚表达“加载/使用 Easy Coding skill”。
2. 用户显式触发 With Claude：`$with-claude`、`with-claude`，或清楚表达“加载/使用 With Claude skill”。
3. 当前轮未命中 `#no-coding`。

进入后必须先展示：

```markdown
已启动: Easy Coding With Claude 模式
```

若只命中其中一个 skill，不进入联合模式，按对应 skill 原有流程执行。

---

## 总原则

1. Easy Coding 仍是主流程，继续遵守 INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT → REVIEW → 实施结果报告 → 用户确认结果 → 按项目模式进入初始化资产回补或 MEMORY_SHORT → MEMORY_LONG → COMPLETE。
2. With Claude 只提供只读参谋能力，不接管 Easy Coding 阶段控制。
3. Claude 只在 INIT、ANALYSIS、REVIEW 介入；IMPLEMENT 期间不调用 Claude。
4. 所有写入、修复、初始化资产落地、记忆写入都只能由 host agent 执行。
5. 所有 Claude 输出都必须由 host agent 合并判断，不能直接作为最终结论。
6. Claude 观点必须保留来源与采纳状态：已采纳、部分采纳、未采纳。
7. Claude 不可用时允许降级为 host-only，但必须显著标注 `Claude pass unavailable`。
8. With Claude 的 `workflow_type` / `phase` 只是 worker task packet 字段，不是 Easy Coding 用户可见阶段；Easy Coding 不存在 `[阶段：PLAN]`。
9. REVIEW 结束后的“确认结果”是 Easy Coding 已激活流程续流；用户无需再次显式引用 Easy Coding 或 With Claude。
10. `VERIFY` / `TEST` / `DONE` / `REVIEW_BLOCKED` 不是 Easy Coding 阶段；验证、测试、自检仍属于 `IMPLEMENT`，完成只能使用 `COMPLETE`。
11. REVIEW 必须有真实 Claude 调用证据；未启动 Claude、未收到 final worker contract、或只有 host 自检时，必须降级为 `Claude review unavailable`，不得输出 Claude `accept`。

降级标注约定：
- `Claude pass unavailable`：用于 INIT / ANALYSIS 等通用 Claude 协作不可用场景。
- `Claude review unavailable`：仅用于 REVIEW 阶段 Claude review 不可用场景。

---

## 渐进式加载

联合模式只在命中触发后读取本文件。之后按阶段加载 With Claude 的最小必要文件：

| 阶段 | 加载 With Claude 文件 |
|---|---|
| INIT / ANALYSIS | `flows/common-contract.md`、`flows/task-packet.md`、`flows/readonly-analysis.md` |
| REVIEW | `flows/common-contract.md`、`flows/task-packet.md`、`flows/post-implementation-review.md` |

不得把 With Claude 的全部 flow 常驻复制进 Easy Coding 主流程。
Easy Coding 联合模式的 ANALYSIS 固定使用 With Claude `readonly_analysis` flow；即使当前宿主环境处于 Plan Mode，也不得改用 `plan_mode`。

---

## Claude Worker 调用

默认调用方式：

```bash
python3 -B /Users/ysxiiun/.codex/skills/with-claude/scripts/run_claude_worker.py --cwd "$PWD" < task-packet-stdin
```

若全局安装路径不可用，可退回到源仓库路径 `/Users/ysxiiun/Documents/agent-skill/with-claude/scripts/run_claude_worker.py`；无论使用哪个路径，都必须保持同等只读约束。

任务包必须包含：

```json
{
  "user_request": "",
  "cwd": "",
  "expected_output_type": "analysis | review",
  "workflow_type": "readonly_analysis | post_implementation_review",
  "phase": "init_draft | analysis | post_code_review",
  "constraints": [
    "Claude worker is read-only.",
    "Claude must not mutate repository files.",
    "Host agent owns final judgment and all writes."
  ],
  "known_context": [],
  "add_read_dirs": [],
  "readonly_policy": {
    "mutation_allowed": false,
    "allowed_tools": ["Read", "Grep", "Glob", "LS"]
  }
}
```

`add_read_dirs` 只能使用精确、窄范围目录；禁止 `/`、`$HOME`、`/Users`、`/Users/<user>` 等宽目录。

---

## INIT 协作

适用场景：

- `interactive_init`：迭代项目 `.easy-coding/` 资产不完整，用户确认初始化。
- `post_v1_auto_init`：初创项目首次任务为先交付第一版而跳过前置 INIT 时，第一版完成后自动执行初始化资产回补。

执行方式：

1. host agent 先按 `flow/init.md` 完成项目只读扫描。
2. 对 SOUL、RULES、ABSTRACT 的草拟，可调用 Claude 做只读分析。
3. Claude 输出只作为草稿和风险提醒。
4. host agent 必须合并项目现状、Spec、Prototype、记忆和 Claude 建议。
5. 初始化文件写入仍由 host agent 执行。

INIT 输出必须补充：

```markdown
### Claude 初始化协作
- Claude 状态：{done / blocked；若 blocked，写 Claude pass unavailable}
- Claude 草拟要点：{SOUL / RULES / ABSTRACT 的建议摘要}
- 采纳情况：{已采纳 / 部分采纳 / 未采纳}
- 冲突摘要：{若无则写“无”}
```

---

## ANALYSIS 协作

固定使用 With Claude 的 `readonly_analysis` flow，任务包固定为 `workflow_type=readonly_analysis`、`phase=analysis`、`expected_output_type=analysis`。

不得使用 With Claude 的 `plan_mode` flow 承载 Easy Coding ANALYSIS；不得输出 `[阶段：PLAN]`；不得把 `workflow_type` / `phase` 当作 Easy Coding 阶段。

执行方式：

1. host agent 完成 Easy Coding 既有只读上下文采集。
2. 构建 Claude 只读任务包，包含用户需求、当前项目模式、已读文件摘要、候选 Dev-Spec 状态、冲突点和待决策点；若命中 Canonical Spec，必须携带 `spec_id`、`source_digest`、`selected_task_ids`、`repo_ids`、`dependency_summary` 和 `scope_digest`。
3. Claude 运行期间，所有用户可见进度更新都保持 `[阶段：ANALYSIS]`。
4. 等待 Claude 时只能输出 Claude 协作进展、当前已读证据和等待最终 contract 的状态；不得提前输出正式技术方案，也不得进入 `WAITING_CONFIRM`。
5. Claude 返回六字段 worker contract 后，host agent 合并结果，输出 Easy Coding 的 ANALYSIS 方案。
6. 方案必须遵循 `SKILL.md` 2.5 的“核心必填 + 条件展开”模板，并包含 `### Claude 协作` 条件章节。

Canonical Spec 附加门禁：

- 只向 Claude 提供 `scripts/inspect_dev_spec.py` 生成的消费闭包，不传未选 task 正文。
- `add_read_dirs` 只允许选中 repo 的必要代码目录，不得用 Spec 所在父目录扩大读取范围。
- Host 与 Claude packet 必须记录相同 `source_sha256` 和 `scope_sha256`；任一 digest 不一致时丢弃 worker 结果并重新构造 packet。
- Claude 返回未选仓库文件、符号、调用链或实施步骤时，丢弃越界部分，并在 `### Claude 协作` 中记录越界。

如果 Claude 返回 `needs_user_input`，host agent 必须把 Claude 问题与 Easy Coding 自身问题去重后一次性问用户。

如果 Claude 返回 `blocked`，host agent 继续完成方案，但在 `### Claude 协作` 中标注 `Claude pass unavailable`。

---

## IMPLEMENT 边界

IMPLEMENT 阶段不调用 Claude。

host agent 必须：

1. 按用户已确认的 Easy Coding 方案实施。
2. 严格遵守改动范围、文件编码、注释策略和验证要求。
3. 变更范围扩大时回到 ANALYSIS / WAITING_CONFIRM。
4. 实施完成后进入 REVIEW，而不是直接进入记忆阶段。
5. Canonical task 只能修改已确认的 `change_ids` path/symbols，并按 `step_ids` 与 `test_ids` 执行；Claude 不参与 IMPLEMENT。

---

## REVIEW 协作

REVIEW 使用 With Claude 的 `post_implementation_review` flow。

仅当 IMPLEMENT 已完成，且已有用户已确认方案、变更文件清单、变更摘要、验证结果和 host 自检结论时，才允许进入 REVIEW。分析等待、方案合并、方案修订和等待用户确认都不得使用 REVIEW。

REVIEW 必须按以下闭环执行：

1. 构造 `workflow_type=post_implementation_review`、`phase=post_code_review`、`expected_output_type=review` 的 task packet。
2. 启动或尝试启动 `run_claude_worker.py`；优先使用全局安装路径，失败时才使用源仓库 fallback。
3. 等待 Claude final worker contract，并记录调用状态、wrapper path、final contract 接收状态和 worker status。
4. host agent 只能在 `Claude 调用状态=executed` 且 `final contract=received` 时合并 Claude `accept` / `fix` / `replan` verdict。
5. 若未执行、启动失败、被阻断或未收到 final contract，REVIEW 只能映射为 `blocked`，标注 `Claude review unavailable`，并把 host self-review 作为降级说明，不能伪造成 Claude verdict。
6. Canonical Spec 场景下，review packet 继续携带已确认的 task/change/test ID、`source_digest` 和 `scope_digest`；review 不得借机扩大实现范围。

任务包必须包含：

```json
{
  "workflow_type": "post_implementation_review",
  "phase": "post_code_review",
  "expected_output_type": "review",
  "implementation_context": {
    "approved_plan": "",
    "change_summary": "",
    "changed_files": [],
    "test_results": [],
    "host_self_check": "",
    "diff_summary": ""
  },
  "review_scope": {
    "focus": [],
    "diff_summary": ""
  },
  "readonly_policy": {
    "mutation_allowed": false,
    "allowed_tools": ["Read", "Grep", "Glob", "LS"]
  }
}
```

### Verdict 处理

| verdict | 处理方式 |
|---|---|
| `accept` | 结束 REVIEW，在实施结果报告中说明 review 通过 |
| `fix` | 若仍在已确认方案范围内，由 host 修复并重新 review |
| `replan` | 不自动重走方案分析，在实施结果报告中说明建议重新规划，等待用户指令 |
| `blocked` | 不是 Claude verdict，而是 `worker.status=blocked` 的 host 降级映射；降级为 host self-review，并标注 `Claude review unavailable` |

REVIEW 最多 3 轮。

若 3 轮仍未收敛：

1. 立即结束 REVIEW。
2. 不新增任何额外阶段。
3. 不自动重走方案分析。
4. 在实施结果报告中说明：
   - 已执行 review 轮次
   - 已修复内容
   - 剩余未收敛问题
   - 风险与建议
5. 等待用户进一步指令。

---

## 最终报告要求

联合模式下，IMPLEMENT 完成报告必须额外包含：

```markdown
### Easy Coding With Claude Review 结论
- Claude 可用性：{可用 / unavailable}
- Claude 调用状态：{executed / blocked / not_executed}
- wrapper path：{实际使用或尝试使用的 run_claude_worker.py 路径}
- workflow_type：post_implementation_review
- final contract：{received / not_received}
- worker status：{done / needs_user_input / blocked / unavailable}
- delegated reviewer：{started / skipped: 原因 / blocked: 原因 / unavailable}
- Review 轮次：{N}/3
- verdict 来源：{Claude final contract / blocked fallback(host self-review)}
- 最终 verdict：{accept / fix(未收敛，host 派生) / replan / blocked(worker.status 降级)}
- 已采纳并修复：{列表；无则写“无”}
- 未采纳：{列表；无则写“无”}
- 剩余问题：{列表；无则写“无”}
- 风险说明：{列表；无则写“无”}
```

实施结果报告输出后，当前流程处于“等待实施结果确认”的续流状态，必须停止等待用户确认；同一轮不得生成短期记忆、不得执行长期记忆沉淀、不得输出 COMPLETE。

Claude review 的 `accept`、host 自检通过、测试通过、构建通过都不等于用户确认实施结果。

若当前 agent 暴露 `request_user_input` 或等价原生选择工具，实施结果报告后必须调用工具等待“确认结果”；若当前 agent 不支持原生选择工具，才使用文本兜底确认。

用户确认实施结果后，再按项目模式进入后续流程：

- 初创项目：仅当首次任务跳过了前置 INIT 时，执行 `post_v1_auto_init` 初始化资产回补，然后进入 `MEMORY_SHORT → MEMORY_LONG → COMPLETE`
- 迭代项目：直接进入 `MEMORY_SHORT → MEMORY_LONG → COMPLETE`

不得因为上一阶段是 REVIEW，就在用户确认结果后停留在 REVIEW、只输出普通确认回复，或要求用户再次显式触发 Easy Coding。
