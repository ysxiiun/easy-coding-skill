# Easy Coding 与 Harness 数据边界

> 首轮路由、初始化、记忆或 Git 操作前按需读取。目标是共享可复用事实，同时保证一个修改
> 任务只有一个控制器。

## 1. 公共共享层

双方可以原地读取或按各自工作流更新：

- `.easy-coding/SOUL.md`
- `.easy-coding/RULES.md`
- `.easy-coding/ABSTRACT.md`
- `.easy-coding/TEST_STRATEGY.md`
- `.easy-coding/CHANGELOG.md`（仅记录有证据的架构认知变化）
- `.easy-coding/spec/` 下的固定 Spec 与用户选择的 Dev-Spec 原文件
- `.easy-coding/prototype/`
- `easy-dev-spec/v1` Canonical 原文件及其 `EDS:EXECUTION`
- `.easy-coding/memory/short/` 和 `.easy-coding/memory/long/`

Easy Coding 只使用共享 Markdown/资源协议，不通过 Harness 运行时访问这些数据。Canonical
execution 只能由本 Skill 自带 writer 原地更新；普通 Harness 任务产物不属于共享协议。

## 2. Harness 私有层

Easy Coding 不读取为自身配置、不修改、不生成或复制：

- `.easy-coding/config.yaml`
- `.easy-coding/project.yaml`
- `.easy-coding/install-manifest.json`
- `.easy-coding/sessions/`
- `.easy-coding/tasks/`
- Harness 派生的 task、dev-spec、test-strategy、execution JSONL 或报告
- `.codex/`、`.claude/`、`.gemini/`、`.qoder/` 等平台托管配置、Hooks 和托管 skills

同名共享 `TEST_STRATEGY.md` 是项目知识；Harness 任务目录内的派生测试策略是私有任务产物，
二者不能混用。

## 3. Harness 管理标记与路由

出现任一强标记即视为 Harness 管理：

1. `.easy-coding/config.yaml` 同时声明 `harness_version` 和 `agents`；
2. `.easy-coding/install-manifest.json` 声明 Harness 安装版本或托管产物；
3. 根级 agent 约束的生成区明确写明项目由 `easy-coding-harness` 管理。

仅有 `.easy-coding/`、共享知识、Spec、Prototype、Canonical 或 memory 不构成管理标记。

- 只读请求：可以读取公共共享层和项目事实，走 `ANALYSIS → COMPLETE`。
- 修改请求：在 ANALYSIS 前停止，说明检测到的标记，要求改用 Harness 的任务入口。
- 不得通过 `#no-coding`、删除标记、编辑私有配置或伪造 session 绕过单控制器门禁。

若标记损坏或含义不明，只做只读诊断并请求用户选择修复 Harness 还是清理其安装；Easy Coding
不能自行取得修改控制权。
