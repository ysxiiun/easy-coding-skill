from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "quality_fingerprint.py"


class QualityFingerprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repo = self._new_repo("repo")
        self.baseline_path = self.base / "baseline.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git(self, repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return result.stdout.strip()

    def _new_repo(self, name: str) -> Path:
        repo = self.base / name
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        self._git(repo, "config", "user.email", "quality@example.test")
        self._git(repo, "config", "user.name", "Quality Test")
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        self._git(repo, "add", "--", "tracked.txt")
        self._git(repo, "commit", "-qm", "baseline")
        return repo

    def _run(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stderr or result.stdout)
        return result

    def _baseline(self, *repos: tuple[str, Path]) -> Path:
        args: list[str] = ["baseline"]
        for repo_id, root in repos or (("main", self.repo),):
            args.extend(["--repo", f"{repo_id}={root}"])
        args.extend(["--output", str(self.baseline_path)])
        self._run(*args)
        return self.baseline_path

    def _capture(
        self,
        *scopes: str,
        ignores: tuple[str, ...] = (),
        baseline: Path | None = None,
    ) -> dict:
        args = ["capture", "--baseline", str(baseline or self.baseline_path)]
        for scope in scopes or ("main:.",):
            args.extend(["--scope", scope])
        for ignore in ignores:
            args.extend(["--ignore", ignore])
        return json.loads(self._run(*args).stdout)

    def _check(
        self,
        expected_sha: str,
        *scopes: str,
        ignores: tuple[str, ...] = (),
        baseline: Path | None = None,
        exit_code: int = 0,
    ) -> dict:
        args = [
            "check",
            "--baseline",
            str(baseline or self.baseline_path),
            "--expected",
            expected_sha,
        ]
        for scope in scopes or ("main:.",):
            args.extend(["--scope", scope])
        for ignore in ignores:
            args.extend(["--ignore", ignore])
        return json.loads(self._run(*args, expected=exit_code).stdout)

    def test_clean_candidate_is_stable(self) -> None:
        self._baseline()
        first = self._capture()
        second = self._capture()
        self.assertEqual("easy-coding-quality-fingerprint/v1", first["schema"])
        self.assertEqual([], first["changes"])
        self.assertEqual(first["candidate_sha256"], second["candidate_sha256"])
        self.assertEqual("match", self._check(first["candidate_sha256"])["status"])

    def test_staged_unstaged_untracked_and_deleted_are_fingerprinted(self) -> None:
        (self.repo / "staged.txt").write_text("staged\n", encoding="utf-8")
        self._git(self.repo, "add", "--", "staged.txt")
        (self.repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
        (self.repo / "untracked.txt").write_text("new\n", encoding="utf-8")
        (self.repo / "deleted.txt").write_text("delete me\n", encoding="utf-8")
        self._git(self.repo, "add", "--", "deleted.txt")
        self._git(self.repo, "commit", "-qm", "add deleted fixture")
        self._baseline()

        (self.repo / "staged.txt").write_text("staged again\n", encoding="utf-8")
        self._git(self.repo, "add", "--", "staged.txt")
        (self.repo / "tracked.txt").write_text("changed again\n", encoding="utf-8")
        (self.repo / "untracked.txt").write_text("new again\n", encoding="utf-8")
        (self.repo / "deleted.txt").unlink()

        payload = self._capture()
        changes = {item["path"]: item for item in payload["changes"]}
        self.assertEqual(
            {"deleted.txt", "staged.txt", "tracked.txt", "untracked.txt"}, set(changes)
        )
        self.assertIn("staged", changes["staged.txt"]["after"]["categories"])
        self.assertIn("unstaged", changes["tracked.txt"]["after"]["categories"])
        self.assertIn("untracked", changes["untracked.txt"]["after"]["categories"])
        self.assertIsNone(changes["deleted.txt"]["after"]["worktree"])

    def test_unchanged_preexisting_dirty_state_does_not_block(self) -> None:
        (self.repo / "tracked.txt").write_text("preexisting\n", encoding="utf-8")
        (self.repo / "old-untracked.txt").write_text("old\n", encoding="utf-8")
        self._baseline()
        clean_delta = self._capture()
        self.assertEqual([], clean_delta["changes"])

        (self.repo / "tracked.txt").write_text("implementation\n", encoding="utf-8")
        changed = self._capture()
        self.assertEqual(["tracked.txt"], [item["path"] for item in changed["changes"]])
        self.assertEqual("match", self._check(changed["candidate_sha256"])["status"])

    def test_new_out_of_scope_change_returns_exit_three(self) -> None:
        self._baseline()
        (self.repo / "src").mkdir()
        (self.repo / "src" / "allowed.py").write_text("ok\n", encoding="utf-8")
        candidate = self._capture("main:src")
        (self.repo / "outside.txt").write_text("drift\n", encoding="utf-8")
        result = self._check(candidate["candidate_sha256"], "main:src", exit_code=3)
        self.assertIn("new out-of-scope changes", result["reasons"])

    def test_head_movement_returns_exit_three(self) -> None:
        self._baseline()
        candidate = self._capture()
        (self.repo / "commit.txt").write_text("head\n", encoding="utf-8")
        self._git(self.repo, "add", "--", "commit.txt")
        self._git(self.repo, "commit", "-qm", "move head")
        result = self._check(candidate["candidate_sha256"], exit_code=3)
        self.assertIn("HEAD moved: main", result["reasons"])

    def test_candidate_drift_returns_exit_three(self) -> None:
        self._baseline()
        (self.repo / "tracked.txt").write_text("one\n", encoding="utf-8")
        candidate = self._capture()
        (self.repo / "tracked.txt").write_text("two\n", encoding="utf-8")
        result = self._check(candidate["candidate_sha256"], exit_code=3)
        self.assertIn("candidate drift", result["reasons"])

    def test_ignore_excludes_machine_writeback(self) -> None:
        self._baseline()
        (self.repo / "code.py").write_text("candidate\n", encoding="utf-8")
        (self.repo / "canonical.md").write_text("execution\n", encoding="utf-8")
        payload = self._capture("main:code.py", ignores=("main:canonical.md",))
        self.assertEqual(["code.py"], [item["path"] for item in payload["changes"]])
        self.assertEqual(["canonical.md"], [item["path"] for item in payload["ignored_changes"]])
        self.assertEqual([], payload["unexpected_changes"])

    def test_check_binds_scope_and_ignore_arguments(self) -> None:
        self._baseline()
        (self.repo / "code.py").write_text("candidate\n", encoding="utf-8")
        candidate = self._capture("main:code.py")
        result = self._check(
            candidate["candidate_sha256"],
            "main:.",
            ignores=("main:hidden.txt",),
            exit_code=3,
        )
        self.assertIn("candidate drift", result["reasons"])

    def test_path_escape_and_unknown_repo_exit_two(self) -> None:
        self._baseline()
        self._run(
            "capture",
            "--baseline",
            str(self.baseline_path),
            "--scope",
            "main:../escape",
            expected=2,
        )
        self._run(
            "capture",
            "--baseline",
            str(self.baseline_path),
            "--scope",
            "main:.",
            "--ignore",
            "main:.",
            expected=2,
        )
        self._run(
            "capture",
            "--baseline",
            str(self.baseline_path),
            "--scope",
            "missing:tracked.txt",
            expected=2,
        )

    def test_duplicate_repository_root_exit_two(self) -> None:
        self._run(
            "baseline",
            "--repo",
            f"one={self.repo}",
            "--repo",
            f"two={self.repo}",
            "--output",
            str(self.baseline_path),
            expected=2,
        )

    def test_baseline_output_inside_repository_exit_two(self) -> None:
        self._run(
            "baseline",
            "--repo",
            f"main={self.repo}",
            "--output",
            str(self.repo / "baseline.json"),
            expected=2,
        )

    def test_missing_input_and_output_paths_exit_two_without_traceback(self) -> None:
        missing_repo = self.base / "missing-repo"
        missing_parent = self.base / "missing-parent"
        missing_baseline = self.base / "missing-baseline.json"
        commands = (
            (
                "baseline",
                "--repo",
                f"main={missing_repo}",
                "--output",
                str(self.baseline_path),
            ),
            (
                "baseline",
                "--repo",
                f"main={self.repo}",
                "--output",
                str(missing_parent / "baseline.json"),
            ),
            (
                "capture",
                "--baseline",
                str(missing_baseline),
                "--scope",
                "main:.",
            ),
            (
                "check",
                "--baseline",
                str(missing_baseline),
                "--scope",
                "main:.",
                "--expected",
                "0" * 64,
            ),
        )
        for command in commands:
            with self.subTest(command=command[0:2]):
                result = self._run(*command, expected=2)
                self.assertNotIn("Traceback", result.stderr)

        self._baseline()
        result = self._run(
            "capture",
            "--baseline",
            str(self.baseline_path),
            "--scope",
            "main:.",
            "--output",
            str(missing_parent / "candidate.json"),
            expected=2,
        )
        self.assertNotIn("Traceback", result.stderr)

    def test_capture_and_check_cannot_overwrite_baseline(self) -> None:
        self._baseline()
        original = self.baseline_path.read_text(encoding="utf-8")
        for command in ("capture", "check"):
            args = [
                command,
                "--baseline",
                str(self.baseline_path),
                "--scope",
                "main:.",
                "--output",
                str(self.baseline_path),
            ]
            if command == "check":
                args.extend(["--expected", "0" * 64])
            with self.subTest(command=command):
                self._run(*args, expected=2)
                self.assertEqual(original, self.baseline_path.read_text(encoding="utf-8"))

    def test_malformed_baseline_content_exits_two(self) -> None:
        self._baseline()
        original = json.loads(self.baseline_path.read_text(encoding="utf-8"))
        corruptions = (
            lambda payload: payload.update(unexpected="field"),
            lambda payload: payload["repositories"][0].update(head="not-a-git-object"),
            lambda payload: payload["repositories"][0].update(root=""),
            lambda payload: payload["repositories"][0].update(root="/invalid\0root"),
            lambda payload: payload["repositories"][0]["dirty"].update(
                {"../escape": {"categories": ["untracked"], "index": [], "worktree": None}}
            ),
            lambda payload: payload["repositories"][0]["dirty"].update(
                {".": {"categories": ["untracked"], "index": [], "worktree": None}}
            ),
            lambda payload: payload["repositories"][0]["dirty"].update(
                {"broken.txt": ["not", "a", "state"]}
            ),
            lambda payload: payload["repositories"][0]["dirty"].update(
                {
                    "bad-kind": {
                        "categories": ["untracked"],
                        "index": [],
                        "worktree": {"kind": [], "mode": "100644"},
                    }
                }
            ),
            lambda payload: payload["repositories"][0]["dirty"].update(
                {
                    "bad-stage": {
                        "categories": ["staged"],
                        "index": [
                            {
                                "mode": "100644",
                                "object": "0" * 40,
                                "stage": [],
                            }
                        ],
                        "worktree": None,
                    }
                }
            ),
            lambda payload: payload["repositories"].append(
                {
                    **payload["repositories"][0],
                    "id": "duplicate-root",
                }
            ),
        )
        for index, corrupt in enumerate(corruptions):
            with self.subTest(index=index):
                payload = json.loads(json.dumps(original))
                corrupt(payload)
                malformed = self.base / f"malformed-{index}.json"
                malformed.write_text(json.dumps(payload), encoding="utf-8")
                result = self._run(
                    "capture",
                    "--baseline",
                    str(malformed),
                    "--scope",
                    "main:.",
                    expected=2,
                )
                self.assertNotIn("Traceback", result.stderr)

    def test_git_special_characters_are_literal(self) -> None:
        special = "special [*]: name\n.txt"
        (self.repo / special).write_text("base\n", encoding="utf-8")
        self._git(self.repo, "add", "--", special)
        self._git(self.repo, "commit", "-qm", "special path")
        self._baseline()
        (self.repo / special).write_text("changed\n", encoding="utf-8")
        payload = self._capture(f"main:{special}")
        self.assertEqual([special], [item["path"] for item in payload["changes"]])

    def test_external_symlink_is_hashed_without_following(self) -> None:
        external = self.base / "external.txt"
        external.write_text("outside-one\n", encoding="utf-8")
        link = self.repo / "link"
        link.symlink_to(external)
        self._git(self.repo, "add", "--", "link")
        self._git(self.repo, "commit", "-qm", "add link")
        self._baseline()

        external.write_text("outside-two\n", encoding="utf-8")
        self.assertEqual([], self._capture()["changes"])
        link.unlink()
        link.symlink_to(self.base / "another-external.txt")
        payload = self._capture()
        after = payload["changes"][0]["after"]["worktree"]
        self.assertEqual("symlink", after["kind"])
        self.assertEqual(str(self.base / "another-external.txt"), after["target"])

    def test_parent_symlink_is_not_followed_outside_repository(self) -> None:
        tracked_directory = self.repo / "directory"
        tracked_directory.mkdir()
        (tracked_directory / "child.txt").write_text("inside\n", encoding="utf-8")
        self._git(self.repo, "add", "--", "directory/child.txt")
        self._git(self.repo, "commit", "-qm", "add nested file")
        self._baseline()

        (tracked_directory / "child.txt").unlink()
        tracked_directory.rmdir()
        external_directory = self.base / "external-directory"
        external_directory.mkdir()
        external_child = external_directory / "child.txt"
        external_child.write_text("outside-one\n", encoding="utf-8")
        tracked_directory.symlink_to(external_directory, target_is_directory=True)

        first = self._capture()
        child_change = next(item for item in first["changes"] if item["path"] == "directory/child.txt")
        self.assertEqual("parent-symlink", child_change["after"]["worktree"]["kind"])
        external_child.write_text("outside-two\n", encoding="utf-8")
        second = self._capture()
        self.assertEqual(first["candidate_sha256"], second["candidate_sha256"])

    def test_file_mode_change_is_fingerprinted(self) -> None:
        executable = self.repo / "tool.sh"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        self._git(self.repo, "add", "--", "tool.sh")
        self._git(self.repo, "commit", "-qm", "add tool")
        self._baseline()
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        payload = self._capture()
        self.assertEqual("100755", payload["changes"][0]["after"]["worktree"]["mode"])

    def test_multi_repo_fingerprint_is_order_independent(self) -> None:
        second = self._new_repo("second")
        self._baseline(("zeta", second), ("alpha", self.repo))
        (self.repo / "alpha.txt").write_text("a\n", encoding="utf-8")
        (second / "zeta.txt").write_text("z\n", encoding="utf-8")
        first = self._capture("alpha:.", "zeta:.")
        second_capture = self._capture("zeta:.", "alpha:.")
        self.assertEqual(first["candidate_sha256"], second_capture["candidate_sha256"])
        self.assertEqual(["alpha", "zeta"], [repo["id"] for repo in first["repositories"]])
        self.assertEqual(2, len(first["changes"]))

    def test_dirty_submodule_requires_separate_repo_and_then_detects_drift(self) -> None:
        source = self._new_repo("submodule-source")
        parent = self._new_repo("submodule-parent")
        self._git(
            parent,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(source),
            "dependency",
        )
        self._git(parent, "commit", "-qam", "add submodule")
        child = parent / "dependency"
        self._git(child, "config", "user.email", "quality@example.test")
        self._git(child, "config", "user.name", "Quality Test")
        self._git(parent, "config", "-f", ".gitmodules", "submodule.dependency.ignore", "all")
        self._git(parent, "add", "--", ".gitmodules")
        self._git(parent, "commit", "-qm", "ignore submodule status by default")
        (child / "tracked.txt").write_text("dirty-one\n", encoding="utf-8")

        self._run(
            "baseline",
            "--repo",
            f"parent={parent}",
            "--output",
            str(self.baseline_path),
            expected=2,
        )

        self._baseline(("parent", parent), ("child", child))
        first = self._capture("parent:.", "child:.")
        (child / "tracked.txt").write_text("dirty-two\n", encoding="utf-8")
        second = self._capture("parent:.", "child:.")
        self.assertNotEqual(first["candidate_sha256"], second["candidate_sha256"])
        self.assertEqual(["tracked.txt"], [item["path"] for item in second["changes"]])

    def test_check_treats_new_uncovered_dirty_submodule_as_drift(self) -> None:
        source = self._new_repo("check-submodule-source")
        parent = self._new_repo("check-submodule-parent")
        self._git(
            parent,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(source),
            "dependency",
        )
        self._git(parent, "commit", "-qam", "add clean submodule")
        self._baseline(("parent", parent))
        candidate = self._capture("parent:.")

        (parent / "dependency" / "tracked.txt").write_text("new dirty state\n", encoding="utf-8")
        result = self._check(
            candidate["candidate_sha256"],
            "parent:.",
            exit_code=3,
        )
        self.assertIn("uncovered dirty gitlink: parent:dependency", result["reasons"])

    def test_staged_gitlink_deletion_still_requires_child_repo(self) -> None:
        source = self._new_repo("deleted-submodule-source")
        parent = self._new_repo("deleted-submodule-parent")
        self._git(
            parent,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(source),
            "dependency",
        )
        self._git(parent, "commit", "-qam", "add submodule for deletion")
        child = parent / "dependency"
        self._git(parent, "rm", "--cached", "-q", "--", "dependency")
        (child / "tracked.txt").write_text("dirty-one\n", encoding="utf-8")

        self._run(
            "baseline",
            "--repo",
            f"parent={parent}",
            "--output",
            str(self.baseline_path),
            expected=2,
        )
        self._baseline(("parent", parent), ("child", child))
        (child / "tracked.txt").write_text("dirty-two\n", encoding="utf-8")
        payload = self._capture("parent:.", "child:.")
        self.assertEqual(["tracked.txt"], [item["path"] for item in payload["changes"]])

    def test_untracked_nested_git_repo_requires_separate_repo(self) -> None:
        parent = self._new_repo("nested-parent")
        nested = parent / "nested"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        self._git(nested, "config", "user.email", "quality@example.test")
        self._git(nested, "config", "user.name", "Quality Test")
        (nested / "nested.txt").write_text("dirty-one\n", encoding="utf-8")
        self._git(nested, "add", "--", "nested.txt")
        self._git(nested, "commit", "-qm", "nested baseline")
        (nested / "nested.txt").write_text("dirty-two\n", encoding="utf-8")

        self._run(
            "baseline",
            "--repo",
            f"parent={parent}",
            "--output",
            str(self.baseline_path),
            expected=2,
        )
        self._baseline(("parent", parent), ("nested", nested))
        (nested / "nested.txt").write_text("dirty-three\n", encoding="utf-8")
        payload = self._capture("parent:.", "nested:.")
        self.assertEqual(["nested.txt"], [item["path"] for item in payload["changes"]])

    def test_check_treats_new_nested_git_repo_as_drift(self) -> None:
        parent = self._new_repo("new-nested-parent")
        self._baseline(("parent", parent))
        candidate = self._capture("parent:.")

        nested = parent / "nested"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        self._git(nested, "config", "user.email", "quality@example.test")
        self._git(nested, "config", "user.name", "Quality Test")
        (nested / "nested.txt").write_text("new\n", encoding="utf-8")
        self._git(nested, "add", "--", "nested.txt")
        self._git(nested, "commit", "-qm", "new nested repository")

        result = self._check(candidate["candidate_sha256"], "parent:.", exit_code=3)
        self.assertIn("uncovered nested Git root: parent:nested", result["reasons"])

    def test_invalid_expected_digest_exit_two(self) -> None:
        self._baseline()
        self._run(
            "check",
            "--baseline",
            str(self.baseline_path),
            "--scope",
            "main:.",
            "--expected",
            "NOT-A-SHA",
            expected=2,
        )


if __name__ == "__main__":
    unittest.main()
