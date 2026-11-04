"""Auditable tool router with a strict command allowlist and deny-by-default writes."""
import shlex
import subprocess

from core.protocol import AgentStep
from .base import ToolOutcome
from .workspace import Workspace, WorkspaceError

READ_ONLY_CHECKS = {
    ("git", "status", "--short"),
    ("git", "diff", "--check"),
    ("git", "diff", "--stat"),
}
OPT_IN_CHECKS = {
    ("python", "-m", "unittest", "discover", "-s", "tests", "-v"),
    ("python", "-m", "pytest", "-q"),
    ("python3", "-m", "pytest", "-q"),
    ("npm", "test"),
}


class ToolRegistry:
    def __init__(self, workspace: Workspace, *, allow_writes: bool = False,
                 allow_checks: bool = False, max_output_chars: int = 6500):
        self.workspace = workspace
        self.allow_writes = allow_writes
        self.allow_checks = allow_checks
        self.max_output_chars = max_output_chars

    def _output(self, action: str, text: str, *, ok: bool = True,
                verification: bool = False) -> ToolOutcome:
        short = text[:self.max_output_chars]
        if len(text) > self.max_output_chars:
            short += "\n[output truncated]"
        summary = f"{action}: {'ok' if ok else 'failed'}"
        return ToolOutcome(action, ok, summary, short, verification)

    def invoke(self, step: AgentStep) -> ToolOutcome:
        action = step.action
        if action == "finish":
            return self._output("finish", step.summary or "Model requested finish.")

        try:
            if action == "list_files":
                return self._output(action, self.workspace.list_files(step.path or "."))
            if action == "read_file":
                if not step.path:
                    raise WorkspaceError("read_file requires path.")
                return self._output(action, self.workspace.read_file(step.path))
            if action == "search_text":
                if not step.query:
                    raise WorkspaceError("search_text requires query.")
                return self._output(action, self.workspace.search_text(step.query))
            if action == "write_file":
                if not self.allow_writes:
                    return self._output(action, "BLOCKED: --apply was not provided.", ok=False)
                if not step.path or step.content is None:
                    raise WorkspaceError("write_file requires path and content.")
                return self._output(action, self.workspace.write_file(step.path, step.content))
            if action == "run_check":
                return self._run_check(step.command or "")
            return self._output(action, "BLOCKED: unknown operation.", ok=False)
        except (WorkspaceError, OSError, UnicodeError) as exc:
            return self._output(action, f"BLOCKED or FAILED: {type(exc).__name__}: {exc}", ok=False)

    def _run_check(self, command: str) -> ToolOutcome:
        try:
            argv = tuple(shlex.split(command))
        except ValueError as exc:
            return self._output("run_check", f"BLOCKED: {exc}", ok=False)
        if argv in READ_ONLY_CHECKS:
            verification = False
        elif argv in OPT_IN_CHECKS and self.allow_checks:
            verification = True
        else:
            return self._output("run_check", "BLOCKED: not an approved command or --allow-checks absent.", ok=False)
        try:
            completed = subprocess.run(
                list(argv), cwd=self.workspace.root, capture_output=True, text=True,
                timeout=45, check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return self._output("run_check", f"FAILED {command}: {exc}", ok=False)
        output = (completed.stdout + "\n" + completed.stderr).strip()
        passed = completed.returncode == 0
        # unittest discover can exit zero when no tests were found: that is not evidence.
        if argv in OPT_IN_CHECKS and "unittest" in argv:
            import re
            match = re.search(r"Ran (\\d+) tests?", output)
            if not match or int(match.group(1)) == 0:
                passed = False
                output += "\\nFAILED: no executed unittest cases could be verified."
        return self._output(
            "run_check",
            f"command={command}\nexit_code={completed.returncode}\n{output}",
            ok=passed, verification=(verification and passed),
        )
