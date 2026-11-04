"""House style for the seeker package: object-oriented Pydantic models, no
dataclasses, and no generic typing above the primitive level."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "seeker"
SOURCES = sorted(PACKAGE.rglob("*.py"))

FORBIDDEN_NAMES = {
    "dataclass": "use a Pydantic model, not a dataclass",
    "dataclasses": "use a Pydantic model, not a dataclass",
    "NamedTuple": "use a Pydantic model, not a NamedTuple",
    "namedtuple": "use a Pydantic model, not a namedtuple",
    "TypedDict": "use a Pydantic model, not a TypedDict",
    "Any": "name the type; Any is not allowed",
    "Generic": "no Generic classes above the primitive level",
    "TypeVar": "no TypeVar-parameterized types above the primitive level",
    "Dict": "no dict-shaped payloads; use a model",
}
FORBIDDEN_SUBSCRIPTS = {"dict", "Dict", "Mapping", "MutableMapping"}


def violations(source: Path) -> list[str]:
    tree = ast.parse(source.read_text(), filename=str(source))
    label = source.relative_to(PACKAGE.parent) if source.is_relative_to(PACKAGE.parent) else source.name
    found: list[str] = []
    for node in ast.walk(tree):
        where = f"{label}:{getattr(node, 'lineno', '?')}"
        if isinstance(node, ast.Import):
            found += [
                f"{where}: import {alias.name} ({FORBIDDEN_NAMES[alias.name]})"
                for alias in node.names
                if alias.name in FORBIDDEN_NAMES
            ]
        elif isinstance(node, ast.ImportFrom):
            if node.module in FORBIDDEN_NAMES:
                found.append(f"{where}: from {node.module} ({FORBIDDEN_NAMES[node.module]})")
            found += [
                f"{where}: {alias.name} ({FORBIDDEN_NAMES[alias.name]})"
                for alias in node.names
                if alias.name in FORBIDDEN_NAMES
            ]
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            found.append(f"{where}: .{node.attr} ({FORBIDDEN_NAMES[node.attr]})")
        elif isinstance(node, ast.Subscript):
            target = node.value
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", None)
            if name in FORBIDDEN_SUBSCRIPTS:
                found.append(f"{where}: {name}[...] (no dict-shaped payloads; use a model)")
    return found


@pytest.mark.parametrize("source", SOURCES, ids=lambda p: str(p.relative_to(PACKAGE.parent)))
def test_house_style(source: Path) -> None:
    assert violations(source) == []


def test_style_check_catches_violations(tmp_path: Path) -> None:
    bad = tmp_path / "probe.py"
    bad.write_text(
        "from dataclasses import dataclass\n"
        "from typing import Any, TypedDict\n"
        "payload: dict[str, Any] = {}\n"
    )
    found = violations(bad)
    assert len(found) == 5, found
    assert any("dict[...]" in line for line in found)
