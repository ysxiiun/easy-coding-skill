#!/usr/bin/env python3
"""Inspect a Legacy or Canonical Dev-Spec for one or more local repositories.

The Canonical parser, validator, design digests, scope selection, and execution
projection are provided by the synchronized Easy Dev Spec protocol module.  This
consumer owns only local repository matching, task routing, and Git baseline
classification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

try:
    from easy_dev_spec_protocol import (
        SCHEMA,
        CanonicalSpecError,
        select_scope,
        validate_spec,
    )
except ModuleNotFoundError:  # pragma: no cover - package-style import
    from scripts.easy_dev_spec_protocol import (
        SCHEMA,
        CanonicalSpecError,
        select_scope,
        validate_spec,
    )


class SelectionError(ValueError):
    """Raised when a repository or task selection cannot be resolved safely."""


class RepositoryAmbiguityError(SelectionError):
    """Raised when a repository requires explicit user confirmation."""

    def __init__(self, message: str, candidates: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.candidates = candidates

    @property
    def candidate_repo_ids(self) -> set[str]:
        return {candidate["repo_id"] for candidate in self.candidates}


@dataclass(frozen=True)
class RepositoryMatch:
    repo_id: str
    name: str
    repo_root: str
    method: str
    normalized_remote: str | None = None
    path_hint_status: str = "missing"


def _require_list(manifest: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = manifest.get(key)
    if not isinstance(value, list):
        raise CanonicalSpecError(f"manifest.{key} 必须是数组")
    return value


def _index_unique(
    items: Iterable[dict[str, Any]], key: str, label: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        value = item.get(key)
        if not isinstance(value, str) or not value:
            raise CanonicalSpecError(f"{label}.{key} 必须是非空字符串")
        if value in result:
            raise CanonicalSpecError(f"{label}.{key} 重复：{value}")
        result[value] = item
    return result


def _sha256_json(value: Any) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validation_error(report: Any) -> CanonicalSpecError:
    details = "；".join(issue.message for issue in report.issues[:5])
    return CanonicalSpecError(f"Spec 校验失败：{details or '未知协议错误'}")


def _resolve_spec_path(spec_path: Path) -> Path:
    path = spec_path.expanduser().resolve()
    if not path.is_file():
        raise CanonicalSpecError(f"Spec 文件不存在：{path}")
    return path


def _validate_snapshot(spec_text: str) -> Any:
    # The upstream reader treats a newline-free string as a possible path.
    # Canonical documents are multiline, while a one-line Legacy document may
    # legitimately equal a filename in the current working directory.  Append
    # a sentinel newline only for protocol classification, then restore the
    # exact snapshot digests; never ask the validator to read the path again.
    if "\n" in spec_text:
        return validate_spec(spec_text)
    report = validate_spec(f"{spec_text}\n")
    if report.protocol == "legacy":
        digest = hashlib.sha256(spec_text.encode("utf-8")).hexdigest()
        report.document_sha256 = digest
        report.design_sha256 = digest
    return report


def normalize_remote(url: str) -> str:
    """Normalize SSH, HTTPS, and scp-like Git remotes to host/path."""

    value = url.strip()
    if not value:
        return ""
    host = ""
    path = ""
    if "://" in value:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        path = parsed.path
    else:
        scp_like = re.fullmatch(r"(?:[^@/]+@)?([^:/]+):(.+)", value)
        if scp_like:
            host, path = scp_like.groups()
            host = host.lower()
        else:
            without_auth = value.rsplit("@", 1)[-1]
            parts = without_auth.split("/", 1)
            if len(parts) == 2:
                host, path = parts[0].lower(), parts[1]
            else:
                return value.removesuffix(".git").rstrip("/")
    normalized_path = path.replace(":", "/").strip("/")
    if normalized_path.endswith(".git"):
        normalized_path = normalized_path[:-4]
    return "/".join(part for part in (host, normalized_path) if part).rstrip("/")


def _run_git(
    repo_root: Path, args: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", "-C", str(repo_root), *args],
            check=check,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SelectionError("git is required for repository and baseline inspection") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "git command failed"
        raise SelectionError(message) from exc


def _repository_root(repo_root: Path) -> Path:
    completed = _run_git(repo_root, ["rev-parse", "--show-toplevel"])
    return Path(completed.stdout.strip()).resolve()


def _remote_urls(repo_root: Path) -> list[str]:
    names = _run_git(repo_root, ["remote"]).stdout.splitlines()
    urls: list[str] = []
    for name in names:
        completed = _run_git(repo_root, ["remote", "get-url", "--all", name], check=False)
        if completed.returncode == 0:
            urls.extend(line.strip() for line in completed.stdout.splitlines() if line.strip())
    return urls


def _repository_candidate_metadata(
    repositories: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "repo_id": repository["repo_id"],
            "name": repository["name"],
            "remote_urls": repository.get("remote_urls", []),
            "path_hint": repository.get("path_hint"),
        }
        for repository in repositories
    ]


def _path_hint_status(repository: dict[str, Any], repo_root: Path) -> str:
    """Compare an advisory path hint with the resolved runtime worktree."""

    raw_hint = str(repository.get("path_hint") or "").strip()
    if not raw_hint:
        return "missing"
    hint = Path(raw_hint).expanduser()
    resolved_hint = (hint if hint.is_absolute() else repo_root / hint).resolve()
    return "matched" if resolved_hint == repo_root.resolve() else "different"


def match_repository(manifest: dict[str, Any], repo_root: Path) -> RepositoryMatch:
    """Match a local Git repository to exactly one manifest repository."""

    root = _repository_root(repo_root)
    repositories = _require_list(manifest, "repositories")
    local_remotes = _remote_urls(root)
    normalized_local = {normalize_remote(url) for url in local_remotes if normalize_remote(url)}
    if normalized_local:
        matches: list[tuple[dict[str, Any], str]] = []
        for repository in repositories:
            expected = {
                normalize_remote(url)
                for url in repository.get("remote_urls", [])
                if normalize_remote(url)
            }
            intersection = normalized_local & expected
            if intersection:
                matches.append((repository, sorted(intersection)[0]))
        if len(matches) == 1:
            repository, matched_remote = matches[0]
            return RepositoryMatch(
                repo_id=repository["repo_id"],
                name=repository["name"],
                repo_root=str(root),
                method="remote",
                normalized_remote=matched_remote,
                path_hint_status=_path_hint_status(repository, root),
            )
        if len(matches) > 1:
            ids = ", ".join(repository["repo_id"] for repository, _ in matches)
            raise RepositoryAmbiguityError(
                f"local remotes match multiple manifest repositories: {ids}",
                _repository_candidate_metadata(repository for repository, _ in matches),
            )
        raise SelectionError("local remotes do not match any manifest repository")

    basename_matches = [repo for repo in repositories if repo.get("name") == root.name]
    if len(basename_matches) == 1:
        repository = basename_matches[0]
        return RepositoryMatch(
            repo_id=repository["repo_id"],
            name=repository["name"],
            repo_root=str(root),
            method="basename",
            path_hint_status=_path_hint_status(repository, root),
        )
    if len(basename_matches) > 1:
        ids = ", ".join(repository["repo_id"] for repository in basename_matches)
        raise RepositoryAmbiguityError(
            f"repository basename is ambiguous: {ids}",
            _repository_candidate_metadata(basename_matches),
        )
    raise SelectionError(
        "repository has no usable remote and its basename does not match the manifest"
    )


def _confirmed_repository_match(
    manifest: dict[str, Any], repo_id: str, repo_root: Path
) -> RepositoryMatch:
    repository_by_id = _index_unique(
        _require_list(manifest, "repositories"), "repo_id", "repositories"
    )
    if repo_id not in repository_by_id:
        raise SelectionError(f"unknown repo_id: {repo_id}")
    repository = repository_by_id[repo_id]
    resolved_root = _repository_root(repo_root)
    return RepositoryMatch(
        repo_id=repo_id,
        name=repository["name"],
        repo_root=str(resolved_root),
        method="user-confirmed",
        path_hint_status=_path_hint_status(repository, resolved_root),
    )


def _match_repository_with_confirmation(
    manifest: dict[str, Any], repo_root: Path, confirmed_repo_id: str
) -> RepositoryMatch:
    try:
        match = match_repository(manifest, repo_root)
    except RepositoryAmbiguityError as exc:
        if confirmed_repo_id not in exc.candidate_repo_ids:
            raise SelectionError(
                f"confirmed repository {confirmed_repo_id} is not an ambiguity candidate"
            ) from exc
        return _confirmed_repository_match(manifest, confirmed_repo_id, repo_root)
    if match.repo_id != confirmed_repo_id:
        raise SelectionError(
            f"--repo-path {confirmed_repo_id} resolves to manifest repository {match.repo_id}"
        )
    return match


def _match_current_repository(
    manifest: dict[str, Any], repo_root: Path, repo_paths: dict[str, Path]
) -> RepositoryMatch:
    try:
        return match_repository(manifest, repo_root)
    except RepositoryAmbiguityError as exc:
        current_root = _repository_root(repo_root)
        confirmations = [
            repo_id
            for repo_id, path in repo_paths.items()
            if _repository_root(path) == current_root
        ]
        if len(confirmations) != 1 or confirmations[0] not in exc.candidate_repo_ids:
            raise
        return _confirmed_repository_match(manifest, confirmations[0], current_root)


def _parse_repo_paths(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SelectionError(f"--repo-path must use <repo-id>=<path>: {value}")
        repo_id, raw_path = value.split("=", 1)
        if not repo_id or not raw_path or repo_id in result:
            raise SelectionError(f"invalid or duplicate --repo-path: {value}")
        result[repo_id] = Path(raw_path).expanduser()
    return result


def _paths_for_selection(
    manifest: dict[str, Any], current_match: RepositoryMatch, repo_paths: dict[str, Path]
) -> tuple[dict[str, Path], dict[str, RepositoryMatch]]:
    current_root = Path(current_match.repo_root)
    resolved_paths = {current_match.repo_id: current_root}
    matches = {current_match.repo_id: current_match}
    for expected_repo_id, path in repo_paths.items():
        path_root = _repository_root(path)
        if expected_repo_id == current_match.repo_id:
            if path_root != current_root:
                raise SelectionError(
                    f"--repo-path {expected_repo_id} conflicts with --repo-root"
                )
            continue
        if path_root == current_root:
            raise SelectionError(
                f"--repo-path {expected_repo_id} conflicts with the confirmed current repository"
            )
        match = _match_repository_with_confirmation(manifest, path_root, expected_repo_id)
        resolved_paths[expected_repo_id] = Path(match.repo_root)
        matches[expected_repo_id] = match
    return resolved_paths, matches


def classify_baseline(repo_root: Path, baseline: str, files: list[str]) -> str:
    """Classify the selected file scope against a manifest baseline commit."""

    root = _repository_root(repo_root)
    head = _run_git(root, ["rev-parse", "HEAD"]).stdout.strip()
    available = _run_git(root, ["cat-file", "-e", f"{baseline}^{{commit}}"], check=False)
    if available.returncode != 0:
        return "baseline-unavailable"
    if files:
        working_tree = _run_git(
            root,
            [
                "--literal-pathspecs",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                *files,
            ],
        )
        if working_tree.stdout:
            return "scope-drifted"
    if head == baseline:
        return "exact"
    ancestor = _run_git(root, ["merge-base", "--is-ancestor", baseline, head], check=False)
    if ancestor.returncode != 0:
        return "scope-drifted"
    if not files:
        return "scope-unchanged"
    diff = _run_git(
        root,
        [
            "--literal-pathspecs",
            "diff",
            "--quiet",
            f"{baseline}..{head}",
            "--",
            *files,
        ],
        check=False,
    )
    if diff.returncode == 0:
        return "scope-unchanged"
    if diff.returncode == 1:
        return "scope-drifted"
    raise SelectionError(diff.stderr.strip() or "failed to compare baseline scope")


def _select_tasks(
    manifest: dict[str, Any], current_repo_id: str, task_ids: list[str]
) -> list[dict[str, Any]]:
    task_by_id = _index_unique(_require_list(manifest, "tasks"), "task_id", "tasks")
    if task_ids:
        unknown = sorted(set(task_ids) - set(task_by_id))
        if unknown:
            raise SelectionError(f"unknown task_id: {', '.join(unknown)}")
        requested = set(task_ids)
        selected = [task for task in task_by_id.values() if task["task_id"] in requested]
    else:
        selected = [
            task
            for task in task_by_id.values()
            if task.get("repo_id") == current_repo_id and task.get("status") == "READY"
        ]
    if not selected:
        raise SelectionError("task selection is empty")
    return selected


def _build_waves(selected_tasks: list[dict[str, Any]]) -> list[list[str]]:
    selected_ids = {task["task_id"] for task in selected_tasks}
    remaining = {task["task_id"]: task for task in selected_tasks}
    completed: set[str] = set()
    waves: list[list[str]] = []
    while remaining:
        wave = sorted(
            task_id
            for task_id, task in remaining.items()
            if all(
                dependency.get("type") != "hard"
                or dependency.get("task_id") not in selected_ids
                or dependency.get("task_id") in completed
                for dependency in task.get("depends_on", [])
            )
        )
        if not wave:
            raise CanonicalSpecError("selected task graph contains a dependency cycle")
        waves.append(wave)
        completed.update(wave)
        for task_id in wave:
            del remaining[task_id]
    return waves


def _group_task_ids(selected_tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for task in selected_tasks:
        grouped.setdefault(task["repo_id"], []).append(task["task_id"])
    return {repo_id: grouped[repo_id] for repo_id in sorted(grouped)}


def _merge_execution(scopes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    first = scopes[sorted(scopes)[0]]["execution"]
    tasks: dict[str, dict[str, Any]] = {}
    dependencies: dict[tuple[str, str, str], dict[str, Any]] = {}
    for repo_id in sorted(scopes):
        execution = scopes[repo_id]["execution"]
        for snapshot in execution.get("tasks", []):
            tasks.setdefault(snapshot["task_id"], snapshot)
        for dependency in execution.get("dependency_status", []):
            key = (
                dependency["source_task_id"],
                dependency["task_id"],
                dependency["type"],
            )
            dependencies.setdefault(key, dependency)
    return {
        "schema": first["schema"],
        "available": first["available"],
        "execution_revision": first["execution_revision"],
        "updated_at": first["updated_at"],
        "tasks": [tasks[task_id] for task_id in sorted(tasks)],
        "dependency_status": [dependencies[key] for key in sorted(dependencies)],
    }


def _select_scopes(
    spec_text: str,
    spec_path: Path,
    grouped_task_ids: dict[str, list[str]],
    *,
    include_markdown: bool = True,
) -> tuple[dict[str, dict[str, Any]], str, str, str]:
    scopes: dict[str, dict[str, Any]] = {}
    markdown_scopes: dict[str, str] = {}
    for repo_id in sorted(grouped_task_ids):
        scopes[repo_id] = select_scope(
            spec_text,
            repo_id,
            grouped_task_ids[repo_id],
            output_format="json",
        )
        scopes[repo_id]["source_path"] = str(spec_path)
        if include_markdown:
            markdown_scope = select_scope(
                spec_text,
                repo_id,
                grouped_task_ids[repo_id],
                output_format="markdown",
            )
            source_marker = '  "source_path": null,'
            if markdown_scope.count(source_marker) != 1:
                raise CanonicalSpecError("上游消费闭包缺少唯一 source_path locator")
            markdown_scopes[repo_id] = markdown_scope.replace(
                source_marker,
                f'  "source_path": {json.dumps(str(spec_path), ensure_ascii=False)},',
                1,
            )
    if len(scopes) == 1:
        repo_id = next(iter(scopes))
        return (
            scopes,
            markdown_scopes.get(repo_id, ""),
            scopes[repo_id]["design_scope_sha256"],
            scopes[repo_id]["execution_scope_sha256"],
        )
    scope_markdown = ""
    if include_markdown:
        scope_markdown = "\n\n".join(
            ["# Canonical Spec Composite Consumption Scope"]
            + [
                f"## Repository `{repo_id}`\n\n{markdown_scopes[repo_id].rstrip()}"
                for repo_id in sorted(markdown_scopes)
            ]
        ).rstrip() + "\n"
    design_scope_digest = _sha256_json(
        {repo_id: scopes[repo_id]["design_scope_sha256"] for repo_id in sorted(scopes)}
    )
    execution_scope_digest = _sha256_json(
        {repo_id: scopes[repo_id]["execution_scope_sha256"] for repo_id in sorted(scopes)}
    )
    return scopes, scope_markdown, design_scope_digest, execution_scope_digest


def _scope_files(scope: dict[str, Any]) -> list[str]:
    files = {
        change["path"]
        for change in scope.get("selected_changes", [])
        if isinstance(change.get("path"), str)
    }
    files.update(
        test["file"]
        for test in scope.get("selected_tests", [])
        if isinstance(test.get("file"), str)
    )
    return sorted(files)


def _execution_status_by_task(execution: dict[str, Any] | None) -> dict[str, str]:
    if execution is None:
        return {}
    return {
        snapshot["task_id"]: snapshot["status"]
        for snapshot in execution.get("tasks", [])
        if isinstance(snapshot, dict)
        and isinstance(snapshot.get("task_id"), str)
        and isinstance(snapshot.get("status"), str)
    }


def _full_execution_projection(
    report: Any, relevant_task_ids: set[str] | None = None
) -> dict[str, Any]:
    execution = report.execution
    if execution is None:
        return {
            "schema": "easy-dev-spec-execution/v1",
            "available": False,
            "execution_revision": None,
            "updated_at": None,
            "tasks": [],
            "dependency_status": [],
        }
    snapshots = sorted(execution.get("tasks", []), key=lambda item: item["task_id"])
    if relevant_task_ids is not None:
        snapshots = [
            snapshot
            for snapshot in snapshots
            if snapshot.get("task_id") in relevant_task_ids
        ]
    return {
        "schema": execution.get("schema", "easy-dev-spec-execution/v1"),
        "available": True,
        "execution_revision": execution.get("execution_revision"),
        "updated_at": execution.get("updated_at"),
        "tasks": snapshots,
        "dependency_status": [],
    }


def _legacy_result(
    spec_path: Path, report: Any, inspection_mode: str = "selected"
) -> dict[str, Any]:
    source_digest = report.document_sha256
    return {
        "inspection_mode": inspection_mode,
        "protocol": "legacy",
        "source_path": str(spec_path),
        "spec_id": None,
        "revision": None,
        "spec_status": None,
        "source_sha256": source_digest,
        "document_sha256": report.document_sha256,
        "design_sha256": report.design_sha256,
        "design_scope_sha256": None,
        "execution_scope_sha256": None,
        "execution": _full_execution_projection(report),
        "repositories": [],
        "selected_tasks": [],
        "dependency_gaps": [],
        "baseline_status": {},
        "scope_markdown": "",
        "repository_match": None,
    }


def inspect_manifest(
    spec_path: Path,
    repo_root: Path,
    repo_path_values: list[str] | None = None,
) -> dict[str, Any]:
    """Validate the Spec and return routing metadata without selecting a scope."""

    resolved_spec = _resolve_spec_path(spec_path)
    spec_text = resolved_spec.read_text(encoding="utf-8")
    report = _validate_snapshot(spec_text)
    if report.protocol == "legacy":
        return {
            **_legacy_result(resolved_spec, report, "manifest-only"),
            "selection_required": False,
            "task_catalog": [],
        }
    if not report.ok or report.manifest is None:
        raise _validation_error(report)
    manifest = report.manifest
    provided_repo_paths = _parse_repo_paths(repo_path_values or [])
    if len(provided_repo_paths) > 1:
        raise SelectionError(
            "--manifest-only accepts at most one --repo-path for current repository confirmation"
        )
    repository_match = _match_current_repository(manifest, repo_root, provided_repo_paths)
    if provided_repo_paths:
        if set(provided_repo_paths) != {repository_match.repo_id}:
            raise SelectionError(
                "--manifest-only --repo-path must confirm the current repository"
            )
        _paths_for_selection(manifest, repository_match, provided_repo_paths)

    execution_status = _execution_status_by_task(report.execution)
    current_tasks = [
        task
        for task in _require_list(manifest, "tasks")
        if task.get("repo_id") == repository_match.repo_id
    ]
    relevant_execution_task_ids = {
        str(task["task_id"]) for task in current_tasks
    } | {
        str(dependency["task_id"])
        for task in current_tasks
        for dependency in task.get("depends_on", [])
    }
    task_catalog: list[dict[str, Any]] = []
    for task in current_tasks:
        task_catalog.append(
            {
                "task_id": task["task_id"],
                "repo_id": task["repo_id"],
                "title": task["title"],
                "status": task["status"],
                "execution_status": (
                    execution_status.get(task["task_id"], "not_started")
                    if report.execution is not None
                    else None
                ),
                "depends_on": task.get("depends_on", []),
                "baseline_status": "not-inspected",
            }
        )
    return {
        "inspection_mode": "manifest-only",
        "protocol": "canonical-v1",
        "schema": manifest["schema"],
        "source_path": str(resolved_spec),
        "spec_id": manifest["spec_id"],
        "revision": manifest["revision"],
        "spec_status": manifest["status"],
        "source_sha256": report.document_sha256,
        "document_sha256": report.document_sha256,
        "design_sha256": report.design_sha256,
        "design_scope_sha256": None,
        "execution_scope_sha256": None,
        "execution": _full_execution_projection(report, relevant_execution_task_ids),
        "repository_match": asdict(repository_match),
        "task_catalog": task_catalog,
        "selection_required": True,
        "repositories": [],
        "selected_tasks": [],
        "dependency_gaps": [],
        "baseline_status": {},
        "scope_markdown": "",
    }


def inspect_spec(
    spec_path: Path,
    repo_root: Path,
    task_ids: list[str],
    repo_path_values: list[str],
    *,
    refresh_only: bool = False,
) -> dict[str, Any]:
    if refresh_only and not task_ids:
        raise SelectionError("--refresh-only requires at least one --task")
    resolved_spec = _resolve_spec_path(spec_path)
    spec_text = resolved_spec.read_text(encoding="utf-8")
    report = _validate_snapshot(spec_text)
    if report.protocol == "legacy":
        if refresh_only:
            raise CanonicalSpecError("--refresh-only only supports Canonical Spec v1")
        return _legacy_result(resolved_spec, report)
    if not report.ok or report.manifest is None:
        raise _validation_error(report)
    manifest = report.manifest
    if manifest.get("schema") != SCHEMA:
        raise CanonicalSpecError(f"不支持的 schema：{manifest.get('schema')}")

    provided_repo_paths = _parse_repo_paths(repo_path_values)
    current_match = _match_current_repository(manifest, repo_root, provided_repo_paths)
    repo_paths, matches = _paths_for_selection(manifest, current_match, provided_repo_paths)
    selected_tasks = _select_tasks(manifest, current_match.repo_id, task_ids)
    grouped_task_ids = _group_task_ids(selected_tasks)
    missing_paths = sorted(set(grouped_task_ids) - set(repo_paths))
    if missing_paths:
        raise SelectionError(
            "selected tasks require unresolved repository paths: " + ", ".join(missing_paths)
        )

    scopes, scope_markdown, design_scope_digest, execution_scope_digest = _select_scopes(
        spec_text,
        resolved_spec,
        grouped_task_ids,
        include_markdown=not refresh_only,
    )
    execution = _merge_execution(scopes)
    execution_status = _execution_status_by_task(execution)
    selected_with_execution = [
        {
            **task,
            "execution_status": (
                execution_status.get(task["task_id"], "not_started")
                if execution["available"]
                else None
            ),
        }
        for task in selected_tasks
    ]

    task_by_id = _index_unique(_require_list(manifest, "tasks"), "task_id", "tasks")
    selected_ids = {task["task_id"] for task in selected_tasks}
    dependency_summary: list[dict[str, Any]] = []
    dependency_gaps: list[dict[str, Any]] = []
    for dependency in execution.get("dependency_status", []):
        dependency_task = task_by_id[dependency["task_id"]]
        summary = {
            **dependency,
            "depends_on_task_id": dependency["task_id"],
            "repo_id": dependency_task["repo_id"],
            "title": dependency_task.get("title", ""),
            "design_status": dependency_task.get("status"),
            "execution_status": (
                execution_status.get(dependency["task_id"], "not_started")
                if execution["available"]
                else None
            ),
            "selected": dependency["task_id"] in selected_ids,
            "blocking_implementation": dependency["type"] in {"hard", "contract"},
            "blocking_completion": True,
        }
        dependency_summary.append(summary)
        if dependency["status"] != "satisfied":
            dependency_gaps.append(summary)

    repository_by_id = _index_unique(
        _require_list(manifest, "repositories"), "repo_id", "repositories"
    )
    if refresh_only:
        return {
            "inspection_mode": "refresh-only",
            "protocol": "canonical-v1",
            "schema": manifest["schema"],
            "source_path": str(resolved_spec),
            "spec_id": manifest["spec_id"],
            "revision": manifest["revision"],
            "spec_status": manifest["status"],
            "source_sha256": report.document_sha256,
            "document_sha256": report.document_sha256,
            "design_sha256": report.design_sha256,
            "design_scope_sha256": design_scope_digest,
            "execution_scope_sha256": execution_scope_digest,
            "execution": execution,
            "repository_match": asdict(current_match),
            "repositories": [
                {
                    "repo_id": repo_id,
                    "name": repository_by_id[repo_id]["name"],
                    "path": str(repo_paths[repo_id]),
                    "match": asdict(matches[repo_id]),
                    "baseline": repository_by_id[repo_id]["baseline"]["commit"],
                    "baseline_status": "not-inspected",
                }
                for repo_id in sorted(scopes)
            ],
            "selected_tasks": selected_with_execution,
            "dependency_gaps": dependency_gaps,
            "dependency_summary": dependency_summary,
            "waves": _build_waves(selected_tasks),
            "baseline_status": {},
            "scope_markdown": "",
        }
    baseline_status: dict[str, str] = {}
    repository_results: list[dict[str, Any]] = []
    for repo_id in sorted(scopes):
        repository = repository_by_id[repo_id]
        path = repo_paths[repo_id]
        baseline = repository["baseline"]["commit"]
        status = classify_baseline(path, baseline, _scope_files(scopes[repo_id]))
        head = _run_git(path, ["rev-parse", "HEAD"]).stdout.strip()
        baseline_status[repo_id] = status
        repository_results.append(
            {
                "repo_id": repo_id,
                "name": repository["name"],
                "path": str(path),
                "match": asdict(matches[repo_id]),
                "baseline": baseline,
                "head": head,
                "baseline_status": status,
            }
        )

    return {
        "inspection_mode": "selected",
        "protocol": "canonical-v1",
        "schema": manifest["schema"],
        "source_path": str(resolved_spec),
        "spec_id": manifest["spec_id"],
        "revision": manifest["revision"],
        "spec_status": manifest["status"],
        "source_sha256": report.document_sha256,
        "document_sha256": report.document_sha256,
        "design_sha256": report.design_sha256,
        "design_scope_sha256": design_scope_digest,
        "execution_scope_sha256": execution_scope_digest,
        "execution": execution,
        "repository_match": asdict(current_match),
        "repositories": repository_results,
        "selected_tasks": selected_with_execution,
        "dependency_gaps": dependency_gaps,
        "dependency_summary": dependency_summary,
        "waves": _build_waves(selected_tasks),
        "baseline_status": baseline_status,
        "scope_markdown": scope_markdown,
    }


def _markdown_result(result: dict[str, Any]) -> str:
    if result["protocol"] == "legacy":
        return (
            "# Dev-Spec Inspection\n\n"
            f"- Protocol: `legacy`\n- Source: `{result['source_path']}`\n"
        )
    if result.get("selection_required"):
        match = result["repository_match"]
        lines = [
            "# Dev-Spec Manifest Inspection",
            "",
            f"- Protocol: `{result['protocol']}`",
            f"- Inspection mode: `{result['inspection_mode']}`",
            f"- Spec: `{result['spec_id']}`",
            f"- Status: `{result['spec_status']}`",
            f"- Design SHA-256: `{result['design_sha256']}`",
            f"- Execution revision: `{result['execution']['execution_revision']}`",
            f"- Current repository: `{match['repo_id']}` via `{match['method']}`",
            f"- Path hint: `{match['path_hint_status']}` (advisory only)",
            "",
            "| Task | Repository | Design | Execution | Dependencies | Baseline | Title |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for task in result["task_catalog"]:
            dependencies = "<br>".join(
                f"{dependency['type']}:{dependency['task_id']}"
                for dependency in task["depends_on"]
            ) or "-"
            cells = (
                task["task_id"],
                task["repo_id"],
                task["status"],
                task["execution_status"] or "unavailable",
                dependencies,
                task["baseline_status"],
                task["title"],
            )
            escaped = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in cells]
            lines.append("| " + " | ".join(escaped) + " |")
        return "\n".join(lines) + "\n"
    lines = [
        "# Dev-Spec Inspection",
        "",
        f"- Protocol: `{result['protocol']}`",
        f"- Inspection mode: `{result['inspection_mode']}`",
        f"- Spec: `{result['spec_id']}`",
        f"- Status: `{result['spec_status']}`",
        f"- Source SHA-256: `{result['source_sha256']}`",
        f"- Document SHA-256: `{result['document_sha256']}`",
        f"- Design SHA-256: `{result['design_sha256']}`",
        f"- Design scope SHA-256: `{result['design_scope_sha256']}`",
        f"- Execution revision: `{result['execution']['execution_revision']}`",
        f"- Execution scope SHA-256: `{result['execution_scope_sha256']}`",
        f"- Tasks: `{', '.join(task['task_id'] for task in result['selected_tasks'])}`",
    ]
    if result["scope_markdown"]:
        lines.extend(("", result["scope_markdown"].rstrip(), ""))
    return "\n".join(lines)


def _error_result(exc: Exception) -> dict[str, Any]:
    result: dict[str, Any] = {
        "protocol": "error",
        "error_type": exc.__class__.__name__,
        "error": str(exc),
    }
    if isinstance(exc, RepositoryAmbiguityError):
        result["candidates"] = exc.candidates
    return result


def _markdown_error(exc: Exception) -> str:
    lines = ["# Dev-Spec Inspection Error", "", str(exc)]
    if isinstance(exc, RepositoryAmbiguityError):
        lines.extend(
            (
                "",
                "| Repository | Name | Remotes | Path hint |",
                "| --- | --- | --- | --- |",
            )
        )
        lines.extend(
            "| {repo_id} | {name} | {remotes} | {path_hint} |".format(
                repo_id=candidate["repo_id"],
                name=candidate["name"],
                remotes="<br>".join(candidate["remote_urls"]),
                path_hint=candidate.get("path_hint") or "",
            )
            for candidate in exc.candidates
        )
    return "\n".join(lines) + "\n"


class InspectorArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(
            json.dumps(
                {
                    "protocol": "error",
                    "error_type": "ArgumentError",
                    "error": message,
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = InspectorArgumentParser(description=__doc__)
    parser.add_argument("spec_path", type=Path)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--task", action="append", default=[], dest="task_ids")
    parser.add_argument("--repo-path", action="append", default=[], dest="repo_paths")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="inspect routing metadata without selecting a task scope",
    )
    parser.add_argument(
        "--refresh-only",
        action="store_true",
        help="refresh selected Canonical identity and execution without scope Markdown or baseline",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.manifest_only and args.refresh_only:
            raise CanonicalSpecError("--manifest-only cannot be combined with --refresh-only")
        if args.manifest_only:
            if args.task_ids:
                raise CanonicalSpecError("--manifest-only cannot be combined with --task")
            result = inspect_manifest(args.spec_path, args.repo_root, args.repo_paths)
        else:
            if args.refresh_only and not args.task_ids:
                raise CanonicalSpecError("--refresh-only requires at least one --task")
            result = inspect_spec(
                args.spec_path,
                args.repo_root,
                args.task_ids,
                args.repo_paths,
                refresh_only=args.refresh_only,
            )
    except SelectionError as exc:
        if args.format == "json":
            print(json.dumps(_error_result(exc), ensure_ascii=False))
        else:
            print(_markdown_error(exc), end="")
        return 3
    except (CanonicalSpecError, OSError, UnicodeError) as exc:
        if args.format == "json":
            print(json.dumps(_error_result(exc), ensure_ascii=False))
        else:
            print(_markdown_error(exc), end="")
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_markdown_result(result), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
