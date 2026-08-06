# Canonical Spec Fixture

<!-- EDS:MANIFEST:BEGIN -->
```json
{
  "schema": "easy-dev-spec/v1",
  "spec_id": "EDS-20260805-fixture",
  "revision": 1,
  "status": "READY",
  "title": "Canonical consumer fixture",
  "repositories": [
    {
      "repo_id": "R1",
      "name": "easy-coding",
      "remote_urls": ["git@github.com:example/easy-coding.git"],
      "path_hint": "/workspace/easy-coding",
      "baseline": {
        "ref": "main",
        "commit": "0000000000000000000000000000000000000000"
      },
      "tech_stack": ["Python"],
      "section_id": "repo-r1"
    },
    {
      "repo_id": "R2",
      "name": "downstream-service",
      "remote_urls": ["https://github.com/example/downstream-service.git"],
      "path_hint": "/workspace/downstream-service",
      "baseline": {
        "ref": "main",
        "commit": "1111111111111111111111111111111111111111"
      },
      "tech_stack": ["Python"],
      "section_id": "repo-r2"
    }
  ],
  "contracts": [
    {
      "contract_id": "C1",
      "name": "CanonicalScope#digest",
      "owner_task_id": "R1-T1",
      "consumer_task_ids": ["R2-T1"],
      "section_id": "contract-c1"
    }
  ],
  "tasks": [
    {
      "task_id": "R1-T1",
      "repo_id": "R1",
      "title": "解析 Canonical Spec",
      "status": "READY",
      "section_id": "task-r1-t1",
      "depends_on": [],
      "change_ids": ["F1"],
      "step_ids": ["S1"],
      "test_ids": ["T1"]
    },
    {
      "task_id": "R1-T2",
      "repo_id": "R1",
      "title": "接入任务级消费",
      "status": "READY",
      "section_id": "task-r1-t2",
      "depends_on": [
        {
          "task_id": "R1-T1",
          "type": "hard",
          "required_evidence": "parser tests pass"
        },
        {
          "task_id": "R2-T1",
          "type": "integration",
          "required_evidence": "integration report"
        }
      ],
      "change_ids": ["F2"],
      "step_ids": ["S2"],
      "test_ids": ["T2"]
    },
    {
      "task_id": "R2-T1",
      "repo_id": "R2",
      "title": "消费冻结契约",
      "status": "READY",
      "section_id": "task-r2-t1",
      "depends_on": [
        {
          "task_id": "R1-T1",
          "type": "contract",
          "required_evidence": "C1 frozen"
        }
      ],
      "change_ids": ["F3"],
      "step_ids": ["S3"],
      "test_ids": ["T3"]
    }
  ],
  "changes": [
    {
      "change_id": "F1",
      "task_id": "R1-T1",
      "repo_id": "R1",
      "module": "scripts",
      "path": "scripts/inspect_dev_spec.py",
      "action": "add",
      "symbols": ["parse_manifest"]
    },
    {
      "change_id": "F2",
      "task_id": "R1-T2",
      "repo_id": "R1",
      "module": "skill",
      "path": "SKILL.md",
      "action": "modify",
      "symbols": ["Dev-Spec candidate routing"]
    },
    {
      "change_id": "F3",
      "task_id": "R2-T1",
      "repo_id": "R2",
      "module": "downstream",
      "path": "downstream/secret.py",
      "action": "modify",
      "symbols": ["consume_scope"]
    }
  ],
  "steps": [
    {
      "step_id": "S1",
      "task_id": "R1-T1",
      "change_ids": ["F1"],
      "depends_on_step_ids": [],
      "test_ids": ["T1"]
    },
    {
      "step_id": "S2",
      "task_id": "R1-T2",
      "change_ids": ["F2"],
      "depends_on_step_ids": [],
      "test_ids": ["T2"]
    },
    {
      "step_id": "S3",
      "task_id": "R2-T1",
      "change_ids": ["F3"],
      "depends_on_step_ids": [],
      "test_ids": ["T3"]
    }
  ],
  "tests": [
    {
      "test_id": "T1",
      "task_id": "R1-T1",
      "file": "tests/test_inspect_dev_spec.py",
      "command": "python3 -m unittest tests.test_inspect_dev_spec"
    },
    {
      "test_id": "T2",
      "task_id": "R1-T2",
      "file": "tests/test_inspect_dev_spec.py",
      "command": "python3 -m unittest tests.test_inspect_dev_spec"
    },
    {
      "test_id": "T3",
      "task_id": "R2-T1",
      "file": "tests/test_consumer.py",
      "command": "python3 -m unittest tests.test_consumer"
    }
  ]
}
```
<!-- EDS:MANIFEST:END -->

<!-- EDS:SECTION:BEGIN id=global-context -->
## 全局约束

只允许消费已选择任务的闭包。
<!-- EDS:SECTION:END id=global-context -->

<!-- EDS:SECTION:BEGIN id=contract-c1 -->
## C1：CanonicalScope#digest

`scope_sha256` 必须由 UTF-8 的消费闭包计算。
<!-- EDS:SECTION:END id=contract-c1 -->

<!-- EDS:SECTION:BEGIN id=repo-r1 -->
## R1：easy-coding

Canonical Spec 消费端。
<!-- EDS:SECTION:END id=repo-r1 -->

<!-- EDS:SECTION:BEGIN id=repo-r2 -->
## R2：downstream-service

下游契约消费者。
<!-- EDS:SECTION:END id=repo-r2 -->

<!-- EDS:SECTION:BEGIN id=task-r1-t1 -->
## R1-T1：解析 Canonical Spec

- 交付物：标准库解析器。
- 文件：`scripts/inspect_dev_spec.py`。
<!-- EDS:SECTION:END id=task-r1-t1 -->

<!-- EDS:SECTION:BEGIN id=task-r1-t2 -->
## R1-T2：接入任务级消费

- 交付物：任务级范围门禁。
- 文件：`SKILL.md`。
<!-- EDS:SECTION:END id=task-r1-t2 -->

<!-- EDS:SECTION:BEGIN id=task-r2-t1 -->
## R2-T1：消费冻结契约

- 交付物：下游消费实现。
- 内部文件：`downstream/secret.py`。
<!-- EDS:SECTION:END id=task-r2-t1 -->

<!-- EDS:SECTION:BEGIN id=integration-plan -->
## 联调计划

| 任务 | 对端 | 门禁 |
| --- | --- | --- |
| R1-T2 | R2-T1 | scope digest 一致 |
| R2-T1 | R1-T1 | C1 已冻结 |
<!-- EDS:SECTION:END id=integration-plan -->

<!-- EDS:SECTION:BEGIN id=rollout-plan -->
## 发布计划

按 Wave 发布。
<!-- EDS:SECTION:END id=rollout-plan -->

<!-- EDS:SECTION:BEGIN id=end-to-end-acceptance -->
## 端到端验收

消费者不泄漏未选任务正文。
<!-- EDS:SECTION:END id=end-to-end-acceptance -->
