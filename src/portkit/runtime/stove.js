// portkit station runtime: Farmer's Delight stove, Bedrock binding (#177).
//
// Fixed file, copied verbatim into every pack that ships the stove
// (portkit/runtime/; see docs/decisions.md). The generated entry
// scripts/portkit/main.js calls registerStove(table) with the mod's data
// table. Script API: @minecraft/server 2.0.0 (Bedrock 1.21.90), custom
// components v2 (learn.microsoft.com, "Introducing Custom Components";
// BlockCustomComponent onPlayerInteract / onTick / onPlayerBreak / onPlace /
// beforeOnPlayerPlace). The block carries minecraft:tick at the table's
// tick_interval, so onTick runs while its chunk is ticking.
//
// What a player does, as Farmer's Delight's AbstractStoveBlock#useItemOn
// (NeoForge dd8b9b0b L66-77, Refabricated a8cb49ed L65-76) has it:
//   * lit: a shovel (shovel_dig) or a water bucket puts it out;
//   * unlit: flint and steel or a fire charge lights it;
//   * a food a campfire recipe takes goes onto the first free spot, unless
//     something covers the top or all six spots are taken.
// Java draws the food on top with a block-entity renderer; Bedrock custom
// blocks have none, so every use shows the stove's contents in the action bar.

import { EntityDamageCause, EquipmentSlot, GameMode, ItemStack, system } from "@minecraft/server";
import {
  burns,
  cookedMotion,
  emptyStove,
  findRecipe,
  interaction,
  isEmpty,
  placeFood,
  soundChance,
  status,
  step,
  storageKey,
  takesDamage,
} from "./stove_core.js";
import { centre, describe, dropStored, loadStored, play, rebuild, saveStored } from "./station_storage.js";

function keyOf(table, block) {
  return storageKey(table.component, block.dimension.id, block.location);
}

function load(table, block) {
  return loadStored(keyOf(table, block));
}

function save(table, block, stove) {
  saveStored(keyOf(table, block), stove && !isEmpty(stove) ? stove : undefined);
}

function isLit(table, block) {
  return block.permutation.getState(table.lit_state) === "true";
}

function setLit(table, block, lit) {
  // Block#ignite / #extinguish (L140-160): the LIT state, nothing else.
  const value = lit ? "true" : "false";
  if (block.permutation.getState(table.lit_state) === value) return;
  block.setPermutation(block.permutation.withState(table.lit_state, value));
}

/**
 * Block#isStoveTopCovered (L197-205): Java tests the block above's shape
 * against the grilling area (3..13 px across, the bottom pixel). Scripts can't
 * read a block's shape, so any block above that isn't air or a liquid covers
 * it (liquids have no shape in Java either).
 */
function covered(block) {
  let above;
  try {
    above = block.above(1);
  } catch {
    return false; // top of the world or an unloaded chunk
  }
  if (!above) return false;
  return !(above.isAir || above.isLiquid);
}

function enchantLevel(stack, id) {
  const enchantable = stack.getComponent("minecraft:enchantable");
  const found = enchantable ? enchantable.getEnchantment(id) : undefined;
  return found ? found.level : 0;
}

/** One use of the held tool: Unbreaking, then damage or break (ItemStack#hurtAndBreak). */
function damageHeld(table, player, equippable, held) {
  const durability = held.getComponent("minecraft:durability");
  if (!durability || !takesDamage(enchantLevel(held, "unbreaking"), Math.random)) return;
  if (durability.damage + 1 > durability.maxDurability) {
    equippable.setEquipment(EquipmentSlot.Mainhand, undefined);
    play(player.dimension, player.location, table.sounds.break);
    return;
  }
  durability.damage += 1;
  equippable.setEquipment(EquipmentSlot.Mainhand, held);
}

function shrinkHeld(equippable, held) {
  if (held.amount > 1) {
    held.amount -= 1;
    equippable.setEquipment(EquipmentSlot.Mainhand, held);
  } else {
    equippable.setEquipment(EquipmentSlot.Mainhand, undefined);
  }
}

function show(table, player, block, stove) {
  player.onScreenDisplay.setActionBar(status(stove ?? emptyStove(table.slots), isLit(table, block), covered(block)));
}

function interact(table, event) {
  const { block, dimension, player } = event;
  if (!player) return;
  const equippable = player.getComponent("minecraft:equippable");
  const held = equippable.getEquipment(EquipmentSlot.Mainhand);
  // Java: player.getAbilities().instabuild (creative) keeps the held stack and
  // skips tool damage.
  const creative = player.getGameMode() === GameMode.Creative;
  const lit = isLit(table, block);
  const action = interaction(table, lit, held && held.typeId, (tag) => held.hasTag(tag));
  const at = centre(block);

  if (action === "extinguish_shovel") {
    // tryToExtinguish L106-113: the extinguish sound, unlit, the tool takes 1.
    play(dimension, at, table.sounds.shovel);
    setLit(table, block, false);
    if (!creative) damageHeld(table, player, equippable, held);
  } else if (action === "extinguish_water") {
    // L115-122: the extinguish sound at 1.0/1.0, unlit, the bucket's
    // crafting remainder in the hand (not in creative).
    play(dimension, at, table.sounds.water);
    setLit(table, block, false);
    if (!creative) equippable.setEquipment(EquipmentSlot.Mainhand, new ItemStack(table.extinguish.water[held.typeId], 1));
  } else if (action === "ignite_flint") {
    // tryToIgnite L82-89: flint and steel's sound at pitch 0.8-1.2, lit, 1 damage.
    const sound = table.sounds.flint_and_steel;
    if (sound) play(dimension, at, sound, sound.pitch_min + Math.random() * (sound.pitch_max - sound.pitch_min));
    setLit(table, block, true);
    if (!creative) damageHeld(table, player, equippable, held);
  } else if (action === "ignite_charge") {
    // L91-100: the fire charge's sound at pitch 1 + (r - r) * 0.2, lit, one used up.
    const sound = table.sounds.fire_charge;
    if (sound) play(dimension, at, sound, sound.pitch + (Math.random() - Math.random()) * sound.pitch_spread);
    setLit(table, block, true);
    if (!creative) shrinkHeld(equippable, held);
  } else if (action === "place" && !covered(block)) {
    // tryToPlaceFoodItem L127-138 / BE#placeFood: one item onto the first
    // free spot, the lantern place sound at 0.5/1.0.
    const stove = load(table, block) ?? emptyStove(table.slots);
    if (placeFood(stove, describe(held, 1), findRecipe(table.recipes, held.typeId)) >= 0) {
      if (!creative) shrinkHeld(equippable, held);
      play(dimension, at, table.sounds.place);
      save(table, block, stove);
    }
  }
  show(table, player, block, load(table, block));
}

function burnStanding(table, block, dimension) {
  // Block#stepOn -> burnEntitySteppingOnStove (L174-186): 1 damage of FD's
  // stove_burn type (Bedrock: campfire). Java runs it every tick an entity
  // stands there; a hurt entity ignores more of the same damage for 10 ticks
  // (minecraft.wiki, Damage, invulnerability timer), so one hit per 10-tick
  // run is the rate Java deals.
  const at = block.location;
  let entities = [];
  try {
    entities = dimension.getEntities({ location: { x: at.x + 0.5, y: at.y + 1, z: at.z + 0.5 }, maxDistance: 1.5 });
  } catch {
    return;
  }
  for (const entity of entities) {
    try {
      const view = {
        living: entity.getComponent("minecraft:health") !== undefined && entity.typeId !== "minecraft:item",
        sneaking: !!entity.isSneaking,
        onGround: !!entity.isOnGround,
        feet: entity.location,
      };
      if (burns(true, view, at)) {
        entity.applyDamage(table.burn.amount, { cause: EntityDamageCause[table.burn.cause] });
      }
    } catch {
      // an entity that left or can't take damage
    }
  }
}

function tick(table, event) {
  const { block, dimension } = event;
  const lit = isLit(table, block);
  if (lit) {
    // StoveBlock#animateTick: the crackle, 1 in 10 client ticks, at 1.0/1.0.
    const crackle = table.sounds.crackle;
    if (crackle && Math.random() < soundChance(crackle.chance_per_tick, table.tick_interval)) {
      play(dimension, centre(block, 0), crackle);
    }
    burnStanding(table, block, dimension);
  }
  const stove = load(table, block);
  if (!stove || isEmpty(stove)) return;
  if (covered(block)) {
    // BE#serverTick L97-101 / #dropAllItems: something covers the top, so
    // every item drops where the stove is.
    dropAll(dimension, block, stove);
    save(table, block, undefined);
    return;
  }
  const done = step(stove, { lit, interval: table.tick_interval, recipes: table.recipes });
  for (const stack of done.cooked) {
    const motion = cookedMotion(Math.random);
    const where = { x: block.location.x + motion.dx, y: block.location.y + motion.dy, z: block.location.z + motion.dz };
    const entity = dimension.spawnItem(rebuild(stack, stack.amount), where);
    entity.clearVelocity();
    entity.applyImpulse({ x: motion.vx, y: motion.vy, z: motion.vz });
  }
  if (done.changed) save(table, block, stove);
}

function dropAll(dimension, block, stove) {
  const at = centre(block);
  for (const item of stove.items) {
    if (item) dropStored(dimension, item, item.amount, at);
  }
}

function broken(table, event) {
  // Block#onRemove (NeoForge L188-195) / BE#preRemoveSideEffects
  // (Refabricated L91-97): the items on top drop where the stove was.
  const stove = load(table, event.block);
  saveStored(keyOf(table, event.block), undefined);
  if (stove) dropAll(event.dimension, event.block, stove);
}

function beforePlace(table, event) {
  // Block#getStateForPlacement (L167-172): placed lit.
  event.permutationToPlace = event.permutationToPlace.withState(table.lit_state, "true");
}

/** Register the stove's custom component for one mod's data table. */
export function registerStove(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      onPlayerInteract: (event) => interact(table, event),
      onTick: (event) => tick(table, event),
      onPlayerBreak: (event) => broken(table, event),
      beforeOnPlayerPlace: (event) => beforePlace(table, event),
      // A stove placed where one was destroyed without a player (explosion,
      // piston) must not inherit its food; lighting or putting it out
      // re-places the same block and keeps it.
      onPlace: (event) => {
        if (event.previousBlock && event.previousBlock.type && event.previousBlock.type.id === table.block) return;
        saveStored(keyOf(table, event.block), undefined);
      },
    });
  });
}
