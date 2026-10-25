"""Applied Energistics 2 (#296): how its machines' ``facing`` and ``spin`` are placed.

AE2 (AppliedEnergistics/Applied-Energistics-2, tag ``neoforge/v19.2.18``,
the gauntlet's 1.21.1 NeoForge jar) gives a machine all 24 orientations of a
cube with two block states, ``facing`` (vanilla ``BlockStateProperties.FACING``)
and ``spin`` (0-3, its own ``IntegerProperty``), through an orientation
strategy each block class names:

* ``AEBaseBlock#getStateForPlacement`` (``src/main/java/appeng/block/AEBaseBlock.java``
  L108-111) is ``getOrientationStrategy().getStateForPlacement(defaultBlockState(), context)``;
  a block whose ``getOrientationStrategy`` returns ``OrientationStrategies.full()``
  (``ChargerBlock`` L65-66, ``InscriberBlock`` L84-85, ``IOPortBlock`` L65-66,
  ``SpatialIOPortBlock`` L65-66, ``VibrationChamberBlock`` L64-65) is placed by
  ``FacingWithSpinStrategy``.
* ``FacingWithSpinStrategy#getStateForPlacement`` (``api/orientation/FacingWithSpinStrategy.java``
  L60-75): forward = the player's horizontal facing turned round, up = UP;
  when the player's pitch is above 65 (looking down) forward = UP and up =
  the player's horizontal facing; below -65 (looking up) forward = DOWN and
  up = the player's horizontal facing. ``setOrientation(state, forward, up)``
  (``IOrientationStrategy`` L57-59) sets ``facing`` = forward and ``spin`` =
  ``SpinMapping.getSpinFromUp(facing, up)`` (``block/orientation/SpinMapping.java``
  L34-42): the index of ``up`` in the facing's row of ``SPIN_DIRECTIONS``.
  Nothing else in the state is set: every other state starts where
  ``defaultBlockState()`` has it.
* ``InscriberBlock#getStateForPlacement`` (L88-94) adds ``waterlogged`` from
  the fluid at the clicked position to ``super``'s.
* The blockstates turn each variant by ``x``, ``y`` and AE2's own variant key
  ``ae2:z``, read by AE2's mixin ``VariantDeserializerMixin`` (L36-48) into
  ``BlockstateDefinitionHook#rotateVariant`` (L20-48): the quarter turns are
  composed as ``rotateYXZ(-y, -x, -z)``, the order vanilla's
  ``BlockModelRotation`` composes ``x`` and ``y`` in, so ``ae2:z`` is a turn
  about z applied before x and y.

:func:`orientations` reads all of that from the jar, never from a table
here: the method each block class resolves, the instructions of
``FacingWithSpinStrategy#getStateForPlacement`` (its calls and its two pitch
constants, which must be exactly the form above), and ``SpinMapping``'s
``SPIN_DIRECTIONS`` from its class initializer. A jar whose code differs
gets no orientation (or the reason it isn't read), never a guess.

Bedrock has no pitch threshold: ``minecraft:placement_direction``'s
``minecraft:facing_direction`` is the player's facing over six values, its
up/down cut not documented (MicrosoftDocs minecraft-creator, Block Traits:
placement_direction). It stands in for AE2's 65-degree pitch rule as a
labelled **DEFAULT** (#296).
"""
from __future__ import annotations

from .. import Adapter, Orientation

NAMESPACE = "ae2"
_BASE = "appeng/block/AEBaseBlock"
_STRATEGIES = "appeng/api/orientation/OrientationStrategies"
_STRATEGY = "appeng/api/orientation/IOrientationStrategy"
_FULL = "appeng/api/orientation/FacingWithSpinStrategy"
_SPIN_MAPPING = "appeng/block/orientation/SpinMapping"
_DIRECTION = "net/minecraft/core/Direction"
_STRATEGY_DESC = f"()L{_STRATEGY};"
_PLACEMENT_DESC = ("(Lnet/minecraft/world/item/context/BlockPlaceContext;)"
                   "Lnet/minecraft/world/level/block/state/BlockState;")
_SIX = ("down", "up", "north", "south", "west", "east")  # Direction's ordinal order
_CARDINALS = ("north", "east", "south", "west")
_OPPOSITE = {"down": "up", "up": "down", "north": "south", "south": "north", "west": "east", "east": "west"}
# FacingWithSpinStrategy#getStateForPlacement as its compiled calls, field
# reads and constants run (tag neoforge/v19.2.18 L60-75), with the two pitch
# constants left as None: they are read.
_FULL_PLACEMENT = (
    ("getstatic", "Direction.UP"), ("invokevirtual", "BlockPlaceContext.getHorizontalDirection"),
    ("invokevirtual", "Direction.getOpposite"), ("invokevirtual", "BlockPlaceContext.getPlayer"),
    ("invokevirtual", "Player.getXRot"), ("ldc", None), ("invokevirtual", "Direction.getOpposite"),
    ("getstatic", "Direction.UP"), ("invokevirtual", "Player.getXRot"), ("ldc", None),
    ("invokevirtual", "Direction.getOpposite"), ("getstatic", "Direction.DOWN"),
    ("invokevirtual", "FacingWithSpinStrategy.setOrientation"), ("areturn", None),
)
_SOURCE = ("AE2 FacingWithSpinStrategy#getStateForPlacement (pitch {down} / {up}) through "
           "AEBaseBlock#getStateForPlacement and SpinMapping.SPIN_DIRECTIONS, read from the jar")


def _shape(cf, method) -> tuple:
    from ...bytecode import Ref, instructions
    out = []
    for insn in instructions(cf, method.code):
        if not insn.name.startswith(("invoke", "ldc", "getstatic", "putstatic", "areturn")):
            continue
        arg = insn.arg
        if isinstance(arg, Ref):
            arg = f"{arg.owner.rsplit('/', 1)[-1]}.{arg.name}"
        out.append((insn.name.replace("ldc_w", "ldc").replace("ldc2_w", "ldc"), arg))
    return tuple(out)


def _declaring(classes, cls: str, name: str, desc: str):
    """(class file, method) of the first class from ``cls`` up that declares it."""
    seen = set()
    while cls and cls not in seen:
        seen.add(cls)
        cf = classes.get(cls)
        if cf is None:
            return None, None
        method = cf.method(name, desc)
        if method is not None and method.code is not None:
            return cf, method
        cls = cf.super_name
    return None, None


def _spin_rows(classes) -> tuple[tuple[tuple, ...] | None, str]:
    """SpinMapping.SPIN_DIRECTIONS (one row of four directions per facing, in
    Direction order) as its class initializer builds it, or why not."""
    from ...bytecode import Ref, instructions
    cf = classes.get(_SPIN_MAPPING)
    method = cf.method("<clinit>", "()V") if cf is not None else None
    if method is None or method.code is None:
        return None, f"{_SPIN_MAPPING} has no class initializer"
    dirs, stored = [], False
    for insn in instructions(cf, method.code):
        if insn.name == "getstatic" and isinstance(insn.arg, Ref) and insn.arg.owner == _DIRECTION:
            dirs.append(insn.arg.name.lower())
        elif insn.name == "putstatic" and isinstance(insn.arg, Ref) and insn.arg.name == "SPIN_DIRECTIONS":
            stored = True
            break
    if not stored or len(dirs) != 24 or any(d not in _SIX for d in dirs):
        return None, "SpinMapping.SPIN_DIRECTIONS isn't six rows of four directions"
    rows = tuple(tuple(dirs[i:i + 4]) for i in range(0, 24, 4))
    return rows, ""


def _full_rule(classes) -> tuple[tuple | None, str, str]:
    """(placed cells, rule text, source) for FacingWithSpinStrategy, or
    (None, "", why it isn't read)."""
    cf = classes.get(_FULL)
    method = cf.method("getStateForPlacement") if cf is not None else None
    if method is None or method.code is None:
        return None, "", f"{_FULL} has no getStateForPlacement"
    shape = _shape(cf, method)
    if len(shape) != len(_FULL_PLACEMENT) or any(
            g[0] != w[0] or (w[0] != "ldc" and g != w) for w, g in zip(_FULL_PLACEMENT, shape)):
        return None, "", "FacingWithSpinStrategy#getStateForPlacement isn't the form read here"
    pitches = [arg for name, arg in shape if name == "ldc"]
    if len(pitches) != 2 or not all(isinstance(p, float) for p in pitches) or pitches[0] <= 0 or pitches[1] >= 0:
        return None, "", "FacingWithSpinStrategy#getStateForPlacement's pitch limits aren't read"
    rows, why = _spin_rows(classes)
    if rows is None:
        return None, "", why
    spin_row = dict(zip(_SIX, rows))
    placed = []
    # Looking level: facing = the player's horizontal facing turned round,
    # up = UP (Bedrock: facing_direction is that horizontal).
    for look in _CARDINALS:
        facing = _OPPOSITE[look]
        if "up" not in spin_row[facing]:
            return None, "", f"SpinMapping has no UP in the {facing} row"
        placed.append(((("minecraft:facing_direction", look),),
                       (("facing", facing), ("spin", str(spin_row[facing].index("up"))))))
    # Looking down (pitch > limit): facing UP, up = the horizontal facing;
    # looking up (pitch < -limit): facing DOWN, likewise.
    for look, facing in (("down", "up"), ("up", "down")):
        for h in _CARDINALS:
            if h not in spin_row[facing]:
                return None, "", f"SpinMapping has no {h} in the {facing} row"
            placed.append(((("minecraft:facing_direction", look), ("minecraft:cardinal_direction", h)),
                           (("facing", facing), ("spin", str(spin_row[facing].index(h))))))
    down, up = pitches[0], pitches[1]
    text = (f"facing = the player's horizontal facing turned round, spin {spin_row['north'].index('up')}; "
            f"pitch above {down:g} (looking down): facing up, spin from the player's horizontal facing; "
            f"pitch below {up:g} (looking up): facing down, likewise")
    return tuple(placed), text, _SOURCE.format(down=f"{down:g}", up=f"{up:g}")


def _placement(classes, cls: str) -> tuple[tuple, str]:
    """(states placement sets besides facing and spin, why not read)."""
    cf, method = _declaring(classes, cls, "getStateForPlacement", _PLACEMENT_DESC)
    if cf is None:
        return (), "getStateForPlacement isn't found"
    if cf.name == _BASE:
        want = (("invokevirtual", "AEBaseBlock.defaultBlockState"),
                ("invokevirtual", "AEBaseBlock.getOrientationStrategy"),
                ("invokeinterface", "IOrientationStrategy.getStateForPlacement"), ("areturn", None))
        if _shape(cf, method) != want:
            return (), "AEBaseBlock#getStateForPlacement isn't the form read here"
        return (), ""
    # An override that adds waterlogged from the clicked position's fluid to
    # super's (InscriberBlock L88-94); any other override isn't read.
    shape = _shape(cf, method)
    supers = [a for n, a in shape if n == "invokespecial"]
    fields = [a for n, a in shape if n == "getstatic" and a.endswith(".WATERLOGGED")]
    sets = [a for n, a in shape if n == "invokevirtual" and a.endswith(".setValue")]
    if supers != [f"{cf.super_name.rsplit('/', 1)[-1]}.getStateForPlacement"] or len(fields) != 1 or len(sets) != 1:
        return (), f"{cf.name.replace('/', '.')}#getStateForPlacement isn't read"
    parent = _placement(classes, cf.super_name)
    if parent[1]:
        return (), parent[1]
    return ("waterlogged",), ""


def _uses_full(classes, cls: str) -> bool:
    cf, method = _declaring(classes, cls, "getOrientationStrategy", _STRATEGY_DESC)
    if cf is None:
        return False
    if _shape(cf, method) != (("invokestatic", "OrientationStrategies.full"), ("areturn", None)):
        return False
    holder = classes.get(_STRATEGIES)
    full = holder.method("full", _STRATEGY_DESC) if holder is not None else None
    init = holder.method("<clinit>", "()V") if holder is not None else None
    if full is None or init is None or _shape(holder, full) != (("getstatic", "OrientationStrategies.full"),
                                                                ("areturn", None)):
        return False
    made = _shape(holder, init)
    return ("invokespecial", "FacingWithSpinStrategy.<init>") in made and \
        made[made.index(("invokespecial", "FacingWithSpinStrategy.<init>")) + 1] == \
        ("putstatic", "OrientationStrategies.full")


def orientations(mod, classes_by_name) -> dict[str, Orientation]:
    """{blockstate name: Orientation} for the names of ``classes_by_name``
    (blockstate name -> its block class, dotted) whose class AE2's
    FacingWithSpinStrategy places."""
    classes = getattr(mod, "classes", None)
    if getattr(mod, "namespace", "") != NAMESPACE or classes is None or classes.get(_FULL) is None:
        return {}
    rule = None
    out = {}
    for name, dotted in classes_by_name.items():
        cls = (dotted or "").replace(".", "/")
        if not cls or not _uses_full(classes, cls):
            continue
        if rule is None:
            rule = _full_rule(classes)
        placed, text, source = rule
        also, why = _placement(classes, cls)
        if placed is None:
            why, source = source, ""
        out[name] = Orientation(
            states=("facing", "spin"), turns={"ae2:z": "z"}, placed=placed or (), sets=also,
            text=text, source=source,
            default=("Bedrock's minecraft:facing_direction (the player's facing over six values) stands in "
                     "for AE2's pitch limits; its own up/down cut isn't documented"),
            turned_by="AE2's wrench (the other spins and facings)", why=why)
    return out


ADAPTER = Adapter(name="ae2", namespaces=frozenset({NAMESPACE}), orientations=orientations)
