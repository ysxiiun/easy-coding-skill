# CLAUDE.md

本文档为 Claude Code (claude.ai/code) 在此代码仓库中工作提供指引。

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

## Git 忽略

- `.easy-coding/` - 运行时生成的项目配置
- `.claude/` - Claude Code 记忆系统
- `.qoder/` - Qoder 平台配置