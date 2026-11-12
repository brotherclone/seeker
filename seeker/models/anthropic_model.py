"""The real model: Claude through the official ``anthropic`` SDK."""

from __future__ import annotations

import json

import anthropic
from pydantic import SecretStr, ValidationError

from seeker.models.base import LanguageModel, ModelCallFailed, ModelReply, ModelRequest, SearchResult
from seeker.ontology import Usage

NOT_ANSWERS = frozenset({"refusal", "max_tokens"})
PAUSE = "pause_turn"
MAX_RESUMES = 3
WEB_SEARCH_TOOL = "web_search_20260209"


class AnthropicModel(LanguageModel):
    """Calls Claude with native JSON-schema output and a cached system block.

    Forcing a tool call is not supported by current models, so the answer
    shape is given as ``output_config.format`` instead. When a request allows
    web searches, the server-side search tool is offered with that limit; a
    paused server-tool turn is resumed up to ``MAX_RESUMES`` times. ``client``
    can be injected (tests pass a stub); otherwise one is built from
    ``api_key``. SDK objects never leave this class: the answer is returned as
    JSON text, search results as ``SearchResult``s and usage as ``Usage``.
    """

    def __init__(self, api_key: SecretStr | None = None, client: object | None = None) -> None:
        if client is None:
            if api_key is None:
                raise ValueError("AnthropicModel needs an api_key or a client")
            client = anthropic.Anthropic(api_key=api_key.get_secret_value())
        self._client = client

    def reply(self, request: ModelRequest) -> ModelReply:
        messages = self._messages(request)
        usage = Usage.zero()
        results: list[SearchResult] = []
        for _attempt in range(MAX_RESUMES + 1):
            try:
                response = self._client.messages.create(**self._arguments(request, messages))
            except anthropic.AnthropicError as exc:
                raise ModelCallFailed(f"{type(exc).__name__}: {exc}") from exc
            usage = usage + self._usage(response)
            results += self._search_results(response)
            stop = str(response.stop_reason)
            if stop != PAUSE:
                break
            messages = [*messages, {"role": "assistant", "content": response.content}]
        else:
            raise ModelCallFailed(f"server tool turn still paused after {MAX_RESUMES} resumes for {request.output.name}")

        if stop in NOT_ANSWERS:
            raise ModelCallFailed(f"no usable answer for {request.output.name} (stop reason: {stop})")
        texts = [block.text for block in response.content if block.type == "text"]
        text = (texts[-1] if request.max_searches else "".join(texts)).strip()
        if not text:
            raise ModelCallFailed(f"model returned no text for {request.output.name} (stop reason: {stop})")
        return ModelReply(output_json=text, usage=usage, stop_reason=stop, search_results=tuple(results))

    @staticmethod
    def _usage(response: object) -> Usage:
        usage = response.usage
        server = getattr(usage, "server_tool_use", None)
        return Usage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", None) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None) or 0,
            web_search_requests=getattr(server, "web_search_requests", None) or 0,
        )

    @staticmethod
    def _search_results(response: object) -> list[SearchResult]:
        """Results from every web-search result block. An error result (an object,
        not a list) counts as no results. Other server blocks, such as the
        search tool's own code execution, are skipped."""
        found: list[SearchResult] = []
        for block in response.content:
            if block.type != "web_search_tool_result" or not isinstance(block.content, list):
                continue
            for result in block.content:
                try:
                    found.append(SearchResult(url=result.url, title=getattr(result, "title", None) or ""))
                except ValidationError:
                    continue
        return found

    @staticmethod
    def _messages(request: ModelRequest) -> list[object]:
        """The opening turns: the prompt, and the rejected answer plus feedback on a retry."""
        messages: list[object] = [{"role": "user", "content": request.prompt}]
        if request.retry is not None:
            messages += [
                {"role": "assistant", "content": request.retry.previous_output},
                {"role": "user", "content": request.retry.feedback},
            ]
        return messages

    @staticmethod
    def _arguments(request: ModelRequest, messages: list[object]) -> object:
        """SDK keyword arguments. Plain JSON-like structures exist only here, at the SDK edge."""
        arguments = {
            "model": str(request.model),
            "max_tokens": request.max_tokens,
            "system": [{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": {
                "effort": request.effort.value,
                "format": {"type": "json_schema", "schema": json.loads(request.output.json_schema_text)},
            },
        }
        if request.max_searches:
            arguments["tools"] = [{"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": request.max_searches}]
        return arguments
