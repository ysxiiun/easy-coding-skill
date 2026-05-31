# Easy-Coding 智能编程助手

> AI 编程协作技能，让 AI 成为懂业务、记历史、守规范、能理解 Spec 的编程伙伴。

当前版本：`4.3.2`

## 版本号规则

- 第一位：重大功能更新大版本。
- 第二位：新功能或新优化迭代。
- 第三位：Bug 修复。

## 4.3.2 更新

- 修复 Dev-Spec 启动选择体验：扫描到候选后必须打印完整编号清单，不能只展示数量或状态。
- Dev-Spec 多选统一使用编号输入，支持 `1,3`、`1-3`、`全部/all` 和 `不加载/none`。
- 原生选择框只承接全部加载、不加载、暂不选择等真实分支，部分加载通过客户端 free-form Other 输入编号。
- 新增 `GEMINI.md`，补齐 Antigravity / Gemini 系 agent 的仓库适配说明。

## 4.3.1 更新

- 修正注释语种门禁：新增或修改注释必须匹配当前对话语种，无法识别对话语种时默认使用简体中文。
- 明确中文对话中不得默认写英文注释，除非用户明确要求英文或项目规范硬性要求英文。
- 新建文件需要作者署名时，统一使用 `${Agent Name} with Easy Coding`，由宿主 Agent 替换自己的名称。

## 4.3.0 更新

- 新增 `flow/memory-retirement.md`，在长期记忆沉淀时按需执行定向淘汰检查。
- 长期记忆会围绕本轮沉淀主题处理重复、冲突和过期内容，支持删除、合并和移入已淘汰记录。
- `ANALYSIS` 默认只读取 active 主题和有效记忆区，不读取已淘汰记录，避免上下文污染。

## 4.2.0 更新

- 升级记忆系统为 `MEMORY.md / BUSINESS.md / TECHNICAL.md` 三文件长期结构，`MEMORY.md` 只做索引与读取导航。
- 短期记忆新增 `memory_schema: 2` frontmatter 和业务/技术沉淀候选区，便于检索、分拣和审计。
- 新版短期记忆改为滑动窗口沉淀：达到 10 条后只沉淀窗口外旧短期，保留最新 5 条近期上下文。
- 新增旧版记忆渐进式迁移流程：INIT 阶段先探测并提示用户确认，确认后旧长期记忆自动拆分，旧短期记忆一次性沉淀并删除，迁移完成后自动进入分析。

## 4.1.3 更新

- 修正长期记忆沉淀规则：短期记忆达到阈值后全量沉淀，取消五条短期记忆留存策略。
- 长期记忆更新成功后，删除本次已沉淀的全部短期记忆文件。
- 统一沉淀阈值文案为“短期记忆 ≥10 条”。

## 4.1.2 更新

- 修复 Easy Coding With Claude 联合模式 REVIEW 软约束问题：IMPLEMENT 后不得只输出 host 自检式简短 review 来冒充 Claude review。
- REVIEW 必须实际调用或尝试调用 With Claude `post_implementation_review`，并记录 wrapper path、final contract、worker status 和 verdict 来源。
- 未执行 Claude、启动失败或未收到 final contract 时，只能降级为 `Claude review unavailable`，不得输出 Claude `accept`。

## 4.1.1 更新

- 优化原生选择框选项设计：选项必须映射真实下游分支，不再为凑数手写低价值反馈按钮。
- 确认类场景只保留“确认项 + 保持等待/安全否决项”，修改意见、反馈意见和补充说明统一交给客户端 free-form Other。
- Dev-Spec 超过 3 个候选时曾改为先选加载策略、再通过输入框按编号回复；该策略已在 4.3.2 收敛为统一编号多选。

## 4.1.0 更新

- 收敛阶段状态机：用户可见阶段只能使用 `INIT / ANALYSIS / WAITING_CONFIRM / IMPLEMENT / REVIEW / MEMORY_SHORT / MEMORY_LONG / COMPLETE`。
- 明确禁止 `[阶段：PLAN]`、`[阶段：VERIFY]`、`[阶段：TEST]`、`[阶段：DONE]`、`[阶段：REVIEW_BLOCKED]`；验证、测试、自检都属于 `IMPLEMENT` 内部工作。
- 修正记忆生成门禁：Claude review accept、测试通过、host 自检通过都不等于用户确认结果；实施结果报告输出后必须等待用户确认，确认后才进入 `MEMORY_SHORT`。
- 强化原生选择框能力探测：当前 agent 暴露 `request_user_input` 或等价工具时必须调用；不支持时才文本兜底。
- 压缩 `agents/openai.yaml` 的默认提示，避免 metadata 承载过多流程细节造成阶段污染。

## 4.0.2 更新

- 修复 Easy Coding With Claude 联合模式在“确认结果”后未进入记忆阶段的问题：已激活流程的确认续流不要求用户再次显式触发 `$easy-coding`。
- 明确 REVIEW 结束后的实施结果确认必须按项目模式进入后续流转，不能停留在 REVIEW 或普通对话确认。
- 明确 `post_v1_auto_init` 是初创项目第一版完成后的“初始化资产回补”，仅用于首次任务跳过前置 INIT 的场景。

## 4.0.1 更新

- 修复 Easy Coding With Claude 联合模式阶段串线：ANALYSIS 固定使用 Easy Coding 完整方案模板，不再因 With Claude `plan_mode` 退化为简单计划。
- 明确 Easy Coding 不存在 `[阶段：PLAN]`；With Claude 的 `workflow_type` / `phase` 只属于 worker task packet，不代表 Easy Coding 用户可见阶段。
- 明确 Claude 分析未返回时仍处于 `[阶段：ANALYSIS]`，只能汇报协作进展，不能提前进入 `WAITING_CONFIRM` 或误用 `[阶段：REVIEW]`。
- 收紧 `REVIEW` 进入条件：只能在 IMPLEMENT 完成，并具备变更清单、验证结果和 host 自检结论后进入。

## 4.0.0 更新

- 新增 Easy Coding With Claude 联合模式：仅当用户同时显式引用 Easy Coding 与 With Claude 时启用。
- 联合模式下，`INIT` / `ANALYSIS` / `REVIEW` 可调用 Claude 只读协作，`IMPLEMENT` 仍由本地 host agent 独立完成。
- 实施完成后自动进入 Claude 只读 Review；`fix` 最多循环 3 轮，未收敛时在实施结果报告中说明剩余问题并等待用户指令，不新增阻断阶段。
- 新增 `flow/with-claude.md`，以渐进式加载承载组合编排，避免污染普通 Easy-Coding 流程。

> 4.0.0 是 Easy Coding 与 With Claude 协同能力的首个大版本：普通 Easy-Coding 七阶段流程保持兼容，联合模式仅在双显式触发时启用。

## 3.1.2 更新

- 收敛 `ANALYSIS` 方案模板为“核心必填 + 条件展开”，小改动不再强制输出无关章节。
- 新增短期记忆模板，修正记忆阶段为“实施结果经用户确认后自动生成短期记忆并检查长期沉淀”。
- 收敛注释规范：保留必要注释，避免把所有公开方法都一刀切要求文档注释。

## 3.1.1 更新

- 明确区分“只读上下文采集”和“写入 / 修改类操作”。
- `INIT` / `ANALYSIS` 阶段必须主动扫描项目、读取配置与固定上下文，不需要用户先确认。
- 方案确认前禁止的是写入、修改、常规初始化写入、记忆写入、提交和推送，不是 `rg` / `ls` / 读取文件这类只读扫描；初创项目 `post_v1_auto_init` 初始化资产回补在用户确认第一版实现结果后自动执行。

## 3.1.0 更新

- `ANALYSIS` 技术方案新增逐文件“改动范围”表，明确改动文件、改动类型、文件编码和改动核心内容。
- 强化文件编码约束：修改旧文件必须保持原编码，新建文件必须套用项目编码，编码不明确时先等待用户确认。
- `WAITING_CONFIRM` 阶段收到用户修改意见后，必须输出“基于用户要求的改动提要”和“修改后的完整方案”，再等待确认。

## 3.0.0 更新

- 新增 `.easy-coding/spec/dev/` 运行时候选目录扫描，不再把 Dev-Spec 作为固定全局输入。
- 扫描到 Dev-Spec 后会先显式提示用户，并要求用户选择加载范围后再进入分析；当前策略以 4.3.2 的统一编号多选为准。
- 已选 Dev-Spec 仅对当前需求生效，不写入长期资产，也不会在后续需求中自动加载。
- 用户拒绝加载 Dev-Spec 且当前轮没有有效提示词或固定 Spec / Prototype 时，直接友好退出，不强行进入分析。
- `ANALYSIS` 输出会保留 Dev-Spec 候选文件、已选文件和未加载文件列表，便于复盘与控制。

---

## 产品简述

Easy-Coding 面向真实软件研发协作场景设计。它不只是代码生成器，而是带有阶段管控、项目记忆、规范约束和 Spec 驱动能力的协作式编程技能。

本次升级后，Easy-Coding 同时支持两类项目：

- **初创项目**：项目尚未形成成熟业务代码，允许基于 Spec 驱动第一版建设
- **迭代项目**：项目已有成型业务代码，继续按照既有系统做保守迭代

---

## 核心能力

### 1. 三层结构

Easy-Coding 采用“三层结构”组织规则，降低上下文污染：

- `SKILL.md`
  - 总控层
  - 负责全局约束、阶段定义、模式判定、输入发现、冲突处理、流程路由
- `agents/openai.yaml`
  - 接口层
  - 负责 Codex 侧展示名称、简述和默认调用提示词
- `flow/`
  - 流程层
  - 负责初始化、初创项目等场景流程
- `references/`
  - 参考层
  - 负责按需加载的设计规范与未来语言规范

### 2. Spec 驱动开发

Easy-Coding 支持在原有 `.easy-coding` 资产之外，按需读取以下输入：

- `.easy-coding/spec/Architect-Spec.md`
- `.easy-coding/spec/Product-Spec.md`
- `.easy-coding/spec/UI-Spec.md`
- `.easy-coding/prototype/Easy-UI-Prototype.md`
- `.easy-coding/prototype/` 下的 HTML 原型文件、assets 和 AI 原生生图图片
- `.easy-coding/spec/dev/` 下的候选 Dev-Spec 文档（仅扫描候选，不自动读取正文）

读取规则：

- 存在则读取，不存在则跳过
- 能从代码、Spec、Prototype 推断的信息不重复追问
- 当前提示词与 Spec 冲突时，必须提示用户拍板
- 若项目被识别为初创项目，且已发现可用 Spec / Prototype，系统会主动进入分析，不等待用户补充需求描述

关于 Dev-Spec：

- `spec/dev/` 是运行时候选目录，不属于固定全局 Spec 输入
- 扫描到候选后，Easy-Coding 会先显式告诉用户“已扫描到 Dev-Spec”
- 只有用户明确选择后，才会读取该文件并纳入当前需求分析；候选会按编号完整列出，支持 `1,3`、`1-3`、`全部/all` 和 `不加载/none`
- 已选 Dev-Spec 仅对当前需求生效，不写入长期资产，也不会在后续需求中自动加载
- 若用户拒绝加载，且当前轮又没有任何可支撑分析的有效提示词或固定 Spec / Prototype，Easy-Coding 会直接提示已准备好并退出当前流程

### 3. 初创项目与迭代项目

#### 初创项目

- 基本无成型业务代码
- 触发后会主动做空项目 / 近似空项目检测，不依赖用户口头声明
- 首次任务跳过前置初始化
- 若已存在 Spec / Prototype，会直接基于文档进入 ANALYSIS
- 若仅存在 `spec/dev/` 候选文档，会先输出完整编号清单并等待选择；可选择全部、不加载，或通过编号多选加载部分文件；选定后直接进入 ANALYSIS
- 严格按 Spec 推进第一版开发
- 第一版开发完成并经用户确认后，若首次任务跳过了前置 INIT，自动执行初始化资产回补，再进入记忆阶段

#### 迭代项目

- 已存在明确业务代码、页面、接口、服务或领域模型
- 保持原有七阶段主流程
- ANALYSIS 阶段会参考 Spec，但默认以现有代码现状为主，且必须先阅读相关代码后再给出实施级方案
- 若 Spec 与现有代码冲突，默认采用保守迭代策略

### 4. 长短期记忆系统

**短期记忆：任务级追溯**

```text
格式：001_20260324_新增用户登录功能.md
内容：frontmatter 元数据、任务摘要、执行证据、业务记忆候选、技术记忆候选、不沉淀内容、关联记忆
```

- 单条短期记忆创建后不修改，作为待沉淀任务记录保留
- frontmatter 必须包含 `memory_schema: 2`、任务类型、业务域、标签、关键文件、提交、验证状态、沉淀目标
- `target_long=BUSINESS / TECHNICAL / BOTH / NONE` 是未来进入滑动窗口外时的沉淀建议，沉淀时仍结合正文和当前代码复核
- 短期记忆同时承担近期细节滑动窗口和待沉淀缓冲区职责，支持前置 / 后续关联，并明确哪些内容不进入长期记忆

**长期记忆：三文件知识资产**

- 实施结果经用户确认后，自动生成短期记忆并检查长期沉淀条件
- 当短期记忆 ≥10 条时自动沉淀窗口外旧短期：按 `date → 文件名前缀序号 → 文件名` 排序，保留最新 5 条
- `MEMORY.md` 只做索引与读取导航
- `BUSINESS.md` 保存业务概念、字段语义、业务流程、业务规则、上下游契约、业务排障经验
- `TECHNICAL.md` 保存架构决策、接口决策、工程规则、实现模式、易错点、验证/发布经验
- 长期沉淀时按需加载 `flow/memory-retirement.md`，对本轮命中主题执行定向淘汰检查；已淘汰记录默认不进入分析上下文
- 长期沉淀成功后删除窗口外旧短期，短期目录保留最新 5 条近期细节上下文
- INIT 阶段发现旧版记忆时先提示用户确认；确认后按 `flow/memory-migration.md` 渐进迁移：旧长期拆分为三文件，旧短期一次性沉淀并删除，迁移完成后自动进入分析，后续新短期按滑动窗口运行
- 让 AI 在后续任务中持续复用历史知识

### 5. 前端任务增强

涉及页面、界面、交互、样式、组件、前端重构或视觉升级时：

- 必须优先启用 `frontend-skill`
- 若执行环境支持 agent / 子代理协作，应尽可能调度带前端 skill 的实现角色
- 按需读取 `references/design/apple-design-reference.md`
- 优先参考 `.easy-coding/prototype/` 下的 Prototype 文档、HTML、assets 与 images

**重要边界：**

- Prototype HTML 与图片仅供原型参考
- 不得直接复制到生产代码，也不得把图片当作生产设计稿
- 必须结合当前项目框架、组件体系、状态管理、路由和样式方案做深度再设计与适配
- 若交付目标是真实前端代码，必须完成真实接口对接或明确的接口契约接入，不能用 mock 页面冒充最终结果

### 6. With Claude 联合模式

当用户同时显式引用 Easy Coding 与 With Claude 时，Easy-Coding 会进入联合模式，并明确展示：

```text
已启动: Easy Coding With Claude 模式
```

联合模式的边界：

- `INIT`：Claude 只读参与项目摘要、规则和背景梳理，host agent 合并并负责写入。
- `ANALYSIS`：Claude 参与方案分析，但 Easy Coding 阶段仍固定为 `ANALYSIS`，最终必须输出完整技术方案模板，并写明 Claude 观点、采纳情况和冲突点。
- `IMPLEMENT`：Claude 不参与，仍由本地 host agent 按确认方案完成写入。
- `REVIEW`：实施完成且已有变更清单、验证结果和 host 自检结论后调用 Claude 只读 review，host agent 判断是否采纳并修复。
- `REVIEW` 最多 3 轮；未收敛时结束 review，在实施结果报告中说明剩余问题和风险，等待用户进一步指令。
- Claude 不可用时允许降级为 host-only，并在报告中标注 `Claude pass unavailable`。

阶段边界：

- Easy Coding 合法阶段只有 `INIT / ANALYSIS / WAITING_CONFIRM / IMPLEMENT / REVIEW / MEMORY_SHORT / MEMORY_LONG / COMPLETE`。
- `PLAN` 不是 Easy Coding 阶段；任何用户可见输出都不得写 `[阶段：PLAN]`。
- `VERIFY` / `TEST` / `DONE` / `REVIEW_BLOCKED` 也不是 Easy Coding 阶段；验证、自检和测试仍属于 `IMPLEMENT`，完成只能使用 `COMPLETE`。
- With Claude 的 `workflow_type` / `phase` 只是 worker task packet 字段，不等于 Easy Coding 阶段。
- Claude 分析还在运行时，进度更新仍使用 `[阶段：ANALYSIS]`，只能汇报协作进展和已读证据；收到 `done / blocked / needs_user_input` 后才合并输出完整方案。

---

## 工作流程

### 统一七阶段

```text
INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT → MEMORY_SHORT → MEMORY_LONG → COMPLETE
```

联合模式会在 `IMPLEMENT` 后增加一个只读 Review 插槽：

```text
INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT → REVIEW → 实施结果报告 → 用户确认结果 → 按项目模式进入初始化资产回补或 MEMORY_SHORT → MEMORY_LONG → COMPLETE
```

### 初创项目流程

```text
模式判定 → 空项目检测 → 发现 Spec / Prototype → 跳过前置 INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT
→ 用户确认第一版结果 → 初始化资产回补 → MEMORY_SHORT → MEMORY_LONG → COMPLETE
```

实施结果报告后的“确认结果”属于已激活流程续流，不要求用户再次显式引用 `$easy-coding`；但必须先等待用户确认结果，不能在输出实施结果报告的同一轮生成记忆。

详细规则见：

- `flow/startup-project.md`
- `flow/init.md`

### 迭代项目流程

```text
模式判定 → INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT → MEMORY_SHORT → MEMORY_LONG → COMPLETE
```

---

## 触发方式

**仅支持显式加载：**

- `使用 $easy-coding ...`
- `加载 easy-coding ...`
- `使用 Easy Coding skill ...`

若需要联合 With Claude，必须同时显式引用两个 skill：

- `使用 $easy-coding 和 $with-claude ...`
- `加载 Easy Coding skill，并搭配 With Claude skill ...`

普通任务描述不会自动加载本 skill，例如“帮我实现”“帮我修改”“我有一个需求”等都只按普通 agent 流程处理，除非用户同时显式点名 Easy Coding。

### 跳过 skill 流程

若已经显式加载 Easy Coding，但当前轮不希望进入 Easy-Coding 的阶段流程，可在消息开头写入 `#no-coding`。

例如：

- `#no-coding 帮我看下当前分支状态`
- `#no-coding 帮我整理这个报错原因`

---

## 目录结构

```text
easy-coding/
├── agents/
│   └── openai.yaml
├── SKILL.md
├── flow/
│   ├── init.md
│   ├── startup-project.md
│   ├── memory-migration.md
│   ├── memory-retirement.md
│   └── with-claude.md
├── references/
│   ├── design/
│   │   └── apple-design-reference.md
│   ├── scenarios/
│   │   └── easy-coding-with-claude.md
│   └── coding/
│       └── README.md
├── templates/
│   ├── SOUL.md
│   ├── RULES.md
│   ├── ABSTRACT.md
│   ├── MEMORY.md
│   ├── BUSINESS.md
│   ├── TECHNICAL.md
│   ├── SHORT_MEMORY.md
│   └── CLAUDE_TASK_PACKET.md
└── .easy-coding/
    ├── SOUL.md
    ├── RULES.md
    ├── ABSTRACT.md
    ├── spec/
    ├── prototype/
    │   ├── Easy-UI-Prototype.md
    │   ├── index.html
    │   ├── assets/
    │   └── images/
    └── memory/
        ├── short/
        └── long/
            ├── MEMORY.md
            ├── BUSINESS.md
            └── TECHNICAL.md
```

---

## 关键约束

- 方案未确认前，禁止执行代码变更、常规初始化写入、实施后记忆写入、提交或推送；旧版记忆兼容迁移仅限 `.easy-coding/memory/`，必须在 INIT 阶段提示并获得用户确认后按 `flow/memory-migration.md` 渐进触发；初创项目初始化资产回补按 `post_v1_auto_init` 流程，在用户确认第一版实现结果后自动执行
- 只读上下文采集不属于禁止范围；`INIT` / `ANALYSIS` 阶段必须主动扫描项目、读取配置、读取固定上下文并基于真实现状输出方案
- 无论变更大小，必须重新确认
- 每次回复必须标注当前阶段
- 不允许输出 `[阶段：PLAN]`、`[阶段：VERIFY]`、`[阶段：TEST]`、`[阶段：DONE]`、`[阶段：REVIEW_BLOCKED]`；等待 Claude 分析时仍属于 `[阶段：ANALYSIS]`；`REVIEW` 只能在 IMPLEMENT 完成后出现
- 当前 agent 暴露 `request_user_input` 或等价原生选择工具时，确认执行方案、确认结果和 Dev-Spec 选择必须调用工具；不支持时才文本兜底
- 原生选择框选项必须映射真实下游分支，不得与客户端 free-form Other 重叠；修改意见、反馈意见和补充说明不要手写成按钮
- 实施结果报告输出后必须等待用户确认结果；Claude review accept、测试通过、host 自检通过都不等于用户确认结果
- ANALYSIS 方案必须按“核心必填 + 条件展开”输出；无关条件章节不要硬填
- ANALYSIS 方案必须包含“改动范围”表，逐文件说明改动文件、改动类型、文件编码和改动核心内容
- ANALYSIS 方案必须包含“待用户决策”和“验证与验收”，冲突存在时先等待用户拍板
- 修改旧文件必须保持原文件编码；新建文件必须套用项目编码；用户可在确认前修改任一文件的编码要求
- 编码时必须补充必要注释；新增或修改注释必须匹配当前对话语种，无法识别对话语种时默认使用简体中文；若用户明确指定注释语言，以用户要求为准
- 新建文件若因项目模板、同类文件惯例或用户要求需要作者署名，必须写为 `${Agent Name} with Easy Coding`
- ANALYSIS 方案必须列出注释策略；IMPLEMENT 完成后必须回看 diff 做注释语种、作者署名和必要性自检，已补充或无需补充都要说明原因
- WAITING_CONFIRM 阶段若用户提出修改意见，下一轮必须输出“基于用户要求的改动提要”和“修改后的完整方案”，不能只回复摘要
- 当前提示词与 Spec 冲突时，必须先询问用户
- Prototype HTML 与图片永远只作为参考输入，不直接当作生产实现或生产设计稿
- Apple 设计规范只是默认高质量前端基线，不覆盖项目既有设计系统或用户显式要求

---

## 参考资料

### 设计参考

- `references/design/apple-design-reference.md`
  - 用途：前端视觉与交互参考
  - 读取策略：前端相关任务默认参考；若用户没有特殊风格要求，默认采用 Apple 风格质感作为视觉基线

### 编码参考

- `references/coding/`
  - 预留给 Java、TypeScript、Go、Python 等语言 / 框架规范
  - 不默认加载，按任务类型按需扩展

---

## 最佳实践

1. 初创项目尽量先准备 Product / UI / Architect Spec，再让 Easy-Coding 按 Spec 推进第一版开发。
2. 迭代项目中，如果历史 Spec 与现状代码已经偏离，优先让 Easy-Coding 先说明冲突，而不是直接强推 Spec。
3. 前端任务尽量同时提供 UI-Spec、Prototype 文档、原型 HTML 或 AI 原型图片，能显著提升分析质量。
4. 不要把 Prototype HTML 或图片当成最终页面代码 / 生产设计稿；真正实现时应结合工程环境重新设计与适配。
5. 若任务目标是生产级前端交付，必须要求 AI 明确页面映射、组件拆解、数据来源和接口对接方案；只有 mock 页面不算完成。
6. 若仓库中已经有代码，ANALYSIS 必须先基于实际代码给出现状和修改方案；只复述需求不算合格分析。

---

## 总结

Easy-Coding 的目标不是替代工程师，而是让 AI 更像一名有流程感、能守边界、懂上下文、会参考 Spec 的协作伙伴：

- **懂业务**：通过记忆与 Spec 理解项目背景
- **守规范**：自动遵守编码规则与阶段约束
- **可追溯**：方案、变更、记忆都有明确记录
- **可控制**：专家全程把关，避免 AI 擅自推进
