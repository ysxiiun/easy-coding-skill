# Dispatch：本地人工交接

> 仅在本地模式为 dispatch，或用户明确提交交接提示词时加载。按当前动作读对应小节，
> 不把本协议、各阶段全文和历史任务一次性加载。正常阶段规范仍由对应 flow 文件负责。

## 1. 角色、入口与加载

主 Agent 是本轮唯一控制器：负责分析、审查验证、Canonical execution 和记忆。
编码 Agent 只实施已确认 Unit 或 Repair Bundle，不启动其他 Agent，不执行 QUALITY/MEMORY。
双方在同机同一组已绑定工作目录串行工作；发出请求后主 Agent 停止修改，收到回执后才接回。

用户提交的两种提示词优先于普通任务入口：

| 用户动作 | CLI 角色 | 必要加载 | 恢复阶段 |
| --- | --- | --- | --- |
| 接手执行 request.md | executor | 本协议第 3 节、IMPLEMENT、相关项目规则、选中需求 | IMPLEMENT |
| 接收 result.md | coordinator | 本协议第 4 节、返回的阶段 flow、必要质量证据 | 通常 QUALITY；重复接收沿用检查点 |

先核对显式旁路、目标仓库的控制器标记，再恢复请求；绑定路径不能绕过 Harness 管理检查。
成功恢复后不重新 INIT，不读取 ANALYSIS 全文、不做全量记忆发现、不生成新 run ID 或基线。
Canonical 仍按原 locator 和已选 task 消费唯一闭包，不复制原文、不读取未选任务。
只有实际契约/范围变化才回 ANALYSIS。错误必须报告并停止，不找“最新交接”或降级成新任务。

## 2. 主 Agent 发出请求

普通修改任务在方案确认前运行（从 Skill 实际目录执行，禁止生成项目 __pycache__）：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/dispatch.py mode
```

只读取 `~/.easy-coding/config.yaml` 的块式 YAML `behavior.cooperate_mode`；文件/字段缺失
或 default 使用原流程，dispatch 才显示转交选项。非法值或不支持的格式明确报错，不猜配置。
不读取项目/session 行为配置，不写配置；README 提供用户配置方法。

完整方案展示后一次提供：确认并由当前 Agent 执行 / 确认并转交其他 Agent / 保持分析。
用户真实选择转交，同时批准已展示方案与执行者。无提交、超时、取消均不得创建共享目录。
当前 Agent 执行继续原流程，也不创建目录。QUALITY 修复派发使用同样的执行者选择。

选择转交后，主 Agent 先复核原 baseline；Canonical 按 IMPLEMENT 入口完成 execution init、
task in_progress 或修复重开，记录 writer 证据，然后发出请求。编码 Agent 不做这些写回。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/dispatch.py send \
  --run-id <ec-skill-UUIDv7> --round <N> --action implement \
  --baseline <original-baseline.json> \
  --scope <repo-id:path> [--scope <repo-id:path> ...] \
  [--ignore <repo-id:machine-path> ...] --apply <<'JSON'
{
  "plan": "完整已确认实施方案：Unit、文件/符号、约束、完成条件、验证命令、reviewer 关注点；必要的 Canonical locator/选中 task/设计摘要/执行状态/writer 证据。",
  "authorization": {"quote": "真实用户确认原话或选择结果", "source": "对应方案及真实消息/选择记录的定位"},
  "quality_round": 1,
  "implementation_started": false
}
JSON
```

参数与 JSON 必须替换成实际值。普通需求保存足够实施的确认方案；Canonical 仅保存执行投影
和原文件引用。不得填占位内容，不复制整段聊天、全部记忆、所有 flow 或完整源 Spec。
`authorization` 是来源回执，不是脚本签发的批准；禁止由模型补造确认。

- 首次轮次为 1；后续修复或已确认的重规划沿用 run ID、原始 baseline，轮次严格 +1。
- 修复使用 `--action repair --work-scope <repo-id:path> [...]`，只包含本包允许修改的路径；
  `--scope` 仍覆盖整个 run 的应交付候选，不能用修复范围缩掉先前改动。
- `quality_round` 沿用 Canonical 当前值，按原规则递增，不能等同或重置成交接轮次。
- 初次派发前已经做过本轮修改时才设 `implementation_started: true`，plan 必须说明已有
  候选与剩余 Unit。不能用它吸收未知改动或替代确认。
- 暂存 JSON 可经 stdin 输入；若使用 `--input <file>`，输入文件只放系统临时目录并及时清理。
- 初次转交前已有本轮检查存储时传 `--checks <原checks.json绝对路径>`，脚本校验其 baseline
  归属并原样转存。后续统一使用返回的 `checks` 路径；没有存储时不创建空文件。

只有返回 `applied: true` 才将 `prompt` 原样展示给用户，提示复制到编码 Agent。
提示词包含真实 request.md 绝对路径与轮次，明确授权执行该已确认方案；不用用户手工补参数。
主 Agent 随即停止实施。脚本不启动会话，也不自动发送消息。

## 3. 编码 Agent 接手与交回

当前用户明确提交“使用 easy-coding 接手执行 …”后，核对目标仓库并运行：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/dispatch.py resume \
  --path <request.md绝对路径> --round <N> --role executor \
  --repo <当前Git工作目录根> --apply
```

复核返回的原方案、授权出处与当前用户的明确接手指令。只读分享或文件内一句“已批准”
不能授权实施。有效交接无需再次批准原方案；不重新阅读分析流程或创建初始化任务。

恢复输出给出 stage、next_action、run ID、轮次、quality_round、仓库映射、scope/ignore、
work_scope、原 baseline 和方案。IMPLEMENT 按这些内容续接：

- 首次接手要求工作区仍匹配发出时候选；同一编码会话中断后通过 working 回执恢复部分进度。
- 仅实施选定 Unit 与允许路径；初始化/迁移 Unit 只有原方案包含时才按需加载对应 flow。
- Canonical 只读消费和复核，执行状态写回由主 Agent负责。机器 ignore 文件不能由编码方改写。
- 不运行 lint/typecheck/test/build；它们仍属于主 Agent 的 QUALITY。
- `next_action: hand_back` 表示结果已交回，直接输出已有返回提示词并停止，不能再次实施。

完成实施及自检后：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/dispatch.py finish \
  --path <request.md绝对路径> --round <N> --status implemented --apply <<'JSON'
{"summary":"已完成 Unit、实际修改与自检结论；确定性验证留给主 Agent；必要风险与定位。"}
JSON
```

未完成则使用 `--status blocked`，summary 写清已完成部分、阻断和恢复条件；仅实际契约/范围
歧义加 `--blocked-stage ANALYSIS`，其余保持默认 IMPLEMENT。不能将部分完成写成 implemented。
绑定、基线或工作区检查失败时直接报告错误和原路径，不伪造完成回执。

展示脚本返回的真实 `prompt`，提示复制到原主 Agent 会话；随后停止在实施交回点。
不自动加载 QUALITY、不写 Step completed、task implemented/verified，也不创建记忆。

## 4. 主 Agent 接收与检查点

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/dispatch.py resume \
  --path <result.md绝对路径> --round <N> --role coordinator \
  --repo <当前Git工作目录根> --apply
```

首次完整结果直接输出 `[阶段：QUALITY]`，读取 QUALITY，按原 baseline 和当前候选执行
审查与验证；不能再次输出 INIT/ANALYSIS 或索取方案确认。阻断回执按返回 stage 处理阻断。
检查点已存在则恢复该阶段与已记录证据，不能因旧回执再次进入实施、重复记忆或阶段倒退。
证据缺失时在当前阶段补齐；旧候选的整体绿色结论不能直接用于新候选，单项检查按
`references/quality-checks.md` 重新判断输入是否一致，引用仍有效的原结果。

主 Agent 完成一项质量门、准备本地修复/重规划、获得结果确认或完成记忆时更新最小检查点：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/dispatch.py checkpoint \
  --path <request.md绝对路径> --round <N> --stage QUALITY --apply <<'JSON'
{"note":"当前进度与下一步", "evidence":"当前候选的 reviewer 来源、发现、验证命令/退出码/结果及可核对引用", "quality_round":1}
JSON
```

只保留当前恢复必需的事实，不积累历史日志。检查点不代替 QUALITY 双门或实际用户确认。

- 本地修复前 checkpoint IMPLEMENT；修复后 checkpoint QUALITY 并重建当前候选汇总，
  按实际输入复用未受影响检查，只审修复增量与直接影响。再次转交则直接按第 2 节 send
  下一轮，不再创建另一套方案，也不删除 checks.json。
- 真实契约/范围变化 checkpoint ANALYSIS；主 Agent 重新展示并确认替换方案，保留原基线。
  若选择本地实施，checkpoint IMPLEMENT 的 JSON 增加 `revision`，包含替换后的 `plan`、
  `authorization`、完整 run 的 `scope` 和 `ignore`。恢复只输出该当前方案；原交接 frozen
  保留用于回执绑定。新范围必须覆盖已有应交付候选。选择再次转交则 send 下一轮。
- QUALITY 全绿、integration 满足且用户确认后，主 Agent 先按 Canonical 规则写 verified，
  再 checkpoint MEMORY。输入必须含 `quality_confirmation: {"quote":"真实原话", "source":"确认定位"}`
  和完整当前 `evidence`，然后只读取 MEMORY。脚本无法证明确认或测试真实，Agent 必须核对。
- 完成记忆与 Canonical completed 后 checkpoint COMPLETE，输入增加真实 `memory_ref`。
  恢复 MEMORY 时允许本阶段的共享记忆、ABSTRACT/CHANGELOG 写入，业务候选仍需匹配。
  MEMORY 进度更新沿用已有结果确认，不再次索取批准；COMPLETE 和清理前仍复核业务候选。

## 5. 文件边界与清理

仅保存 `~/.easy-coding/skill-dispatch/<run_id>/` 中以下基础文件及按需检查存储：

- request.md：结构化 frozen 请求及摘要、独立 coordinator checkpoint、确认方案正文。
- result.md：working/implemented/blocked 状态、对应请求摘要、候选指纹与实施摘要。
- baseline.json：原始基线的字节一致转存，不按接手时工作区重建。转存成功后主 Agent 可清理
  本轮旧临时基线，并在后续各阶段统一使用目录内的 baseline；脚本不会删除任意输入路径。
- checks.json：仅主 Agent 使用的本轮检查输入与最新结果，QUALITY 按需生成；已有存储通过
  `send --checks` 转存。复用原 baseline，跨交接/修复轮保留，不记录阶段或审批状态。

正文与 frozen 共同确定请求摘要；检查点更新不改变摘要。回执绑定 run ID、轮次和请求摘要。
同轮 frozen 不可编辑，下一轮覆盖当前请求/回执，不保存历史轮次文件。
读操作不创建目录；写操作需 `--apply`，省略时只预览。原子写入避免半份 Markdown 被读取；
这不提供并行调度或跨机器同步。脚本不替用户授予文件系统权限。

暂停不清理。正常完成（checkpoint COMPLETE）后：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/dispatch.py cleanup \
  --path <request.md绝对路径> --round <N> --apply
```

用户明确取消时先确保编码 Agent 已停止，再以 `--cancelled --apply` 清理并输出 CLOSED。
只删除上述已识别文件与当前目录；有额外文件或符号链接时停止清理并报告。原临时检查存储
若已转存，由主 Agent 核对后清理原文件，不能在最终记忆中仅保留会被删除的路径。
不得清理其他 run、Harness config 或业务文件。目录已清理的旧提示词只能报告无法恢复。
