"""Offline end-to-end and failure-mode tests for the production-like local agent loop."""
import asyncio
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

from agents.coding_agent import CodingAgent, ScriptedProvider
from core.protocol import AgentStep, RunStatus
from providers.gemini_provider import GeminiProvider
from tools.registry import ToolRegistry
from tools.workspace import Workspace, WorkspaceError


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ws = Workspace(self.root)

    def test_traversal_secret_and_internal_paths_are_blocked(self):
        for path in (
            "../outside.py", "/etc/passwd", ".git/config", ".github/workflows/ci.yml",
            ".env", ".env.local", "keys/private.pem", "id_rsa",
            "node_modules/bundle.js", "src/../secrets.txt", "a\\..\\file.txt",
        ):
            with self.subTest(path=path), self.assertRaises(WorkspaceError):
                self.ws.resolve(path)

    def test_symlink_escape_is_blocked(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "shortcut").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(WorkspaceError):
                self.ws.write_file("shortcut/stolen.txt", "should never write")
            self.assertFalse((Path(outside) / "stolen.txt").exists())

    def test_existing_symlink_file_is_not_followed(self):
        (self.root / "note").symlink_to("/etc/hosts")
        with self.assertRaises(WorkspaceError):
            self.ws.read_file("note")

    def test_atomic_edit_and_secret_listing(self):
        (self.root / ".env").write_text("API_KEY=SECRET", encoding="utf-8")
        self.assertTrue(self.ws.write_file("src/hello.py", "print('hello')\n").startswith("WRITTEN"))
        self.assertEqual(self.ws.read_file("src/hello.py"), "print('hello')\n")
        self.assertIn("src/hello.py", self.ws.list_files())
        self.assertNotIn(".env", self.ws.list_files())
        self.assertIn("src/hello.py:1:", self.ws.search_text("hello"))
        self.assertEqual(self.ws.changed_files, ["src/hello.py"])
        self.assertTrue(self.ws.write_file("src/hello.py", "print('hello')\n").startswith("UNCHANGED"))
        self.assertEqual(len(self.ws.changed_files), 1)

    def test_write_budget_enforced(self):
        ws = Workspace(self.root, max_file_bytes=5, max_total_write_bytes=8)
        ws.write_file("a.txt", "12345")
        with self.assertRaises(WorkspaceError):
            ws.write_file("b.txt", "6789")
        with self.assertRaises(WorkspaceError):
            ws.write_file("b.txt", "012345")

    def test_binary_or_large_read_is_rejected(self):
        (self.root / "binary.dat").write_bytes(b"\xff\xfe")
        with self.assertRaises(WorkspaceError):
            self.ws.read_file("binary.dat")
        (self.root / "large.dat").write_text("x" * 120_001)
        with self.assertRaises(WorkspaceError):
            self.ws.read_file("large.dat")


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        self.registry = ToolRegistry(Workspace(self.root))

    def invoke(self, action, **kwargs):
        return self.registry.invoke(AgentStep(action=action, reason="test", **kwargs))

    def test_explicit_apply_required(self):
        result = self.invoke("write_file", path="src/code.py", content="pass")
        self.assertFalse(result.ok)
        self.assertFalse((self.root / "src/code.py").exists())

    def test_arbitrary_commands_remain_blocked(self):
        for command in (
            "curl https://example.com", "git push origin main",
            "python -c 'print(5)'", "rm -rf .", "pip install requests",
            "python -m pytest -q", "npm test; echo injected",
        ):
            with self.subTest(command=command):
                result = self.invoke("run_check", command=command)
                self.assertFalse(result.ok)
                self.assertFalse(result.verification)

    def test_real_read_only_git_command_is_not_a_test(self):
        output = self.invoke("run_check", command="git status --short")
        self.assertTrue(output.ok)
        self.assertFalse(output.verification)

    def test_unittest_with_no_cases_is_not_verification(self):
        self.registry.allow_checks = True
        outcome = self.invoke(
            "run_check", command="python -m unittest discover -s tests -v"
        )
        self.assertFalse(outcome.ok)
        self.assertFalse(outcome.verification)

    def test_failed_actual_test_cannot_count(self):
        self.registry.allow_checks = True
        (self.root / "tests").mkdir()
        (self.root / "tests/test_fail.py").write_text(
            "import unittest\n"
            "class Failure(unittest.TestCase):\n"
            "    def test_failure(self): self.assertEqual(1, 2)\n",
            encoding="utf-8",
        )
        outcome = self.invoke(
            "run_check", command="python -m unittest discover -s tests -v"
        )
        self.assertFalse(outcome.ok)
        self.assertFalse(outcome.verification)
        self.assertIn("exit_code=1", outcome.feedback)


class AgentWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)

    def runner(self, actions, *, writable=True, checks=True, budget=8):
        return CodingAgent(
            ScriptedProvider(actions),
            ToolRegistry(Workspace(self.root), allow_writes=writable, allow_checks=checks),
            max_steps=budget,
        )

    async def test_real_file_and_real_unittest_pass_after_write(self):
        (self.root / "tests").mkdir()
        (self.root / "tests/test_result.py").write_text(
            "import unittest\nfrom pathlib import Path\n"
            "class ResultTest(unittest.TestCase):\n"
            "    def test_result(self):\n"
            "        self.assertEqual(Path('result.txt').read_text(), 'real\\n')\n",
            encoding="utf-8",
        )
        steps = [
            AgentStep(action="list_files", reason="Inspect."),
            AgentStep(action="write_file", reason="Write output.", path="result.txt", content="real\n"),
            AgentStep(action="run_check", reason="Verify real test.",
                      command="python -m unittest discover -s tests -v"),
            AgentStep(action="finish", reason="Summarize.", summary="Added result and ran tests."),
        ]
        report = await self.runner(steps).run("Create and verify a file")
        self.assertEqual(report.status, RunStatus.VERIFIED_LOCAL)
        self.assertEqual(report.files_changed, ["result.txt"])
        self.assertTrue((self.root / "result.txt").exists())
        self.assertTrue(all(evt.ok for evt in report.events))
        self.assertEqual(report.steps, 4)

    async def test_writes_without_checks_are_unverified(self):
        steps = [
            AgentStep(action="write_file", reason="Write.", path="a.txt", content="real"),
            AgentStep(action="run_check", reason="Use Git.", command="git status --short"),
            AgentStep(action="finish", reason="Finish."),
        ]
        report = await self.runner(steps).run("Change a local file safely")
        self.assertEqual(report.status, RunStatus.UNVERIFIED_CHANGES)

    async def test_test_before_last_write_is_not_verification(self):
        (self.root / "tests").mkdir()
        (self.root / "tests/test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n"
            "    def test_one(self): self.assertTrue(True)\n",
            encoding="utf-8",
        )
        steps = [
            AgentStep(action="run_check", reason="Run tests.",
                      command="python -m unittest discover -s tests -v"),
            AgentStep(action="write_file", reason="Write after test.",
                      path="changed.txt", content="untested"),
            AgentStep(action="finish", reason="Finish."),
        ]
        report = await self.runner(steps).run("Make and verify a change")
        self.assertEqual(report.status, RunStatus.UNVERIFIED_CHANGES)

    async def test_budget_exhaustion_is_not_completion(self):
        steps = [AgentStep(action="list_files", reason="Inspect.")]
        report = await self.runner(steps, budget=1).run("Implement a finished feature")
        self.assertEqual(report.status, RunStatus.INCOMPLETE)

    async def test_read_only_denies_model_request_and_does_not_change_files(self):
        steps = [
            AgentStep(action="write_file", reason="Attempt.", path="file.txt", content="no"),
            AgentStep(action="finish", reason="Finish."),
        ]
        report = await self.runner(steps, writable=False).run("Write a file")
        self.assertEqual(report.status, RunStatus.INCOMPLETE)
        self.assertFalse((self.root / "file.txt").exists())

    async def test_model_failure_does_not_become_success(self):
        class BrokenModel:
            async def generate_structured(self, **kwargs):
                raise RuntimeError("offline provider failure")
        agent = CodingAgent(BrokenModel(), ToolRegistry(Workspace(self.root)))
        report = await agent.run("Test provider failure handling")
        self.assertEqual(report.status, RunStatus.FAILED)
        self.assertFalse(report.events[0].ok)


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_provider_contract_without_any_api_call(self):
        # A fake SDK client validates that the provider passes the Pydantic schema
        # but cannot claim live model integration (no network call is made).
        observed = {}
        class FakeModels:
            async def generate_content(self, *, model, contents, config):
                observed.update(model=model, prompt=contents, config=config)
                return SimpleNamespace(
                    parsed=AgentStep(action="finish", reason="Fake", summary="No live request."),
                    text=None,
                )
        provider = GeminiProvider.__new__(GeminiProvider)
        provider.client = SimpleNamespace(aio=SimpleNamespace(models=FakeModels()))
        provider.model_name = "fake-offline-model"
        result = await provider.generate_structured(
            "hello", AgentStep, system_prompt="system for test"
        )
        self.assertEqual(result.action, "finish")
        self.assertEqual(observed["model"], "fake-offline-model")
        self.assertIsNotNone(observed["config"])
