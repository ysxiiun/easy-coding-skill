#!/usr/bin/env python3
"""Create and verify Easy Coding QUALITY candidate fingerprints.

The implementation uses only the Python standard library and Git plumbing. A baseline records
the dirty state that existed before implementation; capture/check compare against that snapshot,
so unchanged pre-existing edits do not become part of the candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence


BASELINE_SCHEMA = "easy-coding-quality-baseline/v1"
FINGERPRINT_SCHEMA = "easy-coding-quality-fingerprint/v1"
REPO_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
GIT_MODE_RE = re.compile(r"^[0-7]{6}$")
DIRTY_CATEGORIES = {"staged", "unstaged", "untracked", "unmerged"}


class InputError(ValueError):
    """The CLI input or repository boundary is invalid."""


def _git(root: Path, *args: str, allow_failure: bool = False) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode and not allow_failure:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise InputError(f"git {' '.join(args)} failed for {root}: {message}")
    return result.stdout if result.returncode == 0 else b""


def _decode_path(value: bytes) -> str:
    return value.decode("utf-8", "surrogateescape")


def _nul_paths(value: bytes) -> list[str]:
    return [_decode_path(item) for item in value.split(b"\0") if item]


def _head(root: Path) -> str:
    value = _git(root, "rev-parse", "--verify", "HEAD", allow_failure=True).strip()
    return value.decode("ascii") if value else "UNBORN"


def _index_entries(root: Path) -> dict[str, list[dict[str, str]]]:
    entries: dict[str, list[dict[str, str]]] = {}
    raw = _git(root, "ls-files", "-s", "-z")
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path_bytes = record.split(b"\t", 1)
            mode, object_id, stage_number = metadata.decode("ascii").split(" ", 2)
        except (ValueError, UnicodeDecodeError) as exc:
            raise InputError(f"invalid git index record in {root}") from exc
        path = _decode_path(path_bytes)
        entries.setdefault(path, []).append(
            {"mode": mode, "object": object_id, "stage": stage_number}
        )
    for value in entries.values():
        value.sort(key=lambda item: (item["stage"], item["mode"], item["object"]))
    return entries


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _worktree_entry(root: Path, relative_path: str) -> dict[str, Any] | None:
    parts = relative_path.split("/")
    path = root
    metadata = None
    for index, part in enumerate(parts):
        path = path / part
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            return None
        if index < len(parts) - 1 and stat.S_ISLNK(metadata.st_mode):
            target = os.readlink(path)
            return {
                "kind": "parent-symlink",
                "mode": "120000",
                "component": "/".join(parts[: index + 1]),
                "sha256": hashlib.sha256(os.fsencode(target)).hexdigest(),
                "target": target,
            }
    assert metadata is not None

    if stat.S_ISLNK(metadata.st_mode):
        target = os.readlink(path)
        target_bytes = os.fsencode(target)
        return {
            "kind": "symlink",
            "mode": "120000",
            "sha256": hashlib.sha256(target_bytes).hexdigest(),
            "target": target,
        }
    if stat.S_ISREG(metadata.st_mode):
        return {
            "kind": "file",
            "mode": "100755" if metadata.st_mode & stat.S_IXUSR else "100644",
            "sha256": _file_sha256(path),
            "size": metadata.st_size,
        }
    if stat.S_ISDIR(metadata.st_mode):
        return {"kind": "directory", "mode": oct(stat.S_IMODE(metadata.st_mode))}
    return {
        "kind": "other",
        "mode": oct(stat.S_IFMT(metadata.st_mode) | stat.S_IMODE(metadata.st_mode)),
    }


def _dirty_state(root: Path) -> dict[str, dict[str, Any]]:
    categories: dict[str, set[str]] = {}
    commands = (
        (
            "unstaged",
            ("diff", "--ignore-submodules=none", "--no-renames", "--name-only", "-z"),
        ),
        (
            "staged",
            (
                "diff",
                "--cached",
                "--ignore-submodules=none",
                "--no-renames",
                "--name-only",
                "-z",
            ),
        ),
        ("untracked", ("ls-files", "--others", "--exclude-standard", "-z")),
        (
            "unmerged",
            ("diff", "--ignore-submodules=none", "--name-only", "--diff-filter=U", "-z"),
        ),
    )
    for label, command in commands:
        for path in _nul_paths(_git(root, *command)):
            categories.setdefault(path, set()).add(label)

    index = _index_entries(root)
    state: dict[str, dict[str, Any]] = {}
    for path in sorted(categories):
        state[path] = {
            "categories": sorted(categories[path]),
            "index": index.get(path, []),
            "worktree": _worktree_entry(root, path),
        }
    return state


def _gitlink_paths(root: Path) -> set[str]:
    paths = {
        path
        for path, entries in _index_entries(root).items()
        if any(entry.get("mode") == "160000" for entry in entries)
    }
    raw_head = _git(root, "ls-tree", "-r", "-z", "HEAD", allow_failure=True)
    for record in raw_head.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path_bytes = record.split(b"\t", 1)
            mode = metadata.split(b" ", 1)[0]
        except ValueError as exc:
            raise InputError(f"invalid git tree record in {root}") from exc
        if mode == b"160000":
            paths.add(_decode_path(path_bytes))
    return paths


def _validate_dirty_gitlinks(
    repo_id: str,
    root: Path,
    dirty: dict[str, dict[str, Any]],
    configured_roots: set[Path],
) -> list[str]:
    uncovered: list[str] = []
    gitlink_paths = _gitlink_paths(root)
    for path in dirty:
        if path not in gitlink_paths:
            continue
        gitlink_root = root.joinpath(*path.split("/")).resolve(strict=False)
        if gitlink_root not in configured_roots:
            uncovered.append(f"{repo_id}:{path}")
    return uncovered


def _validate_nested_repositories(
    repo_id: str,
    root: Path,
    dirty: dict[str, dict[str, Any]],
    configured_roots: set[Path],
) -> list[str]:
    uncovered: list[str] = []
    for path, path_state in dirty.items():
        worktree = path_state.get("worktree")
        if not isinstance(worktree, dict) or worktree.get("kind") != "directory":
            continue
        nested_path = path.rstrip("/")
        if not nested_path:
            continue
        candidate = root.joinpath(*nested_path.split("/")).resolve(strict=False)
        nested_root_raw = _git(candidate, "rev-parse", "--show-toplevel", allow_failure=True).strip()
        if not nested_root_raw:
            continue
        nested_root = Path(_decode_path(nested_root_raw)).resolve(strict=False)
        if nested_root == candidate and nested_root not in configured_roots:
            uncovered.append(f"{repo_id}:{nested_path}")
    return uncovered


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _parse_repositories(values: Sequence[str]) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_roots: set[Path] = set()
    for value in values:
        if "=" not in value:
            raise InputError(f"repository must use ID=ROOT: {value!r}")
        repo_id, root_value = value.split("=", 1)
        if not REPO_ID_RE.fullmatch(repo_id):
            raise InputError(f"invalid repository id: {repo_id!r}")
        if repo_id in seen:
            raise InputError(f"duplicate repository id: {repo_id}")
        if not root_value:
            raise InputError(f"repository root is empty for {repo_id}")
        requested = Path(root_value).expanduser().resolve(strict=True)
        git_root_raw = _git(requested, "rev-parse", "--show-toplevel").strip()
        git_root = Path(_decode_path(git_root_raw)).resolve(strict=True)
        if requested != git_root:
            raise InputError(f"repository root must be the Git root: {requested} != {git_root}")
        if git_root in seen_roots:
            raise InputError(f"duplicate repository root: {git_root}")
        repositories.append({"id": repo_id, "root": str(git_root)})
        seen.add(repo_id)
        seen_roots.add(git_root)
    if not repositories:
        raise InputError("at least one --repo is required")
    repositories.sort(key=lambda item: item["id"])
    return repositories


def _validate_output_path(output: Path, roots: Iterable[Path]) -> Path:
    output = output.expanduser()
    if not output.is_absolute():
        raise InputError("output path must be absolute")
    parent = output.parent.resolve(strict=True)
    resolved = parent / output.name
    for root in roots:
        if _inside(resolved, root):
            raise InputError(f"output must be outside repositories: {resolved}")
    return resolved


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _normalize_relative_path(value: str) -> str:
    if not value or "\0" in value or value.startswith("/"):
        raise InputError(f"invalid repository-relative path: {value!r}")
    parts = value.split("/")
    if any(part == ".." for part in parts):
        raise InputError(f"path escapes repository: {value!r}")
    normalized = posixpath.normpath(value)
    if normalized == ".." or normalized.startswith("../") or normalized.startswith("/"):
        raise InputError(f"path escapes repository: {value!r}")
    return normalized


def _validate_baseline_worktree(value: Any, repo_id: str, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise InputError(f"invalid baseline worktree state: {repo_id}:{path}")
    kind = value.get("kind")
    required_fields = {
        "file": {"kind", "mode", "sha256", "size"},
        "symlink": {"kind", "mode", "sha256", "target"},
        "parent-symlink": {"kind", "mode", "component", "sha256", "target"},
        "directory": {"kind", "mode"},
        "other": {"kind", "mode"},
    }
    if (
        not isinstance(kind, str)
        or kind not in required_fields
        or set(value) != required_fields[kind]
    ):
        raise InputError(f"invalid baseline worktree entry: {repo_id}:{path}")
    if not isinstance(value.get("mode"), str) or not value["mode"]:
        raise InputError(f"invalid baseline worktree mode: {repo_id}:{path}")
    if "sha256" in value and (
        not isinstance(value["sha256"], str) or not SHA256_RE.fullmatch(value["sha256"])
    ):
        raise InputError(f"invalid baseline worktree digest: {repo_id}:{path}")
    if "size" in value and (
        not isinstance(value["size"], int)
        or isinstance(value["size"], bool)
        or value["size"] < 0
    ):
        raise InputError(f"invalid baseline worktree size: {repo_id}:{path}")
    for field in ("component", "target"):
        if field in value and not isinstance(value[field], str):
            raise InputError(f"invalid baseline worktree {field}: {repo_id}:{path}")


def _validate_baseline_dirty_state(repo_id: str, dirty: dict[str, Any]) -> None:
    for path, state in dirty.items():
        if not isinstance(path, str):
            raise InputError(f"invalid baseline dirty path for {repo_id}")
        normalized = _normalize_relative_path(path)
        if normalized == "." or path not in {normalized, f"{normalized}/"}:
            raise InputError(f"non-canonical baseline dirty path: {repo_id}:{path}")
        if not isinstance(state, dict) or set(state) != {"categories", "index", "worktree"}:
            raise InputError(f"invalid baseline dirty entry: {repo_id}:{path}")
        categories = state["categories"]
        if (
            not isinstance(categories, list)
            or not categories
            or any(not isinstance(item, str) or item not in DIRTY_CATEGORIES for item in categories)
            or len(categories) != len(set(categories))
        ):
            raise InputError(f"invalid baseline dirty categories: {repo_id}:{path}")
        index = state["index"]
        if not isinstance(index, list):
            raise InputError(f"invalid baseline index state: {repo_id}:{path}")
        for entry in index:
            if not isinstance(entry, dict) or set(entry) != {"mode", "object", "stage"}:
                raise InputError(f"invalid baseline index entry: {repo_id}:{path}")
            if not isinstance(entry["mode"], str) or not GIT_MODE_RE.fullmatch(entry["mode"]):
                raise InputError(f"invalid baseline index mode: {repo_id}:{path}")
            if not isinstance(entry["object"], str) or not GIT_OBJECT_RE.fullmatch(
                entry["object"]
            ):
                raise InputError(f"invalid baseline index object: {repo_id}:{path}")
            if not isinstance(entry["stage"], str) or entry["stage"] not in {
                "0",
                "1",
                "2",
                "3",
            }:
                raise InputError(f"invalid baseline index stage: {repo_id}:{path}")
        _validate_baseline_worktree(state["worktree"], repo_id, path)


def _load_baseline(path_value: str) -> tuple[Path, dict[str, Any]]:
    path = Path(path_value).expanduser().resolve(strict=True)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid baseline JSON: {path}") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "repositories"}
        or payload.get("schema") != BASELINE_SCHEMA
    ):
        raise InputError("unsupported baseline schema")
    repositories = payload.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        raise InputError("baseline repositories must be a non-empty list")
    seen: set[str] = set()
    seen_roots: set[Path] = set()
    for repo in repositories:
        if not isinstance(repo, dict) or set(repo) != {"id", "root", "head", "dirty"}:
            raise InputError("invalid baseline repository")
        repo_id = repo.get("id")
        root_value = repo.get("root")
        if not isinstance(repo_id, str) or not REPO_ID_RE.fullmatch(repo_id) or repo_id in seen:
            raise InputError("invalid or duplicate baseline repository id")
        head = repo.get("head")
        if (
            not isinstance(root_value, str)
            or not root_value
            or "\0" in root_value
            or not Path(root_value).is_absolute()
            or not isinstance(head, str)
            or (head != "UNBORN" and not GIT_OBJECT_RE.fullmatch(head))
        ):
            raise InputError(f"invalid baseline repository metadata: {repo_id}")
        root = Path(root_value).resolve(strict=True)
        if str(root) != root_value:
            raise InputError(f"baseline repository root is not canonical: {repo_id}")
        git_root = Path(_decode_path(_git(root, "rev-parse", "--show-toplevel").strip())).resolve(
            strict=True
        )
        if root != git_root:
            raise InputError(f"baseline repository root changed: {repo_id}")
        if root in seen_roots:
            raise InputError(f"duplicate baseline repository root: {root}")
        if _inside(path, root):
            raise InputError("baseline file must remain outside repositories")
        dirty = repo.get("dirty")
        if not isinstance(dirty, dict):
            raise InputError(f"invalid baseline dirty state: {repo_id}")
        _validate_baseline_dirty_state(repo_id, dirty)
        seen.add(repo_id)
        seen_roots.add(root)
    return path, payload


def _parse_paths(
    values: Sequence[str], repository_ids: set[str], option: str
) -> dict[str, list[str]]:
    result = {repo_id: [] for repo_id in repository_ids}
    for value in values:
        if ":" not in value:
            raise InputError(f"{option} must use ID:PATH: {value!r}")
        repo_id, path_value = value.split(":", 1)
        if repo_id not in repository_ids:
            raise InputError(f"unknown repository id in {option}: {repo_id!r}")
        normalized = _normalize_relative_path(path_value)
        if option == "--ignore" and normalized == ".":
            raise InputError("--ignore cannot exclude an entire repository")
        if normalized not in result[repo_id]:
            result[repo_id].append(normalized)
    for paths in result.values():
        paths.sort()
    return result


def _matches(path: str, boundaries: Sequence[str]) -> bool:
    return any(boundary == "." or path == boundary or path.startswith(f"{boundary}/") for boundary in boundaries)


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _capture_payload(
    baseline: dict[str, Any],
    scopes: dict[str, list[str]],
    ignores: dict[str, list[str]],
    *,
    allow_uncovered_repositories: bool = False,
) -> dict[str, Any]:
    repositories: list[dict[str, Any]] = []
    candidate_changes: list[dict[str, Any]] = []
    unexpected_changes: list[dict[str, Any]] = []
    ignored_changes: list[dict[str, Any]] = []
    uncovered_dirty_gitlinks: list[str] = []
    uncovered_nested_repositories: list[str] = []

    configured_roots = {Path(repo["root"]) for repo in baseline["repositories"]}
    for baseline_repo in sorted(baseline["repositories"], key=lambda item: item["id"]):
        repo_id = baseline_repo["id"]
        root = Path(baseline_repo["root"])
        current_head = _head(root)
        current_dirty = _dirty_state(root)
        uncovered = _validate_dirty_gitlinks(repo_id, root, current_dirty, configured_roots)
        if uncovered and not allow_uncovered_repositories:
            raise InputError(
                "dirty gitlink requires its submodule Git root as a separate --repo: "
                + ", ".join(uncovered)
            )
        uncovered_dirty_gitlinks.extend(uncovered)
        uncovered_nested = _validate_nested_repositories(
            repo_id, root, current_dirty, configured_roots
        )
        if uncovered_nested and not allow_uncovered_repositories:
            raise InputError(
                "nested Git root requires a separate --repo: " + ", ".join(uncovered_nested)
            )
        uncovered_nested_repositories.extend(uncovered_nested)
        baseline_dirty = baseline_repo["dirty"]
        repo_candidate: list[dict[str, Any]] = []
        repo_unexpected: list[dict[str, Any]] = []
        repo_ignored: list[dict[str, Any]] = []

        for path in sorted(set(baseline_dirty) | set(current_dirty)):
            before = baseline_dirty.get(path)
            after = current_dirty.get(path)
            if before == after:
                continue
            change = {
                "repo_id": repo_id,
                "path": path,
                "before": before,
                "after": after,
            }
            if _matches(path, ignores[repo_id]):
                repo_ignored.append(change)
                ignored_changes.append(change)
            elif _matches(path, scopes[repo_id]):
                repo_candidate.append(change)
                candidate_changes.append(change)
            else:
                repo_unexpected.append(change)
                unexpected_changes.append(change)

        repositories.append(
            {
                "id": repo_id,
                "root": str(root),
                "baseline_head": baseline_repo["head"],
                "head": current_head,
                "head_moved": current_head != baseline_repo["head"],
                "scopes": scopes[repo_id],
                "ignores": ignores[repo_id],
                "changes": repo_candidate,
                "unexpected_changes": repo_unexpected,
                "ignored_changes": repo_ignored,
            }
        )

    fingerprint_material = {
        "schema": FINGERPRINT_SCHEMA,
        "repositories": [
            {
                "id": repo["id"],
                "baseline_head": repo["baseline_head"],
                "head": repo["head"],
                "scopes": repo["scopes"],
                "ignores": repo["ignores"],
                "changes": repo["changes"],
            }
            for repo in repositories
        ],
    }
    return {
        "schema": FINGERPRINT_SCHEMA,
        "candidate_sha256": _canonical_sha256(fingerprint_material),
        "repositories": repositories,
        "changes": candidate_changes,
        "unexpected_changes": unexpected_changes,
        "ignored_changes": ignored_changes,
        "uncovered_dirty_gitlinks": uncovered_dirty_gitlinks,
        "uncovered_nested_repositories": uncovered_nested_repositories,
    }


def _emit(payload: dict[str, Any], output_value: str | None, roots: Iterable[Path]) -> None:
    if output_value:
        output = _validate_output_path(Path(output_value), roots)
        _write_json(output, payload)
    else:
        json.dump(payload, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
        sys.stdout.write("\n")


def command_baseline(args: argparse.Namespace) -> int:
    repositories = _parse_repositories(args.repo)
    roots = [Path(repo["root"]) for repo in repositories]
    output = _validate_output_path(Path(args.output), roots)
    payload_repositories: list[dict[str, Any]] = []
    configured_roots = set(roots)
    for repo in repositories:
        root = Path(repo["root"])
        dirty = _dirty_state(root)
        uncovered = _validate_dirty_gitlinks(repo["id"], root, dirty, configured_roots)
        if uncovered:
            raise InputError(
                "dirty gitlink requires its submodule Git root as a separate --repo: "
                + ", ".join(uncovered)
            )
        uncovered_nested = _validate_nested_repositories(
            repo["id"], root, dirty, configured_roots
        )
        if uncovered_nested:
            raise InputError(
                "nested Git root requires a separate --repo: " + ", ".join(uncovered_nested)
            )
        payload_repositories.append(
            {"id": repo["id"], "root": repo["root"], "head": _head(root), "dirty": dirty}
        )
    payload = {"schema": BASELINE_SCHEMA, "repositories": payload_repositories}
    _write_json(output, payload)
    return 0


def _capture_from_args(
    args: argparse.Namespace, *, allow_uncovered_repositories: bool = False
) -> tuple[dict[str, Any], list[Path], Path]:
    baseline_path, baseline = _load_baseline(args.baseline)
    repository_ids = {repo["id"] for repo in baseline["repositories"]}
    scopes = _parse_paths(args.scope, repository_ids, "--scope")
    if not any(scopes.values()):
        raise InputError("at least one --scope is required")
    ignores = _parse_paths(args.ignore, repository_ids, "--ignore")
    payload = _capture_payload(
        baseline,
        scopes,
        ignores,
        allow_uncovered_repositories=allow_uncovered_repositories,
    )
    roots = [Path(repo["root"]) for repo in baseline["repositories"]]
    return payload, roots, baseline_path


def _reject_baseline_overwrite(output_value: str | None, baseline_path: Path) -> None:
    if not output_value:
        return
    output = Path(output_value).expanduser()
    if output.is_absolute() and output.resolve(strict=False) == baseline_path:
        raise InputError("capture/check output cannot overwrite the baseline")


def command_capture(args: argparse.Namespace) -> int:
    payload, roots, baseline_path = _capture_from_args(args)
    _reject_baseline_overwrite(args.output, baseline_path)
    _emit(payload, args.output, roots)
    return 0


def command_check(args: argparse.Namespace) -> int:
    if not SHA256_RE.fullmatch(args.expected):
        raise InputError("--expected must be a lowercase SHA-256 digest")
    payload, roots, baseline_path = _capture_from_args(
        args, allow_uncovered_repositories=True
    )
    _reject_baseline_overwrite(args.output, baseline_path)
    reasons: list[str] = []
    moved = [repo["id"] for repo in payload["repositories"] if repo["head_moved"]]
    if moved:
        reasons.append(f"HEAD moved: {', '.join(moved)}")
    if payload["unexpected_changes"]:
        reasons.append("new out-of-scope changes")
    if payload["uncovered_dirty_gitlinks"]:
        reasons.append(
            "uncovered dirty gitlink: " + ", ".join(payload["uncovered_dirty_gitlinks"])
        )
    if payload["uncovered_nested_repositories"]:
        reasons.append(
            "uncovered nested Git root: "
            + ", ".join(payload["uncovered_nested_repositories"])
        )
    if payload["candidate_sha256"] != args.expected:
        reasons.append("candidate drift")
    result = dict(payload)
    result["expected_sha256"] = args.expected
    result["status"] = "match" if not reasons else "drift"
    result["reasons"] = reasons
    _emit(result, args.output, roots)
    return 0 if not reasons else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    baseline = subparsers.add_parser("baseline", help="record pre-existing Git state")
    baseline.add_argument("--repo", action="append", default=[], metavar="ID=ROOT")
    baseline.add_argument("--output", required=True)
    baseline.set_defaults(handler=command_baseline)

    def add_capture_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--baseline", required=True)
        target.add_argument("--scope", action="append", default=[], metavar="ID:PATH")
        target.add_argument("--ignore", action="append", default=[], metavar="ID:PATH")
        target.add_argument("--output")

    capture = subparsers.add_parser("capture", help="capture the current candidate")
    add_capture_arguments(capture)
    capture.set_defaults(handler=command_capture)

    check = subparsers.add_parser("check", help="verify an existing candidate digest")
    add_capture_arguments(check)
    check.add_argument("--expected", required=True)
    check.set_defaults(handler=command_check)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except InputError as exc:
        print(f"quality-fingerprint: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"quality-fingerprint: filesystem error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
