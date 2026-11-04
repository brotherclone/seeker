"""Loading a role from its YAML file in prompts/, with the file's digest."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import ConfigDict, Field, ValidationError

from seeker.ontology import Role, SeekerModel, Sha256Digest


class RoleFileError(Exception):
    """A role file is missing, malformed, or not a valid Role."""


class LoadedRole(SeekerModel):
    """A validated Role together with where it came from and its digest."""

    model_config = ConfigDict(title="LoadedRole")

    path: Path = Field(description="The role file.")
    digest: Sha256Digest = Field(description="SHA-256 of the file's bytes.")
    role: Role

    @classmethod
    def load(cls, path: Path) -> LoadedRole:
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise RoleFileError(f"{path}: cannot read role file ({exc.strerror})") from exc
        try:
            raw = yaml.safe_load(data.decode("utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError) as exc:
            raise RoleFileError(f"{path}: invalid YAML: {' '.join(str(exc).split())}") from exc
        try:
            role = Role.model_validate(raw)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(p) for p in error['loc']) or 'role'}: {error['msg']}" for error in exc.errors()
            )
            raise RoleFileError(f"{path}: {details}") from exc
        return cls(path=path, digest=hashlib.sha256(data).hexdigest(), role=role)
