# CLAUDE.md

本文档为 Claude Code (claude.ai/code) 在此代码仓库中工作提供指引。

## 项目概述

**easy-coding-skill** - AI 编程助手技能，通过六阶段强制流程和长短期记忆系统实现人机共创模式。

## 核心文件

| 文件 | 用途 |
|------|------|
| `SKILL.md` | 技能主定义，AI 执行时加载 |
| `flow/init.md` | 项目初始化流程 |
| `flow/with-claude.md` | Easy Coding With Claude 联合模式编排 |
| `templates/` | SOUL/RULES/ABSTRACT/MEMORY 模板 |

## 开发约定

- 主分支：`main`
- 交流语言：简体中文
- 阶段标注格式：`[阶段：XXXX]`（中文冒号）
- 6 阶段：INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT → MEMORY → COMPLETE
- 联合模式：仅当用户同时显式引用 Easy Coding 与 With Claude 时启用；IMPLEMENT 后增加 Claude 只读 REVIEW 插槽，最多 3 轮
- `PLAN` / `VERIFY` / `TEST` / `DONE` / `REVIEW_BLOCKED` 不是 Easy Coding 阶段；Claude 分析等待态仍使用 `[阶段：ANALYSIS]`，验证与自检仍使用 `[阶段：IMPLEMENT]`，完成只能使用 `[阶段：COMPLETE]`
- 版本号规则：第一位=重大功能更新，第二位=新功能或新优化迭代，第三位=Bug 修复
- 若用户消息开头包含 `#no-coding`，则该轮跳过 easy-coding 全部流程与约束，下一轮恢复正常

## Git 忽略

- `.easy-coding/` - 运行时生成的项目配置
- `.claude/` - Claude Code 记忆系统
- `.gemini/` - Gemini / Antigravity 运行时配置
- `.antigravitycli/` - Antigravity CLI 项目配置
- `.qoder/` - Qoder 平台配置
