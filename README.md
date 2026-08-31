# Easy Coding Skill

当前版本：`7.0.0`

Easy Coding 是一个显式触发、轻量化、单入口的 AI 编程 Skill。7.0.0 固定采用 Guard 审批
语义和 Standard 质量深度，不提供模式配置；核心目标是以最少运行时依赖提供方案确认、候选
落地、独立审查、确定性验证、记忆和 Canonical 共享执行闭环。

## 7.0.0 设计边界

- 唯一入口：`$easy-coding`，内部通过 `SKILL.md` 渐进加载 flow/reference/template/script。
- 不依赖 Harness CLI、状态 API、Hooks、session、task 或平台配置。
- 不安装测试基础设施，不提供测试先行专用工作流或直通执行路径。
- `#no-coding` 只是当前轮完全跳过 Skill，下一轮恢复，不承担其他执行语义。
- 已移除 With Claude 联合 flow、独立阶段、场景回归和 Task Packet；历史版本中的相关说明
  仅是版本记录，不再是当前功能入口。
- 同一修改任务只能有一个控制器：检测到 Harness 管理标记时，只读请求可以继续，修改任务
  必须改用 Harness。

## 工作流

合法阶段固定为：

```text
INIT / ANALYSIS / IMPLEMENT / QUALITY / MEMORY / COMPLETE / CLOSED
```

修改任务主链：

```text
INIT → ANALYSIS → IMPLEMENT → QUALITY → MEMORY → COMPLETE
```

- INIT 只读盘点项目模式、控制器标记和共享项目知识；缺失资产进入待确认的
  Initialization Unit，INIT 本身不写项目文件，盘点后自动进入 ANALYSIS。
- ANALYSIS 发现真实上下文，输出确认范围、Implementation Unit、Local Baseline、精确验证命令
  和 reviewer 关注点；方案在 ANALYSIS 内等待用户确认。
- IMPLEMENT 只落地确认范围内的代码和测试，并做范围/编码/注释自检；不运行确定性验证。
- QUALITY 固定执行审查门和验证门。优先使用宿主原生独立 reviewer，不可用时由主代理按同一
  清单降级自审，并披露来源。
- QUALITY 绿色后采用 Guard 结果确认；用户确认后才进入 MEMORY。
- MEMORY 创建质量证据完整的短期记忆，执行 max 10 / keep 5 冻结窗口，成功后 COMPLETE。
- 显式中止进入 CLOSED，并清理仓库外临时 baseline。

只读请求走 `ANALYSIS → COMPLETE`，不创建质量基线、候选指纹或记忆。

## Standard QUALITY

审查和验证绑定同一 `candidate_sha256`：

1. IMPLEMENT 前，`scripts/quality_fingerprint.py baseline` 把 HEAD 与预存脏状态写入仓库外
   临时 JSON。
2. QUALITY 通过 `capture` 计算范围内业务候选，并单列机器 ignore 与意外范围外变化；候选
   摘要同时绑定 HEAD 和确认的 scope/ignore。
3. 每个 Gate 后通过 `check --expected` 重算；HEAD 移动、候选漂移或新增范围外变化都会使
   本轮证据失效。
4. 审查发现分为 `code-defect`、`test-defect`、`contract-ambiguity`、`environment`、
   `suggestion`。前两类聚合为一次 Repair Bundle。
5. 验证门执行方案中的受影响 lint/typecheck/test，以及契约、构建配置或项目规则要求的
   build；缺少环境时停留 QUALITY，不临时安装基础设施制造绿色。
指纹脚本只依赖 Python 标准库与 Git，支持 staged/unstaged/untracked/删除、文件模式、符号
链接、Git 特殊字符和多仓组合。符号链接只散列链接本身，不跟随到仓库外。预存无关脏改动
相对 baseline 不变时不会阻断。脏 gitlink 必须把对应子仓作为独立 `--repo` 纳入，否则脚本
拒绝建立候选；Gate 期间才出现的未覆盖脏 gitlink 由 `check` 按漂移返回 3。
未跟踪 nested Git repo 也必须作为独立 `--repo` 纳入，不能只指纹父目录。

## 与 Harness 的共享数据

公共共享层：

- `.easy-coding/SOUL.md`
- `.easy-coding/RULES.md`
- `.easy-coding/ABSTRACT.md`
- `.easy-coding/TEST_STRATEGY.md`
- `.easy-coding/CHANGELOG.md`（有证据的架构认知变化）
- Spec、Prototype、Canonical 原文件及 `EDS:EXECUTION`
- `.easy-coding/memory/short/` 与 `.easy-coding/memory/long/`

Harness 私有层：

- `.easy-coding/config.yaml`、`project.yaml`、`install-manifest.json`
- sessions、tasks、派生 task/dev-spec/test-strategy/execution/report
- `.codex/`、`.claude/`、`.gemini/`、`.qoder/` 的托管配置、Hooks 与 skills

Easy Coding 不把私有文件当自身配置，不生成或修改它们。详细标记和路由见
`references/shared-data.md`。

## Canonical 共享时序

Easy Coding 继续原地消费 `easy-dev-spec/v1`，不复制 Canonical，也不生成 Harness 普通任务
产物：

```text
方案确认
  → init execution / task in_progress
  → IMPLEMENT 候选
  → QUALITY 双门 + 稳定 candidate SHA
  → Step completed（绑定 Canonical Test 证据）
  → task implemented
  → integration satisfied
  → 用户确认 Guard 结果
  → task verified
  → MEMORY 成功
  → task completed
```

integration 未满足时保持 QUALITY/implemented，不显示最终结果确认。Canonical execution-only
受控写回作为机器事实单列，不进入业务候选摘要；设计摘要和 execution revision 仍由 writer
双 CAS 校验。

## 项目知识与记忆

初始化公共层会补齐 `TEST_STRATEGY.md`，记录项目现有 lint/typecheck/test/build 入口、测试
分层、环境依赖和 Canonical Test 映射，不生成任务级派生策略。

短期记忆 frontmatter 兼容字段：

```yaml
memory_schema: 2
id: SM-<UUIDv7>
source_task: ec-skill-<UUIDv7>
workflow_mode: standard
producer: easy-coding-skill
```

短期正文还记录 candidate SHA、reviewer 来源、发现/修复、验证证据、用户确认与剩余风险。
窗口固定 max 10 / keep 5，只有数量严格大于 10 才 distill。长期沉淀时才评估架构；只有模块
边界、依赖方向、核心数据流、技术栈、构建或部署变化才更新 ABSTRACT 和 CHANGELOG。

## Git 纪律

- 相关共享 `.easy-coding` 知识与记忆默认属于交付范围；sessions 和 Harness 私有层永不提交。
- `.easy-coding/spec/dev/` 只有用户明确要求时才提交。
- 跨仓先交付子仓，再交付父 gitlink。
- `.easy-coding` 冲突必须先说明双方语义和归纳式方案，获得确认后才能修改。
- “提交推送”必须证明远端 SHA 等于本地 HEAD、ahead/behind `0/0` 和最终状态，不只报告本地
  commit。

详细规则见 `flow/git.md`。

## 触发方式

只支持显式加载：

- `使用 $easy-coding 实现……`
- `加载 easy-coding 分析并开发……`
- `使用 Easy Coding skill……`

普通“帮我实现/修改/修复”不会隐式加载。已激活流程中的方案确认、QUALITY 结果确认和
MEMORY 续流无需再次点名。

当前轮完全旁路：

```text
#no-coding 帮我只看一下当前状态
```

## 目录结构

```text
easy-coding/
├── SKILL.md
├── agents/openai.yaml
├── flow/
│   ├── analysis.md
│   ├── implement.md
│   ├── quality.md
│   ├── memory.md
│   ├── init.md
│   ├── startup-project.md
│   ├── git.md
│   ├── memory-migration.md
│   └── memory-retirement.md
├── references/
│   ├── shared-data.md
│   ├── dev-spec/canonical-v1.md
│   ├── design/apple-design-reference.md
│   └── coding/README.md
├── scripts/
│   ├── quality_fingerprint.py
│   ├── inspect_dev_spec.py
│   ├── update_dev_spec_execution.py
│   ├── dev_spec_execution.py
│   └── easy_dev_spec_protocol.py
├── templates/
│   ├── SOUL.md
│   ├── RULES.md
│   ├── ABSTRACT.md
│   ├── CHANGELOG.md
│   ├── TEST_STRATEGY.md
│   ├── SHORT_MEMORY.md
│   ├── MEMORY.md
│   ├── BUSINESS.md
│   └── TECHNICAL.md
└── tests/
```

## 验证

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=<system-temp>/easy-coding-pyc python3 -m py_compile scripts/*.py
python3 /path/to/skill-creator/scripts/quick_validate.py .
git diff --check
```

语法检查完成后清理仓库外的 `easy-coding-pyc` 临时目录；不得把 `__pycache__` 写入项目。

## 历史版本

- `7.0.0`：删除联合协作功能，新增固定 QUALITY 双门、质量指纹、共享数据控制器边界、项目级
  TEST_STRATEGY 和 Git 交付纪律。
- `6.0.0`：完成 Canonical 原文件单一消费闭包和受控 writer 重构；当时仍保留联合协作功能。
- `5.1.0`：统一 schema 2 记忆窗口与 Canonical 基础协议。
