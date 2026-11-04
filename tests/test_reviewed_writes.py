"""Real filesystem and subprocess regression tests for reviewed writes."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agents.coding_agent import CodingAgent, ScriptedProvider
from core.protocol import AgentStep, RunStatus
from tools.registry import ToolRegistry
from tools.workspace import Workspace, WorkspaceError


def action(name, **fields):
    return AgentStep(action=name, reason="regression test", **fields)


class ReviewedWriteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.workspace = Workspace(self.root)
        self.registry = ToolRegistry(
            self.workspace, allow_writes=True, require_preview=True
        )

    def test_preview_is_non_mutating_and_contains_diff(self):
        original = self.root / "src.py"
        original.write_text("old\n", encoding="utf-8")
        result = self.registry.invoke(action(
            "preview_file", path="src.py", content="new\n"
        ))
        self.assertTrue(result.ok, result.feedback)
        self.assertIn("-old", result.feedback)
        self.assertIn("+new", result.feedback)
        self.assertEqual(original.read_text(), "old\n")

    def test_write_without_matching_preview_is_blocked(self):
        outcome = self.registry.invoke(action(
            "write_file", path="a.py", content="hello\n"
        ))
        self.assertFalse(outcome.ok)
        self.assertFalse((self.root / "a.py").exists())

    def test_different_content_cannot_replace_approved_preview(self):
        self.registry.invoke(action("preview_file", path="a.py", content="good\n"))
        result = self.registry.invoke(action("write_file", path="a.py", content="bad\n"))
        self.assertFalse(result.ok)
        self.assertFalse((self.root / "a.py").exists())
        self.assertTrue(self.registry.invoke(action(
            "preview_file", path="a.py", content="good\n"
        )).ok)
        valid = self.registry.invoke(action(
            "write_file", path="a.py", content="good\n"
        ))
        self.assertTrue(valid.ok)
        self.assertEqual((self.root / "a.py").read_text(), "good\n")

    def test_stale_file_preview_fails_closed(self):
        p = self.root / "existing.py"
        p.write_text("initial\n", encoding="utf-8")
        self.registry.invoke(action("preview_file", path="existing.py", content="model\n"))
        p.write_text("human changed\n", encoding="utf-8")
        outcome = self.registry.invoke(action(
            "write_file", path="existing.py", content="model\n"
        ))
        self.assertFalse(outcome.ok)
        self.assertIn("changed after preview", outcome.feedback)
        self.assertEqual(p.read_text(), "human changed\n")

    def test_human_approval_can_deny_or_accept(self):
        asked = []
        def deny(path, diff):
            asked.append((path, diff))
            return False
        registry = ToolRegistry(
            self.workspace, allow_writes=True, require_preview=True,
            approve_write=deny
        )
        registry.invoke(action("preview_file", path="code.py", content="print(1)\n"))
        result = registry.invoke(action("write_file", path="code.py", content="print(1)\n"))
        self.assertFalse(result.ok)
        self.assertFalse((self.root / "code.py").exists())
        self.assertEqual(asked[0][0], "code.py")
        self.assertIn("+print(1)", asked[0][1])

        registry.approve_write = lambda path, diff: True
        registry.invoke(action("preview_file", path="code.py", content="print(1)\n"))
        result = registry.invoke(action("write_file", path="code.py", content="print(1)\n"))
        self.assertTrue(result.ok)

    def test_rollback_restores_original_and_removes_created_files(self):
        old = self.root / "existing.py"
        old.write_text("original\n", encoding="utf-8")
        self.workspace.write_file("existing.py", "new one\n")
        self.workspace.write_file("existing.py", "new two\n")
        self.workspace.write_file("created.py", "created\n")
        self.assertEqual(self.workspace.changed_files, ["existing.py", "created.py"])
        reverted = self.workspace.rollback_changes()
        self.assertEqual(reverted, ["created.py", "existing.py"])
        self.assertEqual(old.read_text(), "original\n")
        self.assertFalse((self.root / "created.py").exists())
        self.assertEqual(self.workspace.changed_files, [])

    def test_rollback_conflict_prevents_partial_restore(self):
        p = self.root / "one.txt"
        p.write_text("initial\n", encoding="utf-8")
        self.workspace.write_file("one.txt", "first change\n")
        self.workspace.write_file("two.txt", "second change\n")
        p.write_text("independent human edit\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceError, "Rollback conflict"):
            self.workspace.rollback_changes()
        self.assertEqual(p.read_text(), "independent human edit\n")
        self.assertEqual((self.root / "two.txt").read_text(), "second change\n")

    def test_preview_never_exposes_forbidden_file(self):
        (self.root / ".env").write_text("TOKEN=SECRET", encoding="utf-8")
        result = self.registry.invoke(action(
            "preview_file", path=".env", content="TOKEN=OVERWRITE"
        ))
        self.assertFalse(result.ok)
        self.assertNotIn("SECRET", result.feedback)

    def test_secret_api_keys_are_not_passed_into_test_subprocesses(self):
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_secret_environment.py").write_text(
            "import os\nimport unittest\n"
            "class TestNoSecrets(unittest.TestCase):\n"
            "  def test_secret_not_in_child_environment(self):\n"
            "    self.assertNotIn('GEMINI_API_KEY', os.environ)\n"
            "    self.assertNotIn('TEST_SECRET_TOKEN', os.environ)\n",
            encoding="utf-8"
        )
        reg = ToolRegistry(self.workspace, allow_checks=True)
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "must-not-reach-child",
            "TEST_SECRET_TOKEN": "must-not-reach-child",
        }):
            outcome = reg.invoke(action(
                "run_check", command="python -m unittest discover -s tests -v"
            ))
        self.assertTrue(outcome.ok, outcome.feedback)
        self.assertTrue(outcome.verification)


class RealAgentReviewedWorkflow(unittest.IsolatedAsyncioTestCase):
    async def test_real_preview_then_write_then_test(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "tests").mkdir()
            (root / "tests" / "test_output.py").write_text(
                "from pathlib import Path\nimport unittest\n"
                "class Smoke(unittest.TestCase):\n"
                "  def test_content(self):\n"
                "    self.assertEqual(Path('sample.txt').read_text(), 'works\\n')\n"
            )
            registry = ToolRegistry(
                Workspace(root), allow_writes=True, allow_checks=True,
                require_preview=True
            )
            provider = ScriptedProvider([
                action("list_files"),
                action("preview_file", path="sample.txt", content="works\n"),
                action("write_file", path="sample.txt", content="works\n"),
                action("run_check", command="python -m unittest discover -s tests -v"),
                action("finish", summary="Verified local file change."),
            ])
            report = await CodingAgent(provider, registry).run(
                "Generate tested sample locally"
            )
            self.assertEqual(report.status, RunStatus.VERIFIED_LOCAL)
            self.assertEqual(report.files_changed, ["sample.txt"])
            self.assertEqual((root / "sample.txt").read_text(), "works\n")

    async def test_changed_content_without_matching_preview_is_unverified(self):
        with tempfile.TemporaryDirectory() as folder:
            registry = ToolRegistry(
                Workspace(folder), allow_writes=True, require_preview=True
            )
            agent = CodingAgent(ScriptedProvider([
                action("preview_file", path="a.txt", content="safe"),
                action("write_file", path="a.txt", content="different"),
                action("finish", summary="Incorrect claim, no write."),
            ]), registry)
            report = await agent.run("Apply reviewed change safely")
            self.assertEqual(report.status, RunStatus.INSPECTED)
            self.assertEqual(report.files_changed, [])
            self.assertFalse((Path(folder) / "a.txt").exists())


class CliSafetyTests(unittest.TestCase):
    def test_noninteractive_approval_rejected_before_network_access(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--workspace", ".", "--goal", "Change file safely",
             "--apply", "--approve-each"],
            capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires an interactive terminal", result.stderr)


if __name__ == "__main__":
    unittest.main()
