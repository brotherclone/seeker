"""A scripted stand-in for a real model, so tests never touch the network."""

from __future__ import annotations

from seeker.models.base import LanguageModel, ModelCallFailed, ModelReply, ModelRequest


class ScriptExhausted(AssertionError):
    """The code under test asked for more replies than the test scripted."""


class ScriptedModel(LanguageModel):
    """Returns scripted replies in order and records every request it receives.

    A scripted ``ModelCallFailed`` is raised instead of returned, to simulate a
    failed call.
    """

    def __init__(self, replies: tuple[ModelReply | ModelCallFailed, ...]) -> None:
        self._replies = list(replies)
        self.requests: list[ModelRequest] = []

    def reply(self, request: ModelRequest) -> ModelReply:
        self.requests.append(request)
        if not self._replies:
            raise ScriptExhausted(f"no scripted reply left for request {len(self.requests)}")
        scripted = self._replies.pop(0)
        if isinstance(scripted, ModelCallFailed):
            raise scripted
        return scripted

    @property
    def remaining(self) -> int:
        return len(self._replies)
