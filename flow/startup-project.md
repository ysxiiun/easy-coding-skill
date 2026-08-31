# 初创项目差异流程

> INIT 判定为初创项目时读取。本文件只定义首版 Implementation Unit 的差异，不改变固定阶段
> 主链：`INIT → ANALYSIS → IMPLEMENT → QUALITY → MEMORY → COMPLETE`。

## 1. 判定与 INIT

空仓库、近似空仓库、只有脚手架/构建配置，或主要输入为 Spec/Prototype 且没有稳定业务
模块时，可判定为初创项目。已有稳定页面、接口、领域模型或持久化结构时按迭代项目处理。

修改任务的 INIT 仍只读盘点并自动进入 ANALYSIS。不得跳过 INIT，也不得在首版 QUALITY 后回跳
INIT；只读请求不进入本差异流程，保持 `ANALYSIS → COMPLETE`。

## 2. ANALYSIS 差异

- Architect Spec 决定模块边界，Product Spec 决定业务规则，UI Spec/Prototype 表达页面与
  交互意图；冲突必须在方案中闭合。
- 只有 Dev-Spec 候选时仍按通用选择与 Canonical 路由。
- 没有足够事实时只询问会改变首版边界的问题，不虚构接口、数据模型或架构。
- 首版拆成最小完整业务/测试 Unit；共享资产缺失时按 `flow/init.md` 增加末尾
  Initialization Unit，由同一方案确认。
- Local Baseline、审查关注点和精确验证命令与迭代项目要求相同。

## 3. IMPLEMENT 与 QUALITY 差异

- 业务 Unit 只交付已确认的最小完整首版，不预埋未来能力。
- 新文件遵循脚手架、同类文件和已确认架构的目录/编码惯例。
- 前端必须把 Prototype 映射到真实页面、组件、状态、数据和接口；mock 退出条件写入方案。
- 业务代码/测试落地后执行 Initialization Unit，使 ABSTRACT/TEST_STRATEGY 基于真实候选。
- 实施证明 Spec 契约或验收不可行时返回 ANALYSIS；Canonical 按设计修订契约处理。
- 全部 Unit 自动进入 Standard QUALITY；共享资产与业务候选一起受审查、验证和指纹约束。

## 4. 完成语义

QUALITY 绿色并获用户确认后直接进入 MEMORY，不回补、不回跳 INIT。MEMORY 成功后才能
COMPLETE；Canonical integration 未闭合时保持 QUALITY。
