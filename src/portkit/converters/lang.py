"""Translation strings.

Java: assets/<ns>/lang/en_us.json, keys like "block.<ns>.<name>".
Bedrock: texts/en_US.lang, lines like "tile.<ns>:<name>.name=Value".
Key shapes we do not recognise are reported, not mangled.
"""
from __future__ import annotations

import json

from ..model import ConversionResult, SourceMod, Unhandled

_PREFIX = {"block": "tile", "item": "item", "itemGroup": "itemGroup"}


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

    lines = []
    for key, value in entries.items():
        translated = _translate_key(key, mod.namespace)
        if translated is None:
            result.unhandled.append(
                Unhandled(rel, "lang", f"unrecognised translation key {key!r}")
            )
            continue
        lines.append(f"{translated}={value}")

    if lines:
        result.files["texts/en_US.lang"] = "\n".join(sorted(lines)) + "\n"
        result.files["texts/languages.json"] = ["en_US"]
    return result
