from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.dev_spec_execution import initialize_execution, record_dependency_status
from scripts.easy_dev_spec_protocol import (
    MANIFEST_BEGIN,
    MANIFEST_END,
    CanonicalSpecError,
    design_sha256,
    parse_manifest,
    select_scope,
    validate_spec,
)
from scripts.inspect_dev_spec import (
    RepositoryAmbiguityError,
    SelectionError,
    classify_baseline,
    inspect_manifest,
    inspect_spec,
    match_repository,
    normalize_remote,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inspect_dev_spec.py"
VALID_FIXTURE = ROOT / "tests" / "fixtures" / "easy-dev-spec-v1-final.md"
LEGACY_FIXTURE = ROOT / "tests" / "fixtures" / "legacy-dev-spec.md"


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def create_repo(parent: Path, repo_id: str, remote: str | None = None) -> tuple[Path, str]:
    name = "order-service" if repo_id == "R1" else "notification-service"
    repo = parent / name
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "tests@example.com")
    git(repo, "config", "user.name", "Easy Coding Tests")
    files = (
        [
            "order-domain/src/main/java/com/example/order/OrderEventPublisher.java",
            "order-domain/src/test/java/com/example/order/OrderEventPublisherTest.java",
            "order-api/src/main/java/com/example/order/api/DeliveryStatusController.java",
            "order-api/src/test/java/com/example/order/api/DeliveryStatusControllerTest.java",
        ]
        if repo_id == "R1"
        else [
            "notification-app/src/main/java/com/example/notification/OrderEventConsumer.java",
            "notification-app/src/test/java/com/example/notification/OrderEventConsumerTest.java",
        ]
    )
    for relative in files:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// fixture\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "initial")
    if remote:
        git(repo, "remote", "add", "origin", remote)
    return repo, git(repo, "rev-parse", "HEAD").stdout.strip()


def replace_manifest(text: str, manifest: dict) -> str:
    start = text.index(MANIFEST_BEGIN) + len(MANIFEST_BEGIN)
    end = text.index(MANIFEST_END)
    block = "\n```json\n" + json.dumps(manifest, ensure_ascii=False, indent=2) + "\n```\n"
    return text[:start] + block + text[end:]


def bind_baselines(text: str, baselines: dict[str, str]) -> str:
    manifest = parse_manifest(text)
    assert manifest is not None
    bound = text
    for repository in manifest["repositories"]:
        if repository["repo_id"] in baselines:
            bound = bound.replace(
                repository["baseline"]["commit"], baselines[repository["repo_id"]]
            )
    report = validate_spec(bound, require_ready=True)
    if not report.ok:
        raise AssertionError([issue.to_dict() for issue in report.issues])
    return bound


def sha256_json(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class InspectDevSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_text = VALID_FIXTURE.read_text(encoding="utf-8")
        self.manifest = parse_manifest(self.valid_text)
        assert self.manifest is not None

    def _environment(self, parent: Path, include_r2: bool = False) -> tuple[Path, Path, Path | None]:
        r1, r1_head = create_repo(
            parent, "R1", "git@example.com:demo/order-service.git"
        )
        r2: Path | None = None
        baselines = {"R1": r1_head}
        if include_r2:
            r2, r2_head = create_repo(
                parent,
                "R2",
                "https://example.com/demo/notification-service.git",
            )
            baselines["R2"] = r2_head
        spec = parent / "external-spec.md"
        spec.write_text(bind_baselines(self.valid_text, baselines), encoding="utf-8")
        return spec, r1, r2

    def test_fixture_is_current_strict_protocol_and_has_no_execution(self) -> None:
        report = validate_spec(VALID_FIXTURE, require_ready=True)
        self.assertTrue(report.ok, [issue.to_dict() for issue in report.issues])
        self.assertEqual("canonical-v1", report.protocol)
        self.assertIsNone(report.execution)
        self.assertIn("execution.missing", {warning.code for warning in report.warnings})

    def test_normalize_remote_variants(self) -> None:
        expected = "github.com/example/easy-coding"
        self.assertEqual(normalize_remote("git@github.com:example/easy-coding.git"), expected)
        self.assertEqual(
            normalize_remote("ssh://git@github.com/example/easy-coding.git"), expected
        )
        self.assertEqual(
            normalize_remote("https://token@github.com/example/easy-coding.git/"), expected
        )

    def test_match_repository_prefers_remote_and_falls_back_only_without_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            remote_repo, _ = create_repo(
                parent, "R1", "git@example.com:demo/order-service.git"
            )
            match = match_repository(self.manifest, remote_repo)
            self.assertEqual("R1", match.repo_id)
            self.assertEqual("remote", match.method)

        with tempfile.TemporaryDirectory() as directory:
            basename_repo, _ = create_repo(Path(directory), "R1")
            match = match_repository(self.manifest, basename_repo)
            self.assertEqual("R1", match.repo_id)
            self.assertEqual("basename", match.method)

    def test_mismatched_usable_remote_cannot_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, _ = create_repo(Path(directory), "R1", "git@example.com:other/repo.git")
            with self.assertRaisesRegex(SelectionError, "do not match"):
                inspect_spec(VALID_FIXTURE, repo, ["R1-T1"], [f"R1={repo}"])

    def test_manifest_catalog_separates_design_and_execution_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec, r1, _ = self._environment(Path(directory))
            result = inspect_manifest(spec, r1)
            r1_t1 = next(task for task in result["task_catalog"] if task["task_id"] == "R1-T1")
            self.assertEqual("READY", r1_t1["status"])
            self.assertIsNone(r1_t1["execution_status"])
            self.assertFalse(result["execution"]["available"])
            initialize_execution(spec, expected_design_sha256=result["design_sha256"])
            initialized = inspect_manifest(spec, r1)
            r1_t1 = next(
                task for task in initialized["task_catalog"] if task["task_id"] == "R1-T1"
            )
            self.assertEqual("READY", r1_t1["status"])
            self.assertEqual("not_started", r1_t1["execution_status"])

    def test_single_repo_scope_uses_upstream_digests_and_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec, r1, _ = self._environment(Path(directory))
            result = inspect_spec(spec, r1, ["R1-T1"], [])
            upstream = select_scope(spec, "R1", ["R1-T1"], output_format="json")
            self.assertEqual(upstream["design_sha256"], result["design_sha256"])
            self.assertEqual(
                upstream["design_scope_sha256"], result["design_scope_sha256"]
            )
            self.assertEqual(
                upstream["execution_scope_sha256"], result["execution_scope_sha256"]
            )
            self.assertEqual(upstream["execution"], result["execution"])
            self.assertEqual(str(spec.resolve()), result["source_path"])
            self.assertIn(str(spec.resolve()), result["scope_markdown"])
            self.assertEqual(result["source_sha256"], result["document_sha256"])
            self.assertNotIn("scope_sha256", result)

    def test_full_inspection_uses_one_immutable_spec_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec, r1, _ = self._environment(Path(directory))
            original_text = spec.read_text(encoding="utf-8")
            original_document_sha = hashlib.sha256(original_text.encode("utf-8")).hexdigest()
            original_design_sha = design_sha256(original_text)
            sources: list[object] = []

            def update_between_scope_calls(
                source: object,
                repo_id: str,
                task_ids: list[str],
                output_format: str = "markdown",
            ) -> object:
                sources.append(source)
                if len(sources) == 1:
                    initialize_execution(
                        spec, expected_design_sha256=original_design_sha
                    )
                return select_scope(
                    source, repo_id, task_ids, output_format=output_format
                )

            with patch(
                "scripts.inspect_dev_spec.select_scope",
                side_effect=update_between_scope_calls,
            ):
                result = inspect_spec(spec, r1, ["R1-T1"], [])

            self.assertTrue(all(isinstance(source, str) for source in sources))
            self.assertEqual(original_document_sha, result["document_sha256"])
            self.assertFalse(result["execution"]["available"])
            self.assertIn(str(spec.resolve()), result["scope_markdown"])
            current = select_scope(spec, "R1", ["R1-T1"], output_format="json")
            self.assertTrue(current["execution"]["available"])
            self.assertNotEqual(
                result["document_sha256"], current["document_sha256"]
            )

    def test_cross_repo_scope_is_sorted_and_composite_digest_is_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec, r1, r2 = self._environment(Path(directory), include_r2=True)
            assert r2 is not None
            result = inspect_spec(
                spec,
                r1,
                ["R2-T1", "R1-T1"],
                [f"R2={r2}"],
            )
            child_r1 = select_scope(spec, "R1", ["R1-T1"], output_format="json")
            child_r2 = select_scope(spec, "R2", ["R2-T1"], output_format="json")
            expected = sha256_json(
                {
                    "R1": child_r1["design_scope_sha256"],
                    "R2": child_r2["design_scope_sha256"],
                }
            )
            self.assertEqual(expected, result["design_scope_sha256"])
            self.assertEqual(["R1", "R2"], [repo["repo_id"] for repo in result["repositories"]])
            self.assertEqual(
                ["R1-T1", "R2-T1"], [task["task_id"] for task in result["selected_tasks"]]
            )
            self.assertLess(
                result["scope_markdown"].index("## Repository `R1`"),
                result["scope_markdown"].index("## Repository `R2`"),
            )

    def test_cross_repo_digest_is_independent_of_task_argument_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec, r1, r2 = self._environment(Path(directory), include_r2=True)
            assert r2 is not None
            first = inspect_spec(spec, r1, ["R1-T1", "R2-T1"], [f"R2={r2}"])
            second = inspect_spec(spec, r1, ["R2-T1", "R1-T1"], [f"R2={r2}"])
            self.assertEqual(first["design_scope_sha256"], second["design_scope_sha256"])
            self.assertEqual(first["execution_scope_sha256"], second["execution_scope_sha256"])
            self.assertEqual(first["scope_markdown"], second["scope_markdown"])

    def test_explicit_cross_repo_task_requires_confirmed_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec, r1, _ = self._environment(Path(directory))
            with self.assertRaisesRegex(SelectionError, "unresolved repository paths"):
                inspect_spec(spec, r1, ["R2-T1"], [])

    def test_execution_dependency_gates_have_distinct_blocking_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec, r1, _ = self._environment(Path(directory))
            digest = design_sha256(spec.read_text(encoding="utf-8"))
            initialize_execution(spec, expected_design_sha256=digest)
            result = inspect_spec(spec, r1, ["R1-T2"], [])
            by_type = {item["type"]: item for item in result["dependency_summary"]}
            self.assertEqual("pending", by_type["hard"]["status"])
            self.assertTrue(by_type["hard"]["blocking_implementation"])
            self.assertEqual("pending", by_type["integration"]["status"])
            self.assertFalse(by_type["integration"]["blocking_implementation"])
            self.assertTrue(by_type["integration"]["blocking_completion"])

            execution = record_dependency_status(
                spec,
                "R1-T2",
                "R1-T1",
                "satisfied",
                "外部构件证据。",
                "easy-coding",
                "Codex with Easy Coding",
                digest,
                0,
                evidence=[{"kind": "artifact", "status": "recorded", "ref": "api@1"}],
                run_id="run-inspector",
                idempotency_key="run-inspector:R1-T2:hard",
            )
            refreshed = inspect_spec(spec, r1, ["R1-T2"], [])
            by_type = {item["type"]: item for item in refreshed["dependency_summary"]}
            self.assertEqual("satisfied", by_type["hard"]["status"])
            self.assertEqual(execution["execution_revision"], refreshed["execution"]["execution_revision"])
            self.assertEqual(result["design_scope_sha256"], refreshed["design_scope_sha256"])
            self.assertNotEqual(
                result["execution_scope_sha256"], refreshed["execution_scope_sha256"]
            )

    def test_contract_dependency_comes_from_ready_frozen_design(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec, r1, r2 = self._environment(Path(directory), include_r2=True)
            assert r2 is not None
            initialize_execution(
                spec, expected_design_sha256=design_sha256(spec.read_text(encoding="utf-8"))
            )
            result = inspect_spec(spec, r2, ["R2-T1"], [])
            contract = result["dependency_summary"][0]
            self.assertEqual("contract", contract["type"])
            self.assertEqual("satisfied", contract["status"])
            self.assertEqual("design-ready", contract["basis"])
            self.assertEqual([], result["dependency_gaps"])

    def test_default_selection_retains_hard_dependency_waves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec, r1, _ = self._environment(Path(directory))
            result = inspect_spec(spec, r1, [], [])
            self.assertEqual(
                ["R1-T1", "R1-T2"], [task["task_id"] for task in result["selected_tasks"]]
            )
            self.assertEqual([["R1-T1"], ["R1-T2"]], result["waves"])

    def test_git_baseline_includes_test_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec, r1, _ = self._environment(Path(directory))
            exact = inspect_spec(spec, r1, ["R1-T1"], [])
            self.assertEqual("exact", exact["baseline_status"]["R1"])
            test_file = (
                r1
                / "order-domain/src/test/java/com/example/order/OrderEventPublisherTest.java"
            )
            test_file.write_text("// changed\n", encoding="utf-8")
            drifted = inspect_spec(spec, r1, ["R1-T1"], [])
            self.assertEqual("scope-drifted", drifted["baseline_status"]["R1"])

    def test_git_baseline_uses_literal_pathspecs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "literal-repo"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "tests@example.com")
            git(repo, "config", "user.name", "Easy Coding Tests")
            (repo / "literal[1].txt").write_text("selected\n", encoding="utf-8")
            (repo / "literal1.txt").write_text("decoy\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "initial")
            baseline = git(repo, "rev-parse", "HEAD").stdout.strip()
            (repo / "literal1.txt").write_text("decoy changed\n", encoding="utf-8")
            self.assertEqual("exact", classify_baseline(repo, baseline, ["literal[1].txt"]))
            (repo / "literal[1].txt").write_text("selected changed\n", encoding="utf-8")
            self.assertEqual(
                "scope-drifted", classify_baseline(repo, baseline, ["literal[1].txt"])
            )

    def test_ambiguous_repository_can_be_recovered_only_with_candidate_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            spec, r1, _ = self._environment(parent)
            text = spec.read_text(encoding="utf-8")
            spec.write_text(
                text.replace(
                    "https://example.com/demo/notification-service.git",
                    "git@example.com:demo/order-service.git",
                ),
                encoding="utf-8",
            )
            with self.assertRaises(RepositoryAmbiguityError):
                inspect_spec(spec, r1, ["R1-T1"], [])
            recovered = inspect_spec(spec, r1, ["R1-T1"], [f"R1={r1}"])
            self.assertEqual("user-confirmed", recovered["repositories"][0]["match"]["method"])

    def test_legacy_is_read_only_compatible_and_future_schema_is_rejected(self) -> None:
        legacy = inspect_spec(LEGACY_FIXTURE, ROOT, [], [])
        self.assertEqual("legacy", legacy["protocol"])
        with tempfile.TemporaryDirectory() as directory:
            future = Path(directory) / "future.md"
            future.write_text(
                self.valid_text.replace("easy-dev-spec/v1", "easy-dev-spec/v2", 1),
                encoding="utf-8",
            )
            with self.assertRaises(CanonicalSpecError):
                inspect_spec(future, ROOT, [], [])

    def test_single_line_legacy_content_is_not_reinterpreted_as_a_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            spec = Path(directory) / "single-line.md"
            spec.write_text("README.md", encoding="utf-8")
            result = inspect_spec(spec, ROOT, [], [])
            self.assertEqual("legacy", result["protocol"])
            self.assertEqual(
                hashlib.sha256(b"README.md").hexdigest(),
                result["document_sha256"],
            )

    def test_cli_accepts_relative_external_locator_and_preserves_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            spec, r1, _ = self._environment(parent)
            success = subprocess.run(
                [
                    "python3",
                    "-B",
                    str(SCRIPT),
                    spec.name,
                    "--repo-root",
                    str(r1),
                    "--task",
                    "R1-T1",
                ],
                cwd=parent,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, success.returncode, success.stderr or success.stdout)
            payload = json.loads(success.stdout)
            self.assertEqual(str(spec.resolve()), payload["source_path"])

            selection_error = subprocess.run(
                [
                    "python3",
                    "-B",
                    str(SCRIPT),
                    spec.name,
                    "--repo-root",
                    str(r1),
                    "--task",
                    "R9-T9",
                ],
                cwd=parent,
                capture_output=True,
                text=True,
            )
            self.assertEqual(3, selection_error.returncode)
            protocol_error = subprocess.run(
                [
                    "python3",
                    "-B",
                    str(SCRIPT),
                    "missing.md",
                    "--repo-root",
                    str(r1),
                ],
                cwd=parent,
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, protocol_error.returncode)


if __name__ == "__main__":
    unittest.main()
