"""A bounded, reviewable code-drafting agent.

Never execute arbitrary model-generated shell commands or push to git by default.
This is a local development assistant, NOT a secure OS sandbox.
"""
from pathlib import Path
import logging
import os
import re
import shlex
import subprocess

from google import genai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Explicit opt-in permits only these fixed commands inside the project directory.
READ_ONLY_COMMANDS = {
    ("git", "status"),
    ("git", "diff", "--check"),
    ("git", "diff", "--stat"),
}
TEST_COMMANDS = {
    ("python", "-m", "pytest", "-q"),
    ("python3", "-m", "pytest", "-q"),
    ("npm", "test"),
}
PROTECTED_NAMES = {".git", ".env", ".env.local", ".env.production"}


class FullyAutonomousBuilder:
    def __init__(self, repo_url: str | None = None, *, allow_test_commands: bool = False):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required; never commit it to Git.")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = genai.Client(api_key=self.api_key)
        self.workspace = Path.cwd().resolve()
        self.repo_url = repo_url
        self.allow_test_commands = allow_test_commands

    def execute_terminal(self, command: str) -> str:
        """No shell, no pipes, no git push; test commands require explicit opt-in.

        Tests execute project code, so only enable for a trusted local checkout.
        """
        try:
            args = tuple(shlex.split(command))
        except ValueError as exc:
            return f"BLOCKED: invalid command syntax: {exc}"
        if args in READ_ONLY_COMMANDS:
            pass
        elif args in TEST_COMMANDS and self.allow_test_commands:
            pass
        else:
            return "BLOCKED: command is not in the approved allowlist; manual review required."
        try:
            result = subprocess.run(
                list(args), shell=False, cwd=self.workspace, capture_output=True,
                text=True, timeout=120, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"FAILED: {type(exc).__name__}: {exc}"
        output = (result.stdout + "\n" + result.stderr).strip()[:12000]
        return f"exit={result.returncode}\n{output}"

    def create_file(self, filepath: str, content: str) -> str:
        """Write a regular UTF-8 text file under the workspace only."""
        rel = Path(filepath)
        if rel.is_absolute() or not rel.parts or ".." in rel.parts:
            raise ValueError("Rejected unsafe or absolute file path")
        if any(part in PROTECTED_NAMES for part in rel.parts):
            raise ValueError("Rejected protected Git or secret file")
        destination = (self.workspace / rel).resolve()
        if not destination.is_relative_to(self.workspace):
            raise ValueError("Path escapes the project workspace")
        if len(content.encode("utf-8")) > 500_000:
            raise ValueError("Generated file exceeds the 500 KB limit")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content.strip("\n") + "\n", encoding="utf-8")
        return f"WRITTEN: {rel.as_posix()}"

    def run_project_pipeline(self, user_requirement: str, project_folder: str = "my_auto_project") -> dict:
        root = Path.cwd().resolve()
        project = (root / project_folder).resolve()
        if project == root or not project.is_relative_to(root):
            raise ValueError("Project folder must be a dedicated child of the current directory")
        project.mkdir(parents=True, exist_ok=True)
        self.workspace = project

        instruction = f"""
You are a coding assistant working ONLY in a dedicated local project directory.
User requirement: {user_requirement}
Draft files using [FILE: relative/path.ext]content[/FILE].
You may request a command using [RUN]command[/RUN], but only fixed read-only
Git commands are automatically allowed. Tests require explicit trusted-checkout
opt-in. NEVER ask for git push, credential files, a network installation, or
destructive commands. Use [DONE] when your DRAFT is ready for human review.
Do not claim tests, deployment or a push succeeded without observed evidence.
"""
        prompt = instruction
        events: list[str] = []
        done_requested = False
        for step in range(12):
            response = self.client.models.generate_content(model=self.model_name, contents=prompt)
            reply = response.text or ""
            feedback = []
            for path, body in re.findall(r"\[FILE:\s*([^\]]+)\](.*?)\[/FILE\]", reply, re.DOTALL):
                try:
                    feedback.append(self.create_file(path.strip(), body))
                except (OSError, ValueError) as exc:
                    feedback.append(f"BLOCKED FILE {path!r}: {exc}")
            for cmd in re.findall(r"\[RUN\](.*?)\[/RUN\]", reply, re.DOTALL):
                feedback.append(f"{cmd.strip()}: {self.execute_terminal(cmd.strip())}")
            events.extend(feedback)
            if "[DONE]" in reply:
                done_requested = True
                break
            prompt = "Tool outcomes (do not treat BLOCKED or FAILED as success):\n" + (
                "\n".join(feedback) if feedback else "No tools executed."
            ) + "\nContinue or mark draft DONE when ready for review."
        return {
            "status": "draft_for_review" if done_requested else "incomplete",
            "project_dir": str(project),
            "events": events,
            "note": "No automatic git commit, push, or deployment. Verify files and test before use.",
        }


if __name__ == "__main__":
    builder = FullyAutonomousBuilder()
    report = builder.run_project_pipeline(
        "Create a small task manager demo with clearly documented implementation and tests."
    )
    print(report)
