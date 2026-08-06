#!/usr/bin/env python3
"""Inspect an easy-dev-spec Canonical Spec v1 without mutating repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlsplit


MANIFEST_BEGIN = "<!-- EDS:MANIFEST:BEGIN -->"
MANIFEST_END = "<!-- EDS:MANIFEST:END -->"
SECTION_BEGIN_RE = re.compile(r"^<!-- EDS:SECTION:BEGIN id=([a-z0-9][a-z0-9-]*) -->$")
SECTION_END_RE = re.compile(r"^<!-- EDS:SECTION:END id=([a-z0-9][a-z0-9-]*) -->$")
TASK_ID_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])R[1-9][0-9]*-T[1-9][0-9]*(?![A-Za-z0-9])"
)
SUPPORTED_SCHEMA = "easy-dev-spec/v1"
ID_PATTERNS = {
    "repository": re.compile(r"^R[1-9][0-9]*$"),
    "contract": re.compile(r"^C[1-9][0-9]*$"),
    "task": re.compile(r"^(R[1-9][0-9]*)-T[1-9][0-9]*$"),
    "change": re.compile(r"^F[1-9][0-9]*$"),
    "step": re.compile(r"^S[1-9][0-9]*$"),
    "test": re.compile(r"^T[1-9][0-9]*$"),
}
REMOTE_RE = re.compile(r"^(https?://|ssh://|git://|git@|file://)")


class CanonicalSpecError(ValueError):
    """Raised when a Canonical Spec cannot be parsed or safely consumed."""


class SelectionError(CanonicalSpecError):
    """Raised when repository or task selection is invalid."""


class RepositoryAmbiguityError(SelectionError):
    """Raised when repository identity requires an explicit user confirmation."""

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


@dataclass
class TaskSelection:
    selected_tasks: list[dict[str, Any]]
    selected_repo_ids: list[str]
    contract_ids: list[str] = field(default_factory=list)
    dependency_summaries: list[dict[str, Any]] = field(default_factory=list)
    dependency_gaps: list[dict[str, Any]] = field(default_factory=list)
    waves: list[list[str]] = field(default_factory=list)


def _require_list(manifest: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = manifest.get(key)
    if not isinstance(value, list):
        raise CanonicalSpecError(f"manifest.{key} must be an array")
    if not all(isinstance(item, dict) for item in value):
        raise CanonicalSpecError(f"manifest.{key} must contain objects")
    return value


def _index_unique(
    items: Iterable[dict[str, Any]],
    key: str,
    collection: str,
    id_kind: str | None = None,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        value = item.get(key)
        if not isinstance(value, str) or not value:
            raise CanonicalSpecError(f"{collection}.{key} must be a non-empty string")
        if id_kind is not None and not ID_PATTERNS[id_kind].fullmatch(value):
            raise CanonicalSpecError(f"invalid {key}: {value}")
        if value in result:
            raise CanonicalSpecError(f"duplicate {key}: {value}")
        result[value] = item
    return result


def _require_string(item: dict[str, Any], key: str, label: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CanonicalSpecError(f"{label}.{key} must be a non-empty string")
    return value


def _require_string_list(
    item: dict[str, Any], key: str, label: str, *, nonempty: bool = False
) -> list[str]:
    value = item.get(key)
    if not isinstance(value, list) or any(
        not isinstance(entry, str) or not entry for entry in value
    ):
        raise CanonicalSpecError(f"{label}.{key} must be an array of strings")
    if nonempty and not value:
        raise CanonicalSpecError(f"{label}.{key} must not be empty")
    if len(value) != len(set(value)):
        raise CanonicalSpecError(f"{label}.{key} contains duplicate values")
    return value


def _validate_repo_relative(path_value: Any, label: str) -> None:
    if (
        not isinstance(path_value, str)
        or not path_value
        or path_value != path_value.strip()
    ):
        raise CanonicalSpecError(f"{label} must be a non-empty repo-relative path")
    if any(ord(character) < 32 or ord(character) == 127 for character in path_value):
        raise CanonicalSpecError(f"{label} contains control characters")
    if (
        "\\" in path_value
        or path_value.startswith(("/", "~/", "//"))
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path_value)
    ):
        raise CanonicalSpecError(f"{label} must be a POSIX repo-relative path: {path_value}")
    raw_parts = path_value.split("/")
    path = PurePosixPath(path_value)
    if (
        any(part in {"", ".", ".."} for part in raw_parts)
        or path.is_absolute()
        or ".." in path.parts
        or path_value in {".", "./"}
    ):
        raise CanonicalSpecError(f"{label} must be repo-relative: {path_value}")


def _validate_manifest(manifest: dict[str, Any]) -> None:
    _require_string(manifest, "spec_id", "manifest")
    _require_string(manifest, "title", "manifest")
    revision = manifest.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise CanonicalSpecError("manifest.revision must be an integer greater than or equal to 1")
    status = manifest.get("status")
    if not isinstance(status, str) or status not in {"DRAFT", "BLOCKED", "READY"}:
        raise CanonicalSpecError(f"unsupported spec status: {status}")

    repositories = _require_list(manifest, "repositories")
    contracts = _require_list(manifest, "contracts")
    tasks = _require_list(manifest, "tasks")
    changes = _require_list(manifest, "changes")
    steps = _require_list(manifest, "steps")
    tests = _require_list(manifest, "tests")
    if not repositories:
        raise CanonicalSpecError("manifest.repositories must not be empty")
    if not tasks:
        raise CanonicalSpecError("manifest.tasks must not be empty")

    repo_by_id = _index_unique(repositories, "repo_id", "repositories", "repository")
    contract_by_id = _index_unique(contracts, "contract_id", "contracts", "contract")
    task_by_id = _index_unique(tasks, "task_id", "tasks", "task")
    change_by_id = _index_unique(changes, "change_id", "changes", "change")
    step_by_id = _index_unique(steps, "step_id", "steps", "step")
    test_by_id = _index_unique(tests, "test_id", "tests", "test")
    section_owners: dict[str, str] = {}

    def register_section(section_id: str, owner: str) -> None:
        if section_id in {
            "global-context",
            "integration-plan",
            "rollout-plan",
            "end-to-end-acceptance",
        }:
            raise CanonicalSpecError(f"{owner} uses reserved section_id: {section_id}")
        if section_id in section_owners:
            raise CanonicalSpecError(
                f"duplicate section_id {section_id}: {section_owners[section_id]} and {owner}"
            )
        section_owners[section_id] = owner

    for repo_id, repo in repo_by_id.items():
        _require_string(repo, "name", repo_id)
        remotes = _require_string_list(repo, "remote_urls", repo_id, nonempty=True)
        invalid_remotes = [remote for remote in remotes if not REMOTE_RE.match(remote)]
        if invalid_remotes:
            raise CanonicalSpecError(
                f"repository {repo_id} has invalid remote_urls: {', '.join(invalid_remotes)}"
            )
        _require_string(repo, "path_hint", repo_id)
        _require_string_list(repo, "tech_stack", repo_id, nonempty=True)
        baseline = repo.get("baseline")
        if not isinstance(baseline, dict):
            raise CanonicalSpecError(f"repository {repo_id} requires baseline")
        _require_string(baseline, "ref", f"{repo_id}.baseline")
        baseline_commit = baseline.get("commit")
        if not isinstance(baseline_commit, str) or not re.fullmatch(
            r"[0-9a-fA-F]{40}", baseline_commit
        ):
            raise CanonicalSpecError(f"repository {repo_id} requires a 40-character baseline commit")
        section_id = _require_string(repo, "section_id", repo_id)
        expected_section_id = f"repo-{repo_id.lower()}"
        if section_id != expected_section_id:
            raise CanonicalSpecError(
                f"repository {repo_id}.section_id must be {expected_section_id}"
            )
        register_section(section_id, f"repository {repo_id}")

    for contract_id, contract in contract_by_id.items():
        _require_string(contract, "name", contract_id)
        owner = _require_string(contract, "owner_task_id", contract_id)
        consumers = _require_string_list(
            contract, "consumer_task_ids", contract_id, nonempty=True
        )
        if owner not in task_by_id or any(consumer not in task_by_id for consumer in consumers):
            raise CanonicalSpecError(f"contract {contract_id} has invalid task references")
        if owner in consumers:
            raise CanonicalSpecError(f"contract {contract_id} owner cannot also be a consumer")
        section_id = _require_string(contract, "section_id", contract_id)
        expected_section_id = f"contract-{contract_id.lower()}"
        if section_id != expected_section_id:
            raise CanonicalSpecError(
                f"contract {contract_id}.section_id must be {expected_section_id}"
            )
        register_section(section_id, f"contract {contract_id}")

    for task_id, task in task_by_id.items():
        repo_id = task.get("repo_id")
        task_match = ID_PATTERNS["task"].fullmatch(task_id)
        if (
            not isinstance(repo_id, str)
            or repo_id not in repo_by_id
            or task_match is None
            or task_match.group(1) != repo_id
        ):
            raise CanonicalSpecError(f"task {task_id} has invalid repo_id: {repo_id}")
        _require_string(task, "title", task_id)
        task_status = task.get("status")
        if not isinstance(task_status, str) or task_status not in {
            "DRAFT",
            "BLOCKED",
            "READY",
        }:
            raise CanonicalSpecError(f"task {task_id} has invalid status")
        section_id = _require_string(task, "section_id", task_id)
        expected_section_id = f"task-{task_id.lower()}"
        if section_id != expected_section_id:
            raise CanonicalSpecError(f"task {task_id}.section_id must be {expected_section_id}")
        register_section(section_id, f"task {task_id}")
        depends_on = task.get("depends_on")
        if not isinstance(depends_on, list):
            raise CanonicalSpecError(f"task {task_id}.depends_on must be an array")
        seen_dependencies: set[str] = set()
        for dependency in depends_on:
            if not isinstance(dependency, dict):
                raise CanonicalSpecError(f"task {task_id} has an invalid dependency")
            dependency_id = dependency.get("task_id")
            dependency_type = dependency.get("type")
            if (
                not isinstance(dependency_id, str)
                or dependency_id not in task_by_id
                or dependency_id == task_id
            ):
                raise CanonicalSpecError(
                    f"task {task_id} references invalid dependency: {dependency_id}"
                )
            if not isinstance(dependency_type, str) or dependency_type not in {
                "hard",
                "contract",
                "integration",
            }:
                raise CanonicalSpecError(
                    f"task {task_id} has invalid dependency type: {dependency_type}"
                )
            evidence = dependency.get("required_evidence")
            if not isinstance(evidence, str) or not evidence.strip():
                raise CanonicalSpecError(
                    f"task {task_id} dependency {dependency_id} requires required_evidence"
                )
            if dependency_id in seen_dependencies:
                raise CanonicalSpecError(
                    f"task {task_id} has duplicate dependency: {dependency_id}"
                )
            seen_dependencies.add(dependency_id)
        _require_string_list(task, "change_ids", task_id, nonempty=True)
        _require_string_list(task, "step_ids", task_id, nonempty=True)
        _require_string_list(task, "test_ids", task_id, nonempty=True)

    if manifest["status"] == "READY":
        non_ready_tasks = [
            task_id
            for task_id, task in task_by_id.items()
            if task.get("status") != "READY"
        ]
        if non_ready_tasks:
            raise CanonicalSpecError(
                "READY spec contains non-READY tasks: " + ", ".join(non_ready_tasks)
            )

    ownership = (
        (change_by_id, "change_ids", "task_id"),
        (step_by_id, "step_ids", "task_id"),
        (test_by_id, "test_ids", "task_id"),
    )
    for task_id, task in task_by_id.items():
        for index, field_name, owner_field in ownership:
            ids = _require_string_list(task, field_name, task_id, nonempty=True)
            reverse_ids = sorted(
                item_id for item_id, item in index.items() if item.get(owner_field) == task_id
            )
            if sorted(ids) != reverse_ids:
                raise CanonicalSpecError(
                    f"task {task_id}.{field_name} does not match reverse ownership"
                )

    for change_id, change in change_by_id.items():
        task_id = change.get("task_id")
        repo_id = change.get("repo_id")
        if (
            not isinstance(task_id, str)
            or task_id not in task_by_id
            or not isinstance(repo_id, str)
            or repo_id != task_by_id[task_id].get("repo_id")
        ):
            raise CanonicalSpecError(f"change {change_id} has invalid task/repository ownership")
        _require_string(change, "module", change_id)
        action = change.get("action")
        if not isinstance(action, str) or action not in {"add", "modify", "delete"}:
            raise CanonicalSpecError(f"change {change_id} has invalid action")
        _validate_repo_relative(change.get("path"), f"change {change_id}.path")
        _require_string_list(change, "symbols", change_id, nonempty=True)

    for step_id, step in step_by_id.items():
        task_id = step.get("task_id")
        if not isinstance(task_id, str) or task_id not in task_by_id:
            raise CanonicalSpecError(f"step {step_id} has invalid task ownership")
        change_ids = _require_string_list(step, "change_ids", step_id, nonempty=True)
        test_ids = _require_string_list(step, "test_ids", step_id, nonempty=True)
        dependencies = _require_string_list(step, "depends_on_step_ids", step_id)
        for change_id in change_ids:
            if change_id not in change_by_id or change_by_id[change_id].get("task_id") != task_id:
                raise CanonicalSpecError(f"step {step_id} references invalid change: {change_id}")
        for test_id in test_ids:
            if test_id not in test_by_id or test_by_id[test_id].get("task_id") != task_id:
                raise CanonicalSpecError(f"step {step_id} references invalid test: {test_id}")
        for dependency_id in dependencies:
            if dependency_id not in step_by_id or dependency_id == step_id:
                raise CanonicalSpecError(
                    f"step {step_id} references invalid dependency: {dependency_id}"
                )
            if step_by_id[dependency_id].get("task_id") != task_id:
                raise CanonicalSpecError(
                    f"step {step_id} depends on a step outside task {task_id}: {dependency_id}"
                )

    for test_id, test in test_by_id.items():
        task_id = test.get("task_id")
        if not isinstance(task_id, str) or task_id not in task_by_id:
            raise CanonicalSpecError(f"test {test_id} has invalid task ownership")
        _validate_repo_relative(test.get("file"), f"test {test_id}.file")
        _require_string(test, "command", test_id)

    _assert_acyclic_tasks(task_by_id)
    _assert_acyclic_steps(step_by_id)


def _assert_acyclic_tasks(task_by_id: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise CanonicalSpecError(f"task dependency cycle detected at {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in task_by_id[task_id].get("depends_on", []):
            visit(dependency["task_id"])
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_by_id:
        visit(task_id)


def _assert_acyclic_steps(step_by_id: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise CanonicalSpecError(f"step dependency cycle detected at {step_id}")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency_id in step_by_id[step_id].get("depends_on_step_ids", []):
            visit(dependency_id)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in step_by_id:
        visit(step_id)


def parse_manifest(text: str) -> dict[str, object]:
    """Parse and validate the single Canonical Spec v1 manifest in *text*.

    A legacy document is represented by an empty dictionary. Any manifest markers
    that are present but malformed, duplicated, or unsupported raise an error.
    """

    begin_count = text.count(MANIFEST_BEGIN)
    end_count = text.count(MANIFEST_END)
    if begin_count == 0 and end_count == 0:
        return {}
    if begin_count != 1 or end_count != 1:
        raise CanonicalSpecError("a Canonical Spec must contain exactly one manifest boundary")
    begin = text.index(MANIFEST_BEGIN) + len(MANIFEST_BEGIN)
    end = text.index(MANIFEST_END)
    if end <= begin:
        raise CanonicalSpecError("manifest end boundary precedes its begin boundary")
    block = text[begin:end].strip()
    fenced = re.fullmatch(r"```json\s*\n([\s\S]*?)\n```", block)
    if fenced is None:
        raise CanonicalSpecError("manifest boundary must contain one json code fence")
    try:
        manifest = json.loads(fenced.group(1))
    except json.JSONDecodeError as exc:
        raise CanonicalSpecError(
            f"invalid manifest JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(manifest, dict):
        raise CanonicalSpecError("manifest JSON must be an object")
    if manifest.get("schema") != SUPPORTED_SCHEMA:
        raise CanonicalSpecError(f"unsupported schema: {manifest.get('schema')!r}")
    _validate_manifest(manifest)
    return manifest


def parse_sections(text: str) -> dict[str, str]:
    """Parse non-nested EDS section boundaries."""

    sections: dict[str, str] = {}
    active_id: str | None = None
    active_lines: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        begin_match = SECTION_BEGIN_RE.fullmatch(line.strip())
        end_match = SECTION_END_RE.fullmatch(line.strip())
        if begin_match:
            section_id = begin_match.group(1)
            if active_id is not None:
                raise CanonicalSpecError(
                    f"nested section {section_id} inside {active_id} is not allowed"
                )
            if section_id in sections:
                raise CanonicalSpecError(f"duplicate section id: {section_id}")
            active_id = section_id
            active_lines = []
            continue
        if end_match:
            section_id = end_match.group(1)
            if active_id is None:
                raise CanonicalSpecError(
                    f"section end without begin at line {line_number}: {section_id}"
                )
            if active_id != section_id:
                raise CanonicalSpecError(
                    f"section end {section_id} does not match active section {active_id}"
                )
            sections[section_id] = "\n".join(active_lines).strip()
            active_id = None
            active_lines = []
            continue
        if active_id is not None:
            active_lines.append(line)
    if active_id is not None:
        raise CanonicalSpecError(f"section is not closed: {active_id}")
    return sections


def _validate_section_structure(
    text: str, manifest: dict[str, Any], sections: dict[str, str]
) -> None:
    first_section = text.find("<!-- EDS:SECTION:BEGIN")
    if first_section != -1 and text.find(MANIFEST_BEGIN) > first_section:
        raise CanonicalSpecError("manifest must precede all EDS sections")
    expected = ["global-context"]
    expected.extend(contract["section_id"] for contract in _require_list(manifest, "contracts"))
    expected.extend(repository["section_id"] for repository in _require_list(manifest, "repositories"))
    expected.extend(task["section_id"] for task in _require_list(manifest, "tasks"))
    expected.extend(("integration-plan", "rollout-plan", "end-to-end-acceptance"))
    missing = [section_id for section_id in expected if section_id not in sections]
    if missing:
        raise CanonicalSpecError(f"missing required sections: {', '.join(missing)}")
    expected_set = set(expected)
    unexpected = [section_id for section_id in sections if section_id not in expected_set]
    if unexpected:
        raise CanonicalSpecError(f"unreferenced sections: {', '.join(unexpected)}")
    actual = list(sections)
    if actual != expected:
        raise CanonicalSpecError(
            "section order does not match Canonical Spec v1: " + ", ".join(actual)
        )


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


def _run_git(repo_root: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
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


def match_repository(
    manifest: dict[str, object], repo_root: Path
) -> RepositoryMatch:
    """Match a local Git repository to exactly one manifest repository."""

    root = _repository_root(repo_root)
    repositories = _require_list(manifest, "repositories")
    remote_urls = _remote_urls(root)
    normalized_local = {normalize_remote(url) for url in remote_urls if normalize_remote(url)}
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
        )
    if len(basename_matches) > 1:
        ids = ", ".join(repository["repo_id"] for repository in basename_matches)
        raise RepositoryAmbiguityError(
            f"repository basename is ambiguous: {ids}",
            _repository_candidate_metadata(basename_matches),
        )
    raise SelectionError("repository has no usable remote and its basename does not match the manifest")


def _confirmed_repository_match(
    manifest: dict[str, Any], repo_id: str, repo_root: Path
) -> RepositoryMatch:
    repository_by_id = _index_unique(
        _require_list(manifest, "repositories"), "repo_id", "repositories"
    )
    if repo_id not in repository_by_id:
        raise SelectionError(f"unknown repo_id: {repo_id}")
    repository = repository_by_id[repo_id]
    return RepositoryMatch(
        repo_id=repo_id,
        name=repository["name"],
        repo_root=str(_repository_root(repo_root)),
        method="user-confirmed",
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


def _dependency_contract_ids(
    manifest: dict[str, Any], selected_ids: set[str]
) -> list[str]:
    contract_ids: set[str] = set()
    for contract in _require_list(manifest, "contracts"):
        participants = {contract.get("owner_task_id"), *contract.get("consumer_task_ids", [])}
        if selected_ids & participants:
            contract_ids.add(contract["contract_id"])
    return sorted(contract_ids)


def _build_waves(
    selected_tasks: list[dict[str, Any]], selected_ids: set[str]
) -> list[list[str]]:
    remaining = {task["task_id"]: task for task in selected_tasks}
    completed: set[str] = set()
    waves: list[list[str]] = []
    while remaining:
        wave = sorted(
            task_id
            for task_id, task in remaining.items()
            if all(
                dependency["type"] != "hard"
                or dependency["task_id"] not in selected_ids
                or dependency["task_id"] in completed
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


def select_tasks(
    manifest: dict[str, object], repo_ids: list[str], task_ids: list[str]
) -> TaskSelection:
    """Select explicit tasks, or every READY task in the requested repositories."""

    repositories = _index_unique(_require_list(manifest, "repositories"), "repo_id", "repositories")
    unknown_repositories = sorted(set(repo_ids) - set(repositories))
    if unknown_repositories:
        raise SelectionError(f"unknown repo_id: {', '.join(unknown_repositories)}")

    task_by_id = _index_unique(_require_list(manifest, "tasks"), "task_id", "tasks")
    if task_ids:
        unknown_tasks = sorted(set(task_ids) - set(task_by_id))
        if unknown_tasks:
            raise SelectionError(f"unknown task_id: {', '.join(unknown_tasks)}")
        requested_task_ids = set(task_ids)
        selected_tasks = [
            task
            for task_id, task in task_by_id.items()
            if task_id in requested_task_ids
        ]
        unavailable_repositories = sorted(
            {task["repo_id"] for task in selected_tasks} - set(repo_ids)
        )
        if unavailable_repositories:
            raise SelectionError(
                "selected tasks require unresolved repository paths: "
                + ", ".join(unavailable_repositories)
            )
    else:
        selected_tasks = [
            task
            for task in task_by_id.values()
            if task.get("repo_id") in repo_ids and task.get("status") == "READY"
        ]
    if not selected_tasks:
        raise SelectionError("task selection is empty")

    selected_ids = {task["task_id"] for task in selected_tasks}
    contracts = _require_list(manifest, "contracts")
    dependency_summaries: list[dict[str, Any]] = []
    dependency_gaps: list[dict[str, Any]] = []
    for task in selected_tasks:
        for dependency in task.get("depends_on", []):
            dependency_task = task_by_id[dependency["task_id"]]
            summary = {
                "task_id": task["task_id"],
                "depends_on_task_id": dependency_task["task_id"],
                "repo_id": dependency_task["repo_id"],
                "title": dependency_task.get("title", ""),
                "status": dependency_task["status"],
                "type": dependency["type"],
                "required_evidence": dependency.get("required_evidence", ""),
                "selected": dependency_task["task_id"] in selected_ids,
            }
            dependency_summaries.append(summary)
            if dependency["type"] == "hard" and not summary["selected"]:
                dependency_gaps.append(summary)
            if dependency["type"] == "contract":
                matching_contract = any(
                    contract.get("owner_task_id") == dependency_task["task_id"]
                    and task["task_id"] in contract.get("consumer_task_ids", [])
                    for contract in contracts
                )
                if not matching_contract:
                    dependency_gaps.append({**summary, "reason": "contract-missing"})
                elif manifest.get("status") != "READY":
                    dependency_gaps.append({**summary, "reason": "spec-not-ready"})

    selected_repo_ids = sorted({task["repo_id"] for task in selected_tasks})
    return TaskSelection(
        selected_tasks=selected_tasks,
        selected_repo_ids=selected_repo_ids,
        contract_ids=_dependency_contract_ids(manifest, selected_ids),
        dependency_summaries=dependency_summaries,
        dependency_gaps=dependency_gaps,
        waves=_build_waves(selected_tasks, selected_ids),
    )


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


def _selected_manifest_summary(
    manifest: dict[str, Any], selection: TaskSelection, source_sha256: str
) -> dict[str, Any]:
    selected_ids = {task["task_id"] for task in selection.selected_tasks}
    selected_change_ids = {
        change_id for task in selection.selected_tasks for change_id in task.get("change_ids", [])
    }
    selected_step_ids = {
        step_id for task in selection.selected_tasks for step_id in task.get("step_ids", [])
    }
    selected_test_ids = {
        test_id for task in selection.selected_tasks for test_id in task.get("test_ids", [])
    }
    repositories = [
        repository
        for repository in _require_list(manifest, "repositories")
        if repository["repo_id"] in selection.selected_repo_ids
    ]
    contracts = [
        contract
        for contract in _require_list(manifest, "contracts")
        if contract["contract_id"] in selection.contract_ids
    ]
    changes = [
        change
        for change in _require_list(manifest, "changes")
        if change["change_id"] in selected_change_ids
    ]
    steps = [
        step
        for step in _require_list(manifest, "steps")
        if step["step_id"] in selected_step_ids
    ]
    tests = [
        test
        for test in _require_list(manifest, "tests")
        if test["test_id"] in selected_test_ids
    ]
    return {
        "schema": manifest["schema"],
        "spec_id": manifest["spec_id"],
        "revision": manifest.get("revision"),
        "status": manifest["status"],
        "title": manifest["title"],
        "source_sha256": source_sha256,
        "selected_repo_ids": selection.selected_repo_ids,
        "selected_task_ids": sorted(selected_ids),
        "selected_contract_ids": selection.contract_ids,
        "selected_change_ids": sorted(selected_change_ids),
        "selected_step_ids": sorted(selected_step_ids),
        "selected_test_ids": sorted(selected_test_ids),
        "repositories": repositories,
        "contracts": contracts,
        "tasks": selection.selected_tasks,
        "changes": changes,
        "steps": steps,
        "tests": tests,
        "waves": selection.waves,
    }


def _filter_integration(section: str, selection: TaskSelection) -> str:
    if not section:
        return ""
    relevant_task_ids = {task["task_id"] for task in selection.selected_tasks}
    relevant_task_ids.update(
        summary["depends_on_task_id"]
        for summary in selection.dependency_summaries
        if isinstance(summary.get("depends_on_task_id"), str)
    )
    selected_lines = []
    for line in section.splitlines():
        mentioned_task_ids = set(TASK_ID_TOKEN_RE.findall(line))
        if not mentioned_task_ids or mentioned_task_ids & relevant_task_ids:
            selected_lines.append(line)
    return "\n".join(selected_lines).strip()


def render_scope(text: str, selection: TaskSelection) -> str:
    """Render the deterministic consumption closure for a task selection."""

    manifest = parse_manifest(text)
    if not manifest:
        raise CanonicalSpecError("legacy Dev-Spec has no Canonical v1 consumption scope")
    sections = parse_sections(text)
    _validate_section_structure(text, manifest, sections)
    source_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    repository_by_id = _index_unique(
        _require_list(manifest, "repositories"), "repo_id", "repositories"
    )
    task_by_id = _index_unique(_require_list(manifest, "tasks"), "task_id", "tasks")
    contract_by_id = _index_unique(
        _require_list(manifest, "contracts"), "contract_id", "contracts"
    )
    blocks = [
        "# Canonical Spec Consumption Scope",
        "## Manifest Summary\n\n```json\n"
        + json.dumps(
            _selected_manifest_summary(manifest, selection, source_sha256),
            ensure_ascii=False,
            indent=2,
        )
        + "\n```",
        f"## Global Context\n\n{sections['global-context']}",
    ]
    for repo_id in selection.selected_repo_ids:
        section_id = repository_by_id[repo_id]["section_id"]
        blocks.append(f"## Repository {repo_id}\n\n{sections[section_id]}")
    for contract_id in selection.contract_ids:
        section_id = contract_by_id[contract_id]["section_id"]
        blocks.append(f"## Contract {contract_id}\n\n{sections[section_id]}")
    for task in selection.selected_tasks:
        task_id = task["task_id"]
        section_id = task_by_id[task_id]["section_id"]
        blocks.append(f"## Task {task_id}\n\n{sections[section_id]}")
    if selection.dependency_summaries:
        blocks.append(
            "## Direct Dependency Summaries\n\n```json\n"
            + json.dumps(selection.dependency_summaries, ensure_ascii=False, indent=2)
            + "\n```"
        )
    integration = _filter_integration(sections.get("integration-plan", ""), selection)
    if integration:
        blocks.append(f"## Related Integration Plan\n\n{integration}")
    return "\n\n".join(blocks).strip() + "\n"


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
    resolved_paths = {current_match.repo_id: Path(current_match.repo_root)}
    matches = {current_match.repo_id: current_match}
    for expected_repo_id, path in repo_paths.items():
        path_root = _repository_root(path)
        if expected_repo_id == current_match.repo_id:
            if path_root != Path(current_match.repo_root):
                raise SelectionError(
                    f"--repo-path {expected_repo_id} conflicts with --repo-root"
                )
            continue
        if path_root == Path(current_match.repo_root):
            raise SelectionError(
                f"--repo-path {expected_repo_id} conflicts with the confirmed current repository"
            )
        match = _match_repository_with_confirmation(manifest, path_root, expected_repo_id)
        resolved_paths[expected_repo_id] = Path(match.repo_root)
        matches[expected_repo_id] = match
    return resolved_paths, matches


def _scope_files_for_repo(
    manifest: dict[str, Any], selection: TaskSelection, repo_id: str
) -> list[str]:
    selected_change_ids = {
        change_id
        for task in selection.selected_tasks
        if task["repo_id"] == repo_id
        for change_id in task.get("change_ids", [])
    }
    selected_test_ids = {
        test_id
        for task in selection.selected_tasks
        if task["repo_id"] == repo_id
        for test_id in task.get("test_ids", [])
    }
    files = {
        change["path"]
        for change in _require_list(manifest, "changes")
        if change["change_id"] in selected_change_ids
    }
    files.update(
        test["file"]
        for test in _require_list(manifest, "tests")
        if test["test_id"] in selected_test_ids
    )
    return sorted(files)


def _legacy_result() -> dict[str, Any]:
    return {
        "protocol": "legacy",
        "spec_id": None,
        "spec_status": None,
        "source_sha256": None,
        "repositories": [],
        "selected_tasks": [],
        "dependency_gaps": [],
        "baseline_status": {},
        "scope_markdown": "",
        "scope_sha256": None,
    }


def _read_manifest_region(spec_path: Path) -> str:
    captured: list[str] = []
    begin_count = 0
    end_count = 0
    capturing = False
    with spec_path.open("r", encoding="utf-8") as source:
        for line in source:
            if MANIFEST_BEGIN in line:
                begin_count += line.count(MANIFEST_BEGIN)
                capturing = True
            if capturing:
                captured.append(line)
            if MANIFEST_END in line:
                end_count += line.count(MANIFEST_END)
                capturing = False
    if begin_count == 0 and end_count == 0:
        return ""
    if begin_count != 1 or end_count != 1:
        raise CanonicalSpecError("a Canonical Spec must contain exactly one manifest boundary")
    return "".join(captured)


def inspect_manifest(
    spec_path: Path,
    repo_root: Path,
    repo_path_values: list[str] | None = None,
) -> dict[str, Any]:
    """Inspect only the routing manifest without loading task sections."""

    manifest_text = _read_manifest_region(spec_path)
    manifest = parse_manifest(manifest_text)
    if not manifest:
        return {**_legacy_result(), "selection_required": False, "task_catalog": []}
    provided_repo_paths = _parse_repo_paths(repo_path_values or [])
    if len(provided_repo_paths) > 1:
        raise SelectionError(
            "--manifest-only accepts at most one --repo-path for current repository confirmation"
        )
    repository_match = _match_current_repository(
        manifest, repo_root, provided_repo_paths
    )
    if provided_repo_paths:
        if set(provided_repo_paths) != {repository_match.repo_id}:
            raise SelectionError(
                "--manifest-only --repo-path must confirm the current repository"
            )
        _paths_for_selection(manifest, repository_match, provided_repo_paths)
    change_by_id = _index_unique(
        _require_list(manifest, "changes"), "change_id", "changes"
    )
    test_by_id = _index_unique(_require_list(manifest, "tests"), "test_id", "tests")
    repository_by_id = _index_unique(
        _require_list(manifest, "repositories"), "repo_id", "repositories"
    )
    task_catalog = []
    for task in _require_list(manifest, "tasks"):
        change_paths = [
            change_by_id[change_id]["path"] for change_id in task.get("change_ids", [])
        ]
        test_files = [test_by_id[test_id]["file"] for test_id in task.get("test_ids", [])]
        if task["repo_id"] == repository_match.repo_id:
            baseline_status = classify_baseline(
                Path(repository_match.repo_root),
                repository_by_id[task["repo_id"]]["baseline"]["commit"],
                sorted({*change_paths, *test_files}),
            )
        else:
            baseline_status = "repo-unresolved"
        task_catalog.append(
            {
                "task_id": task["task_id"],
                "repo_id": task["repo_id"],
                "title": task["title"],
                "status": task["status"],
                "depends_on": task.get("depends_on", []),
                "key_deliverables": change_paths,
                "change_paths": change_paths,
                "baseline_status": baseline_status,
            }
        )
    return {
        "protocol": "canonical-v1",
        "spec_id": manifest["spec_id"],
        "spec_status": manifest["status"],
        "source_sha256": None,
        "repository_match": asdict(repository_match),
        "task_catalog": task_catalog,
        "selection_required": True,
        "repositories": [],
        "selected_tasks": [],
        "dependency_gaps": [],
        "baseline_status": {},
        "scope_markdown": "",
        "scope_sha256": None,
    }


def inspect_spec(
    spec_path: Path,
    repo_root: Path,
    task_ids: list[str],
    repo_path_values: list[str],
) -> dict[str, Any]:
    text = spec_path.read_text(encoding="utf-8")
    manifest = parse_manifest(text)
    if not manifest:
        return _legacy_result()
    _validate_section_structure(text, manifest, parse_sections(text))

    provided_repo_paths = _parse_repo_paths(repo_path_values)
    current_match = _match_current_repository(manifest, repo_root, provided_repo_paths)
    repo_paths, matches = _paths_for_selection(
        manifest, current_match, provided_repo_paths
    )
    required_repo_ids = {current_match.repo_id}
    if task_ids:
        task_by_id = _index_unique(_require_list(manifest, "tasks"), "task_id", "tasks")
        unknown = sorted(set(task_ids) - set(task_by_id))
        if unknown:
            raise SelectionError(f"unknown task_id: {', '.join(unknown)}")
        required_repo_ids = {task_by_id[task_id]["repo_id"] for task_id in task_ids}
        missing_paths = sorted(required_repo_ids - set(repo_paths))
        if missing_paths:
            raise SelectionError(
                "selected tasks require unresolved repository paths: " + ", ".join(missing_paths)
            )
    selection = select_tasks(manifest, sorted(required_repo_ids), task_ids)
    scope_markdown = render_scope(text, selection)
    scope_sha256 = hashlib.sha256(scope_markdown.encode("utf-8")).hexdigest()

    repository_by_id = _index_unique(
        _require_list(manifest, "repositories"), "repo_id", "repositories"
    )
    baseline_status: dict[str, str] = {}
    repository_results: list[dict[str, Any]] = []
    for repo_id in selection.selected_repo_ids:
        repository = repository_by_id[repo_id]
        path = repo_paths[repo_id]
        baseline = repository["baseline"]["commit"]
        status = classify_baseline(
            path, baseline, _scope_files_for_repo(manifest, selection, repo_id)
        )
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
        "protocol": "canonical-v1",
        "spec_id": manifest["spec_id"],
        "spec_status": manifest["status"],
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "repositories": repository_results,
        "selected_tasks": selection.selected_tasks,
        "dependency_gaps": selection.dependency_gaps,
        "dependency_summary": selection.dependency_summaries,
        "waves": selection.waves,
        "baseline_status": baseline_status,
        "scope_markdown": scope_markdown,
        "scope_sha256": scope_sha256,
    }


def _markdown_result(result: dict[str, Any]) -> str:
    if result["protocol"] == "legacy":
        return "# Dev-Spec Inspection\n\n- Protocol: `legacy`\n"
    if result.get("selection_required"):
        match = result["repository_match"]
        lines = [
            "# Dev-Spec Manifest Inspection",
            "",
            f"- Protocol: `{result['protocol']}`",
            f"- Spec: `{result['spec_id']}`",
            f"- Status: `{result['spec_status']}`",
            f"- Current repository: `{match['repo_id']}` via `{match['method']}`",
            "",
            "| Task | Repository | Status | Dependencies | Deliverables | Baseline | Title |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for task in result["task_catalog"]:
            dependencies = "<br>".join(
                f"{dependency['type']}:{dependency['task_id']}"
                for dependency in task["depends_on"]
            ) or "-"
            deliverables = "<br>".join(task["key_deliverables"]) or "-"
            cells = (
                task["task_id"],
                task["repo_id"],
                task["status"],
                dependencies,
                deliverables,
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
        f"- Spec: `{result['spec_id']}`",
        f"- Status: `{result['spec_status']}`",
        f"- Source SHA-256: `{result['source_sha256']}`",
        f"- Tasks: `{', '.join(task['task_id'] for task in result['selected_tasks'])}`",
        f"- Scope SHA-256: `{result['scope_sha256']}`",
        "",
        result["scope_markdown"].rstrip(),
        "",
    ]
    return "\n".join(lines)


def _error_result(exc: Exception) -> dict[str, Any]:
    result = {
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
        help="inspect routing metadata without selecting or loading task sections",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.manifest_only:
            if args.task_ids:
                raise CanonicalSpecError(
                    "--manifest-only cannot be combined with --task"
                )
            result = inspect_manifest(args.spec_path, args.repo_root, args.repo_paths)
        else:
            result = inspect_spec(
                args.spec_path,
                args.repo_root,
                args.task_ids,
                args.repo_paths,
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
