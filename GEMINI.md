# GEMINI.md

本文档为 Antigravity / Gemini 系 agent 在此代码仓库中工作提供指引。

## 项目概述

**easy-coding-skill** - 固定 Guard + Standard 的轻量单 Skill 编程工作流，支持共享知识、记忆与 Canonical execution。

## 核心文件

| 文件 | 用途 |
|------|------|
| `SKILL.md` | 不超过 500 行的总控与渐进加载入口 |
| `flow/analysis.md` | 输入发现、方案与确认门禁 |
| `flow/implement.md` | 代码与测试候选落地 |
| `flow/quality.md` | Standard 审查/验证双门与 Guard 结果确认 |
| `flow/memory.md` | 记忆窗口与完成流程 |
| `flow/init.md` | 项目初始化流程 |
| `flow/git.md` | 单 Skill Git 纪律与交付证明 |
| `references/shared-data.md` | 与 Harness 的共享/私有数据边界 |
| `references/dev-spec/canonical-v1.md` | Canonical 原文件消费与共享 execution 契约 |
| `templates/` | SOUL/RULES/ABSTRACT/TEST_STRATEGY/MEMORY/CHANGELOG 模板 |

## 开发约定

- 主分支：`main`
- 交流语言：简体中文
- 阶段标注格式：`[阶段：XXXX]`（中文冒号）
- 合法阶段：INIT / ANALYSIS / IMPLEMENT / QUALITY / MEMORY / COMPLETE / CLOSED
- 修改主链：INIT → ANALYSIS → IMPLEMENT → QUALITY → MEMORY → COMPLETE；方案确认留在 ANALYSIS，结果确认留在 QUALITY
- 固定采用 Guard 审批语义与 Standard 质量深度，不提供模式入口；审查/验证统一属于 QUALITY
- 版本号规则：第一位=重大功能更新，第二位=新功能或新优化迭代，第三位=Bug 修复
- 若用户消息开头包含 `#no-coding`，则该轮跳过 easy-coding 全部流程与约束，下一轮恢复正常
- Easy Coding 与 Harness 互相替代；不得依赖 Harness 运行时或生成私有任务产物，只共享项目知识、记忆、Canonical Markdown 原文件及 `EDS:EXECUTION`

## Git 忽略

- `.easy-coding/` - 运行时生成的项目配置
- `.gemini/` - Gemini / Antigravity 运行时配置
- `.antigravitycli/` - Antigravity CLI 项目配置
- `.qoder/` - Qoder 平台配置
