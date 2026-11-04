# AI Agent — safe, reviewable prototype

This repository contains two distinct experimental paths:
- `main.py` + `agents/orchestrator.py`: generate a structured plan, then run tasks **only with an explicitly provided executor**. Without an executor they are marked **FAILED**, never reported as completed.
- `agents/autonomous_engineer.py`: an opt-in code-drafting helper using Gemini that can write text files within a dedicated child project directory.

## Safety and truthful status

This is **not** a sandboxed autonomous engineer or a production tool. Generated code is untrusted. Model-generated terminal commands run **only** if they exactly match an allowlist. Read-only `git status`, `git diff --check`, and `git diff --stat` are permitted. Running `python -m pytest -q` or `npm test` requires explicit `allow_test_commands=True` and a trusted local checkout, because tests execute project code. `git push`, `git commit`, package installation, network calls, shell expansion, and arbitrary commands are denied. Relative text file writes cannot escape the workspace or overwrite `.env` or `.git`.

There is no automatic deployment, PR creation, or verified production correctness. You must review all generated changes before using them.

## Install and run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY='your-key-from-a-secret-store'
python main.py
```

Or run the bounded drafting demo using `python -m agents.autonomous_engineer`. Gemini API usage may cost money depending on your account, even though this repository itself is free.

## Tests

```bash
python -m unittest discover -s tests -v
```

CI runs the safety tests for pushes and pull requests. Passing these tests establishes only the guarded behaviors they cover; it is not a full security audit.
