"""Workspace file access with fail-closed path and data limits.

This limits accidental access; it is not an operating-system sandbox.
"""
import difflib
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
import stat
import tempfile


DENIED_DIRS = {
    ".git", ".github", ".ssh", ".aws", ".config", ".idea", ".vscode",
    ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".next", ".cache", "dist", "build", "site-packages",
}
DENIED_NAMES = {
    "id_rsa", "id_ed25519", "credentials", "credentials.json",
    "secrets.json", ".npmrc", ".pypirc", "authorized_keys", "known_hosts",
}
DENIED_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".keystore", ".sqlite", ".db"}


class WorkspaceError(ValueError):
    """The requested file or operation is outside the permitted workspace policy."""


@dataclass(frozen=True)
class FilePreview:
    path: str
    before_sha256: str
    after_sha256: str
    diff: str
    changed: bool


def _digest(value: bytes | None) -> str:
    return "missing" if value is None else hashlib.sha256(value).hexdigest()


class Workspace:
    def __init__(self, root: str | Path, *, max_file_bytes: int = 120_000,
                 max_total_write_bytes: int = 500_000):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise WorkspaceError("Workspace must be an existing directory.")
        self.max_file_bytes = max_file_bytes
        self.max_total_write_bytes = max_total_write_bytes
        self.bytes_written = 0
        self.changed_files: list[str] = []
        self._original_bytes: dict[str, bytes | None] = {}
        self._original_modes: dict[str, int] = {}
        self._latest_digests: dict[str, str] = {}

    @staticmethod
    def _denied(part: str) -> bool:
        lower = part.lower()
        return (
            lower in DENIED_DIRS or lower in DENIED_NAMES
            or lower.startswith(".env")
            or Path(lower).suffix in DENIED_EXTENSIONS
        )

    def resolve(self, name: str, *, allow_root: bool = False) -> Path:
        if not isinstance(name, str) or not name or len(name) > 240:
            raise WorkspaceError("Missing or overlong relative path.")
        if "\x00" in name or "\\" in name or name.startswith("~"):
            raise WorkspaceError("Unsafe path representation.")
        if name == "." and allow_root:
            return self.root
        parts = name.split("/")
        if any(p in ("", ".", "..") or self._denied(p) for p in parts):
            raise WorkspaceError("Protected, secret, or traversal path.")
        rel = Path(*parts)
        if rel.is_absolute():
            raise WorkspaceError("Absolute paths are forbidden.")
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise WorkspaceError("Symlinks are not permitted.")
        target = current.resolve(strict=False)
        if not target.is_relative_to(self.root):
            raise WorkspaceError("Path escapes workspace.")
        return target

    def list_files(self, path: str = ".", limit: int = 80) -> str:
        base = self.resolve(path, allow_root=True)
        if not base.is_dir():
            raise WorkspaceError("Directory not found.")
        output = []
        # Bound traversal and do not follow symlink directories.
        for root, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = sorted(
                d for d in dirs
                if not self._denied(d) and not (Path(root) / d).is_symlink()
            )
            for name in sorted(files):
                if self._denied(name):
                    continue
                full = Path(root) / name
                if full.is_symlink() or not full.is_file():
                    continue
                rel = full.relative_to(self.root).as_posix()
                if len(output) >= limit:
                    return "\n".join(output) + "\n[listing limited]"
                output.append(rel)
        return "\n".join(output) or "[no visible files]"

    def read_file(self, name: str) -> str:
        target = self.resolve(name)
        if not target.is_file():
            raise WorkspaceError("File not found.")
        if target.stat().st_size > self.max_file_bytes:
            raise WorkspaceError("File exceeds read limit.")
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise WorkspaceError("Binary/non-UTF-8 file not supported.") from exc

    def search_text(self, query: str) -> str:
        if not 2 <= len(query) <= 150:
            raise WorkspaceError("Search query must be 2-150 characters.")
        matches: list[str] = []
        files = self.list_files().splitlines()
        for name in files:
            if not name or name.startswith("["):
                continue
            try:
                content = self.read_file(name)
            except (WorkspaceError, OSError):
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                if query.casefold() in line.casefold():
                    matches.append(f"{name}:{line_no}: {line[:200]}")
                    if len(matches) >= 30:
                        return "\n".join(matches) + "\n[matches limited]"
        result = "\n".join(matches) or "[no matches]"
        if "[listing limited]" in files:
            result += "\n[search limited]"
        return result

    def preview_write(self, name: str, content: str) -> FilePreview:
        """Show an exact proposed change, including a baseline digest for conflict checks.

        Preview never creates/modifies a file. No unbounded reads, binary overwrites
        or symlink targets are accepted. A workspace directory is assumed trusted.
        """
        if not isinstance(content, str):
            raise WorkspaceError("Content must be UTF-8 text.")
        data = content.encode("utf-8")
        if len(data) > self.max_file_bytes:
            raise WorkspaceError("File exceeds write limit.")
        target = self.resolve(name)
        if target.exists() and not target.is_file():
            raise WorkspaceError("Cannot replace a directory/device.")
        if target.exists() and target.stat().st_size > self.max_file_bytes:
            raise WorkspaceError("Existing file exceeds review limit.")
        before = target.read_bytes() if target.exists() else None
        try:
            original = before.decode("utf-8") if before is not None else ""
        except UnicodeError as exc:
            raise WorkspaceError("Cannot modify non-UTF-8 or binary files.") from exc
        lines = difflib.unified_diff(
            original.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{name}" if before is not None else "/dev/null",
            tofile=f"b/{name}",
            lineterm="\n",
        )
        diff = "".join(lines)
        if len(diff) > 12000:
            diff = diff[:12000] + "\n[preview truncated]\n"
        return FilePreview(
            path=name, before_sha256=_digest(before), after_sha256=_digest(data),
            diff=diff if diff else "[no changes]", changed=(before != data),
        )

    def write_file(self, name: str, content: str, *,
                   expected_sha256: str | None = None) -> str:
        if not isinstance(content, str):
            raise WorkspaceError("Content must be UTF-8 text.")
        encoded = content.encode("utf-8")
        if len(encoded) > self.max_file_bytes:
            raise WorkspaceError("File exceeds write limit.")
        if self.bytes_written + len(encoded) > self.max_total_write_bytes:
            raise WorkspaceError("Total write budget exceeded.")
        target = self.resolve(name)
        if target.exists() and not target.is_file():
            raise WorkspaceError("Cannot overwrite a directory/device.")
        if target.exists() and target.stat().st_size > self.max_file_bytes:
            raise WorkspaceError("Existing file exceeds review limit.")
        old = target.read_bytes() if target.exists() else None
        if expected_sha256 is not None and _digest(old) != expected_sha256:
            raise WorkspaceError("File changed after preview; review again before writing.")
        if old is not None:
            try:
                old.decode("utf-8")
            except UnicodeError as exc:
                raise WorkspaceError("Cannot overwrite non-UTF-8 or binary files.") from exc
        if old == encoded:
            return f"UNCHANGED {name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        # Re-check path after mkdir (the workspace must still be trusted).
        target = self.resolve(name)
        old_mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600
        handle = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent,
                                             prefix=".agent-write-", delete=False) as f:
                handle = Path(f.name)
                f.write(encoded)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(handle, old_mode)
            os.replace(handle, target)
            # Snapshot only after the write succeeds, preserving the first original
            # value even when a model revisits the same file.
            if name not in self._original_bytes:
                self._original_bytes[name] = old
                self._original_modes[name] = old_mode
            self._latest_digests[name] = _digest(encoded)
        finally:
            if handle is not None:
                handle.unlink(missing_ok=True)
        self.bytes_written += len(encoded)
        if name not in self.changed_files:
            self.changed_files.append(name)
        digest = hashlib.sha256(encoded).hexdigest()[:16]
        return f"WRITTEN {name}: {len(encoded)} bytes; sha256-prefix={digest}"


    def rollback_changes(self) -> list[str]:
        """Restore this session's original bytes, refusing external modifications.

        Preflight checks all changed files before restoring any. This is not an
        ACID transaction across multiple files or an OS-level sandbox.
        """
        items = list(reversed(self.changed_files))
        for name in items:
            target = self.resolve(name)
            current = target.read_bytes() if target.exists() and target.is_file() else None
            if _digest(current) != self._latest_digests.get(name):
                raise WorkspaceError(f"Rollback conflict on {name}: file was modified externally.")
        reverted = []
        for name in items:
            target = self.resolve(name)
            original = self._original_bytes[name]
            if original is None:
                target.unlink()
            else:
                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="wb", dir=target.parent, prefix=".agent-restore-", delete=False
                    ) as stream:
                        temp_path = Path(stream.name)
                        stream.write(original)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.chmod(temp_path, self._original_modes[name])
                    os.replace(temp_path, target)
                finally:
                    if temp_path is not None:
                        temp_path.unlink(missing_ok=True)
            reverted.append(name)
        self.changed_files.clear()
        self._original_bytes.clear()
        self._original_modes.clear()
        self._latest_digests.clear()
        self.bytes_written = 0
        return reverted
