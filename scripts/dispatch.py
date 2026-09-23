#!/usr/bin/env python3
"""Local, serial handoff receipts. No Harness runtime or project task files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

if __package__:
    from . import quality_fingerprint as quality
    from . import quality_checks
else:
    import quality_fingerprint as quality
    import quality_checks


SCHEMA = "easy-coding-dispatch/v1"
HEADER = "<!-- easy-coding-dispatch/v1 -->\n```json\n"
STAGES = {
    "IMPLEMENT": {"QUALITY", "ANALYSIS", "CLOSED"},
    "QUALITY": {"IMPLEMENT", "ANALYSIS", "MEMORY", "CLOSED"},
    "ANALYSIS": {"IMPLEMENT", "CLOSED"},
    "MEMORY": {"COMPLETE", "CLOSED"},
    "COMPLETE": set(), "CLOSED": set(),
}


class DispatchError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DispatchError(message)


def nonempty(value: object, label: str) -> None:
    require(isinstance(value, str) and bool(value.strip()), f"{label} must be non-empty")


def receipt(value: object, label: str) -> None:
    require(isinstance(value, dict), f"{label} requires quote and source")
    nonempty(value.get("quote"), f"{label}.quote")
    nonempty(value.get("source"), f"{label}.source")


def digest(value: object) -> str:
    return quality._canonical_sha256(value)


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_run_id(value: str) -> None:
    require(value.startswith("ec-skill-"), "run_id must be ec-skill-<UUIDv7>")
    try:
        parsed = uuid.UUID(value[9:])
    except ValueError as exc:
        raise DispatchError("run_id must be ec-skill-<UUIDv7>") from exc
    require(parsed.version == 7 and str(parsed) == value[9:], "run_id must be ec-skill-<UUIDv7>")


def dispatch_root() -> Path:
    return Path.home() / ".easy-coding" / "skill-dispatch"


def mode() -> dict:
    """Read only the block YAML field used by Harness, without importing its parser."""
    path = Path.home() / ".easy-coding" / "config.yaml"
    if not path.exists():
        return {"cooperate_mode": "default", "source": "default"}
    in_behavior = False
    found_behavior = False
    value = None
    field_indent = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        require("\t" not in line, "local config must use space-indented block YAML")
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0:
            in_behavior = False
            if stripped.startswith("behavior:"):
                require(stripped == "behavior:" and not found_behavior,
                        "behavior must be one block YAML mapping")
                in_behavior = found_behavior = True
            continue
        if in_behavior:
            if field_indent is None:
                field_indent = indent
            if stripped.startswith("cooperate_mode:"):
                require(indent == field_indent and value is None,
                        "behavior.cooperate_mode must be one direct field")
                value = stripped.split(":", 1)[1].strip()
                require(value in {"default", "dispatch", "'default'", "'dispatch'",
                                  '"default"', '"dispatch"'},
                        "behavior.cooperate_mode must be default or dispatch")
                value = value.strip("'\"")
    return {"cooperate_mode": value or "default", "source": str(path) if value else "default"}


def atomic_write(path: Path, content: str) -> None:
    require(not path.is_symlink(), f"refuse symlink: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_document(path: Path, metadata: dict, body: str) -> None:
    atomic_write(path, HEADER + json.dumps(metadata, ensure_ascii=False, indent=2)
                 + "\n```\n" + body)


def read_document(path: Path, kind: str) -> tuple[dict, str]:
    require(path.is_file() and not path.is_symlink(), f"missing or unsafe {kind}: {path}")
    text = path.read_text(encoding="utf-8")
    require(text.startswith(HEADER), f"invalid {kind} header")
    raw, separator, body = text[len(HEADER):].partition("\n```\n")
    require(bool(separator), f"invalid {kind} metadata block")
    data = json.loads(raw)
    require(isinstance(data, dict) and data.get("schema") == SCHEMA and data.get("kind") == kind,
            f"unsupported {kind} protocol")
    return data, body


def location(value: str, name: str) -> Path:
    path = Path(value).expanduser()
    require(path.is_absolute() and path.name == name, f"use the absolute {name} path")
    validate_run_id(path.parent.name)
    require(path.parent.parent == dispatch_root(), "handoff must be inside local skill-dispatch")
    require(not path.parent.is_symlink() and not dispatch_root().is_symlink(),
            "handoff directories must not be symlinks")
    return path


def load_request(path: Path, round_number: int) -> tuple[dict, str]:
    data, body = read_document(path, "request")
    frozen = data.get("frozen")
    require(isinstance(frozen, dict), "missing frozen request")
    require(frozen.get("run_id") == path.parent.name and frozen.get("round") == round_number,
            "run_id or handoff round mismatch; do not select another request")
    require(digest(frozen) == data.get("request_sha256") and digest(body) == frozen.get("body_sha256"),
            "frozen request changed")
    checkpoint = data.get("checkpoint")
    require(isinstance(checkpoint, dict) and checkpoint.get("stage") in STAGES,
            "invalid coordinator checkpoint")
    baseline = path.parent / "baseline.json"
    require(baseline.is_file() and not baseline.is_symlink(), "original baseline is missing or unsafe")
    require(file_digest(baseline) == frozen.get("baseline_sha256"), "original baseline changed")
    return data, body


def memory_path(path: str) -> bool:
    return path.startswith(".easy-coding/memory/") or path in {
        ".easy-coding/ABSTRACT.md", ".easy-coding/CHANGELOG.md"}


def memory_business_digest(current: dict) -> str:
    return digest([change for change in current["changes"] if not memory_path(change["path"])])


def snapshot(baseline: Path, scope: list[str], ignore: list[str], *, memory: bool = False) -> dict:
    require(all(isinstance(values, list) and all(isinstance(value, str) for value in values)
                for values in (scope, ignore)), "scope and ignore must be string lists")
    _, state = quality._load_baseline(str(baseline))
    ids = {repo["id"] for repo in state["repositories"]}
    scopes = quality._parse_paths(scope, ids, "--scope")
    require(any(scopes.values()), "scope must not be empty")
    current = quality._capture_payload(state, scopes, quality._parse_paths(ignore, ids, "--ignore"))
    require(not any(repo["head_moved"] for repo in current["repositories"]), "repository HEAD moved")
    unexpected = current["unexpected_changes"]
    if memory:
        unexpected = [change for change in unexpected if not memory_path(change["path"])]
    require(not unexpected, "worktree changed outside the approved scope")
    return current


def request_snapshot(path: Path, data: dict, *, memory: bool = False) -> dict:
    context = data["checkpoint"].get("revision") or data["frozen"]
    return snapshot(path.parent / "baseline.json", context["scope"], context["ignore"], memory=memory)


def changes(current: dict) -> dict:
    return {f'{item["repo_id"]}:{item["path"]}': digest(item) for item in current["changes"]}


def worker_scope(data: dict, current: dict) -> None:
    frozen = data["frozen"]
    before, after = frozen["input_changes"], changes(current)
    ids = {repo["id"] for repo in current["repositories"]}
    scopes = quality._parse_paths(frozen["work_scope"], ids, "--scope")
    for key in set(before) | set(after):
        repo, path = key.split(":", 1)
        require(before.get(key) == after.get(key) or quality._matches(path, scopes[repo]),
                f"executor changed a file outside this handoff: {key}")
    require(digest(current["ignored_changes"]) == frozen["input_ignored_sha256"],
            "executor changed coordinator-owned machine files")


def bound_result(path: Path, request: dict) -> tuple[dict, str]:
    result, body = read_document(path, "result")
    frozen = request["frozen"]
    require(all(result.get(key) == frozen[key] for key in ("run_id", "round"))
            and result.get("request_sha256") == request["request_sha256"], "result belongs to another request")
    require(result.get("body_sha256") == digest(body), "result body changed")
    require(result.get("status") in {"working", "implemented", "blocked"}, "invalid result status")
    require(result.get("blocked_stage") in {"IMPLEMENT", "ANALYSIS"}, "invalid blocked stage")
    return result, body


def prompt(path: Path, round_number: int, returning: bool) -> str:
    action = "接收" if returning else "接手执行"
    tail = "继续审查与验证（阻断回执先处理阻断）" if returning else "按已确认方案实施，完成后交回主 Agent"
    return f"使用 easy-coding {action} {path}，交接轮次 {round_number}；{tail}。"


def read_input(args: argparse.Namespace) -> dict:
    data = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text(encoding="utf-8"))
    require(isinstance(data, dict), "input must be a JSON object")
    return data


def send(args: argparse.Namespace) -> dict:
    require(mode()["cooperate_mode"] == "dispatch", "new handoffs require cooperate_mode: dispatch")
    validate_run_id(args.run_id)
    require(args.round > 0, "round must be positive")
    path = location(str(dispatch_root() / args.run_id / "request.md"), "request.md")
    payload = read_input(args)
    nonempty(payload.get("plan"), "plan")
    receipt(payload.get("authorization"), "authorization")
    quality_round = payload.get("quality_round", 1)
    require(type(quality_round) is int and quality_round > 0, "quality_round must be positive")
    original, _ = quality._load_baseline(args.baseline)
    current = snapshot(original, args.scope, args.ignore)
    checks_path = path.parent / "checks.json"
    checks_source = None
    if args.checks:
        checks_source = quality._validate_output_path(Path(args.checks),
                                                     (Path(repo["root"]) for repo in current["repositories"]))
        require(checks_source.is_file(), "check store is missing")
        quality_checks.load_store(checks_source, file_digest(original))
        require(not checks_path.exists() or checks_source == checks_path
                or checks_source.read_bytes() == checks_path.read_bytes(),
                "cannot replace existing handoff check evidence")
    require(all(not path.parent.resolve().is_relative_to(Path(repo["root"]))
                for repo in current["repositories"]), "handoff must remain outside repositories")
    if path.exists():
        previous, _ = load_request(path, args.round - 1)
        checkpoint = previous["checkpoint"]
        require(checkpoint["stage"] in {"QUALITY", "ANALYSIS", "IMPLEMENT"}
                and checkpoint.get("accepted_result"), "previous handoff has not returned to the coordinator")
        require(file_digest(original) == previous["frozen"]["baseline_sha256"], "cannot replace original baseline")
        require(quality_round >= checkpoint["quality_round"], "quality_round cannot move backwards")
    else:
        require(args.round == 1 and not path.parent.exists(), "new handoff must start at round 1 in an unused directory")
        require(not current["changes"] or payload.get("implementation_started") is True,
                "existing candidate requires implementation_started and its explanation in the plan")
    work_scope = args.work_scope or args.scope
    ids = {repo["id"] for repo in current["repositories"]}
    full = quality._parse_paths(args.scope, ids, "--scope")
    for repo, paths in quality._parse_paths(work_scope, ids, "--scope").items():
        require(all(quality._matches(item, full[repo]) for item in paths), "work_scope exceeds the approved run scope")
    body = payload["plan"].strip() + "\n"
    frozen = {
        "run_id": args.run_id, "round": args.round, "next_action": args.action,
        "stop_after": "IMPLEMENT", "return_to": "QUALITY", "quality_round": quality_round,
        "authorization": payload["authorization"], "body_sha256": digest(body),
        "baseline_sha256": file_digest(original), "scope": args.scope, "ignore": args.ignore,
        "work_scope": work_scope, "input_candidate_sha256": current["candidate_sha256"],
        "input_changes": changes(current), "input_ignored_sha256": digest(current["ignored_changes"]),
    }
    data = {"schema": SCHEMA, "kind": "request", "frozen": frozen, "request_sha256": digest(frozen),
            "checkpoint": {"stage": "IMPLEMENT", "quality_round": quality_round,
                           "accepted_result": None, "candidate_sha256": current["candidate_sha256"], "note": ""}}
    if args.apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not (path.parent / "baseline.json").exists():
            atomic_write(path.parent / "baseline.json", original.read_text(encoding="utf-8"))
        if checks_source and checks_source != checks_path and not checks_path.exists():
            atomic_write(checks_path, checks_source.read_text(encoding="utf-8"))
        write_document(path, data, body)
        (path.parent / "result.md").unlink(missing_ok=True)
    return {"applied": args.apply, "request": str(path), "request_sha256": data["request_sha256"],
            "baseline": str(path.parent / "baseline.json"), "checks": str(checks_path),
            "prompt": prompt(path, args.round, False)}


def resume(args: argparse.Namespace) -> dict:
    name = "request.md" if args.role == "executor" else "result.md"
    provided = location(args.path, name)
    path = provided.parent / "request.md"
    data, body = load_request(path, args.round)
    frozen, checkpoint = data["frozen"], data["checkpoint"]
    _, baseline = quality._load_baseline(str(path.parent / "baseline.json"))
    require(Path(args.repo).resolve() in {Path(repo["root"]) for repo in baseline["repositories"]},
            "current worktree is not bound to this handoff")
    result_path = path.parent / "result.md"
    stage = checkpoint["stage"]
    outcome = None
    result_body = ""
    if args.role == "executor":
        require(not checkpoint["accepted_result"], "handoff already returned; continue in the coordinator")
        current = request_snapshot(path, data)
        if result_path.exists():
            result, result_body = bound_result(result_path, data)
            if result["status"] != "working":
                require(current["candidate_sha256"] == result["candidate_sha256"], "returned candidate changed")
                worker_scope(data, current)
                return {"stage": "IMPLEMENT", "next_action": "hand_back", "stop": True,
                        "prompt": prompt(result_path, args.round, True)}
            worker_scope(data, current)
        else:
            require(current["candidate_sha256"] == frozen["input_candidate_sha256"], "candidate changed before executor acceptance")
            worker_scope(data, current)
            if args.apply:
                write_result(result_path, data, current, "working", "Executor accepted this handoff.\n", "IMPLEMENT")
        stage, action = "IMPLEMENT", frozen["next_action"]
    else:
        result, result_body = bound_result(result_path, data)
        require(result["status"] != "working", "executor has not returned a result")
        signature = digest(result)
        if checkpoint["accepted_result"]:
            require(signature == checkpoint["accepted_result"], "accepted result changed")
        else:
            stage = "QUALITY" if result["status"] == "implemented" else result["blocked_stage"]
        if stage != "CLOSED":
            current = request_snapshot(path, data, memory=stage in {"MEMORY", "COMPLETE"})
            expected = checkpoint["candidate_sha256"] if checkpoint["accepted_result"] else result["candidate_sha256"]
            if stage in {"MEMORY", "COMPLETE"}:
                require(memory_business_digest(current) == checkpoint.get("memory_business_sha256"),
                        "business candidate changed during MEMORY")
            elif not (checkpoint["accepted_result"] and stage == "IMPLEMENT"):
                require(current["candidate_sha256"] == expected, "candidate changed since the recorded handoff/checkpoint")
        if not checkpoint["accepted_result"] and args.apply:
            checkpoint.update(stage=stage, accepted_result=signature, candidate_sha256=result["candidate_sha256"])
            write_document(path, data, body)
        action, outcome = stage.lower(), result["status"]
    context = checkpoint.get("revision") or frozen
    return {"applied": args.apply, "role": args.role, "stage": stage, "next_action": action,
            "outcome": outcome, "run_id": frozen["run_id"], "round": args.round,
            "quality_round": checkpoint["quality_round"], "baseline": str(path.parent / "baseline.json"),
            "checks": str(path.parent / "checks.json"),
            "repositories": [{"id": repo["id"], "root": repo["root"]} for repo in baseline["repositories"]],
            "scope": context["scope"], "ignore": context["ignore"],
            "work_scope": frozen["work_scope"] if args.role == "executor" else context["scope"],
            "authorization": context["authorization"], "plan": context.get("plan", body), "result": result_body,
            "checkpoint": {key: value for key, value in checkpoint.items() if key != "revision"},
            "stop_after": frozen["stop_after"] if args.role == "executor" else None}


def write_result(path: Path, request: dict, current: dict, status: str, body: str, blocked_stage: str) -> None:
    frozen = request["frozen"]
    before, after = frozen["input_changes"], changes(current)
    data = {"schema": SCHEMA, "kind": "result", "run_id": frozen["run_id"], "round": frozen["round"],
            "request_sha256": request["request_sha256"], "status": status,
            "next_action": "quality" if status == "implemented" else "blocked" if status == "blocked" else "implement",
            "blocked_stage": blocked_stage, "candidate_sha256": current["candidate_sha256"],
            "changed_files": sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key)),
            "body_sha256": digest(body)}
    write_document(path, data, body)


def finish(args: argparse.Namespace) -> dict:
    path = location(args.path, "request.md")
    data, _ = load_request(path, args.round)
    result_path = path.parent / "result.md"
    previous, _ = bound_result(result_path, data)
    require(not data["checkpoint"]["accepted_result"], "result already accepted by coordinator")
    require(previous["status"] == "working", "result already returned; use its existing return prompt")
    payload = read_input(args)
    nonempty(payload.get("summary"), "summary")
    current = request_snapshot(path, data)
    worker_scope(data, current)
    require(args.status != "implemented" or bool(current["changes"]), "cannot return an empty implementation")
    if args.apply:
        write_result(result_path, data, current, args.status, payload["summary"].strip() + "\n", args.blocked_stage)
    return {"applied": args.apply, "status": args.status, "candidate_sha256": current["candidate_sha256"],
            "prompt": prompt(result_path, args.round, True), "stop": True}


def checkpoint(args: argparse.Namespace) -> dict:
    path = location(args.path, "request.md")
    data, body = load_request(path, args.round)
    point = data["checkpoint"]
    require(bool(point["accepted_result"]), "coordinator must receive the result before checkpointing")
    require(args.stage == point["stage"] or args.stage in STAGES[point["stage"]], "checkpoint cannot move to that stage")
    payload = read_input(args)
    nonempty(payload.get("note"), "checkpoint note")
    if "revision" in payload:
        require(point["stage"] == "ANALYSIS" and args.stage == "IMPLEMENT",
                "a confirmed local revision requires ANALYSIS -> IMPLEMENT")
        revision = payload["revision"]
        require(isinstance(revision, dict) and set(revision) == {"plan", "authorization", "scope", "ignore"},
                "revision requires plan, authorization, scope and ignore")
        nonempty(revision["plan"], "revision.plan")
        receipt(revision["authorization"], "revision.authorization")
        point["revision"] = revision
    next_round = payload.get("quality_round", point["quality_round"])
    require(type(next_round) is int and next_round >= point["quality_round"], "quality_round cannot move backwards")
    if args.stage == "MEMORY" and point["stage"] != "MEMORY":
        receipt(payload.get("quality_confirmation"), "quality_confirmation")
        nonempty(payload.get("evidence"), "QUALITY evidence")
    if args.stage == "COMPLETE":
        nonempty(payload.get("memory_ref"), "memory_ref")
    if args.stage != "CLOSED":
        current = request_snapshot(path, data, memory=point["stage"] in {"MEMORY", "COMPLETE"})
        if point["stage"] in {"MEMORY", "COMPLETE"}:
            require(memory_business_digest(current) == point.get("memory_business_sha256"),
                    "business candidate changed during MEMORY")
        elif args.stage == "MEMORY":
            require(current["candidate_sha256"] == point["candidate_sha256"], "candidate changed after QUALITY")
            point["memory_business_sha256"] = memory_business_digest(current)
        if ((point["stage"] not in {"MEMORY", "COMPLETE"} and current["candidate_sha256"] != point["candidate_sha256"])
                or args.stage in {"IMPLEMENT", "ANALYSIS"}):
            for key in ("quality_confirmation", "evidence", "memory_ref"):
                point.pop(key, None)
        if point["stage"] not in {"MEMORY", "COMPLETE"}:
            point["candidate_sha256"] = current["candidate_sha256"]
    point.update(stage=args.stage, quality_round=next_round, note=payload["note"])
    for key in ("quality_confirmation", "evidence", "memory_ref"):
        if key in payload:
            point[key] = payload[key]
    if args.apply:
        write_document(path, data, body)
    return {"applied": args.apply, "checkpoint": point}


def cleanup(args: argparse.Namespace) -> dict:
    path = location(args.path, "request.md")
    data, _ = load_request(path, args.round)
    require(data["checkpoint"]["stage"] in {"COMPLETE", "CLOSED"} or args.cancelled,
            "cleanup requires completion or explicit user cancellation")
    if data["checkpoint"]["stage"] == "COMPLETE" and not args.cancelled:
        current = request_snapshot(path, data, memory=True)
        require(memory_business_digest(current) == data["checkpoint"].get("memory_business_sha256"),
                "business candidate changed before cleanup")
    children = list(path.parent.iterdir())
    require(all(item.name in {"request.md", "result.md", "baseline.json", "checks.json"}
                and item.is_file() and not item.is_symlink() for item in children),
            "unexpected files in handoff directory; refuse recursive cleanup")
    if args.apply:
        for item in children:
            item.unlink()
        path.parent.rmdir()
    return {"applied": args.apply, "removed": str(path.parent), "stage": "CLOSED" if args.cancelled else data["checkpoint"]["stage"]}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("mode").set_defaults(handler=lambda _: mode())
    for name, handler in (("send", send), ("resume", resume), ("finish", finish),
                          ("checkpoint", checkpoint), ("cleanup", cleanup)):
        command = commands.add_parser(name)
        command.set_defaults(handler=handler)
        command.add_argument("--apply", action="store_true", help="apply the explicit handoff operation; otherwise read-only")
        command.add_argument("--round", type=int, required=True)
        if name == "send":
            command.add_argument("--run-id", required=True)
            command.add_argument("--baseline", required=True)
            command.add_argument("--checks", help="carry existing input-bound checks into the handoff")
            command.add_argument("--scope", action="append", required=True)
            command.add_argument("--ignore", action="append", default=[])
            command.add_argument("--work-scope", action="append")
            command.add_argument("--action", choices=["implement", "repair"], required=True)
        else:
            command.add_argument("--path", required=True)
        if name in {"send", "finish", "checkpoint"}:
            command.add_argument("--input", default="-", help="JSON from stdin (-) or a file")
        if name == "resume":
            command.add_argument("--role", choices=["executor", "coordinator"], required=True)
            command.add_argument("--repo", required=True, help="current Git worktree root")
        if name == "finish":
            command.add_argument("--status", choices=["implemented", "blocked"], required=True)
            command.add_argument("--blocked-stage", choices=["IMPLEMENT", "ANALYSIS"], default="IMPLEMENT")
        if name == "checkpoint":
            command.add_argument("--stage", choices=list(STAGES), required=True)
        if name == "cleanup":
            command.add_argument("--cancelled", action="store_true", help="user explicitly cancelled this run")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(args.handler(args), ensure_ascii=False, indent=2))
        return 0
    except (DispatchError, quality.InputError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "action": "stop; do not start a new task"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
