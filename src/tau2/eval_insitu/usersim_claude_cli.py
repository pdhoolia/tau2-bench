"""A `claude -p`-backed user simulator (zero-setup gateway fallback).

Subclasses tau2's :class:`UserSimulator` so the user persona/guidelines (the system
prompt) are *identical* to the canonical simulator — only the transport changes: the next
user turn is produced by a one-shot ``claude -p`` call instead of a LiteLLM completion.

This lets the whole in-situ loop run on a Claude subscription with no MLX server and no
API key — handy for demos and quick iteration. For faithful, cost-controlled benchmarking
prefer the local MLX / proxy providers (see ``model_gateway``).

Tools are not supported on this backend (the OpenAI/Anthropic tool-call plumbing is
bypassed); domains whose user simulator needs tools (e.g. telecom) should use a LiteLLM
provider instead.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from loguru import logger

from tau2.data_model.message import (
    AssistantMessage,
    MultiToolMessage,
    ToolMessage,
    UserMessage,
)
from tau2.user.user_simulator import UserSimulator
from tau2.user.user_simulator_base import OUT_OF_SCOPE, STOP, TRANSFER

_INSTRUCTION = (
    "Reply with ONLY your next message as the customer — no labels, no quotes, no "
    f"meta-commentary. When your task is complete or you want to end the conversation, "
    f"include the token {STOP} (use {TRANSFER} to ask for a human, {OUT_OF_SCOPE} if the "
    "request is out of scope)."
)


class ClaudeCliUserSimulator(UserSimulator):
    """User simulator whose turns come from ``claude -p`` rather than LiteLLM."""

    def __init__(
        self,
        *args,
        claude_bin: str = "claude",
        cli_model: Optional[str] = None,
        timeout: float = 120.0,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if self.tools:
            raise ValueError(
                "ClaudeCliUserSimulator does not support user tools; use a LiteLLM "
                "provider for tool-using user simulators."
            )
        self._claude_bin = claude_bin
        self._cli_model = cli_model
        self._timeout = timeout

    def _generate_next_message(self, message, state) -> UserMessage:
        # Mirror the parent's incoming-message accumulation so state/history match.
        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        elif isinstance(message, ToolMessage):
            state.messages.append(message)
        elif message.has_content() or message.is_tool_call():
            state.messages.append(message)

        text = self._run_claude(state)
        return UserMessage(role="user", content=text)

    def _render_dialogue(self, state) -> str:
        lines = []
        for m in state.messages:
            if isinstance(m, AssistantMessage) and m.content:
                lines.append(f"Support agent: {m.content}")
            elif isinstance(m, UserMessage) and m.content:
                lines.append(f"Customer (you): {m.content}")
        return "\n".join(lines)

    def _run_claude(self, state) -> str:
        prompt = f"{self._render_dialogue(state)}\n\n{_INSTRUCTION}"
        cmd = [
            self._claude_bin,
            "-p",
            prompt,
            "--append-system-prompt",
            self.system_prompt,
            "--max-turns",
            "1",
        ]
        if self._cli_model:
            cmd += ["--model", self._cli_model]
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._timeout
            )
        except subprocess.TimeoutExpired:
            logger.warning("claude -p user-sim timed out; ending conversation")
            return STOP
        if res.returncode != 0:
            logger.warning(
                f"claude -p user-sim failed (rc={res.returncode}): "
                f"{res.stderr.strip()[:200]}"
            )
            return STOP
        return res.stdout.strip()
