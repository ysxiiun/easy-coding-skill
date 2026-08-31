# ANALYSIS：输入、方案与确认

> 进入 ANALYSIS 时完整读取。本文件是输入发现、实施级方案和方案确认的唯一权威来源。

## 1. 输入与控制器检查

1. 先读取 `references/shared-data.md`。检测到 Harness 管理标记时，只读请求可继续；修改任务
   立即停止并引导使用 Harness。
2. 读取用户需求、显式文件、截图、链接和已确认决定。
3. 读取真实代码、构建配置、直接调用链和相关测试。
4. 按需读取共享 `SOUL.md`、`RULES.md`、`ABSTRACT.md`、`TEST_STRATEGY.md`、长期索引、
   命中主题及全部有效短期记忆。
5. 读取固定 Spec、Prototype 和用户选择的 Dev-Spec；Prototype 只用于理解，不直接成为
   生产实现。
6. 记录每个目标仓库 HEAD、预存 staged/unstaged/untracked 状态、文件编码和构建入口。

修改任务中，INIT 盘点出的缺失共享资产必须形成明确 Initialization Unit；旧记忆必须形成
Migration Unit，并引用 `flow/init.md` / `flow/memory-migration.md`。这些 Unit 与业务改动一起
由本方案确认，不能在 INIT 提前写入，也不能推迟到 QUALITY 之后。只读请求只报告资产状态，
不得创建这些 Unit，保持 `ANALYSIS → COMPLETE`。

显式 Dev-Spec 路径是唯一 locator；未显式给出时只列 `.easy-coding/spec/dev/*.md` 名称，
用户选择前不读正文。选定后先运行 `scripts/inspect_dev_spec.py --manifest-only`：Legacy 才
全文读取；Canonical 按 `references/dev-spec/canonical-v1.md` 冻结唯一消费闭包。非法协议、
未来 schema、仓库零匹配或 baseline 不可用必须停止，不能降级。

## 2. 清晰度与冲突

- 检查目标场景、输入输出、任务边界、涉及模块、性能/安全/兼容约束。可从代码发现的事实
  先自行检查；只有未知项会实质改变路线且无法推导时才询问。
- 已有实现必须追到真实文件、直接调用链和测试；不存在时明确写“空项目/脚手架”。
- 提示词、Spec、代码和记忆有冲突时，列出差异、影响与建议，等待用户决策。
- 不添加没有依据的兼容、兜底、重试、迁移或一次性抽象。
- Canonical 只生成一份 task/Step/change/Test 实施投影，不叠加第二套普通设计。

## 3. Implementation Unit 与 Local Baseline

修改任务必须拆成一个或多个可独立落地的 Implementation Unit。每个 Unit 包含：

- 目标行为和明确不做项；
- 精确文件、符号和测试范围；
- 前置依赖、输入输出和完成条件；
- 对应验证命令与 reviewer 关注点。

修改任务进入本节时先生成一次 `run_id=ec-skill-<UUIDv7>` 并冻结到当前需求；baseline 文件名、
Canonical writer 事件和短期记忆必须复用它。方案修订保持同一 run ID；方案被重置、任务中止或
结束时才释放。只读请求不生成 run ID 或 baseline。

Canonical 修改任务同时冻结 `quality_round=1`，只用于区分同一 run 内不同候选/修复轮次的
writer 幂等命名空间，不是审批模式或执行深度配置。每次 Repair Bundle，或 execution 已初始化
后因契约/方案重置而恢复修改时，必须先递增 round；普通 CAS 重试不得递增。

Local Baseline 必须列出：

- `repo_id → Git root → HEAD`；
- 方案前已存在的 staged/unstaged/untracked 路径，或“干净”；
- 允许候选范围 `repo_id:path`；
- 只允许机器写回的 ignore 路径，例如位于目标 repo 内的 Canonical locator；repo 外 locator
  只记录绝对路径和 writer/CAS 证据，不传给 fingerprint；
- 在方案输出前执行 `quality_fingerprint.py baseline`，并记录仓库外临时输出位置。

父仓存在脏 gitlink，或本轮会修改 submodule 时，必须把已检出的子仓 Git root 作为独立
`--repo` 纳入并配置自身 scope；只传父仓会被指纹脚本拒绝，不能用父仓目录状态代替子仓内容。
未跟踪的 nested Git repo 同样必须独立纳入；普通父仓目录条目不能证明其内部状态。

预存无关脏改动不是候选；相对 baseline 未变化时不得阻断。方案重置或替换时清理旧 baseline
并重新生成。任何目标 HEAD 或预存状态在确认前发生变化，都必须刷新方案事实，不能静默吸收。

## 4. 方案模板

```markdown
[阶段：ANALYSIS]

## 技术方案：{任务标题}

### 任务边界
- 项目模式：{startup / iteration}
- 任务类型：{feature / bugfix / refactor / perf / frontend / doc / workflow}
- 目标与输出：{最小完整结果}
- 确认范围：{模块、行为、文件}
- 明确不做：{边界}

### 现状与证据
- 当前实现：{真实链路}
- 缺口与原因：{问题}
- 证据：{file:line / 命令 / 配置}
- 冲突与待决策：{无或差异、影响、建议}

### Implementation Units
| Unit | 文件/符号 | 行为改动 | 完成条件 |
| --- | --- | --- | --- |
| U1 | `{path}:{symbol}` | {改动} | {条件} |

### 改动范围
| 文件 | 类型 | 编码 | 核心改动 |
| --- | --- | --- | --- |
| `{path}` | 新增/修改/删除 | {依据} | {内容} |

### Local Baseline
- 仓库与 HEAD：{repo_id / root / HEAD}
- 预存脏改动：{路径或干净}
- 候选范围：{repo_id:path}
- 机器 ignore：{路径或无}
- 临时 baseline：{系统临时路径与生成命令}

### 实施方案
1. {Unit、文件/符号、依赖和改法}
- 编码与注释：{保持策略与必要注释}
- Canonical：{不适用或 task/Step/change/Test/integration 映射}

### QUALITY 计划
- 审查关注点：{行为、边界、回归、测试有效性、规则符合性}
- lint/typecheck：{精确命令或不适用及依据}
- test：{精确受影响命令与预期}
- build：{契约/配置/项目规则要求的命令，或不适用及依据}
- 人工验收：{用户可观察结果}

### 风险与剩余限制
- {风险、环境限制和缓解}
```

前端任务补充页面、组件、状态、数据、接口和 mock 退出条件；Canonical 任务补充 locator、
身份摘要、baseline、execution/依赖、Test 证据和 integration 门禁。

## 5. 方案确认

完整方案输出后保持 `[阶段：ANALYSIS]` 并停止：

```text
技术方案已完成。确认后才会修改项目文件、写入 Canonical execution 或执行会生成项目产物的命令。
```

运行时有原生选择工具时提供“确认执行方案（推荐）”和“保持分析”；自由修改意见由 free-form
输入承接。用户提出修改时输出改动提要和替换后的完整方案，再次等待确认。确认后直接进入
IMPLEMENT。
