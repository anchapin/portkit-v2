# Station runtimes

Hand-written Bedrock Script API (`@minecraft/server` 2.0.0) scripts, one per
station kind, copied verbatim into converted behavior packs under
`scripts/portkit/`. They are not generated: the converter writes only the data
table each one reads (`scripts/portkit/data/<namespace>_<station>.js`) and the
entry `scripts/portkit/main.js` that wires the two.

- `cutting_board_core.js`: Farmer's Delight cutting board logic, no imports
  (tested with node, `tests/js/`).
- `cutting_board.js`: its Bedrock binding (custom component registration,
  storage, sounds, item spawning).
- `cooking_pot_core.js`: Farmer's Delight cooking pot logic (recipe matching,
  the cook timer, meal/container/output slots, heat rule, experience), no
  imports.
- `cooking_pot.js`: its Bedrock binding (interaction by hand, `onTick`,
  placement support state, breaking).
- `stove_core.js`: Farmer's Delight stove logic (six spots, campfire recipe
  lookup, cooking while lit and cooling while not, what using an item does,
  the burn test), no imports.
- `stove.js`: its Bedrock binding (lighting and putting out, placing food,
  `onTick` cooking, burning and the crackle, the covered-top drop, breaking).
- `skillet_core.js`: Farmer's Delight skillet logic (the skillet cook time
  with Fire Aspect, one stack cooking item by item, cooling off heat, the
  thrown result, held cooking sessions, the near-heat test), no imports.
- `skillet.js`: its Bedrock binding (the placed skillet's use, `onTick`, tray
  state, sneak-only placement, breaking; held cooking with the skillet in the
  off-hand through `world.beforeEvents.itemUse` and a `system.runInterval`
  loop; the hit sound). It imports the heat helpers of `cooking_pot_core.js`.
- `feast_core.js`: Farmer's Delight feast logic (what a use does at a
  serving count: serve, ask for the container, clear the leftovers; the
  medley's serving by count; the clearing command), no imports.
- `feast.js`: its Bedrock binding (one component for every feast block,
  `onPlayerInteract`; the serving count is the block's integer state, so
  nothing is stored; clearing runs `setblock ... destroy`, which drops through
  the block's `minecraft:loot`).
- `waystone_core.js`: Waystones waystone, sharestone and portstone logic (the experience
  cost from the table's warp requirement modifiers, affording, the teleport
  side and destination, names, the edit rule, the menu's entries: activated
  waystones, or every sharestone of one colour; storage keys; the warp plate's
  idle status, shard target, attunement step and each entity's on-plate count
  and cooldown; the warp portal's facing, the place a portal scroll opens it
  and each entity's portal cooldown; where a fleeting memorial goes and which
  memorials a player's menus list), no imports.
- `waystone.js`: its Bedrock binding (placement of both halves through
  `beforeOnPlayerPlace` and `world.afterEvents.playerPlaceBlock`, activation
  and the menu through `onPlayerInteract`, breaking through `onPlayerBreak`;
  the menu and the rename form are `@minecraft/server-ui` forms, so a pack
  shipping it also declares that module; waystones, sharestones and each
  player's activated list are dynamic properties; the table maps each block to
  its network: a waystone's activation list or a sharestone colour's shared
  list; a portstone stores nothing and opens the menu of the network it
  targets, with no waystone in use; a warp plate has its own component,
  `onTick` every tick through `minecraft:tick` to attune its shard and warp
  what stands on it, `onPlayerInteract` for shards in and out, `onPlayerBreak`
  to drop its shard; an attuned shard keeps its plate as an item dynamic
  property, and each entity's warp plate state lives in memory, unsaved, as in
  Java; a warp portal has its own component, `onTick` every tick through
  `minecraft:tick` to send what stands in it to its waystone and close it
  after its lifetime, opened by a portal scroll held for its use time
  (`world.afterEvents.itemUse` and a `system.runInterval` timer, stopped by
  switching away or `world.afterEvents.entityHurt`); a player who went through
  keeps the portal as a player dynamic property for the "Return to Portal"
  entry of waystone and sharestone menus; a player who dies with an epitaph
  (`world.afterEvents.entityDie`) leaves a fleeting memorial, listed at the top
  of their menus until a teleport reaches it).
- `toggle.js`: not a station: the use toggle of a block with facing and
  boolean states (`onPlayerInteract` flips the one boolean state the table
  names per block). A block is in the table only when its Java
  `useWithoutItem` was read from bytecode to flip that boolean on every way
  through it (`portkit.blockcode.read_state_blocks`); the converter writes the
  table (`scripts/portkit/data/<namespace>_toggle.js`).
- `book_core.js`: not a station: what one page of a guide book shows (#182):
  title, text and the page's buttons as translation keys, back to its parent;
  no imports.
- `book.js`: its Bedrock binding (`world.afterEvents.itemUse` opens the book a
  used item names at its root page; each page is a `@minecraft/server-ui`
  `ActionFormData`). The converter writes the page table
  (`scripts/portkit/data/<namespace>_books.js`) from a Citadel book's page
  JSON, and the page text into the resource pack's `texts/*.lang`
  (`portkit.converters.books`).
- `station_storage.js`: helpers the bindings share (world dynamic property
  storage, stored stacks, giving and dropping items, sounds).

Every behaviour is cited to the mod's source in the comments. Change these
files only with the source open; see docs/decisions.md (2026-10-13).
