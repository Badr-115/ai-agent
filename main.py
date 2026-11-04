"""Entry point. Use --demo for a zero-key, zero-cost real local tool run."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from dotenv import load_dotenv

from agents.coding_agent import CodingAgent, ScriptedProvider
from core.protocol import AgentStep, RunStatus
from tools.registry import ToolRegistry
from tools.workspace import Workspace


def demo() -> int:
    """A fully local executable test using files, Git and actual Python unittest."""
    with tempfile.TemporaryDirectory(prefix="professional-agent-demo-") as directory:
        root = Path(directory)
        (root / "README.md").write_text("Small local agent demo.\n", encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests/test_result.py").write_text(
            "import unittest\nfrom pathlib import Path\n\n"
            "class DemoTest(unittest.TestCase):\n"
            "    def test_generated_file(self):\n"
            "        self.assertEqual(Path('notes/result.txt').read_text(), 'done\\n')\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", str(root)], check=True,
                       capture_output=True)
        steps = [
            AgentStep(action="list_files", reason="Inspect the available local files."),
            AgentStep(action="read_file", path="README.md", reason="Read scope."),
            AgentStep(action="write_file", path="notes/result.txt", content="done\n",
                      reason="Create an actual result file."),
            AgentStep(action="run_check",
                      command="python -m unittest discover -s tests -v",
                      reason="Execute a real test that checks the new file."),
            AgentStep(action="finish", reason="All scripted steps complete.",
                      summary="Offline demo created and tested a real file in an isolated temp directory."),
        ]
        registry = ToolRegistry(Workspace(root), allow_writes=True, allow_checks=True)
        report = asyncio.run(CodingAgent(
            ScriptedProvider(steps), registry, max_steps=6,
        ).run("Create a small file and verify its contents locally."))
        print(report.model_dump_json(indent=2))
        return 0 if report.status == RunStatus.VERIFIED_LOCAL else 1


async def execute(args: argparse.Namespace) -> int:
    # Deliberately do not construct an API client unless the user selected it.
    from providers.gemini_provider import GeminiProvider

    workspace = Workspace(args.workspace)
    registry = ToolRegistry(
        workspace, allow_writes=args.apply, allow_checks=args.allow_checks
    )
    report = await CodingAgent(
        GeminiProvider(model=args.model), registry, max_steps=args.max_steps,
    ).run(args.goal))
    print(report.model_dump_json(indent=2))
    return 0 if report.status in {RunStatus.INSPECTED, RunStatus.VERIFIED_LOCAL} else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local coding agent with explicit permissions and evidence-based reporting."
    )
    parser.add_argument("--demo", action="store_true",
                        help="Run a real offline file+test workflow with NO model/API charges.")
    parser.add_argument("--workspace", type=Path,
                        help="Explicit existing local workspace (required without --demo).")
    parser.add_argument("--goal", type=str, help="Engineering task, 3-1500 characters.")
    parser.add_argument("--model", default=None, help="Opt-in Gemini model override.")
    parser.add_argument("--apply", action="store_true",
                        help="Permit bounded edits to non-protected workspace files.")
    parser.add_argument("--allow-checks", action="store_true",
                        help="Permit tests that execute workspace code (only trusted checkouts).")
    parser.add_argument("--max-steps", type=int, default=8, help="Max model requests, 1-20.")
    args = parser.parse_args()
    if args.demo:
        return demo()
    if args.workspace is None or not args.goal:
        parser.error("--workspace and --goal are required unless --demo is selected.")
    load_dotenv()
    try:
        return asyncio.run(execute(args))
    except (ValueError, OSError) as exc:
        print(f"Agent failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
