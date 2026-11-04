# AI Agent — Bounded Coding Assistant

A **local, evidence-first coding assistant** for a trusted workspace. A model proposes **one typed tool action at a time**; a host-controlled registry validates paths, permissions, commands, output, and budgets. The report never treats model text as proof of test success.

> **Status:** a working, local developer-assistant prototype, **not** an unattended production/autonomous engineer, container sandbox, security-certified agent, or hosted service.

## What it really does

- Lists, reads and searches UTF-8 source files in an explicitly selected workspace.
- Can write or replace files **only** with `--apply`. Every change is first previewed as a line-by-line diff. The host refuses changed content or stale files after preview. Denies absolute paths, traversal, symlinks, `.git`, `.github`, `.env*`, private-key formats, common credential files and build caches.
- Can run read-only Git checks (status, diff checks). Running Python unit/pytest or npm tests requires **`--allow-checks`**, since tests execute project code.
- Rejects arbitrary shell commands, network tools, package installation, `git push`, `git commit`, file deletion, deployment and unapproved commands.
- Enforces model-step and file-write budgets, file-size limits, command timeouts and output truncation.
- Outputs an evidence-based **JSON report**, including changed files, tool outcomes, budget status and verification level. A model cannot declare itself "verified" without an actual successful approved test **after the last file write**.
- Supports the maintained `google-genai` SDK and an **offline deterministic demo** with zero API consumption.

## First: real execution without paying anything

Requires Python 3.11+ and Git:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py --demo
python -m unittest discover -s tests -v
```

`--demo` creates a temporary Git repository, writes a real file and runs a real unittest. It calls **no external model** and requires **no API key**. CI runs it on every pull request.

## Opt in to the Gemini API

The model can incur API charges depending on the provider/account and tokens used. Never place credentials in committed files. **Gemini receives the task prompt and excerpts of files read by the agent, which could include your private source code.** Only connect workspaces you are willing to share with that provider. The filename filter is not a guarantee that sensitive text is absent from otherwise ordinary files.

```bash
export GEMINI_API_KEY="YOUR_KEY_IN_YOUR_LOCAL_SHELL"
python main.py --workspace ./my-trusted-project --goal "Find the bug in this code" --max-steps 8
```

The default is **read-only**. To permit source changes:

```bash
python main.py --workspace ./my-trusted-project --goal "Improve error handling" --apply --max-steps 10
```

To permit test execution for a **trusted local checkout only**:

```bash
python main.py --workspace ./my-trusted-project --goal "Improve error handling and verify tests" --apply --allow-checks --max-steps 12
```

Expected final statuses:

| Status | Meaning |
|---|---|
| `verified_local` | File was changed and an allowed real test passed after the last write |
| `unverified_changes` | Files changed, but no later permitted test passed |
| `inspected` | Read/search operations succeeded, no files changed |
| `incomplete` | Model step budget elapsed or stopped without evidence |
| `failed` | Provider/response failed; no false completion claim |
| `rolled_back` | Unverified local edits were reverted rather than retained |

## Reviewed edits, approvals and rollback (new)

The standard `--apply` workflow requires **two distinct model actions**: `preview_file` followed by `write_file` with **identical contents**. If a person or another process edits a file after the preview, the write fails instead of overwriting their work. All edits in a run keep their original file bytes in memory for recovery.

For a local prompt displaying the exact diff before each write:

```bash
python main.py --workspace ./my-trusted-project --goal "Improve error handling" --apply --approve-each --allow-checks
```

Only an explicit `y` approves a change. The option requires an interactive terminal; otherwise the CLI exits **before** calling a paid model.

**Automatic rollback:** When the run cannot demonstrate a passing allowed test after its last edit, the CLI restores the session's original file contents by default. It refuses rollback if someone independently modified any touched file. To retain changes for manual inspection **even without a passing test**, explicitly add `--keep-unverified`. A rollback reports `rolled_back`, not `verified_local`.

```bash
python main.py --workspace ./my-trusted-project --goal "Draft the refactor" --apply --keep-unverified
```

`--keep-unverified` leaves untested changes in place; inspect the diff yourself before committing. By default, the coding agent does not make Git commits or pushes.

**Limitations:** The review/rollback journal exists in memory for a single process only and is not crash-proof or a full filesystem transaction. The workspace must be trusted; adversarial local processes can exploit OS-level races. Running project tests is still arbitrary execution of trusted project code. The shell subprocess environment now omits many common API keys and tokens, but this is not a guarantee against all secret exposure.

## Architecture

- `core/protocol.py`: strict Pydantic actions, audit events and statuses.
- `agents/coding_agent.py`: bounded model/tool loop, explicit permissions, evidence-based finish.
- `tools/workspace.py`: path policy, size budgets, diff previews, conflict detection, atomic writes and session rollback.
- `tools/registry.py`: host-owned preview approval, real tool execution and fixed command allowlist.
- `providers/gemini_provider.py`: current Google Gen AI SDK with schema-validated model output.
- `main.py`: CLI and offline executable demonstration.
- `agents/orchestrator.py`: retained legacy plan/executor experiment. Without an injected executor, tasks are FAILED, not executed.
- `agents/autonomous_engineer.py`: retained legacy gated code-drafting experiment for compatibility. Use the new `main.py` entry point for supported behavior.

## Security boundaries and limitations

- **Not a sandbox**: Python/npm tests can read files, execute processes and use the network. `--allow-checks` is for **trusted local projects only** and does not enforce OS/network isolation.
- **No remote execution**: the agent intentionally has no web browsing, git push, cloud deployments or autonomous commits.
- **No guarantee of correctness**: green CI verifies the documented behaviors, not all model outputs or production use.
- **No live Gemini test in CI**: provider contract tests use fake clients. Actual Gemini model availability, latency, billing and API quota cannot be verified without credentials.
- Human review is required before deployment and before trusting code changes. Any repository text and tool output is untrusted content.

## Verification

```bash
python -m unittest discover -s tests -v
python main.py --demo
python -m compileall -q agents core execution providers tools main.py
python -m pip check
```

See [GitHub Actions](../../actions) for actual results on the current commit.

## Technical next steps

Container- or VM-level sandboxing, GUI approvals, crash-resilient transaction storage, secure remote execution workers, GitHub pull-request integration, persistent traces, dependency lockfiles, model-cost accounting, and evaluation against real benchmark tasks. Do not treat these as implemented.
