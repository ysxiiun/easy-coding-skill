# Canonical Spec v1 共享执行协议

> 当 Dev-Spec 使用 `easy-dev-spec/v1` 时，由 `SKILL.md` 按需读取本文件。
> Easy Coding 读取静态设计、共享 execution，并只通过受控 writer 回写原 Spec；不得创建可编辑副本。

## 1. Locator、身份与兼容

- 用户显式提供绝对或相对路径时，该路径是唯一候选；解析为绝对 locator 后直接读取，不扫描或复制到 `.easy-coding/spec/dev/`。
- 仅在用户未给具体路径时，兼容扫描 `.easy-coding/spec/dev/*.md`，选择前只列文件名。
- 一轮需求只激活一份 Canonical Spec。Legacy Dev-Spec 继续按原流程全文读取；未来 schema 或非法 Canonical 不得降级为 legacy。
- 当前需求记录绝对 locator。Canonical 身份是 `schema + spec_id + revision + design_sha256`。
- locator 失效时只能重新绑定已知或用户提供的路径，并核对 `spec_id + design_sha256`；不得按文件名猜测。
- 无 execution 的旧 Canonical v1 可只读分析。进入开发的技术方案必须包含“初始化并回写原 Spec”，用户确认方案后才执行 `init`。

## 2. Inspector

从当前已加载 Easy Coding Skill 的实际目录解析 `<easy-coding-skill-dir>`：

```bash
python3 <easy-coding-skill-dir>/scripts/inspect_dev_spec.py <spec-path> \
  --repo-root <repo-root> \
  [--task <task-id>]... \
  [--repo-path <repo-id>=<path>]... \
  [--format json|markdown] \
  [--manifest-only]
```

约束：

- 首次路由用 `--manifest-only`；它不能与 `--task` 同用。
- 用户明确 task 后重复传 `--task`；只有用户明确要求当前仓全部任务时才省略。
- 成功退出 `0`；协议/输入错误退出 `2`；仓库或任务选择错误退出 `3`。
- `RepositoryAmbiguityError` 会带 `candidates`。用户确认候选后，用 `--repo-path <repo-id>=<repo-root>` 重试；remote 零匹配不能由确认覆盖。
- Inspector 只读，不 fetch、checkout、build、test 或写 Spec。
- 完整 Canonical 输出包含：`source_path`、`schema`、`spec_id`、`revision`、`source_sha256`、`document_sha256`、`design_sha256`、`design_scope_sha256`、`execution_scope_sha256`、`execution`、仓库/任务/依赖/Wave/baseline 和 `scope_markdown`。
- `source_sha256` 是整文兼容诊断字段，等同 `document_sha256`；实施门禁只使用设计摘要。
- task catalog 的 `status` 是 manifest 静态状态，`execution_status` 是实际状态；`READY` 不代表代码已完成。
- 单仓闭包直接透传上游选择结果；跨仓按 `repo_id` 分组选取、排序合并，复合摘要由 `{repo_id: child_digest}` 的 canonical JSON 计算。

Host/Claude 只加载 `scope_markdown`，不读取未选 task 正文。跨仓任务必须为额外仓库显式提供并验证 `--repo-path`。

## 3. 仓库与 baseline

仓库识别顺序：

1. 规范化本地 Git remote，与 `repositories[].remote_urls` 唯一匹配。
2. 仅在没有可用 remote 时，用 Git 根目录 basename 唯一匹配 `repositories[].name`。
3. 多匹配必须让用户从候选中确认；零匹配停止。
4. `path_hint` 只作提示，不能证明身份。

baseline 状态：

| 状态 | 处理 |
| --- | --- |
| `exact` | HEAD 等于 baseline，且选中 change/test 路径无工作树变更，可走快速路径 |
| `scope-unchanged` | baseline 是 HEAD 祖先，选中 change/test 路径无已提交或工作树差异，可记录 HEAD 后快速分析 |
| `scope-drifted` | 读取漂移文件和符号，核对设计；影响静态边界时走设计修订 |
| `baseline-unavailable` | 停止实施，先取得可验证基线 |

Git 文件范围必须同时包含 change path 和 test file，并使用 literal pathspec。

## 4. 任务与依赖

任务选择优先级：用户给定 task ID → 用户明确当前仓全部 task → 使用 catalog 标题/交付物唯一匹配 → 让用户选择。语义匹配只能决定传给 Inspector 的 task ID，不能绕过仓库和协议校验。

共享 execution 是依赖事实来源：

| 类型 | ANALYSIS / 编码门禁 | 完成门禁 |
| --- | --- | --- |
| `hard` | 仅当前置 task 实际为 `completed`，或该依赖边已有 `satisfied` 证据时放行 | 未满足时不得开始/推进被依赖 task |
| `contract` | Spec 为 `READY` 且冻结契约通过静态校验时满足，可并行编码 | 必须严格遵守冻结契约 |
| `integration` | pending 不阻断本仓编码 | pending 阻断 task 写入 `completed` |

依赖证据必须落入 execution event；manifest 的 `READY` 或正文“已完成”不能伪装实际完成。Wave 只表达 hard DAG 的实施次序，不替代 execution 门禁。

## 5. 摘要语义

- `document_sha256 / source_sha256`：完整文件，execution 更新会变化，只作诊断。
- `design_sha256`：去除 execution 区域后的完整静态设计，是确认与 writer CAS 门禁。
- `design_scope_sha256`：当前 repo/task 静态消费闭包，是 Host/Claude 范围门禁。
- `execution_revision`：共享执行状态 CAS 修订号。
- `execution_scope_sha256`：当前选择涉及的 task/依赖执行投影。

execution-only 变化：刷新 `execution_revision / execution_scope_sha256` 和依赖事实，保留已确认静态方案。`design_sha256` 或 `design_scope_sha256` 变化：旧方案/Claude 结果失效，回到 `ANALYSIS`。

## 6. Writer CLI

所有写入只使用当前 Skill 内的 writer：

```bash
python3 <easy-coding-skill-dir>/scripts/update_dev_spec_execution.py show <spec-path>
```

初始化旧 Canonical v1：

```bash
python3 <easy-coding-skill-dir>/scripts/update_dev_spec_execution.py init <spec-path> \
  --expected-design-sha256 <confirmed-design-sha256>
```

任务状态：

```bash
python3 <easy-coding-skill-dir>/scripts/update_dev_spec_execution.py task <spec-path> \
  --task <task-id> \
  --status <in_progress|blocked|implemented|verified|completed|cancelled> \
  --summary '<summary>' \
  [--evidence '<json-object>']... \
  --expected-design-sha256 <design-sha256> \
  --expected-execution-revision <revision> \
  --app easy-coding \
  --agent '<Agent Name> with Easy Coding' \
  --run-id <stable-run-id> \
  --idempotency-key <stable-event-key>
```

Step 状态：

```bash
python3 <easy-coding-skill-dir>/scripts/update_dev_spec_execution.py step <spec-path> \
  --task <task-id> --step <step-id> --status <completed|failed> \
  --summary '<summary>' \
  --evidence '{"kind":"test","status":"passed","test_id":"<test-id>","ref":"<command/result>"}' \
  --expected-design-sha256 <design-sha256> \
  --expected-execution-revision <revision> \
  --app easy-coding --agent '<Agent Name> with Easy Coding' \
  --run-id <stable-run-id> --idempotency-key <stable-event-key>
```

依赖证据：

```bash
python3 <easy-coding-skill-dir>/scripts/update_dev_spec_execution.py dependency <spec-path> \
  --source-task <task-id> --dependency-task <dependency-task-id> \
  --status <pending|satisfied> --summary '<summary>' \
  --evidence '{"kind":"artifact","status":"recorded","ref":"<evidence>"}' \
  --expected-design-sha256 <design-sha256> \
  --expected-execution-revision <revision> \
  --app easy-coding --agent '<Agent Name> with Easy Coding' \
  --run-id <stable-run-id> --idempotency-key <stable-event-key>
```

设计同步：

```bash
python3 <easy-coding-skill-dir>/scripts/update_dev_spec_execution.py sync-design <spec-path> \
  [--affected-task <task-id>]... \
  --summary '<summary>' \
  --expected-design-sha256 <previous-design-sha256> \
  --expected-execution-revision <revision> \
  --app easy-coding --agent '<Agent Name> with Easy Coding' \
  --run-id <stable-run-id> --idempotency-key <stable-event-key>
```

`--evidence` 每次接收一个 JSON object，可重复。测试证据必须声明其 Canonical `test_id`。

## 7. 固定写入顺序

1. `show`，校验已确认的 `design_sha256`；再运行 Inspector 校验 `design_scope_sha256`。
2. execution 不存在时，仅在方案已明确且用户已确认后执行 `init`。
3. 将 task 写为 `in_progress`；写入成功后才修改业务代码。
4. 按 Step 前置关系实施。声明变更和绑定 Test 都完成后写 Step `completed`；失败写 `failed`，writer 会使 task 进入 `blocked`。
5. 全部 Step 完成后写 task `implemented`。
6. 有完整 Canonical Test 证据后写 task `verified`。
7. 输出实施结果并等待用户确认。确认后重新 `show`；只有 integration 全部满足才写 task `completed`。
8. integration 未闭合时保留 `verified`，明确 Canonical task 未完成；不得用 Easy Coding `COMPLETE` 标签掩盖该事实。

所有事件使用同一稳定 run ID；幂等键按事件唯一，例如 `<run>:<task>:start`、`<run>:<task>:<step>:completed`。同一幂等键只能对应同一事件内容。

## 8. 状态与证据规则

正常主链：

```text
not_started -> in_progress -> implemented -> verified -> completed
```

- `blocked` / `cancelled` 的恢复和重开只能走 writer 允许的状态迁移。
- task 未 `in_progress` 时不得写 Step。
- Step 必须属于 task，前置 Step 必须 completed。
- Step `completed` 必须携带所有绑定 Test 的 passed 证据。
- task `implemented` 要求所有声明 Step completed。
- task `verified` 要求 task 声明的所有 Canonical Test 有 passed 证据。
- task `completed` 还要求 integration 满足，并且只能在用户确认实施结果后由 Host 发起。
- 不允许手工编辑 execution JSON、伪造快照、跳事件、跳修订或复用其他 task 的 Test 证据。

## 9. 冲突、重试与原子性

writer 在文件锁内执行设计校验、execution 校验、幂等检查、CAS、事件投影和原子替换。

- 退出 `0`：写入成功或完全等价的幂等重试成功。
- 退出 `2`：输入/状态/证据/协议非法；修正原因，不盲目重放。
- 退出 `3`：设计摘要或 execution revision 冲突。重新 `show` 与 Inspector：
  - 设计摘要未变：刷新 revision，只重放当前事件；不要重放整个实施序列。
  - 设计或设计范围摘要变化：停止业务修改，回到 `ANALYSIS`。
- writer 会先核对当前设计一致性，再接受幂等重试；静态设计被未同步修改时，旧幂等键不能绕过冲突。

## 10. 静态设计修订

实施发现 manifest、契约、change/symbol、Step 或 Test 映射需要变化时：

1. 停止当前 Step，不继续业务代码。
2. 在 `ANALYSIS` 说明为何必须修改原 Spec、受影响 task 和后继范围。
3. 获得用户明确确认后，直接编辑原 Spec 静态设计；`revision` 必须恰好加一。
4. 用同步协议模块做完整静态校验。
5. 调用 `sync-design`，传明确的 `--affected-task`。
6. writer 重置受影响 task 及全部后继 task；旧 Step、测试、依赖证据不恢复。
7. 重新运行 Inspector，输出并确认新设计方案后才继续实施。

同一 revision 下再改静态设计、revision 跳号、受影响 task 不存在，均必须拒绝。

## 11. With Claude

ANALYSIS 与 REVIEW packet 携带：

- `spec_id`
- `source_digest`（仅诊断）
- `design_digest`
- `design_scope_digest`
- `execution_revision`
- `execution_scope_digest`
- `selected_task_ids / repo_ids / dependency_summary`

Claude 只读，且只接收 `scope_markdown` 和必要代码目录。Claude 返回期间：

- 只有 execution revision/scope 变化：Host 刷新进度，可继续使用只读分析。
- design/design scope 变化：丢弃旧 worker 结果并返回 `ANALYSIS`。
- Claude 引用未选 task、仓库、symbol 或步骤：丢弃越界部分。
- REVIEW 不得扩大已确认 task/change/test 范围。

## 12. 禁止事项

- 不创建、复制或维护第二份可编辑 Canonical Spec。
- 不把 `READY`、本地测试通过或 Claude `accept` 当成 task `completed`。
- 不直接编辑 execution 区域，不绕过 writer。
- 不因 `source_sha256` 随 execution 变化而要求重新确认静态方案。
- 不在用户确认方案前执行 `init` 或任何 execution 写入。
- 不自动安装、同步、提交、推送或发布 Skill。
