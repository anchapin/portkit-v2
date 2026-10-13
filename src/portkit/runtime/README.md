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
- `station_storage.js`: helpers the bindings share (world dynamic property
  storage, stored stacks, giving and dropping items, sounds).

Every behaviour is cited to the mod's source in the comments. Change these
files only with the source open; see docs/decisions.md (2026-10-13).
