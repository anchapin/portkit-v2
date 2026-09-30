"""Translation strings.

Java: assets/<ns>/lang/<locale>.json, keys like "block.<ns>.<name>".
Bedrock: texts/<Locale>.lang, lines like "tile.<ns>:<name>.name=Value".

Keys fall into three buckets: content we can translate, strings that belong to
mod code and have no Bedrock text surface at all, and shapes we do not
recognise. Only the third kind is worth reporting one at a time, because it is
the only one where we might be wrong.
"""
from __future__ import annotations

import json

from ..model import ConversionResult, SourceMod, Unhandled

# Java locale file name -> Bedrock locale file name. Bedrock ships a fixed list
# of locales and ignores a texts/ file outside it, so a locale we cannot place
# is residue rather than a file that looks converted and never loads.
_LOCALES = {
    "en_us": "en_US",
    "en_gb": "en_GB",
    "bg_bg": "bg_BG",
    "cs_cz": "cs_CZ",
    "da_dk": "da_DK",
    "de_de": "de_DE",
    "el_gr": "el_GR",
    "es_es": "es_ES",
    "es_mx": "es_MX",
    "fi_fi": "fi_FI",
    "fr_ca": "fr_CA",
    "fr_fr": "fr_FR",
    "hu_hu": "hu_HU",
    "id_id": "id_ID",
    "it_it": "it_IT",
    "ja_jp": "ja_JP",
    "ko_kr": "ko_KR",
    "nl_nl": "nl_NL",
    # Java ships Norwegian as no_no, Bedrock names the same language nb_NO
    "no_no": "nb_NO",
    "nb_no": "nb_NO",
    "pl_pl": "pl_PL",
    "pt_br": "pt_BR",
    "pt_pt": "pt_PT",
    "ru_ru": "ru_RU",
    "sk_sk": "sk_SK",
    "sv_se": "sv_SE",
    "tr_tr": "tr_TR",
    "uk_ua": "uk_UA",
    "zh_cn": "zh_CN",
    "zh_tw": "zh_TW",
}

_PRIMARY = "en_us"

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


def _lines(entries: dict, namespace: str) -> tuple[list[str], list[str], list[str]]:
    """Split one locale file into translated lines, code strings and unknown keys."""
    lines: list[str] = []
    code_strings: list[str] = []
    unknown: list[str] = []
    for key, value in entries.items():
        translated = _translate_key(key, namespace)
        if translated is not None:
            lines.append(f"{translated}={value}")
        elif _is_code_string(key):
            code_strings.append(key)
        else:
            unknown.append(key)
    return lines, code_strings, unknown


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    src = mod.assets / "lang"
    if not src.is_dir():
        return result

    converted: dict[str, str] = {}
    primary_untranslated: set[str] = set()

    for path in sorted(src.glob("*.json")):
        locale = path.stem.lower()
        rel = result.claim(mod, path)
        bedrock = _LOCALES.get(locale)
        if bedrock is None:
            result.unhandled.append(
                Unhandled(rel, "lang", f"Bedrock has no locale matching {locale!r}")
            )
            continue

        try:
            entries = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            result.unhandled.append(Unhandled(rel, "lang", f"invalid JSON: {exc}"))
            continue

        lines, code_strings, unknown = _lines(entries, mod.namespace)

        if locale == _PRIMARY:
            # The primary locale is where key shapes get reported. Every other
            # locale translates the same keys, so repeating the report per file
            # would multiply one fact by the number of languages shipped.
            primary_untranslated = set(code_strings) | set(unknown)
            for key in sorted(unknown):
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
                            f"{len(code_strings)} string(s) belong to mod code with no "
                            f"Bedrock text surface (e.g. {sample})"
                        ),
                    )
                )
        else:
            # Only a key this locale has and the primary does not is news.
            extra = sorted((set(code_strings) | set(unknown)) - primary_untranslated)
            if extra:
                sample = ", ".join(extra[:3])
                result.unhandled.append(
                    Unhandled(
                        source=rel,
                        kind="lang",
                        reason=(
                            f"{len(extra)} key(s) present in {locale} but not in "
                            f"{_PRIMARY} went untranslated (e.g. {sample})"
                        ),
                    )
                )

        if lines:
            converted[bedrock] = "\n".join(sorted(lines)) + "\n"

    for bedrock, text in converted.items():
        result.files[f"texts/{bedrock}.lang"] = text
    if converted:
        # en_US first, the way the vanilla packs list it, then the rest by name.
        rest = sorted(k for k in converted if k != "en_US")
        result.files["texts/languages.json"] = (
            (["en_US"] if "en_US" in converted else []) + rest
        )
    return result
