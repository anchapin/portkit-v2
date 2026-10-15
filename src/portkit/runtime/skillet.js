// portkit station runtime: Farmer's Delight skillet, Bedrock binding (#177).
//
// Fixed file, copied verbatim into every pack that ships the skillet
// (portkit/runtime/; see docs/decisions.md). The generated entry
// scripts/portkit/main.js calls registerSkillet(table) with the mod's data
// table. Script API: @minecraft/server 2.0.0 (Bedrock 1.21.90), custom
// components v2 (BlockCustomComponent onPlayerInteract / onTick /
// onPlayerBreak / onPlace / beforeOnPlayerPlace), world.beforeEvents.itemUse,
// world.afterEvents.entityHitEntity and system.runInterval.
//
// Placed (SkilletBlock#useItemOn, NeoForge dd8b9b0b L73-97, Refabricated
// a8cb49ed L67-97): an empty hand takes the stack out; a food a campfire
// recipe takes goes in whole when the skillet is empty; over heat it cooks one
// item at a time and throws each result out to the side. Java draws the food
// with a block-entity renderer; Bedrock custom blocks have none, so every use
// shows the skillet's contents in the action bar.
//
// Held (SkilletItem#use L154-183): Java cooks with the skillet in one hand and
// the food in the other while the use button is held. Bedrock's off-hand only
// takes a few vanilla items (never food), and a script can't see the use
// button held on an item with no use animation, so here the skillet goes in
// the off-hand, the food in the main hand: using the food near heat cooks one
// of it instead of eating it, for as long as the skillet stays in the off-hand
// (docs/decisions.md, 2026-10-13 skillet).
//
// The item is a weapon (iron tier stats on the item JSON) that plays FD's hit
// sound, and is placed only while sneaking (SkilletItem#place L300-307).

import { EquipmentSlot, GameMode, ItemStack, system, world } from "@minecraft/server";
import {
  emptySkillet,
  findRecipe,
  fireAspectOf,
  heldStatus,
  insert,
  interaction,
  isCooking,
  launch,
  nearHeat,
  soundChance,
  startHeld,
  status,
  step,
  stepHeld,
  takeOut,
} from "./skillet_core.js";
import { blockMatches, isHeated, storageKey, trayState } from "./station_core.js";
import {
  blockBelow as below,
  blockView as view,
  centre,
  describe,
  dropStored,
  facingOf,
  give,
  loadStored,
  maxAmountOf,
  play,
  rebuild,
  saveStored,
} from "./station_storage.js";

function keyOf(table, block) {
  return storageKey(table.component, block.dimension.id, block.location);
}

function load(table, block) {
  return loadStored(keyOf(table, block));
}

function save(table, block, skillet) {
  saveStored(keyOf(table, block), skillet);
}

function heated(table, block) {
  // HeatableBlockEntity#isHeated (the cooking pot's rule, same tags).
  return isHeated(table.heat, view(below(block, 1)), view(below(block, 2)));
}

/** Block#getTrayState (L195-197): "true" over a tray heat source. */
function support(table, block) {
  return trayState(table.heat, view(below(block, 1))) === "tray" ? "true" : "false";
}

function message(table, player, role) {
  const key = table.messages[role];
  if (key) player.onScreenDisplay.setActionBar({ rawtext: [{ translate: key }] });
}

function pitchOf(sound) {
  return sound.pitch_min + Math.random() * (sound.pitch_max - sound.pitch_min);
}

function show(table, player, block, skillet) {
  player.onScreenDisplay.setActionBar(status(skillet ?? emptySkillet(), heated(table, block)));
}

function interact(table, event) {
  const { block, dimension, player } = event;
  if (!player) return;
  const equippable = player.getComponent("minecraft:equippable");
  const held = equippable.getEquipment(EquipmentSlot.Mainhand);
  const creative = player.getGameMode() === GameMode.Creative;
  const skillet = load(table, block) ?? emptySkillet();
  const action = interaction(skillet, held && held.typeId, table.recipes);

  if (action === "take") {
    // L80-86: the stack comes out into the hand (in creative it is removed
    // and not given, as Java does).
    const stack = takeOut(skillet);
    if (stack && !creative) equippable.setEquipment(EquipmentSlot.Mainhand, rebuild(stack, stack.amount));
    save(table, block, skillet);
  } else if (action === "insert") {
    // BE#addItemToCook L158-179 and L87-93: the stack goes in, the hand keeps
    // what didn't fit, the lantern place sound (0.7 / 1.0); add_food (0.8 /
    // 1.0) when it was empty and is heated.
    const recipe = findRecipe(table.recipes, held.typeId);
    const moved = insert(skillet, describe(held, held.amount), held.amount, Math.min(64, maxAmountOf(held.typeId)),
      recipe, table.cooking);
    if (moved > 0) {
      if (!creative) {
        if (held.amount > moved) {
          held.amount -= moved;
          equippable.setEquipment(EquipmentSlot.Mainhand, held);
        } else {
          equippable.setEquipment(EquipmentSlot.Mainhand, undefined);
        }
      }
      if (heated(table, block)) play(dimension, centre(block), table.sounds.add_food);
      play(dimension, centre(block), table.sounds.place);
      save(table, block, skillet);
    }
  } else {
    message(table, player, "invalid_item");
    return;
  }
  show(table, player, block, skillet);
}

function tick(table, event) {
  const { block, dimension } = event;
  // Block#updateShape (L136-145): the tray state follows the block below.
  // Bedrock has no neighbour-update hook for custom blocks in 2.0.0, so it is
  // re-read every run.
  const tray = support(table, block);
  if (block.permutation.getState(table.support_state) !== tray) {
    block.setPermutation(block.permutation.withState(table.support_state, tray));
  }
  const skillet = load(table, block);
  if (!skillet) return;
  const hot = heated(table, block);
  if (isCooking(skillet, hot)) {
    // Block#animateTick (L162-173): the sizzle, 1 in 10 client ticks.
    const sizzle = table.sounds.sizzle;
    if (sizzle && Math.random() < soundChance(sizzle.chance_per_tick, table.tick_interval)) {
      play(dimension, centre(block, 0), sizzle, pitchOf(sizzle));
    }
  }
  const done = step(skillet, { heated: hot, interval: table.tick_interval, recipes: table.recipes });
  for (const stack of done.cooked) {
    const motion = launch(facingOf(block), table.launch);
    const where = { x: block.location.x + motion.dx, y: block.location.y + motion.dy, z: block.location.z + motion.dz };
    const entity = dimension.spawnItem(new ItemStack(stack.id, stack.amount), where);
    entity.clearVelocity();
    entity.applyImpulse({ x: motion.vx, y: motion.vy, z: motion.vz });
  }
  if (done.changed) save(table, block, skillet);
}

function broken(table, event) {
  // Block#onRemove (NeoForge L105-113) / BE#preRemoveSideEffects
  // (Refabricated L145-150): the stored stack drops.
  const { block, dimension, player } = event;
  const skillet = load(table, block);
  saveStored(keyOf(table, block), undefined);
  const at = centre(block);
  if (skillet && skillet.stack) dropStored(dimension, skillet.stack, skillet.stack.amount, at);
  // The loot table's copy_skillet (CopySkilletFunction) drops the skillet item
  // it was placed from, enchantments and wear kept. Bedrock's block drops a
  // plain skillet as its own item (none for a creative player, as in Java), so
  // once it has spawned it is swapped for the placed one.
  const item = skillet && skillet.item;
  if (!item || !hasData(item) || (player && player.getGameMode() === GameMode.Creative)) return;
  system.run(() => swapDrop(table, dimension, at, item));
}

function hasData(stored) {
  return Object.keys(stored).some((k) => k !== "id" && k !== "amount");
}

function swapDrop(table, dimension, at, item) {
  let entities = [];
  try {
    entities = dimension.getEntities({ location: at, maxDistance: 1.5, type: "minecraft:item" });
  } catch {
    return;
  }
  for (const entity of entities) {
    const component = entity.getComponent("minecraft:item");
    const stack = component && component.itemStack;
    if (!stack || stack.typeId !== table.item || hasData(describe(stack, 1))) continue;
    const where = entity.location;
    entity.remove();
    dimension.spawnItem(rebuild(item, 1), where);
    return;
  }
}

// Skillet item data read at placement, until onPlace stores it.
const placing = new Map();

function beforePlace(table, event) {
  const { player } = event;
  // SkilletItem#place (L300-307): only while sneaking; otherwise Java goes on
  // to SkilletItem#use, which with the skillet in the main hand (the food
  // would be in the off-hand) has nothing to cook here.
  if (player && !player.isSneaking) {
    event.cancel = true;
    system.run(() => mainHandUse(table, player));
    return;
  }
  // Block#getStateForPlacement (L126-134): facing (the placement trait) and
  // the tray state from the block below.
  event.permutationToPlace = event.permutationToPlace.withState(table.support_state, support(table, event.block));
  // SkilletItem#updateCustomBlockEntityTag -> BE#setSkilletItem (L152-156):
  // the placed skillet remembers the item it came from.
  const held = player && player.getComponent("minecraft:equippable").getEquipment(EquipmentSlot.Mainhand);
  if (held && held.typeId === table.item) placing.set(keyOf(table, event.block), describe(held, 1));
}

function placed(table, event) {
  // A state change (the tray) re-places the same block and keeps it.
  if (event.previousBlock && event.previousBlock.type && event.previousBlock.type.id === table.block) return;
  const key = keyOf(table, event.block);
  const item = placing.get(key) ?? null;
  placing.delete(key);
  saveStored(key, emptySkillet(item));
}

// -- held -----------------------------------------------------------------------

function sessionKey(table) {
  return `${table.component}|held`;
}

function loadSession(table, player) {
  const raw = player.getDynamicProperty(sessionKey(table));
  if (typeof raw !== "string") return undefined;
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function saveSession(table, player, session) {
  player.setDynamicProperty(sessionKey(table), session === undefined ? undefined : JSON.stringify(session));
}

function playerNearHeat(table, player) {
  // Item#isPlayerNearHeatSource (L128-139).
  const onFire = player.getComponent("minecraft:onfire") !== undefined;
  const base = { x: Math.floor(player.location.x), y: Math.floor(player.location.y), z: Math.floor(player.location.z) };
  const blocks = [];
  for (let dx = -1; dx <= 1; dx += 1) {
    for (let dy = -1; dy <= 1; dy += 1) {
      for (let dz = -1; dz <= 1; dz += 1) {
        try {
          blocks.push(view(player.dimension.getBlock({ x: base.x + dx, y: base.y + dy, z: base.z + dz })));
        } catch {
          // outside the world or an unloaded chunk
        }
      }
    }
  }
  return nearHeat(onFire, blocks.filter(Boolean), table.heat.nearby, blockMatches);
}

function underwater(player) {
  // Entity#isUnderWater: the eyes are in water.
  try {
    const head = player.dimension.getBlock(player.getHeadLocation());
    return !!head && (head.typeId === "minecraft:water" || head.typeId === "minecraft:flowing_water" || head.isWaterlogged);
  } catch {
    return false;
  }
}

/** The skillet used from the main hand: Java's other hand (here, the off-hand) holds no food. */
function mainHandUse(table, player) {
  if (playerNearHeat(table, player)) message(table, player, "how_to_cook");
}

function offhandSkillet(table, player) {
  const offhand = player.getComponent("minecraft:equippable").getEquipment(EquipmentSlot.Offhand);
  return offhand && offhand.typeId === table.item ? offhand : undefined;
}

function beforeItemUse(table, event) {
  const player = event.source;
  const stack = event.itemStack;
  if (!player || !stack || player.typeId !== "minecraft:player") return;
  if (stack.typeId === table.item) {
    system.run(() => mainHandUse(table, player));
    return;
  }
  const recipe = findRecipe(table.recipes, stack.typeId);
  if (!recipe) return;
  const skillet = offhandSkillet(table, player);
  if (!skillet) return;
  if (loadSession(table, player)) {
    // Item#use L160-163: already cooking; the use goes on.
    event.cancel = true;
    return;
  }
  if (!playerNearHeat(table, player)) return;
  event.cancel = true;
  const fire = fireAspectOf(describe(skillet, 1));
  system.run(() => startCooking(table, player, recipe, fire));
}

function startCooking(table, player, recipe, fireAspect) {
  if (underwater(player)) {
    message(table, player, "underwater");
    return;
  }
  const equippable = player.getComponent("minecraft:equippable");
  const food = equippable.getEquipment(EquipmentSlot.Mainhand);
  const current = food && findRecipe(table.recipes, food.typeId);
  if (!current || current.id !== recipe.id) return;
  // L171-177: one of the food goes into the skillet (in creative too: Java
  // sets the other hand to what is left without a creative check).
  const session = startHeld(describe(food, 1), recipe, fireAspect, table.cooking);
  if (food.amount > 1) {
    food.amount -= 1;
    equippable.setEquipment(EquipmentSlot.Mainhand, food);
  } else {
    equippable.setEquipment(EquipmentSlot.Mainhand, undefined);
  }
  saveSession(table, player, session);
  player.onScreenDisplay.setActionBar(heldStatus(session));
}

function heldTick(table) {
  for (const player of world.getPlayers()) {
    const session = loadSession(table, player);
    if (!session) continue;
    if (!offhandSkillet(table, player)) {
      // Item#releaseUsing (L208-220): the food goes back to the inventory.
      give(player, rebuild(session.ingredient, 1));
      saveSession(table, player, undefined);
      continue;
    }
    if (stepHeld(session, table.tick_interval) === "done") {
      // Item#finishUsingItem (L223-247): the result to the inventory, or at
      // the player's feet when it doesn't fit.
      const recipe = table.recipes.find((r) => r.id === session.recipe);
      if (recipe) give(player, new ItemStack(recipe.result.item, recipe.result.count));
      saveSession(table, player, undefined);
      player.onScreenDisplay.setActionBar("");
      continue;
    }
    // Item#onUseTick (L186-205): a sizzle 1 in 50 ticks while cooking.
    const sizzle = table.sounds.held_sizzle;
    if (sizzle && Math.random() < soundChance(sizzle.chance_per_tick, table.tick_interval)) {
      play(player.dimension, player.location, sizzle, pitchOf(sizzle));
    }
    saveSession(table, player, session);
    player.onScreenDisplay.setActionBar(heldStatus(session));
  }
}

function hit(table, event) {
  // SkilletEvents#playSkilletAttackSound (NeoForge Item L91-110,
  // Refabricated L307-322): the strong hit sound at pitch 0.9-1.1 when the
  // attacker's main hand holds the skillet. Java plays the weak one for a
  // player's under-charged swing; Bedrock has no attack charge, so every hit
  // is a full one.
  const attacker = event.damagingEntity;
  if (!attacker || attacker.typeId !== "minecraft:player") return;
  const held = attacker.getComponent("minecraft:equippable").getEquipment(EquipmentSlot.Mainhand);
  if (!held || held.typeId !== table.item) return;
  const sound = table.sounds.attack;
  if (sound) play(attacker.dimension, attacker.location, sound, pitchOf(sound));
}

/** Register the skillet's custom component and events for one mod's data table. */
export function registerSkillet(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      onPlayerInteract: (event) => interact(table, event),
      onTick: (event) => tick(table, event),
      onPlayerBreak: (event) => broken(table, event),
      beforeOnPlayerPlace: (event) => beforePlace(table, event),
      onPlace: (event) => placed(table, event),
    });
  });
  world.beforeEvents.itemUse.subscribe((event) => beforeItemUse(table, event));
  world.afterEvents.entityHitEntity.subscribe((event) => hit(table, event));
  system.runInterval(() => heldTick(table), table.tick_interval);
}

