// portkit station runtimes: shared Bedrock helpers (#177).
//
// Fixed file, copied verbatim into every pack that ships a station runtime
// (portkit/runtime/; see docs/decisions.md, 2026-10-13). Custom blocks have no
// inventory, so each station keeps what it holds in a world dynamic property
// per block position, as JSON. A stored stack keeps its id, count, name, lore,
// durability damage and enchantments; other item data is not kept.
//
// Part of the namespace-free station kit (#245) with station_core.js (pure
// helpers) and forms.js. The block view, facing, enchantment, held-item and
// record-listing helpers were copies in the mods' runtimes before #245.

import { EnchantmentTypes, ItemStack, world } from "@minecraft/server";

/** The JSON value stored under `key`, or undefined. */
export function loadStored(key) {
  const raw = world.getDynamicProperty(key);
  if (typeof raw !== "string") return undefined;
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

/** Every stored JSON value whose key starts with `prefix` (a station's records), in getDynamicPropertyIds order. */
export function loadAll(prefix) {
  return world.getDynamicPropertyIds()
    .filter((key) => key.startsWith(prefix))
    .map((key) => loadStored(key));
}

/** Store `value` under `key` as JSON; undefined clears it. */
export function saveStored(key, value) {
  world.setDynamicProperty(key, value === undefined ? undefined : JSON.stringify(value));
}

/** A held stack as stored data: `amount` of it. */
export function describe(stack, amount) {
  const stored = { id: stack.typeId, amount };
  if (stack.nameTag) stored.nameTag = stack.nameTag;
  const lore = stack.getLore();
  if (lore.length > 0) stored.lore = lore;
  const durability = stack.getComponent("minecraft:durability");
  if (durability && durability.damage > 0) stored.damage = durability.damage;
  const enchantable = stack.getComponent("minecraft:enchantable");
  const enchantments = enchantable ? enchantable.getEnchantments() : [];
  if (enchantments.length > 0) stored.enchantments = enchantments.map((e) => ({ id: e.type.id, level: e.level }));
  return stored;
}

/** Stored data back as an ItemStack of `amount`. */
export function rebuild(stored, amount) {
  const stack = new ItemStack(stored.id, amount);
  if (stored.nameTag) stack.nameTag = stored.nameTag;
  if (stored.lore) stack.setLore(stored.lore);
  if (stored.damage) {
    const durability = stack.getComponent("minecraft:durability");
    if (durability) durability.damage = stored.damage;
  }
  if (stored.enchantments) {
    const enchantable = stack.getComponent("minecraft:enchantable");
    for (const e of stored.enchantments) {
      const type = EnchantmentTypes.get(e.id);
      if (enchantable && type) enchantable.addEnchantment({ type, level: e.level });
    }
  }
  return stack;
}

/** Most of `id` one stack holds on Bedrock. */
export function maxAmountOf(id) {
  return new ItemStack(id, 1).maxAmount;
}

export function play(dimension, location, sound, pitch) {
  if (!sound || !sound.id) return;
  dimension.playSound(sound.id, location, { volume: sound.volume, pitch: pitch ?? sound.pitch });
}

export function centre(block, dy = 0.5) {
  return { x: block.location.x + 0.5, y: block.location.y + dy, z: block.location.z + 0.5 };
}

/**
 * Give a stack to the player; what doesn't fit drops at their feet. (Java's
 * Inventory#add leaves what doesn't fit in the removed stack, which nothing
 * keeps, so it is lost there; dropping it here is a deliberate difference.)
 */
export function give(player, stack) {
  const container = player.getComponent("minecraft:inventory").container;
  const left = container.addItem(stack);
  if (left) player.dimension.spawnItem(left, player.location);
}

/** Drop `amount` of a stored stack at `at`, split into stacks Bedrock allows. */
export function dropStored(dimension, stored, amount, at) {
  let left = amount;
  const max = maxAmountOf(stored.id);
  while (left > 0) {
    const size = Math.min(left, max);
    dimension.spawnItem(rebuild(stored, size), at);
    left -= size;
  }
}

/** The level of enchantment `id` on a stack, 0 without it. */
export function enchantLevel(stack, id) {
  const enchantable = stack.getComponent("minecraft:enchantable");
  const found = enchantable ? enchantable.getEnchantment(id) : undefined;
  return found ? found.level : 0;
}

/** A block as table rules read it (the heat rule): { id, state(name) }, or undefined. */
export function blockView(block) {
  if (!block) return undefined;
  const permutation = block.permutation;
  return { id: block.typeId, state: (name) => permutation.getState(name) };
}

/** The block `steps` below, or undefined outside the world or in an unloaded chunk. */
export function blockBelow(block, steps) {
  try {
    return block.below(steps);
  } catch {
    return undefined; // outside the world or an unloaded chunk
  }
}

/** A block's minecraft:cardinal_direction, north when it has none. */
export function facingOf(block) {
  const facing = block.permutation.getState("minecraft:cardinal_direction");
  return typeof facing === "string" ? facing : "north";
}

/** The stack in a player's inventory slot, or undefined. */
export function heldAt(player, slot) {
  const inventory = player.getComponent("minecraft:inventory");
  try {
    return inventory && inventory.container ? inventory.container.getItem(slot) : undefined;
  } catch {
    return undefined;
  }
}
