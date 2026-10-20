# Station runtimes

Hand-written Bedrock Script API (`@minecraft/server` 2.0.0) scripts, one per
station kind, copied verbatim into converted behavior packs under
`scripts/portkit/`. They are not generated: the converter writes only the data
table each one reads (`scripts/portkit/data/<namespace>_<station>.js`) and the
entry `scripts/portkit/main.js` that wires the two.

- `cutting_board*.js`, `cooking_pot*.js`, `stove*.js`, `skillet*.js`, `feast*.js`:
  moved to the Farmer's Delight adapter (#245, `portkit/adapters/farmersdelight/runtime/`,
  described in its README); they still ship here, in `scripts/portkit/`.
- `waystone_core.js`, `waystone.js`: moved to the Waystones adapter (#245,
  `portkit/adapters/waystones/runtime/`, described in its README); they still
  ship here, in `scripts/portkit/`, beside the kit files they import.
- `toggle.js`: not a station: the use toggle of a block with facing and
  boolean states (`onPlayerInteract` flips the one boolean state the table
  names per block). A block is in the table only when its Java
  `useWithoutItem` was read from bytecode to flip that boolean on every way
  through it (`portkit.blockcode.read_state_blocks`); the converter writes the
  table (`scripts/portkit/data/<namespace>_toggle.js`).
- `door_core.js`: not a station: the pure rules of a door (#296), no
  imports (tested with node, `tests/js/door_core.test.mjs`): vanilla
  `DoorBlock#getHinge` (neighbouring doors, then blocks, then where the player
  clicked), a use (only when the door's `BlockSetType` opens by hand) and a
  change of redstone power (`neighborChanged`: open = powered, the sound when
  open changes).
- `door.js`: its Bedrock binding (`@minecraft/server` 2.5.0, the first stable
  version with `BlockCustomComponent.onRedstoneUpdate`; the first line
  `// portkit-requires: @minecraft/server 2.5.0` makes the pack declare it,
  `pack.script_version`). One custom component per namespace:
  `beforeOnPlayerPlace` picks the hinge, `onPlayerInteract` opens and closes,
  `onRedstoneUpdate` (the block's `minecraft:redstone_consumer`, min_power 0)
  follows the power, `onPlace` opens a door placed already powered. The block
  is on `minecraft:multi_block`, whose parts must keep equal states, so every
  change is written to both parts. The converter writes the table
  (`scripts/portkit/data/<namespace>_doors.js`: per door whether a hand opens
  it and its sounds) only for doors whose code was read as vanilla
  `DoorBlock`, or the labelled DEFAULT wooden door (`converters/doors.py`).
- `trapdoor.js`: the Bedrock binding of a trapdoor (#296), on the door's
  rules in `door_core.js` (vanilla `TrapDoorBlock#useWithoutItem` and
  `#neighborChanged` are `DoorBlock`'s for one block); `@minecraft/server`
  2.5.0 like `door.js`. `onPlayerInteract` opens and closes when its
  `BlockSetType` lets a hand, `onRedstoneUpdate` follows the power, `onPlace`
  opens a trapdoor placed already powered. Placement is the block's own traits
  (`vertical_half`, `cardinal_direction`), so there is no
  `beforeOnPlayerPlace`. The converter writes the table
  (`scripts/portkit/data/<namespace>_trapdoors.js`) only for trapdoors read as
  vanilla `TrapDoorBlock`, or the labelled DEFAULT wooden trapdoor
  (`converters/trapdoors.py`).
- `pressure_plate_core.js`: the pure rules of a pressure plate (#296), from
  vanilla `BasePressurePlateBlock` / `PressurePlateBlock` (1.21.1): the touch
  box, what presses it (everything, or mobs and players only; never a
  spectator) and `checkPressed`'s timing (press at once, re-check every
  `getPressedTime()` = 20 ticks, release at the first empty re-check); no
  imports.
- `pressure_plate.js`: its Bedrock binding, `@minecraft/server` 2.0.0. A
  plate has no collision, and Bedrock's step events need a collision box
  taller than 3.2 pixels, so the block's `minecraft:tick` sends `onTick`
  every few ticks (DEFAULT) and the plate reads `Dimension.getEntities` in its
  touch box. The redstone output is the block's own
  `minecraft:redstone_producer` on the powered permutation. The converter
  writes the table (`scripts/portkit/data/<namespace>_pressure_plates.js`)
  only for plates read as vanilla `PressurePlateBlock`, or the labelled
  DEFAULT wooden plate (`converters/plates.py`).
- `button_core.js`: the pure rules of a button (#280), from vanilla
  `ButtonBlock` (1.21.1, checked against 1.20.1): a use presses an unpowered
  button and schedules its release `ticksToStayPressed` later; the release
  (`checkPressed`) keeps it pressed while an arrow is in it where its set type
  lets arrows press it; an arrow presses an unpowered one; no imports.
- `button.js`: its Bedrock binding, `@minecraft/server` 2.0.0: the custom
  component's `onPlayerInteract`, `world.afterEvents.projectileHitBlock`
  (arrows, tridents) and `/scriptevent portkit:button_press <x> <y> <z>`
  press; `system.runTimeout` releases; the block's `minecraft:tick` releases
  a powered button whose timer a reload dropped. The redstone output is the
  block's own `minecraft:redstone_producer` on the powered permutations. The
  converter writes the table (`scripts/portkit/data/<namespace>_buttons.js`)
  only for buttons read as vanilla `ButtonBlock` with a press time and set
  type read from code (`converters/buttons.py`); there is no DEFAULT.
- `book_core.js`: not a station: what one page of a guide book shows (#182):
  title, text and the page's buttons as translation keys, back to its parent;
  no imports.
- `book.js`: its Bedrock binding (`world.afterEvents.itemUse` opens the book a
  used item names at its root page; each page is a `@minecraft/server-ui`
  `ActionFormData`, shown through `forms.js`). The converter writes the page table
  (`scripts/portkit/data/<namespace>_books.js`) from a Citadel book's page
  JSON, and the page text into the resource pack's `texts/*.lang`
  (`portkit.adapters.citadel.books`, the Citadel library adapter).

The station kit (#245): namespace-free files any station runtime builds on.
They name no mod; `portkit.converters.station_kit` ships them
(`KIT_FILES` beside every station runtime, `FORMS` with a runtime that shows
forms), and the conversion fails if a shipped script imports a file the pack
does not ship (`station_kit.unresolved_imports`).

- `station_core.js`: pure helpers, no imports (tested with node,
  `tests/js/station_core.test.mjs`): the storage key and its prefix, the
  counter-clockwise side step, the heat rule (heat sources, conductors, tray),
  the `setblock ... destroy` command and `HoldTimer`, the held-item use timer
  (Waystones' scrolls and warp stone).
- `station_storage.js`: Bedrock-side helpers the bindings share (world dynamic
  property storage and listing a station's records, stored stacks, giving and
  dropping items, sounds, enchantment levels, the block view the heat rule
  reads, the block below, a block's facing, the stack in an inventory slot).
- `forms.js`: shows a `@minecraft/server-ui` form, shown again next tick
  (up to 20 times) when cancelled because the player is busy.

Every behaviour is cited to the mod's source in the comments. Change these
files only with the source open; see docs/decisions.md (2026-10-13).
