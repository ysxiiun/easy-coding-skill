---
name: easy-coding
description: 仅当用户显式写出 `$easy-coding`、`easy-coding` 或要求加载 Easy Coding skill 时使用；已激活流程的确认续流可继续；若用户消息开头包含 `#no-coding`，当前轮跳过 skill 全部流程与约束。Spec 驱动的人机共创编程助手，支持固定阶段状态机、项目记忆、初创/迭代项目和 With Claude 联合模式。
metadata:
  version: 5.0.0
---

# 🔴 核心约束（每轮对话必须遵守）

## 显式加载规则

- 本 skill 只能由用户显式点名加载：`$easy-coding`、`easy-coding`，或清楚表达“加载/使用 Easy Coding skill”
- 不得因为用户说“帮我实现”“帮我修改”“帮我修复”“我有一个需求”“ec”等普通任务提示而自动进入本 skill
- 如果用户没有显式点名，且不属于下方“已激活流程续流例外”，本 skill 的阶段、阻断、记忆和初始化流程都不应生效
- `#no-coding` 仅用于用户已经显式加载本 skill 后，临时跳过当前轮 skill 流程

## 已激活流程续流例外

以下情况不属于“隐式触发”，而是上一轮 Easy Coding 状态机的继续；即使用户没有再次写 `$easy-coding`，也必须继续当前流程：

- 上一轮停在 `WAITING_CONFIRM`，用户回复“确认 / ok / 开始 / 没问题”或点选“确认执行方案” → 进入 `IMPLEMENT`
- 上一轮停在 `INIT` 的旧版记忆迁移确认，用户回复“确认 / ok / 开始 / 没问题”或点选“确认迁移” → 执行 `flow/memory-migration.md`，迁移完成后自动进入 `ANALYSIS`
- 上一轮已输出实施结果报告并等待确认，用户回复“确认 / ok / 没问题 / 确认结果”或点选“确认结果” → 进入实施后续流转
- 上一轮已经开始 `MEMORY` / 初创项目初始化资产回补，但尚未输出 `COMPLETE` → 继续直到 `COMPLETE`

实施后续流转必须按项目模式执行：

- 初创项目：仅当首次任务为先交付第一版而跳过了前置 INIT 时，执行初始化资产回补 → `MEMORY` → `COMPLETE`
- 迭代项目：直接执行 `MEMORY` → `COMPLETE`

若用户在续流确认中提出新的修改意见，必须停止后续流转，回到对应方案或变更确认流程。

## 阶段标签硬门

Easy Coding 用户可见阶段标签只能从以下集合中选择：

`INIT / ANALYSIS / WAITING_CONFIRM / IMPLEMENT / REVIEW / MEMORY / COMPLETE`

强制规则：

- 每次输出 `[阶段：X]` 前，必须先检查 `X` 是否在合法集合内。
- 若 `X` 不在合法集合内，必须改写为最近的合法阶段；不得输出未知阶段。
- 禁止输出 `[阶段：PLAN]`、`[阶段：VERIFY]`、`[阶段：TEST]`、`[阶段：DONE]`、`[阶段：REVIEW_BLOCKED]`。
- 验证、测试、构建、diff 检查、编码自检、注释自检都属于 `IMPLEMENT` 内部工作，不是独立阶段。
- Claude worker 的 `phase` / `workflow_type` / `expected_output_type` / `status` / `verdict` 不是 Easy Coding 阶段；`done` / `accept` 不能映射为 `[阶段：DONE]`。
- 任务完成只能使用 `[阶段：COMPLETE]`。

## Easy Coding With Claude 联合模式

仅当用户在同一轮请求中同时显式引用 Easy Coding 与 With Claude 时启用联合模式。

触发条件：
- Easy Coding 显式触发：`$easy-coding`、`easy-coding`，或清楚表达“加载/使用 Easy Coding skill”
- With Claude 显式触发：`$with-claude`、`with-claude`，或清楚表达“加载/使用 With Claude skill”
- 两者必须同时成立；仅命中其中一个时，不启用联合模式
- 不支持 `$easy-coding+with-claude`、`ec+wc` 等未定义速记触发
- `#no-coding` 优先级最高；若命中 `#no-coding`，联合模式同样跳过

命中联合模式时，必须在本轮第一条阶段输出前明确展示：

```markdown
已启动: Easy Coding With Claude 模式
```

联合模式执行规则：
- 立即按需读取 `flow/with-claude.md`
- `INIT`：如需要初始化，Claude 仅作为只读顾问参与 SOUL / RULES / ABSTRACT 草拟，host agent 负责合并和写入
- `ANALYSIS`：Claude 参与方案分析，但 Easy Coding 阶段仍固定为 `ANALYSIS`；分析结果必须按 2.5 完整方案模板输出，并写明 Claude 观点与采纳情况
- `IMPLEMENT`：只由本地 host agent 执行，不调用 Claude 写代码或参与实施
- `REVIEW`：仅在 IMPLEMENT 完成，且已有变更文件清单、验证结果和 host 自检结论后实际调用 Claude 只读 review；不得用 host 自检冒充 Claude verdict；若需要修复，由 host agent 在已确认范围内修复并重新 review
- `REVIEW` 最多 3 轮；3 轮仍未收敛时，结束 review，在实施结果报告中说明剩余问题、已修复内容与风险，等待用户进一步指令
- Claude 不可用时允许降级为 host-only 流程，但必须在分析或最终报告中明确标注 `Claude pass unavailable`；REVIEW 阶段必须标注 `Claude review unavailable`

## `#no-coding` 单轮旁路规则

**优先级最高，先于所有显式加载后的阶段判断、工具阻断检查执行。**

- 若用户消息在开头写入 `#no-coding`，则当前轮立即退出 easy-coding 模式
- 当前轮完全跳过 easy-coding 的全部约束与流程，包括但不限于：
  - 阶段标注 `[阶段：XXXX]`
  - INIT / ANALYSIS / WAITING_CONFIRM / IMPLEMENT / REVIEW / MEMORY / COMPLETE
  - 方案确认阻断
  - 记忆写入与流程重置规则
  - 项目模式判定与 Spec 读取规则
- `#no-coding` 仅对当前轮生效，下一轮恢复正常触发逻辑
- 判定条件为“用户消息开头包含 `#no-coding`”；若仅在正文中出现，不触发旁路

**命中 `#no-coding` 时的处理要求：**
- 不引用本 skill 的流程规范约束当前轮行为
- 直接按普通 agent 模式理解并处理用户请求
- 不输出“当前阶段禁止执行”之类的 skill 阻断文案

## 原生确认能力探测

需要用户选择、确认、加载候选、确认写入、确认执行或确认结果时，必须先判断当前 agent 是否暴露 `request_user_input` 或等价原生选择工具。

- 若当前可用工具中存在 `request_user_input` 或等价原生选择工具：必须调用该工具，不得只输出文本确认提示。
- 若当前 agent 没有暴露该工具：使用文本兜底确认，不得声称已经展示原生选择框。
- 工具可用性只看当前运行时实际暴露的工具，不按 Codex / Claude / 其他 agent 名称猜测。
- 原生选择框每次最多 3 个问题；每题提供 2-3 个互斥选项，推荐项放第一位，并在 label 末尾标注 `(Recommended)`。
- 每个选项必须映射到真实下游分支，不得为了凑满选项而添加低价值按钮。
- 客户端会自动提供 free-form Other；修改意见、补充说明、反馈意见、自由输入、以及旧式第四补充项都必须交给该入口承接，不要手写成选项。
- 确认类场景若只有一个主动作，原生选择框只提供“确认项 + 保持等待/安全否决项”；后者仅表达不推进当前流程，不承接反馈意见。
- 如果原本需要 `A/B/C/D` 四个业务选项，在不影响效率时压缩为 2-3 个真实业务分支 + 原生 free-form Other；如果 4 个业务分支都不可压缩，先用原生选择框呈现最高价值的 2-3 个分支，再用文本兜底展开剩余分支。
- Dev-Spec 选择必须先输出完整编号清单；原生选择框可用时仍必须调用工具，但部分加载和多选统一交给客户端 free-form Other 输入编号，例如 `1,3` 或 `1-3`。
- 高风险操作确认仍保留安全语义：只有用户点选“确认写入/确认执行”等明确确认项，或文本回复既有确认词，才视为确认。

> 违反以下任何一条 = 任务失败

| 约束 | 违反示例 | 正确做法 |
|------|---------|---------|
| 禁止跳步 | 分析完需求直接写代码 | 必须按阶段顺序执行 |
| 方案未确认禁止执行 | 用户说"确认"前直接修改代码 | 输出 `[阶段：WAITING_CONFIRM]` 阻断等待 |
| 无论变更大小必须确认 | 以"改动很小"为由直接修改 | 即使改一个变量名也要出方案等待确认 |
| 每次回复必须标注合法阶段 | 直接输出方案，或输出未定义阶段 | 用合法集合中的 `[阶段：XXXX]` 开头 |
| 禁止自动推进 | 多轮讨论后未等用户确认就执行 | 必须等待用户明确说"确认/ok/开始" |

---

# ⚠️ 工具使用边界与阻断检查（执行任何操作前必须检查）

**若当前轮命中 `#no-coding`，本节全部失效，直接跳过。**

## 操作类型定义

### 只读上下文采集（允许且必要）

只读上下文采集指不会改变项目文件、工作区、依赖、缓存、构建产物或远端状态的读取 / 扫描 / 检索 / 对比操作，例如：

- 扫描目录结构、列出文件名、读取文件正文、查看配置、查看文件编码
- 使用 `rg` / `find` / `ls` / `pwd` / `cat` / `sed -n` 等只读命令理解项目
- 读取 `.easy-coding/` 固定资产与 Spec / Prototype 输入
- 仅扫描 `.easy-coding/spec/dev/` 下的 Markdown 候选文件名
- 用户选定 Dev-Spec 后调用当前已加载 Skill 根目录下的 `scripts/inspect_dev_spec.py`，做只读 manifest、仓库、任务和基线检查
- 查看 `git status` / `git diff` / `git log` 等只读状态与历史

**规则：**
- 在项目模式判定、INIT 背景加载、输入发现、ANALYSIS 技术方案分析中，只读上下文采集不需要用户确认，且必须主动执行。
- 不得以“方案未确认禁止执行”为理由拒绝只读扫描；正确行为是先完成只读扫描，再输出阶段状态、初始化缺失项或技术方案。
- Dev-Spec 候选目录在用户选择前只能扫描文件名，不能读取正文；选中 Canonical Spec 后只把脚本返回的消费闭包加载到上下文。

### 写入 / 修改类操作（必须阻断到确认后）

写入 / 修改类操作指任何会新增、修改、删除、移动文件，或改变项目状态的操作，包括但不限于：

- 使用 `apply_patch` 或其他方式写入文件
- 创建、删除、移动、重命名文件或目录
- 格式化、自动修复、代码生成、依赖安装、构建输出、测试写快照等可能写入文件的命令
- 生成或更新 `.easy-coding/` 初始化资产、短期记忆、长期记忆沉淀结果
- 旧版记忆兼容迁移（仅限 `.easy-coding/memory/`）
- `git add` / `git commit` / `git push` 等提交或远端状态变更

**使用任何写入 / 修改类操作前，必须完成以下检查：**

```
□ 当前阶段是否允许写入？
  - IMPLEMENT：必须已有用户确认的技术方案
  - REVIEW：仅联合模式在 IMPLEMENT 完成后使用；必须已有变更文件清单、验证结果和 host 自检结论；Claude 只能只读 review，若 verdict=fix 且修复仍在已确认方案范围内，可由 host agent 修复后重新 review
  - INIT / interactive_init：仅允许用户明确确认初始化后，按 flow/init.md 写入 .easy-coding/ 初始化资产
  - INIT / post_v1_auto_init：仅允许初创项目第一版实现结果已由用户确认，且首次任务为先交付第一版而跳过前置 INIT 后，按 flow/init.md 自动回补 .easy-coding/ 初始化资产
  - INIT / legacy_memory_migration：仅当发现旧版记忆文件时，按 flow/memory-migration.md 渐进迁移 .easy-coding/memory/；不得改写业务代码、Spec 或 Prototype
  - MEMORY：仅允许实施结果已由用户确认后，按记忆流程写入；必须在同一阶段内先生成并验证本轮短期记忆，再执行长期沉淀检查
  - 其他情况 → 禁止写入，输出阻断提示等待确认
□ 用户是否已明确确认对应操作？
  - 技术实现：用户已确认技术方案
  - 联合模式 review 修复：技术方案已确认，且 review 问题仍属于已确认改动范围
  - 常规初始化 interactive_init：用户已确认开始初始化
  - 初创项目初始化资产回补 post_v1_auto_init：用户已确认第一版实现结果，且该初创任务曾跳过前置 INIT
  - 旧版记忆迁移 legacy_memory_migration：已在 `INIT` 阶段输出迁移提示并获得用户明确确认，且只写入 `.easy-coding/memory/`
  - 实施后记忆：用户已确认实施结果
  - 若否 → 禁止写入，输出阻断提示等待确认
□ 本次操作是否在已确认的方案范围内？
  - 若否 → 必须重新出方案，返回 WAITING_CONFIRM
□ 本次操作是否遵守已确认改动范围中的改动类型与文件编码？
  - 若否 → 必须重新出完整方案，返回 WAITING_CONFIRM
```

**绝对禁止（违反=任务失败）：**
- ❌ 把只读扫描误判为“未确认前禁止的文件操作”，导致不扫描项目就直接等待用户
- ❌ 在 ANALYSIS / WAITING_CONFIRM 阶段执行任何写入 / 修改类操作
- ❌ 未经用户明确确认就执行文件修改、初始化写入、记忆写入、提交或推送
- ❌ 以"改动很小"为由跳过确认直接写入

---

# 🛑 用户紧急停止指令

**若当前轮命中 `#no-coding`，本节全部失效，直接跳过。**

**用户说以下任一指令时，AI 必须立即停止当前操作：**
- "停止" / "不对" / "错了" / "你没按流程" / "检查 skill 规则"

**停止后的处理：**
1. 立即停止当前操作
2. 输出：`[阶段：INIT] 检测到紧急停止指令，流程重置`
3. 重新从阶段 1 开始执行

---

# 🧭 主控层职责

`SKILL.md` 只负责总控，不承载场景细节正文。

- 负责：全局硬约束、阶段定义、项目模式判定、输入发现、冲突处理、流程路由
- 不负责：初始化细节、初创项目细节、设计规范正文、语言规范正文

**按需读取路由：**
- Easy Coding With Claude 联合模式：读取 `flow/with-claude.md`
- 普通初始化或初始化资产回补：读取 `flow/init.md`
- 初创项目：读取 `flow/startup-project.md`
- 选中 `easy-dev-spec/v1` Canonical Spec：读取 `references/dev-spec/canonical-v1.md`
- 前端设计任务：按需读取 `references/design/apple-design-reference.md`
- 涉及前端页面、界面、交互、样式、组件、视觉升级时：
  - 优先启用 `frontend-skill`
  - 若执行环境支持 agent / 子代理协作，应尽可能调度带 `frontend-skill` 的前端实现角色
- 未来语言或框架规范统一存放于 `references/coding/`，按需读取，不写回本文件

---

# 📋 阶段总览（完整工作流程）

**若当前轮命中 `#no-coding`，不进入下述任何阶段。**

```
┌─────────────────────────────────────────────────────────────┐
│  ① INIT → ② ANALYSIS → ③ WAITING_CONFIRM → ④ IMPLEMENT  │
│                                      ↓                      │
│        ④.5 REVIEW（仅联合模式，可跳过）                    │
│                                      ↓                      │
│  实施结果报告 → 等待用户确认结果 → 项目模式后续流转          │
│                                      ↓                      │
│            ⑤ MEMORY → ⑥ COMPLETE                           │
└─────────────────────────────────────────────────────────────┘
```

> `REVIEW` 仅在 Easy Coding With Claude 联合模式中启用；普通 Easy-Coding 流程保持六阶段。

| 阶段 | 名称 | 进入条件 | 离开条件 | 关键约束 |
|:---:|------|---------|---------|---------|
| ① | INIT | skill 被触发且进入迭代项目，或初创项目第一版完成后的初始化资产回补 | 初始化完成 / 背景加载完成 | 初创项目首次任务可跳过前置 INIT；回补不是流程开头的前置 INIT |
| ② | ANALYSIS | 用户描述需求 | 方案输出完成 | 需求不清晰禁止进入下一阶段 |
| ③ | WAITING_CONFIRM | 方案已输出 | 用户说"确认/ok/开始" | 用户未确认禁止进入下一阶段 |
| ④ | IMPLEMENT | 用户已确认方案 | 所有步骤完成 | 每步完成后必须汇报 |
| ④.5 | REVIEW | 仅联合模式；IMPLEMENT 完成且已有变更清单、验证结果、host 自检结论后自动进入 | Claude review 通过 / 3 轮结束 / Claude 不可用降级 | Claude 只读，修复仅由 host agent 执行 |
| ⑤ | MEMORY | 实施结果报告后收到用户确认，且必要的初始化资产回补已完成 | 短期记忆与条件性长期沉淀全部处理完成 | 确认后自动触发；先写短期检查点，再按冻结候选执行 `no-op` 或 `distill` |
| ⑥ | COMPLETE | 记忆处理完成 | 流程结束 | 输出完成报告 |

## 阶段命名硬约束

- 必须遵守顶部“阶段标签硬门”；未知阶段一律禁止输出。
- `PLAN` 不是 Easy Coding 阶段；任何用户可见输出都不得写 `[阶段：PLAN]` 或把 With Claude 的 `plan_mode` 表述为 Easy Coding 阶段。
- With Claude task packet 中的 `workflow_type` / `phase` / `status` / `verdict` 只是 Claude worker 内部字段，不等于 Easy Coding 阶段标识。
- Claude 在 ANALYSIS 协作中仍在运行、没有最终 worker contract 时，所有进度更新必须继续使用 `[阶段：ANALYSIS]`。
- `REVIEW` 只能在 IMPLEMENT 完成后出现；需求分析、方案合并、等待 Claude 分析结果、方案修订、等待用户确认时都不得使用 `[阶段：REVIEW]`。
- 实施结果报告后的“确认结果”属于已激活流程续流；只有收到用户确认后，才允许进入初始化资产回补或记忆流程。

---

# 🧠 强制自我审查（每次回复前执行）

**若当前轮命中 `#no-coding`，本节全部失效。**

在生成任何内容前，AI 必须先在内心完成以下检查：

```
□ 我现在处于哪个阶段？
□ 当前阶段的核心约束是什么？
□ 我是否即将违反“方案未确认禁止执行”规则？
□ 我是否即将违反“禁止跳步”规则？
□ 我即将使用的是只读上下文采集还是写入 / 修改类操作？
□ 如果是写入 / 修改类操作，当前阶段与用户确认状态是否允许？
□ 本次回复是否已包含合法阶段标注？阶段是否属于 INIT / ANALYSIS / WAITING_CONFIRM / IMPLEMENT / REVIEW / MEMORY / COMPLETE？
```

**若任一检查不通过 → 停止生成 → 输出阻断提示 → 等待用户确认**

---

# 🏷️ 项目模式判定

进入 INIT 之前，必须先判定项目模式。

## 首要动作

当 `easy-coding` 被触发后，第一优先级不是等待用户补充描述，而是立即完成以下动作：

1. 扫描当前项目代码、目录结构和配置文件
2. 主动检测是否为空项目 / 近似空项目
3. 主动发现 `.easy-coding/spec/` 与 `.easy-coding/prototype/` 下的可用输入
4. 先判定项目模式，再决定是否需要向用户追问

以上动作均属于只读上下文采集，必须主动执行，不受“方案确认前禁止写入”的阻断影响。

若已经能够从项目现状和 Spec 中得出足够上下文，不要先回复“请描述您的需求”。

## 模式名称

- `初创项目`：原“0-1 项目”
- `迭代项目`：原“非0-1项目”

## 判定规则

**判定依据固定为：代码现状 + Spec 现状。**

**检测方式必须是主动检测，不依赖用户口头声明。**

### 判为 `初创项目` 的典型信号
- 仓库几乎无成型业务代码
- 仅有脚手架、配置、README、空目录、示例页、占位代码
- 已有 `Product-Spec.md` / `UI-Spec.md` / `Architect-Spec.md` / Prototype，但代码仍处于未落地状态

### 判为 `迭代项目` 的典型信号
- 已存在明确业务实现
- 已存在页面 / 接口 / 服务 / 领域模型 / 数据模型 / 核心流程代码
- 当前任务明显是在既有系统上修复、扩展、重构或优化

### 重要说明
- Spec 的存在与否只作辅助证据，不单独决定项目模式
- 若无法可靠判定，优先按 `迭代项目` 处理，并在 ANALYSIS 中说明判断依据
- 若空项目信号明显，且已发现可用 Spec / Prototype 输入，应直接判为 `初创项目`

## 判定后的路由

- 若为 `初创项目`：
  - 跳过前置 INIT 阻断
  - 立即读取并遵循 `flow/startup-project.md`
  - 若已发现可用 Spec / Prototype 输入，直接进入 ANALYSIS，不等待用户补充需求描述
- 若为 `迭代项目`：
  - 继续执行本文件中的 INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT 流程

---

# 📥 输入发现规则

进入 ANALYSIS 前，必须按以下顺序发现上下文。除 Dev-Spec 候选需要用户选择外，以下发现与读取均属于只读上下文采集，允许在方案确认前执行：

1. 用户当前提示词
2. 当前项目代码、目录结构、配置文件
3. `.easy-coding/SOUL.md`
4. `.easy-coding/RULES.md`
5. `.easy-coding/ABSTRACT.md`
6. `.easy-coding/memory/long/MEMORY.md`（先轻量探测 `memory_schema` 与索引）
7. `.easy-coding/memory/long/BUSINESS.md`（仅当索引或本轮需求命中业务记忆时读取）
8. `.easy-coding/memory/long/TECHNICAL.md`（仅当索引或本轮需求命中技术记忆时读取）
9. `.easy-coding/memory/short/*.md`
10. `.easy-coding/spec/Architect-Spec.md`
11. `.easy-coding/spec/Product-Spec.md`
12. `.easy-coding/spec/UI-Spec.md`
13. `.easy-coding/prototype/Easy-UI-Prototype.md`
14. `.easy-coding/prototype/index.html` 与 `.easy-coding/prototype/` 下的页面 HTML 文件
15. `.easy-coding/prototype/assets/` 下与原型行为、样式或 mock 数据相关的资源文件
16. `.easy-coding/prototype/images/` 下的 AI 原生生图原型图片
17. 扫描 `.easy-coding/spec/dev/` 下的 Markdown 候选文件（仅扫描文件名，不自动读取正文）
18. 若用户显式引用任意具体 Markdown Dev-Spec 路径，直接将其作为当前候选

## 读取规则

- 存在则读取，不存在则跳过
- 若发现旧版记忆结构，必须回到 `INIT` 迁移确认门禁；未获用户确认前不得执行迁移、不得进入 `ANALYSIS`
- 新版长期记忆以 `long/MEMORY.md` 为索引；`BUSINESS.md` / `TECHNICAL.md` 只在索引或本轮需求命中时读取，不把未命中的长期正文硬塞进方案
- 默认只读取 `BUSINESS.md` / `TECHNICAL.md` 的有效记忆区和 `MEMORY.md` 中状态为 `active` 的主题；“已淘汰记录”默认不进入 `ANALYSIS` 上下文，仅在旧版迁移、冲突排查或用户追溯历史原因时读取
- 短期记忆最多 10 条，允许全部读取；读取时优先看 frontmatter、业务记忆候选、技术记忆候选和不沉淀内容
- Prototype 固定根目录为 `.easy-coding/prototype/`；不要到其他目录猜测原型产物
- 原型 HTML 读取后只作为参考输入，绝不视为可直接落地的生产代码
- 解析 `.easy-coding/prototype/Easy-UI-Prototype.md` 后，应尽可能读取其中引用的 HTML 文件；若文档未列全，则继续扫描 `.easy-coding/prototype/` 下的 HTML 文件
- `assets/` 中的 CSS、JS 和 mock 数据只用于理解视觉、交互与数据示例，不作为生产实现直接复用
- `images/` 中的 AI 原型图片只作为视觉和布局参考；若当前运行环境无法直接读取图片像素，应读取 `Easy-UI-Prototype.md` 中的页面索引、用途和提示词，并在分析中标注未直接检查图片像素
- 若项目已判定为 `初创项目` 且发现了可用 Spec / Prototype 输入，应直接基于这些输入进入分析
- 只有在关键实现信息仍明显不足时，才向用户追问

## Dev-Spec 候选处理

- `.easy-coding/spec/dev/` 仅作为运行时候选目录，不属于固定全局 Spec 输入。
- 扫描时只列出候选 Markdown 文件，不自动读取正文；候选按相对路径字典序稳定排序并生成 1 开始的编号。
- 用户显式引用具体 Dev-Spec 路径时，直接使用该路径，不再要求按编号二次选择。
- 若发现候选文件，且当前需求尚未选定 Dev-Spec：
  - 在 `ANALYSIS` 阶段先输出短提示，并必须列出完整候选编号清单；只显示数量、不显示文件名视为失败。
  - 选择协议统一为编号多选：`1,3` 表示加载第 1 和第 3 个文件，`1-3` 表示加载连续区间，`all` / `全部` 表示加载全部，`none` / `不加载` 表示不加载。
  - 若当前 agent 暴露原生选择工具，必须调用工具提供 `全部加载`、`不加载`、`暂不选择/保持等待` 等真实分支；部分加载、多文件组合和区间选择由客户端 free-form Other 输入编号承接。
  - 若原生选择工具不可用，使用文本兜底，但仍必须先打印完整编号清单，并提示用户按编号回复，例如 `1,3`、`1-3`、`全部` 或 `不加载`。
  - 若用户输入无法解析、编号越界或没有命中任何候选，必须重新展示候选清单并等待选择；不得读取正文，不得进入正式技术方案分析。
  - 在用户明确选择前，不读取任何 Dev-Spec 正文，不进入正式技术方案分析。
- 用户选定文件后，先解析本 `SKILL.md` 所在目录为 `<easy-coding-skill-dir>`，运行 `python3 <easy-coding-skill-dir>/scripts/inspect_dev_spec.py <spec-path> --repo-root <repo-root> --manifest-only` 探测协议；不得从业务仓库 cwd 猜测脚本路径，也不得先把任务正文读入 Agent 上下文：
  - 返回 `legacy`：保留现有多文件选择能力，读取所选 legacy 文件全文并进入正式分析。
  - 返回 `canonical-v1`：一轮需求只允许激活一份 Canonical Spec；立即读取并遵循 `references/dev-spec/canonical-v1.md`，继续仓库识别与 task 选择。
  - 返回 `RepositoryAmbiguityError` 且包含 `candidates`：展示候选 `repo_id / name / remote_urls / path_hint` 并等待用户确认；确认后先用 `--manifest-only --repo-path <repo-id>=<repo-root>` 重新取得 task catalog，完成 task 选择后在完整检查命令中保留同一 repo path；不得替用户猜测。
  - 返回不支持的 schema、非法 manifest 或仓库零匹配：明确报告错误并停止消费；不得按 legacy 降级。
  - 同时选择多份文件且其中包含 Canonical Spec：保留 legacy 文件但不加载正文，要求用户选择一份 Canonical Spec 作为当前需求的唯一任务空间。
- Canonical Spec 路由完成后：
  - 用户明确 task ID 时用重复的 `--task <task-id>` 运行完整检查；用户明确要求完成当前仓库时才允许不传 `--task` 选择该仓全部 READY task。
  - 只把脚本返回的 `scope_markdown` 作为当前需求已选 Dev-Spec 上下文。
  - 记录 `spec_id`、`source_sha256`、`selected_task_ids`、`repo_ids`、`dependency_gaps`、`baseline_status` 和 `scope_sha256`。
  - 不读取未选 task 的正文，不重新要求用户描述已由选中 task 明确表达的需求。
- 若用户明确表示“不加载”：
  - 若当前轮也没有任何足以支撑分析的有效提示词，且不存在可补足上下文的固定 Spec / Prototype 输入，直接输出：
    - `未识别到用户意图, Easy Coding 已准备好, 请随时向我发问`
    - 当前轮到此结束，不进入 `WAITING_CONFIRM`，不产出技术方案。
  - 否则继续按现有流程分析。
  - 但必须在分析结果中标注具体“未加载 Dev-Spec”文件列表。
- 已选 Dev-Spec、Canonical task 选择、`source_sha256` 与 `scope_sha256` 的生命周期仅限当前需求：
  - 从本次 `ANALYSIS` 开始，持续到该需求结束或用户明确切换/清空为止。
  - 不写入 `.easy-coding/spec/` 固定输入集合。
  - 不写入 `.easy-coding/memory/`，不作为后续需求默认输入。
  - 若用户在需求中途切换 Dev-Spec、task 或 repo path，视为需求变更；必须重新运行检查脚本，回到 `ANALYSIS` 并用新的闭包重新输出方案。

## 前端任务附加读取

若任务涉及页面、界面、交互、样式、组件、前端重构或视觉升级，额外执行：

1. 按需读取 `references/design/apple-design-reference.md`
2. 优先启用 `frontend-skill`
3. 优先参考 `.easy-coding/prototype/` 下的 Prototype 文档、HTML、assets 与 images
4. 明确遵守以下约束：
   - Prototype HTML 仅供原型参考
   - Prototype 图片仅供视觉、布局和交互意图参考
   - 不得直接复制到生产代码
   - 必须结合当前项目框架、组件体系、状态管理、路由和样式方案做深度再设计与适配

## 前端生产实现硬约束

若本次任务不是“制作原型”，而是要交付真实前端代码，则以下规则必须同时满足：

1. 先把 Prototype 拆成“页面 / 组件 / 状态 / 交互 / 数据需求”的实现映射，禁止整页照搬 HTML。
2. 必须优先复用当前项目已有的前端技术栈：
   - 视图框架
   - 路由方案
   - 状态管理
   - 组件体系
   - 样式方案
   - API 请求封装
3. 必须说明每个页面或核心模块的数据来源：
   - 对接现有真实接口
   - 对接 Architect-Spec / Product-Spec 中定义的接口契约
   - 若接口缺失，明确列为阻塞项或待确认项
4. 不允许把 mock 数据页面、静态 JSON 页面、演示页直接当作“前端已完成”交付。
5. 若当前阶段无法完成真实接口对接，必须明确说明缺失的后端契约或联调条件，并回到 WAITING_CONFIRM，而不是用 mock 实现冒充最终结果。

---

# ⚔️ 冲突优先级与处理规则

## 默认优先级

1. 用户当前提示词
2. 现有代码与项目现状
3. 当前需求已选 Dev-Spec
4. 历史 Spec / Prototype / Memory / ABSTRACT

## 必须显式提示的冲突

### 当前提示词 vs Spec
- 必须输出冲突摘要
- 必须询问用户采用“按当前提示词”还是“按 Spec”
- 在用户拍板前，不得进入 IMPLEMENT

### Dev-Spec vs 固定 Spec / 现有代码
- 若当前需求已选 Dev-Spec 或 Canonical task 集合，必须检查其与固定 Spec、现有代码是否冲突
- 若冲突会影响技术路线、模型、接口、状态流转或页面交互，必须在 `ANALYSIS` 中显式说明
- Canonical Spec 已冻结的契约和 task 边界不得被静默改写；本地漂移影响契约或边界时必须输出 Spec 修订项并等待用户确认

### Spec vs 现有代码（仅迭代项目）
- 默认采用保守迭代策略
- 即以现有代码和结构现状为主，Spec 作为参考
- 若冲突会影响技术路线、模型、接口、状态流转或页面交互，必须提示用户拍板

### 初创项目中的 Spec 缺口
- 若关键实现信息不足，不得自由脑补
- 必须主动追问，或在方案中显式标注“当前假设”，等待用户确认

---

# 【阶段 1】INIT - 初始化

**进入条件：**
- 项目模式为 `迭代项目`
- 或 `初创项目` 第一版开发完成后的初始化资产回补

## 1.1 初始化检查

只认 `.easy-coding/` 目录及以下关键文件：

```
□ .easy-coding/
□ .easy-coding/memory/short/
□ .easy-coding/memory/long/
□ .easy-coding/SOUL.md
□ .easy-coding/RULES.md
□ .easy-coding/ABSTRACT.md
□ .easy-coding/memory/long/MEMORY.md
□ .easy-coding/memory/long/BUSINESS.md
□ .easy-coding/memory/long/TECHNICAL.md
```

若仅缺失 `BUSINESS.md` / `TECHNICAL.md`，或 `MEMORY.md` 缺少 `memory_schema: 2`，不直接判定为初始化失败；应进入下方旧版记忆迁移确认门禁。

## 1.2 旧版记忆迁移确认门禁

INIT 阶段必须在输出背景摘要、进入 `ANALYSIS` 之前，先对记忆结构做轻量迁移探测。探测只允许读取文件存在性、`MEMORY.md` frontmatter / 索引特征、短期记忆 frontmatter，不执行写入。

满足任一条件即判定需要迁移：

- `.easy-coding/memory/long/MEMORY.md` 存在但缺少 `memory_schema: 2`
- `.easy-coding/memory/long/BUSINESS.md` 缺失
- `.easy-coding/memory/long/TECHNICAL.md` 缺失
- `.easy-coding/memory/short/*.md` 存在缺少 frontmatter 或 `memory_schema != 2` 的旧版短期记忆
- `MEMORY.md` 仍是旧版长期正文，而非新版索引导航

若需要迁移：

- 必须停留在 `[阶段：INIT]`
- 不得进入 `ANALYSIS`
- 不得静默执行迁移
- 必须提示用户确认迁移；若当前 agent 暴露 `request_user_input` 或等价原生选择工具，优先提供“确认迁移 (Recommended) / 暂不迁移”

输出模板：

```markdown
[阶段：INIT]

⚠️ 检测到旧版记忆结构，需要迁移后再继续分析

- 旧版长期记忆：{MEMORY.md schema / 索引状态；无则写“无”}
- 缺失的新长期文件：{BUSINESS.md / TECHNICAL.md；无则写“无”}
- 旧版短期记忆：{旧版短期文件数量与示例；无则写“无”}
- 迁移范围：仅 `.easy-coding/memory/`
- 迁移结果：旧长期拆分为 MEMORY / BUSINESS / TECHNICAL；短期记忆一次性沉淀，成功后删除已处理短期文件

是否确认执行记忆迁移？确认后将执行 `flow/memory-migration.md`，完成后自动进入 ANALYSIS。
```

用户确认迁移后：

1. 读取并执行 `flow/memory-migration.md`
2. 输出迁移审计摘要
3. 重新按新版三文件记忆结构加载背景
4. 自动进入 `ANALYSIS`

用户选择暂不迁移时：

- 保持 `[阶段：INIT]` 阻断
- 不进入 `ANALYSIS`
- 说明旧版记忆结构未迁移，无法保证后续记忆读取一致性

## 1.3 初始化分支

### 情况 A：全部存在且有效，且迁移门禁未命中
输出背景摘要后进入 ANALYSIS。

### 情况 B：缺失
输出缺失明细，并等待用户确认初始化：

```markdown
[阶段：INIT]

⚠️ 项目初始化不完全

缺失项明细：
1. ❌ .easy-coding/SOUL.md - 未创建
2. ❌ .easy-coding/RULES.md - 已创建但未填充
3. ❌ .easy-coding/ABSTRACT.md - 未创建

是否开始初始化？优先使用原生选择框提供“确认初始化 / 暂不初始化”；不可用时回复"确认"开始，将执行 flow/init.md 中的初始化流程。
```

**用户确认后：**
- 读取 `flow/init.md`
- 若是常规初始化，按交互式初始化执行
- 若是初创项目第一版开发后的初始化资产回补，则按 `post_v1_auto_init` 语义执行

## 1.4 输出背景摘要

```markdown
[阶段：INIT]

✅ 背景加载完成
- 项目模式：{初创项目/迭代项目}
- 项目架构：{已读取/已初始化}
- 历史记忆：{memory_schema 版本；迁移状态；N 条短期记忆；命中的业务/技术长期主题}
- 编码规范：{已加载}

若当前为迭代项目，请描述您的需求，我将为您分析技术方案。
```

---

# 【阶段 2】ANALYSIS - 需求分析

**进入条件：**
- 用户已描述需求
- 或项目已判定为 `初创项目`，且已发现足以支撑首版方案的 Spec / Prototype 输入

## 2.1 需求清晰度检查

检查以下五项，满足至少四项才能进入方案设计：

| # | 检查项 |
|---|--------|
| 1 | 目标用户 / 使用场景 |
| 2 | 输入 / 输出格式 |
| 3 | 边界条件（做什么 / 不做什么） |
| 4 | 涉及模块 |
| 5 | 约束条件（性能 / 安全 / 兼容性） |

若未知项 ≥ 2，必须先追问，禁止猜测。

**初创项目特例：**
- 若 Product-Spec / UI-Spec / Architect-Spec / Prototype 已经覆盖了大部分关键信息，应直接把这些文档内容视为已知项
- 不要因为“用户本轮没有额外输入”就退回到泛化追问
- 只有 Spec 中缺少关键实现信息时，才追问用户
- 若已扫描到 Dev-Spec 候选但用户尚未选择，先输出完整编号清单并完成选择，再进入正式方案分析

## 2.2 背景数据加载

进入 ANALYSIS 阶段后，必须重新加载：

- `.easy-coding/SOUL.md`
- `.easy-coding/RULES.md`
- `.easy-coding/ABSTRACT.md`
- `.easy-coding/memory/long/MEMORY.md`
- `.easy-coding/memory/long/BUSINESS.md`（按索引或需求命中读取）
- `.easy-coding/memory/long/TECHNICAL.md`（按索引或需求命中读取）
- `.easy-coding/memory/short/*.md`
- 发现到的 Spec / Prototype 文档 / Prototype HTML / Prototype 图片 / Prototype assets
- 当前需求已选 legacy Dev-Spec 全文，或 Canonical Spec 的 `scope_markdown` 消费闭包（若有）

若长期记忆缺少 `memory_schema: 2`、缺少 `BUSINESS.md` / `TECHNICAL.md`，或发现短期记忆缺少 frontmatter / `memory_schema != 2`，必须回到 `INIT` 旧版记忆迁移确认门禁；用户确认后按 `flow/memory-migration.md` 迁移，再继续正式分析。旧版短期迁移是一次性升级动作，不保留旧短期滑动窗口。

若当前为 `初创项目` 且用户没有补充额外需求，必须默认把 Spec / Prototype 视为本轮主要需求来源。

**额外强制要求：**
- 若当前项目已存在相关代码、页面、接口、服务、模型或配置，必须先读取这些实际文件，再输出方案
- 不允许在没有看过相关代码的情况下，只根据用户需求复述出“分析结果”
- 若代码尚不存在，必须明确写出“当前现状为空项目 / 脚手架项目”，而不是伪装成已有实现分析

## 2.3 分析维度

- 项目模式：初创项目 / 迭代项目
- 任务类型：新功能 / Bug 修复 / 重构 / 性能优化 / 前端设计实现
- 业务子域与影响范围
- 现状代码结构与关键实现位置
- Spec 输入是否参与本次分析
- Canonical Spec 的 `spec_id / source_sha256 / selected_task_ids / repo_ids / scope_sha256`（若有）
- Canonical task 的依赖缺口、执行 Wave 与 baseline 状态（若有）
- 是否涉及前端实现
- 是否存在提示词与 Spec 冲突
- 是否存在 Spec 与现有代码冲突

## 2.3.1 Easy Coding With Claude 等待态

若当前处于 Easy Coding With Claude 联合模式：

- ANALYSIS 协作固定使用 With Claude `readonly_analysis` flow：`workflow_type=readonly_analysis`、`phase=analysis`、`expected_output_type=analysis`。
- 不得因为当前 host 处于 Plan Mode、用户说“方案/计划”、或 With Claude 支持 `plan_mode`，就把 Easy Coding ANALYSIS 切换为 `PLAN` 或 With Claude `plan_mode`。
- Claude 还在运行、尚未返回最终 worker contract 时，用户可见进展必须保持 `[阶段：ANALYSIS]`。
- 等待期间只能输出“Claude 协作进展 / 当前已读证据 / 仍在等待最终 contract”，不能输出正式技术方案，不能进入 `WAITING_CONFIRM`。
- 只有 Claude 返回 `done` / `blocked` / `needs_user_input` 后，才能合并结果：`done` 输出完整 2.5 技术方案，`blocked` 输出完整 2.5 技术方案并在 `### Claude 协作` 标注 `Claude pass unavailable`，`needs_user_input` 与 Easy Coding 自身问题去重后一次性询问用户。

## 2.4 前端任务专属分析

若本次任务涉及前端：

- 必须说明已启用或应启用 `frontend-skill`
- 必须说明是否参考了 `references/design/apple-design-reference.md`
- 必须说明是否参考了 Prototype 文档、HTML、图片与 assets
- 必须明确写出“Prototype HTML 与图片仅供参考，不能直接用于生产实现”
- 必须输出“原型到工程实现映射”，至少覆盖：
  - 页面 / 模块拆解
  - 组件拆解
  - 状态来源
  - 数据来源
  - 接口对接策略
- 必须明确说明 mock 数据是否存在；若存在，必须说明其用途、替代条件和退出方式

## 2.4.1 Canonical Spec 快速路径

仅当 `references/dev-spec/canonical-v1.md` 的快速路径条件全部满足时使用。快速路径必须输出：

1. 当前 `spec_id`、所选 `task_id` 与 `repo_id`。
2. 各仓库 baseline 状态和当前 HEAD。
3. RULES、ABSTRACT、用户提示词与 Canonical Spec 的冲突。
4. task Wave、仓库路径映射与依赖状态。
5. 本轮文件、符号、测试和 integration 门禁。
6. 原 Spec 的 `source_sha256`、消费闭包的 `scope_sha256` 与进入 `WAITING_CONFIRM` 所需的完整确认信息。

快速路径不得重新选择接口类型、重新命名字段、重新拆 task，或把 Canonical Spec 改写成另一份平行技术方案。条件不满足时继续执行 2.5 的完整方案；`scope-drifted` 必须先读取漂移文件和符号，并列出 Spec 修订项。

## 2.5 输出技术方案（核心必填 + 条件展开）

技术方案必须优先保证可实施、可确认、可验收。不要为了填满模板输出无关章节；未命中的条件章节必须省略。

### 核心必填章节

每次正式方案必须包含以下章节：

```markdown
[阶段：ANALYSIS]

## 技术方案：{任务标题}

### 项目模式
{初创项目/迭代项目}

### 任务类型
{新功能/Bug 修复/重构/性能优化/前端设计实现}

### 需求解析
- 目标：{真正要解决的问题}
- 输入：{用户输入 / 系统输入 / 触发条件}
- 输出：{最终交付结果}
- 边界：{明确不做什么}

### 现状
- 相关代码 / 页面 / 接口 / 模块：{基于实际文件与代码的现状说明}
- 当前实现方式：{现在是如何工作的}
- 现有问题 / 缺口：{为什么需要改}
- 证据：{引用的关键文件、类、页面、接口}

### 冲突摘要
- 提示词 vs Spec：{无 / 冲突说明}
- 提示词 vs Dev-Spec：{无 / 冲突说明}
- Dev-Spec vs 固定 Spec：{无 / 冲突说明}
- Dev-Spec vs 现有代码：{无 / 冲突说明}
- Spec vs 现有代码：{无 / 冲突说明}

### 待用户决策
- {若存在会影响技术路线、模型、接口、状态流转、页面交互、改动范围或文件编码的冲突，逐条列出需要用户拍板的问题；若无则写“无”}

### 影响面分析
- 涉及模块：{列表}
- 核心类 / 页面 / 接口：{列表}
- 数据库变更：{有/无}
- 接口变更：{有/无}
- 关联历史任务：{相关短期记忆序号；若无则填“无”}

### 改动范围
| 改动文件 | 改动类型（新增/修改/删除） | 文件编码 | 改动核心内容 |
|----------|----------------------------|----------|--------------|
| `{文件路径 A}` | `{新增/修改/删除}` | `{修改旧文件：保持原编码 X；新建文件：项目编码 X，依据为 xxx；删除文件：不写入，原编码 X/不适用；无法确认：待用户确认}` | `{结合代码或描述说明核心改动}` |
| `{文件路径 B}` | `{新增/修改/删除}` | `{同上}` | `{核心改动}` |

> 文件编码要求：修改旧文件必须先识别并保持原文件编码，永远不要擅自转换编码；新建文件必须分析项目编码依据并套用项目编码；若编码证据冲突或无法确认，必须在表格中标注“待用户确认”。用户可在确认前针对任一文件的编码字段提出修改。

### 修改方案
- 总体改法：{一句话说清改哪里、怎么改}
- 后端改动：{若涉及，说明服务 / 控制器 / 数据模型 / DDL / 接口契约；不涉及则写“不涉及”}
- 前端改动：{若涉及，说明页面 / 组件 / 状态 / 路由 / 接口接入；不涉及则写“不涉及”}
- 注释策略：{必须列出本次预计补充注释的位置与原因；写明注释语种判断结果：优先匹配当前对话语种，无法识别时默认简体中文，用户明确指定时按用户要求；若判断本次无必要注释，必须写“本次无必要注释”并说明原因；若涉及需要作者署名的新文件，写明署名将使用 `${Agent Name} with Easy Coding`}
- 兼容处理：{旧逻辑如何迁移、保留或替换}
- 风险点：{最容易出问题的位置}

### 实现步骤
1. {步骤 1}
2. {步骤 2}
3. {步骤 3}

### 验证与验收
- 自动化验证：{测试 / 构建 / 静态检查命令；若无法执行，说明原因}
- 人工验收：{用户或开发者需要检查的关键行为}
- 无法验证项：{无 / 说明缺失环境、数据、权限或接口契约}

### 风险与注意事项
- {风险 1}
- {风险 2}
```

### 条件展开章节

只有在命中对应条件时，才输出以下章节。

**命中 `.easy-coding` 背景数据且其内容影响本次方案时，输出：**

```markdown
### 背景数据应用
- 相关架构：{引用 ABSTRACT.md 与当前代码现状}
- 业务记忆：{引用 BUSINESS.md 中命中的业务域、字段语义、流程或规则；若无相关内容则填“无”}
- 技术记忆：{引用 TECHNICAL.md 中命中的架构决策、工程规则、实现模式或易错点；若无相关内容则填“无”}
- 记忆冲突：{若记忆与当前代码或用户最新表达冲突，说明冲突并以当前代码/用户最新表达为准；无则填“无”}
- 规范约束：{引用 RULES.md 中相关强制规范}
```

**命中固定 Spec / Prototype / 已选 Dev-Spec 时，输出：**

```markdown
### Spec 输入应用
- Architect-Spec：{已使用/未使用}
- Product-Spec：{已使用/未使用}
- UI-Spec：{已使用/未使用}
- Prototype 文档：{已使用/未使用}
- Prototype HTML：{已使用/未使用}
- Prototype 图片：{已使用/未使用/环境不支持直接读取像素}
- Prototype assets：{已使用/未使用}
- Dev-Spec 目录扫描：{有/无}
- Dev-Spec 候选文件：{文件路径列表/无}
- 已选 Dev-Spec：{文件路径列表/无}
- 未加载 Dev-Spec：{文件路径列表/无}
- Dev-Spec 协议：{legacy/canonical-v1/无}
- Canonical Spec：{spec_id/无}
- Source SHA-256：{source_sha256/无}
- 已选任务：{selected_task_ids/无}
- 仓库范围：{repo_ids 与路径映射/无}
- 依赖缺口：{dependency_gaps/无}
- Baseline：{各 repo 状态/无}
- Scope SHA-256：{scope_sha256/无}
```

**命中 Easy Coding With Claude 联合模式时，输出：**

```markdown
### Claude 协作
- 任务 packet 摘要：{必须为 workflow_type=readonly_analysis / phase=analysis / expected_output_type=analysis；INIT/REVIEW 例外按对应阶段填写；add_read_dirs 使用情况}
- Claude 状态：{done / needs_user_input / blocked；若 blocked，必须写 Claude pass unavailable}
- Claude 观点简述：{概括 Claude 的主要建议与风险提醒}
- 采纳情况：{已采纳 / 部分采纳 / 未采纳，逐条说明原因}
- 与 Claude 的冲突点：{若无则写“无”；若有，说明以哪一侧证据为准}
```

**任务涉及多个核心文件 / 模块，且仅靠“改动范围”不足以表达当前逻辑和目标逻辑时，输出：**

```markdown
### 核心改动明细
1. `{文件或模块 A}`
   - 当前：{当前逻辑}
   - 修改：{准备怎么改}
2. `{文件或模块 B}`
   - 当前：{当前逻辑}
   - 修改：{准备怎么改}
```

**涉及页面、界面、交互、样式、组件、前端重构或视觉升级时，输出：**

```markdown
### 前端实现映射
- 页面 / 模块映射：{Prototype 页面如何映射到真实工程页面}
- 组件映射：{可复用组件 / 新增组件}
- 数据来源：{真实接口 / 既有 store / 服务层 / 契约待补充}
- 接口对接策略：{已对接 / 需新增接口 / 需等待后端}
- Mock 使用计划：{无 / 仅临时占位，并说明退出条件}
```

**禁止输出：**
- “分析 XXXX 的计划”
- 仅复述需求、几乎不引用代码现状的空泛方案
- 只列“已加载哪些信息”，但不给出具体可实施改法
- 为了凑格式输出与本次任务无关的条件章节

---

# 【阶段 3】WAITING_CONFIRM - 等待确认（阻断状态）

**进入条件：方案已输出**

```markdown
[阶段：WAITING_CONFIRM] ⏸️ 阻断状态

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
以上为技术方案，请确认或提出修改意见。

✅ 确认方式：优先使用原生选择框点选“确认执行方案”；不可用时回复"确认" / "ok" / "开始" / "没问题"
✏️ 修改方式：直接告知修改意见，我将更新方案

⚠️ 在您明确确认前，我绝对不会执行任何代码变更。
⚠️ 即使多轮讨论，我也必须等待您的明确确认指令。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

若当前 agent 暴露 `request_user_input` 或等价原生选择工具，进入 WAITING_CONFIRM 时必须调用工具，不能只输出上述文本。推荐选项：

- `确认执行方案 (Recommended)`：进入 IMPLEMENT。
- `保持等待`：不进入 IMPLEMENT，继续停留在 WAITING_CONFIRM。

修改意见、补充说明或反馈意见必须通过客户端 free-form Other 或普通文本输入承接；不要手写成选项。

若当前 agent 不支持原生选择工具，才使用文本兜底。

**继续等待的情况：**
- 用户提出修改
- 用户继续追问
- 用户未明确表态

## 3.1 用户反馈后的方案修订

若用户在 WAITING_CONFIRM 阶段提出任何修改意见，不得只回复改动摘要；必须回到 ANALYSIS 重新输出修订方案，并再次进入 WAITING_CONFIRM。

修订回复必须分为两部分：

```markdown
[阶段：ANALYSIS]（方案修订）

### 基于用户要求的改动提要
- {用户要求 1 对方案的影响}
- {用户要求 2 对方案的影响}
- {若用户修改了文件编码要求，逐文件说明编码字段如何调整}

### 修改后的完整方案
{按 2.5 的“核心必填 + 条件展开”重新输出完整方案，必须包含更新后的“改动范围”表，不输出与本次任务无关的条件章节}
```

完整方案输出后，必须再次输出 WAITING_CONFIRM 确认提示，直至用户明确确认方案。

---

# 【阶段 4】IMPLEMENT - 技术实现

**进入条件：用户已明确确认方案**

## 4.1 实施前声明

```markdown
[阶段：IMPLEMENT]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 开始技术实施

确认状态：✅ 用户已确认
实施方案：{方案标题}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 4.2 实施前必须加载

- `.easy-coding/RULES.md`
- 若当前需求使用 Canonical Spec：重新确认当前 task 的消费闭包、相关契约、`source_sha256` 和 `scope_sha256`
- 若涉及前端：按需读取 `references/design/apple-design-reference.md`

## 4.3 实施约束

- 所有代码必须遵守 `RULES.md` 中的强制规范
- 必须严格按照已确认的“改动范围”实施；不得新增、删除或修改未列入方案的文件，除非先回到 ANALYSIS 输出完整修订方案并重新确认
- Canonical Spec task 只允许修改其 `repo_id` 下 `change_ids` 声明的 path 与 symbols；新增文件、符号或步骤时必须返回 ANALYSIS 修订范围并重新确认
- Canonical task 按 Wave、`step_ids` 和 step dependency 执行；每个 step 完成后执行绑定的 `test_ids` 命令
- hard dependency 未满足时不得进入被阻断 task；integration 未完成不阻断本仓编码，但必须在实施报告中标记待联调，不能宣称全链路完成
- 必须严格遵守已确认的文件编码字段：修改旧文件保持原编码；新建文件使用项目编码；不得擅自转换文件编码，除非用户明确要求
- 新建文件若因项目模板、同类文件惯例或用户要求需要作者署名，必须写为 `${Agent Name} with Easy Coding`；`${Agent Name}` 由当前宿主 Agent 替换为自己的名称，例如 `Codex with Easy Coding`
- 编码时必须补充必要注释，并将其视为交付门禁；重点覆盖非直观业务规则、兼容/兜底逻辑、协议字段映射、异常处理、幂等/并发/缓存、配置 key 含义、风险或易错边界
- 禁止用逐行注释或无信息量注释凑数；普通赋值、简单调用、显然语法动作不需要注释
- 新增或修改注释时，注释语种必须匹配当前对话语种；无法识别对话语种时默认使用简体中文；若用户明确指定注释语言，以用户要求为准。不得在中文对话中默认写英文注释，除非用户明确要求英文或项目规范硬性要求英文
- 前端任务必须优先调用或参考 `frontend-skill`
- Prototype HTML 与图片仅可作为参考输入，不得直接复制或转贴为生产代码 / 生产设计稿
- 初创项目第一版开发必须严格以 Spec 为主依据
- 迭代项目默认按保守迭代执行，不擅自用 Spec 覆盖现有系统
- 若交付目标是真实前端代码，不得仅交付 mock 页面、静态演示页、原型截图，或把原型 HTML 改后缀后直接提交
- 前端实施必须优先完成真实工程接入：
  - 接入现有页面路由
  - 接入真实组件体系与状态管理
  - 接入真实接口或明确的接口契约
- 若后端接口或契约尚未具备，必须把缺口作为阻塞项汇报，并回到 WAITING_CONFIRM

## 4.4 注释检查门禁

实施完成后、进入实施结果报告前，必须回看本次 diff 并输出注释自检结论；注释自检、编码自检、测试、构建和验证都仍属于 `[阶段：IMPLEMENT]`，不得输出 `[阶段：VERIFY]` / `[阶段：TEST]`：
- 对新增/改动代码逐项判断是否存在必须补充注释的逻辑
- 检查新增/修改注释的语种是否匹配当前对话语种；无法识别时是否已使用简体中文；用户明确指定注释语言时是否已按用户要求执行
- 检查需要作者署名的新文件是否使用 `${Agent Name} with Easy Coding`
- 若已补充，说明覆盖了哪些关键意图、边界或风险
- 若未补充，说明为什么本次改动没有必要注释
- 若发现缺失，必须先补齐注释再继续后续阶段

## 4.5 步骤汇报

Legacy 或普通方案每完成一步使用原有步骤格式。Canonical task 每完成一个 step 必须使用 task/step/change/test ID 汇报：

```markdown
[阶段：IMPLEMENT]

✅ {task_id} / {step_id} 完成
- 仓库：{repo_id}
- 文件与符号：{change_id} / `{symbol}`
- 验证：{test_id} / `<command>`
- 依赖状态：{hard/contract/integration 状态}
```

非 Canonical 任务使用：

```markdown
[阶段：IMPLEMENT]

✅ 步骤 {N}/{总} 完成：{步骤描述}
   文件：{文件路径}
   变更：{简要说明}
   规范检查：{是否遵守 RULES.md 中的强制规范}
   编码检查：{是否符合已确认改动范围中的文件编码要求}
   注释检查：{已补充必要注释 / 本次无需补充，并说明原因}
```

## 4.6 实施中的变更控制

实施过程中，若用户提出任何变更：

1. 立即停止当前实施
2. 输出变更方案
3. 返回 WAITING_CONFIRM
4. 待用户确认后继续

## 4.7 初创项目的初始化资产回补

`post_v1_auto_init` 不是项目开始时的前置 INIT，而是“初创项目第一版实现后的初始化资产回补”。

仅当同时满足以下条件时执行：

- 当前为 `初创项目`
- 首次任务为了先交付第一版而跳过了前置 INIT
- 第一版开发已完成
- 联合模式 REVIEW 已结束（如适用）
- 用户已确认实施结果

1. 自动读取 `flow/init.md`
2. 按 `post_v1_auto_init` 语义回补 `.easy-coding/` 初始化资产
3. 不覆盖已有 Spec、Prototype 和已确认代码成果
4. 回补完成后再进入 MEMORY

## 4.8 实施完成后的自动流转

IMPLEMENT 完成后，必须按模式执行：

- Easy Coding With Claude 联合模式
  - REVIEW → 实施结果报告 → 等待用户确认实施结果 → 用户确认后按项目模式进入实施后续流转
- 非联合模式 `初创项目`
  - 实施结果报告 → 等待用户确认实施结果 → 用户确认后初始化资产回补 → MEMORY → COMPLETE
- 非联合模式 `迭代项目`
  - 实施结果报告 → 等待用户确认实施结果 → 用户确认后 MEMORY → COMPLETE

实施结果报告输出后，必须停止：

- 同一轮不得生成短期记忆、不得执行长期记忆沉淀、不得输出 COMPLETE。
- 当前 Easy Coding 流程处于“等待实施结果确认”的续流状态。
- 下一轮用户点选“确认结果”，或回复“确认 / ok / 没问题 / 确认结果”，必须恢复当前 Easy Coding 流程，不要求用户再次显式写 `$easy-coding`。

Claude review 的 `accept`、host 自检通过、测试通过、构建通过都不等于用户确认实施结果。

用户确认实施结果后，联合模式仍按项目模式进入后续流程，不能停留在 REVIEW：

- `初创项目`
  - 若首次任务跳过了前置 INIT：初始化资产回补 → MEMORY → COMPLETE
  - 若已完成前置 INIT 或无需回补：MEMORY → COMPLETE
- `迭代项目`
  - MEMORY → COMPLETE

若 REVIEW 3 轮未收敛但用户明确确认当前实施结果，视为用户接受报告中的剩余风险，仍按上面的实施后续流转进入记忆；若用户要求继续调整或重新规划，则按其指令回到对应阶段。

## 4.9 实施完成报告

```markdown
[阶段：IMPLEMENT]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 技术实施完成

变更文件汇总：
1. {文件路径}：{变更说明}
2. {文件路径}：{变更说明}

注释自检：
- 结论：{已补充必要注释 / 本次无必要注释}
- 说明：{覆盖的关键意图、边界或风险；若无注释则说明无需补充的原因}

编码自检：
- 结论：{所有修改旧文件均保持原编码 / 新建文件均使用项目编码 / 无文件编码写入}
- 说明：{逐文件说明实际编码与已确认改动范围是否一致}

EASY-CODING 已完成代码编写，请您检查代码变动，如有不妥，请发送指令给我，如无问题请确认。

✅ 确认方式：若当前 agent 支持 `request_user_input` 或等价原生选择工具，必须弹出“确认结果”选择框；不支持时回复"确认" / "ok" / "开始" / "没问题"
✏️ 修改方式：直接告知修改意见

⚠️ 确认后将自动执行：
- 联合模式：Claude Review 结论已纳入本报告；确认后按项目模式继续实施后续流转，不停留在 REVIEW
- 初创项目：如本轮跳过了前置 INIT，则初始化资产回补 → MEMORY（短期记忆生成与长期沉淀检查）
- 迭代项目：进入 MEMORY（短期记忆生成与长期沉淀检查）
⚠️ 在用户确认结果前，禁止生成短期记忆。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

实施完成报告输出后必须等待用户确认结果。若当前 agent 暴露 `request_user_input` 或等价原生选择工具，必须调用工具，不能只输出文本。推荐选项：

- `确认结果 (Recommended)`：进入实施后续流转。
- `暂不进入后续流转`：保持 `[阶段：IMPLEMENT]` 等待，不生成记忆。

修复意见、补充说明或反馈意见必须通过客户端 free-form Other 或普通文本输入承接；不要手写成选项。

若当前 agent 不支持原生选择工具，才使用文本兜底。

---

# 【阶段 4.5】REVIEW - Claude 只读 Review（联合模式专属）

> 仅 Easy Coding With Claude 联合模式启用。普通 Easy-Coding 流程不进入本阶段。

## 4.10 进入条件

- IMPLEMENT 已完成
- 已有本轮已确认方案、变更文件清单、变更摘要、验证结果和 host 自检结论
- 当前仍处于联合模式

## 4.11 Review 执行规则

1. 读取并遵循 `flow/with-claude.md` 的 REVIEW 子流程。
2. 调用 With Claude 的 `post_implementation_review` flow 构建只读任务 packet。
3. 启动或尝试启动 With Claude worker：优先使用 `/Users/ysxiiun/.codex/skills/with-claude/scripts/run_claude_worker.py`，不可用时才使用源仓库 fallback。
4. 等待 Claude final worker contract；只有收到 final contract 后，才能把 `accept` / `fix` / `replan` 作为 Claude verdict。
5. Claude 只能读取和 review，禁止编辑、patch、格式化、提交、推送或发布。
6. host agent 负责合并 Claude verdict 与本地事实，并决定处理方式。
7. `fix` 若仍在已确认改动范围内，由 host agent 修复后重新 review。
8. `fix` 若超出已确认改动范围，不得自动修复，必须在实施结果报告中说明并等待用户指令。
9. REVIEW 最多 3 轮；3 轮仍未收敛时，结束 review，不新增阶段、不自动重走方案分析。
10. Claude 不可用时，降级为 host self-review，并在报告中标注 `Claude review unavailable`。

## 4.11.1 Claude 调用证据门禁

REVIEW 不得只输出一个简短 review 或 host self-review 结论来冒充 Claude review。REVIEW 结束前必须完成以下证据检查：

- `workflow_type` 必须为 `post_implementation_review`，`phase` 必须为 `post_code_review`，`expected_output_type` 必须为 `review`。
- 必须记录实际使用或尝试使用的 `run_claude_worker.py` 路径。
- 必须记录 Claude 调用状态：`executed` / `blocked` / `not_executed`。
- 必须记录是否收到 Claude final worker contract：`received` / `not_received`。
- 只有 `Claude 调用状态=executed` 且 `final contract=received` 时，才能使用 Claude 返回的 `accept` / `fix` / `replan`。
- 若未执行 Claude、启动失败、被权限或环境阻断、未收到 final contract、或只有 host 自检结论，则 verdict 必须映射为 `blocked`，并标注 `Claude review unavailable`；不得输出 `Claude accept`、`Claude 已 review 通过` 或等价表述。
- 若 Claude final contract 的 `status=needs_user_input`，不得产出最终 verdict；必须把问题与 host 疑问去重后一次性询问用户。

## 4.12 Verdict 处理

| verdict | 处理方式 |
|---|---|
| `accept` | 结束 REVIEW，在实施结果报告中说明 review 已通过 |
| `fix` | 若在已确认范围内，由 host 修复并重新 review，最多 3 轮 |
| `replan` | 不自动重回分析，在实施结果报告中说明 Claude 建议重新规划，等待用户决定 |
| `blocked` | 降级为 host self-review，并标注 `Claude review unavailable` |

## 4.13 Review 输出模板

```markdown
[阶段：REVIEW]

### Claude Review 第 {N}/3 轮
- Claude 调用状态：{executed / blocked / not_executed；若不是 executed，写 Claude review unavailable}
- wrapper path：{实际使用或尝试使用的 run_claude_worker.py 路径}
- workflow_type：post_implementation_review
- final contract：{received / not_received}
- worker status：{done / needs_user_input / blocked / unavailable}
- delegated reviewer：{started / skipped: 原因 / blocked: 原因 / unavailable}
- verdict 来源：{Claude final contract / blocked fallback(host self-review)}
- verdict：{accept / fix / replan / blocked}
- Claude 状态：{done / blocked；若 blocked，写 Claude review unavailable}
- 必须修复：{列表；无则写“无”}
- 可选优化：{列表；无则写“无”}
- 验证建议：{列表；无则写“无”}
- host 处理决策：{采纳并修复 / 不采纳并说明 / 结束 review 等待用户指令}
```

REVIEW 结束后，回到 `IMPLEMENT` 完成报告，统一输出整体实施与 review 结论。

---

# 【阶段 5】MEMORY - 记忆归档

> 仅在实施结果报告之后收到用户确认时进入；同一轮输出实施结果报告时不得进入本阶段。进入后在同一阶段内先生成短期记忆检查点，再执行长期记忆 `no-op / distill`，无需二次确认。

## 5.1 生成短期记忆检查点

- 先确保 `.easy-coding/memory/short/` 存在；目录缺失时按当前项目编码创建，不得因此跳过记忆归档。
- 每次用户确认实施结果后，必须为本轮任务新增 1 条 schema 2 短期记忆；不得用直接更新长期记忆替代。
- 先为本轮记忆生成一次 `memory_id`，格式固定为 `SM-<UUIDv7>`：
  - UUIDv7 使用当前 Unix 毫秒时间戳的低 48 位、版本位 `7`、RFC variant `10` 和 74 位安全随机数。
  - 必须使用宿主环境可用的安全随机能力；同一条记忆只生成一次，发生文件名碰撞时重新生成完整 UUIDv7。
  - 不得扫描短期目录计算 `001 / 002` 数字序号。
- 文件名固定为 `{memory_id}_{YYYYMMDD}_{smart_name}.md`：
  - `memory_id` 必须与 frontmatter `id` 完全一致，使用小写规范 UUID 文本。
  - 日期使用当前自然日 `YYYYMMDD`；`smart_name` 使用可读短横线或中文短语，避免空格和特殊符号。
- 内容必须读取并遵循 `templates/SHORT_MEMORY.md`，frontmatter 包含 `memory_schema / id / date / task_type / project_mode / domain / tags / related_files / commit / verification / memory_value / target_long`。
- 正文记录任务摘要、执行证据、业务记忆候选、技术记忆候选、不沉淀内容和关联记忆；`target_long` 只是候选建议，沉淀时仍须结合正文和当前代码复核。
- 写入后重新读取并验证：文件存在、`memory_schema: 2`、`id` 为 `SM-<UUIDv7>`、文件名前缀与 `id` 完全一致。验证失败时保持 `[阶段：MEMORY]` 并修复，不得计算归档指令。

旧 `{NNN}_{YYYYMMDD}_{smart_name}.md` 文件和 frontmatter `id=SM-YYYYMMDD-NNN` 继续兼容读取，不做破坏性重命名；只有本轮新检查点强制使用 UUIDv7。

## 5.2 冻结长期记忆指令

- 默认窗口配置为 `short_term_max=10`、`short_term_keep=5`。
- 若 `.easy-coding/config.yaml` 存在 `memory.short_term_max` / `memory.short_term_keep`，使用其中的非负整数覆盖默认值；无法解析的值忽略并使用默认值。
- 若 `short_term_keep > short_term_max`，报告非法配置并保持 `[阶段：MEMORY]`；不得沉淀、删除短期记忆或进入 `COMPLETE`。
- 只把 `memory_schema: 2` 的 Markdown 文件计入正常窗口；旧版无 schema 文件必须先按 `flow/memory-migration.md` 迁移。
- 对全部有效短期记忆稳定排序：
  1. frontmatter `date` 升序；
  2. 同日先排旧 `SM-YYYYMMDD-NNN` ID，再排 `SM-<UUIDv7>` ID，其他 ID 最后；
  3. 同类按 frontmatter `id` 升序；
  4. 仍相同时按文件名升序。
- 计算并在本次 MEMORY 处理中冻结以下指令；后续不得因文件变化重新分配候选：
  - `short_count`：有效短期记忆总数；
  - `action`：仅当 `short_count > short_term_max` 时为 `distill`，否则为 `no-op`；
  - `trim_count`：`distill` 时为 `short_count - short_term_keep`，否则为 `0`；
  - `candidate_files`：排序后最旧的 `trim_count` 个文件；
  - `kept_files`：其余保留文件；
  - `checkpoint_disposition`：本轮短期检查点属于 `candidate` 或 `kept`；若两者都未命中，说明冻结集合异常，必须保持 `[阶段：MEMORY]`。
- 默认配置下，10 条短期记忆必须 `no-op`；写入第 11 条后必须冻结最旧 6 条为候选、保留最新 5 条。

## 5.3 执行 `no-op / distill`

- `action=no-op`：不得修改 `.easy-coding/memory/long/MEMORY.md` / `BUSINESS.md` / `TECHNICAL.md`，不得删除任何短期记忆。
- `action=distill`：
  1. 只读取冻结的 `candidate_files`，不得沉淀或删除 `kept_files`。
  2. 按 frontmatter 和正文分拣：业务事实进入 `BUSINESS.md`，工程事实进入 `TECHNICAL.md`，普通流水、临时日志、一次性数据和无复用价值细节记为不沉淀。
  3. 写入长期记忆前加载并执行 `flow/memory-retirement.md`，只对候选命中的主题做定向 `delete / merge / deprecate` 检查。
  4. 更新 `MEMORY.md` 索引；一致内容合并来源，冲突内容以当前代码和用户最新确认为准，旧内容进入已淘汰记录。
  5. 长期三文件更新和不沉淀审计完成后，删除全部 `candidate_files`，包括没有进入长期记忆的候选；短期候选被消费后不得继续留在窗口中。

## 5.4 完成校验与输出

- `no-op` 完成前，确认本轮短期检查点仍存在且内容未被修改。
- `distill` 完成前，逐项确认所有 `candidate_files` 已不存在、所有 `kept_files` 仍存在；本轮检查点只有在 `checkpoint_disposition=candidate` 时才允许被消费。任一候选未消费或保留文件缺失时保持 `[阶段：MEMORY]` 并修复。
- 只有短期检查点与长期指令均处理完成后，才能进入 `COMPLETE`。

输出两种分支：

- `distill`：输出本轮短期文件、窗口配置、归档前总数、候选与保留文件、业务/技术主题、不沉淀原因、淘汰检查摘要、候选消费校验，然后进入 `COMPLETE`。
- `no-op`：输出本轮短期文件、窗口配置、当前总数和未写入长期记忆的原因，然后进入 `COMPLETE`。

---

# 【阶段 6】COMPLETE - 完成

```markdown
[阶段：COMPLETE]

🎉 任务全部完成！

{若为 Easy Coding With Claude 联合模式，补充：整体实施与 Review 结论、Review 轮次、已采纳修复、未收敛问题与剩余风险；若 Claude 不可用，明确标注 Claude pass unavailable。}

如需继续新任务，请描述需求。
```

---

# 🔄 中断处理

| 用户行为 | AI 响应 | 阶段跳转 |
|---------|--------|---------|
| "需求变了" / "重新想一下" | 停止当前操作，清空当前方案 | → ANALYSIS |
| "等等，我再看下" | 暂停等待，不输出方案 | 保持当前阶段 |
| "换个方案" / "有其他方式吗" | 输出备选方案 | → WAITING_CONFIRM |
| "检查 skill 规则" / "错了" | 立即停止，重置 | → INIT |
| 实施中变更请求 | 停止实施，输出变更方案 | → WAITING_CONFIRM |

中断输出规范：

```markdown
[阶段：ANALYSIS]（重置）

检测到需求变更，已清空原方案。

请描述变更后的需求，我将重新分析。
```

---

# 📎 附录：子流程与参考资料

## 子流程

- `flow/init.md`：迭代项目初始化与初创项目初始化资产回补
- `flow/startup-project.md`：初创项目完整执行流程
- `flow/with-claude.md`：Easy Coding With Claude 联合模式编排

## 参考资料

- `references/design/apple-design-reference.md`：前端视觉与交互设计参考
- `references/dev-spec/canonical-v1.md`：easy-dev-spec Canonical Spec v1 任务级消费协议
- `references/coding/`：未来语言 / 框架规范扩展目录

**默认原则：**
- 参考资料只在相关任务中按需读取
- 参考资料不会替代项目现有设计系统、编码规范或用户显式要求
