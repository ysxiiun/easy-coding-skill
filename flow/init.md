# 初始化流程

> 本文件由 `SKILL.md` 按需加载执行。
> 支持两种语义：常规初始化 `interactive_init` 与初创项目第一版完成后的初始化资产回补 `post_v1_auto_init`。

---

## 进入条件

- `interactive_init`
  - 项目被判定为 `迭代项目`
  - `.easy-coding/` 资产不完整
  - 用户明确回复“确认”开始初始化
- `post_v1_auto_init`
  - 项目被判定为 `初创项目`
  - 首次任务为了先交付第一版而跳过了前置 INIT
  - 第一版开发已经完成并得到用户确认
  - 需要自动补齐 `.easy-coding/` 基础资产并生成项目摘要

---

## 模式差异

| 维度 | interactive_init | post_v1_auto_init |
|---|---|---|
| 触发时机 | 首次使用或迭代项目补齐资产 | 初创项目第一版开发完成后，且该首次任务曾跳过前置 INIT |
| 交互方式 | 逐步展示并与用户确认 | 自动执行，不再逐文件二次确认 |
| 信息来源 | 项目现状 + 用户补充 | 已生成代码 + Spec + Prototype + 项目现状 |
| 覆盖策略 | 创建或更新缺失资产 | 回补基础资产，不覆盖已确认成果 |

---

## 执行原则

1. 只补齐 `.easy-coding/` 基础资产，不改写业务代码。
2. 初始化资产回补时，不覆盖以下内容：
   - `.easy-coding/spec/` 下已有 Spec
   - `.easy-coding/prototype/` 下已有 Prototype 文档、HTML、assets 与 images
   - 用户已确认的代码成果
3. 若以 `post_v1_auto_init` 运行，`ABSTRACT.md` 必须结合“现有代码 + Spec + Prototype”生成，而不是按空项目逻辑草率创建。
4. `.easy-coding/spec/dev/` 下的 Dev-Spec 候选仅属于运行时按需输入，不纳入初始化资产回补的固定 Spec 集合，也不写入长期资产。
5. 若当前处于 Easy Coding With Claude 联合模式，读取 `flow/with-claude.md` 的 INIT 协作规则；Claude 只做只读草拟，最终合并与写入仍由 host agent 完成。

---

## 初始化文件清单

| 序号 | 文件/目录 | 来源 | 说明 |
|---|---|---|---|
| 1 | `.easy-coding/` 目录 | 新建 | 项目配置根目录 |
| 2 | `.easy-coding/memory/` 目录 | 新建 | 记忆存储目录 |
| 3 | `.easy-coding/memory/short/` 目录 | 新建 | 短期记忆目录 |
| 4 | `.easy-coding/memory/long/` 目录 | 新建 | 长期记忆目录 |
| 5 | `.easy-coding/SOUL.md` | `templates/SOUL.md` | 项目灵魂文件 |
| 6 | `.easy-coding/RULES.md` | `templates/RULES.md` | 编码规范文件 |
| 7 | `.easy-coding/ABSTRACT.md` | 分析生成 | 架构摘要文件 |
| 8 | `.easy-coding/memory/long/MEMORY.md` | `templates/MEMORY.md` | 长期记忆文件 |

---

## 执行步骤

### 步骤 1：创建目录结构

创建以下目录：

```text
.easy-coding/
└── memory/
    ├── short/
    └── long/
```

详细步骤：
1. 创建 `.easy-coding/memory/short/`
2. 创建 `.easy-coding/memory/long/`
3. 验证目录创建成功

---

### 步骤 2：初始化 SOUL.md

来源：`templates/SOUL.md`

执行要求：
1. 读取模板并写入 `.easy-coding/SOUL.md`
2. 推断并填充项目名称、技术栈、团队约定、禁止事项
3. `interactive_init` 模式下向用户展示并确认
4. `post_v1_auto_init` 模式下自动生成，并在完成报告中统一摘要说明
5. 联合模式下，可先让 Claude 基于项目现状只读草拟项目定位、团队约定和禁止事项；host agent 必须说明 Claude 草拟要点与采纳情况

---

### 步骤 3：初始化 RULES.md

来源：`templates/RULES.md`

执行要求：
1. 检测项目语言与主要技术栈
2. 生成对应语言的基础编码规范
3. `interactive_init` 模式下展示语言检测结果并等待确认
4. `post_v1_auto_init` 模式下自动填充，不额外阻断
5. 联合模式下，可先让 Claude 基于项目语言、框架、编码习惯只读提出规范建议；host agent 必须按现有代码证据合并，不允许 Claude 覆盖已确认约束

---

### 步骤 4：初始化 ABSTRACT.md

来源：根据项目实际分析生成

#### 4.1 分析输入

- 项目代码与目录结构
- 配置文件与构建文件
- `.easy-coding/spec/Architect-Spec.md`
- `.easy-coding/spec/Product-Spec.md`
- `.easy-coding/spec/UI-Spec.md`
- `.easy-coding/prototype/Easy-UI-Prototype.md`
- `.easy-coding/prototype/` 下的 HTML 原型文件、assets 与 images

不默认吸收：

- `.easy-coding/spec/dev/` 下的候选 Dev-Spec 文档

#### 4.2 生成原则

**有源码文件时：**
- 生成完整架构摘要
- 说明核心模块、技术栈、流程、目录索引

**仅有配置文件时：**
- 生成简化版摘要
- 标明模块结构与核心流程待首次任务补充

**几乎为空时：**
- 生成最简版摘要
- 标明项目待初始化与后续补充项

**post_v1_auto_init 特别要求：**
- 必须优先吸收第一版代码成果和 Spec 结论
- 必须把 Prototype 视为参考输入，而非生产实现
- 不得因初始化资产回补而回退已确认实现

#### 4.3 交互要求

- `interactive_init`：向用户展示摘要并确认
- `post_v1_auto_init`：自动生成，在完成报告中说明数据来源和摘要结论
- 联合模式：补充展示 `Claude 初始化协作`，说明 Claude 状态、草拟要点、采纳情况与冲突摘要

---

### 步骤 5：初始化 MEMORY.md

来源：`templates/MEMORY.md`

执行要求：
1. 拷贝模板到 `.easy-coding/memory/long/MEMORY.md`
2. 预填充日期字段
3. 验证文件创建成功

---

## 初始化完成

输出完成报告：

```markdown
[阶段：INIT]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 初始化全部完成！

已创建/更新的文件：
1. ✅ .easy-coding/ 目录结构
2. ✅ .easy-coding/SOUL.md - 项目灵魂
3. ✅ .easy-coding/RULES.md - 语言编码规范
4. ✅ .easy-coding/ABSTRACT.md - 架构摘要
5. ✅ .easy-coding/memory/long/MEMORY.md - 长期记忆

说明：
- 当前模式：{interactive_init/post_v1_auto_init}
- 初始化资产回补不会覆盖既有 Spec、Prototype 和已确认代码成果
- Claude 初始化协作：{非联合模式填“不适用”；联合模式填 Claude 状态、采纳情况与冲突摘要}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 返回 SKILL.md

初始化完成后，AI 返回 `SKILL.md` 继续执行：

- 常规初始化：回到 INIT 背景摘要，再进入 ANALYSIS
- 初创项目初始化资产回补：直接进入 MEMORY_SHORT
