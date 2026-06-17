"""Convert a `claude -p` stream-json transcript into a tau2 trajectory.

In the in-situ design the whole conversation runs inside a single `claude -p` process
(the Stop hook drives multi-turn continuation), so that process's stream-json stdout
carries the full trajectory: the agent's assistant texts and its MCP tool calls, plus
the tool results returned by the eval-control MCP server.

This adapter turns that stream into the tau2 message shape the evaluator consumes:
an ``AssistantMessage`` carrying the domain ``ToolCall``(s) immediately followed by the
matching ``ToolMessage``(s) (paired by tool_use id, in call order), interleaved with the
agent's user-facing text. Only domain tools (``mcp__<server>__*``) become tau2 tool
calls — internal tools (Bash, scripts, etc.) are not part of the scored trajectory,
matching how the claude_harness bridge treats them.

Pairing is done in two passes (collect ``id -> result`` first, then emit each tool call
with its result by id) so id alignment holds regardless of how results are ordered or
batched in the stream.
"""

from __future__ import annotations

import json

from tau2.agent.claude_harness.cli_runner import _iter_json_events
from tau2.data_model.message import (
    AssistantMessage,
    Message,
    ToolCall,
    ToolMessage,
)


def _result_to_str(content) -> str:
    """Normalize a tool_result content (str | list[block] | obj) to a string."""
    if content is None:
        return "{}"
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", json.dumps(block)))
            else:
                parts.append(str(block))
        return "".join(parts)
    return json.dumps(content)


def _collect_tool_results(stdout: str) -> dict[str, str]:
    """Map tool_use_id -> result string from all user/tool_result events."""
    results: dict[str, str] = {}
    for event in _iter_json_events(stdout):
        if event.get("type") != "user":
            continue
        content = event.get("message", event).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                tid = block.get("tool_use_id")
                if tid:
                    results[tid] = _result_to_str(block.get("content"))
    return results


def _collect_denied_ids(stdout: str) -> set[str]:
    """Tool-use ids the permission system denied (their calls never executed).

    Such denials appear in ``permission_denials`` (typically on the terminal ``result``
    event). The model EMITTED the tool_use but it never ran against the env, so it must
    not enter the scored trajectory — otherwise replay re-executes a call the live run
    never made (and the stored "permission denied" stub mismatches on verification).
    Mirrors the claude_harness bridge's denial handling.
    """
    denied: set[str] = set()
    for event in _iter_json_events(stdout):
        denials = event.get("permission_denials")
        if isinstance(denials, list):
            for d in denials:
                if isinstance(d, dict) and d.get("tool_use_id"):
                    denied.add(d["tool_use_id"])
    return denied


def stream_json_to_trajectory(
    stdout: str,
    mcp_prefix: str,
) -> list[Message]:
    """Assemble a tau2 trajectory from `claude -p` stream-json ``stdout``.

    :param mcp_prefix: the domain MCP tool prefix to keep, e.g.
        ``"mcp__tau2-legal__"``. The prefix is stripped to the bare toolkit name.
    """
    results = _collect_tool_results(stdout)
    denied = _collect_denied_ids(stdout)
    messages: list[Message] = []

    for event in _iter_json_events(stdout):
        if event.get("type") != "assistant":
            continue
        content = event.get("message", event).get("content")
        if not isinstance(content, list):
            if isinstance(content, str) and content.strip():
                messages.append(
                    AssistantMessage(role="assistant", content=content.strip())
                )
            continue

        text_parts = [
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        text = "".join(text_parts).strip() or None

        domain_calls = [
            b
            for b in content
            if isinstance(b, dict)
            and b.get("type") == "tool_use"
            and str(b.get("name", "")).startswith(mcp_prefix)
            and b.get("id") not in denied
        ]

        if domain_calls:
            tool_calls = [
                ToolCall(
                    id=b.get("id", ""),
                    name=b["name"][len(mcp_prefix) :],
                    arguments=b.get("input") or {},
                    requestor="assistant",
                )
                for b in domain_calls
            ]
            messages.append(
                AssistantMessage(role="assistant", content=text, tool_calls=tool_calls)
            )
            # Emit each call's result immediately, by id, in call order.
            for tc in tool_calls:
                messages.append(
                    ToolMessage(
                        id=tc.id,
                        role="tool",
                        content=results.get(tc.id, "{}"),
                        requestor="assistant",
                    )
                )
        elif text:
            messages.append(AssistantMessage(role="assistant", content=text))

    return messages
