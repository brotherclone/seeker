"""The five debate roles, loaded together and checked before any call is made."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import ConfigDict, Field, model_validator

from seeker.config import PriceTable
from seeker.generate.role_file import LoadedRole, RoleFileError
from seeker.ontology import RoleDigest, RoleName, SeekerModel


class DebateRoleError(Exception):
    """The debate roles cannot be used together."""


class IdenticalCritics(DebateRoleError):
    def __init__(self, first: LoadedRole, second: LoadedRole) -> None:
        super().__init__(
            f"{first.path} and {second.path} name the same model and persona; "
            "critics must differ in at least one, so they do not agree by construction"
        )


class UnpricedRole(DebateRoleError):
    def __init__(self, role: LoadedRole) -> None:
        super().__init__(
            f"{role.path}: model {role.role.model} has no entry in the price table (seeker.yaml: prices.models)"
        )


class DebateRoles(SeekerModel):
    """The prosecutor, skeptic, taste critic, advocate and judge, each with its file's digest."""

    model_config = ConfigDict(title="DebateRoles")

    CRITICS: ClassVar[tuple[RoleName, ...]] = (RoleName.PROSECUTOR, RoleName.SKEPTIC, RoleName.TASTE_CRITIC)
    ALL: ClassVar[tuple[RoleName, ...]] = (*CRITICS, RoleName.ADVOCATE, RoleName.JUDGE)

    roles: tuple[LoadedRole, ...] = Field(min_length=5, max_length=5, description="One per debate role, in ALL order.")

    @model_validator(mode="after")
    def _one_each(self) -> DebateRoles:
        names = tuple(loaded.role.role_name for loaded in self.roles)
        if names != self.ALL:
            raise ValueError(f"expected roles {[r.value for r in self.ALL]}, got {[n.value for n in names]}")
        return self

    @classmethod
    def load(cls, prompts: Path, prices: PriceTable) -> DebateRoles:
        """Load ``prompts/<role>.yaml`` for every debate role and check them as a set."""
        loaded = []
        for name in cls.ALL:
            role = LoadedRole.load(prompts / f"{name.value}.yaml")
            if role.role.role_name is not name:
                raise RoleFileError(f"{role.path}: role_name is {role.role.role_name.value}, expected {name.value}")
            loaded.append(role)
        roles = cls(roles=tuple(loaded))
        roles.check(prices)
        return roles

    def check(self, prices: PriceTable) -> None:
        """Raise if two critics share a voice or any role's model is unpriced."""
        critics = [self.role(name) for name in self.CRITICS]
        for i, first in enumerate(critics):
            for second in critics[i + 1 :]:
                if (first.role.model, first.role.persona) == (second.role.model, second.role.persona):
                    raise IdenticalCritics(first, second)
        for loaded in self.roles:
            if prices.price_for(loaded.role.model) is None:
                raise UnpricedRole(loaded)

    def role(self, name: RoleName) -> LoadedRole:
        return next(loaded for loaded in self.roles if loaded.role.role_name is name)

    @property
    def digests(self) -> tuple[RoleDigest, ...]:
        return tuple(RoleDigest(role_name=r.role.role_name, role_digest=r.digest) for r in self.roles)
