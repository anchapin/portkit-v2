"""Quark's QoL residue classes are explained (#465; the #287 Quark gauntlet split 3).

Quark is a content mod: most of its residue is content the converter has still
to convert (block, item, recipe, loot on the board), and that is not this
slice's business. This slice is the residue Quark's *QoL* code produces --
inventory sorting, reach-around placing and the like: gameplay code with no
convertible content. Those classes have to be explained kinds with a
documented reason in the shared registry (``portkit.agent.residue.SKIP_KINDS``),
so the residue agent skips them instead of burning a session on them, and so
#277 rule 6 counts them as explained (the #279 pattern: nothing Bedrock can
hold).

The committed board (``docs/gauntlet.md``) and the banked baseline
(``fixtures/real/gauntlet-baseline.json``) are the evidence: the Quark row is
read from them here, so a re-bank that drops the row or leaves a QoL class
unexplained is caught.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from portkit import gauntlet
from portkit.agent.residue import SKIP_KINDS

ROOT = Path(__file__).resolve().parents[1]

# The residue classes Quark's QoL code produces: the gameplay code itself, the
# assets only that code draws, and the texts only that code shows. Each one is
# in the shared registry with a documented reason.
QOL_KINDS = ("java_code", "java_only_asset", "code_only", "lang_code_string")

# The content classes a content mod still has to convert: not this slice, and
# never to be explained away.
CONTENT_KINDS = ("block", "item", "recipe", "loot", "sound", "texture_animation")


# --- the shared registry ---------------------------------------------------------

@pytest.mark.parametrize("kind", QOL_KINDS)
def test_every_qol_residue_class_is_an_explained_kind(kind):
    assert kind in SKIP_KINDS, f"{kind} is residue a QoL feature produces and has no documented reason"
    reason = SKIP_KINDS[kind]
    assert isinstance(reason, str) and reason.strip(), f"{kind} has no reason text"


def test_the_gameplay_code_of_a_content_mod_is_explained():
    # A QoL feature (inventory sorting, reach-around placing) is Java code
    # with no convertible content: it is skipped with a reason, not converted.
    reason = SKIP_KINDS["java_code"]
    assert "bytecode" in reason and "text files" in reason


# --- the board -------------------------------------------------------------------

def _shard(reasons):
    record = {"status": "ok", "namespace": "quark", "files": 10,
              "residue": sum(f for _, _, f in reasons), "coverage": 54.6, "valid": True,
              "errors": 0, "seconds": 1.0,
              "reasons": {f"{k}: {r}": {"kind": k, "reason": r, "entries": 1, "files": f, "examples": []}
                          for k, r, f in reasons}}
    return [{"schema": 1, "kind": "gap-shard", "manifest": "fixtures/real/gauntlet.toml",
             "shard": "1/1", "generated": "t",
             "mods": {"quark": {**record, "rank": 32, "title": "Quark",
                                "profile": {"class": "content", "evidence": ["blockstates 809"]}}}}]


def _quark_row(reasons):
    board = gauntlet.board(_shard(reasons))
    return {m["name"]: m for m in board["mods"]}["quark"]


def test_residue_of_qol_code_only_counts_as_done_under_rule_6():
    row = _quark_row([("java_code", "compiled classes", 972),
                      ("java_only_asset", "only the mod's Java code draws them", 547),
                      ("owned_by_residue", "only residue that has its own entry uses them", 658),
                      ("code_only", "the mod ships nothing Bedrock can hold", 12),
                      ("lang_code_string", "only the mod's Java code shows it", 8)])
    assert row["done"] is True
    assert row["done_why"] == "validator clean, residue explained"


def test_the_content_residue_still_blocks_the_mod():
    row = _quark_row([("java_code", "compiled classes", 972),
                      ("block", "the model has no elements", 12)])
    assert row["done"] is False
    assert row["done_why"] == "unexplained: block"


# --- the committed board and baseline --------------------------------------------

def _board_rows():
    """The rows of the board's mod table (12 cells, the first one the rank)."""
    rows = []
    for line in (ROOT / "docs" / "gauntlet.md").read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 12 and cells[0].isdigit():
            rows.append(cells)
    return rows


def _quark_cells():
    for cells in _board_rows():
        if cells[1] == "Quark":
            return cells
    pytest.fail("the board has no Quark row")


def test_the_board_has_the_quark_row():
    cells = _quark_cells()
    assert cells[2] == "content"          # the class the classifier gives it
    assert cells[4] == "ok"               # the jar was fetched and converted
    assert "%" in cells[5]                # coverage, with its delta
    assert cells[6].isdigit() and cells[7].isdigit()   # files and residue
    assert cells[9] == "clean"            # no validator error
    assert cells[8], "the row lists no residue class"


def test_every_residue_class_on_the_quark_row_is_explained():
    cells = _quark_cells()
    classes = [c.split(" ")[0] for c in cells[8].split(", ") if c]
    assert classes, "the Quark row lists no residue class"
    for kind in classes:
        assert kind in SKIP_KINDS, f"Quark's {kind} residue has no documented reason"


def test_no_qol_class_of_quark_is_unexplained_on_the_board():
    cells = _quark_cells()
    done = cells[11]
    assert not done.startswith("yes")      # Quark is a content mod, not done
    assert done.startswith("unexplained: ")
    unexplained = {c.strip() for c in done[len("unexplained: "):].split(",")}
    for kind in unexplained:
        base = kind.split(" ")[0]
        assert base not in QOL_KINDS, f"Quark's QoL class {base} is unexplained on the board"
        assert base in CONTENT_KINDS, f"unexpected unexplained class {base} on the Quark row"


def test_the_banked_baseline_row_for_quark_is_present_and_classified():
    base = json.loads((ROOT / "fixtures" / "real" / "gauntlet-baseline.json").read_text())
    quark = base["mods"]["quark"]
    assert quark["class"] == _quark_cells()[2]      # the same class as the board
    assert quark["status"] == "ok"
    assert quark["errors"] == 0
    assert isinstance(quark["coverage"], float)
    assert quark["done"] is False                   # a content mod, not done


def test_no_qol_class_of_quark_is_unexplained_in_the_cross_mod_table():
    # Every reason class the board rolls up across the mods, with the mods it
    # covers most: the classes Quark sits in that are not explained are the
    # content ones (and the files no converter claims), never a QoL class.
    for line in (ROOT / "docs" / "gauntlet.md").read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 7 or not cells[0].isdigit():
            continue
        reason_class, explained, mods = cells[1], cells[5], cells[6]
        if "quark" not in mods.split(", "):
            continue
        if explained == "yes":
            continue
        base = reason_class.split(" ")[0]
        assert base not in QOL_KINDS, f"Quark's QoL class {reason_class} is unexplained on the board"
        assert base in CONTENT_KINDS or base == "unowned", \
            f"unexpected unexplained class {reason_class} on the board"
