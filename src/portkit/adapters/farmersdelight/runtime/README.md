# Farmer's Delight runtimes (adapter)

Fixed Script API runtimes of the Farmer's Delight adapter (#177, moved here in #245).
They ship at `scripts/portkit/` beside the core runtime (pick 6a), so their
`./station_core.js` and `./station_storage.js` imports are the core kit files
(`src/portkit/runtime/`).

- `cutting_board_core.js`: Farmer's Delight cutting board logic; imports only
  `station_core.js` (tested with node, `tests/js/`).
- `cutting_board.js`: its Bedrock binding (custom component registration,
  storage, sounds, item spawning).
- `cooking_pot_core.js`: Farmer's Delight cooking pot logic (recipe matching,
  the cook timer, meal/container/output slots, experience); imports only
  `station_core.js`.
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
  loop; the hit sound). It reads the heat rule from `station_core.js`.
- `feast_core.js`: Farmer's Delight feast logic (what a use does at a
  serving count: serve, ask for the container, clear the leftovers; the
  medley's serving by count), no imports; the clearing command is
  `station_core.js`'s.
- `feast.js`: its Bedrock binding (one component for every feast block,
  `onPlayerInteract`; the serving count is the block's integer state, so
  nothing is stored; clearing runs `setblock ... destroy`, which drops through
  the block's `minecraft:loot`).
