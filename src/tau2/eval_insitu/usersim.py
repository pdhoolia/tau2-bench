"""User-simulator driver for the in-situ harness (Phase 2).

Wraps tau2's canonical ``UserSimulator`` so the in-situ loop drives the *same* user
behavior tau2 evaluates with — parity by reuse, not reimplementation. The agent-under-
test is the live Claude session; this driver plays the counterparty.

Process model: the orchestration is a **Stop hook**, which runs as a fresh process each
turn. So the driver is file-backed — :meth:`save` / :meth:`load` round-trip the
conversation so the next invocation resumes the user-sim's state. Only the user-visible
dialogue (assistant/user text) is kept; the agent's tool calls are internal and the
user simulator never sees them, exactly as in tau2.

Flow:
    driver = UserSimDriver(task, llm)
    opening = driver.opening()            # user's first turn -> the `claude -p` prompt
    driver.save(state_path)
    ... agent responds ...
    driver = UserSimDriver.load(state_path, task, llm)
    user_text, done = driver.respond_to(agent_text)   # next user turn / end-of-convo
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from tau2.data_model.message import AssistantMessage, Message, UserMessage
from tau2.data_model.persona import PersonaConfig
from tau2.data_model.tasks import Task
from tau2.orchestrator.orchestrator import DEFAULT_FIRST_AGENT_MESSAGE
from tau2.user.user_simulator import UserSimulator


class UserSimDriver:
    """Drives a tau2 ``UserSimulator`` one turn at a time, with file-backed state."""

    def __init__(
        self,
        task: Task,
        llm: str,
        *,
        llm_args: Optional[dict] = None,
        persona_config: Optional[PersonaConfig] = None,
        history: Optional[list[Message]] = None,
    ):
        self.task = task
        self.llm = llm
        self.llm_args = llm_args or {}
        self.sim = UserSimulator(
            llm=llm,
            instructions=str(task.user_scenario),
            llm_args=self.llm_args,
            persona_config=persona_config,
        )
        self.history: list[Message] = list(history or [])
        self.state = self.sim.get_init_state(message_history=list(self.history))

    # --- turn generation -----------------------------------------------------

    def opening(self) -> str:
        """The user's first turn: a response to the agent's standard greeting.

        Mirrors tau2, where the agent greets first and the user simulator replies.
        The returned text is the opening `claude -p` prompt for the agent-under-test.
        """
        return self._respond(DEFAULT_FIRST_AGENT_MESSAGE)[0]

    def respond_to(self, agent_text: str) -> tuple[str, bool]:
        """Generate the user's reply to ``agent_text``.

        Returns ``(user_text, done)`` where ``done`` is True if the user ended the
        conversation (tau2 stop/transfer/out-of-scope markers).
        """
        return self._respond(AssistantMessage(role="assistant", content=agent_text))

    def _respond(self, agent_message: AssistantMessage) -> tuple[str, bool]:
        user_msg, self.state = self.sim.generate_next_message(agent_message, self.state)
        done = self.sim.is_stop(user_msg)
        # Keep the user-visible dialogue for state round-tripping.
        self.history.append(agent_message)
        self.history.append(user_msg)
        return (user_msg.content or ""), done

    # --- file-backed state ---------------------------------------------------

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "task_id": self.task.id,
            "llm": self.llm,
            "history": [{"role": m.role, "content": m.content} for m in self.history],
        }
        path.write_text(json.dumps(payload, indent=2))

    @classmethod
    def load(
        cls,
        path: str | Path,
        task: Task,
        llm: str,
        *,
        llm_args: Optional[dict] = None,
        persona_config: Optional[PersonaConfig] = None,
    ) -> "UserSimDriver":
        payload = json.loads(Path(path).read_text())
        history: list[Message] = []
        for m in payload.get("history", []):
            if m["role"] == "assistant":
                history.append(AssistantMessage(role="assistant", content=m["content"]))
            elif m["role"] == "user":
                history.append(UserMessage(role="user", content=m["content"]))
        return cls(
            task,
            llm,
            llm_args=llm_args,
            persona_config=persona_config,
            history=history,
        )
