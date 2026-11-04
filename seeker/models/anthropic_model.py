"""The real model: Claude through the official ``anthropic`` SDK."""

from __future__ import annotations

import json

import anthropic
from pydantic import SecretStr

from seeker.models.base import LanguageModel, ModelCallFailed, ModelReply, ModelRequest
from seeker.ontology import Usage


class AnthropicModel(LanguageModel):
    """Calls Claude with a forced tool choice and a cached system block.

    ``client`` can be injected (tests pass a stub); otherwise one is built from
    ``api_key``. SDK objects never leave this class: tool input is serialized to
    JSON text and usage is mapped to ``Usage``.
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
        except anthropic.APIError as exc:
            raise ModelCallFailed(f"{type(exc).__name__}: {exc}") from exc
        except anthropic.AnthropicError as exc:
            raise ModelCallFailed(f"{type(exc).__name__}: {exc}") from exc

        call = next((block for block in response.content if block.type == "tool_use"), None)
        if call is None or call.name != request.tool.name:
            raise ModelCallFailed(f"model did not call {request.tool.name} (stop reason: {response.stop_reason})")
        usage = response.usage
        return ModelReply(
            tool_use_id=call.id,
            tool_input_json=json.dumps(call.input, ensure_ascii=False),
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", None) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None) or 0,
            ),
            stop_reason=str(response.stop_reason),
        )

    @staticmethod
    def _arguments(request: ModelRequest) -> object:
        """SDK keyword arguments. Plain JSON-like structures exist only here, at the SDK edge."""
        messages = [{"role": "user", "content": request.prompt}]
        if request.retry is not None:
            messages += [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": request.retry.tool_use_id,
                            "name": request.tool.name,
                            "input": json.loads(request.retry.previous_input_json),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": request.retry.tool_use_id,
                            "is_error": True,
                            "content": request.retry.feedback,
                        }
                    ],
                },
            ]
        return {
            "model": str(request.model),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": [{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "tools": [
                {
                    "name": request.tool.name,
                    "description": request.tool.description,
                    "input_schema": json.loads(request.tool.input_schema_json),
                }
            ],
            "tool_choice": {"type": "tool", "name": request.tool.name},
        }
