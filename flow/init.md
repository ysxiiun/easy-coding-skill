# 初始化流程

> 本文件由 SKILL.md 渐进式加载执行
> 当用户确认开始初始化后触发

---

## 进入条件

- SKILL.md 检测到项目初始化不完全
- 用户明确回复"确认"开始初始化

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

**创建以下目录：**
```
.easy-coding/
└── memory/
    ├── short/
    └── long/
```

**详细步骤：**
1. 使用 `mkdir -p` 创建 `.easy-coding/memory/short/`
2. 使用 `mkdir -p` 创建 `.easy-coding/memory/long/`
3. 使用 `list_dir` 验证目录创建成功

**完成反馈：**
```
✅ 步骤 1/5 完成：目录结构创建
   - .easy-coding/ ✅
   - .easy-coding/memory/short/ ✅
   - .easy-coding/memory/long/ ✅
```

---

### 步骤 2：初始化 SOUL.md

**来源：** `templates/SOUL.md`

**详细步骤：**
1. 使用 `read_file` 读取 `templates/SOUL.md`
2. 拷贝内容到 `.easy-coding/SOUL.md`
3. 根据项目信息填充以下内容：
   - **项目名称**：从项目目录名或用户确认获取
   - **主要技术栈**：通过 `list_dir` 和文件检测推断（pom.xml=Java, package.json=Node, go.mod=Go 等）
   - **团队约定**：询问用户或留空待后续填充
   - **禁止事项**：询问用户或留空待后续填充
4. 使用 `search_replace` 填充模板变量
5. 向用户展示填充后的 SOUL.md 内容
6. 询问用户："SOUL.md 内容是否准确？（回复'确认'或提出修改）"

**用户确认后：**
- 若用户提出修改 → 更新内容 → 重新确认
- 若用户确认 → 进入步骤 3

**完成反馈：**
```
✅ 步骤 2/5 完成：SOUL.md 初始化
   文件：.easy-coding/SOUL.md
   状态：已创建并填充
```

---

### 步骤 3：初始化 RULES.md

**来源：** `templates/RULES.md`

**详细步骤：**
1. 使用 `read_file` 读取 `templates/RULES.md`
2. **检测项目编程语言：**
   - 检查 `pom.xml` / `build.gradle` / `*.java` → Java/Kotlin
   - 检查 `requirements.txt` / `setup.py` / `*.py` → Python
   - 检查 `package.json` / `*.js` / `*.ts` → JavaScript/TypeScript
   - 检查 `go.mod` / `*.go` → Go
   - 检查 `Cargo.toml` / `*.rs` → Rust
   - 其他 → 通用规范
3. 根据检测到的语言，选择对应规范填充：
   - **Java**：UpperCamelCase 类名、@Slf4j 日志、Javadoc 注释
   - **Python**：PEP8、snake_case、docstring
   - **Go**：驼峰命名、显式 error 处理
   - **JS/TS**：camelCase、JSDoc/TSDoc
   - **通用**：通用命名规范、通用注释要求
4. 拷贝并填充到 `.easy-coding/RULES.md`
5. 向用户展示语言检测结果和规范概要
6. 询问用户："检测到的语言是 {语言}，规范是否适用？（回复'确认'或提出修改）"

**用户确认后：**
- 若语言检测有误 → 重新检测 → 重新确认
- 若用户确认 → 进入步骤 4

**完成反馈：**
```
✅ 步骤 3/5 完成：RULES.md 初始化
   文件：.easy-coding/RULES.md
   检测语言：{语言}
   状态：已创建并填充
```

---

### 步骤 4：初始化 ABSTRACT.md（支持空项目）

**来源：** 根据项目实际分析生成

#### 4.1 项目扫描

**扫描结果检测：**
```
□ 有源码文件（src/, app/, lib/ 下有.java/.py/.js 等）
□ 仅有配置文件（package.json/pom.xml/go.mod）
□ 几乎为空（只有 README 或.gitignore）
```

#### 4.2 根据结果分支处理

**情况 A：有源码文件（完整初始化）**

1. **扫描项目结构：**
   - `list_dir` 项目根目录
   - 识别主要模块（src/, app/, lib/ 等）
   - 识别配置文件（推断技术栈）
2. **读取核心源码：**
   - 读取所有核心源文件
   - 理解项目主要功能
3. **分析生成内容：**
   - **项目定位**：一句话描述项目是什么
   - **模块结构**：表格形式列出模块、职责、路径
   - **核心业务流程**：所有关键流程
   - **技术栈**：主要技术框架列表
   - **目录索引**：关键功能 → 路径映射
4. 生成内容写入 `.easy-coding/ABSTRACT.md`
5. 向用户展示生成的架构摘要
6. 询问用户："架构分析是否准确？（回复'确认'或提出修改意见）"

**用户确认后：**
- 若用户提出修改 → 更新内容 → 重新确认
- 若用户确认 → 进入步骤 5

**完成反馈：**
```
✅ 步骤 4/5 完成：ABSTRACT.md 初始化（完整版）
   文件：.easy-coding/ABSTRACT.md
   项目定位：{一句话描述}
   状态：已生成并确认
```

---

**情况 B：仅有配置文件（简化初始化）**

1. 根据配置文件推断技术栈
2. 生成简化版 ABSTRACT.md：
```markdown
# 项目架构摘要

> 最后更新：{日期}

## 项目定位
{根据 package.json name 字段或目录名推断}

## 技术栈
- 语言：{根据配置文件推断：Node.js/Java/Go}
- 包管理：{npm/maven/go mod}

## 模块结构
> 待补充：项目尚未开始编码，首次任务完成后更新此章节

## 核心业务流程
> 待补充

## 目录索引
> 待补充
```
3. 向用户展示
4. 询问用户："简化版架构摘要是否适用？（回复'确认'或提出修改）"

**完成反馈：**
```
✅ 步骤 4/5 完成：ABSTRACT.md 初始化（简化版）
   文件：.easy-coding/ABSTRACT.md
   项目定位：{一句话描述}
   状态：已生成并确认（待后续补充）
```

---

**情况 C：几乎为空（最简初始化）**

1. 生成最简版 ABSTRACT.md：
```markdown
# 项目架构摘要

> 最后更新：{日期}

## 项目定位
> 待补充：请在 SOUL.md 中填写项目描述

## 技术栈
> 待补充：请在 SOUL.md 中填写技术栈

## 模块结构
> 待补充：首次编码任务完成后更新

## 核心业务流程
> 待补充

## 目录索引
> 待补充
```
2. 提示用户：`项目尚未初始化，建议在 SOUL.md 中补充项目信息`
3. 进入步骤 5

**完成反馈：**
```
✅ 步骤 4/5 完成：ABSTRACT.md 初始化（最简版）
   文件：.easy-coding/ABSTRACT.md
   状态：已创建（待首次任务后补充）
```

---

### 步骤 5：初始化 MEMORY.md

**来源：** `templates/MEMORY.md`

**详细步骤：**
1. 使用 `read_file` 读取 `templates/MEMORY.md`
2. 拷贝到 `.easy-coding/memory/long/MEMORY.md`
3. 预填充日期字段
4. 验证文件创建成功

**完成反馈：**
```
✅ 步骤 5/5 完成：MEMORY.md 初始化
   文件：.easy-coding/memory/long/MEMORY.md
   状态：已创建
```

---

## 初始化完成

**输出完成报告：**

```
[阶段：INIT]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 初始化全部完成！

已创建/更新的文件：
1. ✅ .easy-coding/ 目录结构
2. ✅ .easy-coding/SOUL.md - 项目灵魂
3. ✅ .easy-coding/RULES.md - {语言}编码规范
4. ✅ .easy-coding/ABSTRACT.md - 架构摘要（{完整版/简化版/最简版}）
5. ✅ .easy-coding/memory/long/MEMORY.md - 长期记忆

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

返回 SKILL.md 继续阶段 2...
```

---

## 返回 SKILL.md

初始化完成后，AI 回到 SKILL.md 的 **1.2 输出背景摘要** 继续执行。