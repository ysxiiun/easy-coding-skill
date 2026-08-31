from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_RULES = (
    "SKILL.md",
    "flow/analysis.md",
    "flow/implement.md",
    "flow/quality.md",
    "flow/memory.md",
    "flow/init.md",
    "flow/startup-project.md",
    "flow/git.md",
    "flow/memory-migration.md",
    "flow/memory-retirement.md",
    "references/shared-data.md",
    "references/dev-spec/canonical-v1.md",
)


class SkillContractTest(unittest.TestCase):
    def _read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_main_skill_is_small_versioned_single_skill_router(self) -> None:
        skill = self._read("SKILL.md")
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("version: 7.0.0", skill)
        self.assertIn("固定 Guard", skill)
        self.assertIn("固定 Standard", skill)
        for relative in ACTIVE_RULES[1:]:
            self.assertIn(relative, skill)
            self.assertTrue((ROOT / relative).is_file(), relative)
        self.assertFalse((ROOT / "flow/with-claude.md").exists())
        self.assertFalse((ROOT / "templates/CLAUDE_TASK_PACKET.md").exists())
        self.assertFalse((ROOT / "references/scenarios/easy-coding-with-claude.md").exists())

    def test_only_the_7_0_stage_set_is_exposed(self) -> None:
        allowed = {"INIT", "ANALYSIS", "IMPLEMENT", "QUALITY", "MEMORY", "COMPLETE", "CLOSED"}
        combined = "\n".join(self._read(relative) for relative in ACTIVE_RULES)
        exposed = set(re.findall(r"\[阶段：([A-Z_]+)\]", combined))
        self.assertEqual(allowed, exposed)
        self.assertIn("INIT → ANALYSIS → IMPLEMENT → QUALITY → MEMORY → COMPLETE", combined)
        self.assertIn("只读请求直接走 `ANALYSIS → COMPLETE`", combined)
        self.assertIn("不进入或输出 INIT", self._read("SKILL.md"))
        for removed in ("WAITING_CONFIRM", "[阶段：REVIEW]", "With Claude"):
            self.assertNotIn(removed, combined)
        self.assertIn("只读请求仅报告缺失或旧结构", self._read("SKILL.md"))
        self.assertIn("只报告事实，不创建 Unit", self._read("flow/init.md"))

    def test_startup_and_migration_do_not_add_stage_detours(self) -> None:
        startup = self._read("flow/startup-project.md")
        migration = self._read("flow/memory-migration.md")
        self.assertIn("INIT → ANALYSIS → IMPLEMENT → QUALITY → MEMORY → COMPLETE", startup)
        self.assertIn("不得跳过 INIT", startup)
        self.assertIn("QUALITY 绿色并获用户确认后直接进入 MEMORY", startup)
        self.assertNotIn("post_v1_auto_init", startup)
        self.assertIn("在 IMPLEMENT 加载执行", migration)
        self.assertIn("返回 IMPLEMENT", migration)

    def test_fixed_quality_has_no_public_mode_controls(self) -> None:
        combined = "\n".join(self._read(relative) for relative in ACTIVE_RULES)
        self.assertIn("Standard 双门", combined)
        self.assertIn("Guard 结果确认", combined)
        self.assertIn("host-fallback", combined)
        self.assertIn("code-defect", combined)
        self.assertIn("test-defect", combined)
        self.assertIn("contract-ambiguity", combined)
        self.assertIn("environment", combined)
        self.assertIn("suggestion", combined)
        for removed_entry in (
            "approval_mode",
            "approval-mode",
            "execution_depth",
            "workflow_type",
            "Lite Direct",
            "tdd_mode",
            "java_tdd",
        ):
            self.assertNotIn(removed_entry, combined)

    def test_run_id_baseline_and_canonical_order_is_unambiguous(self) -> None:
        analysis = self._read("flow/analysis.md")
        implementation = self._read("flow/implement.md")
        canonical = self._read("references/dev-spec/canonical-v1.md")
        self.assertLess(analysis.index("先生成一次 `run_id"), analysis.index("quality_fingerprint.py baseline"))
        self.assertIn("不得在 IMPLEMENT 另生成 ID", implementation)
        baseline = canonical.index("创建质量 baseline")
        canonical_init = canonical.index("无 execution 时 `init`", baseline)
        self.assertLess(baseline, canonical_init)
        quality = self._read("flow/quality.md")
        self.assertIn("使用 ANALYSIS 创建、IMPLEMENT 写入前复核通过的 baseline", quality)
        self.assertNotIn("使用 IMPLEMENT 创建的 baseline", quality)
        self.assertIn("受影响 Step 写 `failed`", quality)
        self.assertIn("task 置为 `blocked`", quality)
        self.assertIn("repo 外 locator 不传 `--ignore`", quality)
        self.assertIn("外部 locator 不传给 fingerprint", canonical)
        self.assertIn("quality_round=1", analysis)
        self.assertIn("round:<N>:task:<task-id>:<status>", canonical)
        self.assertIn("task 已为 `implemented`", quality)

    def test_shared_data_contract_separates_harness_private_layer(self) -> None:
        shared = self._read("references/shared-data.md")
        skill = self._read("SKILL.md")
        for public in (
            "SOUL.md",
            "RULES.md",
            "ABSTRACT.md",
            "TEST_STRATEGY.md",
            "Canonical 原文件",
            "memory/short/",
            "memory/long/",
        ):
            self.assertIn(public, shared)
        for private in (
            "config.yaml",
            "project.yaml",
            "install-manifest.json",
            "sessions/",
            "tasks/",
        ):
            self.assertIn(private, shared)
        self.assertIn("只读请求", shared)
        self.assertIn("修改请求", shared)
        self.assertIn("一个控制器", skill)

    def test_memory_and_initialization_use_shared_compatibility_fields(self) -> None:
        memory = self._read("flow/memory.md")
        template = self._read("templates/SHORT_MEMORY.md")
        initialization = self._read("flow/init.md")
        strategy = self._read("templates/TEST_STRATEGY.md")
        changelog = self._read("templates/CHANGELOG.md")
        for field in (
            "source_task: ec-skill-{UUIDv7}",
            "workflow_mode: standard",
            "producer: easy-coding-skill",
        ):
            self.assertIn(field, template)
        self.assertIn("candidate_sha256", memory)
        self.assertIn("short_count > 10", memory)
        self.assertIn("第 11 条", memory)
        self.assertIn("模块边界、依赖方向、核心数据流、技术栈、构建或部署方式", memory)
        self.assertIn("TEST_STRATEGY.md", initialization)
        self.assertIn("项目级验证知识", strategy)
        self.assertIn(".easy-coding/CHANGELOG.md", memory)
        self.assertIn("来源记忆", changelog)
        self.assertIn("受影响章节", changelog)

    def test_git_contract_covers_delivery_and_shared_boundaries(self) -> None:
        git = self._read("flow/git.md")
        self.assertIn(".easy-coding/sessions/", git)
        self.assertIn(".easy-coding/spec/dev/", git)
        self.assertIn("Canonical\n  locator 位于该目录时同样适用本例外", git)
        self.assertNotIn("知识、Canonical 和记忆", git)
        self.assertIn("先在子仓完成", git)
        self.assertIn("脏 gitlink", git)
        self.assertIn("父 gitlink", git)
        self.assertIn("获得用户确认后才编辑", git)
        self.assertIn("远端目标 SHA", git)
        self.assertIn("ahead/behind 为 `0/0`", git)

    def test_docs_and_agent_metadata_match_7_0_0_contract(self) -> None:
        readme = self._read("README.md")
        openai = self._read("agents/openai.yaml")
        self.assertIn("当前版本：`7.0.0`", readme)
        self.assertIn("INIT 只读盘点项目模式", readme)
        self.assertNotIn("INIT 补齐共享项目知识", readme)
        self.assertIn("QUALITY", readme)
        self.assertIn("已移除", readme)
        self.assertIn("PYTHONPYCACHEPREFIX=<system-temp>/easy-coding-pyc", readme)
        self.assertIn("不得把 `__pycache__` 写入项目", readme)
        self.assertIn("Guard", openai)
        self.assertIn("Standard", openai)
        self.assertNotIn("六阶段", openai)


if __name__ == "__main__":
    unittest.main()
