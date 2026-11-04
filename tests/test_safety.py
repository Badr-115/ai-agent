import asyncio
import tempfile
import unittest
from pathlib import Path

from agents.autonomous_engineer import FullyAutonomousBuilder
from core.schemas import Task, TaskStatus
from execution.engine import ExecutionEngine


class AgentSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.agent = FullyAutonomousBuilder.__new__(FullyAutonomousBuilder)
        self.agent.workspace = Path(self.temp.name).resolve()
        self.agent.allow_test_commands = False

    def tearDown(self):
        self.temp.cleanup()

    def test_rejects_parent_traversal(self):
        with self.assertRaises(ValueError):
            self.agent.create_file("../escape.txt", "unsafe")

    def test_rejects_absolute_and_secret_paths(self):
        for name in ("/tmp/escape.txt", ".env", ".git/config"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.agent.create_file(name, "secret")

    def test_writes_only_inside_workspace(self):
        result = self.agent.create_file("src/app.py", "print('ok')")
        self.assertIn("WRITTEN", result)
        self.assertEqual((self.agent.workspace / "src/app.py").read_text(), "print('ok')\n")

    def test_blocks_model_generated_shell_commands(self):
        for command in ("rm -rf .", "git push origin main", "python -c 'print(1)'", "npm install"):
            with self.subTest(command=command):
                self.assertIn("BLOCKED", self.agent.execute_terminal(command))

    def test_refuses_to_fake_task_success(self):
        task = Task(description="do a real thing")
        success = asyncio.run(ExecutionEngine().execute_task(task))
        self.assertFalse(success)
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIsNone(task.result)


if __name__ == "__main__":
    unittest.main()
