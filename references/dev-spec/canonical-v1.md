# Canonical Spec v1 消费协议

> 当候选 Dev-Spec 含 `easy-dev-spec/v1` manifest 时，由 `SKILL.md` 直接读取本文件。
> 本文件只定义消费规则；不得修改 Canonical Spec，也不得把运行进度写回 Spec。

## 目录

1. [协议识别](#协议识别)
2. [确定性检查工具](#确定性检查工具)
3. [仓库识别](#仓库识别)
4. [任务选择](#任务选择)
5. [依赖语义](#依赖语义)
6. [消费闭包](#消费闭包)
7. [基线与 ANALYSIS 路由](#基线与-analysis-路由)
8. [IMPLEMENT 门禁](#implement-门禁)
9. [With Claude 边界](#with-claude-边界)
10. [兼容与错误处理](#兼容与错误处理)

## 协议识别

Canonical Spec 的第一个机器区域必须为：

````markdown
<!-- EDS:MANIFEST:BEGIN -->
```json
{"schema":"easy-dev-spec/v1"}
```
<!-- EDS:MANIFEST:END -->
````

执行以下路由：

1. 候选阶段只扫描 `.easy-coding/spec/dev/` 下的 Markdown 文件名。
2. 用户显式引用具体路径时，将该路径直接作为当前候选，不再要求按文件编号二次选择。
3. 用户选择候选后，只调用检查工具探测 manifest；不要把任务正文预先读入 Agent 上下文。
4. 无 manifest 时返回 `legacy`，继续现有全文读取流程。
5. manifest 存在但边界、JSON 或 schema 非法时停止消费；未来 schema 不得降级为 legacy。
6. 一轮需求只激活一份 Canonical Spec；多份 legacy 文档仍可沿用编号多选。

## 确定性检查工具

使用当前已加载 Easy Coding Skill 根目录内的只读脚本。先从本 `SKILL.md` 的实际路径解析 `<easy-coding-skill-dir>`，不要把业务仓库 cwd 下的同名 `scripts/` 当成 Skill 工具：

```bash
python3 <easy-coding-skill-dir>/scripts/inspect_dev_spec.py <spec-path> \
  --repo-root <repo-root> \
  [--task <task-id>]... \
  [--repo-path <repo-id>=<path>]... \
  [--format json|markdown] \
  [--manifest-only]
```

约束：

- 默认 `--format json`，stdout 只输出一个 JSON 对象。
- 候选文件首次探测使用 `--manifest-only`，只返回仓库匹配和 task catalog，不生成消费闭包；该参数不能与 `--task` 同用。仓库歧义经用户确认后，允许携带唯一一个指向当前仓库的 `--repo-path` 重新取得 task catalog。
- 用户明确 task 后传 `--task`；只有用户明确要求完成当前仓库时才不传 `--task`，选择当前仓全部 READY task。
- 成功返回 `0`；manifest/schema/输入错误返回 `2`；仓库或任务选择错误返回 `3`。
- 仓库歧义返回 `RepositoryAmbiguityError` 和结构化 `candidates`；用户确认后先以 `--manifest-only --repo-path <repo-id>=<repo-root>` 恢复 task catalog，完整检查继续携带相同映射，不新增或猜测仓库身份。
- 脚本不写文件、不联网，不执行 fetch、checkout、merge、build 或 test。
- `legacy` 结果不包含消费闭包；由 host 读取原文。
- `canonical-v1` 完整检查结果至少包含 `spec_id`、`spec_status`、`source_sha256`、带实际 `head` 的 `repositories`、`selected_tasks`、`dependency_gaps`、`baseline_status`、`scope_markdown` 和 `scope_sha256`。

脚本输出是范围判断的机器证据。Host 仍负责读取本地代码、RULES、ABSTRACT，判断语义冲突和外部完成证据。

## 仓库识别

按以下顺序识别，不得用 `path_hint` 猜测身份：

1. 规范化本地 Git remote，与 `repositories[].remote_urls` 唯一匹配。
2. 仅当本地没有可用 remote 时，使用 Git 根目录 basename 与 `repositories[].name` 唯一匹配。
3. remote 多匹配或 basename 歧义时返回候选信息并等待用户选择；用户选择后用 `--repo-path <repo-id>=<当前 repo root>` 显式确认。
4. remote 零匹配或 basename 零匹配时停止，不允许以用户确认覆盖零匹配。
5. 跨仓任务必须为每个额外 `repo_id` 显式提供 `--repo-path`；脚本重新验证路径对应的 remote/名称，歧义路径同样只接受候选集合内的显式确认。

remote 规范化会去除协议、认证信息、`.git` 和尾斜杠，将 scp/SSH/HTTPS 统一为 `host/group/repo`。

## 任务选择

按优先级处理：

1. 用户明确给出 task ID：选择指定 task，并检查其直接依赖。
2. 用户明确要求完成当前仓库：选择当前仓库全部 `READY` task。
3. 用户描述功能：仅使用 manifest 中的 task 标题和 `change_paths`（作为关键交付物）做语义匹配；唯一命中时选择。
4. 多个互不依赖任务组命中：列出任务清单，使用原生选择工具让用户选择。
5. 用户显式选择跨仓 task：先解析并确认全部 repo path，再建立跨仓任务集合。

任务清单必须包含：`task_id`、仓库、标题、依赖类型、以 `change_paths` 表示的关键交付物、task 状态和 baseline 状态；尚未解析路径的其他仓库显示 `repo-unresolved`。未选 task 不进入实现范围。

语义匹配只决定要传给脚本的 task ID，不得绕过脚本的仓库归属和依赖校验。

## 依赖语义

| 类型 | ANALYSIS | IMPLEMENT | 完成门禁 |
| --- | --- | --- | --- |
| `hard` | 未选择前置且无完成证据时进入 `dependency_gaps` | 不进入被阻断 task | 前置纳入选择或提供有效完成证据 |
| `contract` | Spec 整体 READY 且契约区域存在时满足 | 可与定义方并行 | 严格使用冻结契约 |
| `integration` | 记录联调前置 | 不阻断本仓编码 | 必须标记联调未完成，不得宣称全链路完成 |

有效完成证据只能是 commit、发布版本、可访问构件、测试报告或用户明确确认的外部状态。Spec 内单独写“已完成”不算证据。

执行 Wave 由所选 task DAG 确定。同一 Wave 只有在仓库路径和文件范围无交叉时才允许并行。

## 消费闭包

Host 和 Claude 只能读取脚本输出的 `scope_markdown`。其中 manifest 摘要保留已选范围的 repository/task/contract/change/step/test 完整对象，确保文件、symbol 和测试命令可执行；所有未选对象必须删除：

```text
manifest 摘要（含原 Spec 的 `source_sha256`）
+ global-context
+ 选中 task 所属 repo 区域
+ 直接引用的 contract 区域
+ 选中 task 区域
+ 直接依赖 task 摘要
+ integration-plan 中提到选中 task 或其直接依赖的行
```

禁止把以下内容放入上下文：

- 未选仓库 task 的文件、符号、调用链和实施步骤。
- 依赖 task 的内部实现正文；依赖只保留 ID、仓库、标题、状态、类型和证据要求。
- rollout 或端到端章节中与当前选择无关的内容。

使用 `source_sha256` 追踪原 Spec，使用 `scope_sha256` 检查 Host、Claude 和后续阶段的闭包一致性。原 Spec 内容变化，或切换 Spec、task、repo path 后必须重新运行脚本，旧摘要立即失效。

## 基线与 ANALYSIS 路由

| 状态 | 处理 |
| --- | --- |
| `exact` | 当前 HEAD 等于 baseline，且选中 change path 与 test file 没有 staged、unstaged 或 untracked 变更，允许快速路径 |
| `scope-unchanged` | baseline 是当前 HEAD 祖先，且选中 change path 与 test file 没有已提交或工作树差异，允许快速路径并记录 HEAD |
| `scope-drifted` | change path、test file 存在已提交或工作树差异，或历史已分叉，重新检查文件、符号、调用链和测试映射 |
| `baseline-unavailable` | 本地没有 baseline commit，停止并要求取得可验证基线 |

只有以下条件全部满足才启用 ANALYSIS 快速路径：

- Spec 与全部所选 task 都是 `READY`。
- 仓库身份已唯一确认。
- 每个所选仓库 baseline 为 `exact` 或 `scope-unchanged`。
- 没有未满足的 hard dependency。

快速路径只输出：所选 Spec/task/repo、基线证据、RULES/ABSTRACT/提示词冲突、Wave 与路径映射、文件/符号/测试/联调门禁，以及进入 WAITING_CONFIRM 所需信息。不得重新命名字段、改接口类型、重拆 task 或另写平行技术方案。

`scope-drifted` 时读取发生漂移的本地文件和符号，输出 Spec 修订项。影响契约、架构或 task 边界的差异必须等待用户确认，不得静默改写 Spec。

## IMPLEMENT 门禁

每个 task 开始前重新确认：

- 当前 `source_sha256` 与 `scope_sha256` 均未因 Spec 内容或选择变化而失效。
- task 的 `repo_id` 对应当前实际路径。
- 本次修改只覆盖 task 的 `change_ids` 路径与 symbols。
- 实施顺序遵守 `step_ids`、step dependency 和 Wave。
- 每个 step 完成后执行绑定 `test_ids` 命令。

新增文件、符号、步骤或超出 change path 时立即停止，回到 ANALYSIS 修订范围并重新进入 WAITING_CONFIRM。

固定进度格式：

```markdown
[阶段：IMPLEMENT]

✅ R1-T2 / S4 完成
- 仓库：R1
- 文件与符号：F5 / `Class#method`
- 验证：T6 / `<command>`
- 依赖状态：hard 已满足；integration 待联调
```

## With Claude 边界

- ANALYSIS packet 必须携带 `spec_id`、`source_digest`、`selected_task_ids`、`repo_ids`、`dependency_summary` 和 `scope_digest`。
- `known_context` 只传 `scope_markdown` 的摘要或精确路径；`add_read_dirs` 只开放选中 repo 的必要代码目录。
- Host 与 Claude 使用相同 `source_sha256` 和 `scope_sha256`；任一 digest 不一致时丢弃 worker 结果并重新构造 packet。
- Claude 引用未选 task 正文、未选仓库文件或越界实施步骤时，丢弃该部分并在 `### Claude 协作` 报告越界。
- REVIEW 同样以已确认 task/change/test 范围为边界，不得借 review 扩大实施范围。

## 兼容与错误处理

- legacy：保留原有编号选择、全文读取、ANALYSIS 和确认流程。
- future schema：只报告不支持并停止，不按 legacy 执行。
- repo mismatch：停止，不把当前仓库猜成任意 `repo_id`。
- task mismatch 或跨仓 path 缺失：停止并请求用户选择/提供路径。
- baseline unavailable：不得直接实施。
- integration 未完成：允许完成本仓代码，但实施报告必须标为待联调。
- Canonical Spec 始终是只读设计基线；不得写入任务进度、测试结果或当前会话状态。
