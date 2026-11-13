"""The conversion report: what converted, what did not, and specifically why.

`convert` prints a summary dict, which is fine for a pipeline and useless to a
modder looking at a pack with a missing block. This produces Markdown they can
read top to bottom, or paste into an issue, and know every gap without opening
the source.

It reads what the conversion already left on disk: the two pack trees, the
manifests, and unhandled.json. Nothing is recomputed from the jar, so a report
always describes the tree in front of you rather than a fresh guess at it.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .validate import validate_tree
from .validate.report import Finding

# The version of the JSON report card's shape. Bumped when a section changes.
JSON_SCHEMA = 1

# What each directory in a pack actually holds, in the words a modder uses.
_CONTENT_TYPES = {
    "blocks": "blocks",
    "items": "items",
    "recipes": "recipes",
    "loot_tables": "loot tables",
    "entities": "entities",
    "functions": "functions",
    "models": "models",
    "textures": "textures",
    "texts": "translations",
    "sounds": "sounds",
    "scripts": "station runtimes",
}
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Residue:
    kind: str
    source: str
    reason: str
    count: int = 1

    @classmethod
    def load(cls, tree: Path) -> list["Residue"]:
        """Read the residue the conversion recorded next to the tree."""
        path = tree / "unhandled.json"
        if not path.is_file():
            return []
        try:
            entries = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        out = []
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict):
                out.append(
                    cls(
                        kind=str(entry.get("kind", "unknown")),
                        source=str(entry.get("source", "?")),
                        reason=str(entry.get("reason", "no reason recorded")),
                        count=int(1 if entry.get("count") is None else entry["count"]),
                    )
                )
        return out


def _skip_kinds() -> dict[str, str]:
    """The kinds the agent can never work on, each with its own explanation.

    ``portkit.agent.residue.SKIP_KINDS`` already says, per kind, why the
    converter left the file out. The report reuses those words instead of
    inventing a second mapping: one place says what a kind means.
    """
    from .agent.residue import SKIP_KINDS

    return SKIP_KINDS


def _kind_label(kind: str) -> str:
    """A residue kind as a modder reads it: ``machine_recipe`` -> "Machine recipe"."""
    return kind.replace("_", " ").capitalize()


def _kind_explanation(kind: str) -> str:
    """What this residue kind means, in the words the repo already uses.

    A kind the repo has no explanation for gets no explanation here either:
    the report never says more than the conversion recorded.
    """
    return _skip_kinds().get(kind, "").strip() or (
        "The converter left these files out; the reason under each one says why.")


def _reason_classes(item: "Residue") -> set[str]:
    """The jar's reason classes a ``code_only`` entry names, if it names any.

    ``portkit.codeonly.explain_leftovers`` writes them into the reason:
    "the mod ships nothing Bedrock can hold (reason classes: client_rendering)".
    """
    match = re.search(r"reason classes: ([^)]+)\)", item.reason)
    if not match:
        return set()
    return {name.strip() for name in match.group(1).split(",") if name.strip()}


# The residue kinds that cannot be done on Bedrock at all, and the category
# each falls in. Every rule names the kind it is grounded in, so a category
# is only flagged when the tree actually holds that kind. The "why" of each
# category is the repo's own wording: the jar's reason classes
# (``portkit.codeonly.REASONS``) and the kind explanations
# (``portkit.agent.residue.SKIP_KINDS``).
_CLIENT_RENDERING = "client rendering and shaders"
_CLIENT_TOOLS = "client-side tools"
_REAL_FLUIDS = "real custom fluids"


def _impossible_category(item: "Residue") -> str | None:
    """The category this residue entry cannot be done on Bedrock at all, if any.

    None means "not yet converted": the converter has not found a way, which
    is a different thing from Bedrock having no way at all.
    """
    kind = item.kind
    if kind in ("custom_fluid", "fluid_recipe"):
        # Bedrock add-ons can't define a fluid or store an amount of one.
        return _REAL_FLUIDS
    if kind == "java_only_asset":
        # Only the mod's Java code draws these (renderers, entity models,
        # shader and model formats).
        return _CLIENT_RENDERING
    if kind == "code_only":
        classes = _reason_classes(item)
        if "client_rendering" in classes:
            return _CLIENT_RENDERING
        if classes & {"gui_screen", "hud_overlay", "config_screen", "keybind"}:
            return _CLIENT_TOOLS
    return None


def _impossible_why(category: str, residue: list["Residue"]) -> str:
    """Why this category cannot be done on Bedrock, in the repo's own words."""
    from .codeonly import REASONS

    if category == _CLIENT_RENDERING:
        return REASONS["client_rendering"].bedrock
    if category == _CLIENT_TOOLS:
        classes = sorted({name for item in residue
                          for name in _reason_classes(item)
                          if name in ("gui_screen", "hud_overlay", "config_screen", "keybind")})
        return " ".join(REASONS[name].bedrock for name in classes)
    kinds = _skip_kinds()
    return kinds.get("custom_fluid", "")


def _impossible_cards(residue: list["Residue"]) -> list[dict]:
    """The categories of residue that cannot be done on Bedrock at all.

    Only a category whose kind the tree actually holds is here, and each card
    names the kinds it came from.
    """
    cards: dict[str, dict] = {}
    for item in residue:
        category = _impossible_category(item)
        if category is None:
            continue
        card = cards.setdefault(category, {"category": category, "kinds": set(), "files": 0})
        card["kinds"].add(item.kind)
        card["files"] += item.count
    out = []
    for category in sorted(cards):
        card = cards[category]
        out.append({
            "category": category,
            "kinds": sorted(card["kinds"]),
            "files": card["files"],
            "why": _impossible_why(category, residue),
        })
    return out


def _impossible_sections(residue: list["Residue"]) -> list[str]:
    """The Markdown of the categories that cannot be done on Bedrock at all."""
    cards = _impossible_cards(residue)
    if not cards:
        return []
    lines = [
        "These parts of the mod cannot be done on Bedrock at all. They are not "
        "\"not yet converted\": Bedrock has no way to carry them, so no conversion "
        "of them will ever work.",
        "",
    ]
    for card in cards:
        kinds = ", ".join(f"`{kind}`" for kind in card["kinds"])
        lines.append(f"- **{card['category']}** ({card['files']} file(s), kinds: {kinds}): {card['why']}")
    lines.append("")
    return lines


def _content_type(relpath: str) -> str:
    head = relpath.split("/", 1)[0]
    return _CONTENT_TYPES.get(head, head)


def _converted(tree: Path) -> Counter:
    """Files that made it, counted by content type."""
    counts: Counter = Counter()
    for pack in ("behavior_pack", "resource_pack"):
        root = tree / pack
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name in ("manifest.json", "pack_icon.png"):
                continue
            counts[_content_type(path.relative_to(root).as_posix())] += 1
    return counts


def _mod_name(tree: Path) -> str:
    for pack in ("behavior_pack", "resource_pack"):
        manifest = tree / pack / "manifest.json"
        if manifest.is_file():
            try:
                header = json.loads(manifest.read_text()).get("header") or {}
            except (OSError, json.JSONDecodeError):
                continue
            name = header.get("name")
            if isinstance(name, str) and name:
                return name.removesuffix(" (behavior)").removesuffix(" (resources)")
    return tree.name


def _setting_row(s: dict) -> tuple[str, str, str, str]:
    """One user config setting as a report row: a flag (on/off) or a value option (a number)."""
    default = s.get("cited_default")
    if s.get("condition") is None:  # a non-boolean config value (#190)
        return (f"`{s.get('mod')}.{s.get('flag')}`", f"{s.get('value'):g}",
                "uncited" if default is None else f"{default:g}", f"`{s.get('as_written')}`")
    return (f"`{s.get('condition')}`", "on" if s.get("value") else "off",
            "uncited" if default is None else ("on" if default else "off"),
            f"`{s.get('as_written')}`")


def _config_settings(tree: Path) -> list[dict]:
    """The user config settings the conversion recorded next to the tree, if any."""
    path = tree / "config-overrides.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    settings = data.get("_settings") if isinstance(data, dict) else None
    return [s for s in settings if isinstance(s, dict)] if isinstance(settings, list) else []


@dataclass
class Group:
    """One residue kind and the files it stands for."""

    kind: str
    files: int
    items: list[Residue]
    impossible_files: int = 0

    @property
    def bedrock(self) -> str:
        """What the report says about this group: impossible, partly, or not yet."""
        if self.impossible_files and self.impossible_files == self.files:
            return "cannot-be-done-on-bedrock"
        if self.impossible_files:
            return "partly-cannot-be-done-on-bedrock"
        return "not-yet-converted"


def _groups(residue: list[Residue]) -> list[Group]:
    """The residue grouped by kind, the way the report shows it."""
    by_kind: dict[str, list[Residue]] = defaultdict(list)
    for item in residue:
        by_kind[item.kind].append(item)
    groups = []
    for kind in sorted(by_kind):
        items = by_kind[kind]
        groups.append(Group(
            kind=kind,
            files=sum(i.count for i in items),
            items=items,
            impossible_files=sum(i.count for i in items if _impossible_category(i)),
        ))
    return groups


def _experiments(tree: Path) -> list[dict]:
    """The Bedrock experiments the tree shows it was converted for.

    A custom block's container component is written only when the conversion
    ran with the Upcoming Creator Features experiment on
    (``portkit.converters.blocks``), so its presence in the pack is the tree's
    own record of the flag. Nothing else in the tree names an experiment, so
    a tree without one records none.
    """
    blocks = tree / "behavior_pack" / "blocks"
    if not blocks.is_dir():
        return []
    found = False
    for path in sorted(blocks.glob("*.json")):
        try:
            body = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        block = body.get("minecraft:block") if isinstance(body, dict) else None
        if not isinstance(block, dict):
            continue
        components = block.get("components")
        if not isinstance(components, dict):
            continue
        entity = components.get("minecraft:block_entity")
        if isinstance(entity, dict) and isinstance(entity.get("container"), dict):
            found = True
            break
    if not found:
        return []
    return [{
        "experiment": "upcoming_creator_features",
        "why": ("the pack holds custom blocks with a container component, which portkit writes only "
                "when the world runs the Upcoming Creator Features experiment (portkit.converters.blocks)"),
    }]


def _table(rows: list[tuple[str, ...]], headers: tuple[str, ...]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(" --- " for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _findings_section(findings: list[Finding]) -> list[str]:
    if not findings:
        return ["The validator found nothing to report.", ""]
    lines = []
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.severity].append(finding)
    for severity in sorted(grouped, key=lambda s: _SEVERITY_ORDER.get(s, 9)):
        items = grouped[severity]
        label = {"error": "Errors", "info": "Notes"}.get(severity, "Warnings")
        lines.append(f"### {label} ({len(items)})")
        lines.append("")
        for finding in items:
            lines.append(f"- `{finding.path}` **{finding.rule}**: {finding.message}")
        lines.append("")
    return lines


def render(tree: Path) -> str:
    """Markdown for one converted tree."""
    converted = _converted(tree)
    residue = Residue.load(tree)
    report = validate_tree(tree)

    converted_total = sum(converted.values())
    residue_total = sum(r.count for r in residue)
    denominator = converted_total + residue_total
    coverage = (converted_total / denominator * 100) if denominator else 100.0

    lines = [
        f"# Conversion report: {_mod_name(tree)}",
        "",
        f"- **Coverage:** {coverage:.1f}% ({converted_total} of {denominator} files)",
        f"- **Left unconverted:** {residue_total} file(s) in {len(residue)} item(s)",
        f"- **Validator:** {'passed' if report.ok else 'failed'}, "
        f"{len(report.errors)} error(s), "
        f"{len(report.findings) - len(report.errors)} warning(s)",
        "",
        "## What converted",
        "",
    ]
    if converted:
        lines += _table(
            [(name, str(count)) for name, count in sorted(converted.items())],
            ("Content", "Files"),
        )
    else:
        lines.append("Nothing. The tree holds no pack files.")
    lines.append("")

    lines += ["## What did not, and why", ""]
    if not residue:
        lines += ["Everything in the source was converted.", ""]
    else:
        for group in _groups(residue):
            kind = group.kind
            items = group.items
            files = group.files
            lines.append(f"### {kind} ({files} file(s))")
            lines.append("")
            explanation = _kind_explanation(kind)
            if explanation:
                lines.append(f"**{_kind_label(kind)}:** {explanation}")
                lines.append("")
            if group.impossible_files == files:
                lines.append("**Cannot be done on Bedrock:** no conversion of this kind can make it work.")
                lines.append("")
            elif group.impossible_files:
                lines.append(
                    f"**Cannot be done on Bedrock:** {group.impossible_files} of these {files} file(s); "
                    "the rest is not yet converted."
                )
                lines.append("")
            for item in sorted(items, key=lambda i: i.source):
                suffix = f" ({item.count} files)" if item.count > 1 else ""
                lines.append(f"- `{item.source}`{suffix}: {item.reason}")
            lines.append("")

    impossible = _impossible_sections(residue)
    if impossible:
        lines += ["## Cannot be done on Bedrock", ""]
        lines += impossible

    lines += ["## Validator findings", ""]
    lines += _findings_section(report.findings)

    settings = _config_settings(tree)
    if settings:
        lines += [
            "## Mod config set by user config",
            "",
            "This tree was converted with these mod config settings in place of the "
            "defaults cited from the mod's source (`portkit convert --config`). "
            "`config-overrides.json` next to the tree reproduces the run with "
            "`--config-file`.",
            "",
        ]
        lines += _table(
            [_setting_row(s) for s in settings],
            ("Flag", "Set to", "Cited default", "As written"),
        )
        lines.append("")

    lines += [
        "## What to do with this",
        "",
        "Every line above names a source file and a reason. A reason that reads "
        "like a refusal is deliberate: the converter would rather leave a file "
        "out than emit something that loads and behaves wrongly. Paste this "
        "report into an issue and the gap is reproducible without the jar.",
        "",
    ]
    return "\n".join(lines)


def build(tree: Path) -> dict:
    """The report card as data, read from the tree the Markdown report reads.

    Same tree, same numbers: the JSON is the Markdown report in a form a tool
    can read, not a second opinion about the conversion.
    """
    tree = Path(tree)
    converted = _converted(tree)
    residue = Residue.load(tree)
    report = validate_tree(tree)

    converted_total = sum(converted.values())
    residue_total = sum(r.count for r in residue)
    denominator = converted_total + residue_total
    coverage = (converted_total / denominator * 100) if denominator else 100.0

    return {
        "schema": JSON_SCHEMA,
        "mod": {"name": _mod_name(tree)},
        "coverage": {
            "percent": round(coverage, 1),
            "converted_files": converted_total,
            "residue_files": residue_total,
            "total_files": denominator,
        },
        # What converted, by content type: the same table the Markdown shows.
        "converted": dict(sorted(converted.items())),
        # What shipped with a loss: the mod config settings in force (each with
        # the default cited from the mod's source) and the Bedrock experiment
        # flags the tree records.
        "approximated": {
            "settings": [
                {
                    "mod": s.get("mod"),
                    "flag": s.get("flag"),
                    "condition": s.get("condition"),
                    "value": s.get("value"),
                    "cited_default": s.get("cited_default"),
                    "as_written": s.get("as_written"),
                }
                for s in _config_settings(tree)
            ],
            "experiments": _experiments(tree),
        },
        # What did not convert, grouped by the kind of residue, with the
        # plain-language explanation of each kind.
        "unconverted": [
            {
                "kind": group.kind,
                "label": _kind_label(group.kind),
                "files": group.files,
                "explanation": _kind_explanation(group.kind),
                "bedrock": group.bedrock,
                "items": [
                    {
                        "source": item.source,
                        "reason": item.reason,
                        "count": item.count,
                        "bedrock": ("cannot-be-done-on-bedrock" if _impossible_category(item)
                                    else "not-yet-converted"),
                    }
                    for item in sorted(group.items, key=lambda i: i.source)
                ],
            }
            for group in _groups(residue)
        ],
        # The categories that cannot be done on Bedrock at all, distinct from
        # what is merely not converted yet.
        "cannot_be_done_on_bedrock": _impossible_cards(residue),
        "validator": {
            "ok": report.ok,
            "errors": len(report.errors),
            "warnings": len(report.findings) - len(report.errors),
            "findings": [
                {"severity": f.severity, "path": f.path, "rule": f.rule, "message": f.message}
                for f in report.findings
            ],
        },
        "unverified_in_game": {
            "verified": False,
            "note": ("This report describes the files on disk. It is not an in-game check: "
                     "portkit's in-game checks (#238) run on a separate copy of the pack, and "
                     "this tree carries no record of one, so nothing here says the pack "
                     "behaves correctly in Bedrock."),
        },
    }


def render_json(tree: Path) -> str:
    """The report card as JSON: the same tree, the same numbers."""
    return json.dumps(build(tree), indent=2) + "\n"
