"""Fabric biome modifications read from a jar's bytecode (#281, Fabric slice).

A Forge or NeoForge mod adds a placed feature to biomes with a biome modifier
JSON (:mod:`portkit.converters.features`). A Fabric mod does it in code, with
Fabric API's ``BiomeModifications`` (fabric-biome-api-v1, Fabric API
0.116.17+1.21.1, ``BiomeModifications.java`` L47-50)::

    public static void addFeature(Predicate<BiomeSelectionContext> biomeSelector,
            GenerationStep.Feature step, RegistryKey<PlacedFeature> placedFeatureRegistryKey) {
        create(...).add(ModificationPhase.ADDITIONS, biomeSelector, context -> {
            context.getGenerationSettings().addFeature(step, placedFeatureRegistryKey);
        });
    }

so both spellings come down to ``getGenerationSettings().addFeature(step, key)``
on the biomes a selector picks. This module reads those calls from the jar the
same way for every mod (nothing here names one), starting at the mod's main
entrypoints in its ``fabric.mod.json`` (``main``; ``init`` in
``quilt.mod.json``), where Fabric Loader starts the mod's code:

* :func:`read` follows the calls from each entrypoint into the mod methods that
  (directly or through other mod methods and lambdas) call into
  ``net.fabricmc.fabric.api.biome.v1``, on the abstract values of
  :class:`portkit.blockcode.Machine` (constants, statics from the classes'
  static initializers, ``ResourceLocation``/``ResourceKey``/``TagKey``
  factories). Other mod methods that return a value are run there too; void
  ones that don't reach a biome call are not (registration code, whose effects
  are not what this reads).
* Each method is run once over its control-flow graph, joining the values
  where paths meet, so ``if (a) x(); if (b) y(); ...`` is linear, not 2^n
  paths. A call's *guards* are the branches it is control dependent on
  (Ferrante, Ottenstein and Warren 1987: a node is control dependent on a
  branch edge when it post-dominates the edge's target but not the branch),
  in its own method and in every caller up to the entrypoint. A branch the
  machine decides is no guard; an undecided one is, named by the boolean
  method whose result it tests when there is one (:class:`Gate`), e.g. a
  config wrapper's ``adamantite()``.

What each attachment reads (Mojang names; a Fabric jar is read through its
intermediary mapping, #235, :mod:`portkit.data.mappings`):

* the selector: ``BiomeSelectors.tag(TagKey)`` (a biome tag),
  ``foundInOverworld()``, ``foundInTheNether()``, ``foundInTheEnd()``
  (``BiomeSelectors.java`` L61-84: "all biomes that would normally spawn in
  the Overworld / Nether / End"); anything else (``all()``, ``includeByKey``,
  ``Predicate.and``...) is recorded as a selector this slice doesn't read;
* the step: a ``GenerationStep$Decoration`` constant;
* the placed feature: ``ResourceKey.create(Registries.PLACED_FEATURE, id)``.

Deciding what an attachment means (config gates, biome tags) is
:func:`decide`'s; nothing is guessed (#87): a value the machine can't read
makes the attachment unread, with the reason.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import blockcode
from .blockcode import UNKNOWN, Const, Frame, Lam, Machine, Obj, RL, Unreadable
from .bytecode import ClassIndex, Handle, Indy, Ref, instructions

FABRIC_BIOME = "net/fabricmc/fabric/api/biome/v1/"
_MODIFICATIONS = FABRIC_BIOME + "BiomeModifications"
_SELECTORS = FABRIC_BIOME + "BiomeSelectors"
_RESOURCE_KEY = "net/minecraft/resources/ResourceKey"
_TAG_KEY = "net/minecraft/tags/TagKey"
_REGISTRIES = "net/minecraft/core/registries/Registries"
_DECORATION = "net/minecraft/world/level/levelgen/GenerationStep$Decoration"
_PREDICATE = "java/util/function/Predicate"

# BiomeSelectors' dimension selectors (BiomeSelectors.java L61-84).
_DIMENSION_SELECTORS = {"foundInOverworld": "overworld", "foundInTheNether": "nether",
                        "foundInTheEnd": "the_end"}

_MAX_VISITS = 50_000
_HELPER_BUDGET = 50_000


@dataclass(frozen=True)
class Key:
    """A ``ResourceKey``: the registry (a ``Registries`` field name) and the id."""

    registry: str
    ident: str


@dataclass(frozen=True)
class Tag:
    registry: str
    ident: str


@dataclass(frozen=True)
class Selector:
    """``kind``: tag (``value`` the biome tag id), overworld, nether, the_end,
    or other (``value`` says what it is)."""

    kind: str
    value: str = ""


@dataclass(frozen=True)
class Gate:
    """The undecided result of a no-argument boolean method."""

    owner: str
    name: str
    desc: str

    @property
    def label(self) -> str:
        return f"{self.owner.replace('/', '.')}.{self.name}()"


@dataclass(frozen=True)
class Guard:
    """One branch an attachment depends on: it happens only when ``gate`` is
    ``sense``; ``gate`` None for a branch on anything else (``where`` says)."""

    gate: Gate | None
    sense: bool
    where: str

    @property
    def label(self) -> str:
        if self.gate is not None:
            return f"{self.gate.label} is {'true' if self.sense else 'false'}"
        return f"an undecided branch in {self.where}"


@dataclass
class Attachment:
    selector: object
    step: object
    key: object
    site: str  # Class.method the call is in
    guards: tuple = ()
    removal: bool = False

    @property
    def feature(self) -> str | None:
        k = self.key
        return k.ident if isinstance(k, Key) and k.registry == "PLACED_FEATURE" else None

    @property
    def step_name(self) -> str | None:
        s = self.step
        return s.name.lower() if isinstance(s, Const) and s.owner == _DECORATION else None


@dataclass
class Reading:
    attachments: list[Attachment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# -- control dependence ----------------------------------------------------------

_RETURNS = frozenset(range(0xAC, 0xB2))
_IFS = frozenset((*range(0x99, 0xA7), 0xC6, 0xC7))


def _successors(code: list) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for k, insn in enumerate(code):
        nxt = code[k + 1].offset if k + 1 < len(code) else None
        op = insn.op
        if op in _RETURNS or op == 0xBF:
            out[insn.offset] = []
        elif op in (0xA7, 0xC8):
            out[insn.offset] = [insn.arg]
        elif op in _IFS:
            out[insn.offset] = [insn.arg] + ([nxt] if nxt is not None else [])
        elif op in (0xAA, 0xAB):
            default, table = insn.arg
            out[insn.offset] = sorted({default, *table.values()})
        else:
            out[insn.offset] = [nxt] if nxt is not None else []
    return out


def control_dependence(code: list) -> dict[int, list[tuple[int, int]]]:
    """For each instruction offset, the (branch offset, successor offset)
    edges it is control dependent on."""
    succ = _successors(code)
    nodes = [i.offset for i in code]
    index = {n: k for k, n in enumerate(nodes)}
    exit_bit = 1 << len(nodes)
    full = (1 << (len(nodes) + 1)) - 1
    pdom = {n: full for n in nodes}
    changed = True
    while changed:
        changed = False
        for n in reversed(nodes):
            nexts = succ[n]
            acc = full
            if not nexts:
                acc = exit_bit
            for s in nexts:
                acc &= pdom.get(s, full)
            new = acc | (1 << index[n])
            if new != pdom[n]:
                pdom[n] = new
                changed = True

    def ipdom(n: int) -> int | None:
        strict = pdom[n] & ~(1 << index[n])
        # The immediate post-dominator is the strict one every other strict
        # one post-dominates (its own set is the largest proper subset).
        best, size = None, -1
        for m in nodes:
            if strict >> index[m] & 1:
                c = bin(pdom[m]).count("1")
                if pdom[m] & strict == pdom[m] and c > size:
                    best, size = m, c
        return best

    ip = {n: ipdom(n) for n in nodes}
    cd: dict[int, list[tuple[int, int]]] = {}
    for b in nodes:
        targets = list(dict.fromkeys(succ[b]))
        if len(targets) < 2:
            continue
        for s in targets:
            runner = s
            seen = set()
            while runner is not None and runner != ip[b] and runner not in seen:
                seen.add(runner)
                cd.setdefault(runner, []).append((b, s))
                runner = ip.get(runner)
    return cd


# -- the machine --------------------------------------------------------------------

@dataclass(eq=False)
class _Ctx:
    method: str  # Class.method
    ident: tuple
    depth: int
    cd: dict
    pc: int = 0
    outcomes: dict = field(default_factory=dict)  # branch pc -> set of chosen successors (None: forked)
    conds: dict = field(default_factory=dict)  # branch pc -> (value, op, target)


def _eq(a, b) -> bool:
    if a is b:
        return True
    if type(a) is not type(b) or isinstance(a, (Obj,)):
        return False
    try:
        return a == b
    except Exception:  # pragma: no cover - exotic values
        return False


def _join(old: Frame, new: Frame) -> Frame | None:
    """The frame at a join point, or None when ``new`` adds nothing."""
    if len(old.stack) != len(new.stack):
        raise Unreadable("paths meet with different stack depths")
    changed = new.forked and not old.forked
    locals_ = []
    for a, b in zip(old.locals, new.locals):
        if a is UNKNOWN or _eq(a, b):
            locals_.append(a)
        else:
            locals_.append(UNKNOWN)
            changed = True
    stack = []
    for a, b in zip(old.stack, new.stack):
        if a is UNKNOWN or _eq(a, b):
            stack.append(a)
        else:
            stack.append(UNKNOWN)
            changed = True
    if not changed:
        return None
    return Frame(old.pc, locals_, stack, old.forked or new.forked, old.effects)


class BiomeMachine(Machine):
    def __init__(self, classes: ClassIndex, reaching: set[tuple[str, str, str]]):
        super().__init__(classes)
        self.reaching = reaching
        self._ctxs: list[_Ctx] = []
        self._from_exec = False
        self._selectors: list = []
        self.records: dict[tuple, tuple[Attachment, tuple]] = {}
        self.unread: list[str] = []
        self.ran: set[tuple[str, str, str]] = set()

    # -- running one method over its control-flow graph --------------------------
    def exec_method(self, cf, m, args: list) -> list:
        if self.depth >= blockcode._MAX_DEPTH:
            raise Unreadable("calls nest too deeply")
        self.depth += 1
        code = instructions(cf, m.code)
        at = {insn.offset: k for k, insn in enumerate(code)}
        ctx = _Ctx(f"{cf.name.replace('/', '.')}.{m.name}", (cf.name, m.name, m.desc), self.depth,
                   control_dependence(code))
        self.ran.add(ctx.ident)
        self._ctxs.append(ctx)
        try:
            work = [Frame(0, self._wide_locals(m, args) + [UNKNOWN] * 256, [])]
            states: dict[int, Frame] = {}
            results: list = []
            visits = 0
            while work:
                f = work.pop()
                old = states.get(f.pc)
                if old is not None:
                    joined = _join(old, f)
                    if joined is None:
                        continue
                    f = joined
                states[f.pc] = f
                visits += 1
                if visits > _MAX_VISITS:
                    raise Unreadable(f"too much code to follow in {ctx.method}")
                k = at.get(f.pc)
                if k is None:
                    raise Unreadable(f"jump into the middle of an instruction in {ctx.method}")
                insn = code[k]
                nxt = code[k + 1].offset if k + 1 < len(code) else None
                run = Frame(f.pc, list(f.locals), list(f.stack), f.forked, f.effects)
                ctx.pc = insn.offset
                if run.forked and insn.op in (0xB3, 0xB5):
                    # A write on one side of an undecided branch: what the
                    # field holds afterwards depends on the path, so unknown.
                    value = run.stack.pop()
                    if insn.op == 0xB3:
                        self.statics[(self._field_owner(insn.arg.owner, insn.arg.name), insn.arg.name)] = UNKNOWN
                    else:
                        obj = run.stack.pop()
                        if isinstance(obj, Obj):
                            obj.fields[insn.arg.name] = UNKNOWN
                    del value
                    run.pc = nxt if nxt is not None else -1
                    work.append(run)
                    continue
                outcome = self.step(cf, insn, run, nxt)
                if insn.op in (0xAA, 0xAB):
                    ctx.outcomes.setdefault(insn.offset, set()).add(None if outcome else run.pc)
                    ctx.conds[insn.offset] = (UNKNOWN, insn.op, None)
                if outcome is None:
                    if run.pc != -1:
                        work.append(run)
                    continue
                kind, payload = outcome
                if kind == "return":
                    results.append(payload)
                elif kind == "fork":
                    work.extend(payload)
            return results
        finally:
            self._ctxs.pop()
            self.depth -= 1

    def _branch(self, op: int, target: int, f: Frame, nxt: int | None = None):
        s = f.stack
        value = s[-1] if (op <= 0x9E or op in (0xC6, 0xC7)) and s else UNKNOWN
        out = super()._branch(op, target, f, nxt)
        if self._ctxs and self.depth == self._ctxs[-1].depth:
            ctx = self._ctxs[-1]
            ctx.outcomes.setdefault(ctx.pc, set()).add(None if out is not None else f.pc)
            ctx.conds[ctx.pc] = (value, op, target)
        return out

    def _write(self, frame: Frame, target=None) -> None:
        if self._ctxs and self.depth == self._ctxs[-1].depth:
            return  # a new object's constructor; field writes are handled in exec_method
        super()._write(frame, target)

    def _invoke(self, op: int, ref: Ref, f: Frame):
        self._from_exec = bool(self._ctxs) and self.depth == self._ctxs[-1].depth
        return super()._invoke(op, ref, f)

    def call(self, owner: str, name: str, desc: str, args: list, special: bool = False,
             static: bool = False) -> list:
        from_exec, self._from_exec = self._from_exec, False
        recv = None if static or not args else args[0]
        if isinstance(recv, Lam):
            return super().call(owner, name, desc, args, special, static)
        start = recv.cls if isinstance(recv, Obj) and not special and not static and self.is_mod(recv.cls) \
            else owner
        returns = not desc.endswith(")V")
        if self.is_mod(start):
            found = self.find_method(start, name, desc)
            if found is not None and (found[0].name, found[1].name, found[1].desc) in self.reaching:
                if static:
                    self.init_class(start)
                try:
                    results = self.exec_method(*found, args)
                except Unreadable as exc:
                    self.unread.append(f"{found[0].name.replace('/', '.')}.{name}: {exc}")
                    return [UNKNOWN] if returns else [None]
                return results or ([UNKNOWN] if returns else [None])
            if found is not None and not returns and from_exec:
                return [None]  # registration code that reaches no biome call
            saved = self.steps
            self.steps = max(saved, blockcode._MAX_STEPS - _HELPER_BUDGET)
            try:
                results = super().call(owner, name, desc, args, special, static)
            except Unreadable:
                results = [UNKNOWN] if returns else [None]
            finally:
                self.steps = saved
            # A mod's own boolean method the machine can't decide is named
            # by itself, not by what it calls (a config wrapper's
            # ``adamantite()`` rather than Boolean#booleanValue inside it).
            if desc == "()Z" and results and all(r is UNKNOWN or isinstance(r, Gate) for r in results):
                return [Gate(start, name, desc)]
            return results
        results = super().call(owner, name, desc, args, special, static)
        if desc == "()Z" and results and all(r is UNKNOWN for r in results):
            return [Gate(start, name, desc)]
        return results

    # -- what the biome API calls mean -------------------------------------------
    def _record(self, args: list) -> None:  # registrations are not read here
        return None

    def _attach(self, selector, step, key, removal: bool = False) -> None:
        chain = tuple((c, c.pc) for c in self._ctxs)
        where = tuple((c.ident, pc) for c, pc in chain)
        site = self._ctxs[-1].method if self._ctxs else "?"
        self.records[where] = (Attachment(selector, step, key, site, removal=removal), chain)

    def vanilla(self, owner: str, name: str, desc: str, args: list, static: bool):
        recv = None if static else (args[0] if args else None)
        rest = args if static else args[1:]
        if owner == _RESOURCE_KEY:
            if static and name == "create" and len(rest) == 2:
                reg, loc = rest
                if isinstance(reg, Const) and reg.owner == _REGISTRIES and isinstance(loc, RL):
                    return [Key(reg.name, loc.path)]
                return [UNKNOWN]
            if isinstance(recv, Key) and name == "location":
                return [RL(recv.ident)]
        if owner == _TAG_KEY and static and name == "create" and len(rest) == 2:
            reg, loc = rest
            if isinstance(reg, Const) and reg.owner == _REGISTRIES and isinstance(loc, RL):
                return [Tag(reg.name, loc.path)]
            return [UNKNOWN]
        if isinstance(recv, Tag) and name == "location":
            return [RL(recv.ident)]
        if owner == _SELECTORS and static:
            if name == "tag" and len(rest) == 1:
                t = rest[0]
                if isinstance(t, Tag) and t.registry == "BIOME":
                    return [Selector("tag", t.ident)]
                return [Selector("other", "BiomeSelectors.tag of a tag that can't be read")]
            if name in _DIMENSION_SELECTORS and not rest:
                return [Selector(_DIMENSION_SELECTORS[name])]
            return [Selector("other", f"BiomeSelectors.{name}")]
        if isinstance(recv, Selector) and name in ("and", "or", "negate"):
            return [Selector("other", f"a selector combined with Predicate.{name}")]
        if owner == _MODIFICATIONS and static:
            if name == "addFeature" and len(rest) == 3:
                self._attach(*rest)
                return [None]
            if name == "create":
                return [Obj("__biome_modification")]
            return [None] if desc.endswith(")V") else [UNKNOWN]
        if isinstance(recv, Obj) and recv.cls == "__biome_modification" and name == "add" and len(rest) == 3:
            selector, consumer = rest[1], rest[2]
            if isinstance(consumer, Lam):
                self._selectors.append(selector)
                try:
                    self.call_lambda(consumer, [Obj("__selection_context"), Obj("__modification_context")])
                finally:
                    self._selectors.pop()
            else:
                self.unread.append("a BiomeModification.add whose modifier isn't a lambda in the jar")
            return [recv]
        if isinstance(recv, Obj) and recv.cls == "__modification_context" and name == "getGenerationSettings":
            return [Obj("__generation_settings")]
        if isinstance(recv, Obj) and recv.cls == "__generation_settings" and name in ("addFeature",
                                                                                      "removeFeature"):
            selector = self._selectors[-1] if self._selectors else UNKNOWN
            if len(rest) == 2:
                self._attach(selector, rest[0], rest[1], removal=name == "removeFeature")
            elif name == "removeFeature" and len(rest) == 1:
                self._attach(selector, UNKNOWN, rest[0], removal=True)
            return [None] if desc.endswith(")V") else [UNKNOWN]
        if owner.startswith(FABRIC_BIOME) and name in ("addFeature", "removeFeature"):
            self.unread.append(f"{owner.rsplit('/', 1)[-1]}.{name} on a context the reader didn't follow")
            return [None] if desc.endswith(")V") else [UNKNOWN]
        return super().vanilla(owner, name, desc, args, static)


# -- which methods reach the biome API -------------------------------------------

def _refs(cf, m) -> set[tuple[str, str, str]]:
    out = set()
    if m.code is None:
        return out
    try:
        code = instructions(cf, m.code)
    except Exception:  # pragma: no cover - malformed code
        return out
    for insn in code:
        if insn.op in (0xB6, 0xB7, 0xB8, 0xB9) and isinstance(insn.arg, Ref):
            out.add((insn.arg.owner, insn.arg.name, insn.arg.desc))
        elif insn.op == 0xBA and isinstance(insn.arg, Indy):
            for a in insn.arg.args:
                if isinstance(a, Handle):
                    out.add((a.ref.owner, a.ref.name, a.ref.desc))
    return out


def reaching(classes: ClassIndex) -> set[tuple[str, str, str]]:
    """Mod methods that call into Fabric's biome API, directly or through
    other mod methods (and lambdas) that do."""
    marker = FABRIC_BIOME.encode()
    found: set[tuple[str, str, str]] = set()
    for name in classes.names():
        raw = classes.raw(name)
        if raw is None or marker not in raw:
            continue
        cf = classes.get(name)
        for m in cf.methods if cf else ():
            if any(o.startswith(FABRIC_BIOME) for o, _n, _d in _refs(cf, m)):
                found.add((cf.name, m.name, m.desc))
    frontier = set(found)
    while frontier:
        owners = {o.encode() for o, _n, _d in frontier}
        new = set()
        for name in classes.names():
            raw = classes.raw(name)
            if raw is None or not any(o in raw for o in owners):
                continue
            cf = classes.get(name)
            for m in cf.methods if cf else ():
                ident = (cf.name, m.name, m.desc)
                if ident not in found and _refs(cf, m) & frontier:
                    new.add(ident)
        found |= new
        frontier = new
    return found


def entrypoints(metadata: dict[str, bytes]) -> list[tuple[str, str | None]]:
    """(class internal name, method or None) for each main entrypoint."""
    out = []
    for fname, key in (("fabric.mod.json", "main"), ("quilt.mod.json", "init")):
        raw = metadata.get(fname)
        if raw is None:
            continue
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        points = (doc.get("entrypoints") or {}) if fname == "fabric.mod.json" else \
            ((doc.get("quilt_loader") or {}).get("entrypoints") or {})
        values = points.get(key) or []
        for v in values if isinstance(values, list) else [values]:
            value = v.get("value") if isinstance(v, dict) else v
            if not isinstance(value, str):
                continue
            cls, _, method = value.partition("::")
            out.append((cls.replace(".", "/"), method or None))
    return out


def read(classes: ClassIndex | None, metadata: dict[str, bytes]) -> Reading:
    """Every biome attachment the mod's main entrypoints make, with guards."""
    reading = Reading()
    if classes is None or not len(classes):
        return reading
    reach = reaching(classes)
    if not reach:
        return reading
    machine = BiomeMachine(classes, reach)
    points = entrypoints(metadata)
    for cls, method in points:
        cf = classes.get(cls)
        if cf is None:
            continue
        if method is None:
            # ModInitializer#onInitialize() (Fabric Loader; Quilt's
            # ModInitializer#onInitialize(ModContainer)).
            m = cf.method("onInitialize", "()V") or next(
                (x for x in cf.methods if x.name == "onInitialize"), None)
        else:
            m = next((x for x in cf.methods if x.name == method and x.desc.startswith("()")), None)
        if m is None or m.code is None or (cf.name, m.name, m.desc) not in reach:
            continue
        args = [] if m.access & 0x0008 else [Obj(cf.name)]
        args += [UNKNOWN] * blockcode._arg_count(m.desc)[0]
        try:
            machine.exec_method(cf, m, args)
        except Unreadable as exc:
            reading.notes.append(f"Fabric biome modifications from {cls.replace('/', '.')} couldn't be "
                                 f"followed: {exc}")
    for why in dict.fromkeys(machine.unread):
        reading.notes.append(f"Fabric biome modification not read: {why}")
    direct = {i for i in reach if i not in machine.ran}
    sites = sorted({f"{c.replace('/', '.')}.{n}" for c, n, _d in direct
                    if any(o.startswith(FABRIC_BIOME) for o, _n, _x in _refs(classes.get(c), classes.get(c).method(n, _d)))})
    if sites:
        reading.notes.append("Fabric biome API calls not reached from the mod's main entrypoint(s), so not read: "
                             + ", ".join(sites[:8]) + (" ..." if len(sites) > 8 else ""))
    for att, chain in machine.records.values():
        att.guards = _guards(chain)
        reading.attachments.append(att)
    return reading


def _guards(chain) -> tuple[Guard, ...]:
    out = []
    for ctx, pc in chain:
        for b, s in ctx.cd.get(pc, ()):
            outs = ctx.outcomes.get(b, set())
            if not outs or (None not in outs and len(outs) == 1):
                continue  # decided (or never run)
            value, op, target = ctx.conds.get(b, (UNKNOWN, None, None))
            where = f"{ctx.method} (offset {b})"
            if isinstance(value, Gate) and op in (0x99, 0x9A):
                taken = s == target
                sense = (not taken) if op == 0x99 else taken
                out.append(Guard(value, sense, where))
            else:
                out.append(Guard(None, s == target, where))
    return tuple(dict.fromkeys(out))


# -- deciding what an attachment means ---------------------------------------------

@dataclass
class CodeAttachment:
    """One attachment as the ore converter takes it: a biome-modifier-shaped
    ``doc`` (``biomes`` as vanilla dimension tags, ``step``, ``features``) or
    the reason it can't be one (``refused``)."""

    source: str  # what made it, for notes and residue reasons
    feature: str
    doc: dict
    refused: str | None = None
    consumed: set = field(default_factory=set)  # the jar's biome tag files it read
    removal: bool = False


class _Refused(Exception):
    pass


_BIOME_TAG_DIRS = ("tags/worldgen/biome", "tags/worldgen/biomes")
# Vanilla's and the loaders' namespaces: a tag there is never only the jar's
# (portkit.data.tags.SHARED_NAMESPACES, #160), plus Quilt's.
_SHARED = frozenset({"minecraft", "c", "forge", "neoforge", "fabric", "quilt"})


def _tag_file(root: Path, ident: str) -> str | None:
    ns, _, path = ident.partition(":")
    for d in _BIOME_TAG_DIRS:
        rel = f"data/{ns}/{d}/{path}.json"
        if (root / rel).is_file():
            return rel
    return None


def resolve_biomes(root: Path, tag: str, namespaces: set[str], convention: dict[str, str],
                   dimension_tags: set[str], seen: tuple = ()) -> tuple[list[str], set[str]]:
    """The vanilla dimension tags a biome tag comes down to, and the jar's
    tag files read on the way; raises _Refused with the reason otherwise.

    Only exact facts count (5b, rejected: never a guess from a tag's name):
    a vanilla dimension tag; a loader convention tag whose pinned definition
    is exactly one (``convention``); or a tag in the jar's own namespace whose
    every member resolves the same way."""
    if tag in seen:
        raise _Refused(f"biome tag #{tag} includes itself")
    ns = tag.partition(":")[0]
    own_file = _tag_file(root, tag)
    if tag in dimension_tags or tag in convention:
        if own_file is not None:
            raise _Refused(f"the jar adds to #{tag} ({own_file}), whose other members aren't known")
        return [convention.get(tag, tag)], set()
    if ns in _SHARED or ns not in namespaces:
        raise _Refused(f"biome tag #{tag} is not the jar's own, a vanilla dimension tag, or a loader convention "
                       "tag whose pinned definition is exactly one; other biome sets have no Bedrock biome map "
                       "here (#281 pick 3)")
    if own_file is None:
        raise _Refused(f"biome tag #{tag} has no file in the jar")
    try:
        doc = json.loads((root / own_file).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise _Refused(f"biome tag file {own_file} can't be read")
    values = doc.get("values") if isinstance(doc, dict) else None
    if not isinstance(values, list) or not values:
        raise _Refused(f"biome tag file {own_file} has no values")
    out, consumed = [], {own_file}
    for v in values:
        ident = v.get("id") if isinstance(v, dict) else v
        if not isinstance(ident, str):
            raise _Refused(f"biome tag file {own_file} has an entry that isn't an id")
        if not ident.startswith("#"):
            raise _Refused(f"biome tag #{tag} names the biome {ident} itself; Java biomes have no Bedrock "
                           "biome map here (only vanilla dimension tags, #281 pick 3)")
        found, files = resolve_biomes(root, ident[1:], namespaces, convention, dimension_tags, seen + (tag,))
        out += found
        consumed |= files
    return list(dict.fromkeys(out)), consumed


_DIMENSION_TAG = {"overworld": "minecraft:is_overworld", "nether": "minecraft:is_nether",
                  "the_end": "minecraft:is_end"}


def _gate_entry(gate: Gate, context, table=None):
    from .conditions import flag_entries
    for entry in flag_entries(table if table is not None else getattr(context, "_table", None)):
        if entry.get("code_gate") == gate.owner:
            return entry
    return None


def decide_guards(guards, context) -> str | None:
    """None when every guard holds in this conversion (cited config defaults,
    or the user's ``--config``); else the residue reason."""
    for g in guards:
        if g.gate is None:
            return f"attached only on one side of {g.label} (#281: Fabric code-attached ores)"
        entry = _gate_entry(g.gate, context) if context is not None else None
        if entry is None:
            return (f"attached only when {g.label}, a code condition with no cited config default "
                    "(portkit/data/config_flag_defaults.json)")
        kind = str(entry.get("condition"))
        arg = entry.get("argument")
        verdict = context.flag_verdict(kind, arg, g.gate.name)
        if verdict.passes is None:
            return f"attached only when {g.label}: {verdict.reason()}"
        if verdict.passes != g.sense:
            how = "set by user config" if verdict.user_disabled or any(a.user for a in verdict.assumed) \
                else "its cited default"
            return (f"not attached here: it needs {g.label}, and {g.gate.label} is "
                    f"{'on' if verdict.passes else 'off'} ({how}; {verdict.why})")
        context.remember(verdict)
    return None


def decide(reading: Reading, root: Path, namespaces: set[str], context, convention: dict[str, str],
           dimension_tags: set[str]) -> list[CodeAttachment]:
    out = []
    for att in reading.attachments:
        feature = att.feature
        if feature is None:
            continue  # no placed feature key read: nothing to tie it to (see notes)
        source = f"{att.site} (Fabric BiomeModifications, read from bytecode)"
        doc = {"type": "fabric:code", "features": [feature]}
        item = CodeAttachment(source, feature, doc, removal=att.removal)
        try:
            if att.removal:
                raise _Refused("removed in code")
            why = decide_guards(att.guards, context)
            if why:
                raise _Refused(why)
            step = att.step_name
            if step is None:
                raise _Refused("the generation step can't be read from the code")
            doc["step"] = step
            sel = att.selector
            if not isinstance(sel, Selector):
                raise _Refused("the biome selector can't be read from the code")
            if sel.kind == "tag":
                tags, item.consumed = resolve_biomes(root, sel.value, namespaces, convention, dimension_tags)
            elif sel.kind in _DIMENSION_TAG:
                # BiomeSelectors.foundInOverworld/TheNether/TheEnd: "all biomes
                # that would normally spawn in" that dimension (BiomeSelectors.java
                # L61-84), the vanilla dimension tag's biomes.
                tags = [_DIMENSION_TAG[sel.kind]]
            else:
                raise _Refused(f"biome selector {sel.value or sel.kind} isn't one this slice reads "
                               "(tag, foundInOverworld/TheNether/TheEnd)")
            doc["biomes"] = [f"#{t}" for t in tags]
        except _Refused as exc:
            item.refused = str(exc)
        out.append(item)
    return out
