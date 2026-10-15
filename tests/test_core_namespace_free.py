"""The core must not name a mod namespace (#245, step 4 in allowlist mode).

portkit's goal is a converter that works on any Java mod, so the shared code
under ``src/portkit`` (Python and the fixed runtime JavaScript) should never
need to know one mod's namespace. Code that serves a single mod belongs in a
per-mod adapter (``src/portkit/adapters/<mod>/``, registered in
``src/portkit/adapters/__init__.py``; the audit is
``docs/adapter-audit-2026-10-15.md``). Until the move happens, today's
offenders are frozen in ``tests/data/core_namespace_allowlist.json`` with a
count per (file, namespace), and this test is a ratchet:

* a NEW occurrence (a file or namespace not in the allowlist, or a count above
  it) fails, naming the file, line and literal;
* a count BELOW the allowlist also fails, asking you to lower the number (or
  drop the entry), so a removed reference can't quietly come back.

Detection rule
--------------
Only **string literals in code** are scanned: Python string constants other
than docstrings (f-string text parts included), and JavaScript '...', "..."
and `...` literals outside comments. Comments, docstrings, identifiers and
citations in comments are not literals and are not counted (the audit lists
those). Within one literal, a namespace ``ns`` is counted at most once, when
any of these holds:

A. **Known mod resource location**: ``ns:`` followed by a path character
   (``[a-z0-9_*#{]``) anywhere in the literal, ``ns`` in
   :data:`MOD_NAMESPACES` (``"farmersdelight:cooking"``,
   ``"... tconstruct:melting ..."``).
B. **Any resource location**: the whole literal is ``ns:path``
   (``^[a-z0-9_.-]+:[a-z0-9_/.-]+$``, path not starting with ``/``) and ``ns``
   is neither a platform namespace (:data:`PLATFORM_NAMESPACES`) nor in
   :data:`NOT_NAMESPACES`. This catches a mod that is not in the known list.
C. **Bare namespace**: the literal is exactly a known mod namespace
   (``NAMESPACE = "waystones"``).
D. **Namespace segment**: a known mod namespace delimited by ``/`` or ``.``
   on at least one side and by ``/``, ``.``, or the literal's start/end on
   the other (``"data/waystones/tags/..."``, ``"block.farmersdelight.x"``,
   ``"farmersdelight.cuttingBoardFortuneBonus"``, a Java class path
   ``".../citadel/client/gui/GuiBasicBook"``).

Rules C and D skip :data:`AMBIGUOUS` namespaces that are also ordinary words
(``create`` is Java's ``BlockEntityType#create`` too); those count under A/B
only.

:data:`MOD_NAMESPACES` is every ``assets/<ns>`` / ``data/<ns>`` folder in the
13 corpus jars (``fixtures/real/mods.toml``) and the 13 deco-set jars
(``deco-mods.toml`` of the 2026-10-14 deco spike), less the platform
namespaces and two Axiom folders named ``color``/``material``, plus
``citadel`` (the library behind Alex's Mobs' book, read from bytecode).
Add a mod's namespaces here when it joins either set; rule B covers the gap
for resource locations meanwhile.

Scope: every ``*.py`` and ``*.js`` file under ``src/portkit`` except
``src/portkit/adapters/`` (the home of single-mod code). JSON data
files (``src/portkit/data/*.json``) are per-mod data by design and are not
scanned.
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORE_ROOT = REPO / "src" / "portkit"
ALLOWLIST = Path(__file__).resolve().parent / "data" / "core_namespace_allowlist.json"
# Folders under src/portkit that may name a mod (the adapters of #245).
EXCLUDED_DIRS = ("adapters",)

# Vanilla, the loaders' own and convention namespaces, and portkit's own.
PLATFORM_NAMESPACES = frozenset({"minecraft", "c", "forge", "neoforge", "fabric", "portkit"})
# Prefixes that look like ``ns:path`` but are not namespaces.
NOT_NAMESPACES = frozenset({
    "http", "https",  # URLs
    "r",  # tarfile open mode "r:gz"
})
MOD_NAMESPACES = frozenset({
    # standard corpus (fixtures/real/mods.toml), with the compat folders they ship
    "alexsmobs", "domesticationinnovation",
    "bclib", "betterend", "bewitchment", "blockus", "colored_lights", "emi", "trinkets", "waystones", "wover",
    "create", "curios", "quark",
    "createaddition", "farmersdelight", "origins", "sable", "sereneseasons", "tconstruct",
    "framedblocks", "mekanism", "per-viam-invenire", "projecte",
    "alloy_forgery", "cicada", "custom_piglin_bartering", "mythicmetals", "piglib", "swordblockingmechanics",
    "mmorpg", "silentgear", "silents_mechanisms",
    "storagedrawers",
    "amendments", "dynamictrees", "neapolitan", "supplementaries", "vslab_compat",
    "ceramics", "headlight", "mantle", "parry", "trimmed", "twilightforest",
    # deco set (2026-10-14 deco spike)
    "axiom", "beautify", "cluttered", "decocraft", "fairylights", "moa_toys", "nightlights", "plushie_buddies",
    "carryon", "refurbished_furniture", "seafoamsdyeableblocks", "wallpapercraft",
    # libraries read from bytecode
    "citadel",
})
# Namespaces that are also everyday words: rules A and B only.
AMBIGUOUS = frozenset({"create", "origins", "sable", "parry", "trimmed", "headlight", "emi", "curios"})

_PATH_CHAR = r"[a-z0-9_*#{]"
_RULE_A = re.compile(
    r"(?<![A-Za-z0-9_.\-/])(" + "|".join(sorted(map(re.escape, MOD_NAMESPACES))) + r"):(?=" + _PATH_CHAR + ")"
)
_RULE_B = re.compile(r"^([a-z0-9_.\-]+):([a-z0-9_.\-][a-z0-9_/.\-]*)$")
_SEGMENT_NS = sorted(MOD_NAMESPACES - AMBIGUOUS)
_RULE_D = re.compile(
    r"(?:(?<=[/.])|^)(" + "|".join(map(re.escape, _SEGMENT_NS)) + r")(?=[/.]|$)"
)


def namespaces_in(literal: str) -> set[str]:
    """The mod namespaces one string literal names, by rules A-D."""
    found = {m.group(1) for m in _RULE_A.finditer(literal)}
    full = _RULE_B.match(literal)
    if full and full.group(1) not in PLATFORM_NAMESPACES and full.group(1) not in NOT_NAMESPACES:
        found.add(full.group(1))
    if literal in MOD_NAMESPACES and literal not in AMBIGUOUS:
        found.add(literal)
    for m in _RULE_D.finditer(literal):
        start, end = m.span(1)
        before = literal[start - 1] if start else ""
        after = literal[end] if end < len(literal) else ""
        if before in "/." and before or after in "/." and after:
            found.add(m.group(1))
    return found


def python_literals(source: str) -> list[tuple[int, str]]:
    """(line, value) of every string constant in Python ``source`` but docstrings."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return sorted(
        (node.lineno, node.value) for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    )


def js_literals(source: str) -> list[tuple[int, str]]:
    """(line, value) of every string or template literal in JavaScript ``source``,
    comments skipped. The runtime scripts use no regex literals; a template
    literal is one value, its ``${...}`` text included."""
    out = []
    i, n, line = 0, len(source), 1
    while i < n:
        ch = source[i]
        if ch == "\n":
            line += 1
            i += 1
        elif source.startswith("//", i):
            end = source.find("\n", i)
            i = n if end < 0 else end
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            end = n if end < 0 else end + 2
            line += source.count("\n", i, end)
            i = end
        elif ch in "'\"`":
            j, start, buf = i + 1, line, []
            while j < n and source[j] != ch:
                if source[j] == "\\":
                    buf.append(source[j:j + 2])
                    j += 2
                    continue
                if source[j] == "\n":
                    line += 1
                buf.append(source[j])
                j += 1
            out.append((start, "".join(buf)))
            i = j + 1
        else:
            i += 1
    return out


def core_files() -> list[Path]:
    files = []
    for path in sorted(CORE_ROOT.rglob("*")):
        if path.suffix not in (".py", ".js") or not path.is_file():
            continue
        rel = path.relative_to(CORE_ROOT)
        if rel.parts[0] in EXCLUDED_DIRS or "__pycache__" in rel.parts:
            continue
        files.append(path)
    return files


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """(line, namespace, literal) for every hit in one core file."""
    source = path.read_text(encoding="utf-8")
    literals = python_literals(source) if path.suffix == ".py" else js_literals(source)
    return [(line, ns, value) for line, value in literals for ns in sorted(namespaces_in(value))]


def scan() -> dict[str, dict[str, list[tuple[int, str]]]]:
    """{file relative to src/portkit: {namespace: [(line, literal)]}}."""
    found: dict[str, dict[str, list[tuple[int, str]]]] = {}
    for path in core_files():
        rel = path.relative_to(CORE_ROOT).as_posix()
        for line, ns, value in scan_file(path):
            found.setdefault(rel, {}).setdefault(ns, []).append((line, value))
    return found


def counts(found) -> dict[str, dict[str, int]]:
    return {rel: {ns: len(hits) for ns, hits in sorted(by_ns.items())} for rel, by_ns in sorted(found.items())}


def _allowlist() -> dict[str, dict[str, int]]:
    data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    return data["files"]


# --- the ratchet ----------------------------------------------------------------

def test_no_new_mod_namespaces_in_core():
    found = scan()
    allowed = _allowlist()
    problems = []
    for rel, by_ns in sorted(found.items()):
        for ns, hits in sorted(by_ns.items()):
            limit = allowed.get(rel, {}).get(ns, 0)
            if len(hits) > limit:
                shown = "\n".join(f"      {rel}:{line}: {value[:100]!r}" for line, value in hits)
                problems.append(
                    f"  {rel}: {len(hits)} literal(s) name {ns!r}, allowlist permits {limit}.\n{shown}"
                )
    assert not problems, (
        "New mod namespace literals in core modules (#245). Single-mod code belongs in a per-mod "
        "adapter, not the core; see docs/adapter-audit-2026-10-15.md.\n" + "\n".join(problems)
    )


def test_allowlist_only_shrinks():
    """A count that went down must be lowered in the allowlist, so it can't creep back."""
    actual = counts(scan())
    allowed = _allowlist()
    stale = []
    for rel, by_ns in sorted(allowed.items()):
        for ns, limit in sorted(by_ns.items()):
            now = actual.get(rel, {}).get(ns, 0)
            if now < limit:
                stale.append(f"  {rel} {ns!r}: allowlist {limit}, now {now} -> set it to {now}"
                             + (" (remove the entry)" if now == 0 else ""))
    assert not stale, (
        "Mod namespace literals were removed from core modules: lower "
        "tests/data/core_namespace_allowlist.json to match.\n" + "\n".join(stale)
    )


def test_allowlist_total_matches_entries():
    data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    total = sum(n for by_ns in data["files"].values() for n in by_ns.values())
    assert data["total"] == total
    assert all(n > 0 for by_ns in data["files"].values() for n in by_ns.values())


# --- the detection rule ------------------------------------------------------------

def test_rule_examples():
    assert namespaces_in("farmersdelight:cooking") == {"farmersdelight"}  # A (+B)
    assert namespaces_in("a recipe of type tconstruct:melting needs a smeltery") == {"tconstruct"}  # A
    assert namespaces_in("somenewmod:widget") == {"somenewmod"}  # B: unknown mod
    assert namespaces_in("waystones") == {"waystones"}  # C
    assert namespaces_in("data/waystones/tags/block/waystones.json") == {"waystones"}  # D
    assert namespaces_in("block.farmersdelight.cutting_board.remaining_items") == {"farmersdelight"}  # D
    assert namespaces_in("farmersdelight.cuttingBoardFortuneBonus") == {"farmersdelight"}  # D
    assert namespaces_in("com/github/alexthe666/citadel/client/gui/GuiBasicBook") == {"citadel"}  # D
    assert namespaces_in("create:crushing") == {"create"}  # A on an ambiguous namespace


def test_rule_non_examples():
    for literal in (
        "minecraft:stone", "c:ingots/iron", "forge:mod_loaded", "neoforge:conditions", "fabric:load_conditions",
        "portkit:config_value", "https://example.com/x", "r:gz", "item:minecraft:icon",
        "create",  # BlockEntityType#create, not the Create mod
        "the waystone menu",  # a word, not a namespace token
        "waystones_waystone.js",  # file name built from the namespace: identifier-ish, not a segment
        "{ns}:portkit_toggle",
    ):
        assert namespaces_in(literal) == set(), literal


def test_comments_and_docstrings_are_not_literals():
    py = '"""farmersdelight:cooking"""\n# farmersdelight:cooking\nX = "farmersdelight:cooking"\n' \
         'def f():\n    """waystones"""\n    return f"{a}:waystones"\n'
    assert [v for _, v in python_literals(py)] == ["farmersdelight:cooking", ":waystones"]
    js = '// farmersdelight:cooking\n/* waystones */\nconst a = "farmersdelight:cooking";\n' \
         "const b = 'x';\nconst c = `y${a}`;\n"
    assert js_literals(js) == [(3, "farmersdelight:cooking"), (4, "x"), (5, "y${a}")]
