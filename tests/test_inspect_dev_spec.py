from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.inspect_dev_spec import (
    CanonicalSpecError,
    RepositoryAmbiguityError,
    SelectionError,
    _filter_integration,
    _scope_files_for_repo,
    classify_baseline,
    inspect_spec,
    inspect_manifest,
    match_repository,
    normalize_remote,
    parse_manifest,
    parse_sections,
    render_scope,
    select_tasks,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inspect_dev_spec.py"
VALID_FIXTURE = ROOT / "tests" / "fixtures" / "canonical-v1-valid.md"
FINAL_PRODUCER_FIXTURE = ROOT / "tests" / "fixtures" / "easy-dev-spec-v1-final.md"
FINAL_PRODUCER_FIXTURE_SHA256 = (
    "57171e63a5d2149866999276e10f1aa829c5f92ed77f8db5d8419443002f8022"
)
LEGACY_FIXTURE = ROOT / "tests" / "fixtures" / "legacy-dev-spec.md"


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def create_repo(parent: Path, name: str, remote: str | None = None) -> tuple[Path, str]:
    repo = parent / name
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "tests@example.com")
    git(repo, "config", "user.name", "Easy Coding Tests")
    (repo / "scripts").mkdir()
    (repo / "downstream").mkdir()
    (repo / "tests").mkdir()
    (repo / "scripts" / "inspect_dev_spec.py").write_text("# parser\n", encoding="utf-8")
    (repo / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    (repo / "downstream" / "secret.py").write_text("# secret\n", encoding="utf-8")
    (repo / "tests" / "test_inspect_dev_spec.py").write_text(
        "# tests\n", encoding="utf-8"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "initial")
    if remote:
        git(repo, "remote", "add", "origin", remote)
    return repo, git(repo, "rev-parse", "HEAD").stdout.strip()


class CanonicalSpecInspectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_text = VALID_FIXTURE.read_text(encoding="utf-8")
        self.manifest = parse_manifest(self.valid_text)

    def test_parse_valid_manifest_and_sections(self) -> None:
        self.assertEqual(self.manifest["schema"], "easy-dev-spec/v1")
        self.assertEqual(self.manifest["spec_id"], "EDS-20260805-fixture")
        sections = parse_sections(self.valid_text)
        self.assertIn("global-context", sections)
        self.assertIn("task-r2-t1", sections)

    def test_final_easy_dev_spec_fixture_is_forward_compatible(self) -> None:
        text = FINAL_PRODUCER_FIXTURE.read_text(encoding="utf-8")
        source_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.assertEqual(source_sha256, FINAL_PRODUCER_FIXTURE_SHA256)
        manifest = parse_manifest(text)
        self.assertEqual(manifest["spec_id"], "order-notification-2026")
        selection = select_tasks(manifest, ["R1"], ["R1-T2"])
        scope = render_scope(text, selection)
        self.assertIn(f'"source_sha256": "{source_sha256}"', scope)
        self.assertIn("`R1-T1` contract", scope)
        self.assertIn("`R2-T1` integration", scope)
        self.assertNotIn("OrderEventPublisher.java", scope)
        self.assertNotIn("OrderEventConsumer.java", scope)
        self.assertNotIn("## Task R1-T1", scope)
        self.assertNotIn("## Task R2-T1", scope)

    def test_legacy_document_has_no_manifest(self) -> None:
        self.assertEqual(parse_manifest(LEGACY_FIXTURE.read_text(encoding="utf-8")), {})

    def test_duplicate_manifest_is_rejected(self) -> None:
        duplicated = self.valid_text + "\n" + self.valid_text
        with self.assertRaisesRegex(CanonicalSpecError, "exactly one manifest"):
            parse_manifest(duplicated)

    def test_invalid_json_is_rejected(self) -> None:
        invalid = self.valid_text.replace('"revision": 1,', '"revision": 1,,', 1)
        with self.assertRaisesRegex(CanonicalSpecError, "invalid manifest JSON"):
            parse_manifest(invalid)

    def test_manifest_requires_strict_json_fence_layout(self) -> None:
        inline = self.valid_text.replace(
            "```json\n{", "```json{", 1
        )
        with self.assertRaisesRegex(CanonicalSpecError, "one json code fence"):
            parse_manifest(inline)

        extra_fence = self.valid_text.replace(
            "<!-- EDS:MANIFEST:END -->",
            "```json\n{}\n```\n<!-- EDS:MANIFEST:END -->",
            1,
        )
        with self.assertRaises(CanonicalSpecError):
            parse_manifest(extra_fence)

    def test_future_schema_is_rejected(self) -> None:
        future = self.valid_text.replace("easy-dev-spec/v1", "easy-dev-spec/v2", 1)
        with self.assertRaisesRegex(CanonicalSpecError, "unsupported schema"):
            parse_manifest(future)

    def test_ready_spec_rejects_non_ready_task(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["tasks"][0]["status"] = "DRAFT"
        with self.assertRaisesRegex(CanonicalSpecError, "READY spec contains non-READY tasks"):
            parse_manifest(self._replace_manifest(manifest))

    def test_invalid_reference_type_is_a_canonical_error(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["contracts"][0]["consumer_task_ids"] = [{}]
        with self.assertRaisesRegex(CanonicalSpecError, "consumer_task_ids"):
            parse_manifest(self._replace_manifest(manifest))

    def test_invalid_enum_types_are_canonical_errors(self) -> None:
        mutations = (
            ("task status", lambda manifest: manifest["tasks"][0].update(status={})),
            (
                "dependency type",
                lambda manifest: manifest["tasks"][1]["depends_on"][0].update(type=[]),
            ),
            ("change action", lambda manifest: manifest["changes"][0].update(action={})),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                manifest = copy.deepcopy(self.manifest)
                mutate(manifest)
                with self.assertRaises(CanonicalSpecError):
                    parse_manifest(self._replace_manifest(manifest))

    def test_manifest_enforces_authoritative_v1_structure(self) -> None:
        mutations = (
            ("missing revision", lambda manifest: manifest.pop("revision")),
            ("boolean revision", lambda manifest: manifest.update(revision=True)),
            (
                "missing path hint",
                lambda manifest: manifest["repositories"][0].pop("path_hint"),
            ),
            (
                "missing baseline ref",
                lambda manifest: manifest["repositories"][0]["baseline"].pop("ref"),
            ),
            (
                "empty tech stack",
                lambda manifest: manifest["repositories"][0].update(tech_stack=[]),
            ),
            (
                "missing dependency evidence",
                lambda manifest: manifest["tasks"][1]["depends_on"][0].pop(
                    "required_evidence"
                ),
            ),
            (
                "missing change module",
                lambda manifest: manifest["changes"][0].pop("module"),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                manifest = copy.deepcopy(self.manifest)
                mutate(manifest)
                with self.assertRaises(CanonicalSpecError):
                    parse_manifest(self._replace_manifest(manifest))

    def test_manifest_rejects_invalid_ids_and_non_portable_paths(self) -> None:
        invalid_id = copy.deepcopy(self.manifest)
        invalid_id["tasks"][0]["change_ids"] = ["F0"]
        invalid_id["steps"][0]["change_ids"] = ["F0"]
        invalid_id["changes"][0]["change_id"] = "F0"
        with self.assertRaisesRegex(CanonicalSpecError, "invalid change_id"):
            parse_manifest(self._replace_manifest(invalid_id))

        for path in (
            "src\\main.py",
            "C:/src/main.py",
            "https://example.com/main.py",
            " src/main.py",
            "src//main.py",
            "src/./main.py",
        ):
            with self.subTest(path=path):
                manifest = copy.deepcopy(self.manifest)
                manifest["changes"][0]["path"] = path
                with self.assertRaises(CanonicalSpecError):
                    parse_manifest(self._replace_manifest(manifest))

    def test_nested_sections_are_rejected(self) -> None:
        nested = (
            "<!-- EDS:SECTION:BEGIN id=one -->\n"
            "<!-- EDS:SECTION:BEGIN id=two -->\n"
            "<!-- EDS:SECTION:END id=two -->\n"
            "<!-- EDS:SECTION:END id=one -->"
        )
        with self.assertRaisesRegex(CanonicalSpecError, "nested section"):
            parse_sections(nested)

    def test_normalize_remote_variants(self) -> None:
        expected = "github.com/example/easy-coding"
        self.assertEqual(normalize_remote("git@github.com:example/easy-coding.git"), expected)
        self.assertEqual(normalize_remote("ssh://git@github.com/example/easy-coding.git"), expected)
        self.assertEqual(normalize_remote("https://token@github.com/example/easy-coding.git/"), expected)

    def test_match_repository_by_unique_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, _ = create_repo(
                Path(temp), "different-name", "git@github.com:example/easy-coding.git"
            )
            match = match_repository(self.manifest, repo)
            self.assertEqual(match.repo_id, "R1")
            self.assertEqual(match.method, "remote")

    def test_match_repository_by_basename_when_remote_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, _ = create_repo(Path(temp), "easy-coding")
            match = match_repository(self.manifest, repo)
            self.assertEqual(match.repo_id, "R1")
            self.assertEqual(match.method, "basename")

    def test_usable_but_mismatched_remote_does_not_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, _ = create_repo(
                Path(temp), "easy-coding", "git@github.com:someone/other.git"
            )
            with self.assertRaisesRegex(SelectionError, "do not match"):
                match_repository(self.manifest, repo)

    def test_ambiguous_remote_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["repositories"][1]["remote_urls"] = manifest["repositories"][0][
            "remote_urls"
        ]
        with tempfile.TemporaryDirectory() as temp:
            repo, _ = create_repo(
                Path(temp), "easy-coding", "git@github.com:example/easy-coding.git"
            )
            with self.assertRaisesRegex(RepositoryAmbiguityError, "multiple") as raised:
                match_repository(manifest, repo)
            self.assertEqual(
                {candidate["repo_id"] for candidate in raised.exception.candidates},
                {"R1", "R2"},
            )

    def test_ambiguous_current_repository_accepts_confirmed_repo_path(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["repositories"][1]["remote_urls"] = manifest["repositories"][0][
            "remote_urls"
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo, baseline = create_repo(
                parent, "easy-coding", "git@github.com:example/easy-coding.git"
            )
            manifest["repositories"][0]["baseline"]["commit"] = baseline
            spec = parent / "spec.md"
            spec.write_text(self._replace_manifest(manifest), encoding="utf-8")
            result = inspect_spec(spec, repo, ["R1-T1"], [f"R1={repo}"])
            self.assertEqual(result["repositories"][0]["match"]["method"], "user-confirmed")

    def test_default_selection_uses_all_ready_tasks_for_repo(self) -> None:
        selection = select_tasks(self.manifest, ["R1"], [])
        self.assertEqual(
            [task["task_id"] for task in selection.selected_tasks], ["R1-T1", "R1-T2"]
        )
        self.assertEqual(selection.waves, [["R1-T1"], ["R1-T2"]])
        self.assertEqual(selection.dependency_gaps, [])

    def test_explicit_task_reports_unselected_hard_dependency(self) -> None:
        selection = select_tasks(self.manifest, ["R1"], ["R1-T2"])
        self.assertEqual(selection.dependency_gaps[0]["depends_on_task_id"], "R1-T1")
        integration = [
            item for item in selection.dependency_summaries if item["type"] == "integration"
        ]
        self.assertEqual(len(integration), 1)
        self.assertFalse(integration[0]["selected"])
        self.assertEqual(integration[0]["status"], "READY")

    def test_contract_dependency_is_satisfied_only_for_ready_spec(self) -> None:
        selection = select_tasks(self.manifest, ["R2"], ["R2-T1"])
        self.assertEqual(selection.dependency_gaps, [])
        draft = copy.deepcopy(self.manifest)
        draft["status"] = "DRAFT"
        draft_selection = select_tasks(draft, ["R2"], ["R2-T1"])
        self.assertEqual(draft_selection.dependency_gaps[0]["reason"], "spec-not-ready")

    def test_contract_dependency_does_not_serialize_waves(self) -> None:
        selection = select_tasks(
            self.manifest, ["R1", "R2"], ["R1-T1", "R2-T1"]
        )
        self.assertEqual(selection.waves, [["R1-T1", "R2-T1"]])

    def test_contract_dependency_requires_contract_definition(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["contracts"] = []
        selection = select_tasks(manifest, ["R2"], ["R2-T1"])
        self.assertEqual(selection.dependency_gaps[0]["reason"], "contract-missing")

    def test_explicit_cross_repo_task_requires_resolved_path(self) -> None:
        with self.assertRaisesRegex(SelectionError, "unresolved repository paths"):
            select_tasks(self.manifest, ["R1"], ["R2-T1"])

    def test_unknown_task_is_rejected(self) -> None:
        with self.assertRaisesRegex(SelectionError, "unknown task_id"):
            select_tasks(self.manifest, ["R1"], ["R1-T99"])

    def test_dependency_cycle_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["tasks"][0]["depends_on"] = [
            {"task_id": "R1-T2", "type": "hard", "required_evidence": "test"}
        ]
        text = self._replace_manifest(manifest)
        with self.assertRaisesRegex(CanonicalSpecError, "cycle"):
            parse_manifest(text)

    def test_step_cycle_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["tasks"][0]["step_ids"].append("S4")
        manifest["steps"][0]["depends_on_step_ids"] = ["S4"]
        manifest["steps"].append(
            {
                "step_id": "S4",
                "task_id": "R1-T1",
                "change_ids": ["F1"],
                "depends_on_step_ids": ["S1"],
                "test_ids": ["T1"],
            }
        )
        text = self._replace_manifest(manifest)
        with self.assertRaisesRegex(CanonicalSpecError, "step dependency cycle"):
            parse_manifest(text)

    def test_cross_task_step_dependency_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["steps"][1]["depends_on_step_ids"] = ["S1"]
        text = self._replace_manifest(manifest)
        with self.assertRaisesRegex(CanonicalSpecError, "outside task"):
            parse_manifest(text)

    def test_duplicate_section_id_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["tasks"][1]["section_id"] = manifest["tasks"][0]["section_id"]
        text = self._replace_manifest(manifest)
        with self.assertRaisesRegex(CanonicalSpecError, "section_id"):
            parse_manifest(text)

    def test_scope_excludes_unselected_repository_implementation(self) -> None:
        selection = select_tasks(self.manifest, ["R1"], ["R1-T1"])
        scope = render_scope(self.valid_text, selection)
        self.assertIn("scripts/inspect_dev_spec.py", scope)
        self.assertIn('"symbols": [', scope)
        self.assertIn("python3 -m unittest tests.test_inspect_dev_spec", scope)
        self.assertIn("scope_sha256", scope)
        self.assertIn("| 任务 | 对端 | 门禁 |", scope)
        self.assertIn("| R2-T1 | R1-T1 | C1 已冻结 |", scope)
        self.assertLess(scope.index("## Repository R1"), scope.index("## Contract C1"))
        self.assertNotIn("| R1-T2 | R2-T1 | scope digest 一致 |", scope)
        self.assertNotIn("downstream/secret.py", scope)
        self.assertNotIn("## Task R2-T1", scope)

    def test_scope_digest_is_deterministic(self) -> None:
        selection = select_tasks(self.manifest, ["R1"], ["R1-T1"])
        first = render_scope(self.valid_text, selection)
        second = render_scope(self.valid_text, selection)
        self.assertEqual(first, second)
        source_sha256 = hashlib.sha256(self.valid_text.encode("utf-8")).hexdigest()
        self.assertIn(f'"source_sha256": "{source_sha256}"', first)
        self.assertEqual(
            hashlib.sha256(first.encode("utf-8")).hexdigest(),
            hashlib.sha256(second.encode("utf-8")).hexdigest(),
        )

    def test_source_digest_invalidates_scope_when_unselected_source_changes(self) -> None:
        selection = select_tasks(self.manifest, ["R1"], ["R1-T1"])
        changed_text = self.valid_text.replace(
            "下游契约消费者。", "下游契约消费者，来源已修订。", 1
        )
        original_scope = render_scope(self.valid_text, selection)
        changed_scope = render_scope(changed_text, selection)
        self.assertNotIn("来源已修订", changed_scope)
        self.assertNotEqual(original_scope, changed_scope)
        self.assertNotEqual(
            hashlib.sha256(original_scope.encode("utf-8")).hexdigest(),
            hashlib.sha256(changed_scope.encode("utf-8")).hexdigest(),
        )

    def test_scope_digest_is_independent_of_task_argument_order(self) -> None:
        forward = select_tasks(
            self.manifest, ["R1", "R2"], ["R1-T1", "R2-T1"]
        )
        reversed_order = select_tasks(
            self.manifest, ["R1", "R2"], ["R2-T1", "R1-T1"]
        )
        forward_scope = render_scope(self.valid_text, forward)
        reversed_scope = render_scope(self.valid_text, reversed_order)
        self.assertEqual(forward_scope, reversed_scope)
        self.assertEqual(
            hashlib.sha256(forward_scope.encode("utf-8")).hexdigest(),
            hashlib.sha256(reversed_scope.encode("utf-8")).hexdigest(),
        )

    def test_integration_filter_uses_exact_task_ids(self) -> None:
        selection = select_tasks(self.manifest, ["R1"], ["R1-T1"])
        section = "\n".join(
            (
                "## Integration",
                "### R1-T10 downstream/secret.py",
                "| 任务 | 对端 | 门禁 |",
                "| --- | --- | --- |",
                "| R1-T1 | R2-T1 | selected |",
                "| R1-T10 | R2-T1 | unselected |",
            )
        )
        filtered = _filter_integration(section, selection)
        self.assertIn("## Integration", filtered)
        self.assertIn("| R1-T1 | R2-T1 | selected |", filtered)
        self.assertNotIn("### R1-T10 downstream/secret.py", filtered)
        self.assertNotIn("| R1-T10 | R2-T1 | unselected |", filtered)

    def test_integration_filter_includes_direct_dependency_rows(self) -> None:
        selection = select_tasks(self.manifest, ["R1"], ["R1-T2"])
        section = parse_sections(self.valid_text)["integration-plan"]
        filtered = _filter_integration(section, selection)
        self.assertIn("| R1-T2 | R2-T1 | scope digest 一致 |", filtered)
        self.assertIn("| R2-T1 | R1-T1 | C1 已冻结 |", filtered)

    def test_manifest_rejects_noncanonical_section_id(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["tasks"][0]["section_id"] = "custom-task-section"
        text = self._replace_manifest(manifest).replace(
            "id=task-r1-t1", "id=custom-task-section"
        )
        with self.assertRaisesRegex(CanonicalSpecError, "section_id must be task-r1-t1"):
            parse_manifest(text)

    def test_scope_rejects_noncanonical_section_order(self) -> None:
        contract = "<!-- EDS:SECTION:BEGIN id=contract-c1 -->"
        repository = "<!-- EDS:SECTION:BEGIN id=repo-r1 -->"
        contract_offset = self.valid_text.index(contract)
        repository_offset = self.valid_text.index(repository)
        contract_end = self.valid_text.index(
            "<!-- EDS:SECTION:END id=contract-c1 -->", contract_offset
        ) + len("<!-- EDS:SECTION:END id=contract-c1 -->")
        repository_end = self.valid_text.index(
            "<!-- EDS:SECTION:END id=repo-r1 -->", repository_offset
        ) + len("<!-- EDS:SECTION:END id=repo-r1 -->")
        contract_block = self.valid_text[contract_offset:contract_end]
        repository_block = self.valid_text[repository_offset:repository_end]
        reordered = (
            self.valid_text[:contract_offset]
            + repository_block
            + self.valid_text[contract_end:repository_offset]
            + contract_block
            + self.valid_text[repository_end:]
        )
        selection = select_tasks(self.manifest, ["R1"], ["R1-T1"])
        with self.assertRaisesRegex(CanonicalSpecError, "section order"):
            render_scope(reordered, selection)

    def test_missing_required_scope_section_is_rejected(self) -> None:
        selection = select_tasks(self.manifest, ["R1"], ["R1-T1"])
        text = self.valid_text.replace(
            "<!-- EDS:SECTION:BEGIN id=task-r1-t1 -->",
            "<!-- EDS:SECTION:BEGIN id=missing-task-r1-t1 -->",
        ).replace(
            "<!-- EDS:SECTION:END id=task-r1-t1 -->",
            "<!-- EDS:SECTION:END id=missing-task-r1-t1 -->",
        )
        with self.assertRaisesRegex(CanonicalSpecError, "missing required sections"):
            render_scope(text, selection)

    def test_baseline_classifications(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, baseline = create_repo(Path(temp), "baseline-repo")
            self.assertEqual(
                classify_baseline(repo, baseline, ["scripts/inspect_dev_spec.py"]), "exact"
            )

            (repo / "unrelated.txt").write_text("unrelated\n", encoding="utf-8")
            git(repo, "add", "unrelated.txt")
            git(repo, "commit", "-q", "-m", "unrelated")
            self.assertEqual(
                classify_baseline(repo, baseline, ["scripts/inspect_dev_spec.py"]),
                "scope-unchanged",
            )

            (repo / "scripts" / "inspect_dev_spec.py").write_text(
                "# changed\n", encoding="utf-8"
            )
            git(repo, "add", "scripts/inspect_dev_spec.py")
            git(repo, "commit", "-q", "-m", "scope change")
            self.assertEqual(
                classify_baseline(repo, baseline, ["scripts/inspect_dev_spec.py"]),
                "scope-drifted",
            )
            self.assertEqual(
                classify_baseline(repo, "f" * 40, ["scripts/inspect_dev_spec.py"]),
                "baseline-unavailable",
            )

    def test_selected_test_file_participates_in_baseline_scope(self) -> None:
        selection = select_tasks(self.manifest, ["R1"], ["R1-T1"])
        files = _scope_files_for_repo(self.manifest, selection, "R1")
        self.assertEqual(
            files,
            ["scripts/inspect_dev_spec.py", "tests/test_inspect_dev_spec.py"],
        )
        with tempfile.TemporaryDirectory() as temp:
            repo, baseline = create_repo(Path(temp), "baseline-repo")
            (repo / "tests" / "test_inspect_dev_spec.py").write_text(
                "# changed tests\n", encoding="utf-8"
            )
            git(repo, "add", "tests/test_inspect_dev_spec.py")
            git(repo, "commit", "-q", "-m", "test scope change")
            self.assertEqual(
                classify_baseline(repo, baseline, files),
                "scope-drifted",
            )

    def test_baseline_detects_selected_worktree_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, baseline = create_repo(Path(temp), "dirty-scope-repo")
            selected = ["scripts/inspect_dev_spec.py"]
            (repo / "unrelated.txt").write_text("untracked but unrelated\n", encoding="utf-8")
            self.assertEqual(classify_baseline(repo, baseline, selected), "exact")

            (repo / selected[0]).write_text("# unstaged\n", encoding="utf-8")
            self.assertEqual(classify_baseline(repo, baseline, selected), "scope-drifted")

            git(repo, "add", selected[0])
            self.assertEqual(classify_baseline(repo, baseline, selected), "scope-drifted")

    def test_baseline_detects_selected_untracked_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, baseline = create_repo(Path(temp), "untracked-scope-repo")
            planned = "new/module.py"
            (repo / "new").mkdir()
            (repo / planned).write_text("# already exists\n", encoding="utf-8")
            self.assertEqual(
                classify_baseline(repo, baseline, [planned]),
                "scope-drifted",
            )

    def test_baseline_treats_git_magic_pathspec_as_literal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, baseline = create_repo(Path(temp), "literal-pathspec-repo")
            (repo / ":(exclude)*").write_text("changed\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "add pathspec-like file")
            self.assertEqual(
                classify_baseline(repo, baseline, [":(exclude)*"]),
                "scope-drifted",
            )

    def test_diverged_history_is_scope_drifted_even_when_file_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, common = create_repo(Path(temp), "diverged-repo")
            git(repo, "checkout", "-q", "-b", "baseline-side")
            (repo / "baseline-only.txt").write_text("baseline\n", encoding="utf-8")
            git(repo, "add", "baseline-only.txt")
            git(repo, "commit", "-q", "-m", "baseline side")
            baseline = git(repo, "rev-parse", "HEAD").stdout.strip()

            git(repo, "checkout", "-q", "-b", "current-side", common)
            (repo / "current-only.txt").write_text("current\n", encoding="utf-8")
            git(repo, "add", "current-only.txt")
            git(repo, "commit", "-q", "-m", "current side")
            self.assertEqual(
                classify_baseline(repo, baseline, ["scripts/inspect_dev_spec.py"]),
                "scope-drifted",
            )

    def test_inspect_cross_repository_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo1, baseline1 = create_repo(
                parent, "easy-coding", "git@github.com:example/easy-coding.git"
            )
            repo2, baseline2 = create_repo(
                parent,
                "downstream-service",
                "https://github.com/example/downstream-service.git",
            )
            spec = parent / "spec.md"
            spec.write_text(
                self.valid_text.replace("0" * 40, baseline1, 1).replace("1" * 40, baseline2, 1),
                encoding="utf-8",
            )
            result = inspect_spec(
                spec,
                repo1,
                ["R2-T1"],
                [f"R2={repo2}"],
            )
            self.assertEqual(result["selected_tasks"][0]["task_id"], "R2-T1")
            self.assertEqual(result["baseline_status"], {"R2": "exact"})
            self.assertEqual(result["repositories"][0]["head"], baseline2)
            self.assertEqual(
                result["source_sha256"],
                hashlib.sha256(spec.read_bytes()).hexdigest(),
            )
            self.assertNotIn("scripts/inspect_dev_spec.py", result["scope_markdown"])

    def test_manifest_only_lists_tasks_without_loading_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo, baseline = create_repo(
                parent, "easy-coding", "git@github.com:example/easy-coding.git"
            )
            spec = parent / "spec.md"
            spec.write_text(
                self.valid_text.replace("0" * 40, baseline, 1), encoding="utf-8"
            )
            result = inspect_manifest(spec, repo)
            self.assertTrue(result["selection_required"])
            self.assertEqual(result["repository_match"]["repo_id"], "R1")
            self.assertEqual(result["task_catalog"][0]["task_id"], "R1-T1")
            self.assertEqual(
                result["task_catalog"][0]["key_deliverables"],
                ["scripts/inspect_dev_spec.py"],
            )
            self.assertEqual(result["task_catalog"][0]["baseline_status"], "exact")
            self.assertEqual(
                result["task_catalog"][2]["baseline_status"], "repo-unresolved"
            )
            self.assertEqual(result["scope_markdown"], "")
            self.assertNotIn("下游契约消费者", json.dumps(result, ensure_ascii=False))

    def test_manifest_only_repo_path_must_confirm_current_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo1, _ = create_repo(
                parent, "easy-coding", "git@github.com:example/easy-coding.git"
            )
            repo2, _ = create_repo(
                parent,
                "downstream-service",
                "https://github.com/example/downstream-service.git",
            )
            spec = parent / "spec.md"
            spec.write_text(self.valid_text, encoding="utf-8")
            with self.assertRaisesRegex(SelectionError, "confirm the current repository"):
                inspect_manifest(spec, repo1, [f"R2={repo2}"])

    def test_cli_manifest_only_rejects_task_arguments(self) -> None:
        completed = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                str(VALID_FIXTURE),
                "--repo-root",
                str(ROOT),
                "--manifest-only",
                "--task",
                "R1-T1",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("cannot be combined", json.loads(completed.stdout)["error"])

    def test_cli_ambiguous_repository_lists_candidates(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["repositories"][1]["remote_urls"] = manifest["repositories"][0][
            "remote_urls"
        ]
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo, _ = create_repo(
                parent, "easy-coding", "git@github.com:example/easy-coding.git"
            )
            spec = parent / "ambiguous.md"
            spec.write_text(self._replace_manifest(manifest), encoding="utf-8")
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(spec),
                    "--repo-root",
                    str(repo),
                    "--manifest-only",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            confirmed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(spec),
                    "--repo-root",
                    str(repo),
                    "--manifest-only",
                    "--repo-path",
                    f"R1={repo}",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 3)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["error_type"], "RepositoryAmbiguityError")
        self.assertEqual(
            {candidate["repo_id"] for candidate in payload["candidates"]},
            {"R1", "R2"},
        )
        self.assertEqual(completed.stderr, "")
        self.assertEqual(confirmed.returncode, 0)
        confirmed_payload = json.loads(confirmed.stdout)
        self.assertEqual(confirmed_payload["repository_match"]["method"], "user-confirmed")
        self.assertTrue(confirmed_payload["task_catalog"])
        self.assertEqual(confirmed.stderr, "")

    def test_cli_legacy_and_schema_errors(self) -> None:
        legacy = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                str(LEGACY_FIXTURE),
                "--repo-root",
                str(ROOT),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(legacy.returncode, 0)
        self.assertEqual(json.loads(legacy.stdout)["protocol"], "legacy")

        with tempfile.TemporaryDirectory() as temp:
            future_path = Path(temp) / "future.md"
            future_path.write_text(
                self.valid_text.replace("easy-dev-spec/v1", "easy-dev-spec/v2", 1),
                encoding="utf-8",
            )
            future = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(future_path),
                    "--repo-root",
                    str(ROOT),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(future.returncode, 2)
            self.assertEqual(json.loads(future.stdout)["protocol"], "error")

    def test_cli_argument_error_is_a_single_json_object(self) -> None:
        completed = subprocess.run(
            ["python3", str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["protocol"], "error")
        self.assertEqual(payload["error_type"], "ArgumentError")
        self.assertEqual(completed.stderr, "")

    def test_cli_invalid_reference_type_returns_two(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["contracts"][0]["consumer_task_ids"] = [{}]
        with tempfile.TemporaryDirectory() as temp:
            spec = Path(temp) / "invalid-reference.md"
            spec.write_text(self._replace_manifest(manifest), encoding="utf-8")
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(spec),
                    "--repo-root",
                    str(ROOT),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["error_type"], "CanonicalSpecError")
        self.assertEqual(completed.stderr, "")

    def test_cli_repository_mismatch_returns_three(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            repo, baseline = create_repo(
                parent, "easy-coding", "git@github.com:someone/other.git"
            )
            spec = parent / "spec.md"
            spec.write_text(
                self.valid_text.replace("0" * 40, baseline, 1), encoding="utf-8"
            )
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    str(spec),
                    "--repo-root",
                    str(repo),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 3)
            self.assertEqual(json.loads(completed.stdout)["error_type"], "SelectionError")

    def _replace_manifest(self, manifest: dict[str, object]) -> str:
        start = self.valid_text.index("```json") + len("```json")
        end = self.valid_text.index("```", start)
        return (
            self.valid_text[:start]
            + "\n"
            + json.dumps(manifest, ensure_ascii=False, indent=2)
            + "\n"
            + self.valid_text[end:]
        )


if __name__ == "__main__":
    unittest.main()
