"""Tools the residue agent gets. Note what is NOT here: no shell, no network.

It can read the source mod, write into the output tree, and ask the validator
whether it worked. That last one is the whole design: the loop terminates on a
deterministic check, not on the model declaring victory.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from ..validate import validate_tree
from . import reference


# Bedrock locale files: resource_pack/texts/en_US.lang, pt_BR.lang, ...
_LANG_PATH = re.compile(r"resource_pack/texts/([a-z]{2}_[A-Z]{2})\.lang")


class ToolBox:
    def __init__(self, source: Path, out_tree: Path):
        self.source = source
        self.out_tree = out_tree
        self._tools: dict[str, tuple[dict, Callable[..., Any]]] = {}
        self._register_defaults()

    # -- registration -------------------------------------------------
    def register(self, schema: dict, fn: Callable[..., Any]) -> None:
        self._tools[schema["name"]] = (schema, fn)

    def schemas(self) -> list[dict]:
        return [schema for schema, _ in self._tools.values()]

    def format_error(self, name: str, arguments: Any) -> str | None:
        """Why a call doesn't fit the toolbox, or None when it does (#77).

        A format failure is a call no tool can take as made: an unknown name,
        arguments that aren't an object, a required argument missing, or one
        the tool doesn't declare. It says the harness and the model disagree on
        the tool-call format, which reads differently from a model that is
        merely weaker, so the eval matrix counts it on its own.
        """
        if name not in self._tools:
            return f"unknown tool {name!r}"
        if not isinstance(arguments, dict):
            return f"{name}: arguments are {type(arguments).__name__}, not an object"
        params = self._tools[name][0].get("parameters") or {}
        declared = set(params.get("properties") or {})
        missing = [a for a in params.get("required") or [] if a not in arguments]
        if missing:
            return f"{name}: missing required argument(s) {', '.join(missing)}"
        unknown = sorted(set(arguments) - declared)
        if unknown:
            return f"{name}: unknown argument(s) {', '.join(unknown)}"
        return None

    def invoke(self, name: str, arguments: dict) -> Any:
        if name not in self._tools:
            return {"error": f"unknown tool {name!r}", "available": sorted(self._tools)}
        _, fn = self._tools[name]
        return fn(**arguments)

    # -- the tools ----------------------------------------------------
    def _register_defaults(self) -> None:
        self.register(
            {
                "name": "read_source",
                "description": "Read a file from the Java mod being converted.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "path relative to the mod root"}},
                    "required": ["path"],
                },
            },
            self.read_source,
        )
        self.register(
            {
                "name": "list_source",
                "description": "List files in the Java mod, optionally under a subdirectory.",
                "parameters": {
                    "type": "object",
                    "properties": {"subdir": {"type": "string"}},
                },
            },
            self.list_source,
        )
        self.register(
            {
                "name": "write_output",
                "description": (
                    "Write a JSON file into the Bedrock output tree, e.g. "
                    "'behavior_pack/entities/foo.json'. Overwrites."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "object"},
                    },
                    "required": ["path", "content"],
                },
            },
            self.write_output,
        )
        self.register(
            {
                "name": "set_lang_entries",
                "description": (
                    "Add or replace display names in a Bedrock .lang file, e.g. "
                    "path 'resource_pack/texts/en_US.lang' with lines "
                    "['tile.examplemod:steel_block.name=Steel Block']. Existing keys are "
                    "replaced in place, new ones appended; every other line is kept, so "
                    "send only the entries you are adding."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "resource_pack/texts/<Locale>.lang"},
                        "lines": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "key=value lines",
                        },
                    },
                    "required": ["path", "lines"],
                },
            },
            self.set_lang_entries,
        )
        self.register(
            {
                "name": "validate",
                "description": (
                    "Run the Bedrock structural validator over the whole output tree. "
                    "Returns ok plus a list of findings. This is the ground truth: "
                    "the task is not finished until ok is true."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
            self.validate,
        )
        self.register(
            {
                "name": "lookup_bedrock",
                "description": (
                    "Look up how something is written in Bedrock: a block or item component "
                    "('minecraft:destructible_by_mining', 'item:minecraft:icon'), a recipe type "
                    "('recipe_shaped', 'recipe_smithing_transform'), or a pack file "
                    "('terrain_texture.json', 'item_texture.json', '.lang'). Returns the schema "
                    "fragment, a short real example and a note on what the validator checks. "
                    "An unknown topic returns the closest names."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                    "required": ["topic"],
                },
            },
            self.lookup_bedrock,
        )
        self.register(
            {
                "name": "list_bedrock_topics",
                "description": (
                    "List the topics lookup_bedrock knows, grouped by kind, optionally only "
                    "those starting with a prefix such as 'recipe' or 'minecraft:light'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"prefix": {"type": "string"}},
                },
            },
            self.list_bedrock_topics,
        )

    def _resolve(self, base: Path, path: str) -> Path:
        target = (base / path).resolve()
        if base.resolve() not in target.parents and target != base.resolve():
            raise ValueError(f"path escapes the sandbox: {path}")
        return target

    def read_source(self, path: str) -> dict:
        target = self._resolve(self.source, path)
        if not target.is_file():
            return {"error": f"no such file: {path}"}
        if target.suffix == ".png":
            return {"path": path, "note": "binary texture", "bytes": target.stat().st_size}
        return {"path": path, "content": target.read_text()}

    def list_source(self, subdir: str = "") -> dict:
        base = self._resolve(self.source, subdir) if subdir else self.source
        if not base.is_dir():
            return {"error": f"no such directory: {subdir}"}
        return {
            "files": sorted(
                str(p.relative_to(self.source)) for p in base.rglob("*") if p.is_file()
            )
        }

    def _before_write(self, target: Path) -> None:
        """Hook called before any file in the output tree changes."""

    def write_output(self, path: str, content: dict) -> dict:
        # ``content`` must be a JSON object. A model that hands us a string
        # would write ``json.dumps("foo")`` = ``'"foo"'`` to disk, a valid JSON
        # document but useless as a Bedrock file. Tell the loop the call was
        # bad instead of producing one of those — the model can fix it on the
        # next step.
        if not isinstance(content, dict):
            return {
                "error": (
                    f"content must be a JSON object, got {type(content).__name__}; "
                    "pass Bedrock JSON like {\"minecraft:recipe_shapeless\": {...}}"
                ),
                "received_type": type(content).__name__,
                "received_preview": repr(content)[:120],
            }
        target = self._resolve(self.out_tree, path)
        self._before_write(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(content, indent=2) + "\n")
        return {"written": path, "bytes": target.stat().st_size}

    def set_lang_entries(self, path: str, lines: list) -> dict:
        """Upsert ``key=value`` lines into a resource pack .lang file (#105).

        A merge rather than a write: the deterministic converter already filled
        the file, and a model asked to resend it whole would drop lines. A bad
        line rejects the whole call, so nothing half-applies.
        """
        path = path.replace("\\", "/")
        match = _LANG_PATH.fullmatch(path)
        if not match:
            return {"error": f"path must be resource_pack/texts/<Locale>.lang, got {path!r}"}
        if not isinstance(lines, list) or not lines:
            return {"error": "lines must be a non-empty list of 'key=value' strings"}
        updates: dict[str, str] = {}
        for i, line in enumerate(lines):
            if not isinstance(line, str) or "\n" in line or "\r" in line:
                return {"error": f"lines[{i}] must be one line of text; write a line break inside a value as ~LINEBREAK~"}
            key, sep, value = line.partition("=")
            key = key.strip()
            if not sep or not key or key.startswith("#") or any(c.isspace() for c in key):
                return {"error": f"lines[{i}] is not 'key=value': {line!r}"}
            updates[key] = value.strip()

        target = self._resolve(self.out_tree, path)
        existing = target.read_text(encoding="utf-8-sig").splitlines() if target.is_file() else []
        out, replaced = [], set()
        for old in existing:
            key = old.split("=", 1)[0].strip()
            if "=" in old and key in updates and not old.lstrip().startswith("#"):
                if key not in replaced:
                    out.append(f"{key}={updates[key]}")
                    replaced.add(key)
                continue
            out.append(old)
        added = [k for k in updates if k not in replaced]
        out.extend(f"{k}={updates[k]}" for k in added)

        self._before_write(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(out) + "\n", encoding="utf-8")

        locale = match.group(1)
        index = target.parent / "languages.json"
        try:
            listed = json.loads(index.read_text()) if index.is_file() else []
        except json.JSONDecodeError:
            listed = None  # leave a broken index for the validator to report
        if isinstance(listed, list) and locale not in listed:
            self._before_write(index)
            listed.append(locale)
            index.write_text(json.dumps(listed, indent=2) + "\n")
        return {"written": path, "added": added, "replaced": sorted(replaced)}

    def validate(self) -> dict:
        return validate_tree(self.out_tree).to_dict()

    def lookup_bedrock(self, topic: str) -> dict:
        """Deterministic reference lookup (#114): same topic, same answer."""
        return reference.lookup(topic)

    def list_bedrock_topics(self, prefix: str = "") -> dict:
        return reference.list_topics(prefix)


SYSTEM_PROMPT = """You convert leftover Minecraft Java mod content to Bedrock Edition.

The deterministic converters already handled textures, recipes and lang files.
You only see what they refused to guess at.

Rules:
- Read the source file before writing anything.
- Write Bedrock JSON with write_output, then call validate.
- Name new blocks and items with set_lang_entries, which adds lines to an
  existing .lang file instead of replacing it.
- Unsure how a Bedrock component, recipe or file is spelled? Call
  lookup_bedrock(topic) before writing; list_bedrock_topics shows what it knows.
- Keep calling validate until it returns ok: true. Fix the exact findings it names.
- If a piece of Java behaviour has no Bedrock equivalent, say so plainly in your
  final message instead of inventing a component that does not exist.
"""
