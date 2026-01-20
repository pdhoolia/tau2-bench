# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

τ²-Bench (tau2-bench) is a Python benchmark framework for evaluating conversational customer service agents in dual-control environments. It simulates interactions between an agent, a user simulator, and a domain environment across multiple domains (airline, retail, telecom).

## Common Commands

```bash
# Install in development mode (recommended)
pip install -e .

# Run tests
make test
pytest tests/test_domains/airline/  # specific domain tests
pytest tests/test_agent.py          # specific component

# Lint and format
make lint        # check with ruff
make format      # format with ruff
make lint-fix    # auto-fix linting issues
make check-all   # run both lint and format

# Run agent evaluation
tau2 run --domain airline --agent-llm gpt-4.1 --user-llm gpt-4.1 --num-trials 1 --num-tasks 5

# Interactive play mode
tau2 play

# View results
tau2 view

# View domain API docs (opens at http://127.0.0.1:8004/redoc)
tau2 domain <domain>

# Environment CLI for testing tools
make env-cli
```

## Architecture

### Core Components

- **Orchestrator** (`src/tau2/orchestrator/`): Main simulation loop managing agent↔user↔environment message flow
- **Agent** (`src/tau2/agent/`): Agent implementations. `LLMAgent` is the standard agent; `LLMSoloAgent` and `LLMGTAgent` support ablation studies
- **User Simulator** (`src/tau2/user/`): LLM-based user simulator that acts as the customer
- **Domains** (`src/tau2/domains/`): Domain-specific implementations (mock, airline, retail, telecom)
- **Environment** (`src/tau2/environment/`): Environment state and task management
- **Evaluator** (`src/tau2/evaluator/`): Performance evaluation with action, communication, and environment outcome evaluators
- **Gym** (`src/tau2/gym/`): Gymnasium-compatible interface for RL training

### Domain Structure

Each domain in `src/tau2/domains/<domain>/` contains:
- `data_model.py`: Domain-specific data structures
- `tools.py`: Agent tools/API endpoints
- `user_tools.py`: Optional user simulator tools
- `environment.py`: Environment setup and task definitions

Domain data lives in `data/tau2/domains/<domain>/` with:
- `tasks.json`: Task definitions
- `split_tasks.json`: Train/test/base splits
- `policy.md`: Agent policy guidelines
- `db.json` or `db.toml`: Domain database

### Registry Pattern

Agents and users are registered via `src/tau2/registry.py`:
```python
registry.register_agent(MyAgent, "my_agent")
```

Then invoked with `--agent my_agent` in CLI commands.

### Configuration

Defaults are in `src/tau2/config.py`. Key settings:
- `DEFAULT_MAX_STEPS = 200`
- `DEFAULT_MAX_CONCURRENCY = 3`
- `LLM_CACHE_ENABLED = False` (set to True with Redis for caching)

LLM providers are managed through LiteLLM. API keys go in `.env` (copy from `.env.example`).

## Key Patterns

### Running Ablations (telecom domain)

```bash
# No-user mode
tau2 run --domain telecom --agent llm_agent_solo --agent-llm gpt-4.1 --user dummy_user

# Oracle-plan mode
tau2 run --domain telecom --agent llm_agent_gt --agent-llm gpt-4.1 --user-llm gpt-4.1
```

### Workflow Policy Variant

```bash
tau2 run --domain telecom-workflow --agent-llm gpt-4.1 --user-llm gpt-4.1
```

### Leaderboard Submission

Run all three domains with identical LLM settings, then:
```bash
tau2 submit prepare data/tau2/simulations/my_model_*.json --output ./my_submission
tau2 submit validate ./my_submission
```

## Experiments

Experimental code goes in `src/experiments/`. Each experiment should be self-contained with its own README. Current experiments:
- `agentify_tau_bench/`: A2A protocol implementation
- `hyperparam/`: Hyperparameter optimization

## Commit Conventions

This project uses Release Please with conventional commits:
- `feat:` - new features
- `fix:` - bug fixes
- `docs:` - documentation
- `test:` - test changes
- `refactor:` - code refactoring

## Available Skills

- **plantuml**: Enables Claude Code to generate PlantUML diagrams for visual representation of system architectures, workflows, and processes.
- **design-doc-mermaid**: Allows Claude Code to create design documents featuring Mermaid diagrams.
- **sdlc-skill**: Spec-First, Agent-Implemented SDLC. Guides Claude Code through a structured design-before-code workflow: Intent → HLD → ADR-Lite → Implementation Spec → Code → Validation Tests, with human review gates at each phase.
- ⁠**system-design-skill**: Analyze distributed system designs for scalability, reliability, performance, and security. Produce structured review documents with gaps and actionable recommendations.

## Skills Usage Policy

Proactively activate these skills when:

- **plantuml**: User asks for diagrams or architecture visuals
- **design-doc-mermaid**: User wants to generate design documents with Mermaid diagrams
- **sdlc-skill**: User mentions "SDLC", "spec-first", "design docs", or "implementation spec"; wants to start or continue a new feature/project with structured design; needs requirements-to-code traceability; or requests documented architectural decisions with review checkpoints.
⁠- **system-design-skill**: User asks for: "review my system design", "analyze this architecture", "what are the gaps", "system design recommendations", "scalability review", "reliability analysis".
