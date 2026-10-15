# Waystones runtime (adapter)

Fixed Script API runtime of the Waystones adapter (#178, moved here in #245).
Both files ship at `scripts/portkit/` beside the core runtime (pick 6a), so their
`./station_core.js` and `./forms.js` imports are the core kit files
(`src/portkit/runtime/`).

- `waystone_core.js`: Waystones waystone, sharestone and portstone logic (the experience
  cost from the table's warp requirement modifiers, affording, the teleport
  side and destination, names, the edit rule, the menu's entries: activated
  waystones, or every sharestone of one colour; storage keys; the warp plate's
  idle status, shard target, attunement step and each entity's on-plate count
  and cooldown; the warp portal's facing, the place a portal scroll opens it
  and each entity's portal cooldown; where a fleeting memorial goes and which
  memorials a player's menus list); imports only `station_core.js`.
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
