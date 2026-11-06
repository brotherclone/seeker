"""The offline prior-art check against draws."""

from pathlib import Path

import yaml

from seeker.ontology import Draw, DrawBatch
from seeker.works.catalog import WorkNotes
from seeker.works.check import BatchCheck, DrawPriorArt
from vault_fixtures import ROOT, repo_decks, work_note

DRAW = Draw(position=1, axes=("constraint", "medium", "historical-artifact"), home_field="comics",
            drawn_cards=("no-keyboard", "webcomic", "lumigraph"))


def catalog(folder: Path):
    return WorkNotes(folder=folder, deck_set=repo_decks()).catalog()


def test_pair_overlap(tmp_path: Path) -> None:
    work_note(tmp_path, "light comic", cards='["[[lumigraph]]", "[[webcomic]]", "[[tape]]"]')
    (hit,) = DrawPriorArt.of(catalog(tmp_path), DRAW).hits
    assert hit.work_id == "light-comic" and hit.shared == ("webcomic", "lumigraph") and not hit.full


def test_single_shared_card_is_not_prior_art(tmp_path: Path) -> None:
    work_note(tmp_path, "w", cards='["[[webcomic]]"]')
    assert DrawPriorArt.of(catalog(tmp_path), DRAW).hits == ()


def test_full_hit_and_ordering(tmp_path: Path) -> None:
    work_note(tmp_path, "b pair", cards='["[[no-keyboard]]", "[[webcomic]]"]')
    work_note(tmp_path, "a pair", cards='["[[lumigraph]]", "[[no-keyboard]]"]')
    work_note(tmp_path, "z full", cards='["[[lumigraph]]", "[[webcomic]]", "[[no-keyboard]]"]')
    result = DrawPriorArt.of(catalog(tmp_path), DRAW)
    assert [(h.work_id, h.full) for h in result.hits] == [("z-full", True), ("a-pair", False), ("b-pair", False)]
    assert result.has_full_hit


def test_round_1_batch_reports_every_draw(tmp_path: Path) -> None:
    batch = DrawBatch.model_validate(yaml.safe_load((ROOT / "batches" / "2026-11-04-round-1.yaml").read_text()))
    work_note(tmp_path, "fischinger webcomic", cards='["[[webcomic]]", "[[lumigraph]]"]')
    work_note(tmp_path, "granular tree rings", cards='["[[granular-synthesis]]", "[[dendrochronology]]", "[[one-color]]"]')
    check = BatchCheck.run(catalog(tmp_path), batch)
    assert len(check.draws) == 12 and check.work_count == 2
    assert [entry.draw.position for entry in check.draws if entry.hits] == [1, 6]
    assert check.draws[5].hits[0].full
    assert check.draws_with_prior_art == 2
    assert all(entry.hits == () for entry in check.draws if entry.draw.position not in (1, 6))
