// The in-game check pack (#238): run once when the world loads on a Bedrock
// Dedicated Server, print one tagged line per failure and a summary, then
// DONE so the runner stops the server. Generated per converted pack: the ids
// come from ./data.js, written by portkit.ingame.testpack.
//
// Checks (stable @minecraft/server 2.0.0, no experiments):
//   place      every block resolves and sets in the world, and reads back
//   item       every item (and every block's item) builds and spawns as an
//              item entity carrying the same id
//   container  a block the converter made a container (#226) has an
//              inventory of the slot count it wrote
//   connection a block on the connection trait (#221 multiparts) reports its
//              four cardinal connection states, joined to its own kind and
//              not to air (the states its bones' visibility reads)
// Content-log errors are the runner's to count (it reads the server output).
import { world, system, BlockPermutation, ItemStack } from "@minecraft/server";
import {
  AREA, CONNECTION_STATES, ITEM_Y, Tally, connectionVerdict,
  connectionSlot, containerVerdict, describe, line, slot,
} from "./ingame_core.js";
import { CHECKS } from "./data.js";

const BATCH = 16;
const say = (kind, payload) => console.warn(line(kind, payload));

world.afterEvents.worldLoad.subscribe(() => {
  system.run(() => {
    run().catch((err) => {
      say("ERROR", { detail: describe(err) });
      say("DONE", {});
    });
  });
});

async function loaded(dim) {
  for (let tick = 0; tick < 1200; tick += 10) {
    try {
      if (dim.getBlock({ x: 0, y: 0, z: 0 }) && dim.getBlock({ x: AREA - 1, y: 0, z: AREA - 1 })) return true;
    } catch {
      // not loaded yet
    }
    await system.waitTicks(10);
  }
  return false;
}

async function run() {
  const dim = world.getDimension("overworld");
  dim.runCommand(`tickingarea add 0 0 0 ${AREA - 1} 0 ${AREA - 1} portkit_ingame true`);
  say("START", { blocks: CHECKS.blocks.length, items: CHECKS.items.length });
  if (!(await loaded(dim))) {
    say("ERROR", { detail: "the ticking area never loaded" });
    say("DONE", {});
    return;
  }
  const tally = new Tally();
  const fail = (check, id, detail) => {
    tally.record(check, id, false, detail);
    say("FAIL", { check, id, detail });
  };

  // place (and container, on the placed block)
  for (let i = 0; i < CHECKS.blocks.length; i++) {
    const id = CHECKS.blocks[i];
    const at = slot(i);
    try {
      const block = dim.getBlock(at);
      block.setPermutation(BlockPermutation.resolve(id));
      const got = dim.getBlock(at)?.typeId;
      if (got === id) tally.record("place", id, true);
      else fail("place", id, `reads back as ${got}`);
      const slots = CHECKS.containers[id];
      if (slots !== undefined) {
        let size;
        try {
          size = dim.getBlock(at)?.getComponent("minecraft:inventory")?.container?.size;
        } catch (err) {
          size = undefined;
        }
        const verdict = containerVerdict(slots, size);
        if (verdict.ok) tally.record("container", id, true);
        else fail("container", id, verdict.problems.join("; "));
      }
    } catch (err) {
      fail("place", id, describe(err));
    }
    if (i % BATCH === BATCH - 1) await system.waitTicks(1);
  }

  // connection: the block, its own kind to the east, stone to the north
  for (let i = 0; i < CHECKS.connections.length; i++) {
    const id = CHECKS.connections[i];
    const at = connectionSlot(i);
    try {
      dim.getBlock(at).setPermutation(BlockPermutation.resolve(id));
      dim.getBlock({ x: at.x, y: at.y, z: at.z - 1 }).setPermutation(BlockPermutation.resolve("minecraft:stone"));
      dim.getBlock({ x: at.x + 1, y: at.y, z: at.z }).setPermutation(BlockPermutation.resolve(id));
    } catch (err) {
      fail("connection", id, describe(err));
      continue;
    }
    await system.waitTicks(2);
    try {
      const perm = dim.getBlock(at).permutation;
      const states = {};
      for (const name of CONNECTION_STATES) states[name] = perm.getState(name);
      const verdict = connectionVerdict(states);
      say("CONNECTION", { id, states });
      if (verdict.ok) tally.record("connection", id, true);
      else fail("connection", id, verdict.problems.join("; "));
    } catch (err) {
      fail("connection", id, describe(err));
    }
  }

  // item: each id spawned as an item entity, read back, removed
  const items = [...CHECKS.items, ...CHECKS.blocks.map((id) => `block:${id}`)];
  for (let i = 0; i < items.length; i++) {
    const asBlock = items[i].startsWith("block:");
    const id = asBlock ? items[i].slice(6) : items[i];
    const check = asBlock ? "block_item" : "item";
    const at = slot(i % 1024, ITEM_Y);
    try {
      const entity = dim.spawnItem(new ItemStack(id, 1), { x: at.x + 0.5, y: at.y, z: at.z + 0.5 });
      const got = entity.getComponent("minecraft:item")?.itemStack?.typeId;
      entity.remove();
      if (got === id) tally.record(check, id, true);
      else fail(check, id, `spawned as ${got}`);
    } catch (err) {
      fail(check, id, describe(err));
    }
    if (i % BATCH === BATCH - 1) await system.waitTicks(1);
  }

  say("SUMMARY", tally.summary());
  say("DONE", {});
}
