# INIT 与共享资产 Initialization Unit

> 仅修改任务在 INIT 只读盘点时加载第 1 节；用户确认 ANALYSIS 方案后，若方案包含
> Initialization Unit，在 IMPLEMENT 加载其余章节。INIT 不等待确认、不写项目文件，完成后
> 自动进入 ANALYSIS。只读请求不加载本 flow、不输出 INIT，直接走 ANALYSIS → COMPLETE。

## 1. INIT 只读盘点

1. 读取 `references/shared-data.md`；检测到 Harness 管理标记时，修改请求停止并改用 Harness。
2. 判断 startup/iteration 项目模式。
3. 检查公共共享层 `SOUL.md`、`RULES.md`、`ABSTRACT.md`、`TEST_STRATEGY.md` 和 schema 2
   记忆是否存在、可读、结构有效。
4. 只读检查旧记忆迁移触发条件；发现时记录 Migration Unit 候选。
5. 不创建目录、不草拟或写入资产、不运行会生成项目产物的命令。
6. 以 `[阶段：INIT]` 输出简洁盘点后自动进入 ANALYSIS。修改任务把缺失资产和旧记忆纳入
   完整方案，不单独确认。只读请求的同类检查发生在 ANALYSIS，只报告事实，不创建 Unit、
   不写入或迁移。

## 2. Initialization Unit 进入条件

只有以下条件全部满足时才在 `[阶段：IMPLEMENT]` 执行：

- ANALYSIS 已列出精确资产范围、数据来源、生成顺序和 QUALITY 验证；
- 用户已确认包含该 Unit 的完整方案；
- Harness 控制器门禁仍未命中；
- 质量 baseline 已复核，当前 Unit 在 candidate scope 内。

旧记忆迁移作为独立 Migration Unit 按 `flow/memory-migration.md` 执行；它同样使用本轮方案
确认，不再增加 INIT 确认门。

## 3. 资产清单

| 路径 | 来源/生成方式 |
| --- | --- |
| `.easy-coding/SOUL.md` | `templates/SOUL.md` + 项目事实 |
| `.easy-coding/RULES.md` | `templates/RULES.md` + 语言/框架惯例 |
| `.easy-coding/ABSTRACT.md` | 已落地代码、构建、Spec 与 Prototype 分析 |
| `.easy-coding/TEST_STRATEGY.md` | `templates/TEST_STRATEGY.md` + 现有验证入口 |
| `.easy-coding/memory/short/` | schema 2 短期记忆目录 |
| `.easy-coding/memory/long/MEMORY.md` | `templates/MEMORY.md` |
| `.easy-coding/memory/long/BUSINESS.md` | `templates/BUSINESS.md` |
| `.easy-coding/memory/long/TECHNICAL.md` | `templates/TECHNICAL.md` |

不得创建或修改 config、project、sessions、tasks、install manifest、平台配置或 Hooks；不得把
`.easy-coding/spec/dev/` 候选固化为全局资产。

## 4. 生成原则

- 只补齐方案确认的缺失资产，不覆盖已有 Spec、Prototype、Canonical、用户手工知识或代码。
- Initialization Unit 排在业务代码/测试 Unit 之后，使初创项目 ABSTRACT 能基于本轮真实代码；
  迭代项目基于现有代码和本轮候选做有界生成。
- 有源码时 ABSTRACT 描述真实模块边界、依赖、核心数据流、技术栈、构建与部署；近似空项目
  只写事实有限的骨架和待补项，不虚构架构。
- TEST_STRATEGY 记录已验证存在的框架、命令、测试位置/命名、覆盖预期、测试/跳过边界、
  环境依赖和 Canonical Test 映射；不安装基础设施或生成任务级派生文件。
- Prototype 只作参考，不直接成为生产实现或架构事实。

## 5. Unit 完成与 QUALITY

写入后在 IMPLEMENT 回看 scope、编码和内容来源，输出 Unit 摘要；不得在此运行确定性验证。
所有业务、测试、共享资产和迁移 Unit 完成后统一进入 QUALITY。共享资产属于同一候选，接受
相同审查门、验证门和 Guard 结果确认；QUALITY 后绝不回跳 INIT。
