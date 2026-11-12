"""What a debate run has spent, priced per model, and whether it has reached its budget."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from seeker.config import PriceTable
from seeker.ontology import DebateRun, ModelId, SeekerModel, Usage


class Charge(SeekerModel):
    """The usage of one recorded unit of work, with the model it ran on."""

    model_config = ConfigDict(title="Charge")

    model: ModelId = Field(description="The model the work ran on.")
    usage: Usage = Field(description="What it consumed.")


class RunCost(SeekerModel):
    """Every charge in a debate run's record."""

    model_config = ConfigDict(title="RunCost")

    charges: tuple[Charge, ...] = Field(default=(), description="One per critique, defense, failure and comparison.")

    @classmethod
    def of(cls, run: DebateRun) -> RunCost:
        charges: list[Charge] = []
        for debate in run.debates:
            charges += [Charge(model=c.model, usage=c.usage) for c in debate.critiques]
            charges.append(Charge(model=debate.defense.model, usage=debate.defense.usage))
        for failure in run.debate_failures:
            charges.append(Charge(model=failure.model, usage=failure.usage))
            charges += [Charge(model=c.model, usage=c.usage) for c in failure.discarded_critiques]
        if run.tournament is not None:
            charges += [Charge(model=c.model, usage=c.usage) for c in run.tournament.comparisons]
        return cls(charges=tuple(charges))

    @property
    def usage(self) -> Usage:
        return Usage.total(tuple(charge.usage for charge in self.charges))

    def usd(self, prices: PriceTable) -> float:
        """Each charge priced at its own model's rates, searches included."""
        return round(sum(prices.cost(charge.model, charge.usage) for charge in self.charges), 6)


class CostMeter:
    """Checks a run's recorded spend against its budget before each debate or comparison."""

    def __init__(self, prices: PriceTable, budget_usd: float) -> None:
        self.prices = prices
        self.budget_usd = budget_usd

    def spent(self, run: DebateRun) -> float:
        return RunCost.of(run).usd(self.prices)

    def reached(self, run: DebateRun) -> bool:
        return self.spent(run) >= self.budget_usd

    def totals(self, run: DebateRun) -> DebateRun:
        """The run with its usage and estimated cost recomputed from its records."""
        cost = RunCost.of(run)
        return run.model_copy(update={"usage": cost.usage, "estimated_cost_usd": cost.usd(self.prices)})
