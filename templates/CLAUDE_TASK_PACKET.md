# Claude Task Packet 模板

> 本模板仅供 Easy Coding With Claude 联合模式构造任务包时参考。
> 实际执行时必须按当前项目、阶段和已确认范围裁剪字段，不要把大段源码、密钥或无关上下文直接塞入任务包。
> `add_read_dirs` 只能填精确、窄范围目录；禁止 `/`、`$HOME`、`/Users`、`/Users/<user>` 等宽目录。
> 本模板中的 `phase` / `workflow_type` / `expected_output_type` / `status` / `verdict` 都不是 Easy Coding 用户可见阶段，不能输出为 `[阶段：...]`。

---

## ANALYSIS

Easy Coding 联合模式的 ANALYSIS 固定使用 `readonly_analysis`；不得改用 With Claude `plan_mode`。
Claude 运行期间 Easy Coding 用户可见阶段仍为 `[阶段：ANALYSIS]`，只有收到最终 worker contract 后才输出完整技术方案并进入确认阻断。

```json
{
  "user_request": "{用户当前需求}",
  "cwd": "{当前项目根目录}",
  "expected_output_type": "analysis",
  "workflow_type": "readonly_analysis",
  "phase": "analysis",
  "constraints": [
    "Claude worker is read-only.",
    "Claude must not mutate repository files.",
    "Host agent owns final judgment and all writes."
  ],
  "known_context": [
    "project_mode={初创项目/迭代项目}",
    "selected_dev_specs={当前需求已选 Dev-Spec 列表或无}",
    "conflicts={已识别冲突摘要}"
  ],
  "add_read_dirs": [],
  "readonly_policy": {
    "mutation_allowed": false,
    "allowed_tools": ["Read", "Grep", "Glob", "LS"]
  }
}
```

---

## INIT

```json
{
  "user_request": "Draft initialization assets for Easy Coding.",
  "cwd": "{当前项目根目录}",
  "expected_output_type": "analysis",
  "workflow_type": "readonly_analysis",
  "phase": "init_draft",
  "constraints": [
    "Claude drafts only; host agent writes files.",
    "Do not overwrite confirmed project assets.",
    "Do not absorb .easy-coding/spec/dev/ as long-term memory."
  ],
  "known_context": [
    "init_mode={interactive_init/post_v1_auto_init}",
    "target_assets=SOUL.md,RULES.md,ABSTRACT.md"
  ],
  "add_read_dirs": [],
  "readonly_policy": {
    "mutation_allowed": false,
    "allowed_tools": ["Read", "Grep", "Glob", "LS"]
  }
}
```

---

## REVIEW

仅在 IMPLEMENT 完成，且已有用户确认方案、变更清单、变更摘要、验证结果、host 自检结论和 diff 摘要后构造 REVIEW 任务包。

所有 REVIEW packet 必须使用 `workflow_type=post_implementation_review`、`phase=post_code_review`、`expected_output_type=review`。REVIEW 结果必须来自实际 Claude worker final contract；若未执行 Claude、启动失败或未收到 final contract，只能在 host 侧映射为 `blocked` 并标注 `Claude review unavailable`，不得输出 Claude `accept`。

```json
{
  "user_request": "Review host-agent implementation result.",
  "cwd": "{当前项目根目录}",
  "expected_output_type": "review",
  "workflow_type": "post_implementation_review",
  "phase": "post_code_review",
  "constraints": [
    "Claude reviews only.",
    "Claude must not patch, format, commit, push, or release.",
    "Host agent decides adoption and performs any fix."
  ],
  "implementation_context": {
    "approved_plan": "{用户已确认方案摘要}",
    "change_summary": "{host 变更摘要}",
    "changed_files": ["{文件路径}"],
    "test_results": ["{验证命令与结果}"],
    "host_self_check": "{编码、注释、范围与风险自检}",
    "diff_summary": "{diff 摘要，不粘贴大段源码}"
  },
  "review_scope": {
    "focus": ["scope adherence", "behavior regression", "missing tests"],
    "diff_summary": "{与 implementation_context.diff_summary 保持一致或进一步压缩后的 review 范围摘要}"
  },
  "add_read_dirs": [],
  "readonly_policy": {
    "mutation_allowed": false,
    "allowed_tools": ["Read", "Grep", "Glob", "LS"]
  }
}
```
