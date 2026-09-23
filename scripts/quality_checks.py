#!/usr/bin/env python3
"""Reuse input-bound QUALITY checks without a task runtime or stage state.

prepare/record accept a JSON array from --input (stdin by default). Only --apply
writes the repository-external check store. Commands and reviews are run by the
caller, never by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from . import quality_fingerprint as quality
except ImportError:
    import quality_fingerprint as quality


SCHEMA = "easy-coding-quality-checks/v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise quality.InputError(message)


def digest(value: object) -> str:
    return quality._canonical_sha256(value)


def text_value(value: object, field: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{field} must be non-empty text")
    return value


def strings(value: object, field: str) -> list[str]:
    require(isinstance(value, list) and all(isinstance(item, str) and item for item in value),
            f"{field} must be a list of non-empty strings")
    return sorted(set(value))


def load_store(path: Path, baseline_sha256: str) -> dict:
    require(not path.is_symlink(), "check store must not be a symlink")
    if not path.exists():
        return {"schema": SCHEMA, "baseline_sha256": baseline_sha256, "checks": {}}
    store = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(store, dict) and store.get("schema") == SCHEMA
            and isinstance(store.get("checks"), dict), "invalid check store")
    require(store.get("baseline_sha256") == baseline_sha256,
            "check store belongs to a different baseline")
    return store


class Inputs:
    """One fresh snapshot per invocation; share reads only within that invocation."""

    def __init__(self, baseline: dict):
        self.roots = {repo["id"]: Path(repo["root"]) for repo in baseline["repositories"]}
        self.names: dict[str, set[str]] = {}
        self.entries: dict[tuple[str, str], object] = {}
        self.tools: dict[Path, dict] = {}
        for repo in baseline["repositories"]:
            require(quality._head(Path(repo["root"])) == repo["head"],
                    f"HEAD moved: {repo['id']}; resolve the candidate baseline first")

    def descriptor(self, item: dict) -> dict:
        require(isinstance(item, dict), "each check must be an object")
        require(not set(item) - {"id", "type", "inputs", "command", "cwd", "toolchain",
                                 "environment", "contract", "volatile"}, "unknown check fields")
        check_id = text_value(item.get("id"), "id")
        kind = item.get("type")
        require(kind in {"review", "verify"}, "type must be review or verify")
        paths = item.get("inputs", {repo: ["."] for repo in self.roots})
        require(isinstance(paths, dict) and bool(paths), "inputs must name at least one repository")
        normalized = {}
        for repo, values in sorted(paths.items()):
            require(repo in self.roots, f"unknown input repository: {repo}")
            values = strings(values, "inputs")
            require(bool(values), f"empty input scope: {repo}")
            normalized[repo] = sorted({quality._normalize_relative_path(value) for value in values})
            require(all(".git" not in Path(value).parts for value in normalized[repo]),
                    "Git internals are not check inputs")
        cwd = item.get("cwd", next(iter(self.roots)) + ":.")
        require(isinstance(cwd, str) and ":" in cwd, "cwd must be repo-id:relative-path")
        repo, relative = cwd.split(":", 1)
        require(repo in self.roots, "unknown cwd repository")
        relative = quality._normalize_relative_path(relative)
        tools = strings(item.get("toolchain", []), "toolchain")
        environment = strings(item.get("environment", ["PATH"] if kind == "verify" else []), "environment")
        require(all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in environment),
                "environment must contain variable names, not values")
        volatile = item.get("volatile", False)
        require(type(volatile) is bool, "volatile must be boolean")
        result = {"id": check_id, "type": kind, "inputs": normalized, "cwd": f"{repo}:{relative}",
                  "toolchain": tools, "environment": environment, "volatile": volatile}
        if kind == "verify":
            result["command"] = text_value(item.get("command"), "command")
            require(bool(tools), "verification must declare its actual toolchain executables")
        else:
            result["contract"] = text_value(item.get("contract"), "review contract")
        return result

    def file_inputs(self, repo: str, scopes: list[str]) -> dict:
        root = self.roots[repo]
        if repo not in self.names:
            self.names[repo] = set(quality._nul_paths(quality._git(
                root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")))
        names = set(scopes)
        for scope in scopes:
            names.update(name for name in self.names[repo] if quality._matches(name, [scope]))
        result = {}
        for name in sorted(names):
            key = (repo, name)
            if key not in self.entries:
                entry = quality._worktree_entry(root, name)
                # A scope inside a nested repo is as opaque as its gitlink/root.
                if entry and entry["kind"] == "directory":
                    directory = root / name
                    entry = {**entry, "nested_repo": any(
                        (parent / ".git").exists() for parent in (directory, *directory.parents)
                        if parent != root and parent.is_relative_to(root))}
                self.entries[key] = entry
            result[name] = self.entries[key]
        return result

    def capture(self, descriptor: dict) -> dict:
        files = {repo: self.file_inputs(repo, scopes) for repo, scopes in descriptor["inputs"].items()}
        uncacheable = [f"{repo}:{name}" for repo, entries in files.items() for name, entry in entries.items()
                       if entry and (entry["kind"] in {"symlink", "parent-symlink", "other"}
                                     or entry.get("nested_repo"))]
        repo, relative = descriptor["cwd"].split(":", 1)
        directory = (self.roots[repo] / relative).resolve(strict=True)
        require(directory.is_dir() and directory.is_relative_to(self.roots[repo]), "cwd escapes repository")
        search_path = os.pathsep.join(str(directory / component) for component in os.get_exec_path())
        toolchain = {}
        for name in descriptor["toolchain"]:
            path = directory / name if "/" in name else shutil.which(name, path=search_path)
            require(path is not None, f"toolchain executable unavailable: {name}")
            path = Path(path).resolve(strict=True)
            require(path.is_file() and os.access(path, os.X_OK), f"toolchain must be an executable file: {name}")
            if path not in self.tools:
                self.tools[path] = {"path": str(path), "sha256": quality._file_sha256(path),
                                    "mode": oct(path.stat().st_mode & 0o777)}
            toolchain[name] = self.tools[path]
        # Never copy environment values (which may contain credentials) into the store or output.
        environment = {name: hashlib.sha256(os.environ[name].encode()).hexdigest() if name in os.environ else None
                       for name in descriptor["environment"]}
        material = {"descriptor": descriptor, "files": files, "resolved_cwd": str(directory),
                    "toolchain": toolchain, "environment": environment}
        return {**material, "input_sha256": digest(material), "uncacheable_inputs": sorted(uncacheable)}


def changed_inputs(previous: dict | None, current: dict) -> list[str]:
    if previous is None:
        return ["no previous result"]
    result = []
    for repo in sorted(set(previous["files"]) | set(current["files"])):
        before, after = previous["files"].get(repo, {}), current["files"].get(repo, {})
        result.extend(f"{repo}:{name}" for name in sorted(set(before) | set(after))
                      if before.get(name) != after.get(name))
    for field in ("descriptor", "resolved_cwd", "toolchain", "environment"):
        if previous[field] != current[field]:
            result.append(field + " changed")
    return result


def prepare(store: dict, inputs: Inputs, records: list[dict], *, force: bool = False) -> list[dict]:
    responses = []
    seen = set()
    for record in records:
        descriptor = inputs.descriptor(record)
        check_id = descriptor["id"]
        require(check_id not in seen, "duplicate check id in batch")
        seen.add(check_id)
        current = inputs.capture(descriptor)
        check = store["checks"].setdefault(check_id, {})
        if force:
            # A concrete new concern retires the old pass even if this run is interrupted.
            check.pop("result", None)
        previous = check.get("result")
        reusable = bool(not force and not descriptor["volatile"] and not current["uncacheable_inputs"]
                        and previous and previous["passed"]
                        and previous["inputs"]["input_sha256"] == current["input_sha256"])
        response = {"id": check_id, "reusable": reusable, "input_sha256": current["input_sha256"],
                    "changed_inputs": changed_inputs(previous["inputs"] if previous else None, current),
                    "uncacheable_inputs": current["uncacheable_inputs"]}
        if reusable:
            check.pop("prepared", None)
            response["evidence"] = {key: value for key, value in previous.items() if key != "inputs"}
        else:
            prepared_id = str(uuid.uuid4())
            check["prepared"] = {"prepared_id": prepared_id, "inputs": current}
            response["prepared_id"] = prepared_id
        responses.append(response)
    return responses


def record(store: dict, inputs: Inputs, results: list[dict]) -> list[dict]:
    responses = []
    seen = set()
    for result in results:
        require(isinstance(result, dict), "each result must be an object")
        require(not set(result) - {"id", "prepared_id", "passed", "exit_code", "summary", "reviewer"},
                "unknown result fields")
        check_id = text_value(result.get("id"), "id")
        require(check_id not in seen, "duplicate result id in batch")
        seen.add(check_id)
        check = store["checks"].get(check_id, {})
        prepared = check.get("prepared")
        previous = check.get("result")
        if prepared is None and previous and previous.get("receipt_sha256") == digest(result):
            responses.append({"id": check_id, "recorded": True, "replayed": True})
            continue
        require(prepared is not None and result.get("prepared_id") == prepared["prepared_id"],
                f"prepare this check before recording its result: {check_id}")
        descriptor = inputs.descriptor(prepared["inputs"]["descriptor"])
        current = inputs.capture(descriptor)
        require(current["input_sha256"] == prepared["inputs"]["input_sha256"],
                f"check inputs changed during execution: {check_id}")
        require(type(result.get("passed")) is bool, "passed must be boolean")
        text_value(result.get("summary"), "summary")
        if descriptor["type"] == "verify":
            require(type(result.get("exit_code")) is int and result["passed"] == (result["exit_code"] == 0),
                    "passed must agree with the real exit_code")
        else:
            text_value(result.get("reviewer"), "reviewer")
        check["result"] = {**result, "inputs": current, "receipt_sha256": digest(result),
                           "recorded_at": datetime.now(timezone.utc).isoformat()}
        check.pop("prepared")
        responses.append({"id": check_id, "recorded": True, "passed": result["passed"],
                          "input_sha256": current["input_sha256"]})
    return responses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "record"])
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--input", default="-", help="JSON array from stdin (-) or a file")
    parser.add_argument("--force", action="store_true", help="prepare a fresh run after a concrete new concern")
    parser.add_argument("--apply", action="store_true", help="persist check inputs/results; otherwise preview only")
    args = parser.parse_args(argv)
    try:
        baseline_path, baseline = quality._load_baseline(args.baseline)
        path = quality._validate_output_path(Path(args.store), (Path(repo["root"]) for repo in baseline["repositories"]))
        require(path != baseline_path, "check store cannot overwrite the baseline")
        store = load_store(path, quality._file_sha256(baseline_path))
        payload = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text(encoding="utf-8"))
        require(isinstance(payload, list) and bool(payload), "input must be a non-empty JSON array")
        inputs = Inputs(baseline)
        response = prepare(store, inputs, payload, force=args.force) if args.command == "prepare" else record(store, inputs, payload)
        if args.apply:
            quality._write_json(path, store)
        print(json.dumps({"applied": args.apply, "store": str(path), "checks": response}, ensure_ascii=False, indent=2))
        return 0
    except (quality.InputError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
