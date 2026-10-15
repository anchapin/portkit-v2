// portkit station runtime: Farmer's Delight feasts, Bedrock binding (#177).
//
// Fixed file, copied verbatim into every pack that ships a feast
// (portkit/runtime/; see docs/decisions.md). The generated entry
// scripts/portkit/main.js calls registerFeasts(table) with the mod's data
// table. Script API: @minecraft/server 2.0.0 (Bedrock 1.21.90), custom
// components v2 (BlockCustomComponent onPlayerInteract) and
// Dimension.runCommand.
//
// Every feast block carries the one component; the table holds each feast by
// block id. The serving count is the block's integer state (the data table's
// servings_state), so a feast needs no stored data. What a feast drops (when
// broken, cleared at 0 servings, or vanishing with its last serving) is its
// loot table per serving count (minecraft:loot on the block's permutations);
// clearing it here runs `setblock ... destroy`, which drops through the same
// tables, as Java's destroyBlock(pos, true) drops through its loot table.

import { EquipmentSlot, GameMode, ItemStack, system } from "@minecraft/server";
import { containerMessage, interaction } from "./feast_core.js";
import { destroyCommand } from "./station_core.js";
import { centre, give, play } from "./station_storage.js";

function destroy(block) {
  block.dimension.runCommand(destroyCommand(block.location));
}

function interact(table, event) {
  const { block, dimension, player } = event;
  if (!player) return;
  const feast = table.feasts[block.typeId];
  if (!feast) return;
  const servings = block.permutation.getState(table.servings_state);
  const equippable = player.getComponent("minecraft:equippable");
  const held = equippable.getEquipment(EquipmentSlot.Mainhand);
  const creative = player.getGameMode() === GameMode.Creative;
  const act = interaction(feast, servings, held && held.typeId, creative);

  if (act.action === "clear") {
    // L106-110 (Refabricated L113-117): WOOD_BREAK at 0.8 / 0.8, then the
    // block goes with its drops (the plate and scraps).
    play(dimension, centre(block), table.sounds.clear);
    destroy(block);
  } else if (act.action === "serve") {
    // L117-131 (Refabricated L124-137): one serving fewer; the container is
    // used up (not in creative); the serving goes to the inventory, or drops
    // at the player when it doesn't fit; a feast without leftovers goes at 0;
    // the take-portion sound.
    block.setPermutation(block.permutation.withState(table.servings_state, act.next));
    if (act.consume) {
      if (held.amount > 1) {
        held.amount -= 1;
        equippable.setEquipment(EquipmentSlot.Mainhand, held);
      } else {
        equippable.setEquipment(EquipmentSlot.Mainhand, undefined);
      }
    }
    give(player, new ItemStack(act.item, 1));
    if (act.vanish) destroy(block);
    play(dimension, centre(block), table.sounds.serve);
  } else if (act.action === "need_container") {
    // L133-135 (Refabricated L139-141): "You need a %s to eat this."
    const key = table.messages.use_container;
    if (key) player.onScreenDisplay.setActionBar(containerMessage(key, feast));
  }
}

/** Register the feasts' custom component for one mod's data table. */
export function registerFeasts(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      onPlayerInteract: (event) => interact(table, event),
    });
  });
}
