"""The LinkML schema is the ontology of record: it must lint clean, describe
every element, and match its committed SHACL and OWL exports."""

import shutil
import subprocess
from pathlib import Path

import pytest
from linkml_runtime.utils.schemaview import SchemaView

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "seeker.yaml"
GENERATED = ROOT / "schema" / "generated"
EXPORTS = {
    "gen-shacl": GENERATED / "seeker.shacl.ttl",
    "gen-owl": GENERATED / "seeker.owl.ttl",
}


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        pytest.skip(f"{name} not installed (install the dev extra)")
    return path


def test_schema_lints_clean() -> None:
    result = subprocess.run(
        [_tool("linkml-lint"), str(SCHEMA)], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_element_is_described() -> None:
    view = SchemaView(str(SCHEMA))
    undescribed: list[str] = []
    for kind, elements in (
        ("class", view.all_classes(imports=False)),
        ("slot", view.all_slots(imports=False)),
        ("type", view.all_types(imports=False)),
        ("enum", view.all_enums(imports=False)),
    ):
        undescribed += [f"{kind} {name}" for name, element in elements.items() if not element.description]
    for enum_name, enum in view.all_enums(imports=False).items():
        undescribed += [
            f"value {enum_name}.{value_name}"
            for value_name, value in enum.permissible_values.items()
            if not value.description
        ]
    assert undescribed == []


@pytest.mark.parametrize("generator", sorted(EXPORTS))
def test_exports_match_schema(generator: str) -> None:
    result = subprocess.run(
        [_tool(generator), str(SCHEMA)], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert result.stdout == EXPORTS[generator].read_text(), (
        f"{EXPORTS[generator].name} is stale: run `make schema`"
    )
