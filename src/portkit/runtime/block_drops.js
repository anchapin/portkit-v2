// portkit runtime: drops a mod's loot modifiers add to vanilla blocks (#280).
// portkit-requires: @minecraft/server 2.0.0
//
// Fixed file, copied verbatim into every pack with such a drop
// (portkit/runtime/; docs/decisions.md 2026-10-20 loot injection). The
// generated entry scripts/portkit/main.js calls registerBlockDrops(table)
// with the mod's table: per Bedrock vanilla block id, the rows (one per pool
// of the added table) block_drops_core.js rolls.
//
// Bedrock has no loot-table injection and Bedrock's vanilla blocks keep their
// own drops, so this adds the mod's drop beside them when a player breaks the
// block (world.afterEvents.playerBreakBlock): not in Creative (Java gives no
// loot there either), not with the doTileDrops game rule off, and not when
// the tool has Silk Touch where the Java entry says so. Explosions and other
// non-player breaks add nothing (fewer drops than Java, never more).

import { GameMode, ItemStack, world } from "@minecraft/server";
import { rollCount } from "./block_drops_core.js";

function level(stack, id) {
  try {
    const enchantable = stack ? stack.getComponent("minecraft:enchantable") : undefined;
    const found = enchantable ? enchantable.getEnchantment(id) : undefined;
    return found ? found.level : 0;
  } catch {
    return 0;
  }
}

function creative(player) {
  try {
    return player.getGameMode() === GameMode.Creative;
  } catch {
    return false;
  }
}

export function registerBlockDrops(table) {
  world.afterEvents.playerBreakBlock.subscribe((event) => {
    const rows = table.blocks[event.brokenBlockPermutation?.type?.id];
    if (!rows || creative(event.player)) return;
    if (world.gameRules && world.gameRules.doTileDrops === false) return;
    const tool = event.itemStackBeforeBreak;
    const fortune = level(tool, "fortune");
    const silk = level(tool, "silk_touch");
    const at = event.block.center ? event.block.center()
      : { x: event.block.location.x + 0.5, y: event.block.location.y + 0.5, z: event.block.location.z + 0.5 };
    for (const row of rows) {
      const count = rollCount(row, fortune, silk, Math.random);
      if (count > 0) event.dimension.spawnItem(new ItemStack(row.item, count), at);
    }
  });
}
