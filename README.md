# Easy-Coding 智能编程助手

> AI 编程协作技能，让 AI 成为懂业务、记历史、守规范、能理解 Spec 的编程伙伴。

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
- `Easy-UI-Prototype.md` 中引用的每一个 HTML 原型文件

读取规则：

- 存在则读取，不存在则跳过
- 能从代码、Spec、Prototype 推断的信息不重复追问
- 当前提示词与 Spec 冲突时，必须提示用户拍板
- 若项目被识别为初创项目，且已发现可用 Spec / Prototype，系统会主动进入分析，不等待用户补充需求描述

### 3. 初创项目与迭代项目

#### 初创项目

- 基本无成型业务代码
- 触发后会主动做空项目 / 近似空项目检测，不依赖用户口头声明
- 首次任务跳过前置初始化
- 若已存在 Spec / Prototype，会直接基于文档进入 ANALYSIS
- 严格按 Spec 推进第一版开发
- 第一版开发完成并经用户确认后，自动执行初始化回补，再进入记忆阶段

#### 迭代项目

- 已存在明确业务代码、页面、接口、服务或领域模型
- 保持原有七阶段主流程
- ANALYSIS 阶段会参考 Spec，但默认以现有代码现状为主，且必须先阅读相关代码后再给出实施级方案
- 若 Spec 与现有代码冲突，默认采用保守迭代策略

### 4. 长短期记忆系统

**短期记忆：任务级追溯**

```text
格式：001_20260324_新增用户登录功能.md
内容：任务概述、技术方案、变更文件、问题与解法
```

- 纯追加模式，保留时间线
- 记录变更、问题与决策
- 支持前置 / 后续关联

**长期记忆：知识沉淀**

- 当短期记忆达到阈值时自动沉淀
- 提炼架构决策、技术选型、可复用经验、业务规则
- 让 AI 在后续任务中持续复用历史知识

### 5. 前端任务增强

涉及页面、界面、交互、样式、组件、前端重构或视觉升级时：

- 必须优先启用 `frontend-skill`
- 若执行环境支持 agent / 子代理协作，应尽可能调度带前端 skill 的实现角色
- 按需读取 `references/design/apple-design-reference.md`
- 优先参考 `.easy-coding/prototype/Easy-UI-Prototype.md` 与其引用 HTML

**重要边界：**

- Prototype HTML 仅供原型参考
- 不得直接复制到生产代码
- 必须结合当前项目框架、组件体系、状态管理、路由和样式方案做深度再设计与适配
- 若交付目标是真实前端代码，必须完成真实接口对接或明确的接口契约接入，不能用 mock 页面冒充最终结果

---

## 工作流程

### 统一七阶段

```text
INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT → MEMORY_SHORT → MEMORY_LONG → COMPLETE
```

### 初创项目流程

```text
模式判定 → 空项目检测 → 发现 Spec / Prototype → 跳过前置 INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT
→ 用户确认第一版结果 → 初始化回补 → MEMORY_SHORT → MEMORY_LONG → COMPLETE
```

详细规则见：

- `flow/startup-project.md`
- `flow/init.md`

### 迭代项目流程

```text
模式判定 → INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT → MEMORY_SHORT → MEMORY_LONG → COMPLETE
```

---

## 触发方式

**触发词：**

- "帮我完成..."
- "帮我做..."
- "我有一个需求..."
- "帮我实现..."
- "帮我修改..."
- "帮我修复..."
- "帮我优化..."
- `ec` / `EC` / `easy-coding`

### 跳过 skill 流程

若当前轮不希望进入 Easy-Coding 的阶段流程，可在消息开头写入 `#no-coding`。

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
│   └── startup-project.md
├── references/
│   ├── design/
│   │   └── apple-design-reference.md
│   └── coding/
│       └── README.md
├── templates/
└── .easy-coding/
    ├── SOUL.md
    ├── RULES.md
    ├── ABSTRACT.md
    ├── spec/
    ├── prototype/
    └── memory/
```

---

## 关键约束

- 方案未确认前，禁止执行代码变更
- 无论变更大小，必须重新确认
- 每次回复必须标注当前阶段
- 编码时必须补充必要注释，默认使用当前对话语言；若用户明确指定注释语言，以用户要求为准
- 当前提示词与 Spec 冲突时，必须先询问用户
- Prototype HTML 永远只作为参考输入，不直接当作生产实现
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
3. 前端任务尽量同时提供 UI-Spec、Prototype 文档和原型 HTML，能显著提升分析质量。
4. 不要把 Prototype HTML 当成最终页面代码；真正实现时应结合工程环境重新设计与适配。
5. 若任务目标是生产级前端交付，必须要求 AI 明确页面映射、组件拆解、数据来源和接口对接方案；只有 mock 页面不算完成。
6. 若仓库中已经有代码，ANALYSIS 必须先基于实际代码给出现状和修改方案；只复述需求不算合格分析。

---

## 总结

Easy-Coding 的目标不是替代工程师，而是让 AI 更像一名有流程感、能守边界、懂上下文、会参考 Spec 的协作伙伴：

- **懂业务**：通过记忆与 Spec 理解项目背景
- **守规范**：自动遵守编码规则与阶段约束
- **可追溯**：方案、变更、记忆都有明确记录
- **可控制**：专家全程把关，避免 AI 擅自推进
