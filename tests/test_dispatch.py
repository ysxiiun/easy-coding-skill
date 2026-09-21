from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import dispatch
from scripts import quality_fingerprint as quality


RUN = "ec-skill-019a0000-0000-7000-8000-000000000001"


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Dispatch Test")
        self.git("config", "user.email", "dispatch@example.test")
        (self.repo / "a.txt").write_text("base\n")
        (self.repo / "b.txt").write_text("base\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.original = self.root / "baseline.json"
        quality.command_baseline(quality.build_parser().parse_args([
            "baseline", "--repo", f"main={self.repo}", "--output", str(self.original)]))
        self.home_patch = patch.object(dispatch.Path, "home", return_value=self.home)
        self.home_patch.start()
        self.config = self.home / ".easy-coding" / "config.yaml"
        self.directory = dispatch.dispatch_root() / RUN
        self.request = self.directory / "request.md"
        self.result = self.directory / "result.md"
        self.payload = {"plan": "U1: change a.txt; U2: preserve b.txt. Verify the accepted output.",
                        "authorization": {"quote": "确认方案并转交", "source": "user message after plan v1"}}

    def tearDown(self):
        self.home_patch.stop()
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()

    def configure(self, text="behavior:\n  cooperate_mode: dispatch\n"):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(text)

    def run_cli(self, *arguments, payload=None, error=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["dispatch.py", *map(str, arguments)]), \
                patch.object(sys, "stdin", io.StringIO(json.dumps(payload or {}))), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = dispatch.main()
        self.assertEqual(2 if error else 0, code, errors.getvalue())
        if error:
            self.assertIn(error, errors.getvalue())
            return json.loads(errors.getvalue())
        return json.loads(output.getvalue())

    def send(self, number=1, action="implement", apply=True, extra=(), payload=None, error=None):
        return self.run_cli("send", "--run-id", RUN, "--round", number, "--action", action,
                            "--baseline", self.original if number == 1 else self.directory / "baseline.json",
                            "--scope", "main:a.txt", "--scope", "main:b.txt", *extra,
                            *(["--apply"] if apply else []), payload=payload or self.payload, error=error)

    def resume(self, role="executor", number=1, apply=True, repo=None, error=None):
        return self.run_cli("resume", "--path", self.request if role == "executor" else self.result,
                            "--round", number, "--role", role, "--repo", repo or self.repo,
                            *(["--apply"] if apply else []), error=error)

    def finish(self, number=1, status="implemented", extra=(), error=None):
        return self.run_cli("finish", "--path", self.request, "--round", number, "--status", status,
                            "--apply", *extra, payload={"summary": "U1 implemented; deterministic tests not run."}, error=error)

    def checkpoint(self, stage, payload=None, error=None):
        return self.run_cli("checkpoint", "--path", self.request, "--round", 1, "--stage", stage,
                            "--apply", payload=payload or {"note": "recorded stage"}, error=error)

    def returned(self):
        self.configure()
        self.send()
        self.resume()
        (self.repo / "a.txt").write_text("implemented\n")
        self.finish()

    def test_mode_missing_and_default_are_read_only(self):
        self.assertEqual("default", self.run_cli("mode")["cooperate_mode"])
        self.assertFalse(self.home.exists())
        for text in ("behavior:\n  cooperate_mode: default\n", "behavior:\n  another: dispatch\n",
                     "other:\n  cooperate_mode: dispatch\n", "# cooperate_mode: dispatch\n"):
            self.configure(text)
            self.assertEqual("default", self.run_cli("mode")["cooperate_mode"])
            self.assertFalse(self.directory.exists())

    def test_mode_reads_only_direct_behavior_field(self):
        self.configure('behavior:\n  cooperate_mode: "dispatch" # enabled\n  unit_test_mode: arbitrary\n')
        self.assertEqual("dispatch", self.run_cli("mode")["cooperate_mode"])
        for text in ("behavior: { cooperate_mode: dispatch }", "behavior:\n  cooperate_mode: maybe",
                     "behavior:\n  cooperate_mode: dispatch\n  cooperate_mode: default",
                     "behavior:\n  nested:\n    cooperate_mode: dispatch"):
            self.configure(text)
            self.run_cli("mode", error="error")

    def test_send_needs_mode_authorization_and_apply(self):
        self.send(error="require cooperate_mode")
        self.configure()
        self.send(payload={"plan": "plan"}, error="authorization")
        preview = self.send(apply=False)
        self.assertFalse(preview["applied"])
        self.assertFalse(self.directory.exists())
        created = self.send()
        self.assertIn(str(self.request), created["prompt"])
        self.assertIn("交接轮次 1", created["prompt"])
        self.assertEqual({"request.md", "baseline.json"}, {p.name for p in self.directory.iterdir()})
        self.assertEqual(self.original.read_bytes(), (self.directory / "baseline.json").read_bytes())
        self.assertFalse((self.repo / ".easy-coding").exists())

    def test_round_trip_repairs_and_old_prompts(self):
        self.returned()
        received = self.resume("coordinator")
        self.assertEqual(("QUALITY", "quality"), (received["stage"], received["next_action"]))
        self.assertIn("U1", received["plan"])
        self.assertEqual("QUALITY", self.resume("coordinator")["stage"])
        baseline = (self.directory / "baseline.json").read_bytes()
        self.send(2, "repair", extra=("--work-scope", "main:a.txt"),
                  payload={**self.payload, "quality_round": 2})
        self.resume(number=1, error="round mismatch")
        self.assertEqual("repair", self.resume(number=2)["next_action"])
        (self.repo / "a.txt").write_text("repaired\n")
        self.finish(number=2)
        self.assertEqual("QUALITY", self.resume("coordinator", number=2)["stage"])
        self.assertEqual(baseline, (self.directory / "baseline.json").read_bytes())
        self.assertEqual({"request.md", "result.md", "baseline.json"}, {p.name for p in self.directory.iterdir()})

    def test_default_change_does_not_break_existing_handoff(self):
        self.configure()
        self.send()
        self.configure("behavior:\n  cooperate_mode: default\n")
        self.assertEqual("IMPLEMENT", self.resume()["stage"])
        (self.repo / "a.txt").write_text("done\n")
        self.finish()
        self.assertEqual("QUALITY", self.resume("coordinator")["stage"])
        self.send(2, "repair", error="require cooperate_mode")

    def test_worker_restart_resumes_partial_implementation(self):
        self.configure()
        self.send()
        self.resume()
        (self.repo / "a.txt").write_text("partial\n")
        self.assertEqual("IMPLEMENT", self.resume()["stage"])
        self.resume("coordinator", error="not returned")
        self.finish()
        self.assertEqual("hand_back", self.resume()["next_action"])
        self.resume("coordinator")
        self.resume(error="already returned")

    def test_blocked_result_never_enters_quality(self):
        self.configure()
        self.send()
        self.resume()
        self.finish(status="blocked", extra=("--blocked-stage", "ANALYSIS"))
        result = self.resume("coordinator")
        self.assertEqual(("ANALYSIS", "blocked"), (result["stage"], result["outcome"]))

    def test_receipt_and_checkpoint_do_not_rewind_memory(self):
        self.returned()
        self.resume("coordinator")
        self.checkpoint("MEMORY", error="quality_confirmation")
        self.checkpoint("MEMORY", {"note": "green result accepted", "evidence": "test passed on candidate",
                                    "quality_confirmation": {"quote": "确认结果", "source": "user reply"}})
        memory = self.repo / ".easy-coding" / "memory" / "short"
        memory.mkdir(parents=True)
        (memory / "check.md").write_text("actual memory\n")
        self.assertEqual("MEMORY", self.resume("coordinator")["stage"])
        self.checkpoint("QUALITY", error="cannot move")
        self.checkpoint("COMPLETE", {"note": "memory complete", "memory_ref": str(memory / "check.md")})
        self.assertEqual("COMPLETE", self.resume("coordinator")["stage"])
        self.run_cli("cleanup", "--path", self.request, "--round", 1, "--apply")
        self.assertFalse(self.directory.exists())
        self.resume("coordinator", error="missing")

    def test_candidate_drift_and_wrong_worktree_stop_recovery(self):
        self.configure()
        self.send()
        self.resume(repo=self.root, error="not bound")
        (self.repo / "a.txt").write_text("foreign\n")
        self.resume(error="changed before executor")

    def test_result_drift_and_head_movement_are_detected(self):
        self.returned()
        (self.repo / "a.txt").write_text("changed after return\n")
        self.resume("coordinator", error="candidate changed")
        self.git("add", ".")
        self.git("commit", "-qm", "foreign commit")
        self.resume("coordinator", error="HEAD moved")

    def test_repair_scope_and_machine_writes_are_checked(self):
        self.returned()
        self.resume("coordinator")
        self.send(2, "repair", extra=("--work-scope", "main:a.txt"))
        self.resume(number=2)
        (self.repo / "b.txt").write_text("outside repair\n")
        self.finish(number=2, error="outside this handoff")
        (self.repo / "b.txt").write_text("base\n")
        (self.repo / "foreign.txt").write_text("outside run\n")
        self.finish(number=2, error="outside the approved scope")

    def test_frozen_request_and_baseline_cannot_be_replaced(self):
        self.configure()
        self.send()
        original = self.request.read_text()
        self.request.write_text(original.replace("U1: change", "U1: delete"))
        self.resume(error="frozen request changed")
        self.request.write_text(original)
        (self.directory / "baseline.json").write_text("{}")
        self.resume(error="baseline changed")

    def test_new_round_waits_for_return_and_cannot_swap_baseline(self):
        self.configure()
        self.send()
        self.send(2, "repair", error="not returned")
        self.run_cli("cleanup", "--path", self.request, "--round", 1, error="requires completion")
        extra = self.directory / "unowned.txt"
        extra.write_text("preserve")
        self.run_cli("cleanup", "--path", self.request, "--round", 1, "--cancelled", "--apply",
                     error="unexpected files")
        self.assertTrue(extra.exists())
        extra.unlink()
        self.run_cli("cleanup", "--path", self.request, "--round", 1, "--cancelled", "--apply")
        self.assertTrue(self.config.exists())
        self.assertTrue(self.original.exists())

    def test_machine_changes_by_executor_are_rejected(self):
        self.configure()
        self.send(extra=("--ignore", "main:execution.md"))
        self.resume()
        (self.repo / "a.txt").write_text("done\n")
        (self.repo / "execution.md").write_text("unauthorized execution\n")
        self.finish(error="coordinator-owned")

    def test_local_repair_invalidates_previous_evidence(self):
        self.returned()
        self.resume("coordinator")
        self.checkpoint("QUALITY", {"note": "reviewed", "evidence": "old review"})
        self.checkpoint("IMPLEMENT")
        (self.repo / "a.txt").write_text("local repair\n")
        self.assertEqual("IMPLEMENT", self.resume("coordinator")["stage"])
        self.checkpoint("QUALITY", {"note": "repair candidate"})
        restored = self.resume("coordinator")
        self.assertEqual("QUALITY", restored["stage"])
        self.assertNotIn("evidence", restored["checkpoint"])

    def test_memory_can_resume_when_initial_scope_included_shared_memory(self):
        self.configure()
        self.send(extra=("--scope", "main:.easy-coding/memory"))
        self.resume()
        (self.repo / "a.txt").write_text("done\n")
        memory = self.repo / ".easy-coding" / "memory" / "short"
        memory.mkdir(parents=True)
        (memory / "initial.md").write_text("approved initialization\n")
        self.finish()
        self.resume("coordinator")
        self.checkpoint("MEMORY", {"note": "accepted", "evidence": "checks passed on candidate",
                                   "quality_confirmation": {"quote": "确认结果", "source": "user reply"}})
        (memory / "new.md").write_text("new memory\n")
        self.assertEqual("MEMORY", self.resume("coordinator")["stage"])
        saved = self.checkpoint("MEMORY", {"note": "memory written"})
        self.assertEqual("确认结果", saved["checkpoint"]["quality_confirmation"]["quote"])
        (self.repo / "a.txt").write_text("changed after approval\n")
        self.resume("coordinator", error="business candidate changed")

    def test_completion_and_cleanup_recheck_business_candidate(self):
        self.returned()
        self.resume("coordinator")
        self.checkpoint("MEMORY", {"note": "accepted", "evidence": "passed on candidate",
                                   "quality_confirmation": {"quote": "确认结果", "source": "user reply"}})
        accepted = (self.repo / "a.txt").read_text()
        (self.repo / "a.txt").write_text("unreviewed\n")
        self.checkpoint("COMPLETE", {"note": "done", "memory_ref": "memory.md"}, error="business candidate changed")
        (self.repo / "a.txt").write_text(accepted)
        self.checkpoint("COMPLETE", {"note": "done", "memory_ref": "memory.md"})
        (self.repo / "a.txt").write_text("unreviewed\n")
        self.resume("coordinator", error="business candidate changed")
        self.run_cli("cleanup", "--path", self.request, "--round", 1, "--apply", error="business candidate changed")
        self.assertTrue((self.directory / "baseline.json").exists())

    def test_confirmed_replan_can_continue_locally_without_a_new_handoff(self):
        self.returned()
        self.resume("coordinator")
        self.checkpoint("ANALYSIS")
        revision = {"plan": "Replace the confirmed plan; keep a.txt and also implement c.txt.",
                    "authorization": {"quote": "确认新方案，当前 Agent 执行", "source": "user after revised plan"},
                    "scope": ["main:a.txt", "main:b.txt", "main:c.txt"], "ignore": []}
        original, _ = dispatch.read_document(self.request, "request")
        self.checkpoint("IMPLEMENT", {"note": "revised plan accepted", "revision": revision})
        restored = self.resume("coordinator")
        self.assertEqual(revision["plan"], restored["plan"])
        self.assertEqual(revision["scope"], restored["scope"])
        (self.repo / "c.txt").write_text("new confirmed scope\n")
        self.assertEqual("IMPLEMENT", self.resume("coordinator")["stage"])
        self.checkpoint("QUALITY")
        self.assertEqual("QUALITY", self.resume("coordinator")["stage"])
        revised, _ = dispatch.read_document(self.request, "request")
        self.assertEqual(original["request_sha256"], revised["request_sha256"])


if __name__ == "__main__":
    unittest.main()
