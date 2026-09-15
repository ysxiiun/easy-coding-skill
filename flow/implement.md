# IMPLEMENT：候选落地

> 仅在用户确认完整方案后读取。本文件只负责项目写入与实施自检；确定性验证属于 QUALITY。

## 1. 进入与基线

在输出 IMPLEMENT 或任何项目写入前，先按 `flow/analysis.md` 第 5 节核对：当前完整方案的
定位、方案展示之后的真实用户确认原话或实际选择结果，以及拟实施范围与批准范围的一致性。
同一任务、同一方案的有效确认可沿用到续流与范围内 Repair Bundle；缺失、无法核实或因方案
实质变化而失效时，保持或返回 `[阶段：ANALYSIS]`，补齐方案并等待确认。不得用任务启动
指令、模型推断或基线检查通过代替用户确认。

复核通过后，输出 `[阶段：IMPLEMENT]` 并简述确认依据（方案定位、用户原话或选择结果、
范围一致结论），重读相关规则、目标文件和 Local Baseline，复用 ANALYSIS
已经冻结的 `run_id=ec-skill-<UUIDv7>` 和当前 `quality_round`；不得在 IMPLEMENT 另生成 ID，
也不得因同一 writer 调用重试而递增 round。

ANALYSIS 已从本 Skill 实际目录运行：

```bash
python3 <skill-dir>/scripts/quality_fingerprint.py baseline \
  --repo <repo-id>=<repo-root> [...] \
  --output <system-temp>/easy-coding-<run-id>-baseline.json
```

输出必须位于所有仓库外。进入实施前，对原 baseline 运行 `capture`，使用确认的 scope/ignore，
按本轮是否已开始项目写入区分：

- 首次项目写入前：要求 HEAD 未移动且 `changes`、`unexpected_changes`、`ignored_changes`
  都为空；否则停止并返回 ANALYSIS，刷新事实和 baseline，不能把确认等待期间的改动静默
  吸收为候选。
- 已开始本轮项目写入的续流或范围内 Repair Bundle：保留原 baseline，要求 HEAD 未移动、
  `unexpected_changes` 为空。已批准 Unit 的代码/测试候选和有 writer 证据的 ignore 变化
  可以非空，包括仅完成 Canonical execution 写回、尚无业务候选的暂停恢复。已有 QUALITY
  指纹、方案未修订，且该指纹之后没有本轮已记录写入时，先用该指纹核对候选；否则逐项核对已落地
  Unit、Repair Bundle、writer 证据与当前 diff，不能把旧方案或修复前指纹当作当前通过证据。
  无法解释的漂移先停止写入并核查，不能通过刷新 baseline 吸收已有候选。已确认的修订方案
  同样保留原 baseline，按新 scope/ignore 覆盖本轮全部应交付或处理的候选。

Canonical 任务同时读取 `references/dev-spec/canonical-v1.md`：方案确认后才初始化 execution，
随后把 task 写为 `in_progress`。Canonical locator 位于某个目标 repo 内时才转为该 repo 的机器
ignore；repo 外 locator 天然不在 Git 业务候选中，不传 `--ignore`。两种情况的设计摘要与
execution revision 都由 writer 独立校验。

## 2. 落地约束

- 只修改已确认 Unit 中的文件、符号和测试；不得加入顺手优化或未经确认的生成物。
- 旧文件保持原编码、换行与字符集；新文件遵循项目编码和同类文件惯例。
- 注释只解释非直观业务规则、协议、异常、幂等/并发和风险边界；禁止逐行或无信息注释。
- 需要作者署名时使用 `${Agent Name} with Easy Coding`。
- 初创项目按确认 Spec 落地最小完整闭环；迭代项目保守适配真实实现。
- 前端必须接入真实路由、组件、状态与接口契约；Prototype/mock 不能冒充生产结果。
- 不安装或生成测试基础设施。项目缺少必要验证能力时，作为 QUALITY 环境事实披露。
- 接口、契约、范围或交付形态变化时立即停止并返回 ANALYSIS；用户实施中变更需求同样处理。

## 3. Unit 实施与自检

按依赖顺序完成每个 Unit。允许的自检仅包括：

- 回看本轮 diff，确认改动只落在 scope/ignore；
- 检查编码、换行、注释语种、署名和明显语法/拼写错误；
- 核对测试文件已按方案落地，但不在本阶段运行确定性 lint/typecheck/test/build；
- Canonical change/Step/Test 映射没有越界。

每个 Unit 可用以下格式汇报进度：

```markdown
[阶段：IMPLEMENT]

✅ Unit {N}/{总数}：{目标}
- 文件/符号：{范围}
- 代码与测试：{落地摘要}
- 范围/编码/注释自检：{结论}
```

发现范围内代码或测试缺陷时可在本阶段修复；QUALITY 返回的 Repair Bundle 必须作为一个
整体完成，禁止只修部分后反复进门。

## 4. 进入 QUALITY

全部 Unit 落地且实施自检通过后，输出候选文件摘要并自动读取 `flow/quality.md`。此处不等待
用户确认，不写 Step `completed`、task `implemented/verified`，也不创建记忆。

若任务没有任何项目文件候选变更，停止并解释原因；不能用空候选伪装完成。
