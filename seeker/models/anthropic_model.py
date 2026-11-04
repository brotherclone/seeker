"""The real model: Claude through the official ``anthropic`` SDK."""

from __future__ import annotations

import json

import anthropic
from pydantic import SecretStr

from seeker.models.base import LanguageModel, ModelCallFailed, ModelReply, ModelRequest
from seeker.ontology import Usage

NOT_ANSWERS = frozenset({"refusal", "max_tokens"})


class AnthropicModel(LanguageModel):
    """Calls Claude with native JSON-schema output and a cached system block.

    Forcing a tool call is not supported by current models, so the answer
    shape is given as ``output_config.format`` instead. ``client`` can be
    injected (tests pass a stub); otherwise one is built from ``api_key``. SDK
    objects never leave this class: the answer is returned as JSON text and
    usage is mapped to ``Usage``.
    """

    def __init__(self, api_key: SecretStr | None = None, client: object | None = None) -> None:
        if client is None:
            if api_key is None:
                raise ValueError("AnthropicModel needs an api_key or a client")
            client = anthropic.Anthropic(api_key=api_key.get_secret_value())
        self._client = client

    def reply(self, request: ModelRequest) -> ModelReply:
        try:
            response = self._client.messages.create(**self._arguments(request))
        except anthropic.AnthropicError as exc:
            raise ModelCallFailed(f"{type(exc).__name__}: {exc}") from exc

        stop = str(response.stop_reason)
        if stop in NOT_ANSWERS:
            raise ModelCallFailed(f"no usable answer for {request.output.name} (stop reason: {stop})")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise ModelCallFailed(f"model returned no text for {request.output.name} (stop reason: {stop})")
        usage = response.usage
        return ModelReply(
            output_json=text,
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", None) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None) or 0,
            ),
            stop_reason=stop,
        )

    @staticmethod
    def _arguments(request: ModelRequest) -> object:
        """SDK keyword arguments. Plain JSON-like structures exist only here, at the SDK edge."""
        messages = [{"role": "user", "content": request.prompt}]
        if request.retry is not None:
            messages += [
                {"role": "assistant", "content": request.retry.previous_output},
                {"role": "user", "content": request.retry.feedback},
            ]
        return {
            "model": str(request.model),
            "max_tokens": request.max_tokens,
            "system": [{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": {
                "effort": request.effort.value,
                "format": {"type": "json_schema", "schema": json.loads(request.output.json_schema_text)},
            },
        }
