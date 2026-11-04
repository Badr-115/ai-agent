"""Auditable tool router with a strict command allowlist and deny-by-default writes."""
import os
import re
import shlex
import subprocess
from collections.abc import Callable

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
                 allow_checks: bool = False, max_output_chars: int = 6500,
                 require_preview: bool = False,
                 approve_write: Callable[[str, str], bool] | None = None):
        self.workspace = workspace
        self.allow_writes = allow_writes
        self.allow_checks = allow_checks
        self.max_output_chars = max_output_chars
        self.require_preview = require_preview
        self.approve_write = approve_write
        # Exact content digest + previous content digest is owned by the host,
        # not supplied by the model as an authorization token.
        self._staged: dict[str, tuple[str, str, str]] = {}

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
            if action == "preview_file":
                if not step.path or step.content is None:
                    raise WorkspaceError("preview_file requires path and content.")
                preview = self.workspace.preview_write(step.path, step.content)
                self._staged[step.path] = (
                    preview.before_sha256, preview.after_sha256, preview.diff
                )
                return self._output(
                    action,
                    f"PREVIEW {step.path}\nBefore-SHA256: {preview.before_sha256}\n"
                    f"After-SHA256: {preview.after_sha256}\n"
                    f"Changed: {preview.changed}\n{preview.diff}"
                )
            if action == "write_file":
                if not self.allow_writes:
                    return self._output(action, "BLOCKED: --apply was not provided.", ok=False)
                if not step.path or step.content is None:
                    raise WorkspaceError("write_file requires path and content.")
                staged = self._staged.get(step.path)
                if self.require_preview and staged is None:
                    return self._output(
                        action, "BLOCKED: preview_file with the exact content is required first.",
                        ok=False,
                    )
                expected = None
                if staged is not None:
                    from hashlib import sha256
                    expected, content_hash, diff = staged
                    if sha256(step.content.encode("utf-8")).hexdigest() != content_hash:
                        self._staged.pop(step.path, None)
                        return self._output(
                            action, "BLOCKED: content differs from reviewed preview.", ok=False
                        )
                    if self.approve_write is not None and not self.approve_write(
                        step.path, diff
                    ):
                        self._staged.pop(step.path, None)
                        return self._output(action, "DENIED: reviewer declined change.", ok=False)
                elif self.approve_write is not None:
                    return self._output(
                        action, "BLOCKED: reviewer requires a preview.", ok=False
                    )
                result = self.workspace.write_file(
                    step.path, step.content, expected_sha256=expected
                )
                self._staged.pop(step.path, None)
                return self._output(action, result)
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
            # Minimize accidental exposure of model/API credentials to subprocesses.
            # Tests remain powerful and MUST only be run on trusted source code.
            safe_env = {
                k: v for k, v in os.environ.items()
                if not re.search(
                    r"(^|_)(KEY|TOKEN|PASSWORD|PASSWD|SECRET|CREDENTIAL|AUTH|COOKIE|SESSION)($|_)",
                    k, re.IGNORECASE
                )
            }
            completed = subprocess.run(
                list(argv), cwd=self.workspace.root, capture_output=True, text=True,
                timeout=45, check=False, env=safe_env,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return self._output("run_check", f"FAILED {command}: {exc}", ok=False)
        output = (completed.stdout + "\n" + completed.stderr).strip()
        passed = completed.returncode == 0
        # unittest discover can exit zero when no tests were found: that is not evidence.
        if argv in OPT_IN_CHECKS and "unittest" in argv:
            match = re.search(r"Ran (\d+) tests?", output)
            if not match or int(match.group(1)) == 0:
                passed = False
                output += "\nFAILED: no executed unittest cases could be verified."
        return self._output(
            "run_check",
            f"command={command}\nexit_code={completed.returncode}\n{output}",
            ok=passed, verification=(verification and passed),
        )
