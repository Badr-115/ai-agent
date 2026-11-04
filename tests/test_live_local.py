"""Real local file and git execution; fake LLM plans are clearly offline test doubles."""
import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path

from agents.autonomous_engineer import FullyAutonomousBuilder
from agents.orchestrator import AgentOrchestrator
from core.schemas import AgentMode, Plan, Task, TaskStatus
from execution.engine import ExecutionEngine


class FakePlanProvider:
    async def generate_structured(self, prompt, schema, system_prompt=None):
        assert "Create an execution plan" in prompt
        assert schema is Plan
        return Plan(
            goal="check actual executor behavior",
            mode=AgentMode.GENERAL,
            tasks=[Task(description="check-one"),Task(description="check-two")],
        )


class LiveLocalTests(unittest.TestCase):
    def test_real_allowlisted_git_command_in_temp_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git","init",tmp],check=True,capture_output=True)
            agent=FullyAutonomousBuilder.__new__(FullyAutonomousBuilder)
            agent.workspace=Path(tmp).resolve()
            agent.allow_test_commands=False
            actual=agent.execute_terminal("git status")
            self.assertIn("exit=0",actual,actual)
            self.assertTrue(agent.create_file("src/safe.txt","real content").startswith("WRITTEN"))
            self.assertEqual((Path(tmp)/"src/safe.txt").read_text(),"real content\n")
            self.assertIn("BLOCKED",agent.execute_terminal("git push origin main"))
            self.assertIn("BLOCKED",agent.execute_terminal("echo hello; rm -rf ."))

    def test_real_async_executor_produces_task_results(self):
        completed=[]
        async def executor(task):
            await asyncio.sleep(.001)
            completed.append(task.description)
            return "verified execution for "+task.description

        plan=asyncio.run(AgentOrchestrator(FakePlanProvider(),executor).process_request("test tasks"))
        self.assertEqual(completed,["check-one","check-two"])
        self.assertTrue(all(t.status==TaskStatus.COMPLETED for t in plan.tasks))
        self.assertTrue(all(t.result.startswith("verified execution") for t in plan.tasks))

    def test_executor_failure_is_never_reported_as_success(self):
        async def fails(_task):
            raise RuntimeError("observed failure")
        task=Task(description="will fail")
        worked=asyncio.run(ExecutionEngine(fails).execute_task(task))
        self.assertFalse(worked)
        self.assertEqual(task.status,TaskStatus.FAILED)
        self.assertIsNone(task.result)
        self.assertIn("observed failure",task.error)


if __name__=="__main__":
    unittest.main()
