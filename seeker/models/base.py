"""The language-model boundary: what Seeker asks a model and what it gets back.

Every role talks to a model through ``LanguageModel.reply``. Structured output
uses the API's native JSON-schema output format: the model answers with JSON
text matching an ``OutputSpec``, which the caller parses into Pydantic models,
so no dict-shaped payload crosses this boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import ConfigDict, Field

from seeker.ontology import Effort, ModelId, SeekerModel, Url, Usage


class ModelCallFailed(Exception):
    """The model could not be called, refused, or returned no JSON answer."""


class OutputSpec(SeekerModel):
    """The JSON shape a role's answer must take."""

    model_config = ConfigDict(title="OutputSpec")

    name: str = Field(pattern="^[a-z_]+$", description="A name for the answer shape, for logs and errors.")
    json_schema_text: str = Field(min_length=2, description="Strict JSON Schema of the answer, as JSON text.")


class SearchResult(SeekerModel):
    """One page a server-side web search returned during a call."""

    model_config = ConfigDict(title="SearchResult")

    url: Url = Field(description="The result's address, exactly as the search returned it.")
    title: str = Field(default="", description="The result's page title, when the search gave one.")


class RetryContext(SeekerModel):
    """A previous, invalid answer and the problems to fix, sent back as a follow-up turn."""

    model_config = ConfigDict(title="RetryContext")

    previous_output: str = Field(min_length=1, description="The rejected answer, exactly as returned.")
    feedback: str = Field(min_length=1, description="Why it was rejected and what to fix.")


class ModelRequest(SeekerModel):
    """One call to a model: system instructions, one user prompt, an optional
    retry exchange, and the JSON shape the answer must take."""

    model_config = ConfigDict(title="ModelRequest")

    model: ModelId = Field(description="Model to call.")
    system: str = Field(min_length=1, description="System instructions; cached across a generation.")
    prompt: str = Field(min_length=1, description="The user message.")
    output: OutputSpec
    max_tokens: int = Field(ge=1, description="Output token limit.")
    effort: Effort = Field(description="How much effort the model puts into the answer.")
    retry: RetryContext | None = Field(default=None, description="Present when re-asking after an invalid answer.")
    max_searches: int = Field(
        default=0, ge=0, description="Web searches this call may run; 0 means the search tool is not offered."
    )


class ModelReply(SeekerModel):
    """What came back: the answer as JSON text, and what it cost."""

    model_config = ConfigDict(title="ModelReply")

    output_json: str = Field(min_length=1, description="The answer, as JSON text.")
    usage: Usage
    stop_reason: str = Field(default="end_turn", description="Why the model stopped.")
    search_results: tuple[SearchResult, ...] = Field(
        default=(), description="Every page the call's web searches returned, in the order returned."
    )

    @property
    def result_urls(self) -> frozenset[str]:
        return frozenset(str(result.url) for result in self.search_results)


class LanguageModel(ABC):
    """Anything that can answer a ModelRequest."""

    @abstractmethod
    def reply(self, request: ModelRequest) -> ModelReply:
        """Answer ``request``, or raise ModelCallFailed."""
