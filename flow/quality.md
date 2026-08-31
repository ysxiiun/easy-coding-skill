# QUALITY：Standard 双门与 Guard 结果确认

> IMPLEMENT 完成后自动读取。本文件是候选指纹、审查、验证、修复路由和结果确认的唯一
> 权威来源。QUALITY 不提供模式选择。

## 1. 冻结候选

输出 `[阶段：QUALITY]`。使用 ANALYSIS 创建、IMPLEMENT 写入前复核通过的 baseline，以及确认
方案中的 scope/ignore：

```bash
python3 <skill-dir>/scripts/quality_fingerprint.py capture \
  --baseline <baseline.json> \
  --scope <repo-id>:<path> [...] \
  --ignore <repo-id>:<machine-path> [...] \
  --output <system-temp>/easy-coding-<run-id>-candidate.json
```

必须确认：所有 repo HEAD 未移动、`unexpected_changes` 为空、候选非空。记录
`candidate_sha256`、逐仓 HEAD 和范围内变化。repo 内 Canonical locator 作为对应 repo 的机器
ignore；repo 外 locator 不传 `--ignore`，只在独立 writer 证据中记录。ignore 只允许
Canonical execution 等机器事实；
其 writer 事件、design SHA 和 execution revision 必须在独立证据中记录。

`candidate_sha256` 同时绑定每个 repo 的 HEAD、确认 scope/ignore 和范围内状态差异；Gate 期间
不得扩大 scope 或新增 ignore。`capture` 后的审查门和验证门都绑定同一 candidate SHA。每个
门结束后运行：

```bash
python3 <skill-dir>/scripts/quality_fingerprint.py check \
  --baseline <baseline.json> --expected <candidate_sha256> \
  --scope <repo-id>:<path> [...] --ignore <repo-id>:<machine-path> [...]
```

返回 3 表示 HEAD、候选或范围外发生漂移；本轮所有 Gate 证据立即失效，返回 IMPLEMENT 重新
检查候选。Gate 期间新出现且未单列 repo 的脏 gitlink 也按漂移返回 3；baseline/capture 已有
脏 gitlink 未单列子仓属于输入边界错误并返回 2。其他返回 2 保持 QUALITY 修正调用。
未覆盖的 nested Git root 使用相同规则：baseline/capture 返回 2，Gate 期间新出现时 check
返回 3。

## 2. 审查门

优先调用一个宿主原生独立 reviewer，对冻结候选做只读审查；不可用、被禁用或调用失败时，
主代理自动按同一清单完成自审，不向用户请求降级许可。必须记录来源：

- `independent:<host mechanism>`；或
- `host-fallback:<unavailable|disabled|failed>`。

统一清单：

1. 是否忠于确认需求、Unit 和明确不做项；
2. 边界、异常、状态、数据流、兼容与安全是否正确；
3. 是否出现范围外改动、无依据兜底、重复抽象或生成物；
4. 测试是否覆盖受影响行为并能真实失败，而非只验证实现细节；
5. 编码、注释、项目规则、Canonical change/Test 契约是否一致；
6. 多仓时子仓边界、父 gitlink 和依赖方向是否正确。

发现统一分类：

| 分类 | 是否阻断 | 路由 |
| --- | --- | --- |
| `code-defect` | 是 | 与测试缺陷聚合成一次 Repair Bundle，返回 IMPLEMENT |
| `test-defect` | 是 | 与代码缺陷聚合成一次 Repair Bundle，返回 IMPLEMENT |
| `contract-ambiguity` | 是 | 返回 ANALYSIS，重新确认范围/契约 |
| `environment` | 是 | 保持 QUALITY，说明缺失条件和已完成证据 |
| `suggestion` | 否 | 记录但不擅自扩大范围 |

Repair Bundle 必须一次列全：严重度、文件/位置、原因、修复目标和回归验证。修复前 Canonical
按当前 task 状态落阻断事实：

- task 仍为 `in_progress`：受影响 Step 写 `failed`，writer 随之把 task 置为 `blocked`；没有
  可归属 Step 的阻断才直接把 task 写 `blocked`；
- task 已为 `implemented`（例如 Guard 回执后的用户缺陷反馈）：直接把 task 写 `blocked`，
  不能在非 `in_progress` 状态强写 Step；下一轮 QUALITY 必须用新 candidate 重新写全部 Step
  `completed` 证据。

阻断事实写入成功后递增 `quality_round`，再把 task 重开为 `in_progress` 并返回 IMPLEMENT。
当前 round 进入 Canonical writer 的幂等键；同一调用重试复用原 key，Repair Bundle 后不得复用
上一 round 的 `in_progress/completed/implemented` key。契约/范围歧义返回 ANALYSIS 前直接写
task `blocked`；恢复修改时同样先递增 round。环境阻断不改变候选时保持当前 round。
修复完成重新 capture，旧 candidate SHA 和旧 Gate 证据作废。

## 3. 验证门

审查门通过且指纹 `check` 为 0 后，按 ANALYSIS 的精确计划执行：

1. 受影响 lint；
2. 受影响 typecheck；
3. 受影响 test；
4. 契约、构建配置、项目规则或交付形态要求的 build。

不得在此安装测试基础设施、扩大测试面或临时修改项目配置来制造绿色结果。命令失败时分类：

- 代码/测试原因：聚合 Repair Bundle 返回 IMPLEMENT；
- 契约不清：返回 ANALYSIS；
- 环境原因：保持 QUALITY，列出命令、错误、已排除原因和恢复条件；
- 非阻断建议：记录剩余风险。

所有命令保留退出码和简洁结果。完成后再次 `check`，确保验证未改变候选或产生范围外文件。

## 4. Canonical QUALITY 时序

两门绿色且 candidate 未漂移后：

1. 对每个完成 Step 通过 writer 写 `completed`，携带绑定 Canonical `test_id` 的 passed 证据，
   证据 `ref` 同时记录验证命令/结果和 candidate SHA；
2. 全部 Step 完成后把 task 写为 `implemented`；
3. 再次 `show`/`--refresh-only` 检查 integration；
4. integration 未满足时保持 QUALITY/`implemented`，不展示最终结果确认；
5. integration 满足后展示 Guard 结果；用户确认后把 task 写为 `verified`，再进入 MEMORY；
6. MEMORY 成功后才写 `completed`。

Canonical 受控写回后再次执行 fingerprint `check`；ignore 路径不改变业务候选，但 writer 的
CAS、事件证据与状态必须成功。

## 5. Guard 绿色回执与确认

只有审查门、验证门、最终指纹和 Canonical integration（如适用）全部绿色时输出：

```markdown
[阶段：QUALITY]

## Guard 结果：GREEN

- 候选摘要：{candidate_sha256、仓库 HEAD、范围内文件}
- reviewer 来源：{independent / host-fallback 及原因}
- 发现与修复：{分类、Repair Bundle 轮次；无则写无}
- 验证命令与结果：{命令、退出码、结果}
- Canonical：{不适用或 Step completed / task implemented / integration satisfied}
- 剩余风险：{suggestion、环境边界或无}

请确认本次 QUALITY 结果；确认后才进入 MEMORY。
```

输出后立即停止。有原生选择工具时提供“确认 QUALITY 结果（推荐）”与“保持 QUALITY”；用户
反馈缺陷时按分类路由，不能把反馈直接当确认。确认后 Canonical task 先写 `verified`，再读取
`flow/memory.md`。
