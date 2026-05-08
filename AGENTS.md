# AGENTS.md

本文档为 Codex (Codex.ai/code) 在此代码仓库中工作提供指引。

## 项目概述

**easy-coding-skill** - AI 编程助手技能，通过七阶段强制流程和长短期记忆系统实现人机共创模式。

## 核心文件

| 文件 | 用途 |
|------|------|
| `SKILL.md` | 技能主定义，AI 执行时加载 |
| `flow/init.md` | 项目初始化流程 |
| `templates/` | SOUL/RULES/ABSTRACT/MEMORY 模板 |

## 开发约定

- 主分支：`main`
- 交流语言：简体中文
- 阶段标注格式：`[阶段：XXXX]`（中文冒号）
- 7 阶段：INIT → ANALYSIS → WAITING_CONFIRM → IMPLEMENT → MEMORY_SHORT → MEMORY_LONG → COMPLETE
- 若用户消息开头包含 `#no-coding`，则该轮跳过 easy-coding 全部流程与约束，下一轮恢复正常

## Git 忽略

- `.easy-coding/` - 运行时生成的项目配置
- `.codex/` - Codex 记忆系统
- `.qoder/` - Qoder 平台配置
