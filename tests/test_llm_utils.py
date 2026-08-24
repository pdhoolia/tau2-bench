import pytest

from tau2.data_model.message import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from tau2.environment.tool import Tool, as_tool
from tau2.utils.llm_utils import generate


@pytest.fixture
def model() -> str:
    return "gpt-4o-mini"


@pytest.fixture
def messages() -> list[Message]:
    messages = [
        SystemMessage(role="system", content="You are a helpful assistant."),
        UserMessage(role="user", content="What is the capital of the moon?"),
    ]
    return messages


@pytest.fixture
def tool() -> Tool:
    def calculate_square(x: int) -> int:
        """Calculate the square of a number.
            Args:
            x (int): The number to calculate the square of.
        Returns:
            int: The square of the number.
        """
        return x * x

    return as_tool(calculate_square)


@pytest.fixture
def tool_call_messages() -> list[Message]:
    messages = [
        SystemMessage(role="system", content="You are a helpful assistant."),
        UserMessage(
            role="user",
            content="What is the square of 5? Just give me the number, no explanation.",
        ),
    ]
    return messages


def test_generate_no_tool_call(model: str, messages: list[Message]):
    response = generate(model, messages)
    assert isinstance(response, AssistantMessage)
    assert response.content is not None


def test_generate_tool_call(model: str, tool_call_messages: list[Message], tool: Tool):
    response = generate(model, tool_call_messages, tools=[tool])
    assert isinstance(response, AssistantMessage)
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "calculate_square"
    assert response.tool_calls[0].arguments == {"x": 5}
    follow_up_messages = [
        response,
        ToolMessage(role="tool", id=response.tool_calls[0].id, content="25"),
    ]
    response = generate(
        model,
        tool_call_messages + follow_up_messages,
        tools=[tool],
    )
    assert isinstance(response, AssistantMessage)
    assert response.tool_calls is None
    assert response.content == "25"


def test_route_via_strata(monkeypatch):
    from tau2.runner.batch import _current_simulation_id
    from tau2.utils import llm_utils

    monkeypatch.setattr(llm_utils, "STRATA_BASE", "http://strata:8080")
    monkeypatch.setattr(llm_utils, "STRATA_CALLS", {"agent_response"})
    token = _current_simulation_id.set("sim-1")
    try:
        kwargs = {"temperature": 0.0}
        llm_utils._route_via_strata(kwargs, "agent_response")
        assert kwargs["api_base"] == "http://strata:8080/c/tau2-sim-1/litellm/v1"
        assert kwargs["api_key"] == llm_utils.STRATA_API_KEY
        assert kwargs["extra_body"]["metadata"] == {
            "task": "agent_response",
            "user_id": "sim-1",
        }
        # Roles not in STRATA_CALLS are untouched.
        other = {"temperature": 0.0}
        llm_utils._route_via_strata(other, "user_simulator_response")
        assert other == {"temperature": 0.0}
        # Explicit caller api_base wins.
        explicit = {"api_base": "http://elsewhere/v1"}
        llm_utils._route_via_strata(explicit, "agent_response")
        assert explicit["api_base"] == "http://elsewhere/v1"
    finally:
        _current_simulation_id.reset(token)
