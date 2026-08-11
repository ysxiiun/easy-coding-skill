#!/usr/bin/env python3
"""Shared execution-state writer for a single Canonical Dev Spec.

The design portion of a Spec remains human-editable. This module owns only the
strict JSON execution block at the end of the same Markdown file and applies
optimistic concurrency plus a short-lived adjacent lock while rewriting it.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

try:
    from easy_dev_spec_protocol import (
        EXECUTION_BEGIN,
        EXECUTION_END,
        EXECUTION_SCHEMA,
        CanonicalSpecError,
        design_sha256,
        parse_manifest,
        parse_sections,
        split_execution_region,
        validate_model,
        validate_spec,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path in tests
    from scripts.easy_dev_spec_protocol import (
        EXECUTION_BEGIN,
        EXECUTION_END,
        EXECUTION_SCHEMA,
        CanonicalSpecError,
        design_sha256,
        parse_manifest,
        parse_sections,
        split_execution_region,
        validate_model,
        validate_spec,
    )


class ExecutionStateError(ValueError):
    """The execution ledger cannot be safely read or changed."""


class ExecutionConflictError(ExecutionStateError):
    """The caller's expected design or execution revision is stale."""


TASK_TRANSITIONS = {
    "not_started": {"in_progress", "cancelled"},
    "in_progress": {"in_progress", "blocked", "implemented", "cancelled"},
    "blocked": {"blocked", "in_progress", "cancelled"},
    "implemented": {"in_progress", "blocked", "verified"},
    "verified": {"in_progress", "blocked", "completed"},
    "completed": {"in_progress"},
    "cancelled": {"in_progress"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_id() -> str:
    return f"EV-{uuid.uuid4()}"


def _manifest_tasks(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(task["task_id"]): task
        for task in manifest.get("tasks", [])
        if isinstance(task, dict) and isinstance(task.get("task_id"), str)
    }


def _new_snapshot(task: dict[str, Any], design_ready: bool) -> dict[str, Any]:
    dependencies = []
    for dependency in task.get("depends_on", []):
        dependency_type = str(dependency["type"])
        dependencies.append(
            {
                "task_id": str(dependency["task_id"]),
                "type": dependency_type,
                "status": (
                    "satisfied"
                    if dependency_type == "contract" and design_ready
                    else "pending"
                ),
                "evidence_event_id": None,
            }
        )
    return {
        "task_id": str(task["task_id"]),
        "status": "not_started",
        "completed_step_ids": [],
        "failed_step_ids": [],
        "dependencies": dependencies,
        "blockers": [],
        "evidence": [],
        "last_event_id": None,
        "updated_at": None,
    }


def build_initial_execution(manifest: dict[str, Any], current_design_sha256: str) -> dict[str, Any]:
    """Create the revision-zero execution ledger for a validated design."""

    return {
        "schema": EXECUTION_SCHEMA,
        "spec_id": manifest["spec_id"],
        "design_revision": manifest["revision"],
        "design_sha256": current_design_sha256,
        "execution_revision": 0,
        "updated_at": None,
        "tasks": [
            _new_snapshot(task, manifest.get("status") == "READY")
            for task in manifest["tasks"]
        ],
        "events": [],
    }


def render_execution_block(execution: dict[str, Any]) -> str:
    payload = json.dumps(execution, ensure_ascii=False, indent=2)
    if EXECUTION_BEGIN in payload or EXECUTION_END in payload:
        raise ExecutionStateError("execution 数据不得包含保留的 EDS execution 边界标记")
    return f"{EXECUTION_BEGIN}\n```json\n{payload}\n```\n{EXECUTION_END}"


def render_document(design_text: str, execution: dict[str, Any]) -> str:
    return design_text.rstrip() + "\n\n" + render_execution_block(execution) + "\n"


def _load(path: Path) -> tuple[str, str, dict[str, Any], dict[str, Any] | None]:
    if not path.is_file():
        raise ExecutionStateError(f"Spec 文件不存在：{path}")
    try:
        text = path.read_text(encoding="utf-8")
        design_text, execution = split_execution_region(text)
        manifest = parse_manifest(design_text)
    except (OSError, UnicodeError, CanonicalSpecError) as exc:
        raise ExecutionStateError(str(exc)) from exc
    if manifest is None:
        raise ExecutionStateError("legacy Dev Spec 不支持共享执行状态")
    return text, design_text, manifest, execution


def _validate_static_design(design_text: str, manifest: dict[str, Any]) -> None:
    try:
        sections = parse_sections(design_text)
    except CanonicalSpecError as exc:
        raise ExecutionStateError(str(exc)) from exc
    report = validate_model(
        manifest,
        sections,
        text=design_text,
        require_ready=manifest.get("status") == "READY",
    )
    if not report.ok:
        details = "；".join(issue.message for issue in report.issues[:8])
        raise ExecutionStateError(f"静态设计校验失败：{details}")


def _assert_expected(
    execution: dict[str, Any],
    expected_design_sha256: str,
    expected_execution_revision: int,
) -> None:
    if not isinstance(expected_design_sha256, str) or not expected_design_sha256.strip():
        raise ExecutionStateError("expected_design_sha256 必须是非空字符串")
    if not isinstance(expected_execution_revision, int) or isinstance(
        expected_execution_revision, bool
    ):
        raise ExecutionStateError("expected_execution_revision 必须是整数")
    if execution.get("design_sha256") != expected_design_sha256:
        raise ExecutionConflictError("设计指纹已变化，请重新读取 Spec 后再写入")
    if execution.get("execution_revision") != expected_execution_revision:
        raise ExecutionConflictError("执行修订号已变化，请重新读取 Spec 后重放本次更新")


def _assert_current_design(design_text: str, execution: dict[str, Any]) -> None:
    if execution.get("design_sha256") != design_sha256(design_text):
        raise ExecutionConflictError("静态设计已经编辑但尚未 sync-design，不能继续写入进度")


def _validate_existing_execution(path: Path) -> None:
    report = validate_spec(path, require_execution=True)
    if not report.ok:
        details = "；".join(issue.message for issue in report.issues[:8])
        raise ExecutionStateError(f"现有执行状态非法：{details}")


def _validate_execution_envelope(manifest: dict[str, Any], execution: dict[str, Any]) -> None:
    events = execution.get("events")
    tasks = execution.get("tasks")
    execution_revision = execution.get("execution_revision")
    design_revision = execution.get("design_revision")
    if execution.get("schema") != EXECUTION_SCHEMA:
        raise ExecutionStateError("现有 execution.schema 非法")
    if execution.get("spec_id") != manifest.get("spec_id"):
        raise ExecutionStateError("现有 execution.spec_id 与静态设计不一致")
    if not isinstance(events, list) or not isinstance(tasks, list):
        raise ExecutionStateError("现有 execution.events/tasks 必须是数组")
    if (
        not isinstance(execution_revision, int)
        or isinstance(execution_revision, bool)
        or execution_revision != len(events)
    ):
        raise ExecutionStateError("现有 execution_revision 与事件数量不一致")
    if not isinstance(design_revision, int) or isinstance(design_revision, bool):
        raise ExecutionStateError("现有 execution.design_revision 非法")
    if not isinstance(execution.get("design_sha256"), str):
        raise ExecutionStateError("现有 execution.design_sha256 非法")


def _normalize_evidence(evidence: Iterable[dict[str, Any]] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for index, value in enumerate(evidence or []):
        if not isinstance(value, dict):
            raise ExecutionStateError(f"evidence[{index}] 必须是 object")
        kind = value.get("kind")
        status_value = value.get("status")
        reference = value.get("ref")
        if not isinstance(kind, str) or not kind.strip():
            raise ExecutionStateError(f"evidence[{index}].kind 必须是非空字符串")
        if status_value not in {"passed", "failed", "recorded"}:
            raise ExecutionStateError(
                f"evidence[{index}].status 必须是 passed、failed 或 recorded"
            )
        if not isinstance(reference, str) or not reference.strip():
            raise ExecutionStateError(f"evidence[{index}].ref 必须是非空字符串")
        item = {"kind": kind.strip(), "status": str(status_value), "ref": reference.strip()}
        for optional_field in ("test_id", "sha256"):
            optional_value = value.get(optional_field)
            if optional_value is not None:
                if not isinstance(optional_value, str) or not optional_value.strip():
                    raise ExecutionStateError(
                        f"evidence[{index}].{optional_field} 必须是非空字符串"
                    )
                item[optional_field] = optional_value.strip()
        if item["kind"] == "test" and "test_id" not in item:
            raise ExecutionStateError(f"evidence[{index}] 的 test 证据必须声明 test_id")
        normalized.append(item)
    return normalized


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionStateError(f"{label} 必须是非空字符串")
    return value.strip()


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, label)


def _passed_test_ids(evidence: Iterable[dict[str, Any]]) -> set[str]:
    return {
        str(value["test_id"])
        for value in evidence
        if isinstance(value, dict)
        and value.get("kind") == "test"
        and value.get("status") == "passed"
        and isinstance(value.get("test_id"), str)
    }


def _new_event(
    event_type: str,
    app: str,
    agent: str,
    summary: str,
    evidence: Iterable[dict[str, Any]] | None,
    *,
    task_id: str | None = None,
    task_ids: list[str] | None = None,
    run_id: str | None = None,
    idempotency_key: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    for label, value in (("app", app), ("agent", agent), ("summary", summary)):
        if not isinstance(value, str) or not value.strip():
            raise ExecutionStateError(f"{label} 必须是非空字符串")
    event: dict[str, Any] = {
        "event_id": _event_id(),
        "type": event_type,
        "timestamp": _now_iso(),
        "app": app.strip(),
        "agent": agent.strip(),
        "summary": summary.strip(),
        "evidence": _normalize_evidence(evidence),
    }
    if task_id is not None:
        event["task_id"] = task_id
    if task_ids is not None:
        event["task_ids"] = task_ids
    if run_id:
        event["run_id"] = run_id
    if idempotency_key:
        event["idempotency_key"] = idempotency_key
    event.update(fields)
    return event


def _existing_idempotent_event(
    execution: dict[str, Any], idempotency_key: str | None
) -> dict[str, Any] | None:
    if not idempotency_key:
        return None
    return next(
        (
            event
            for event in execution.get("events", [])
            if isinstance(event, dict) and event.get("idempotency_key") == idempotency_key
        ),
        None,
    )


def _idempotent_result(
    execution: dict[str, Any],
    idempotency_key: str | None,
    expected_fields: dict[str, Any],
) -> dict[str, Any] | None:
    """Return an existing equivalent event, rejecting key reuse for another action."""

    existing = _existing_idempotent_event(execution, idempotency_key)
    if existing is None:
        return None
    mismatched = [
        field_name
        for field_name, expected_value in expected_fields.items()
        if existing.get(field_name) != expected_value
    ]
    if mismatched:
        raise ExecutionConflictError(
            "幂等键已被不同事件使用，冲突字段：" + ", ".join(sorted(mismatched))
        )
    return execution


def _snapshot_by_id(execution: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(snapshot["task_id"]): snapshot
        for snapshot in execution.get("tasks", [])
        if isinstance(snapshot, dict) and isinstance(snapshot.get("task_id"), str)
    }


def _require_ready_task(manifest: dict[str, Any], task_id: str) -> dict[str, Any]:
    task = _manifest_tasks(manifest).get(task_id)
    if task is None:
        raise ExecutionStateError(f"执行任务不存在：{task_id}")
    if manifest.get("status") != "READY" or task.get("status") != "READY":
        raise ExecutionStateError(
            f"Canonical Spec 和任务 {task_id} 必须是 READY 才能写入开发执行状态"
        )
    return task


def _dependency_is_satisfied(
    manifest: dict[str, Any],
    execution: dict[str, Any],
    dependency: dict[str, Any],
) -> bool:
    dependency_type = dependency.get("type")
    if dependency_type == "contract":
        return manifest.get("status") == "READY"
    if dependency.get("status") == "satisfied":
        return True
    if dependency_type == "hard":
        dependency_task = _snapshot_by_id(execution).get(str(dependency.get("task_id")))
        return dependency_task is not None and dependency_task.get("status") == "completed"
    return False


def _unsatisfied_dependencies(
    manifest: dict[str, Any],
    execution: dict[str, Any],
    snapshot: dict[str, Any],
    dependency_types: set[str],
) -> list[dict[str, Any]]:
    return [
        dependency
        for dependency in snapshot.get("dependencies", [])
        if isinstance(dependency, dict)
        and dependency.get("type") in dependency_types
        and not _dependency_is_satisfied(manifest, execution, dependency)
    ]


def _attach_event_evidence(snapshot: dict[str, Any], event: dict[str, Any]) -> None:
    for evidence in event.get("evidence", []):
        snapshot["evidence"].append({**evidence, "event_id": event["event_id"]})


def _finalize_event(execution: dict[str, Any], event: dict[str, Any]) -> None:
    execution["events"].append(event)
    execution["execution_revision"] = int(execution["execution_revision"]) + 1
    execution["updated_at"] = event["timestamp"]


@contextmanager
def _exclusive_lock(path: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    lock_path = path.with_name(f".{path.name}.eds.lock")
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(descriptor, f"pid={os.getpid()} created={_now_iso()}\n".encode("utf-8"))
        except FileExistsError:
            try:
                stale = time.time() - lock_path.stat().st_mtime > 300
            except FileNotFoundError:
                continue
            if stale:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise ExecutionConflictError("Spec 正由其他应用写入，请稍后重新读取并重试")
            time.sleep(0.05)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _write_atomic(path: Path, content: str) -> None:
    file_mode = stat.S_IMODE(path.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.eds-", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, file_mode)
        os.replace(temporary_path, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _persist(path: Path, design_text: str, execution: dict[str, Any]) -> dict[str, Any]:
    content = render_document(design_text, execution)
    report = validate_spec(content, require_execution=True)
    if not report.ok:
        details = "；".join(issue.message for issue in report.issues[:8])
        raise ExecutionStateError(f"写入前执行状态校验失败：{details}")
    _write_atomic(path, content)
    return execution


def initialize_execution(
    spec_path: str | Path,
    *,
    expected_design_sha256: str | None = None,
) -> dict[str, Any]:
    path = Path(spec_path).expanduser().resolve()
    with _exclusive_lock(path):
        _, design_text, manifest, execution = _load(path)
        _validate_static_design(design_text, manifest)
        current_design_sha256 = design_sha256(design_text)
        if expected_design_sha256 and expected_design_sha256 != current_design_sha256:
            raise ExecutionConflictError("设计指纹与调用方预期不一致")
        if execution is not None:
            report = validate_spec(path, require_execution=True)
            if not report.ok:
                details = "；".join(issue.message for issue in report.issues[:8])
                raise ExecutionStateError(f"现有执行状态非法：{details}")
            return execution
        execution = build_initial_execution(manifest, current_design_sha256)
        return _persist(path, design_text, execution)


def record_task_status(
    spec_path: str | Path,
    task_id: str,
    status_value: str,
    summary: str,
    app: str,
    agent: str,
    expected_design_sha256: str,
    expected_execution_revision: int,
    *,
    evidence: Iterable[dict[str, Any]] | None = None,
    run_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    task_id = _required_text(task_id, "task_id")
    status_value = _required_text(status_value, "status")
    summary = _required_text(summary, "summary")
    app = _required_text(app, "app")
    agent = _required_text(agent, "agent")
    run_id = _optional_text(run_id, "run_id")
    idempotency_key = _optional_text(idempotency_key, "idempotency_key")
    path = Path(spec_path).expanduser().resolve()
    with _exclusive_lock(path):
        _, design_text, manifest, execution = _load(path)
        if execution is None:
            raise ExecutionStateError("Spec 尚未初始化共享执行状态")
        _assert_current_design(design_text, execution)
        _validate_existing_execution(path)
        normalized_evidence = _normalize_evidence(evidence)
        existing = _idempotent_result(
            execution,
            idempotency_key,
            {
                "type": "task_status_changed",
                "task_id": task_id,
                "to_status": status_value,
                "app": app,
                "agent": agent,
                "summary": summary,
                "evidence": normalized_evidence,
                "run_id": run_id,
                "design_revision": manifest.get("revision"),
            },
        )
        if existing is not None:
            return existing
        _assert_expected(execution, expected_design_sha256, expected_execution_revision)
        manifest_task = _require_ready_task(manifest, task_id)
        snapshots = _snapshot_by_id(execution)
        snapshot = snapshots.get(task_id)
        if snapshot is None:  # execution validation normally catches this first
            raise ExecutionStateError(f"执行任务快照不存在：{task_id}")
        current_status = str(snapshot.get("status"))
        if status_value not in TASK_TRANSITIONS.get(current_status, set()):
            raise ExecutionStateError(f"非法任务状态迁移：{current_status} -> {status_value}")
        if status_value in {"in_progress", "implemented", "verified", "completed"}:
            missing_dependencies = _unsatisfied_dependencies(
                manifest,
                execution,
                snapshot,
                {"hard", "contract"},
            )
            if missing_dependencies:
                labels = [
                    f"{dependency.get('type')}:{dependency.get('task_id')}"
                    for dependency in missing_dependencies
                ]
                raise ExecutionStateError(
                    f"任务 {task_id} 的前置依赖未满足：{', '.join(labels)}"
                )
        expected_steps = set(str(value) for value in manifest_task.get("step_ids", []))
        completed_steps = set(str(value) for value in snapshot.get("completed_step_ids", []))
        if status_value in {"implemented", "verified", "completed"} and completed_steps != expected_steps:
            missing = sorted(expected_steps - completed_steps)
            raise ExecutionStateError(
                f"任务 {task_id} 尚有未完成 Step，不能进入 {status_value}：{', '.join(missing)}"
            )
        cumulative_evidence = [*snapshot.get("evidence", []), *normalized_evidence]
        if status_value == "verified":
            expected_test_ids = set(str(value) for value in manifest_task.get("test_ids", []))
            missing_test_ids = expected_test_ids - _passed_test_ids(cumulative_evidence)
            if missing_test_ids:
                raise ExecutionStateError(
                    "进入 verified 前缺少通过的 Canonical Test 证据："
                    + ", ".join(sorted(missing_test_ids))
                )
        if status_value == "completed" and _unsatisfied_dependencies(
            manifest,
            execution,
            snapshot,
            {"integration"},
        ):
            raise ExecutionStateError("integration 依赖尚未满足，任务不能标记 completed")
        event = _new_event(
            "task_status_changed",
            app,
            agent,
            summary,
            normalized_evidence,
            task_id=task_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            from_status=current_status,
            to_status=status_value,
            design_revision=manifest["revision"],
        )
        snapshot["status"] = status_value
        snapshot["last_event_id"] = event["event_id"]
        snapshot["updated_at"] = event["timestamp"]
        if status_value == "blocked":
            if summary not in snapshot["blockers"]:
                snapshot["blockers"].append(summary)
        elif status_value == "in_progress":
            snapshot["blockers"] = []
            if current_status in {"completed", "cancelled"}:
                snapshot["evidence"] = []
        elif status_value == "cancelled":
            snapshot["blockers"] = []
        _attach_event_evidence(snapshot, event)
        _finalize_event(execution, event)
        return _persist(path, design_text, execution)


def record_step_status(
    spec_path: str | Path,
    task_id: str,
    step_id: str,
    status_value: str,
    summary: str,
    app: str,
    agent: str,
    expected_design_sha256: str,
    expected_execution_revision: int,
    *,
    evidence: Iterable[dict[str, Any]] | None = None,
    run_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    task_id = _required_text(task_id, "task_id")
    step_id = _required_text(step_id, "step_id")
    status_value = _required_text(status_value, "status")
    summary = _required_text(summary, "summary")
    app = _required_text(app, "app")
    agent = _required_text(agent, "agent")
    run_id = _optional_text(run_id, "run_id")
    idempotency_key = _optional_text(idempotency_key, "idempotency_key")
    if status_value not in {"completed", "failed"}:
        raise ExecutionStateError("Step 状态必须是 completed 或 failed")
    path = Path(spec_path).expanduser().resolve()
    with _exclusive_lock(path):
        _, design_text, manifest, execution = _load(path)
        if execution is None:
            raise ExecutionStateError("Spec 尚未初始化共享执行状态")
        _assert_current_design(design_text, execution)
        _validate_existing_execution(path)
        normalized_evidence = _normalize_evidence(evidence)
        existing = _idempotent_result(
            execution,
            idempotency_key,
            {
                "type": "step_status_changed",
                "task_id": task_id,
                "step_id": step_id,
                "step_status": status_value,
                "app": app,
                "agent": agent,
                "summary": summary,
                "evidence": normalized_evidence,
                "run_id": run_id,
                "design_revision": manifest.get("revision"),
            },
        )
        if existing is not None:
            return existing
        _assert_expected(execution, expected_design_sha256, expected_execution_revision)
        task = _require_ready_task(manifest, task_id)
        if step_id not in task.get("step_ids", []):
            raise ExecutionStateError(f"Step 不属于任务 {task_id}：{step_id}")
        snapshot = _snapshot_by_id(execution)[task_id]
        if snapshot.get("status") != "in_progress":
            raise ExecutionStateError("只有 in_progress 任务可以更新 Step；请先显式恢复任务")
        missing_dependencies = _unsatisfied_dependencies(
            manifest,
            execution,
            snapshot,
            {"hard", "contract"},
        )
        if missing_dependencies:
            labels = [
                f"{dependency.get('type')}:{dependency.get('task_id')}"
                for dependency in missing_dependencies
            ]
            raise ExecutionStateError(
                f"任务 {task_id} 的前置依赖未满足：{', '.join(labels)}"
            )
        step = next(
            (
                value
                for value in manifest.get("steps", [])
                if isinstance(value, dict) and value.get("step_id") == step_id
            ),
            None,
        )
        if step is None:
            raise ExecutionStateError(f"manifest 中缺少 Step 定义：{step_id}")
        missing_step_dependencies = set(
            str(value) for value in step.get("depends_on_step_ids", [])
        ) - set(str(value) for value in snapshot.get("completed_step_ids", []))
        if missing_step_dependencies:
            raise ExecutionStateError(
                f"Step {step_id} 的前置 Step 尚未完成："
                + ", ".join(sorted(missing_step_dependencies))
            )
        if status_value == "completed":
            expected_test_ids = set(str(value) for value in step.get("test_ids", []))
            missing_test_ids = expected_test_ids - _passed_test_ids(normalized_evidence)
            if missing_test_ids:
                raise ExecutionStateError(
                    f"Step {step_id} 缺少通过的绑定 Test 证据："
                    + ", ".join(sorted(missing_test_ids))
                )
        event = _new_event(
            "step_status_changed",
            app,
            agent,
            summary,
            normalized_evidence,
            task_id=task_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            step_id=step_id,
            step_status=status_value,
            design_revision=manifest["revision"],
        )
        completed = set(snapshot["completed_step_ids"])
        failed = set(snapshot["failed_step_ids"])
        if status_value == "completed":
            completed.add(step_id)
            failed.discard(step_id)
        else:
            failed.add(step_id)
            completed.discard(step_id)
            snapshot["status"] = "blocked"
            if summary not in snapshot["blockers"]:
                snapshot["blockers"].append(summary)
        snapshot["completed_step_ids"] = sorted(completed)
        snapshot["failed_step_ids"] = sorted(failed)
        snapshot["last_event_id"] = event["event_id"]
        snapshot["updated_at"] = event["timestamp"]
        _attach_event_evidence(snapshot, event)
        _finalize_event(execution, event)
        return _persist(path, design_text, execution)


def record_dependency_status(
    spec_path: str | Path,
    source_task_id: str,
    dependency_task_id: str,
    status_value: str,
    summary: str,
    app: str,
    agent: str,
    expected_design_sha256: str,
    expected_execution_revision: int,
    *,
    evidence: Iterable[dict[str, Any]] | None = None,
    run_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    source_task_id = _required_text(source_task_id, "source_task_id")
    dependency_task_id = _required_text(dependency_task_id, "dependency_task_id")
    status_value = _required_text(status_value, "status")
    summary = _required_text(summary, "summary")
    app = _required_text(app, "app")
    agent = _required_text(agent, "agent")
    run_id = _optional_text(run_id, "run_id")
    idempotency_key = _optional_text(idempotency_key, "idempotency_key")
    if status_value not in {"pending", "satisfied"}:
        raise ExecutionStateError("依赖状态必须是 pending 或 satisfied")
    normalized_evidence = _normalize_evidence(evidence)
    if status_value == "satisfied" and not normalized_evidence:
        raise ExecutionStateError("依赖置为 satisfied 时必须提供证据")
    path = Path(spec_path).expanduser().resolve()
    with _exclusive_lock(path):
        _, design_text, manifest, execution = _load(path)
        if execution is None:
            raise ExecutionStateError("Spec 尚未初始化共享执行状态")
        _assert_current_design(design_text, execution)
        _validate_existing_execution(path)
        existing = _idempotent_result(
            execution,
            idempotency_key,
            {
                "type": "dependency_status_changed",
                "task_id": source_task_id,
                "dependency_task_id": dependency_task_id,
                "dependency_status": status_value,
                "app": app,
                "agent": agent,
                "summary": summary,
                "evidence": normalized_evidence,
                "run_id": run_id,
                "design_revision": manifest.get("revision"),
            },
        )
        if existing is not None:
            return existing
        _assert_expected(execution, expected_design_sha256, expected_execution_revision)
        _require_ready_task(manifest, source_task_id)
        snapshot = _snapshot_by_id(execution).get(source_task_id)
        if snapshot is None:
            raise ExecutionStateError(f"执行任务不存在：{source_task_id}")
        matches = [
            dependency
            for dependency in snapshot.get("dependencies", [])
            if dependency.get("task_id") == dependency_task_id
        ]
        if len(matches) != 1:
            raise ExecutionStateError(
                f"未找到唯一依赖边：{source_task_id}->{dependency_task_id}"
            )
        dependency = matches[0]
        if dependency.get("type") == "contract" and status_value == "pending":
            raise ExecutionStateError("READY 设计中的 contract 依赖不能手工改为 pending")
        if status_value == "pending" and snapshot.get("status") == "completed":
            raise ExecutionStateError("completed 任务必须先重新进入 in_progress 才能重开依赖")
        if (
            status_value == "pending"
            and dependency.get("type") == "hard"
            and _snapshot_by_id(execution).get(dependency_task_id, {}).get("status")
            == "completed"
        ):
            raise ExecutionStateError("前置任务仍是 completed，hard 依赖不能改为 pending")
        event = _new_event(
            "dependency_status_changed",
            app,
            agent,
            summary,
            normalized_evidence,
            task_id=source_task_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            dependency_task_id=dependency_task_id,
            dependency_type=dependency["type"],
            dependency_status=status_value,
            design_revision=manifest["revision"],
        )
        dependency["status"] = status_value
        dependency["evidence_event_id"] = (
            event["event_id"] if status_value == "satisfied" else None
        )
        snapshot["last_event_id"] = event["event_id"]
        snapshot["updated_at"] = event["timestamp"]
        if status_value == "pending" and snapshot.get("status") in {
            "in_progress",
            "implemented",
            "verified",
        }:
            snapshot["status"] = "blocked"
            if summary not in snapshot["blockers"]:
                snapshot["blockers"].append(summary)
        _attach_event_evidence(snapshot, event)
        _finalize_event(execution, event)
        return _persist(path, design_text, execution)


def _affected_closure(manifest: dict[str, Any], affected_task_ids: set[str]) -> set[str]:
    tasks = _manifest_tasks(manifest)
    reverse_dependencies: dict[str, set[str]] = {task_id: set() for task_id in tasks}
    for task_id, task in tasks.items():
        for dependency in task.get("depends_on", []):
            dependency_id = str(dependency.get("task_id"))
            if dependency_id in reverse_dependencies:
                reverse_dependencies[dependency_id].add(task_id)
    closure = set(affected_task_ids)
    pending = list(affected_task_ids)
    while pending:
        task_id = pending.pop()
        for dependent in reverse_dependencies.get(task_id, set()):
            if dependent not in closure:
                closure.add(dependent)
                pending.append(dependent)
    return closure


def sync_design(
    spec_path: str | Path,
    affected_task_ids: Iterable[str],
    summary: str,
    app: str,
    agent: str,
    expected_design_sha256: str,
    expected_execution_revision: int,
    *,
    run_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Accept a validated static revision and reconcile its execution snapshots."""

    summary = _required_text(summary, "summary")
    app = _required_text(app, "app")
    agent = _required_text(agent, "agent")
    run_id = _optional_text(run_id, "run_id")
    idempotency_key = _optional_text(idempotency_key, "idempotency_key")
    path = Path(spec_path).expanduser().resolve()
    with _exclusive_lock(path):
        _, design_text, manifest, execution = _load(path)
        if execution is None:
            raise ExecutionStateError("Spec 尚未初始化共享执行状态")
        _validate_execution_envelope(manifest, execution)
        if execution.get("design_revision") == manifest.get("revision"):
            _assert_current_design(design_text, execution)
            _validate_existing_execution(path)
        requested_task_ids = sorted(
            {_required_text(task_id, "affected_task_id") for task_id in affected_task_ids}
        )
        existing = _idempotent_result(
            execution,
            idempotency_key,
            {
                "type": "spec_revised",
                "requested_task_ids": requested_task_ids,
                "app": app,
                "agent": agent,
                "summary": summary,
                "evidence": [],
                "run_id": run_id,
                "design_revision": manifest.get("revision"),
            },
        )
        if existing is not None:
            return existing
        _assert_expected(execution, expected_design_sha256, expected_execution_revision)
        _validate_static_design(design_text, manifest)
        old_revision = execution.get("design_revision")
        new_revision = manifest.get("revision")
        if not isinstance(old_revision, int) or new_revision != old_revision + 1:
            raise ExecutionStateError(
                "静态设计 revision 必须在每次 sync-design 时恰好递增 1"
            )
        tasks = _manifest_tasks(manifest)
        requested = set(requested_task_ids)
        if not requested:
            requested = set(tasks)
        unknown = sorted(requested - set(tasks))
        if unknown:
            raise ExecutionStateError("受影响任务不存在：" + ", ".join(unknown))
        reset_task_ids = _affected_closure(manifest, requested)
        old_snapshots = _snapshot_by_id(execution)
        reconciled: list[dict[str, Any]] = []
        for task_id, task in tasks.items():
            fresh = _new_snapshot(task, manifest.get("status") == "READY")
            previous = old_snapshots.get(task_id)
            if previous is not None and task_id not in reset_task_ids:
                fresh.update(
                    {
                        key: previous[key]
                        for key in (
                            "status",
                            "completed_step_ids",
                            "failed_step_ids",
                            "blockers",
                            "evidence",
                            "last_event_id",
                            "updated_at",
                        )
                        if key in previous
                    }
                )
                previous_dependencies = {
                    (value.get("task_id"), value.get("type")): value
                    for value in previous.get("dependencies", [])
                    if isinstance(value, dict)
                }
                for dependency in fresh["dependencies"]:
                    prior = previous_dependencies.get(
                        (dependency["task_id"], dependency["type"])
                    )
                    if prior:
                        dependency.update(
                            {
                                "status": prior.get("status", dependency["status"]),
                                "evidence_event_id": prior.get("evidence_event_id"),
                            }
                        )
            reconciled.append(fresh)
        event = _new_event(
            "spec_revised",
            app,
            agent,
            summary,
            [],
            task_ids=sorted(reset_task_ids),
            run_id=run_id,
            idempotency_key=idempotency_key,
            from_design_revision=old_revision,
            to_design_revision=new_revision,
            requested_task_ids=requested_task_ids,
            design_revision=new_revision,
        )
        for snapshot in reconciled:
            if snapshot["task_id"] in reset_task_ids:
                snapshot["last_event_id"] = event["event_id"]
                snapshot["updated_at"] = event["timestamp"]
        execution["tasks"] = reconciled
        execution["design_revision"] = new_revision
        execution["design_sha256"] = design_sha256(design_text)
        _finalize_event(execution, event)
        return _persist(path, design_text, execution)


def show_execution(spec_path: str | Path) -> dict[str, Any]:
    path = Path(spec_path).expanduser().resolve()
    report = validate_spec(path, require_execution=True)
    if not report.ok or report.manifest is None or report.execution is None:
        details = "；".join(issue.message for issue in report.issues[:8])
        raise ExecutionStateError(f"Spec 执行状态不可用：{details}")
    return {
        "protocol": report.protocol,
        "schema": report.manifest["schema"],
        "spec_id": report.manifest["spec_id"],
        "design_revision": report.manifest["revision"],
        "design_sha256": report.design_sha256,
        "document_sha256": report.document_sha256,
        "execution": report.execution,
    }
