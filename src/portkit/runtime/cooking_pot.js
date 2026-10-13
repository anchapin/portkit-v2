// portkit station runtime: Farmer's Delight cooking pot, Bedrock binding (#177).
//
// Fixed file, copied verbatim into every pack that ships the cooking pot
// (portkit/runtime/; see docs/decisions.md, 2026-10-13). The generated entry
// scripts/portkit/main.js calls registerCookingPot(table) with the mod's data
// table. Script API: @minecraft/server 2.0.0 (Bedrock 1.21.90), custom
// components v2 (learn.microsoft.com, "Introducing Custom Components";
// BlockCustomComponent onPlayerInteract / onTick / onPlayerBreak / onPlace /
// beforeOnPlayerPlace). The block carries minecraft:tick at the table's
// tick_interval, so onTick runs while its chunk is ticking.
//
// Java opens a container menu on use; Bedrock custom blocks have none, so the
// pot is worked by hand (CookingPotBlock#useItemOn, NeoForge dd8b9b0b
// L72-93, Refabricated a8cb49ed L65-86, for what Java itself does on use):
//   * sneak with an empty hand: hang the pot on its handle, or take it off
//     (Java, the same);
//   * use the meal's container on it with a meal inside: serve one portion
//     (Java, the same);
//   * use any other item: put the held stack in, as shift-clicking it into
//     FD's menu does (cooking_pot_core.insert);
//   * use an empty hand: take out the output, else the last ingredient stack,
//     else the containers (stands in for taking them out of the menu).
// The action bar then shows what the pot holds.

import { Direction, EquipmentSlot, ItemStack, system } from "@minecraft/server";
import {
  boilChance,
  ejectOffset,
  emptyPot,
  experience,
  findRecipe,
  insert,
  isContainerValid,
  isHeated,
  isIdle,
  serve,
  status,
  step,
  storageKey,
  takeOut,
  trayState,
} from "./cooking_pot_core.js";
import { centre, describe, dropStored, give, loadStored, maxAmountOf, play, rebuild, saveStored } from "./station_storage.js";

function keyOf(table, block) {
  return storageKey(table.component, block.dimension.id, block.location);
}

function load(table, block) {
  return loadStored(keyOf(table, block));
}

function save(table, block, pot) {
  saveStored(keyOf(table, block), pot && !isIdle(pot) ? pot : undefined);
}

/** A block as the heat rules read it: { id, state(name) }, or undefined. */
function view(block) {
  if (!block) return undefined;
  const permutation = block.permutation;
  return { id: block.typeId, state: (name) => permutation.getState(name) };
}

function below(block, steps) {
  try {
    return block.below(steps);
  } catch {
    return undefined; // outside the world or an unloaded chunk
  }
}

function heated(table, block) {
  return isHeated(table.heat, view(below(block, 1)), view(below(block, 2)));
}

function setSupport(table, block, value) {
  const permutation = block.permutation;
  if (permutation.getState(table.support_state) === value) return;
  block.setPermutation(permutation.withState(table.support_state, value));
}

function facingOf(block) {
  const facing = block.permutation.getState("minecraft:cardinal_direction");
  return typeof facing === "string" ? facing : "north";
}

function setHeld(equippable, held, amount) {
  if (amount > 0) {
    held.amount = amount;
    equippable.setEquipment(EquipmentSlot.Mainhand, held);
  } else {
    equippable.setEquipment(EquipmentSlot.Mainhand, undefined);
  }
}

function show(table, player, pot, block) {
  const recipe = findRecipe(table.recipes, pot);
  player.onScreenDisplay.setActionBar(status(pot, heated(table, block), recipe));
}

function interact(table, event) {
  const { block, dimension, player } = event;
  if (!player) return;
  const equippable = player.getComponent("minecraft:equippable");
  const held = equippable.getEquipment(EquipmentSlot.Mainhand);

  if (!held && player.isSneaking) {
    // Block#useItemOn L73-76: toggle the handle; off it, back to tray or none.
    const current = block.permutation.getState(table.support_state);
    setSupport(table, block, current === "handle" ? trayState(table.heat, view(below(block, 1))) : "handle");
    play(dimension, centre(block), table.sounds.handle);
    return;
  }

  const pot = load(table, block) ?? emptyPot();
  if (held && pot.meal && isContainerValid(pot, held.typeId)) {
    // Block L80-86 / BE#useHeldItemOnMeal: one container in, one portion out.
    // Java shrinks the held container in creative too.
    const served = serve(pot, held.typeId);
    setHeld(equippable, held, held.amount - 1);
    give(player, new ItemStack(served, 1));
    play(dimension, centre(block), table.sounds.serve);
    save(table, block, pot);
    show(table, player, pot, block);
    return;
  }

  if (held) {
    // Menu#quickMoveStack: the held stack goes in as a shift-click would.
    const moved = insert(pot, describe(held, held.amount), held.maxAmount, table.serving_containers);
    if (moved > 0) {
      setHeld(equippable, held, held.amount - moved);
      save(table, block, pot);
    }
    show(table, player, pot, block);
    return;
  }

  const taken = takeOut(pot);
  if (taken) {
    let left = taken.stack.amount;
    const max = maxAmountOf(taken.stack.id);
    while (left > 0) {
      const size = Math.min(left, max);
      give(player, rebuild(taken.stack, size));
      left -= size;
    }
    if (taken.from === "output") {
      // CookingPotResultSlot#checkTakeAchievements -> BE#awardUsedRecipes
      // (L360-364): taking the output pays out the experience owed.
      payExperience(table, pot, player);
    }
    save(table, block, pot);
  }
  show(table, player, pot, block);
}

function payExperience(table, pot, player) {
  const xp = experience(pot.used, table.recipes, Math.random);
  pot.used = {};
  if (xp > 0 && player) player.addExperience(xp);
}

function tick(table, event) {
  const { block, dimension } = event;
  // Block#updateShape (L127-135): off its handle, the pot follows the block below.
  if (block.permutation.getState(table.support_state) !== "handle") {
    setSupport(table, block, trayState(table.heat, view(below(block, 1))));
  }
  const pot = load(table, block);
  const hot = heated(table, block);
  if (hot) {
    const sound = pot && pot.meal ? table.sounds.boil_soup : table.sounds.boil;
    if (sound && Math.random() < boilChance(sound.chance_per_tick, table.tick_interval)) {
      const pitch = sound.pitch_min + Math.random() * (sound.pitch_max - sound.pitch_min);
      play(dimension, centre(block, 0), sound, pitch);
    }
  }
  if (!pot) return;
  const done = step(pot, {
    heated: hot,
    recipes: table.recipes,
    interval: table.tick_interval,
    maxAmount: maxAmountOf,
    remainders: table.remainders,
  });
  if (done.ejected.length > 0) {
    const offset = ejectOffset(facingOf(block));
    const at = { x: block.location.x + 0.5 + offset.dx, y: block.location.y + offset.dy, z: block.location.z + 0.5 + offset.dz };
    for (const id of done.ejected) {
      const entity = dimension.spawnItem(new ItemStack(id, 1), at);
      entity.clearVelocity();
      entity.applyImpulse({ x: offset.vx, y: offset.vy, z: offset.vz });
    }
  }
  save(table, block, pot);
}

function broken(table, event) {
  // Block#onRemove (L157-167): the ingredients, containers and output drop
  // where the pot was, and the experience owed pops out. Java keeps the meal
  // inside the dropped pot item (loot copy_components); Bedrock can't, so the
  // meal drops as items too.
  const pot = load(table, event.block);
  saveStored(keyOf(table, event.block), undefined);
  if (!pot) return;
  const at = centre(event.block);
  for (const stack of [...pot.slots, pot.container, pot.output]) {
    if (stack) dropStored(event.dimension, stack, stack.amount, at);
  }
  if (pot.meal) dropStored(event.dimension, { id: pot.meal.id }, pot.meal.amount, at);
  payExperience(table, pot, event.player);
}

function beforePlace(table, event) {
  // Block#getStateForPlacement (L111-124): placed against a ceiling it hangs
  // on its handle, else it sits on a tray over a tray heat source.
  const permutation = event.permutationToPlace;
  const value = event.face === Direction.Down ? "handle" : trayState(table.heat, view(below(event.block, 1)));
  event.permutationToPlace = permutation.withState(table.support_state, value);
}

/** Register the cooking pot's custom component for one mod's data table. */
export function registerCookingPot(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      onPlayerInteract: (event) => interact(table, event),
      onTick: (event) => tick(table, event),
      onPlayerBreak: (event) => broken(table, event),
      beforeOnPlayerPlace: (event) => beforePlace(table, event),
      // A pot placed where one was destroyed without a player (explosion,
      // piston) must not inherit its contents; a state change (handle, tray)
      // re-places the same block and keeps them.
      onPlace: (event) => {
        if (event.previousBlock && event.previousBlock.type && event.previousBlock.type.id === table.block) return;
        saveStored(keyOf(table, event.block), undefined);
      },
    });
  });
}
