from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import quality_checks as checks
from scripts import quality_fingerprint as quality


class QualityChecksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "checks@example.test")
        self.git("config", "user.name", "Checks Test")
        self.write("src/a/value.py", "VALUE = 1\n")
        self.write("src/b/value.py", "VALUE = 2\n")
        self.write("tests/helpers.py", "EXPECTED = 1\n")
        self.write("tests/test_a.py", "import runpy, unittest\nclass ValueTest(unittest.TestCase):\n"
                   "    def test_value(self):\n        self.assertEqual(1, runpy.run_path('src/a/value.py')['VALUE'])\n")
        self.write("pyproject.toml", "[project]\nname = 'checks-test'\n")
        self.write(".gitignore", "__pycache__/\nbuild/\n")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline")
        self.baseline = self.root / "baseline.json"
        self.store = self.root / "checks.json"
        with contextlib.redirect_stdout(io.StringIO()):
            quality.command_baseline(quality.build_parser().parse_args([
                "baseline", "--repo", f"main={self.repo}", "--output", str(self.baseline)]))
        self.command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_a.py"]
        self.check = {"id": "U1-test", "type": "verify",
                      "inputs": {"main": ["src/a", "tests/test_a.py", "tests/helpers.py", "pyproject.toml"]},
                      "command": shlex.join(self.command), "toolchain": [sys.executable], "cwd": "main:."}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def git(self, *arguments):
        return subprocess.run(["git", "-C", str(self.repo), *arguments], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout

    def call(self, command, payload, *, apply=True, extra=(), error=None):
        output, errors = io.StringIO(), io.StringIO()
        arguments = [command, "--baseline", str(self.baseline), "--store", str(self.store),
                     *extra, *(["--apply"] if apply else [])]
        with patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = checks.main(arguments)
        self.assertEqual(2 if error else 0, code, errors.getvalue())
        if error:
            self.assertIn(error, errors.getvalue())
            return None
        return json.loads(output.getvalue())

    def prepare(self, descriptor=None, **options):
        response = self.call("prepare", [descriptor or self.check], **options)
        return response["checks"][0] if response else None

    def complete(self, descriptor=None, *, passed=True):
        descriptor = descriptor or self.check
        prepared = self.prepare(descriptor, extra=("--force",))
        result = {"id": descriptor["id"], "prepared_id": prepared["prepared_id"],
                  "passed": passed, "summary": "checked behavior"}
        if descriptor["type"] == "verify":
            result["exit_code"] = 0 if passed else 1
        else:
            result["reviewer"] = "independent:coordinator"
        self.call("record", [result])
        return result

    def test_real_command_result_reuses_until_its_source_changes(self):
        prepared = self.prepare()
        run = subprocess.run(self.command, cwd=self.repo, capture_output=True, text=True,
                             env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(0, run.returncode, run.stderr)
        result = {"id": self.check["id"], "prepared_id": prepared["prepared_id"],
                  "passed": True, "exit_code": run.returncode, "summary": run.stderr.strip()}
        self.call("record", [result])
        reused = self.prepare()
        self.assertTrue(reused["reusable"])
        self.assertEqual(result["prepared_id"], reused["evidence"]["prepared_id"])
        self.write("src/a/value.py", "VALUE = 9\n")
        self.assertFalse(self.prepare()["reusable"])
        failed = subprocess.run(self.command, cwd=self.repo, capture_output=True, text=True,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertNotEqual(0, failed.returncode)

    def test_unrelated_edit_and_staging_preserve_evidence(self):
        self.complete()
        self.write("src/b/value.py", "VALUE = 3\n")
        self.write("notes.md", "plan wording only\n")
        self.write("tests/test_other.py", "# unrelated\n")
        self.git("add", ".")
        self.assertTrue(self.prepare()["reusable"])

    def test_helpers_and_build_config_invalidate_checks(self):
        for name in ("tests/helpers.py", "pyproject.toml"):
            with self.subTest(name=name):
                self.complete()
                self.write(name, "changed input\n")
                result = self.prepare()
                self.assertFalse(result["reusable"])
                self.assertIn("main:" + name, result["changed_inputs"])

    def test_new_deleted_renamed_and_mode_changed_inputs_are_detected(self):
        self.complete()
        new = self.write("src/a/added.py", "VALUE = 4\n")
        self.assertFalse(self.prepare()["reusable"])
        self.complete()
        new.rename(new.with_name("renamed.py"))
        self.assertFalse(self.prepare()["reusable"])
        self.complete()
        new.with_name("renamed.py").unlink()
        self.assertFalse(self.prepare()["reusable"])
        self.complete()
        (self.repo / "src/a/value.py").chmod(0o755)
        self.assertFalse(self.prepare()["reusable"])

    def test_omitted_scope_is_conservative_and_ignored_inputs_can_be_explicit(self):
        descriptor = {key: value for key, value in self.check.items() if key != "inputs"}
        self.complete(descriptor)
        self.write("src/b/value.py", "changed\n")
        self.assertFalse(self.prepare(descriptor)["reusable"])
        self.write("build/generated.py", "one\n")
        descriptor = {**self.check, "inputs": {"main": ["src/a", "build/generated.py"]}}
        self.complete(descriptor)
        self.write("build/generated.py", "two\n")
        self.assertFalse(self.prepare(descriptor)["reusable"])

    def test_command_cwd_environment_and_toolchain_are_inputs(self):
        self.complete()
        self.assertFalse(self.prepare({**self.check, "command": self.check["command"] + " -v"})["reusable"])
        self.complete()
        self.assertFalse(self.prepare({**self.check, "cwd": "main:tests"})["reusable"])
        descriptor = {**self.check, "environment": ["EC_TEST_SETTING"]}
        with patch.dict(os.environ, {"EC_TEST_SETTING": "private-value-a"}):
            self.complete(descriptor)
        with patch.dict(os.environ, {"EC_TEST_SETTING": "private-value-b"}):
            self.assertFalse(self.prepare(descriptor)["reusable"])
        self.assertNotIn("private-value", self.store.read_text())
        tool = self.root / "compiler"
        tool.write_text("version-one")
        tool.chmod(0o755)
        descriptor = {**self.check, "toolchain": [str(tool)]}
        self.complete(descriptor)
        tool.write_text("version-two")
        self.assertFalse(self.prepare(descriptor)["reusable"])

    def test_review_contract_change_does_not_invalidate_test(self):
        review = {"id": "U1-review", "type": "review", "inputs": {"main": ["src/a"]},
                  "contract": "return one; preserve public API"}
        self.complete(review)
        self.complete()
        self.assertTrue(self.prepare(review)["reusable"])
        self.assertFalse(self.prepare({**review, "contract": "return one; reject missing requests"})["reusable"])
        self.assertTrue(self.prepare()["reusable"])

    def test_relative_path_tool_is_resolved_from_check_working_directory(self):
        descriptor = {**self.check, "cwd": "main:src/b", "command": "fixture-compiler",
                      "toolchain": ["fixture-compiler"]}
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            for component in ("bin", ""):
                with self.subTest(component=component):
                    caller_tool = self.root / component / "fixture-compiler"
                    actual_tool = self.repo / "src/b" / component / "fixture-compiler"
                    for tool in (caller_tool, actual_tool):
                        tool.parent.mkdir(parents=True, exist_ok=True)
                        tool.write_text("#!/bin/sh\nexit 0\n")
                        tool.chmod(0o755)
                    with patch.dict(os.environ, {"PATH": component + os.pathsep + os.environ["PATH"]}):
                        self.assertEqual(0, subprocess.run(["fixture-compiler"], cwd=self.repo / "src/b").returncode)
                        self.complete(descriptor)
                        self.assertTrue(self.prepare(descriptor)["reusable"])
                        actual_tool.write_text("#!/bin/sh\nexit 1\n")
                        self.assertEqual(1, subprocess.run(["fixture-compiler"], cwd=self.repo / "src/b").returncode)
                        self.assertFalse(self.prepare(descriptor)["reusable"])
        finally:
            os.chdir(original_cwd)

    def test_working_directory_symlink_retarget_changes_inputs(self):
        link = self.repo / "selected"
        link.symlink_to("src/a", target_is_directory=True)
        command = [sys.executable, "-c", "import runpy; assert runpy.run_path('value.py')['VALUE'] == 1"]
        descriptor = {**self.check, "cwd": "main:selected", "command": shlex.join(command),
                      "inputs": {"main": ["src/a/value.py", "src/b/value.py"]}}
        self.assertEqual(0, subprocess.run(command, cwd=link, capture_output=True).returncode)
        self.complete(descriptor)
        self.assertTrue(self.prepare(descriptor)["reusable"])
        link.unlink()
        link.symlink_to("src/b", target_is_directory=True)
        self.assertNotEqual(0, subprocess.run(command, cwd=link, capture_output=True).returncode)
        self.assertFalse(self.prepare(descriptor)["reusable"])

    def test_explicit_empty_directory_existence_is_an_input(self):
        descriptor = {**self.check, "inputs": {"main": ["src/a", "src/a/blocking-directory"]}}
        self.complete(descriptor)
        self.assertTrue(self.prepare(descriptor)["reusable"])
        directory = self.repo / "src/a/blocking-directory"
        directory.mkdir()
        self.assertFalse(self.prepare(descriptor)["reusable"])
        self.complete(descriptor)
        directory.rmdir()
        self.assertFalse(self.prepare(descriptor)["reusable"])

    def test_scope_inside_nested_repository_never_reuses_parent_directory_snapshot(self):
        nested = self.repo / "nested"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        source = self.write("nested/src/value.py", "VALUE = 1\n")
        descriptor = {**self.check, "inputs": {"main": ["nested/src"]}}
        self.complete(descriptor)
        source.write_text("VALUE = 2\n")
        response = self.prepare(descriptor)
        self.assertFalse(response["reusable"])
        self.assertIn("main:nested/src", response["uncacheable_inputs"])

    def test_test_only_change_preserves_production_review(self):
        review = {"id": "U1-review", "type": "review", "inputs": {"main": ["src/a"]},
                  "contract": "production contract and directly affected interactions"}
        self.complete(review)
        self.complete()
        self.write("tests/test_a.py", "# changed test\n")
        self.assertFalse(self.prepare()["reusable"])
        self.assertTrue(self.prepare(review)["reusable"])

    def test_cross_repository_dependency_invalidates_only_its_consumers(self):
        dependency = self.root / "dependency"
        dependency.mkdir()
        for arguments in (("init", "-q"), ("config", "user.name", "Checks Test"),
                          ("config", "user.email", "checks@example.test")):
            subprocess.run(["git", "-C", str(dependency), *arguments], check=True, capture_output=True)
        source = dependency / "shared.py"
        source.write_text("VALUE = 1\n")
        subprocess.run(["git", "-C", str(dependency), "add", "."], check=True)
        subprocess.run(["git", "-C", str(dependency), "commit", "-qm", "baseline"], check=True)
        with contextlib.redirect_stdout(io.StringIO()):
            quality.command_baseline(quality.build_parser().parse_args([
                "baseline", "--repo", f"main={self.repo}", "--repo", f"dependency={dependency}",
                "--output", str(self.baseline)]))
        consumer = {**self.check, "id": "dependent-test",
                    "inputs": {**self.check["inputs"], "dependency": ["shared.py"]}}
        self.complete(consumer)
        self.complete()
        source.write_text("VALUE = 2\n")
        response = self.prepare(consumer)
        self.assertFalse(response["reusable"])
        self.assertIn("dependency:shared.py", response["changed_inputs"])
        self.assertTrue(self.prepare()["reusable"])

    def test_changed_during_execution_is_rejected_without_overwriting_store(self):
        prepared = self.prepare()
        previous = self.store.read_bytes()
        self.write("src/a/value.py", "VALUE = 6\n")
        self.call("record", [{"id": self.check["id"], "prepared_id": prepared["prepared_id"],
                              "passed": True, "exit_code": 0, "summary": "passed"}], error="changed during execution")
        self.assertEqual(previous, self.store.read_bytes())

    def test_latest_failure_cannot_be_hidden_by_a_previous_pass(self):
        old = self.complete()
        self.assertTrue(self.prepare()["reusable"])
        self.complete(passed=False)
        self.assertFalse(self.prepare()["reusable"])
        self.call("record", [old], error="prepare this check")

    def test_forced_recheck_cannot_fall_back_to_old_pass_after_interruption(self):
        old = self.complete()
        self.assertTrue(self.prepare()["reusable"])
        self.prepare(extra=("--force",))
        self.assertFalse(self.prepare()["reusable"])
        self.call("record", [old], error="prepare this check")

    def test_preview_does_not_create_or_modify_store_and_receipt_retry_is_idempotent(self):
        self.prepare(apply=False)
        self.assertFalse(self.store.exists())
        result = self.complete()
        original = self.store.read_bytes()
        self.assertTrue(self.call("record", [result])["checks"][0]["replayed"])
        self.prepare(apply=False, extra=("--force",))
        self.assertEqual(original, self.store.read_bytes())

    def test_batch_preparation_shares_file_reads_and_failure_does_not_partially_write(self):
        first = self.check
        second = {**self.check, "id": "U2-test"}
        with patch.object(quality, "_worktree_entry", wraps=quality._worktree_entry) as read:
            self.call("prepare", [first, second])
        file_keys = [(str(call.args[0]), call.args[1]) for call in read.call_args_list]
        self.assertEqual(len(file_keys), len(set(file_keys)))
        original = self.store.read_bytes()
        self.call("prepare", [first, {**second, "inputs": {"missing": ["."]}}], error="unknown input repository")
        self.assertEqual(original, self.store.read_bytes())

    def test_results_require_exit_code_and_review_identity(self):
        prepared = self.prepare()
        self.call("record", [{"id": self.check["id"], "prepared_id": prepared["prepared_id"],
                              "passed": True, "exit_code": 1, "summary": "invalid"}], error="real exit_code")
        review = {"id": "review", "type": "review", "inputs": {"main": ["src/a"]}, "contract": "value"}
        prepared = self.prepare(review)
        self.call("record", [{"id": "review", "prepared_id": prepared["prepared_id"],
                              "passed": True, "summary": "invalid"}], error="reviewer")

    def test_input_and_store_paths_cannot_escape_or_overwrite_baseline(self):
        self.prepare({**self.check, "inputs": {"main": ["../outside"]}}, error="escapes repository")
        self.store = self.baseline
        self.prepare(error="overwrite the baseline")
        self.store = self.repo / "checks.json"
        self.prepare(error="outside repositories")

    def test_wrong_baseline_and_head_movement_reject_reuse(self):
        self.complete()
        payload = json.loads(self.store.read_text())
        payload["baseline_sha256"] = "other-run"
        self.store.write_text(json.dumps(payload))
        self.prepare(error="different baseline")
        self.store.unlink()
        self.write("src/a/value.py", "VALUE = 2\n")
        self.git("add", ".")
        self.git("commit", "-qm", "new head")
        self.prepare(error="HEAD moved")

    def test_volatile_symlink_and_nested_repo_inputs_never_reuse(self):
        descriptor = {**self.check, "volatile": True}
        self.complete(descriptor)
        self.assertFalse(self.prepare(descriptor)["reusable"])
        outside = self.root / "external.txt"
        outside.write_text("external")
        (self.repo / "src/a/link.txt").symlink_to(outside)
        self.complete()
        response = self.prepare()
        self.assertFalse(response["reusable"])
        self.assertIn("main:src/a/link.txt", response["uncacheable_inputs"])
        nested = self.repo / "src/a/nested"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        self.write("src/a/nested/file.py", "nested = True\n")
        self.complete()
        self.assertTrue(any("nested" in name for name in self.prepare()["uncacheable_inputs"]))


if __name__ == "__main__":
    unittest.main()
