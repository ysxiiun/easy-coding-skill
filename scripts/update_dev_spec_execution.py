#!/usr/bin/env python3
"""Safely initialize, read, and update Canonical Spec execution state."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from dev_spec_execution import (
    ExecutionConflictError,
    ExecutionStateError,
    initialize_execution,
    record_dependency_status,
    record_step_status,
    record_task_status,
    show_execution,
    sync_design,
)


def _evidence(values: list[str]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for value in values:
        try:
            item = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ExecutionStateError(f"--evidence 不是合法 JSON：{exc.msg}") from exc
        if not isinstance(item, dict):
            raise ExecutionStateError("--evidence 必须是 JSON object")
        parsed.append(item)
    return parsed


def _add_write_contract(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-design-sha256", required=True)
    parser.add_argument("--expected-execution-revision", required=True, type=int)
    parser.add_argument("--app", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--idempotency-key")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="读写 Canonical Dev Spec 的共享执行状态")
    subcommands = parser.add_subparsers(dest="command", required=True)

    show = subcommands.add_parser("show", help="读取并校验当前执行状态")
    show.add_argument("spec")

    initialize = subcommands.add_parser("init", help="为现有 Canonical v1 初始化执行区域")
    initialize.add_argument("spec")
    initialize.add_argument("--expected-design-sha256")

    task = subcommands.add_parser("task", help="记录任务级状态")
    task.add_argument("spec")
    task.add_argument("--task", required=True)
    task.add_argument(
        "--status",
        required=True,
        choices=(
            "in_progress",
            "blocked",
            "implemented",
            "verified",
            "completed",
            "cancelled",
        ),
    )
    task.add_argument("--summary", required=True)
    task.add_argument("--evidence", action="append", default=[])
    _add_write_contract(task)

    step = subcommands.add_parser("step", help="记录 Step 执行结果")
    step.add_argument("spec")
    step.add_argument("--task", required=True)
    step.add_argument("--step", required=True)
    step.add_argument("--status", required=True, choices=("completed", "failed"))
    step.add_argument("--summary", required=True)
    step.add_argument("--evidence", action="append", default=[])
    _add_write_contract(step)

    dependency = subcommands.add_parser("dependency", help="记录依赖边完成证据")
    dependency.add_argument("spec")
    dependency.add_argument("--source-task", required=True)
    dependency.add_argument("--dependency-task", required=True)
    dependency.add_argument("--status", required=True, choices=("pending", "satisfied"))
    dependency.add_argument("--summary", required=True)
    dependency.add_argument("--evidence", action="append", default=[])
    _add_write_contract(dependency)

    synchronize = subcommands.add_parser(
        "sync-design", help="静态设计 revision 递增后重算指纹并重置受影响任务"
    )
    synchronize.add_argument("spec")
    synchronize.add_argument("--affected-task", action="append", default=[])
    synchronize.add_argument("--summary", required=True)
    _add_write_contract(synchronize)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "show":
            result = show_execution(args.spec)
        elif args.command == "init":
            result = initialize_execution(
                args.spec,
                expected_design_sha256=args.expected_design_sha256,
            )
        elif args.command == "task":
            result = record_task_status(
                args.spec,
                args.task,
                args.status,
                args.summary,
                args.app,
                args.agent,
                args.expected_design_sha256,
                args.expected_execution_revision,
                evidence=_evidence(args.evidence),
                run_id=args.run_id,
                idempotency_key=args.idempotency_key,
            )
        elif args.command == "step":
            result = record_step_status(
                args.spec,
                args.task,
                args.step,
                args.status,
                args.summary,
                args.app,
                args.agent,
                args.expected_design_sha256,
                args.expected_execution_revision,
                evidence=_evidence(args.evidence),
                run_id=args.run_id,
                idempotency_key=args.idempotency_key,
            )
        elif args.command == "dependency":
            result = record_dependency_status(
                args.spec,
                args.source_task,
                args.dependency_task,
                args.status,
                args.summary,
                args.app,
                args.agent,
                args.expected_design_sha256,
                args.expected_execution_revision,
                evidence=_evidence(args.evidence),
                run_id=args.run_id,
                idempotency_key=args.idempotency_key,
            )
        else:
            result = sync_design(
                args.spec,
                args.affected_task,
                args.summary,
                args.app,
                args.agent,
                args.expected_design_sha256,
                args.expected_execution_revision,
                run_id=args.run_id,
                idempotency_key=args.idempotency_key,
            )
    except ExecutionConflictError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "kind": "conflict"}, ensure_ascii=False))
        return 3
    except (ExecutionStateError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "kind": "invalid"}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
