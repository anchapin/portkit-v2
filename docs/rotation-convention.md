# Which way a Java element rotation leans

A Java block model element may carry a rotation: an angle, an axis, and an
origin. To port one we need to know which way that angle actually tips the box,
and no specification says. Guess it and you get a model that loads, renders,
and leans the wrong way, which is the failure this project exists to refuse.

It can be settled without a Java install, by reading a vanilla model whose
in-game appearance everybody already knows.

## The anchor: a wall torch

`assets/minecraft/models/block/template_torch_wall.json` (1.20.4) rotates every
element by **-22.5 degrees about z**, about the origin `[0, 3.5, 8]`. The torch
box sits at `x = -1 .. 1`, centred on `x = 0`, which is the block's west edge.

`blockstates/wall_torch.json` maps `facing=east` to that model with no extra
rotation. A torch must lean *away* from the wall holding it, and this one hangs
on the west edge, so in game its top leans **east**.

That is the whole derivation. Under the right-hand rule, with Java's axes
(x east, y up, z south), a rotation about z maps a point `(x, y)` to
`(x cos t - y sin t, x sin t + y cos t)`. The torch top sits 16 above the
origin, so at `t = -22.5` it moves to `x = -16 sin(-22.5) = +6.1`: east, exactly
what the game shows.

So Java element rotation is the plain right-hand rule about the named axis. A
positive angle tips a thing the opposite way from that torch.

Source files, as mirrored by InventivetalentDev/minecraft-assets at 1.20.4:

- `assets/minecraft/models/block/template_torch_wall.json`
- `assets/minecraft/blockstates/wall_torch.json`

## What that predicts for the rotation probe

`portkit probe --kind rotation` builds one bar per axis, turned +22.5 about the
block centre. Under the rule above, Java renders them like this, and these are
the strings baked into the probe's block names so the answer is readable in the
inventory:

| Axis | Bar runs | Java shows |
| --- | --- | --- |
| x | north-south | north end up, south end dipped |
| y | east-west | east end swings toward north, seen from above |
| z | east-west | east end up, west end dipped |

## What is anchored and what is inferred

The z case is anchored on the torch: a real vanilla model with a known
appearance. The x and y cases carry the same rule across, which is consistency
rather than a second observation. A vanilla lever (`models/block/lever.json`)
does rotate -45 about x, so the axis is at least exercised in vanilla, but its
in-game lean is not common knowledge the way the torch's is, so it is not
treated as a second anchor here.

If the probe disagrees with a row of that table in game, the game is right and
this document is wrong. Say so in the issue and re-derive.

## The pivot

The rotation probe turned every bar about the block centre, where any sensible
pivot mapping is the identity, so it settled the sign and nothing else. Issue
#52 named two candidates for an origin anywhere else:

- A, mirrored: `pivot = [8 - ox, oy, oz - 8]`, the same mirror the cube origin gets.
- B, as written: `pivot = [ox - 8, oy, oz - 8]`.

The pivot probe (`portkit probe --kind pivot`, model `tests/data/pivot_z.json`)
turns one 4x4x4 cube +45 about z around `[0, 8, 8]`, which Java renders high up
and just west of centre. Read in game on Bedrock for Android, 2026-10-01: **A,
pivot mirrored**. Recorded as `models.PIVOT_IS_MIRRORED = True`.

That was the hoped-for answer (pivot and cube living in one space) but it is now
an observation, not a hope.

## Face names

Mirroring the box in X raised one more question (#64): does a face Java calls
west need to be called east in Bedrock? The face probe (`portkit probe --kind
face`) built a 2-pixel slab on one edge, drawn on one face only, with the uv
entry keyed both ways. Read in game on Bedrock for Android, 2026-10-01: **B,
face as written**. Recorded as `models.FACE_NAMES_FOLLOW_MIRROR = False`.

The probe tested the per-face uv key. Built-in face material instances
(`west`, `east`, ...) bind to those same named faces, so they follow the same
rule; that part is inferred from the binding, not separately observed.

## Blockstate y turns

A multipart part turned by `y` (a palisade side aimed at each neighbour) is
turned in Java coordinates before conversion: each quarter turn sends (x, z) to
(16 - z, x) and north to east. Only uvlocked turns of unrotated elements whose
uvs are Java's position-derived ones are taken, because then the turned element
simply wears the position-derived uvs of where it lands. See
`models.turn_y`.
