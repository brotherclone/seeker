"""The ``Role`` and ``ReadingGuidance`` classes from schema/seeker.yaml."""

from __future__ import annotations

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from seeker.ontology.base import SeekerModel
from seeker.ontology.reading import Reading, RoleName
from seeker.ontology.types import ModelId


class ReadingGuidance(SeekerModel):
    """The prompt text a role uses for one Reading setting."""

    model_config = ConfigDict(title="ReadingGuidance", json_schema_extra={"class_uri": "seeker:ReadingGuidance"})

    reading: Reading = Field(
        title="reading",
        description="How freely the cards may be interpreted.",
        examples=["literal"],
        json_schema_extra={"slot_uri": "seeker:reading"},
    )
    guidance: str = Field(
        title="guidance",
        min_length=1,
        description="The prompt text that tells the model how to read the cards at this setting.",
        examples=["Read each card as exactly what it names."],
        json_schema_extra={"slot_uri": "seeker:guidance"},
    )


class Role(SeekerModel):
    """One agent role in the pipeline, defined by a versioned YAML file in
    prompts/: its model, persona, standing instructions and per-reading
    guidance."""

    model_config = ConfigDict(title="Role", json_schema_extra={"class_uri": "seeker:Role"})

    role_name: RoleName = Field(
        title="role_name",
        description="Which role in the pipeline this is.",
        examples=["generator"],
        json_schema_extra={"slot_uri": "seeker:roleName"},
    )
    model: ModelId = Field(
        title="model",
        description="The Claude model the role runs on.",
        examples=["claude-opus-5-5"],
        json_schema_extra={"slot_uri": "seeker:model"},
    )
    persona: str = Field(
        title="persona",
        min_length=1,
        description="Who the role speaks as, which sets its taste and its blind spots.",
        examples=["You are an artist-engineer who has shipped instruments and zines."],
        json_schema_extra={"slot_uri": "seeker:persona"},
    )
    system_prompt: str = Field(
        title="system_prompt",
        min_length=1,
        description="The role's standing instructions and rules.",
        examples=["Collide the three cards into ONE idea."],
        json_schema_extra={"slot_uri": "seeker:systemPrompt"},
    )
    reading_guidance: tuple[ReadingGuidance, ...] = Field(
        title="reading_guidance",
        min_length=3,
        max_length=3,
        description="Exactly one guidance text per Reading value.",
        json_schema_extra={"slot_uri": "seeker:readingGuidance"},
    )
    max_output_tokens: int = Field(
        title="max_output_tokens",
        ge=1,
        description="The most output tokens one call of this role may produce.",
        examples=[1200],
        json_schema_extra={"slot_uri": "seeker:maxOutputTokens"},
    )
    temperature: float = Field(
        title="temperature",
        ge=0,
        le=1,
        description="Sampling temperature for the role's calls, from 0 to 1.",
        examples=[1.0],
        json_schema_extra={"slot_uri": "seeker:temperature"},
    )

    @model_validator(mode="before")
    @classmethod
    def _name_missing_readings(cls, raw: object) -> object:
        """Check guidance coverage before field validation, so the error names the
        missing or repeated readings instead of only counting entries."""
        entries = getattr(raw, "get", lambda _key, default=None: default)("reading_guidance")
        if isinstance(entries, (list, tuple)):
            given = [str(getattr(entry, "get", lambda _k, d=None: d)("reading", "")) for entry in entries]
            cls._require_one_per_reading(given)
        return raw

    @model_validator(mode="after")
    def _one_guidance_per_reading(self) -> Role:
        self._require_one_per_reading([g.reading.value for g in self.reading_guidance])
        return self

    @staticmethod
    def _require_one_per_reading(given: list[str]) -> None:
        missing = [r.value for r in Reading if r.value not in given]
        repeated = sorted({g for g in given if given.count(g) > 1})
        if missing or repeated:
            raise PydanticCustomError(
                "reading_guidance",
                "reading_guidance needs exactly one entry per reading; missing: {missing}; repeated: {repeated}",
                {"missing": ", ".join(missing) or "none", "repeated": ", ".join(repeated) or "none"},
            )

    def guidance_for(self, reading: Reading) -> str:
        """The guidance text for ``reading``."""
        return next(g.guidance for g in self.reading_guidance if g.reading is reading)
