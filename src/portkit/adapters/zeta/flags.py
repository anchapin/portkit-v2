"""Zeta config flags read from bytecode (#280): what ``zeta:flag`` tests.

Zeta (VazkiiMods/Zeta, the library under Quark) registers the load-condition
type ``zeta:flag`` (``{"type": "zeta:flag", "flag": "<name>"}``, optional
``"extraCondition": <bool>``) for recipes and loot tables, and a loot
predicate of the same name. Read from the Zeta 1.1-40 jar (Quark 4.1-487's
pinned library, ``fixtures/real/libraries.toml``):

- ``FlagCondition#test``: a flag containing ``%`` throws; otherwise the first
  ConfigManager whose ``ConfigFlagManager#isValidFlag`` knows the flag answers
  ``extraCondition (default true) && getFlag(flag)``; a flag no manager knows
  is logged ("Non-existent flag {} being used") and passes. portkit never
  takes that last branch: a flag it can't find may come from code it didn't
  read, so it stays undecided (residue), never passed on a guess.
- ``ConfigFlagManager#putFlag(module, flag, value)`` stores
  ``value && module.isEnabled()``; ``putModuleFlag(module)`` is
  ``putFlag(module, module.lowerCaseName(), true)``.
- Where flags come from (``ConfigManager``, ``ConfigObjectMapper``):
  every module's own flag (``putModuleFlag``); every ``@Config(flag = "...")``
  boolean field of a module (``ConfigObjectMapper#readInto``: the field's value
  is the option's default); and the ``ZGatherAdditionalFlags`` load event, whose
  ``@LoadEvent`` handlers call ``putFlag`` themselves
  (``ZetaModuleManager#constructAndSetup`` subscribes every module to the load
  bus, enabled or not, so a disabled module's handler still runs and its
  flags read false).
- ``TentativeModule#from``: a module's name is ``@ZetaLoadModule(name)``, else
  its simple class name without a trailing ``Module``, a space before each
  inner capital (regex ``(?<=.)([A-Z])``); ``lowerCaseName`` is that in lower
  case with spaces as ``_``. Client replacements (``clientReplacement``) stand
  in for a module on the client only and add no flag of their own.
- ``ZetaModule#setEnabled``: enabled is the module's config option (default
  ``enabledByDefault``, the annotation element whose default the annotation
  class's AnnotationDefault gives), and its category's config option (default
  read from ``ConfigManager``), and its category's required mod loaded
  (``ZetaCategory(name, icon, requiredMod)``), and, unless the module's
  "Ignore Anti Overlap" option is set, none of its ``antiOverlap`` mods loaded.

Every one of those defaults is read from the bytecode of the mod being
converted and of the Zeta library jar given with it; when one can't be read
(no Zeta jar, a pattern this reader doesn't know, a required mod decided at
run time) the flags resting on it are undecided rather than guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...bytecode import ClassIndex, Ref, instructions

ANNOTATION = "org/violetmoon/zeta/module/ZetaLoadModule"
_ANN_DESC = f"L{ANNOTATION};"
_CONFIG = "Lorg/violetmoon/zeta/config/Config;"
_LOAD_EVENT = "Lorg/violetmoon/zeta/event/bus/LoadEvent;"
_GATHER = "Lorg/violetmoon/zeta/event/load/ZGatherAdditionalFlags;"
_FLAGS = "org/violetmoon/zeta/config/ConfigFlagManager"
_CATEGORY = "org/violetmoon/zeta/module/ZetaCategory"
_CONFIG_MANAGER = "org/violetmoon/zeta/config/ConfigManager"
_TENTATIVE = "org/violetmoon/zeta/module/TentativeModule"
_BUILDER = "org/violetmoon/zeta/config/ValueDefinition$Builder"
_MODULE = "org/violetmoon/zeta/module/ZetaModule"

_ICONST = {0x03: False, 0x04: True}  # iconst_0, iconst_1
_LDC = (0x12, 0x13)


@dataclass
class Module:
    """One ``@ZetaLoadModule`` class of the mod, as Zeta builds it."""

    cls: str
    name: str  # lowerCaseName: the module's own flag
    category: str
    enabled_by_default: bool
    anti_overlap: tuple[str, ...]


@dataclass
class Flag:
    """Where one flag's value comes from: ``value && module enabled``."""

    name: str
    module: Module
    value: bool | None  # None: the value given to putFlag isn't read
    origin: str  # "module", "config field <Class>.<field>", "load event <Class>#<method>"
    why: str = ""  # why value is None


@dataclass
class Reading:
    """Every flag the mod's Zeta modules register, and what they rest on."""

    flags: dict[str, list[Flag]] = field(default_factory=dict)
    # category name -> required mod ("" for none), or None when it isn't read
    categories: dict[str, str | None] = field(default_factory=dict)
    category_default: bool | None = None  # the categories' enabled option default
    module_default_read: bool = False  # the module option defaults to enabledByDefault
    problem: str = ""  # why nothing could be read (no Zeta library, unknown version)
    source: str = ""  # what the defaults were read from, for citations


def module_name(simple: str, declared: str) -> str:
    """``TentativeModule#from``: the module's lowerCaseName."""
    name = declared or re.sub(r"(?<=.)([A-Z])", r" \1", re.sub(r"Module$", "", simple))
    return name.lower().replace(" ", "_")


def _strings(index: ClassIndex, cls: str, method: str) -> set[str]:
    cf = index.get(cls)
    if cf is None:
        return set()
    out: set[str] = set()
    for m in cf.methods:
        if m.name == method and m.code is not None:
            out |= {i.arg for i in instructions(cf, m.code) if i.op in _LDC and isinstance(i.arg, str)}
    return out


def _option_defaults(index: ClassIndex) -> tuple[bool | None, bool]:
    """(the category option's default, whether the module option defaults to
    ``ZetaModule#enabledByDefault``), read from ``ConfigManager``'s option
    builders: ``ValueDefinition$Builder#defaultValue(Boolean.valueOf(...))``."""
    cf = index.get(_CONFIG_MANAGER)
    if cf is None:
        return None, False
    categories: set[bool] = set()
    module = False
    for m in cf.methods:
        if m.code is None:
            continue
        insns = instructions(cf, m.code)
        names_category = any(i.op == 0xB4 and isinstance(i.arg, Ref) and i.arg.owner == _CATEGORY
                             and i.arg.name == "name" for i in insns)
        for k, i in enumerate(insns):
            if not (i.op == 0xB6 and isinstance(i.arg, Ref) and i.arg.owner == _BUILDER
                    and i.arg.name == "defaultValue" and k >= 2):
                continue
            box, value = insns[k - 1], insns[k - 2]
            if not (box.op == 0xB8 and isinstance(box.arg, Ref) and box.arg.owner == "java/lang/Boolean"):
                continue
            if value.op in _ICONST and names_category:
                categories.add(_ICONST[value.op])
            elif (value.op == 0xB6 and isinstance(value.arg, Ref) and value.arg.owner == _MODULE
                  and value.arg.name == "enabledByDefault"):
                module = True
    # Two category builders disagreeing: not the shape this reader knows.
    return (next(iter(categories)) if len(categories) == 1 else None), module


def _categories(index: ClassIndex) -> dict[str, str | None]:
    """Category name -> required mod ("" for none; None when the required
    mod isn't a constant), from every ``new ZetaCategory(...)`` in the mod."""
    out: dict[str, str | None] = {}
    for cname in index.names():
        raw = index.raw(cname)
        if raw is None or _CATEGORY.encode() not in raw:
            continue
        cf = index.get(cname)
        if cf is None:
            continue
        for m in cf.methods:
            if m.code is None:
                continue
            insns = instructions(cf, m.code)
            for k, i in enumerate(insns):
                if not (i.op == 0xB7 and isinstance(i.arg, Ref) and i.arg.owner == _CATEGORY
                        and i.arg.name == "<init>"):
                    continue
                params = i.arg.desc[1:i.arg.desc.index(")")]
                three = params.endswith("Ljava/lang/String;") and params.count(";") == 3
                at = k - 3 if three else k - 2
                if at < 0 or insns[at].op not in _LDC or not isinstance(insns[at].arg, str):
                    continue
                name = insns[at].arg
                if not three:
                    out.setdefault(name, "")
                    continue
                req = insns[k - 1]
                if req.op in _LDC and isinstance(req.arg, str):
                    out[name] = req.arg
                elif req.op == 0x01:  # aconst_null
                    out[name] = ""
                else:
                    out[name] = None  # e.g. a static field set at run time
    return out


def _stores(index: ClassIndex, cls: str, method: str, desc: str, op: int) -> dict[str, bool | None] | None:
    """Boolean fields of ``cls`` that ``method`` stores with ``op``
    (putfield 0xB5 after ``aload_0``, putstatic 0xB3): the constant stored
    (``iconst_X``), or None for any other value. None when the method isn't
    there or calls another constructor of the class (not followed)."""
    cf = index.get(cls)
    m = cf.method(method, desc) if cf is not None else None
    if m is None or m.code is None:
        return None
    insns = instructions(cf, m.code)
    if method == "<init>" and any(i.op == 0xB7 and isinstance(i.arg, Ref) and i.arg.owner == cls
                                  and i.arg.name == "<init>" for i in insns):
        return None
    out: dict[str, bool | None] = {}
    for k, i in enumerate(insns):
        if i.op == op and isinstance(i.arg, Ref) and i.arg.owner == cls and i.arg.desc == "Z":
            prev = insns[k - 1] if k else None
            this = op == 0xB3 or (k >= 2 and insns[k - 2].op == 0x2A)
            out[i.arg.name] = _ICONST.get(prev.op) if prev is not None and this else None
    return out


def field_default(index: ClassIndex, cls: str, name: str) -> tuple[bool | None, str]:
    """A boolean field's value once the class is initialised and constructed
    (``<clinit>`` for a static field, the no-argument ``<init>`` for an
    instance one), and why it is None when it isn't read. A field the
    initialiser never stores keeps its initial value, false (JVMS 2.3)."""
    cf = index.get(cls)
    if cf is None or cf.fields.get(name) != "Z":
        return None, "not a boolean field"
    if cf.field_access.get(name, 0) & 0x10000:
        return None, "a compile-time constant (ConstantValue), not read here"
    static = bool(cf.field_access.get(name, 0) & 0x0008)
    if static:
        stores = _stores(index, cls, "<clinit>", "()V", 0xB3)
        stores = {} if stores is None and cf.method("<clinit>") is None else stores
    else:
        stores = _stores(index, cls, "<init>", "()V", 0xB5)
    if stores is None:
        return None, "the initialiser isn't read"
    if name not in stores:
        return False, ""
    value = stores[name]
    return value, "" if value is not None else "the initialiser stores a value that isn't a constant"


def read(index: ClassIndex | None) -> Reading:
    """The flags the mod's Zeta modules register, read from its bytecode."""
    reading = Reading()
    if index is None:
        reading.problem = "the jar's classes aren't available"
        return reading
    ann = index.get(ANNOTATION)
    if ann is None:
        reading.problem = (f"Zeta's {ANNOTATION.replace('/', '.')} isn't in the jar or its library "
                           "jars, so module defaults can't be read")
        return reading
    defaults = {m.name: m.default for m in ann.methods if m.has_default}
    if not isinstance(defaults.get("enabledByDefault"), int):
        reading.problem = "ZetaLoadModule#enabledByDefault has no readable default"
        return reading
    naming = _strings(index, _TENTATIVE, "from")
    if not {"Module$", "(?<=.)([A-Z])"} <= naming:
        reading.problem = "Zeta's module naming (TentativeModule#from) isn't the one this reader knows"
        return reading
    reading.category_default, reading.module_default_read = _option_defaults(index)
    reading.categories = _categories(index)
    reading.source = ("Zeta library " + ("jar" if index.is_library(ANNOTATION) else "classes")
                      + f": {ANNOTATION.replace('/', '.')} AnnotationDefault enabledByDefault="
                      + str(bool(defaults["enabledByDefault"])).lower())

    for cname in index.names():
        raw = index.raw(cname)
        if raw is None or _ANN_DESC.encode() not in raw:
            continue
        cf = index.get(cname)
        if cf is None or _ANN_DESC not in cf.annotations:
            continue
        a = {**defaults, **cf.annotations[_ANN_DESC]}
        if a.get("clientReplacement"):
            continue
        simple = cname.rsplit("/", 1)[-1]
        name = module_name(simple, a.get("name") or "")
        overlap = a.get("antiOverlap") or ()
        module = Module(cname, name, str(a.get("category") or ""), bool(a.get("enabledByDefault")),
                        tuple(x for x in overlap if isinstance(x, str)))
        reading.flags.setdefault(name, []).append(Flag(name, module, True, "module"))
        for fname, anns in sorted(cf.field_annotations.items()):
            flag = (anns.get(_CONFIG) or {}).get("flag")
            if not isinstance(flag, str) or not flag:
                continue
            origin = f"config field {cname.replace('/', '.')}.{fname}"
            value, why = field_default(index, cname, fname)
            reading.flags.setdefault(flag, []).append(Flag(flag, module, value, origin, why))
        for m in cf.methods:
            if m.code is None or m.desc != f"({_GATHER})V" or _LOAD_EVENT not in m.annotations:
                continue
            origin = f"load event {cname.replace('/', '.')}#{m.name}"
            insns = instructions(cf, m.code)
            for k, i in enumerate(insns):
                if not (i.op == 0xB6 and isinstance(i.arg, Ref) and i.arg.owner == _FLAGS
                        and i.arg.name == "putFlag"):
                    continue
                value_at, name_at = k - 1, k - 2
                value: bool | None = None
                why = "the value given to putFlag isn't a constant or a field's initial value"
                if insns[value_at].op in _ICONST:
                    value = _ICONST[insns[value_at].op]
                elif (insns[value_at].op == 0xB4 and isinstance(insns[value_at].arg, Ref)
                      and insns[value_at].arg.owner == cname and k >= 3 and insns[k - 2].op == 0x2A):
                    value, why = field_default(index, cname, insns[value_at].arg.name)
                    name_at = k - 3
                elif (insns[value_at].op == 0xB2 and isinstance(insns[value_at].arg, Ref)
                      and insns[value_at].arg.owner == cname):
                    value, why = field_default(index, cname, insns[value_at].arg.name)
                if not (name_at >= 1 and insns[name_at].op in _LDC and isinstance(insns[name_at].arg, str)
                        and insns[name_at - 1].op == 0x2A):
                    continue  # a flag name that isn't a constant: nothing to key it by
                flag = insns[name_at].arg
                reading.flags.setdefault(flag, []).append(
                    Flag(flag, module, value, origin, "" if value is not None else why))
    return reading
