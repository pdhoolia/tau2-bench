"""claude_harness: drive a Claude Code domain harness as a tau2 agent.

See agent.py for the design. Public surface is the factory used by the registry.
"""

from tau2.agent.claude_harness.agent import (
    ClaudeHarnessAgent,
    ClaudeHarnessAgentState,
    create_claude_harness_agent,
)

__all__ = [
    "ClaudeHarnessAgent",
    "ClaudeHarnessAgentState",
    "create_claude_harness_agent",
]
