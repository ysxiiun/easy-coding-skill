# 初创项目执行流程

> 本文件是 `easy-coding` 的子流程文档，不单独作为 skill。
> 当 `SKILL.md` 判定当前项目为 `初创项目` 时，必须读取并遵循本文件。

---

## 进入条件

- 当前项目被判定为 `初创项目`
- 项目几乎无成型业务代码，只有脚手架、配置、README、空目录、示例文件或占位代码
- 用户本轮需求目标是基于 Spec 推进第一版产品或功能落地

---

## 核心原则

1. `初创项目` 首次任务跳过前置 INIT 阻断。
2. 第一版开发必须严格以 Spec 为主依据。
3. 可选输入缺失时可以跳过，但关键实现信息缺失时必须追问或显式标记假设。
4. Prototype HTML 与图片仅供原型参考，不得直接复制到生产代码或当作生产设计稿。
5. 第一版开发完成并经用户确认后，必须自动执行一次初始化资产回补，再进入记忆阶段；这是补齐 `.easy-coding/` 资产，不是流程开头的前置 INIT。
6. 若已存在可用 Spec / Prototype 输入，必须主动进入分析，不等待用户重新描述需求。
7. 若交付的是前端工程代码，必须完成真实工程适配与接口对接，不能用原型页或 mock 页面冒充交付结果。
8. 若当前处于 Easy Coding With Claude 联合模式，读取 `flow/with-claude.md`；Claude 只在 ANALYSIS、初始化资产回补和 REVIEW 中做只读协作，IMPLEMENT 仍由 host agent 独立完成。

---

## 输入优先级

进入 ANALYSIS 前，优先吸收以下输入：

1. 用户当前提示词
2. 当前项目代码、目录结构、配置文件
3. `.easy-coding/spec/Architect-Spec.md`
4. `.easy-coding/spec/Product-Spec.md`
5. `.easy-coding/spec/UI-Spec.md`
6. `.easy-coding/prototype/Easy-UI-Prototype.md`
7. `.easy-coding/prototype/` 下的 HTML 文件、assets 和 images
8. 扫描 `.easy-coding/spec/dev/` 下的 Markdown 候选文件（仅扫描文件名，不自动读取正文）

读取规则：

- 存在则读取，不存在则跳过
- 能从代码、配置、Spec、Prototype 推断的信息不要反问用户
- 若关键信息会影响数据模型、接口、页面结构、核心交互或技术路线，不能脑补，必须停下来确认
- 若发现 Dev-Spec 候选文件，先按相对路径字典序输出完整编号清单；用户可回复 `1,3`、`1-3`、`全部/all` 或 `不加载/none`。原生选择工具可用时仍必须调用工具承接 `全部加载`、`不加载`、`暂不选择/保持等待` 等真实分支，部分加载和多选通过客户端 free-form Other 输入编号；用户未选择前不读取正文

## 自动进入分析

当满足以下条件时，必须直接进入 ANALYSIS，而不是等待用户继续输入：

1. 项目已判定为 `初创项目`
2. 已检测到空项目或近似空项目信号
3. 至少存在以下任一输入：
   - `.easy-coding/spec/Architect-Spec.md`
   - `.easy-coding/spec/Product-Spec.md`
   - `.easy-coding/spec/UI-Spec.md`
   - `.easy-coding/prototype/Easy-UI-Prototype.md`
   - `.easy-coding/spec/dev/` 下存在候选 Markdown 文档

此时的默认行为是：

- 把已发现的 Spec / Prototype 视为本轮主要需求来源
- 若仅发现 Dev-Spec 候选，先输出完整编号清单并等待用户选择；可选择全部、不加载，或通过编号多选加载部分文件；选定后直接进入分析
- 先完成方案分析
- 只有在 Spec 无法支撑关键实现判断时，才向用户追问缺口

若未发现任何可用 Spec / Prototype 输入，才提示用户补充需求或准备 Spec。

---

## 阶段路由

### 1. INIT

- 跳过前置 INIT 阻断
- 不要求先补齐 `.easy-coding/` 基础资产
- 直接进入 ANALYSIS

### 2. ANALYSIS

输出方案前必须完成：

1. 识别本次任务是否涉及前端开发
2. 识别本次实际使用了哪些 Spec / Prototype 输入
3. 若已扫描到 Dev-Spec 候选但未选择，先输出完整编号清单，并优先用原生选择框等待用户选择是否加载；部分加载通过 free-form Other 输入编号
4. 判断用户提示词与 Spec / Dev-Spec 是否冲突
5. 若用户没有额外描述需求，默认以 Spec / Prototype / 已选 Dev-Spec 作为需求来源
6. 若涉及前端：
   - 优先启用 `frontend-skill`
   - 按需读取 `references/design/apple-design-reference.md`
   - 明确说明 Prototype HTML 与图片只作参考，不直接用于生产实现
7. 若处于联合模式：
   - 调用 With Claude 做只读并行分析，固定使用 `readonly_analysis` / `phase=analysis` / `expected_output_type=analysis`
   - Claude 未返回最终 worker contract 前，用户可见输出仍保持 `[阶段：ANALYSIS]`，不能提前输出正式方案或进入 `WAITING_CONFIRM`
   - 按 `SKILL.md` 主模板输出 `### Claude 协作`
   - 明确写出 Claude 观点、采纳情况和冲突点

**若提示词与 Spec 冲突：**
- 必须先输出冲突摘要
- 必须等待用户拍板
- 在用户拍板前，不得进入 IMPLEMENT

**若 Spec 信息不足：**
- 必须追问，或在方案中显式标注“当前假设”
- 不得伪装为已确认结论

**若用户未输入额外需求，但 Spec 已足够：**
- 直接输出首版技术方案
- 不要先回复“请描述您的需求”
- 若仓库里已有脚手架、基础模块、配置或局部实现，仍必须先阅读这些代码，再给出方案
- 输出的必须是可实施方案，不是“后续分析计划”

**若用户拒绝加载 Dev-Spec：**
- 若当前轮没有任何足以支撑分析的有效提示词，且没有固定 Spec / Prototype 可补足上下文，直接输出：
  - `未识别到用户意图, Easy Coding 已准备好, 请随时向我发问`
- 当前轮到此结束，不进入 `WAITING_CONFIRM`，不输出技术方案
- 若仍有足够上下文支撑分析，则继续按现有分析流程执行

**若任务涉及前端工程实现：**
- 必须先输出“原型到工程实现映射”
- 必须逐页说明真实数据来源、接口对接方式和状态管理方案
- 若当前只有 mock 数据或原型静态页面，不能把它们当作最终交付

### 3. WAITING_CONFIRM

与主流程一致：

- 方案输出后必须进入阻断状态
- 用户未明确确认前，不得进入 IMPLEMENT

### 4. IMPLEMENT

实施规则：

1. 严格按已确认 Spec 与方案落地第一版开发
2. 若是前端实现：
   - 优先遵循 `frontend-skill`
   - 参考 Apple 设计规范
   - 参考 Prototype 文档、HTML、assets 与 images
   - 但必须结合当前框架、工程结构、组件体系、状态管理、路由和样式方案做深度适配
   - 必须对接真实接口或已确认的接口契约
   - 不得直接复制 Prototype HTML、转贴 Prototype 图片或保留整页 mock 数据作为最终实现
3. 若用户在实施中变更需求，必须回到 WAITING_CONFIRM
4. 联合模式下，IMPLEMENT 期间不调用 Claude；第一版实现完成后先进入 REVIEW，再输出实施结果报告

### 5. 初始化资产回补

当第一版开发完成、联合模式 REVIEW 已结束（如适用）、且用户确认实现结果后，必须自动执行：

1. 读取 `flow/init.md`
2. 以 `post_v1_auto_init` 语义回补 `.easy-coding/` 资产
3. 生成或更新：
   - `.easy-coding/SOUL.md`
   - `.easy-coding/RULES.md`
   - `.easy-coding/ABSTRACT.md`
   - `.easy-coding/memory/short/`
   - `.easy-coding/memory/long/MEMORY.md`
   - `.easy-coding/memory/long/BUSINESS.md`
   - `.easy-coding/memory/long/TECHNICAL.md`
4. 不覆盖已有 Spec、Prototype 和已确认代码成果
5. 回补长期记忆三文件只代表初始化资产可用，不代表本轮任务已沉淀长期记忆
6. 联合模式下，回补过程按 `flow/with-claude.md` 的 INIT 协作规则执行：Claude 只读草拟，host agent 合并和写入

### 6. MEMORY_SHORT → MEMORY_LONG → COMPLETE

初始化资产回补完成后：

1. 进入 `MEMORY_SHORT`
2. 必须先新增本轮 schema 2 短期记忆并验证文件已落盘
3. 再进入 `MEMORY_LONG` 做长期沉淀检查
4. 最后输出 `COMPLETE`

---

## 输出要求

初创项目的 ANALYSIS 必须遵循 `SKILL.md` 2.5 的“核心必填 + 条件展开”主模板，不重复输出主模板已经要求的 `项目模式`、`Spec 输入应用` 和 `冲突摘要`。

主模板中的 `冲突摘要` 对初创项目同样完整适用，必须覆盖：
- 提示词 vs Spec
- 提示词 vs Dev-Spec
- Dev-Spec vs 固定 Spec
- Dev-Spec vs 现有代码
- Spec vs 现有代码

初创项目必须额外补充：

```markdown
### 当前假设
- {若有则列出；无则填“无”}
```

若初创项目当前已有脚手架或部分代码，还必须补充：

```markdown
### 当前工程现状
- 目录 / 模块现状：{基于实际代码}
- 已有能力：{当前已经具备的部分}
- 缺口：{距离首版可用还缺什么}
```

若涉及前端实现，还必须补充：

```markdown
### 前端实现说明
- frontend-skill：{已启用/应启用}
- Apple 设计参考：{已使用/未使用}
- Prototype 参考：{文档/HTML/图片/assets 的使用情况}
- 说明：Prototype HTML 与图片仅供原型参考，不得直接用于生产实现。
```

---

## 完成定义

`初创项目` 只有在以下全部完成后，才能视为本轮流程完成：

1. 第一版开发完成
2. 用户确认实现结果
3. 初始化资产回补完成
4. 短期记忆生成完成
5. 长期记忆检查完成
6. 输出 COMPLETE

若处于 Easy Coding With Claude 联合模式，第一版开发还必须完成 Claude 只读 REVIEW。

- 若 3 轮 review 仍未收敛，在实施结果报告中说明剩余问题并等待用户指令，不自动进入记忆阶段。
- 用户明确确认当前结果时，视为接受剩余风险并继续初始化资产回补与记忆流程。
