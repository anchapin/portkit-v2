// portkit station runtime: Farmer's Delight feasts, the logic (#177).
//
// Fixed file, copied verbatim into every pack that ships a feast
// (portkit/runtime/; see docs/decisions.md). No imports, so node tests it
// (tests/js/feast.test.mjs). The Bedrock binding is feast.js.
//
// FeastBlock#takeServing (NeoForge dd8b9b0b L103-138, Refabricated a8cb49ed
// L110-144):
// - at 0 servings the block is cleared (WOOD_BREAK 0.8 / 0.8, then
//   destroyBlock with drops);
// - otherwise the serving item is getServingItem(state): one item for most
//   feasts, by serving count for the rice roll medley (servings - 1 indexes
//   RiceRollMedleyBlock.riceRollServings);
// - it is served when it has no crafting remainder, or the held stack is that
//   remainder (ItemStack.isSameItem: the same item); the remainder is used up
//   unless the player is in creative (instabuild); servings drop by one, and a
//   feast without leftovers is destroyed when that reaches 0;
// - otherwise the player is told which container it needs
//   ("block.<ns>.feast.use_container" with the remainder's name).

/** The item a feast serves at `servings` (1 or more). */
export function servingAt(feast, servings) {
  return feast.servings[servings - 1];
}

/**
 * What using a feast with `heldId` in hand does at `servings`:
 * { action: "clear" } at 0;
 * { action: "serve", item, consume, next, vanish } when it serves;
 * { action: "need_container", container } when the hand holds the wrong item.
 */
export function interaction(feast, servings, heldId, creative = false) {
  if (!Number.isInteger(servings) || servings < 0 || servings > feast.max_servings) return { action: "none" };
  if (servings === 0) return { action: "clear" };
  const item = servingAt(feast, servings);
  const container = feast.container;
  if (container && heldId !== container) return { action: "need_container", container };
  const next = servings - 1;
  return {
    action: "serve",
    item,
    consume: Boolean(container) && !creative,
    next,
    vanish: next === 0 && !feast.leftovers,
  };
}

/** The action-bar message for a missing container, as Bedrock rawtext. */
export function containerMessage(key, feast) {
  const name = feast.container_name ? { rawtext: [{ translate: feast.container_name }] } : [feast.container];
  return { rawtext: [{ translate: key, with: name }] };
}

/** The command that clears a block as destroyBlock(pos, true) does: drops by its loot table. */
export function destroyCommand(location) {
  return `setblock ${location.x} ${location.y} ${location.z} air destroy`;
}
