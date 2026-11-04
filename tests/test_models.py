"""The model boundary: ScriptedModel and AnthropicModel (with a stubbed SDK)."""

import json
import os
from types import SimpleNamespace

import anthropic
import pytest
from pydantic import SecretStr

from seeker.models import (
    AnthropicModel,
    ModelCallFailed,
    ModelReply,
    ModelRequest,
    RetryContext,
    ScriptedModel,
    ScriptExhausted,
    ToolSpec,
)
from seeker.ontology import Usage

TOOL = ToolSpec(
    name="submit_idea",
    description="Submit one idea.",
    input_schema_json=json.dumps({"type": "object", "properties": {"statement": {"type": "string"}}}),
)


def request(**overrides: object) -> ModelRequest:
    fields = {
        "model": "claude-haiku-5-5",
        "system": "You are a test.",
        "prompt": "Say something.",
        "tool": TOOL,
        "max_tokens": 100,
        "effort": "low",
        **overrides,
    }
    return ModelRequest(**fields)


def reply(text: str = "hi") -> ModelReply:
    return ModelReply(
        tool_use_id="toolu_1",
        tool_input_json=json.dumps({"statement": text}),
        usage=Usage(input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_write_tokens=0),
    )


# --- ScriptedModel -------------------------------------------------------------


def test_scripted_replays_in_order_and_records() -> None:
    model = ScriptedModel((reply("one"), reply("two")))
    assert json.loads(model.reply(request()).tool_input_json)["statement"] == "one"
    assert json.loads(model.reply(request(prompt="again")).tool_input_json)["statement"] == "two"
    assert [r.prompt for r in model.requests] == ["Say something.", "again"]
    assert model.remaining == 0


def test_scripted_raises_scripted_failures_and_exhaustion() -> None:
    model = ScriptedModel((ModelCallFailed("boom"),))
    with pytest.raises(ModelCallFailed, match="boom"):
        model.reply(request())
    with pytest.raises(ScriptExhausted):
        model.reply(request())


# --- AnthropicModel with a stub client -------------------------------------------


class StubMessages:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def sdk_response(name: str = "submit_idea", cache_read: int | None = 900) -> object:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="thinking"),
            SimpleNamespace(type="tool_use", id="toolu_9", name=name, input={"statement": "ünïcode ok"}),
        ],
        usage=SimpleNamespace(
            input_tokens=120, output_tokens=40, cache_read_input_tokens=cache_read, cache_creation_input_tokens=None
        ),
        stop_reason="tool_use",
    )


def stubbed(messages: StubMessages) -> AnthropicModel:
    return AnthropicModel(client=SimpleNamespace(messages=messages))


def test_anthropic_request_shape_and_reply_mapping() -> None:
    messages = StubMessages(sdk_response())
    result = stubbed(messages).reply(request())
    sent = messages.calls[0]
    assert sent["tool_choice"] == {"type": "tool", "name": "submit_idea", "disable_parallel_tool_use": True}
    assert sent["output_config"] == {"effort": "low"}
    assert "temperature" not in sent
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert sent["tools"][0]["input_schema"]["type"] == "object"
    assert sent["messages"] == [{"role": "user", "content": "Say something."}]
    assert result.tool_use_id == "toolu_9"
    assert json.loads(result.tool_input_json) == {"statement": "ünïcode ok"}
    assert result.usage == Usage(input_tokens=120, output_tokens=40, cache_read_tokens=900, cache_write_tokens=0)


def test_anthropic_retry_sends_tool_use_and_error_result() -> None:
    messages = StubMessages(sdk_response())
    retry = RetryContext(tool_use_id="toolu_1", previous_input_json='{"statement": "a. b."}', feedback="two sentences")
    stubbed(messages).reply(request(retry=retry))
    user, assistant, result = messages.calls[0]["messages"]
    assert assistant["content"][0] == {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "submit_idea",
        "input": {"statement": "a. b."},
    }
    assert result["content"][0]["is_error"] is True
    assert result["content"][0]["content"] == "two sentences"


def test_anthropic_missing_tool_call_fails() -> None:
    with pytest.raises(ModelCallFailed, match="did not call submit_idea"):
        stubbed(StubMessages(sdk_response(name="other"))).reply(request())


def test_anthropic_sdk_errors_are_wrapped() -> None:
    error = anthropic.AnthropicError("connection reset")
    with pytest.raises(ModelCallFailed, match="AnthropicError: connection reset"):
        stubbed(StubMessages(error=error)).reply(request())


def test_anthropic_needs_key_or_client() -> None:
    with pytest.raises(ValueError):
        AnthropicModel()


@pytest.mark.skipif(os.environ.get("SEEKER_LIVE") != "1", reason="live API smoke test; set SEEKER_LIVE=1")
def test_live_smoke_haiku() -> None:
    from seeker.config import SeekerConfig

    model = AnthropicModel(api_key=SeekerConfig.load().api_key())
    result = model.reply(request(prompt="Call submit_idea with statement 'ok'."))
    assert "statement" in json.loads(result.tool_input_json)
    assert result.usage.output_tokens > 0


# --- the arguments must match the installed SDK, not just a stub ---------------


def test_arguments_match_the_installed_sdk_signature() -> None:
    """A stub accepts any keyword; this checks against the real SDK so an
    unsupported argument (like the removed `temperature`) fails here, not live."""
    import inspect
    import typing

    from anthropic.resources.messages import Messages
    from anthropic.types import OutputConfigParam, ToolChoiceToolParam

    retry = RetryContext(tool_use_id="toolu_1", previous_input_json='{"statement": "x"}', feedback="fix it")
    for req in (request(), request(retry=retry)):
        arguments = AnthropicModel._arguments(req)
        accepted = set(inspect.signature(Messages.create).parameters) - {"self"}
        assert set(arguments) <= accepted, set(arguments) - accepted
        assert set(arguments["output_config"]) <= set(typing.get_type_hints(OutputConfigParam))
        assert set(arguments["tool_choice"]) <= set(typing.get_type_hints(ToolChoiceToolParam))
        effort_values = typing.get_args(typing.get_args(typing.get_type_hints(OutputConfigParam)["effort"])[0])
        from seeker.ontology import Effort

        assert {e.value for e in Effort} == set(effort_values)
