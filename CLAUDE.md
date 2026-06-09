# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Canonical agent guide

[AGENTS.md](AGENTS.md) is the authoritative, detailed instruction set for AI agents working in this repo (setup, commands, architecture, key patterns, testing tiers, code style, gotchas). Read it first. This file summarizes the essentials and documents what is specific to **this fork**.

> This repo is a fork of [sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench). The fork's primary addition is the **MCP server layer** under [src/tau2/mcp/](src/tau2/mcp/) (see "Fork-specific: MCP servers" below).

## Essential commands

Uses `uv` (not pip). Python `>=3.12,<3.14`.

```bash
uv sync --extra dev        # core install needed to run tests/lint
make test                  # core tests (skips voice/streaming/gym/banking_knowledge)
make check-all             # ruff lint + format — run before committing (pre-commit enforces it)
uv run tau2 check-data     # verify installation
```

- Run a single test file: `uv run pytest tests/test_agent.py`
- Run one domain's tests: `uv run pytest tests/test_domains/test_<domain>`
- Test tiers (`test-voice`, `test-knowledge`, `test-gym`, `test-all`) each require their matching `--extra`; see [AGENTS.md](AGENTS.md#testing).
- Run an evaluation: `tau2 run --domain airline --agent-llm gpt-4.1 --user-llm gpt-4.1 --num-trials 1 --num-tasks 5` → results in `data/simulations/`, browse with `tau2 view`.

## Architecture in one paragraph

`tau2` is a simulation framework that evaluates conversational customer-service agents. An **orchestrator** drives a conversation between an **agent** (`src/tau2/agent/`) and a **user simulator** (`src/tau2/user/`) inside a **domain environment** (`src/tau2/environment/` + `src/tau2/domains/<name>/`), then an **evaluator** (`src/tau2/evaluator/`) scores the trajectory against task `evaluation_criteria`. Two communication modes share this flow: half-duplex (turn-based, `Orchestrator` + `HalfDuplexAgent.generate_next_message()`) and full-duplex (streaming/voice, `FullDuplexOrchestrator` + `FullDuplexAgent.get_next_chunk()`). Everything pluggable — agents, domains, tasks, user simulators — is wired through the global **registry** ([src/tau2/registry.py](src/tau2/registry.py)); new components are unusable from the CLI until registered there. Default config values live in [src/tau2/config.py](src/tau2/config.py) — import from there rather than redefining.

A domain (`src/tau2/domains/<name>/`) = `data_model.py` (DB subclass) + `tools.py` (`ToolKitBase` subclass) + `environment.py` (`get_environment`/`get_tasks`/`get_tasks_split`), with data in `data/tau2/domains/<name>/` (tasks.json, policy.md, db.json/toml). See [AGENTS.md](AGENTS.md#key-patterns) for the registry/agent/domain patterns in full.

## Fork-specific: MCP servers

This fork adds [src/tau2/mcp/](src/tau2/mcp/) — FastMCP servers that wrap the airline/retail/telecom domain tools so external MCP-compatible agents can call them (requires `uv sync --extra mcp`). The quickest start is the unified server, `python -m tau2.mcp.unified_server --port 8000`. See [AGENTS.md](AGENTS.md#mcp-servers) for the run modes and behavior notes, and [src/tau2/mcp/README.md](src/tau2/mcp/README.md) for the full tool inventory and config snippets.

## Conventions

- **Branch naming:** name branches `<git-username>/<short-kebab-description>`, where `<git-username>` is the committing user's own GitHub handle — derive it from the active git identity (e.g. the `…+<handle>@users.noreply.github.com` email, or `git config user.name`), not a hardcoded name. Examples: `pdhoolia/airline-plugin`, `esxr/retail-fix`. Never create `claude/*` branches.
  - **Precedence over the harness branch:** if a session harness assigns a `claude/*` working branch by default, **this convention wins**. You have explicit permission to leave that branch: rename it (`git branch -m <git-username>/<short-kebab-description>`) before committing and push the renamed branch — do not commit to or push `claude/*`. A SessionStart hook (`.claude/hooks/branch-naming-reminder.sh`, wired in `.claude/settings.json`) surfaces this reminder every session so the rule is present even before this file is read.

## Watch out for

- `make check-all` must pass before committing (pre-commit hook runs it). Ruff, line length 88, rules `E4 E7 E9 F I` (ignoring `E501 F541`); notebooks excluded.
- Never commit `.env` (API keys). Copy `.env.example`. LLM access goes through LiteLLM, so any supported provider works.
- Be careful editing `data/` JSON/TOML — the framework depends on it.
- Voice/audio-native providers each have their own WebSocket protocol; see `.cursor/rules/audio-native-provider.md` and `src/tau2/voice/audio_native/`.
- `banking_knowledge` requires `--retrieval-config` and the `knowledge` extra (plus sandbox tooling for some configs); see [AGENTS.md](AGENTS.md) and [src/tau2/knowledge/README.md](src/tau2/knowledge/README.md).
