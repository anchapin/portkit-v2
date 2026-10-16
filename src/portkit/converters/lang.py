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
import re

from ..model import ConversionResult, SourceMod, Unhandled, _declared

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

# Java registries whose entries carry a translation key ("effect.<ns>.<name>")
# but which portkit converts none of, so a Bedrock line would name nothing in
# the pack (#277 lang). Keys of these shapes are explained as unshipped; the
# label names the registry in the residue.
_REGISTRIES = {
    "effect": "mob effect",
    "enchantment": "enchantment",
    "biome": "biome",
    "fluid": "fluid",
    "fluid_type": "fluid",
    "attribute": "attribute",
    "trim_material": "armor trim material",
    "trim_pattern": "armor trim pattern",
    "painting": "painting variant",
    "dimension": "dimension",
    "structure": "structure",
    "generator": "world preset",
    "jukebox_song": "jukebox song",
    "instrument": "goat horn instrument",
    "upgrade": "smithing upgrade",
}

# Residue kinds this converter files (all explained, #277 lang): strings only
# Java code shows, lines naming something the pack doesn't ship, a locale
# Bedrock has no slot for, and a file Java's own reader rejects.
CODE_STRING = "lang_code_string"
UNSHIPPED = "lang_unshipped"
LOCALE = "lang_locale"
UNREADABLE = "lang_unreadable"
KINDS = frozenset({"lang", CODE_STRING, UNSHIPPED, LOCALE, UNREADABLE})



# A .lang value is one line. Java lang JSON allows a newline inside a value
# (multi-line tooltips); Bedrock spells it ~LINEBREAK~, the way the vanilla
# en_US.lang does. Written raw, the tail of the value lands on a line of its own
# with no '=', which the game cannot parse.
_LINEBREAK = "~LINEBREAK~"


def _one_line(value: str) -> str:
    return value.replace("\r\n", _LINEBREAK).replace("\n", _LINEBREAK).replace("\r", _LINEBREAK)


# Java's lang loader rewrites numeric slots to string slots as it reads a
# file (net.minecraft.locale.Language UNSUPPORTED_FORMAT_PATTERN
# %(\d+\$)?[\d.]*[df] -> %$1s; described in Mojira MC-262117, still so in
# 1.21), so "%d" always fills like "%s"; Bedrock's rawtext documents only %s and
# %1 slots. A runtime key's numeric slots are written as string slots, which is
# what Java reads them as.
_INT_SLOT = re.compile(r"%(\d+\$)?[\d.]*[df]")


def _runtime_value(value: str) -> str:
    return _INT_SLOT.sub(lambda m: f"%{m.group(1) or ''}s", value)


def _translate_key(key: str, namespace: str = "") -> str | None:
    """The Bedrock key for a Java content key, whichever namespace it names.

    Whether the line ships is decided once the pack is final (:func:`settle`):
    a block, item or entity the pack doesn't ship, another namespace's
    included, has nothing for the line to name. ``block.minecraft.*`` and the
    like rename or extend vanilla entries and are not translated here.
    """
    parts = key.split(".")
    if len(parts) < 3:
        return None
    domain, ns, *rest = parts
    prefix = _PREFIX.get(domain)
    if prefix is None or not ns or ns == "minecraft":
        return None
    name = ".".join(rest)
    if domain == "itemGroup":
        return f"itemGroup.name.{name}"
    return f"{prefix}.{ns}:{name}.name"


def _classify(key: str) -> tuple[str, str]:
    """(kind, label) of a key that has no Bedrock line: ``CODE_STRING`` for a
    string only Java code shows, ``UNSHIPPED`` (label: what it names) for a
    registry entry or vanilla entry the pack has nothing of."""
    parts = key.split(".")
    domain = parts[0]
    if domain in _PREFIX and len(parts) >= 3 and parts[1] == "minecraft":
        return UNSHIPPED, "vanilla minecraft: entry"
    if domain == "itemGroup":
        return UNSHIPPED, "creative tab"
    if domain in _REGISTRIES and len(parts) >= 3:
        return UNSHIPPED, _REGISTRIES[domain]
    # No block, item, entity, creative tab or registry entry owns the key, so
    # the only thing that can show it is Java code asking for it by name: a
    # screen, tooltip, chat message, config option or another mod's
    # integration (JEI/EMI categories, Jade/WAILA lines, tag names).
    return CODE_STRING, ""


def _lines(entries: dict, namespace: str,
           runtime_keys: frozenset = frozenset()) -> tuple[list[str], list[str], dict[str, str]]:
    """Split one locale file into translated lines, code strings and keys
    naming something portkit ships none of (key -> what it names).

    ``runtime_keys`` are Java keys a fixed station runtime shows itself (the
    waystone menu's title and chat messages, #178): they keep their Java key
    as the Bedrock key, which the runtime names in a rawtext ``translate``.
    """
    lines: list[str] = []
    code_strings: list[str] = []
    unshipped: dict[str, str] = {}
    for key, value in entries.items():
        runtime = key in runtime_keys
        translated = key if runtime else _translate_key(key, namespace)
        if translated is not None:
            text = _runtime_value(str(value)) if runtime else str(value)
            lines.append(f"{translated}={_one_line(text)}")
            continue
        kind, label = _classify(key)
        if kind == CODE_STRING:
            code_strings.append(key)
        else:
            unshipped[key] = label
    return lines, code_strings, unshipped


def _code_entry(source: str, keys, where: str = "") -> Unhandled:
    keys = sorted(keys)
    sample = ", ".join(keys[:3])
    return Unhandled(
        source=source,
        kind=CODE_STRING,
        reason=(f"{len(keys)} string(s){where} belong to mod code with no Bedrock text surface: no "
                f"block, item, entity or creative tab owns them, so only Java code shows them "
                f"(screens, tooltips, chat, config, integrations) (e.g. {sample})"),
    )


def _unshipped_entry(source: str, named: dict[str, str], where: str = "") -> Unhandled:
    by_label: dict[str, int] = {}
    for label in named.values():
        by_label[label] = by_label.get(label, 0) + 1
    labels = ", ".join(f"{label} {n}" for label, n in sorted(by_label.items(), key=lambda t: (-t[1], t[0])))
    sample = ", ".join(sorted(named)[:3])
    return Unhandled(
        source=source,
        kind=UNSHIPPED,
        reason=(f"{len(named)} key(s){where} name things the pack doesn't ship ({labels}), so a Bedrock "
                f"line would name nothing (e.g. {sample})"),
    )


def _gson_rejects(text: str, exc: json.JSONDecodeError) -> bool:
    """True when Java's own reader fails on this file too. Minecraft reads lang
    JSON with Gson, which is lenient about much Python rejects (comments,
    unquoted names) but, even lenient, throws "Expected name" on a comma
    followed by another comma or by '}' inside an object
    (com.google.gson.stream.JsonReader.doPeek, gson 2.10.1); only that case is
    claimed here."""
    if not exc.msg.startswith("Expecting property name"):
        return False
    pos = exc.pos
    if pos >= len(text) or text[pos] not in ",}":
        return False
    before = text[:pos].rstrip()
    return before.endswith(",")


def _book_lines(bedrock: str, book_text: dict[str, dict[str, str]]) -> list[str]:
    """The book page entries for one Bedrock locale: each page's text from the
    Java locale folder that maps to it, else en_us (Citadel's fallback when the
    game language has no file of its own, #182)."""
    own = [java for java, mapped in sorted(_LOCALES.items()) if mapped == bedrock and java in book_text]
    primary = book_text.get(_PRIMARY, {})
    keys = set(primary)
    for java in own:
        keys |= set(book_text[java])
    lines = []
    for key in sorted(keys):
        value = next((book_text[java][key] for java in own if key in book_text[java]), primary.get(key))
        if value:
            lines.append(f"{key}={_one_line(value)}")
    return lines


def convert(mod: SourceMod, runtime_keys: set[str] | frozenset | None = None,
            book_text: dict[str, dict[str, str]] | None = None) -> ConversionResult:
    """``runtime_keys``: Java keys a station runtime of this namespace shows
    (:func:`portkit.converters.stations.station_lang_keys`); they ship under
    their own name instead of counting as code strings. ``book_text``: Java
    locale -> {key: text} of the guide book pages the book viewer shows
    (:func:`portkit.adapters.citadel.books.lang_text`); every Bedrock locale the
    pack ships, and every one a book folder maps to, gets them."""
    result = ConversionResult()
    runtime_keys = frozenset(runtime_keys or ())
    book_text = book_text or {}
    src = mod.assets / "lang"
    if not src.is_dir() and not book_text:
        return result

    converted: dict[str, str] = {}
    primary_untranslated: set[str] = set()

    # The primary locale first: the others report only the keys it lacks.
    paths = sorted(src.glob("*.json"), key=lambda p: (p.stem.lower() != _PRIMARY, p.name)) if src.is_dir() else []
    for path in paths:
        locale = path.stem.lower()
        rel = result.claim(mod, path)
        bedrock = _LOCALES.get(locale)
        if bedrock is None:
            result.unhandled.append(Unhandled(
                rel, LOCALE,
                f"Bedrock has no locale matching {locale!r}: it loads texts/ only for its own fixed "
                f"list of languages, so this file has no slot"))
            continue

        # utf-8-sig: Gson skips a leading byte order mark (JsonReader.fillBuffer),
        # so a file saved with one loads in Java and must here too.
        text = path.read_text(encoding="utf-8-sig")
        try:
            entries = json.loads(text)
        except json.JSONDecodeError as exc:
            if _gson_rejects(text, exc):
                result.unhandled.append(Unhandled(
                    rel, UNREADABLE,
                    f"Java's own reader rejects this file too (Gson: \"Expected name\" at line "
                    f"{exc.lineno} column {exc.colno}, a stray comma), so Java never shows its text"))
            else:
                result.unhandled.append(Unhandled(rel, "lang", f"invalid JSON: {exc}"))
            continue

        lines, code_strings, unshipped = _lines(entries, mod.namespace, runtime_keys)

        if locale == _PRIMARY:
            # The primary locale is where key shapes get reported. Every other
            # locale translates the same keys, so repeating the report per file
            # would multiply one fact by the number of languages shipped.
            primary_untranslated = set(code_strings) | set(unshipped)
            if unshipped:
                result.unhandled.append(_unshipped_entry(rel, unshipped))
            if code_strings:
                result.unhandled.append(_code_entry(rel, code_strings))
        else:
            # Only a key this locale has and the primary does not is news.
            where = f" present in {locale} but not in {_PRIMARY}"
            extra_code = set(code_strings) - primary_untranslated
            extra_unshipped = {k: v for k, v in unshipped.items() if k not in primary_untranslated}
            if extra_unshipped:
                result.unhandled.append(_unshipped_entry(rel, extra_unshipped, where))
            if extra_code:
                result.unhandled.append(_code_entry(rel, extra_code, where))

        if lines:
            converted[bedrock] = "\n".join(sorted(lines)) + "\n"

    if book_text:
        locales = set(converted) | {_LOCALES[j] for j in book_text if j in _LOCALES}
        for bedrock in sorted(locales):
            lines = _book_lines(bedrock, book_text)
            if lines:
                old = converted.get(bedrock, "").splitlines()
                converted[bedrock] = "\n".join(sorted(set(old) | set(lines))) + "\n"

    for bedrock, text in converted.items():
        result.files[f"texts/{bedrock}.lang"] = text
    if converted:
        # en_US first, the way the vanilla packs list it, then the rest by name.
        rest = sorted(k for k in converted if k != "en_US")
        result.files["texts/languages.json"] = (
            (["en_US"] if "en_US" in converted else []) + rest
        )
    return result


# --- once the pack is final (#277 lang) --------------------------------------

_CONTENT_LINE = re.compile(r"^(?:tile|item|entity)\.([^=:.][^=:]*:[^=]+)\.name=")
_GROUP_LINE = re.compile(r"^(itemGroup\.name\.[^=]+)=")


def _strings(value, out: set[str]) -> None:
    if isinstance(value, str):
        out.add(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            out.add(str(k))
            _strings(v, out)
    elif isinstance(value, list):
        for v in value:
            _strings(v, out)


def _source_for(consumed: set[str], bedrock: str, ident: str = "") -> str:
    """The Java lang file a Bedrock locale's line came from: the one of the
    id's namespace when there is one, else the first; the output file when no
    Java file maps to the locale (an adapter's own lines)."""
    javas = {java for java, mapped in _LOCALES.items() if mapped == bedrock}
    found = sorted(c for c in consumed
                   if c.startswith("assets/") and "/lang/" in c
                   and c.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower() in javas)
    ns = ident.split(":", 1)[0] if ident else ""
    own = [c for c in found if c.split("/")[1] == ns]
    return (own or found or [f"texts/{bedrock}.lang"])[0]


def settle(result: ConversionResult, namespaces=()) -> None:
    """Keep only the content lines that name something the pack ships.

    Runs on the merged pack, after blocks and items were withdrawn
    (:func:`portkit.pipeline.drop_untextured`, the recipe and smithing passes):
    a ``tile.``/``item.``/``entity.``/``itemGroup.name.`` line stays when the
    pack defines that identifier or names the key itself (a
    ``minecraft:display_name``). A line naming one of this jar's own blocks,
    items or entities (``namespaces``) that didn't ship stays too, so the name
    is there when its owner converts (a residue agent writing it, #105); the
    owner's own residue entry already says why it didn't ship. The rest
    is dropped, explained: a sub-key (``block.<ns>.<name>.tooltip``) is a
    string Java code shows; a creative tab, or another mod's entry, names
    nothing the pack has. The source text of every kept line is untouched. A
    locale left with no lines drops out of languages.json.
    """
    own = set(namespaces)
    files = result.files
    langs = sorted(p for p in files if p.startswith("texts/") and p.endswith(".lang") and isinstance(files[p], str))
    if not langs:
        return
    shipped: set[str] = set()
    named: set[str] = set()
    for path, body in files.items():
        if path.startswith("texts/") or not isinstance(body, (dict, list)):
            continue
        ident = _declared(body) if isinstance(body, dict) else None
        if ident:
            shipped.add(ident)
        _strings(body, named)

    dropped: dict[str, dict[str, tuple[str, str]]] = {}  # bedrock -> key -> (kind, label/ident)
    for path in langs:
        bedrock = path[len("texts/"):-len(".lang")]
        kept, gone = [], {}
        for line in files[path].splitlines():
            m = _CONTENT_LINE.match(line)
            g = _GROUP_LINE.match(line) if not m else None
            key = line.split("=", 1)[0]
            if not (m or g) or key in named:
                kept.append(line)
                continue
            if m:
                ident = m.group(1)
                if ident in shipped:
                    kept.append(line)
                elif ident.split(":", 1)[0] in own and "." not in ident.split(":", 1)[1]:
                    # The owner is residue on its own account; its line waits
                    # for it rather than being residue twice.
                    kept.append(line)
                elif "." in ident.split(":", 1)[1]:
                    gone[key] = (CODE_STRING, ident)
                else:
                    gone[key] = (UNSHIPPED, ident)
            else:
                gone[key] = (UNSHIPPED, "creative tab")
        if gone:
            dropped[bedrock] = gone
            if kept:
                files[path] = "\n".join(kept) + "\n"
            else:
                del files[path]

    primary = dropped.get("en_US", {})
    for bedrock, gone in sorted(dropped.items(), key=lambda t: (t[0] != "en_US", t[0])):
        news = gone if bedrock == "en_US" else {k: v for k, v in gone.items() if k not in primary}
        if not news:
            continue
        where = "" if bedrock == "en_US" else f" only in {bedrock}"
        code = [k for k, (kind, _) in news.items() if kind == CODE_STRING]
        unshipped = {k: v for k, v in news.items() if v[0] == UNSHIPPED}
        first = next(iter(sorted(news.values(), key=lambda v: v[1])))[1]
        source = _source_for(result.consumed, bedrock, first if ":" in first else "")
        if unshipped:
            labels = {k: ("creative tab" if ident == "creative tab" else "block, item or entity")
                      for k, (_, ident) in unshipped.items()}
            entry = _unshipped_entry(source, labels, where)
            entry.reason += "; a block, item or entity of this jar has its own residue entry saying why"
            result.unhandled.append(entry)
        if code:
            result.unhandled.append(_code_entry(source, code, where + " (sub-keys of a block or item, "
                                                "e.g. its tooltip)"))

    langs_left = sorted(p[len("texts/"):-len(".lang")] for p in files
                        if p.startswith("texts/") and p.endswith(".lang"))
    if "texts/languages.json" in files:
        files["texts/languages.json"] = (["en_US"] if "en_US" in langs_left else []) + \
            [b for b in langs_left if b != "en_US"]
        if not langs_left:
            del files["texts/languages.json"]
