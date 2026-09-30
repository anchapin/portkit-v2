"""Translation strings.

Java: assets/<ns>/lang/en_us.json, keys like "block.<ns>.<name>".
Bedrock: texts/en_US.lang, lines like "tile.<ns>:<name>.name=Value".

Keys fall into three buckets: content we can translate, strings that belong to
mod code and have no Bedrock text surface at all, and shapes we do not
recognise. Only the third kind is worth reporting one at a time, because it is
the only one where we might be wrong.
"""
from __future__ import annotations

import json

from ..model import ConversionResult, SourceMod, Unhandled

# Java content domain -> Bedrock key prefix.
_PREFIX = {
    "block": "tile",
    "item": "item",
    "entity": "entity",
    "itemGroup": "itemGroup",
}

# Domains the Java code looks up directly. Bedrock has nowhere to put these:
# no wiki pages, no Forge fluid types, no modded keybind or command text.
_CODE_DOMAINS = frozenset({
    "advancement",
    "advancements",
    "argument",
    "book",
    "chat",
    "commands",
    "config",
    "container",
    "death",
    "fluid_type",
    "gui",
    "jei",
    "key",
    "message",
    "narrator",
    "options",
    "screen",
    "selectWorld",
    "sound",
    "stat",
    "subtitles",
    "text",
    "tooltip",
    "wiki",
})


def _translate_key(key: str, namespace: str) -> str | None:
    parts = key.split(".")
    if len(parts) < 3:
        return None
    domain, ns, *rest = parts
    prefix = _PREFIX.get(domain)
    if prefix is None or ns != namespace:
        return None
    name = ".".join(rest)
    if domain == "itemGroup":
        return f"itemGroup.name.{name}"
    return f"{prefix}.{namespace}:{name}.name"


def _is_code_string(key: str) -> bool:
    return key.split(".")[0] in _CODE_DOMAINS


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    src = mod.assets / "lang" / "en_us.json"
    if not src.is_file():
        return result

    rel = str(src.relative_to(mod.root))
    try:
        entries = json.loads(src.read_text())
    except json.JSONDecodeError as exc:
        result.unhandled.append(Unhandled(rel, "lang", f"invalid JSON: {exc}"))
        return result

    lines: list[str] = []
    code_strings: list[str] = []
    for key, value in entries.items():
        translated = _translate_key(key, mod.namespace)
        if translated is not None:
            lines.append(f"{translated}={value}")
        elif _is_code_string(key):
            code_strings.append(key)
        else:
            result.unhandled.append(
                Unhandled(rel, "lang", f"unrecognised translation key {key!r}")
            )

    if code_strings:
        sample = ", ".join(sorted(code_strings)[:3])
        result.unhandled.append(
            Unhandled(
                source=rel,
                kind="lang_code_string",
                reason=(
                    f"{len(code_strings)} string(s) belong to mod code with no Bedrock "
                    f"text surface (e.g. {sample})"
                ),
            )
        )

    if lines:
        result.files["texts/en_US.lang"] = "\n".join(sorted(lines)) + "\n"
        result.files["texts/languages.json"] = ["en_US"]
    return result
