# AI Agent — Bounded Coding Assistant

A **local, evidence-first coding assistant** for a trusted workspace. A model proposes **one typed tool action at a time**; a host-controlled registry validates paths, permissions, commands, output, and budgets. The report never treats model text as proof of test success.

> **Status:** a working, local developer-assistant prototype, **not** an unattended production/autonomous engineer, container sandbox, security-certified agent, or hosted service.

## What it really does

- Lists, reads and searches UTF-8 source files in an explicitly selected workspace.
- Can write or replace files **only** with \`--apply\`. Denies absolute paths, traversal, symlinks, \`.git\`, \`.github\`, \`.env*\`, private-key formats, common credential files and build caches.
- Can run read-only Git checks (status, diff checks). Running Python unit/pytest or npm tests requires **\`--allow-checks\`**, since tests execute project code.
- Rejects arbitrary shell commands, network tools, package installation, \`git push\`, \`git commit\`, file deletion, deployment and unapproved commands.
- Enforces model-step and file-write budgets, file-size limits, command timeouts and output truncation.
- Saves an evidence-based **JSON report**, including changed files, tool outcomes, budget status and verification level. A model cannot declare itself "verified" without an actual successful approved test **after the last file write**.
- Supports the maintained \`google-genai\` SDK and an **offline deterministic demo** with zero API consumption.

## First: real execution without paying anything

Requires Python 3.11+ and Git:

\`\`\`bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py --demo
python -m unittest discover -s tests -v
\`\`\`

\`--demo\` creates a temporary Git repository, writes a real file and runs a real unittest. It calls **no external model** and requires **no API key**. CI runs it on every pull request.

## Opt in to the Gemini API

The model can incur API charges depending on the provider/account and tokens used. Never place credentials in committed files.

\`\`\`bash
export GEMINI_API_KEY="YOUR_KEY_IN_YOUR_LOCAL_SHELL"
python main.py --workspace ./my-trusted-project --goal "Find the bug in this code" --max-steps 8
\`\`\`

The default is **read-only**. To permit source changes:

\`\`\`bash
python main.py --workspace ./my-trusted-project --goal "Improve error handling" --apply --max-steps 10
\`\`\`

To permit test execution for a **trusted local checkout only**:

\`\`\`bash
python main.py --workspace ./my-trusted-project --goal "Improve error handling and verify tests" --apply --allow-checks --max-steps 12
\`\`\`

Expected final statuses:

| Status | Meaning |
|---|---|
| \`verified_local\` | File was changed and an allowed real test passed after the last write |
| \`unverified_changes\` | Files changed, but no later permitted test passed |
| \`inspected\` | Read/search operations succeeded, no files changed |
| \`incomplete\` | Model step budget elapsed or stopped without evidence |
| \`failed\` | Provider/response failed; no false completion claim |

## Architecture

- \`core/protocol.py\`: strict Pydantic actions, audit events and statuses.
- \`agents/coding_agent.py\`: bounded model/tool loop, explicit permissions, evidence-based finish.
- \`tools/workspace.py\`: path policy, size budgets and atomic writes.
- \`tools/registry.py\`: actual tool execution and fixed command allowlist.
- \`providers/gemini_provider.py\`: current Google Gen AI SDK with schema-validated model output.
- \`main.py\`: CLI and offline executable demonstration.
- \`agents/orchestrator.py\`: retained legacy plan/executor experiment. Without an injected executor, tasks are FAILED, not executed.
- \`agents/autonomous_engineer.py\`: retained legacy gated code-drafting experiment for compatibility. Use the new \`main.py\` entry point for supported behavior.

## Security boundaries and limitations

- **Not a sandbox**: Python/npm tests can read files, execute processes and use the network. \`--allow-checks\` is for **trusted local projects only** and does not enforce OS/network isolation.
- **No remote execution**: the agent intentionally has no web browsing, git push, cloud deployments or autonomous commits.
- **No guarantee of correctness**: green CI verifies the documented behaviors, not all model outputs or production use.
- **No live Gemini test in CI**: provider contract tests use fake clients. Actual Gemini model availability, latency, billing and API quota cannot be verified without credentials.
- Human review is required before deployment and before trusting code changes. Any repository text and tool output is untrusted content.

## Verification

\`\`\`bash
python -m unittest discover -s tests -v
python main.py --demo
python -m compileall -q agents core execution providers tools main.py
python -m pip check
\`\`\`

See [GitHub Actions](../../actions) for actual results on the current commit.

## Technical next steps

Container- or VM-level sandboxing, user-approval UI, secure remote execution workers, GitHub pull-request integration, trace persistence, dependency lockfiles, model-cost accounting, and evaluation against real benchmark tasks. Do not treat these as implemented.
