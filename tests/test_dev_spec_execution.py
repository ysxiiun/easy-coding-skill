from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.dev_spec_execution import (
    ExecutionConflictError,
    ExecutionStateError,
    initialize_execution,
    record_dependency_status,
    record_step_status,
    record_task_status,
    render_document,
    show_execution,
    sync_design,
)
from scripts.easy_dev_spec_protocol import (
    MANIFEST_BEGIN,
    MANIFEST_END,
    UPSTREAM_PROTOCOL_COMMIT,
    UPSTREAM_PROTOCOL_SHA256,
    UPSTREAM_SOURCE_SHA256,
    CanonicalSpecError,
    design_sha256,
    parse_manifest,
    parse_sections,
    select_scope,
    split_execution_region,
    validate_model,
    validate_spec,
)


FIXTURES = Path(__file__).parent / "fixtures"
VALID = FIXTURES / "easy-dev-spec-v1-final.md"
LEGACY = FIXTURES / "legacy-dev-spec.md"
APP = "easy-coding"
AGENT = "Codex with Easy Coding"
WRITER_CLI = Path(__file__).parents[1] / "scripts" / "update_dev_spec_execution.py"


def _execution_task(execution: dict, task_id: str) -> dict:
    return next(task for task in execution["tasks"] if task["task_id"] == task_id)


def _replace_manifest(text: str, manifest: dict) -> str:
    start = text.index(MANIFEST_BEGIN) + len(MANIFEST_BEGIN)
    end = text.index(MANIFEST_END)
    block = "\n```json\n" + json.dumps(manifest, ensure_ascii=False, indent=2) + "\n```\n"
    return text[:start] + block + text[end:]


def _passed(test_id: str, ref: str = "canonical test passes") -> list[dict]:
    return [{"kind": "test", "status": "passed", "test_id": test_id, "ref": ref}]


class DevSpecExecutionTest(unittest.TestCase):
    def _copy_spec(self, directory: str, name: str = "shared-spec.md") -> Path:
        spec = Path(directory) / name
        spec.write_text(VALID.read_text(encoding="utf-8"), encoding="utf-8")
        return spec

    def test_arbitrary_external_path_initializes_and_writes_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            execution = initialize_execution(spec, expected_design_sha256=digest)
            self.assertEqual(0, execution["execution_revision"])
            updated = record_task_status(
                spec,
                "R1-T1",
                "in_progress",
                "开始实现。",
                APP,
                AGENT,
                digest,
                0,
                run_id="run-external",
                idempotency_key="run-external:R1-T1:start",
            )
            self.assertEqual(1, updated["execution_revision"])
            shown = show_execution(spec)
            self.assertEqual("order-notification-2026", shown["spec_id"])
            self.assertTrue(shown["execution"]["tasks"])

    def test_execution_updates_only_document_and_execution_scope_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            before = select_scope(spec, "R1", ["R1-T1"], output_format="json")
            digest = before["design_sha256"]
            initialize_execution(spec, expected_design_sha256=digest)
            record_task_status(
                spec,
                "R1-T1",
                "in_progress",
                "开始实现。",
                APP,
                AGENT,
                digest,
                0,
                run_id="run-digest",
                idempotency_key="run-digest:R1-T1:start",
            )
            after = select_scope(spec, "R1", ["R1-T1"], output_format="json")
            self.assertEqual(before["design_sha256"], after["design_sha256"])
            self.assertEqual(before["design_scope_sha256"], after["design_scope_sha256"])
            self.assertNotEqual(before["document_sha256"], after["document_sha256"])
            self.assertNotEqual(
                before["execution_scope_sha256"], after["execution_scope_sha256"]
            )

    def test_stale_revision_and_idempotency_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            first = record_task_status(
                spec,
                "R1-T1",
                "in_progress",
                "开始实现。",
                APP,
                AGENT,
                digest,
                0,
                run_id="run-cas",
                idempotency_key="run-cas:R1-T1:start",
            )
            retried = record_task_status(
                spec,
                "R1-T1",
                "in_progress",
                "开始实现。",
                APP,
                AGENT,
                digest,
                0,
                run_id="run-cas",
                idempotency_key="run-cas:R1-T1:start",
            )
            self.assertEqual(1, first["execution_revision"])
            self.assertEqual(1, retried["execution_revision"])
            self.assertEqual(1, len(retried["events"]))
            with self.assertRaises(ExecutionConflictError):
                record_task_status(
                    spec, "R2-T1", "in_progress", "过期写入。", APP, AGENT, digest, 0
                )
            with self.assertRaises(ExecutionConflictError):
                record_task_status(
                    spec,
                    "R1-T1",
                    "in_progress",
                    "复用幂等键但摘要不同。",
                    APP,
                    AGENT,
                    digest,
                    0,
                    run_id="run-cas",
                    idempotency_key="run-cas:R1-T1:start",
                )

    def test_hard_contract_and_integration_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)

            contract_task = record_task_status(
                spec, "R2-T1", "in_progress", "READY 契约允许开始。", APP, AGENT, digest, 0
            )
            self.assertEqual("in_progress", _execution_task(contract_task, "R2-T1")["status"])
            with self.assertRaises(ExecutionStateError):
                record_task_status(
                    spec,
                    "R1-T2",
                    "in_progress",
                    "试图绕过 hard 前置。",
                    APP,
                    AGENT,
                    digest,
                    contract_task["execution_revision"],
                )

            execution = record_dependency_status(
                spec,
                "R1-T2",
                "R1-T1",
                "satisfied",
                "外部构件证明 hard 前置满足。",
                APP,
                AGENT,
                digest,
                contract_task["execution_revision"],
                evidence=[{"kind": "artifact", "status": "recorded", "ref": "api@1"}],
            )
            execution = record_task_status(
                spec,
                "R1-T2",
                "in_progress",
                "开始本仓编码。",
                APP,
                AGENT,
                digest,
                execution["execution_revision"],
            )
            execution = record_step_status(
                spec,
                "R1-T2",
                "S3",
                "completed",
                "S3 与绑定测试完成。",
                APP,
                AGENT,
                digest,
                execution["execution_revision"],
                evidence=_passed("T3"),
            )
            execution = record_task_status(
                spec,
                "R1-T2",
                "implemented",
                "实现完成。",
                APP,
                AGENT,
                digest,
                execution["execution_revision"],
            )
            execution = record_task_status(
                spec,
                "R1-T2",
                "verified",
                "验证完成。",
                APP,
                AGENT,
                digest,
                execution["execution_revision"],
                evidence=_passed("T3"),
            )
            with self.assertRaises(ExecutionStateError):
                record_task_status(
                    spec,
                    "R1-T2",
                    "completed",
                    "integration 未闭合不能完成。",
                    APP,
                    AGENT,
                    digest,
                    execution["execution_revision"],
                )
            satisfied = record_dependency_status(
                spec,
                "R1-T2",
                "R2-T1",
                "satisfied",
                "联调证据已确认。",
                APP,
                AGENT,
                digest,
                execution["execution_revision"],
                evidence=[
                    {"kind": "artifact", "status": "recorded", "ref": "e2e passes"}
                ],
            )
            completed = record_task_status(
                spec,
                "R1-T2",
                "completed",
                "用户确认实施结果。",
                APP,
                AGENT,
                digest,
                satisfied["execution_revision"],
            )
            self.assertEqual("completed", _execution_task(completed, "R1-T2")["status"])

    def test_completed_predecessor_satisfies_hard_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            execution = initialize_execution(spec, expected_design_sha256=digest)
            execution = record_task_status(
                spec,
                "R1-T1",
                "in_progress",
                "开始前置任务。",
                APP,
                AGENT,
                digest,
                execution["execution_revision"],
            )
            execution = record_step_status(
                spec,
                "R1-T1",
                "S1",
                "completed",
                "S1 和 T1 完成。",
                APP,
                AGENT,
                digest,
                execution["execution_revision"],
                evidence=_passed("T1"),
            )
            for status_value in ("implemented", "verified", "completed"):
                execution = record_task_status(
                    spec,
                    "R1-T1",
                    status_value,
                    f"进入 {status_value}。",
                    APP,
                    AGENT,
                    digest,
                    execution["execution_revision"],
                )
            dependent = select_scope(spec, "R1", ["R1-T2"], output_format="json")
            by_type = {
                item["type"]: item
                for item in dependent["execution"]["dependency_status"]
            }
            self.assertEqual("satisfied", by_type["hard"]["status"])
            self.assertEqual("dependency-task-completed", by_type["hard"]["basis"])
            self.assertEqual("pending", by_type["integration"]["status"])

    def test_step_ownership_start_test_and_failure_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            with self.assertRaises(ExecutionStateError):
                record_step_status(
                    spec, "R1-T1", "S1", "completed", "未开始。", APP, AGENT, digest, 0,
                    evidence=_passed("T1"),
                )
            execution = record_task_status(
                spec, "R1-T1", "in_progress", "显式开始。", APP, AGENT, digest, 0
            )
            with self.assertRaises(ExecutionStateError):
                record_step_status(
                    spec,
                    "R1-T1",
                    "S2",
                    "completed",
                    "S2 不属于当前任务。",
                    APP,
                    AGENT,
                    digest,
                    execution["execution_revision"],
                    evidence=_passed("T2"),
                )
            with self.assertRaises(ExecutionStateError):
                record_step_status(
                    spec,
                    "R1-T1",
                    "S1",
                    "completed",
                    "缺少绑定测试。",
                    APP,
                    AGENT,
                    digest,
                    execution["execution_revision"],
                    evidence=[{"kind": "build", "status": "passed", "ref": "build ok"}],
                )
            failed = record_step_status(
                spec,
                "R1-T1",
                "S1",
                "failed",
                "S1 失败。",
                APP,
                AGENT,
                digest,
                execution["execution_revision"],
            )
            snapshot = _execution_task(failed, "R1-T1")
            self.assertEqual("blocked", snapshot["status"])
            self.assertEqual(["S1"], snapshot["failed_step_ids"])

    def test_task_status_order_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            with self.assertRaises(ExecutionStateError):
                record_task_status(
                    spec, "R1-T1", "implemented", "越过开始与 Step。", APP, AGENT, digest, 0
                )

    def test_step_dependency_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory, "ordered-steps.md")
            text = spec.read_text(encoding="utf-8")
            manifest = copy.deepcopy(parse_manifest(text))
            task = next(value for value in manifest["tasks"] if value["task_id"] == "R1-T1")
            task["step_ids"] = ["S4", "S1"]
            step = next(value for value in manifest["steps"] if value["step_id"] == "S1")
            step["depends_on_step_ids"] = ["S4"]
            manifest["steps"].insert(
                0,
                {
                    "step_id": "S4",
                    "task_id": "R1-T1",
                    "change_ids": ["F1"],
                    "depends_on_step_ids": [],
                    "test_ids": ["T1"],
                },
            )
            text = _replace_manifest(text, manifest)
            text = text.replace(
                "- `S1`：在 `OrderApplicationService#createOrder`",
                "- `S4`：新增 `OrderEventPublisher#publish`；输入为非空事件，输出 void，失败抛出异常。绑定 `F1` 和 `T1`。\n\n"
                "- `S1`：在 `OrderApplicationService#createOrder`",
                1,
            ).replace("- `T1` 覆盖 `S1`，", "- `T1` 覆盖 `S4` 和 `S1`，", 1)
            spec.write_text(text, encoding="utf-8")
            report = validate_spec(spec, require_ready=True)
            self.assertTrue(report.ok, [issue.to_dict() for issue in report.issues])
            digest = design_sha256(text)
            execution = initialize_execution(spec, expected_design_sha256=digest)
            execution = record_task_status(
                spec,
                "R1-T1",
                "in_progress",
                "开始有序步骤。",
                APP,
                AGENT,
                digest,
                execution["execution_revision"],
            )
            with self.assertRaises(ExecutionStateError):
                record_step_status(
                    spec,
                    "R1-T1",
                    "S1",
                    "completed",
                    "不能越过 S4。",
                    APP,
                    AGENT,
                    digest,
                    execution["execution_revision"],
                    evidence=_passed("T1"),
                )

    def test_forged_snapshot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            design_text, execution = split_execution_region(spec.read_text(encoding="utf-8"))
            assert execution is not None
            execution["execution_revision"] = 1
            forged = _execution_task(execution, "R1-T1")
            forged["status"] = "completed"
            forged["completed_step_ids"] = ["S1"]
            spec.write_text(render_document(design_text, execution), encoding="utf-8")
            report = validate_spec(spec, require_execution=True)
            codes = {issue.code for issue in report.issues}
            self.assertIn("execution.revision", codes)
            self.assertIn("execution.event_chain", codes)

    def test_unsynced_design_blocks_idempotent_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            record_task_status(
                spec,
                "R1-T1",
                "in_progress",
                "开始实现。",
                APP,
                AGENT,
                digest,
                0,
                idempotency_key="run-design:R1-T1:start",
            )
            spec.write_text(
                spec.read_text(encoding="utf-8").replace(
                    "订单成功提交后发布事件", "订单成功提交后可靠发布事件", 1
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ExecutionConflictError):
                record_task_status(
                    spec,
                    "R1-T1",
                    "in_progress",
                    "开始实现。",
                    APP,
                    AGENT,
                    digest,
                    0,
                    idempotency_key="run-design:R1-T1:start",
                )

    def test_sync_design_requires_exact_revision_and_resets_successors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            old_digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=old_digest)
            spec.write_text(
                spec.read_text(encoding="utf-8").replace('"revision": 1,', '"revision": 3,', 1),
                encoding="utf-8",
            )
            with self.assertRaises(ExecutionStateError):
                sync_design(
                    spec, ["R1-T1"], "非法跳修订。", APP, AGENT, old_digest, 0
                )

            spec.write_text(
                spec.read_text(encoding="utf-8").replace('"revision": 3,', '"revision": 2,', 1),
                encoding="utf-8",
            )
            execution = sync_design(
                spec,
                ["R1-T1"],
                "revision 2 重置受影响闭包。",
                APP,
                AGENT,
                old_digest,
                0,
                run_id="run-sync",
                idempotency_key="run-sync:revision-2",
            )
            self.assertEqual(2, execution["design_revision"])
            self.assertEqual(1, execution["execution_revision"])
            self.assertEqual(
                {"R1-T1", "R1-T2", "R2-T1"},
                {task["task_id"] for task in execution["tasks"]},
            )
            self.assertTrue(all(task["status"] == "not_started" for task in execution["tasks"]))
            retried = sync_design(
                spec,
                ["R1-T1"],
                "revision 2 重置受影响闭包。",
                APP,
                AGENT,
                old_digest,
                0,
                run_id="run-sync",
                idempotency_key="run-sync:revision-2",
            )
            self.assertEqual(1, retried["execution_revision"])
            self.assertEqual(1, len(retried["events"]))

    def test_same_revision_static_edit_after_sync_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = self._copy_spec(directory)
            old_digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=old_digest)
            spec.write_text(
                spec.read_text(encoding="utf-8").replace('"revision": 1,', '"revision": 2,', 1),
                encoding="utf-8",
            )
            sync_design(
                spec,
                ["R1-T1"],
                "同步 revision 2。",
                APP,
                AGENT,
                old_digest,
                0,
                idempotency_key="run-static:revision-2",
            )
            spec.write_text(
                spec.read_text(encoding="utf-8").replace(
                    "订单成功提交后发布事件", "订单成功提交后可靠发布事件", 1
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ExecutionConflictError):
                sync_design(
                    spec,
                    ["R1-T1"],
                    "同步 revision 2。",
                    APP,
                    AGENT,
                    old_digest,
                    0,
                    idempotency_key="run-static:revision-2",
                )

    def test_legacy_and_missing_execution_remain_read_only_compatible(self) -> None:
        legacy = validate_spec(LEGACY)
        compatible = validate_spec(VALID, require_ready=True)
        strict = validate_spec(VALID, require_ready=True, require_execution=True)
        self.assertTrue(legacy.ok)
        self.assertEqual("legacy", legacy.protocol)
        self.assertTrue(compatible.ok)
        self.assertIn("execution.missing", {warning.code for warning in compatible.warnings})
        self.assertIn("execution.required", {issue.code for issue in strict.issues})

    def test_future_schema_is_rejected_but_document_is_read_only(self) -> None:
        text = VALID.read_text(encoding="utf-8").replace(
            "easy-dev-spec/v1", "easy-dev-spec/v2", 1
        )
        report = validate_spec(text)
        self.assertFalse(report.ok)
        self.assertIn("schema.unsupported", {issue.code for issue in report.issues})


class CanonicalProtocolRegressionTest(unittest.TestCase):
    def test_synced_protocol_records_upstream_provenance(self) -> None:
        self.assertEqual("8239a5befae08b41da43b7cfbf41acf07e487d04", UPSTREAM_PROTOCOL_COMMIT)
        self.assertEqual(
            "a6016f04b4ce18794038ebcdbcab6e400a8a08aa2929a3e777c2b35ee3f7e7a1",
            UPSTREAM_PROTOCOL_SHA256,
        )
        self.assertEqual(
            "17f03314adce341269e2689aa41bb7bb29c236979be530a373fef58fe88a2524",
            UPSTREAM_SOURCE_SHA256["scripts/dev_spec_execution.py"],
        )
        self.assertEqual(
            "18b74fbca1a86a5db223580753a7ed06b219200b8a630ddca817ffb275cb3024",
            UPSTREAM_SOURCE_SHA256["scripts/update_dev_spec_execution.py"],
        )

    def test_duplicate_manifest_is_rejected(self) -> None:
        text = VALID.read_text(encoding="utf-8")
        duplicated = text + "\n" + text[
            text.index(MANIFEST_BEGIN) : text.index(MANIFEST_END) + len(MANIFEST_END)
        ]
        report = validate_spec(duplicated)
        self.assertFalse(report.ok)
        self.assertEqual("canonical-invalid", report.protocol)

    def test_duplicate_object_id_is_rejected(self) -> None:
        text = VALID.read_text(encoding="utf-8")
        manifest = copy.deepcopy(parse_manifest(text))
        manifest["changes"].append(copy.deepcopy(manifest["changes"][0]))
        report = validate_model(manifest, parse_sections(text), text=text)
        self.assertIn("id.duplicate", {issue.code for issue in report.issues})

    def test_unknown_dependency_reports_owning_task(self) -> None:
        text = VALID.read_text(encoding="utf-8")
        manifest = copy.deepcopy(parse_manifest(text))
        manifest["tasks"][0]["depends_on"] = [
            {"task_id": "R9-T9", "type": "hard", "required_evidence": "test passes"}
        ]
        report = validate_model(manifest, parse_sections(text), text=text)
        issue = next(issue for issue in report.issues if issue.code == "reference.missing")
        self.assertEqual("R1-T1", issue.item_id)

    def test_cross_repository_change_is_rejected(self) -> None:
        text = VALID.read_text(encoding="utf-8")
        manifest = copy.deepcopy(parse_manifest(text))
        manifest["changes"][0]["repo_id"] = "R2"
        report = validate_model(manifest, parse_sections(text), text=text)
        self.assertIn("change.repo_mismatch", {issue.code for issue in report.issues})

    def test_empty_symbols_are_rejected(self) -> None:
        text = VALID.read_text(encoding="utf-8")
        manifest = copy.deepcopy(parse_manifest(text))
        manifest["changes"][0]["symbols"] = []
        report = validate_model(manifest, parse_sections(text), text=text)
        self.assertIn("field.nonempty", {issue.code for issue in report.issues})

    def test_nested_sections_are_rejected(self) -> None:
        with self.assertRaises(CanonicalSpecError):
            parse_sections(
                "<!-- EDS:SECTION:BEGIN id=one -->\n"
                "<!-- EDS:SECTION:BEGIN id=two -->\n"
                "<!-- EDS:SECTION:END id=two -->\n"
                "<!-- EDS:SECTION:END id=one -->"
            )

    def test_task_cycle_is_rejected(self) -> None:
        text = VALID.read_text(encoding="utf-8")
        manifest = copy.deepcopy(parse_manifest(text))
        manifest["tasks"][0]["depends_on"] = [
            {"task_id": "R1-T2", "type": "hard", "required_evidence": "test passes"}
        ]
        report = validate_model(manifest, parse_sections(text), text=text)
        self.assertIn("dependency.cycle", {issue.code for issue in report.issues})

    def test_reverse_traceability_is_rejected(self) -> None:
        text = VALID.read_text(encoding="utf-8")
        manifest = copy.deepcopy(parse_manifest(text))
        manifest["tasks"][0]["test_ids"] = ["T1", "T2"]
        report = validate_model(manifest, parse_sections(text), text=text)
        self.assertIn("traceability.reverse", {issue.code for issue in report.issues})

    def test_ready_forbidden_phrase_is_rejected(self) -> None:
        report = validate_spec(
            VALID.read_text(encoding="utf-8") + "\n在合适位置写入实现。\n",
            require_ready=True,
        )
        self.assertIn("vague.implementation", {issue.code for issue in report.issues})

    def test_long_single_line_legacy_document_is_supported(self) -> None:
        report = validate_spec("#" * 300)
        self.assertTrue(report.ok)
        self.assertEqual("legacy", report.protocol)

    def test_malformed_ready_lists_report_issues_without_crashing(self) -> None:
        text = VALID.read_text(encoding="utf-8")
        manifest = copy.deepcopy(parse_manifest(text))
        manifest["repositories"][0]["baseline"] = "main"
        manifest["repositories"][0]["remote_urls"] = None
        manifest["contracts"][0]["consumer_task_ids"] = None
        manifest["changes"][0]["symbols"] = None
        manifest["steps"][0]["change_ids"] = None
        report = validate_model(manifest, parse_sections(text), text=text, require_ready=True)
        self.assertFalse(report.ok)
        self.assertIn("field.list", {issue.code for issue in report.issues})

    def test_scope_contains_selected_task_and_dependency_summaries_only(self) -> None:
        selected = select_scope(VALID, "R1", ["R1-T2"], output_format="markdown")
        self.assertIn("task-r1-t2", selected)
        self.assertNotIn("task-r1-t1 -->", selected)
        self.assertNotIn("task-r2-t1 -->", selected)
        self.assertIn("直接依赖任务摘要", selected)
        self.assertIn("R1-T1", selected)
        self.assertIn("R2-T1", selected)
        self.assertNotIn("OrderEventConsumer.java", selected)

    def test_scope_json_is_deterministic_and_repo_bound(self) -> None:
        first = select_scope(VALID, "R2", ["R2-T1"], output_format="json")
        second = select_scope(VALID, "R2", ["R2-T1"], output_format="json")
        self.assertEqual(first, second)
        self.assertEqual(["R2-T1"], first["selected_task_ids"])
        with self.assertRaises(CanonicalSpecError):
            select_scope(VALID, "R1", ["R2-T1"])

    def test_invalid_relative_and_nonportable_paths_are_rejected(self) -> None:
        text = VALID.read_text(encoding="utf-8")
        sections = parse_sections(text)
        for invalid_path in (
            "../outside.java",
            "C:/repo/Foo.java",
            "https://example.com/Foo.java",
            " src/Foo.java",
            "src/Foo.java\nother",
            "src//Foo.java",
        ):
            with self.subTest(path=invalid_path):
                manifest = copy.deepcopy(parse_manifest(text))
                manifest["changes"][0]["path"] = invalid_path
                report = validate_model(manifest, sections, text=text)
                self.assertIn("path.invalid", {issue.code for issue in report.issues})

    def test_manifest_must_be_strict_json(self) -> None:
        text = VALID.read_text(encoding="utf-8").replace(
            '"schema": "easy-dev-spec/v1",',
            '"schema": "easy-dev-spec/v1", // comment',
            1,
        )
        report = validate_spec(text)
        self.assertFalse(report.ok)
        self.assertEqual("manifest.parse", report.issues[0].code)

    def test_manifest_must_precede_sections(self) -> None:
        text = VALID.read_text(encoding="utf-8")
        start = text.index(MANIFEST_BEGIN)
        end = text.index(MANIFEST_END) + len(MANIFEST_END)
        moved = text[:start] + text[end:] + "\n" + text[start:end] + "\n"
        report = validate_spec(moved)
        self.assertIn("manifest.position", {issue.code for issue in report.issues})

    def test_open_decision_blocks_ready(self) -> None:
        text = VALID.read_text(encoding="utf-8").rstrip() + "\n待用户决策：选择 A 或 B"
        report = validate_spec(text, require_ready=True)
        self.assertIn("ready.open_decision", {issue.code for issue in report.issues})

    def test_explicit_no_open_decision_remains_ready(self) -> None:
        text = VALID.read_text(encoding="utf-8") + "\n当前不存在开放决策。\n"
        report = validate_spec(text, require_ready=True)
        self.assertNotIn("ready.open_decision", {issue.code for issue in report.issues})

    def test_initialization_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.md"
            spec.write_text(VALID.read_text(encoding="utf-8"), encoding="utf-8")
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            first = initialize_execution(spec, expected_design_sha256=digest)
            second = initialize_execution(spec, expected_design_sha256=digest)
            self.assertEqual(first, second)
            self.assertEqual([], second["events"])

    def test_show_requires_initialized_execution(self) -> None:
        with self.assertRaises(ExecutionStateError):
            show_execution(VALID)

    def test_non_ready_design_rejects_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = Path(directory) / "draft.md"
            spec.write_text(
                VALID.read_text(encoding="utf-8").replace(
                    '"status": "READY"', '"status": "DRAFT"'
                ),
                encoding="utf-8",
            )
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            with self.assertRaises(ExecutionStateError):
                record_task_status(
                    spec, "R1-T1", "in_progress", "DRAFT 不开发。", APP, AGENT, digest, 0
                )

    def test_event_rejects_reserved_execution_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.md"
            spec.write_text(VALID.read_text(encoding="utf-8"), encoding="utf-8")
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            with self.assertRaises(ExecutionStateError):
                record_task_status(
                    spec,
                    "R1-T1",
                    "in_progress",
                    "非法 <!-- EDS:EXECUTION:BEGIN -->",
                    APP,
                    AGENT,
                    digest,
                    0,
                )

    def test_task_cannot_borrow_another_tasks_test_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.md"
            spec.write_text(VALID.read_text(encoding="utf-8"), encoding="utf-8")
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            execution = record_task_status(
                spec, "R1-T1", "in_progress", "开始。", APP, AGENT, digest, 0
            )
            with self.assertRaises(ExecutionStateError):
                record_task_status(
                    spec,
                    "R1-T1",
                    "in_progress",
                    "借用 T2。",
                    APP,
                    AGENT,
                    digest,
                    execution["execution_revision"],
                    evidence=_passed("T2"),
                )

    def test_satisfied_dependency_requires_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.md"
            spec.write_text(VALID.read_text(encoding="utf-8"), encoding="utf-8")
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            with self.assertRaises(ExecutionStateError):
                record_dependency_status(
                    spec, "R1-T2", "R1-T1", "satisfied", "无证据。", APP, AGENT, digest, 0
                )

    def test_contract_dependency_cannot_be_manually_reopened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.md"
            spec.write_text(VALID.read_text(encoding="utf-8"), encoding="utf-8")
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            with self.assertRaises(ExecutionStateError):
                record_dependency_status(
                    spec,
                    "R2-T1",
                    "R1-T1",
                    "pending",
                    "READY 契约不可手工重开。",
                    APP,
                    AGENT,
                    digest,
                    0,
                )

    def test_writer_cli_init_show_and_conflict_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.md"
            spec.write_text(VALID.read_text(encoding="utf-8"), encoding="utf-8")
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialized = subprocess.run(
                [
                    "python3",
                    "-B",
                    str(WRITER_CLI),
                    "init",
                    str(spec),
                    "--expected-design-sha256",
                    digest,
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, initialized.returncode, initialized.stdout)
            shown = subprocess.run(
                ["python3", "-B", str(WRITER_CLI), "show", str(spec)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, shown.returncode, shown.stdout)
            self.assertTrue(json.loads(shown.stdout)["ok"])
            started = record_task_status(
                spec, "R1-T1", "in_progress", "开始。", APP, AGENT, digest, 0
            )
            self.assertEqual(1, started["execution_revision"])
            conflict = subprocess.run(
                [
                    "python3",
                    "-B",
                    str(WRITER_CLI),
                    "task",
                    str(spec),
                    "--task",
                    "R2-T1",
                    "--status",
                    "in_progress",
                    "--summary",
                    "过期写。",
                    "--expected-design-sha256",
                    digest,
                    "--expected-execution-revision",
                    "0",
                    "--app",
                    APP,
                    "--agent",
                    AGENT,
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(3, conflict.returncode)
            self.assertEqual("conflict", json.loads(conflict.stdout)["kind"])

    def test_writer_preserves_file_mode_and_removes_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = Path(directory) / "spec.md"
            spec.write_text(VALID.read_text(encoding="utf-8"), encoding="utf-8")
            spec.chmod(0o640)
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            self.assertEqual(0o640, spec.stat().st_mode & 0o777)
            self.assertFalse(spec.with_name(f".{spec.name}.eds.lock").exists())

    def test_with_claude_packets_use_new_digest_branches(self) -> None:
        root = Path(__file__).parents[1]
        template = (root / "templates" / "CLAUDE_TASK_PACKET.md").read_text(
            encoding="utf-8"
        )
        flow = (root / "flow" / "with-claude.md").read_text(encoding="utf-8")
        scenarios = (
            root / "references" / "scenarios" / "easy-coding-with-claude.md"
        ).read_text(encoding="utf-8")
        for field in (
            '"design_digest"',
            '"design_scope_digest"',
            '"execution_revision"',
            '"execution_scope_digest"',
        ):
            self.assertIn(field, template)
        self.assertNotIn('"scope_digest"', template)
        self.assertIn("只有 `execution_revision / execution_scope_sha256` 变化", flow)
        self.assertIn("设计或设计范围摘要变化", flow)
        self.assertIn("Canonical 仅执行态变化", scenarios)
        self.assertIn("继续使用当前只读结果", scenarios)
        self.assertIn("Canonical 设计变化", scenarios)
        self.assertIn("丢弃旧 worker 结果并返回 `[阶段：ANALYSIS]`", scenarios)


if __name__ == "__main__":
    unittest.main()
