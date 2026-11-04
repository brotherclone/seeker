"""The language-model boundary: what Seeker asks a model and what it gets back.

Every role talks to a model through ``LanguageModel.reply``. Structured output
travels as JSON text produced by a forced tool call, and is parsed into
Pydantic models by the caller, so no dict-shaped payload crosses this boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import ConfigDict, Field

from seeker.ontology import ModelId, SeekerModel, Usage


class ModelCallFailed(Exception):
    """The model could not be called, or did not answer through the tool."""


class ToolSpec(SeekerModel):
    """The single tool a role must answer through."""

    model_config = ConfigDict(title="ToolSpec")

    name: str = Field(pattern="^[a-z_]+$", description="Tool name the model must call.")
    description: str = Field(min_length=1, description="What the tool is for, shown to the model.")
    input_schema_json: str = Field(min_length=2, description="JSON Schema of the tool input, as JSON text.")


class RetryContext(SeekerModel):
    """A previous, invalid answer and the problems to fix, sent back as a tool result."""

    model_config = ConfigDict(title="RetryContext")

    tool_use_id: str = Field(min_length=1, description="Id of the rejected tool call.")
    previous_input_json: str = Field(min_length=2, description="The rejected tool input, as JSON text.")
    feedback: str = Field(min_length=1, description="Why it was rejected and what to fix.")


class ModelRequest(SeekerModel):
    """One call to a model: system instructions, one user prompt, an optional
    retry exchange, and the tool the answer must come through."""

    model_config = ConfigDict(title="ModelRequest")

    model: ModelId = Field(description="Model to call.")
    system: str = Field(min_length=1, description="System instructions; cached across a generation.")
    prompt: str = Field(min_length=1, description="The user message.")
    tool: ToolSpec
    max_tokens: int = Field(ge=1, description="Output token limit.")
    temperature: float = Field(ge=0, le=1, description="Sampling temperature.")
    retry: RetryContext | None = Field(default=None, description="Present when re-asking after an invalid answer.")


class ModelReply(SeekerModel):
    """What came back: the tool input as JSON text, and what it cost."""

    model_config = ConfigDict(title="ModelReply")

    tool_use_id: str = Field(min_length=1, description="Id of the tool call, needed to retry.")
    tool_input_json: str = Field(min_length=2, description="The tool input, as JSON text.")
    usage: Usage
    stop_reason: str = Field(default="tool_use", description="Why the model stopped.")


class LanguageModel(ABC):
    """Anything that can answer a ModelRequest."""

    @abstractmethod
    def reply(self, request: ModelRequest) -> ModelReply:
        """Answer ``request``, or raise ModelCallFailed."""
