# Canonical Spec v1 共享执行协议

> Dev-Spec 使用 `easy-dev-spec/v1` 时按需读取。Easy Coding 读取静态设计与共享 execution，
> 只通过本 Skill writer 回写原 Markdown；不得创建可编辑副本或 Harness 派生任务产物。

## 1. Locator、身份与单一消费闭包

- 用户显式路径是唯一 locator；未给路径时才列 `.easy-coding/spec/dev/*.md` 文件名。
- 一轮只激活一份 Canonical。未来 schema、非法 manifest 或仓库零匹配不得降级为 Legacy。
- 身份为 `schema + spec_id + revision + design_sha256`；locator 失效只能重新绑定已知/用户提供
  的路径并核对身份，不能按文件名猜测。
- 路由固定为 `manifest-only → 用户选择 task → 一次 selected inspection`。selected 结果冻结
  为 `CanonicalSelectionContext`，只加载唯一 `scope_markdown`；不得读取未选 task 正文。
- 无 execution 的 READY v1 可只读分析；进入修改的方案必须声明确认后在原文件执行 `init`。

## 2. Inspector

```bash
python3 <skill-dir>/scripts/inspect_dev_spec.py <spec-path> \
  --repo-root <repo-root> \
  [--task <task-id>]... [--repo-path <repo-id>=<path>]... \
  [--format json|markdown] [--manifest-only | --refresh-only]
```

- `--manifest-only` 不得与 task/refresh 同用，只返回当前仓库 task catalog、最小依赖摘要和
  execution 投影，不暴露未选 change/test/symbol 正文。
- `selected` 返回源路径、schema/spec/revision、document/design/scope 摘要、execution、选中
  repo/task/依赖/Wave/baseline 和唯一 `scope_markdown`。
- `--refresh-only` 必须带 task，只返回身份、静态摘要与 execution 投影，不返回正文或重算
  baseline；用于异步依赖、CAS 冲突和疑似漂移。
- 成功退出 0；协议/输入错误退出 2；仓库或任务选择错误退出 3。Inspector 永远只读。
- 仓库优先以规范化 remote 唯一匹配；无 remote 时才以 Git 根 basename 匹配。多匹配请用户
  从候选选择并显式传 repo path；零匹配停止。`path_hint` 只提示，不证明身份。

## 3. 摘要、baseline 与依赖

- `document_sha256/source_sha256`：完整文件诊断摘要，execution 更新会改变。
- `design_sha256`：去除 execution 后的完整静态设计，作为 writer CAS。
- `design_scope_sha256`：当前 repo/task 静态闭包，变化时旧方案和质量证据失效并回 ANALYSIS。
- `execution_revision`：共享状态 CAS；`execution_scope_sha256`：当前 task/依赖执行投影。
- execution-only 变化只用 refresh 更新，不重新加载正文或重做静态方案。

Canonical baseline 必须同时覆盖 change path 和 test file，并使用 Git literal pathspec：

| 状态 | 路由 |
| --- | --- |
| `exact` | HEAD 与路径均匹配，可继续 |
| `scope-unchanged` | baseline 是祖先且选中路径无差异，记录当前 HEAD 后继续 |
| `scope-drifted` | 只读漂移文件/符号；影响契约时 revision +1 并重做 ANALYSIS |
| `baseline-unavailable` | 停止实施 |

依赖门禁：

| 类型 | 编码门禁 | 完成门禁 |
| --- | --- | --- |
| `hard` | 前置 task `completed` 或依赖边有 satisfied 证据 | 未满足不得开始 |
| `contract` | READY 且冻结契约静态校验通过 | 实现必须遵守冻结契约 |
| `integration` | pending 不阻断本仓编码 | pending 阻断 Guard 结果确认与 task completed |

## 4. Writer CLI

所有写入使用本 Skill 实际目录的 writer：

```bash
python3 <skill-dir>/scripts/update_dev_spec_execution.py show <spec-path>

python3 <skill-dir>/scripts/update_dev_spec_execution.py init <spec-path> \
  --expected-design-sha256 <confirmed-design-sha256>

python3 <skill-dir>/scripts/update_dev_spec_execution.py task <spec-path> \
  --task <task-id> --status <in_progress|blocked|implemented|verified|completed|cancelled> \
  --summary '<summary>' [--evidence '<json-object>']... \
  --expected-design-sha256 <design-sha256> \
  --expected-execution-revision <revision> \
  --app easy-coding-skill --agent '<actual-host-agent>' \
  --run-id <run-id> --idempotency-key <event-key>

python3 <skill-dir>/scripts/update_dev_spec_execution.py step <spec-path> \
  --task <task-id> --step <step-id> --status <completed|failed> \
  --summary '<summary>' \
  --evidence '{"kind":"test","status":"passed","test_id":"<test-id>","ref":"<command/result + candidate_sha256>"}' \
  --expected-design-sha256 <design-sha256> \
  --expected-execution-revision <revision> \
  --app easy-coding-skill --agent '<actual-host-agent>' \
  --run-id <run-id> --idempotency-key <event-key>

python3 <skill-dir>/scripts/update_dev_spec_execution.py dependency <spec-path> \
  --source-task <task-id> --dependency-task <dependency-task-id> \
  --status <pending|satisfied> --summary '<summary>' \
  --evidence '<json-object>' \
  --expected-design-sha256 <design-sha256> \
  --expected-execution-revision <revision> \
  --app easy-coding-skill --agent '<actual-host-agent>' \
  --run-id <run-id> --idempotency-key <event-key>

python3 <skill-dir>/scripts/update_dev_spec_execution.py sync-design <spec-path> \
  [--affected-task <task-id>]... --summary '<summary>' \
  --expected-design-sha256 <previous-design-sha256> \
  --expected-execution-revision <revision> \
  --app easy-coding-skill --agent '<actual-host-agent>' \
  --run-id <run-id> --idempotency-key <event-key>
```

`--evidence` 每次接收一个 JSON object，可重复。测试证据必须声明所属 Canonical `test_id`。

## 5. 固定 QUALITY 时序

本轮生成一次 `run_id=ec-skill-<UUIDv7>`，在 Canonical 事件和短期记忆中复用；另从 1 开始
维护非配置性的 `quality_round`，为同一 run 内的候选/修复写入隔离幂等键：

1. ANALYSIS 生成并冻结 run ID、design/scope/依赖与实施投影，并在任何项目写入前用该 run ID
   创建质量 baseline；用户确认前不写 execution。
2. 用户确认后先用确认的 scope/ignore 复核 baseline，要求 HEAD 和所有差异均未变化。
3. `show` 校验 design；无 execution 时 `init`，随后 task 写 `in_progress`。Canonical locator
   位于目标 repo 内时作为对应 repo 的机器 ignore；外部 locator 不传给 fingerprint，只保留
   writer/CAS 证据。然后实施业务代码/测试。此时不得写成功 Step 或 task
   `implemented/verified`。
4. QUALITY 绑定一个 candidate SHA 完成审查门和验证门。task 尚为 `in_progress` 时，失败
   Step 写 `failed` 并使 task `blocked`；Guard 回执后 task 已为 `implemented` 时，用户反馈的
   缺陷直接把 task 写 `blocked`，不能越过 writer 前置条件强写 Step。进入 Repair Bundle 前
   递增 round，再重开 task 为 `in_progress`；下一轮用新 candidate 重写全部 Step 成功证据。
5. 双门绿色且 candidate 未漂移后，按前置顺序把 Step 写 `completed`；每个 Step 携带所有绑定
   Test 的 passed 证据及 candidate SHA。全部 Step 完成后 task 写 `implemented`。
6. refresh integration。integration 未满足时保持 QUALITY/`implemented`，不展示 Guard 结果确认。
7. integration 满足时展示 QUALITY 绿色结果；用户确认后 task 写 `verified`，进入 MEMORY。
8. MEMORY 检查点和窗口动作成功后，重新校验并把 task 写 `completed`。

稳定幂等键（`N` 为当前 `quality_round`）：

- `ec-skill:<run-id>:round:<N>:task:<task-id>:<status>`
- `ec-skill:<run-id>:round:<N>:step:<step-id>:<status>`
- `ec-skill:<run-id>:round:<N>:dependency:<source-task>:<dependency-task>:<status>`

同一逻辑调用的重试必须复用同一 key，且同一 key 只能对应同一事件内容。Repair Bundle 或
execution 已初始化后的方案重置必须先递增 round，避免新的 `in_progress / Step completed /
task implemented` 与旧事件冲突；普通 CAS refresh/retry 不递增。每次写入后从 writer 响应
取得新的 execution revision，不得猜测递增值。

## 6. 状态、证据和受控写回

正常 task 主链为：

```text
not_started -> in_progress -> implemented -> verified -> completed
```

- task 未 in_progress 时不得写 Step；Step 必须属于 task，前置 Step 必须 completed。
- Step completed 必须携带其所有绑定 Test 的 passed 证据；其他 task 的 Test 不能借用。
- task implemented 要求全部 Step completed；verified 要求全部 task Tests 已通过；completed
  还要求 integration satisfied。
- 失败按 Step `failed` 和 task `blocked` 落事实；修复开始再写 `in_progress`。
- Canonical execution-only 受控写回不进入业务 `candidate_sha256`，但必须单独记录 locator、
  revision、事件、test evidence 和 writer 结果。静态设计编辑绝不能用 ignore 隐藏。
- writer 使用设计摘要和 execution revision 做双 CAS，并对原文件锁定、临时文件替换和重读
  校验；冲突时 refresh 后重放仍成立的意图，不得手工编辑 `EDS:EXECUTION`。

## 7. 设计修订与禁止事项

静态设计变化必须由用户/设计方修改原 Spec 并将 revision 严格 +1。Easy Coding 随后运行
`sync-design` 标记受影响 task，再回 ANALYSIS；不能用 execution 事件篡改静态 Task/Step/Test。

禁止：

- 复制 Canonical 到其他目录后执行，或创建 Harness task/dev-spec/test-strategy/execution 文件；
- 手工编辑 execution 区、伪造 revision、绕过 writer CAS/锁/幂等键；
- 同一需求并行激活多份 Canonical，或读取未选 task 正文；
- 把 READY、host 自检、reviewer 结论、测试绿色或用户方案确认伪装成用户 QUALITY 结果确认；
- integration pending 时写 verified/completed 或进入 MEMORY；
- 让 Canonical 机器写回污染或替代业务候选指纹。
