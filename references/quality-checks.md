# QUALITY 检查输入与证据复用

> ANALYSIS 确定检查输入、QUALITY 执行或复用检查时按需读取。脚本只管理本轮检查结果，
> 不管理阶段、审批或任务；范围内修复仍返回 IMPLEMENT。

## 输入合同

每项检查使用稳定的 `id`（例如 `U1-test`、`U1-production-review`），绑定一个 Unit 或一组
真实共用输入的检查。`inputs` 使用 baseline 中的 repo ID 和仓库内相对路径，支持文件、目录；
不是修改文件清单，而是该检查实际读取的输入闭包：

- 生产源码、选中的测试及公共 helper、fixture、资源和直接依赖模块；
- 构建文件、父级构建配置、锁文件、编译/测试配置及实际使用的脚本；
- review 的确认需求、验收条件和关注维度写入 `contract`；验证使用完整实际 `command`；
- `cwd` 标明实际命令工作目录，并绑定其解析后的真实目录；`toolchain` 按该目录解析相对
  PATH 和工具路径，列出解释器、构建器等实际可执行文件，
  如 `python3`，或 `mvn` 与 `java`。工具安装目录中的依赖配置仍需纳入输入或设为不可复用；
- `environment` 只列有影响的变量名，例如 `JAVA_HOME`、`PYTHONPATH`、`NODE_OPTIONS`。
  准备、实际执行和登记必须使用相同环境覆盖；脚本只保存环境值摘要，不输出原值。

优先用项目 TEST_STRATEGY 和真实构建链确定闭包。Maven/Gradle 会编译模块内其他源码，不能
仅按 `-Dtest` 测试名缩成单文件。闭包不明确时覆盖整个受影响模块及依赖；省略 `inputs` 会
覆盖 baseline 的全部仓库。不要为提高命中率漏掉依赖。

目录收集 Git 跟踪和未忽略文件，能识别新增、删除、改名与内容变化；被 Git 忽略但实际被
消费的文件必须显式列出。依赖空目录存在时也须显式列出该路径；依赖无法列全的目录布局或
枚举结果时设 `volatile: true`。只比较工作区内容，单纯 git add 不使测试失效。符号链接、特殊
文件或未展开的嵌套仓输入不能证明完整依赖，返回 `uncacheable_inputs` 并禁止跨轮复用；
应补齐独立仓输入或每轮真实执行。外部服务、未固定外部依赖等不可由文件证明的检查使用
`volatile: true`，每轮执行。输出目录、Canonical execution 和过程记录不是业务检查输入。

## 仓库外检查存储

默认使用本轮 baseline 同目录下的 `easy-coding-<run-id>-checks.json`；dispatch 已开启时用
交接目录的 `checks.json`。存储绑定原始 baseline 内容，只保留每项检查的最新结果和正在
准备的输入，不生成项目 tasks/sessions 或历史流水。主 Agent 是唯一写入方，串行准备和登记；
检查本身可使用同一批冻结输入，任何代码修改后必须重新准备。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/quality_checks.py prepare \
  --baseline <baseline.json> --store <checks.json绝对路径> --apply <<'JSON'
[
  {"id":"U1-review","type":"review","inputs":{"main":["src/module","tests/test_module.py"]},
   "contract":"当前已确认行为、验收条件、边界及需要审查的直接交互"},
  {"id":"U1-test","type":"verify","inputs":{"main":["src/module","tests/test_module.py","tests/helpers","pyproject.toml"]},
   "cwd":"main:.","command":"python3 -m unittest tests.test_module",
   "toolchain":["python3"],"environment":["PATH","PYTHONPATH"]}
]
JSON
```

示例路径必须换成项目真实闭包，不照抄。每个返回项：

- `reusable: true`：沿用返回的原始 `evidence`，保留来源和执行时间，不重新审查/执行。
- `reusable: false`：只执行该项，使用本次 `prepared_id` 登记真实结果；`changed_inputs`
  说明变化。没有历史通过、最新失败、`volatile` 或不可证明的输入同样要求执行。
- 新发现的具体缺陷使既有结论不成立时，对受影响检查用 `prepare --force`；不得因为
  “再保险”而强制重跑，也不得修改存储伪造通过。

实际执行后批量登记：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/quality_checks.py record \
  --baseline <baseline.json> --store <checks.json绝对路径> --apply <<'JSON'
[
  {"id":"U1-review","prepared_id":"本次返回值","passed":true,
   "reviewer":"independent:coordinator","summary":"实际审查范围与结论"},
  {"id":"U1-test","prepared_id":"本次返回值","passed":true,"exit_code":0,
   "summary":"实际命令结果"}
]
JSON
```

失败同样登记，verification 的 `passed` 必须与真实 `exit_code` 一致。record 会重新读取输入，
执行期间漂移则拒收；命令成功也不能覆盖漂移。失败后的旧通过结果不再复用。成功登记的同一
回执可原样重试；不同结果需要新一次 prepare。省略 `--apply` 仅预览，不能用于放行检查。

一个实际组合命令若覆盖多项计划验证，可以一次运行、分别登记各项结果，描述符都填写该
实际命令及完整输入；不能先分别执行，再无依据重复组合 clean。现有测试一次同时产出覆盖率
时复用该次结果，不因此新增覆盖率门禁或安装工具。

## 与候选指纹、修复和 Canonical 的关系

`quality_fingerprint.py` 继续负责整体 HEAD、候选范围、ignore 和意外漂移。整体候选发生变化
后旧 GREEN 不可直接放行，但单项结果不按阶段名、交接轮次或 Spec 修订号整体作废。修复后
先重新 capture 当前候选，再用当前检查合同 prepare；只重跑真实输入变化或被具体缺陷推翻的
检查。输入未变的结果可以汇总进新候选的 QUALITY 回执，并明确是复用原证据。

审查合同变化只使对应审查失效，不使源码、配置和命令均未变的测试失效。审查修复增量及其
直接影响，保留已通过且不受影响的结论。Canonical 仍按当前 quality_round 和 candidate SHA
写回全部所需 Step 证据；`ref` 区分当前候选与复用证据的 input SHA、原命令/结果，不声称重跑。

HEAD 漂移、范围外修改、缺失基线仍先按原候选门禁处理，不能靠命中缓存绕过。缓存缺失时只
补必要检查；不要重建原 baseline 或重做全部分析。最终 QUALITY 回执保留当前候选、每项检查
的新执行/复用来源和真实结果。MEMORY 保存必要质量摘要后，COMPLETE/CLOSED 清理本轮存储。
