// portkit station runtime: Farmer's Delight cutting board, Bedrock binding (#177).
//
// Fixed file, copied verbatim into every pack that ships the cutting board
// (portkit/runtime/; see docs/decisions.md, 2026-10-13). The generated entry
// scripts/portkit/main.js calls registerCuttingBoard(table) with the mod's
// data table. Script API: @minecraft/server 2.0.0 (Bedrock 1.21.90), custom
// components v2 (learn.microsoft.com, "Introducing Custom Components";
// BlockCustomComponent onPlayerInteract / onPlayerBreak / onPlace).
//
// What a player does, as Farmer's Delight's CuttingBoardBlock#useItemOn
// (NeoForge dd8b9b0b L65-101; Refabricated a8cb49ed L67-106) has it:
//   * empty hand on a loaded board: take the stored stack back;
//   * an item the board can take (empty board, or more of the stored item):
//     put the held stack on it;
//   * anything else: cut one stored item with the held tool, if a recipe
//     takes that item with that tool.
//
// Custom blocks have no inventory, so the stored stack lives in a world
// dynamic property per board position: its id, count, name, lore, durability
// damage and enchantments. Other item data is not kept while it sits on the
// board.

import { BlockTypes, EnchantmentTypes, EquipmentSlot, GameMode, ItemStack, system, world } from "@minecraft/server";
import {
  amountToAdd,
  findRecipe,
  processingSound,
  rollResults,
  spawnOffset,
  storageKey,
  takesDamage,
} from "./cutting_board_core.js";

function keyOf(table, block) {
  return storageKey(table.component, block.dimension.id, block.location);
}

function load(table, block) {
  const raw = world.getDynamicProperty(keyOf(table, block));
  if (typeof raw !== "string") return undefined;
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function save(table, block, stored) {
  world.setDynamicProperty(keyOf(table, block), stored && stored.amount > 0 ? JSON.stringify(stored) : undefined);
}

function describe(stack, amount) {
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

function rebuild(stored, amount) {
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

function enchantLevel(stack, id) {
  const enchantable = stack.getComponent("minecraft:enchantable");
  const found = enchantable ? enchantable.getEnchantment(id) : undefined;
  return found ? found.level : 0;
}

function play(dimension, location, sound) {
  if (!sound || !sound.id) return;
  dimension.playSound(sound.id, location, { volume: sound.volume, pitch: sound.pitch });
}

function centre(block, dy = 0.5) {
  return { x: block.location.x + 0.5, y: block.location.y + dy, z: block.location.z + 0.5 };
}

function say(table, player, role, count) {
  const key = table.messages[role];
  if (!key) return;
  const text = count === undefined ? { translate: key } : { translate: key, with: [String(count)] };
  player.onScreenDisplay.setActionBar({ rawtext: [text] });
}

/**
 * Give a stack to the player; what doesn't fit drops at their feet. (Java's
 * Inventory#add leaves what doesn't fit in the removed stack, which nothing
 * keeps, so it is lost there; dropping it here is a deliberate difference.)
 */
function give(player, stack) {
  const container = player.getComponent("minecraft:inventory").container;
  const left = container.addItem(stack);
  if (left) player.dimension.spawnItem(left, player.location);
}

function spawnStacks(dimension, item, count, at, velocity) {
  let left = count;
  while (left > 0) {
    const stack = new ItemStack(item, 1);
    const size = Math.min(left, stack.maxAmount);
    stack.amount = size;
    left -= size;
    const entity = dimension.spawnItem(stack, at);
    entity.clearVelocity();
    entity.applyImpulse(velocity);
  }
}

/** One tool use: Unbreaking, then damage or break (ItemStack#hurtAndBreak). */
function damageTool(table, player, equippable, tool) {
  const durability = tool.getComponent("minecraft:durability");
  if (!durability || !takesDamage(enchantLevel(tool, "unbreaking"), Math.random)) return;
  if (durability.damage + 1 > durability.maxDurability) {
    equippable.setEquipment(EquipmentSlot.Mainhand, undefined);
    play(player.dimension, player.location, table.sounds.break);
    return;
  }
  durability.damage += 1;
  equippable.setEquipment(EquipmentSlot.Mainhand, tool);
}

function interact(table, event) {
  const { block, dimension, player } = event;
  if (!player) return;
  const equippable = player.getComponent("minecraft:equippable");
  const held = equippable.getEquipment(EquipmentSlot.Mainhand);
  // Java: player.isCreative() keeps the held stack and skips tool damage.
  const creative = player.getGameMode() === GameMode.Creative;
  const stored = load(table, block);

  if (!held) {
    // Block L72-82: take the stored stack back.
    if (!stored) return;
    save(table, block, undefined);
    if (!creative) give(player, rebuild(stored, stored.amount));
    play(dimension, centre(block), table.sounds.remove);
    return;
  }

  const same = stored ? held.isStackableWith(rebuild(stored, 1)) : false;
  const moved = amountToAdd(stored, held.amount, held.maxAmount, same);
  if (moved > 0) {
    // Block L84-94: put the held stack on the board.
    save(table, block, stored ? { ...stored, amount: stored.amount + moved } : describe(held, moved));
    if (!creative) {
      if (held.amount > moved) {
        held.amount -= moved;
        equippable.setEquipment(EquipmentSlot.Mainhand, held);
      } else {
        equippable.setEquipment(EquipmentSlot.Mainhand, undefined);
      }
    }
    play(dimension, centre(block), table.sounds.place);
    return;
  }
  if (!stored) return;

  // BE#processStoredItemUsingTool (L92-130): cut one stored item.
  const recipe = findRecipe(table.recipes, stored.id, held.typeId, (tag) => held.hasTag(tag));
  if (!recipe) {
    say(table, player, "no_recipe");
    return;
  }
  const results = rollResults(recipe, enchantLevel(held, "fortune"), table.fortune_bonus, Math.random);
  const facing = block.permutation.getState("minecraft:cardinal_direction");
  const offset = spawnOffset(typeof facing === "string" ? facing : "north");
  const at = { x: block.location.x + 0.5 + offset.dx, y: block.location.y + offset.dy, z: block.location.z + 0.5 + offset.dz };
  for (const result of results) {
    spawnStacks(dimension, result.item, result.count, at, { x: offset.vx, y: offset.vy, z: offset.vz });
  }
  if (!creative) damageTool(table, player, equippable, held);
  play(dimension, centre(block), processingSound(table, recipe, held.typeId, BlockTypes.get(stored.id) !== undefined));
  const left = stored.amount - 1;
  save(table, block, left > 0 ? { ...stored, amount: left } : undefined);
  if (left > 0) say(table, player, "remaining", left);
  else player.onScreenDisplay.setActionBar("");
}

function broken(table, event) {
  // Block#onRemove (L104-115): the stored stack drops where the board was.
  const stored = load(table, event.block);
  save(table, event.block, undefined);
  if (stored) event.dimension.spawnItem(rebuild(stored, stored.amount), centre(event.block));
}

/** Register the cutting board's custom component for one mod's data table. */
export function registerCuttingBoard(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      onPlayerInteract: (event) => interact(table, event),
      onPlayerBreak: (event) => broken(table, event),
      // A board placed where one was destroyed without a player (explosion,
      // piston) must not inherit that board's stored stack.
      onPlace: (event) => save(table, event.block, undefined),
    });
  });
}
