---
name: easy-coding
description: 仅当用户显式写出 `$easy-coding`、`easy-coding` 或要求加载 Easy Coding skill 时使用；已激活流程的确认续流可继续；若用户消息开头包含 `#no-coding`，当前轮跳过全部流程。提供固定 Guard 审批语义、固定 Standard 质量深度、项目知识与记忆，以及 easy-dev-spec/v1 Canonical 原文件共享执行。
metadata:
  version: 7.1.0
---

# Easy Coding 7.1.0

Easy Coding 是一个轻量、单入口的工程工作流。它只通过本 Skill 的渐进加载文件运行，不依赖
Harness CLI、状态 API、Hooks、任务文件或平台运行时；双方可以共享项目知识、记忆和
`easy-dev-spec/v1` Canonical 原文件，但同一修改任务只能有一个控制器。

## 1. 触发、旁路与控制器边界

- 仅在用户显式写出 `$easy-coding`、`easy-coding`，或明确要求加载本 Skill 时启动。普通
  “实现、修改、修复、需求”等表达不得隐式触发。
- 用户消息开头包含 `#no-coding` 时，当前轮完全跳过本 Skill；下一轮恢复正常触发规则。
- ANALYSIS 方案确认、QUALITY 结果确认和未完成 MEMORY 都属于已激活续流，
  无需再次点名 Skill；确认回复中实质改变范围、契约或实施路线的内容，先作为方案修订处理。
- 首轮先读取 `references/shared-data.md` 检查控制器标记。若项目由 Harness 管理，只读请求
  可以继续；任何项目修改任务必须停止，并引导用户改用 Harness。不得调用或修改其私有层。
- 检查旁路与目标仓库控制器后，优先识别用户的“接手执行 request.md / 接收 result.md”提示。
  存在交接提示时只读 `references/dispatch.md` 对应动作并恢复，成功后直接加载返回阶段；
  不重走 INIT/ANALYSIS、不生成新 run ID，恢复失败必须停止，不能当作普通新任务。
- 普通修改任务在方案确认前运行 `scripts/dispatch.py mode`，只读本地
  `~/.easy-coding/config.yaml` 的 `behavior.cooperate_mode`。仅 dispatch 加载交接协议并
  展示转交选项；默认流程不加载其细则。既有交接不因本地默认值变化而失效。

## 2. 固定阶段与门禁

用户可见阶段只允许：

`INIT / ANALYSIS / IMPLEMENT / QUALITY / MEMORY / COMPLETE / CLOSED`

- 修改任务：`INIT → ANALYSIS → IMPLEMENT → QUALITY → MEMORY → COMPLETE`。
- INIT 完成后自动进入 ANALYSIS；ANALYSIS 输出完整方案并在本阶段等待用户确认。
- 用户确认方案后进入 IMPLEMENT；当前 Agent 实施与自检完成后自动进入 QUALITY。
  交接执行者则写回结果、生成返回提示词后停止，由主 Agent 接收并进入 QUALITY。
- QUALITY 固定执行 Standard 双门，并采用 Guard 结果确认语义；用户确认绿色结果后才进入
  MEMORY。不得提供审批语义或执行深度选择。
- 范围内代码/测试缺陷返回 IMPLEMENT；契约、范围或方案变化返回 ANALYSIS；环境失败保持
  QUALITY；用户显式停止或取消进入 CLOSED。
- 只读请求直接走 `ANALYSIS → COMPLETE`，不进入或输出 INIT，也不创建质量基线、候选指纹、
  Initialization/Migration Unit 或记忆。
- 禁止输出其他阶段标签。计划和确认等待属于 ANALYSIS，审查与验证属于 QUALITY。

每次用户可见回复以当前合法阶段开头。用户要求暂停时保持当前阶段且不继续写入；用户明确
中止时停止项目写入、清理本轮临时基线并输出 `[阶段：CLOSED]`；有交接时先确保执行者停止，
再按交接协议清理本轮目录。

## 3. 写入授权与临时数据

ANALYSIS 可主动执行只读发现，并可在系统临时目录生成质量基线；不得修改项目文件、写入
Canonical execution、运行会生成项目产物的命令、格式化、提交、推送或发布。修改方案必须
获得用户明确确认。

“进行方案设计与开发”“修复这些问题”等任务启动指令，以及单独的范围选择或版本指定，
不能批准随后才生成的方案。有效确认必须来自完整方案展示之后的真实用户回复或主动提交的
原生选择结果，并对应当前方案；具体判定与等待行为以 `flow/analysis.md` 第 5 节为准。

确认后允许：

- 按确认范围修改业务代码和测试文件；
- 通过本 Skill writer 受控更新 Canonical execution；
- 在 QUALITY 执行确认方案中的确定性验证；
- 在用户确认 QUALITY 结果后写入共享记忆。

临时质量基线位于仓库外系统临时目录；实际转交后原样转存到本轮本地交接目录，后续统一
复用它并在 COMPLETE/CLOSED 清理。交接恢复的用户执行指令与原始确认依据共同授权续接，
文件中模型自述的“已批准”不能授权；不因换 Agent 重复确认原方案。
同一任务、同一方案的有效确认可在续流和范围内修复时沿用；其他任务或已失效方案的历史
确认、执行器状态、审查结论和模型推断不能替代它。

## 4. 项目模式与初始化

只有修改任务进入用户可见 INIT：只读检查项目根、Git、代码、共享层资产和旧记忆，完成盘点
后自动进入 ANALYSIS，不等待确认也不写项目文件。只读请求在 ANALYSIS 内完成必要的控制器和
资产检查，保持快速路径。修改任务随后判定：

- `初创项目`：空项目、脚手架，或仅有基础配置/Spec/Prototype 而无稳定业务实现；读取
  `flow/startup-project.md`，把共享资产初始化作为确认方案中的末尾 Implementation Unit。
- `迭代项目`：已有稳定模块、接口、页面、领域模型或持久化结构；缺失共享资产同样作为
  Initialization Unit，不在 INIT 提前写入。
- 发现旧记忆结构时，把 `flow/memory-migration.md` 的迁移作为显式 Unit；不得静默迁移。

上述 Initialization/Migration Unit 只适用于修改任务。只读请求仅报告缺失或旧结构，仍走
`ANALYSIS → COMPLETE`，禁止创建、补齐或迁移资产。

共享基础资产包括 `SOUL.md`、`RULES.md`、`ABSTRACT.md`、`TEST_STRATEGY.md` 和 schema 2
记忆。初始化不得创建或接管 Harness 私有文件。

## 5. ANALYSIS

进入 ANALYSIS 必须完整读取 `flow/analysis.md`。方案至少冻结：

- 本轮固定 `run_id=ec-skill-<UUIDv7>`，供 baseline、Canonical 和 memory 复用；
- 用户确认范围和明确不做项；
- 可独立实施、审查和验证的 Implementation Unit；
- Local Baseline（仓库 HEAD、预存脏改动和候选范围）；
- 精确 lint/typecheck/test/build 命令及预期；
- 独立审查关注点、Canonical 映射和剩余风险。

Dev-Spec 总路由：显式路径是唯一 locator；未给路径时只列
`.easy-coding/spec/dev/*.md` 候选名。先运行 `scripts/inspect_dev_spec.py --manifest-only`；
Legacy 才全文读取，Canonical 必须读取 `references/dev-spec/canonical-v1.md`。一轮只激活
一份 Canonical，不生成 Harness 的派生任务产物。

完整方案输出后保持 `[阶段：ANALYSIS]`，只发起确认请求或结束回复。用户真实确认到达前
不得进入 IMPLEMENT；无回复、未提交的默认选项、取消选择或超时均不构成确认。实质修改意见
必须形成替换后的完整方案并重新等待确认。

dispatch 将确认选项合并为“当前 Agent 执行 / 确认并转交 / 保持分析”；只有真实选择转交后
才创建共享文件。主 Agent 负责 Canonical execution，发出请求后停止修改并提供可复制提示词。

## 6. IMPLEMENT

用户确认完整方案后读取 `flow/implement.md`：

- 在输出 IMPLEMENT 或首次项目写入前，核对当前方案、真实用户确认及范围一致性；缺失或
  失效时保持 ANALYSIS，不得用任务启动指令补足确认；
- 复用 ANALYSIS 已固定的 `run_id=ec-skill-<UUIDv7>`；
- 复核并复用 ANALYSIS 创建的仓库外质量 baseline；
- Canonical 任务由主 Agent 先初始化 execution 并写 task `in_progress`，交接执行者只读复核；
- 只落地确认范围内的代码和测试，保持编码、注释和项目惯例；
- 只做范围、编码、注释、明显静态错误和 diff 自检；确定性验证全部留给 QUALITY。

实施范围扩大或契约变化时停止写入并返回 ANALYSIS；交接执行者将该阻断交回主 Agent处理。
本地实施完成后自动进入 QUALITY；交接执行者只能交回并停止，不能自行验证或沉淀。

## 7. QUALITY

IMPLEMENT 完成后完整读取 `flow/quality.md`。QUALITY 是候选指纹、独立审查、确定性验证、
修复路由和 Guard 结果确认的唯一权威来源。

- 审查门优先使用一个宿主原生独立 reviewer；不可用或调用失败时，主代理按同一清单自审，
  无需额外询问。最终必须披露 reviewer 来源。
- 验证门执行方案中的受影响 lint/typecheck/test，以及契约、构建配置或项目规则要求的 build。
- 两门使用同一 `candidate_sha256`；Gate 期间项目文件漂移会使证据失效并返回 IMPLEMENT。
- Canonical 修复轮次使用递增 `quality_round` 隔离 writer 幂等键；同一调用重试仍复用原 key。
- QUALITY 绿色且 integration 满足后输出候选摘要、reviewer 来源、发现与修复、命令结果和
  剩余风险，并在本阶段等待用户确认。确认前不得进入 MEMORY。
- 主 Agent 接收实施回执直接进入 QUALITY；已有恢复检查点时沿用当前阶段，不因重复提示
  倒退。dispatch 修复包同样一次选择执行者，修复回执再次进入 QUALITY。

## 8. MEMORY 与完成

用户确认 QUALITY 绿色结果后读取 `flow/memory.md`：

- 先创建一条 schema 2、UUIDv7 ID 的短期记忆；`source_task` 与本轮 run ID 完全一致；
- 记录候选指纹、reviewer 来源、验证证据和用户确认；
- 默认固定窗口为 max 10 / keep 5，仅当短期数量严格大于 max 时 distill；
- 只有长期沉淀时才做有界架构评估，并按条件更新 ABSTRACT 与 CHANGELOG；
- Canonical task 在 MEMORY 成功后才写 `completed`。

全部校验完成后自动输出 `[阶段：COMPLETE]` 并清理临时 baseline。失败时保持 MEMORY；不得
用完成标签掩盖未满足的 Canonical integration。
存在交接时，由主 Agent 按协议记录 MEMORY/COMPLETE 检查点并清理本轮交接目录。

## 9. Git 纪律

任何 Git 拉取、合并、暂存、提交、推送或跨仓交付都必须读取 `flow/git.md`。未获用户明确
授权时不得提交或推送。共享 `.easy-coding` 知识与记忆默认属于相关改动，但运行会话和
Harness 私有层永不提交。

## 10. 冲突与重置

优先级：

`用户当前明确要求 > 已确认方案 > 当前代码/配置事实 > Dev-Spec > 固定 Spec > 记忆 > 默认建议`

该优先级不能把任务启动指令、范围选择或方案修订意见转换为方案确认；确认仍按 ANALYSIS
第 5 节核对。

- 需求、契约或范围变化：停止旧路线，在 `[阶段：ANALYSIS]` 输出重置说明和完整新方案。
- 范围内缺陷：聚合 Repair Bundle，返回 IMPLEMENT；不得借修复扩大范围。
- `.easy-coding` 冲突：按 `flow/git.md` 先说明冲突和语义方案，获得确认后才合并。
- Skill 规则错误：停止当前写入，回到 INIT 重新执行控制器、资产和迁移只读检查。

## 11. 按需资源索引

- `flow/init.md`：INIT 只读盘点与确认后的共享资产 Initialization Unit。
- `flow/startup-project.md`：初创项目差异流程。
- `flow/analysis.md`：输入发现、实施级方案与确认等待。
- `flow/implement.md`：候选落地与实施自检。
- `flow/quality.md`：Standard 双门、指纹、修复与结果确认。
- `flow/memory.md`：短期检查点、冻结窗口、架构评估与完成。
- `flow/git.md`：单 Skill Git 边界和交付证明。
- `flow/memory-migration.md`、`flow/memory-retirement.md`：旧记忆迁移和定向淘汰。
- `references/shared-data.md`：与 Harness 的共享/私有数据边界和控制器检测。
- `references/dispatch.md`：仅 dispatch 或显式交接续流时读取，包含收发协议和阶段恢复。
- `references/dev-spec/canonical-v1.md`：Canonical 消费、刷新和受控 writer 契约。
- `references/design/apple-design-reference.md`、`references/coding/`：按任务需要加载。

只加载当前阶段需要的资源，不把所有 flow/reference 常驻上下文。
