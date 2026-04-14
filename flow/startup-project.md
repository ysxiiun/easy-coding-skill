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
4. Prototype HTML 仅供原型参考，不得直接复制到生产代码。
5. 第一版开发完成并经用户确认后，必须自动执行一次初始化回补，再进入记忆阶段。

---

## 输入优先级

进入 ANALYSIS 前，优先吸收以下输入：

1. 用户当前提示词
2. 当前项目代码、目录结构、配置文件
3. `.easy-coding/spec/Architect-Spec.md`
4. `.easy-coding/spec/Product-Spec.md`
5. `.easy-coding/spec/UI-Spec.md`
6. `.easy-coding/prototype/Easy-UI-Prototype.md`
7. Prototype 文档中引用的 HTML 文件

读取规则：

- 存在则读取，不存在则跳过
- 能从代码、配置、Spec、Prototype 推断的信息不要反问用户
- 若关键信息会影响数据模型、接口、页面结构、核心交互或技术路线，不能脑补，必须停下来确认

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
3. 判断用户提示词与 Spec 是否冲突
4. 若涉及前端：
   - 优先启用 `frontend-skill`
   - 按需读取 `references/design/apple-design-reference.md`
   - 明确说明 Prototype HTML 只作参考，不直接用于生产实现

**若提示词与 Spec 冲突：**
- 必须先输出冲突摘要
- 必须等待用户拍板
- 在用户拍板前，不得进入 IMPLEMENT

**若 Spec 信息不足：**
- 必须追问，或在方案中显式标注“当前假设”
- 不得伪装为已确认结论

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
   - 参考 Prototype 文档与 HTML
   - 但必须结合当前框架、工程结构、组件体系、状态管理、路由和样式方案做深度适配
3. 若用户在实施中变更需求，必须回到 WAITING_CONFIRM

### 5. INIT 回补

当第一版开发完成并得到用户确认后，必须自动执行：

1. 读取 `flow/init.md`
2. 以 `post_v1_auto_init` 语义回补 `.easy-coding/` 资产
3. 生成或更新：
   - `.easy-coding/SOUL.md`
   - `.easy-coding/RULES.md`
   - `.easy-coding/ABSTRACT.md`
   - `.easy-coding/memory/long/MEMORY.md`
4. 不覆盖已有 Spec、Prototype 和已确认代码成果

### 6. MEMORY_SHORT → MEMORY_LONG → COMPLETE

初始化回补完成后：

1. 进入 `MEMORY_SHORT`
2. 再进入 `MEMORY_LONG`
3. 最后输出 `COMPLETE`

---

## 输出要求

初创项目的 ANALYSIS 输出，至少额外包含以下字段：

```markdown
### 项目模式
初创项目

### Spec 输入应用
- Architect-Spec：{已使用/未使用}
- Product-Spec：{已使用/未使用}
- UI-Spec：{已使用/未使用}
- Prototype 文档：{已使用/未使用}
- Prototype HTML：{已使用/未使用}

### 冲突摘要
- 提示词 vs Spec：{无 / 冲突说明}

### 当前假设
- {若有则列出；无则填“无”}
```

若涉及前端实现，还必须补充：

```markdown
### 前端实现说明
- frontend-skill：{已启用/应启用}
- Apple 设计参考：{已使用/未使用}
- Prototype 参考：{已使用/未使用}
- 说明：Prototype HTML 仅供原型参考，不得直接用于生产实现。
```

---

## 完成定义

`初创项目` 只有在以下全部完成后，才能视为本轮流程完成：

1. 第一版开发完成
2. 用户确认实现结果
3. 初始化回补完成
4. 短期记忆生成完成
5. 长期记忆检查完成
6. 输出 COMPLETE
