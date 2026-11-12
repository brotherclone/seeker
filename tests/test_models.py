"""The model boundary: ScriptedModel and AnthropicModel (with a stubbed SDK)."""

import inspect
import json
import os
import typing
from types import SimpleNamespace

import anthropic
import pytest

from seeker.generate import IdeaDraft
from seeker.models import (
    AnthropicModel,
    ModelCallFailed,
    ModelReply,
    ModelRequest,
    OutputSpec,
    RetryContext,
    ScriptedModel,
    ScriptExhausted,
)
from seeker.ontology import Effort, Usage

OUTPUT = OutputSpec(
    name="idea_draft",
    json_schema_text=json.dumps(
        {
            "type": "object",
            "properties": {"statement": {"type": "string"}},
            "required": ["statement"],
            "additionalProperties": False,
        }
    ),
)


def request(**overrides: object) -> ModelRequest:
    fields = {
        "model": "claude-haiku-5-5",
        "system": "You are a test.",
        "prompt": "Say something.",
        "output": OUTPUT,
        "max_tokens": 100,
        "effort": "low",
        **overrides,
    }
    return ModelRequest(**fields)


def reply(text: str = "hi") -> ModelReply:
    return ModelReply(
        output_json=json.dumps({"statement": text}),
        usage=Usage(input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_write_tokens=0),
    )


# --- ScriptedModel -------------------------------------------------------------


def test_scripted_replays_in_order_and_records() -> None:
    model = ScriptedModel((reply("one"), reply("two")))
    assert json.loads(model.reply(request()).output_json)["statement"] == "one"
    assert json.loads(model.reply(request(prompt="again")).output_json)["statement"] == "two"
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


def sdk_response(text: str = '{"statement": "ünïcode ok"}', stop: str = "end_turn") -> object:
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking="hm"), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=120, output_tokens=40, cache_read_input_tokens=900, cache_creation_input_tokens=None
        ),
        stop_reason=stop,
    )


def stubbed(messages: StubMessages) -> AnthropicModel:
    return AnthropicModel(client=SimpleNamespace(messages=messages))


def test_anthropic_request_shape_and_reply_mapping() -> None:
    messages = StubMessages(sdk_response())
    result = stubbed(messages).reply(request())
    sent = messages.calls[0]
    assert sent["output_config"]["effort"] == "low"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert sent["messages"] == [{"role": "user", "content": "Say something."}]
    assert not {"tools", "tool_choice", "temperature"} & set(sent)
    assert json.loads(result.output_json) == {"statement": "ünïcode ok"}
    assert result.usage == Usage(input_tokens=120, output_tokens=40, cache_read_tokens=900, cache_write_tokens=0)


def test_anthropic_retry_is_a_plain_follow_up_turn() -> None:
    messages = StubMessages(sdk_response())
    retry = RetryContext(previous_output='{"statement": "a. b."}', feedback="two sentences")
    stubbed(messages).reply(request(retry=retry))
    assert messages.calls[0]["messages"] == [
        {"role": "user", "content": "Say something."},
        {"role": "assistant", "content": '{"statement": "a. b."}'},
        {"role": "user", "content": "two sentences"},
    ]


@pytest.mark.parametrize(("text", "stop", "match"), [("", "end_turn", "no text"), ("{}", "refusal", "refusal"), ("{", "max_tokens", "max_tokens")])
def test_anthropic_unusable_answers_fail(text: str, stop: str, match: str) -> None:
    with pytest.raises(ModelCallFailed, match=match):
        stubbed(StubMessages(sdk_response(text=text, stop=stop))).reply(request())


def test_anthropic_sdk_errors_are_wrapped() -> None:
    error = anthropic.AnthropicError("connection reset")
    with pytest.raises(ModelCallFailed, match="AnthropicError: connection reset"):
        stubbed(StubMessages(error=error)).reply(request())


def test_anthropic_needs_key_or_client() -> None:
    with pytest.raises(ValueError):
        AnthropicModel()


# --- the arguments must match the installed SDK, not just a stub ---------------


def test_arguments_match_the_installed_sdk_signature() -> None:
    """A stub accepts any keyword; this checks against the real SDK so an
    unsupported argument (like the removed `temperature`) fails here, not live."""
    from anthropic.resources.messages import Messages
    from anthropic.types import JSONOutputFormatParam, OutputConfigParam

    retry = RetryContext(previous_output='{"statement": "x"}', feedback="fix it")
    accepted = set(inspect.signature(Messages.create).parameters) - {"self"}
    for req in (request(), request(retry=retry), request(max_searches=2)):
        arguments = AnthropicModel._arguments(req, AnthropicModel._messages(req))
        assert set(arguments) <= accepted, set(arguments) - accepted
        assert set(arguments["output_config"]) <= set(typing.get_type_hints(OutputConfigParam))
        assert set(arguments["output_config"]["format"]) <= set(typing.get_type_hints(JSONOutputFormatParam))
    effort_values = typing.get_args(typing.get_args(typing.get_type_hints(OutputConfigParam)["effort"])[0])
    assert {e.value for e in Effort} == set(effort_values)


def test_idea_draft_schema_is_strict() -> None:
    """Every object closed, every property required, no keywords strict output rejects."""
    schema = json.loads(IdeaDraft.output_spec().json_schema_text)
    banned = {"$ref", "$defs", "title", "examples", "pattern", "minItems", "maxItems", "minLength", "type_uri"}

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif hasattr(node, "items"):
            assert not banned & set(node), banned & set(node)
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert sorted(node["required"]) == sorted(node["properties"])
            for value in node.values():
                walk(value)

    walk(schema)
    assert set(schema["properties"]) == {"statement", "subject", "behavior", "rationale", "card_readings"}


@pytest.mark.skipif(os.environ.get("SEEKER_LIVE") != "1", reason="live API smoke test; set SEEKER_LIVE=1")
def test_live_smoke_haiku() -> None:
    """One real call with the actual IdeaDraft schema, so schema rejections show up here."""
    from seeker.config import SeekerConfig

    model = AnthropicModel(api_key=SeekerConfig.load().api_key())
    result = model.reply(
        request(
            prompt=(
                "Invent one tiny idea. Use card ids a, b, c for the three card readings, in that order. "
                "Answer with the JSON object only."
            ),
            output=IdeaDraft.output_spec(),
            max_tokens=800,
        )
    )
    draft, problems = IdeaDraft.parse(result.output_json)
    assert draft is not None, problems
    assert result.usage.output_tokens > 0


# --- debate-ideas 5.1: web search at the boundary ---------------------------------


def search_block(*urls: str) -> object:
    return SimpleNamespace(
        type="web_search_tool_result",
        content=[SimpleNamespace(type="web_search_result", url=u, title=f"Title {i}") for i, u in enumerate(urls)],
    )


def searched_response(
    content: list[object], stop: str = "end_turn", searches: int = 1, text: str = '{"urls": []}'
) -> object:
    return SimpleNamespace(
        content=[*content, SimpleNamespace(type="text", text=text)] if stop != "pause_turn" else content,
        usage=SimpleNamespace(
            input_tokens=39_000,
            output_tokens=800,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            server_tool_use=SimpleNamespace(web_search_requests=searches, web_fetch_requests=0),
        ),
        stop_reason=stop,
    )


class SequenceMessages(StubMessages):
    def __init__(self, *responses: object) -> None:
        super().__init__()
        self.responses = list(responses)

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_no_search_tool_unless_allowed() -> None:
    messages = StubMessages(sdk_response())
    stubbed(messages).reply(request())
    assert "tools" not in messages.calls[0]


def test_search_tool_carries_the_limit_and_results_are_collected() -> None:
    code = SimpleNamespace(type="code_execution_tool_result", content=SimpleNamespace(stdout="filtered"))
    response = searched_response(
        [SimpleNamespace(type="server_tool_use"), code, search_block("https://a.org/x", "https://b.org/y")], searches=2
    )
    messages = StubMessages(response)
    result = stubbed(messages).reply(request(max_searches=3))
    assert messages.calls[0]["tools"] == [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}]
    assert [str(r.url) for r in result.search_results] == ["https://a.org/x", "https://b.org/y"]
    assert result.result_urls == {"https://a.org/x", "https://b.org/y"}
    assert result.usage.web_search_requests == 2
    assert json.loads(result.output_json) == {"urls": []}


def test_search_error_block_is_no_results() -> None:
    error = SimpleNamespace(type="web_search_tool_result", content=SimpleNamespace(error_code="max_uses_exceeded"))
    result = stubbed(StubMessages(searched_response([error], searches=0))).reply(request(max_searches=1))
    assert result.search_results == ()


def test_unusable_result_urls_are_skipped() -> None:
    result = stubbed(StubMessages(searched_response([search_block("not a url", "https://ok.org")]))).reply(
        request(max_searches=1)
    )
    assert [str(r.url) for r in result.search_results] == ["https://ok.org"]


def test_pause_turn_is_resumed_and_usage_summed() -> None:
    paused = searched_response([search_block("https://a.org")], stop="pause_turn")
    final = searched_response([search_block("https://b.org")])
    messages = SequenceMessages(paused, final)
    result = stubbed(messages).reply(request(max_searches=2))
    assert len(messages.calls) == 2
    assert messages.calls[1]["messages"][-1] == {"role": "assistant", "content": paused.content}
    assert result.usage.input_tokens == 78_000 and result.usage.web_search_requests == 2
    assert result.result_urls == {"https://a.org", "https://b.org"}


def test_pause_turn_gives_up_after_three_resumes() -> None:
    paused = [searched_response([], stop="pause_turn") for _ in range(4)]
    messages = SequenceMessages(*paused)
    with pytest.raises(ModelCallFailed, match="still paused after 3 resumes"):
        stubbed(messages).reply(request(max_searches=1))
    assert len(messages.calls) == 4
