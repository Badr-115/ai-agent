"""Test the supported CLI's default rollback/opt-out without calling Gemini."""
import argparse
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main
from agents.coding_agent import ScriptedProvider
from core.protocol import AgentStep


def step(action, **kwargs):
    return AgentStep(action=action, reason="offline scripted CLI test", **kwargs)


def args(workspace, *, keep=False):
    return argparse.Namespace(
        workspace=Path(workspace), goal="Modify a sample file without tests",
        apply=True, allow_checks=False, approve_each=False,
        max_steps=5, model=None, keep_unverified=keep,
    )


class CliRollbackTests(unittest.IsolatedAsyncioTestCase):
    async def run_cli(self, path, actions, keep=False):
        buf = io.StringIO()
        provider = ScriptedProvider(actions)
        with patch("providers.gemini_provider.GeminiProvider", return_value=provider):
            with redirect_stdout(buf):
                result = await main.execute(args(path, keep=keep))
        return result, json.loads(buf.getvalue())

    async def test_unverified_edit_is_reverted_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "a.py"
            target.write_text("original\n", encoding="utf-8")
            rc, report = await self.run_cli(folder, [
                step("preview_file", path="a.py", content="changed\n"),
                step("write_file", path="a.py", content="changed\n"),
                step("finish", summary="Changed file without running tests"),
            ])
            self.assertEqual(rc, 2)
            self.assertEqual(report["status"], "rolled_back")
            self.assertEqual(report["files_changed"], [])
            self.assertEqual(target.read_text(), "original\n")

    async def test_failed_model_restores_new_file(self):
        with tempfile.TemporaryDirectory() as folder:
            class FailsAfterWrite:
                count = 0
                async def generate_structured(self, prompt, schema, system_prompt=None):
                    self.count += 1
                    if self.count == 1:
                        return step("preview_file", path="generated.txt", content="text")
                    if self.count == 2:
                        return step("write_file", path="generated.txt", content="text")
                    raise RuntimeError("offline model failure")
            with patch("providers.gemini_provider.GeminiProvider", return_value=FailsAfterWrite()):
                output = io.StringIO()
                with redirect_stdout(output):
                    rc = await main.execute(args(folder))
                report = json.loads(output.getvalue())
            self.assertEqual(rc, 2)
            self.assertEqual(report["status"], "rolled_back")
            self.assertFalse((Path(folder) / "generated.txt").exists())

    async def test_keep_unverified_preserves_file_with_honest_status(self):
        with tempfile.TemporaryDirectory() as folder:
            rc, report = await self.run_cli(folder, [
                step("preview_file", path="saved.txt", content="untested"),
                step("write_file", path="saved.txt", content="untested"),
                step("finish", summary="No tests were run"),
            ], keep=True)
            self.assertEqual(rc, 2)
            self.assertEqual(report["status"], "unverified_changes")
            self.assertEqual(report["files_changed"], ["saved.txt"])
            self.assertEqual((Path(folder) / "saved.txt").read_text(), "untested")
