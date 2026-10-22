// The in-game check pack (#238): run once when the world loads on a Bedrock
// Dedicated Server, print one tagged line per failure and a summary, then
// DONE so the runner stops the server. Generated per converted pack: the ids
// come from ./data.js, written by portkit.ingame.testpack.
//
// Checks (stable @minecraft/server 2.2.0, no experiments):
//   place      every block resolves and sets in the world, and reads back
//   item       every item (and every block's item) builds and spawns as an
//              item entity carrying the same id
//   container  a block the converter made a container (#226) has an
//              inventory of the slot count it wrote
//   connection a block on the connection trait (#221 multiparts) reports its
//              four cardinal connection states, joined to its own kind and
//              not to air (the states its bones' visibility reads)
//   drop       a block whose minecraft:loot the converter wired (#299),
//              broken with `setblock ... air destroy`, leaves exactly the
//              items its table gives (item entities counted around it)
//   tool_drop  a wired table that gates its drop on match_tool (#299: shears,
//              tool and tier tags) gives, for each tool that tells the gate
//              apart (and a bare hand), what the converter expects: asked of
//              world.getLootTableManager().generateLootFromBlockPermutation
//   paired     a block on the multi_block trait (#296: doors, two-tall
//              plants): placed by script with every part set, both parts read
//              back; a door is powered by a redstone block beside its lower
//              half (both halves open) and unpowered (both close); the upper
//              part broken with `setblock ... air destroy` takes the lower
//              with it and leaves exactly one drop. Reported, not asserted:
//              what placing the lower part alone and the setblock command
//              leave above it.
//   gate       a block carrying the portkit fence gate component (#367): placed
//              (closed, not in a wall), used by the runtime's scriptevent as a
//              player facing it (turned away and open) and again (closed),
//              powered by a redstone block beside it (open, powered) and
//              unpowered (closed), broken (its drop counted), then placed
//              again beside a wall across it (in_wall).
//   trapdoor   a block carrying the portkit trapdoor component (#296): placed
//              by script, powered by a redstone block beside it (it opens),
//              unpowered (it closes), broken with `setblock ... air destroy`
//              and its drop counted (exactly one).
//   plate      a block carrying the portkit pressure plate component (#296):
//              placed by script on a stone block with a redstone lamp beside
//              it; an armor stand spawned on it presses it (powered, lamp
//              lit), removing it releases it after Java's 20-tick re-check
//              (unpowered, lamp unlit); a dropped stick presses a plate any
//              entity presses and leaves a mobs-only plate unpressed; then it
//              is broken with `setblock ... air destroy` and its drop counted.
//   button     a block carrying the portkit button component (#280): placed
//              by script on top of a stone block with a redstone lamp beside
//              it; pressed with the runtime's scriptevent (the same press a
//              player's use takes): powered, lamp lit; read again a few ticks
//              before its press time is up (still powered) and after it
//              (unpowered, lamp unlit); then broken with `setblock ... air
//              destroy` and its drop counted. Reported, not asserted: an
//              arrow spawned flying at it (pressed where its set type lets
//              arrows press it).
//   ore        an ore feature the converter wrote (#281). Asserted
//              (ore_generate): outside the flat Overworld, fresh chunks of the
//              rule's dimension are loaded and the ore blocks the world
//              generated in the rule's height range counted, at least one per
//              rule. Reported, not asserted: a cube of the block it replaces
//              with the feature placed in it by Dimension.placeFeature (on
//              BDS 1.26.52 it returned false for a converted ore feature that
//              the world itself generates)
//   geode      a geode feature the converter wrote (#281 slice 3). Asserted
//              (geode_generate): the check pack's test-only copy of the rule
//              (portkit_check:, no scatter_chance) places it in every chunk;
//              fresh chunks of its dimension (the Overworld only in a
//              generated world) are scanned for its inner and alternate inner
//              layer blocks, at least one per rule. Reported: the
//              minecraft:block_face of each inner placement block found.
// Content-log errors are the runner's to count (it reads the server output).
import { world, system, BlockPermutation, ItemStack } from "@minecraft/server";
import {
  AREA, CONNECTION_STATES, DROP_BATCH, ITEM_Y, PAIRED_PART, Tally, connectionVerdict,
  connectionSlot, containerVerdict, describe, doorVerdict, dropSlot, dropVerdict, line,
  pairedSlot, pairedVerdict, plateSlot, plateVerdict, slot, trapdoorSlot, trapdoorVerdict, buttonSlot,
  gateSlot, gateVerdict, OPPOSITE,
  GEN_ORIGIN, GEN_SIZE, ORE_CUBE, generateVerdict, oreSlot, oreVerdict, scanRange,
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
  say("START", {
    blocks: CHECKS.blocks.length, items: CHECKS.items.length, drops: (CHECKS.drops ?? []).length,
    tool_drops: (CHECKS.tool_drops ?? []).length, paired: (CHECKS.paired ?? []).length,
    trapdoors: (CHECKS.trapdoors ?? []).length, plates: (CHECKS.plates ?? []).length,
    buttons: (CHECKS.buttons ?? []).length, gates: (CHECKS.gates ?? []).length, ores: (CHECKS.ores ?? []).length,
    geodes: (CHECKS.geodes ?? []).length,
  });
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

  // drop: each wired block on a stone floor, broken as a player would (the
  // destroy mode of setblock), then the item entities around it counted
  const drops = CHECKS.drops ?? [];
  const itemsNear = (at) => dim.getEntities({
    type: "minecraft:item", location: { x: at.x + 0.5, y: at.y + 0.5, z: at.z + 0.5 }, maxDistance: 3,
  });
  for (let start = 0; start < drops.length; start += DROP_BATCH) {
    const batch = drops.slice(start, start + DROP_BATCH);
    const placed = [];
    for (let k = 0; k < batch.length; k++) {
      const { id } = batch[k];
      const at = dropSlot(k);
      try {
        for (const e of itemsNear(at)) e.remove();
        dim.getBlock({ x: at.x, y: at.y - 1, z: at.z }).setPermutation(BlockPermutation.resolve("minecraft:stone"));
        dim.getBlock(at).setPermutation(BlockPermutation.resolve(id));
        placed.push(k);
      } catch (err) {
        fail("drop", id, describe(err));
      }
    }
    await system.waitTicks(1);
    for (const k of placed) {
      const at = dropSlot(k);
      try {
        dim.runCommand(`setblock ${at.x} ${at.y} ${at.z} air destroy`);
      } catch (err) {
        fail("drop", batch[k].id, describe(err));
      }
    }
    await system.waitTicks(10);
    for (const k of placed) {
      const { id, expect } = batch[k];
      const at = dropSlot(k);
      try {
        const got = [];
        for (const e of itemsNear(at)) {
          const stack = e.getComponent("minecraft:item")?.itemStack;
          if (stack) got.push({ item: stack.typeId, count: stack.amount });
          e.remove();
        }
        const verdict = dropVerdict(expect, got);
        say("DROP", { id, expect, got });
        if (verdict.ok) tally.record("drop", id, true);
        else fail("drop", id, verdict.problems.join("; "));
      } catch (err) {
        fail("drop", id, describe(err));
      }
    }
  }

  // tool_drop: the server's own loot roll for the block with each tool
  const loot = world.getLootTableManager();
  for (const { id, tool, expect } of CHECKS.tool_drops ?? []) {
    try {
      const held = tool ? new ItemStack(tool, 1) : undefined;
      const stacks = loot.generateLootFromBlockPermutation(BlockPermutation.resolve(id), held) ?? [];
      const got = stacks.map((s) => ({ item: s.typeId, count: s.amount }));
      const verdict = dropVerdict(expect, got);
      say("TOOL_DROP", { id, tool, expect, got });
      if (verdict.ok) tally.record("tool_drop", `${id} ${tool ?? "hand"}`, true);
      else fail("tool_drop", `${id} ${tool ?? "hand"}`, verdict.problems.join("; "));
    } catch (err) {
      fail("tool_drop", `${id} ${tool ?? "hand"}`, describe(err));
    }
  }

  // paired: one block at a time (#296)
  const PAIRED = CHECKS.paired ?? [];
  const read = (at) => {
    const b = dim.getBlock(at);
    let part;
    try {
      part = b?.permutation.getState(PAIRED_PART);
    } catch {
      part = undefined;
    }
    return { typeId: b?.typeId, part };
  };
  const clear = async (at) => {
    dim.runCommand(`fill ${at.x} ${at.y} ${at.z} ${at.x + 1} ${at.y + 1} ${at.z} air`);
    await system.waitTicks(2);
    for (const e of itemsNear(at)) e.remove();
  };
  const half = (at, states) => {
    const perm = dim.getBlock(at).permutation;
    return { open: perm.getState(states.open), powered: perm.getState(states.powered) };
  };
  for (let i = 0; i < PAIRED.length; i++) {
    const { id, expect, door } = PAIRED[i];
    const at = pairedSlot(i);
    const up = { x: at.x, y: at.y + 1, z: at.z };
    const seen = { id };
    try {
      dim.getBlock({ x: at.x, y: at.y - 1, z: at.z }).setPermutation(BlockPermutation.resolve("minecraft:stone"));
      // 1. the lower part alone (what the place check did)
      await clear(at);
      dim.getBlock(at).setPermutation(BlockPermutation.resolve(id));
      await system.waitTicks(2);
      seen.lower_only = { lower: read(at), upper: read(up) };
      // 2. the setblock command
      await clear(at);
      try {
        dim.runCommand(`setblock ${at.x} ${at.y} ${at.z} ${id}`);
        await system.waitTicks(2);
        seen.setblock = { lower: read(at), upper: read(up) };
      } catch (err) {
        seen.setblock = { error: describe(err) };
      }
      // 3. every part set by script: the check
      await clear(at);
      dim.getBlock(at).setPermutation(BlockPermutation.resolve(id, { [PAIRED_PART]: 0 }));
      dim.getBlock(up).setPermutation(BlockPermutation.resolve(id, { [PAIRED_PART]: 1 }));
      await system.waitTicks(2);
      seen.both = { lower: read(at), upper: read(up) };
      const placed = pairedVerdict(id, seen.both.lower, seen.both.upper);
      if (placed.ok) tally.record("paired_place", id, true);
      else fail("paired_place", id, placed.problems.join("; "));
      if (placed.ok && door) {
        const beside = { x: at.x + 1, y: at.y, z: at.z };
        dim.getBlock(beside).setPermutation(BlockPermutation.resolve("minecraft:redstone_block"));
        await system.waitTicks(4);
        seen.powered = [half(at, door), half(up, door)];
        const on = doorVerdict(true, seen.powered);
        if (on.ok) tally.record("door_power", id, true);
        else fail("door_power", id, on.problems.join("; "));
        dim.getBlock(beside).setPermutation(BlockPermutation.resolve("minecraft:air"));
        await system.waitTicks(4);
        seen.unpowered = [half(at, door), half(up, door)];
        const off = doorVerdict(false, seen.unpowered);
        if (off.ok) tally.record("door_unpower", id, true);
        else fail("door_unpower", id, off.problems.join("; "));
        seen.still_paired = pairedVerdict(id, read(at), read(up)).ok;
      }
      // 4. break the upper part as a player would; the lower goes with it
      if (placed.ok) {
        for (const e of itemsNear(at)) e.remove();
        dim.runCommand(`setblock ${up.x} ${up.y} ${up.z} air destroy`);
        await system.waitTicks(10);
        seen.after_break = { lower: read(at), upper: read(up) };
        if (seen.after_break.lower.typeId === id) fail("paired_break", id, "the lower part stayed");
        else tally.record("paired_break", id, true);
        const got = [];
        for (const e of itemsNear(at)) {
          const stack = e.getComponent("minecraft:item")?.itemStack;
          if (stack) got.push({ item: stack.typeId, count: stack.amount });
          e.remove();
        }
        seen.drop = got;
        if (expect) {
          const verdict = dropVerdict(expect, got);
          if (verdict.ok) tally.record("paired_drop", id, true);
          else fail("paired_drop", id, verdict.problems.join("; "));
        }
      }
    } catch (err) {
      fail("paired", id, describe(err));
    }
    say("PAIRED", seen);
  }

  // trapdoor: one block at a time (#296)
  const TRAPDOORS = CHECKS.trapdoors ?? [];
  for (let i = 0; i < TRAPDOORS.length; i++) {
    const { id, expect, states } = TRAPDOORS[i];
    const at = trapdoorSlot(i);
    const beside = { x: at.x + 1, y: at.y, z: at.z };
    const seen = { id };
    const stateAt = () => {
      const perm = dim.getBlock(at).permutation;
      return { open: perm.getState(states.open), powered: perm.getState(states.powered) };
    };
    try {
      for (const e of itemsNear(at)) e.remove();
      dim.getBlock(at).setPermutation(BlockPermutation.resolve(id));
      await system.waitTicks(2);
      seen.placed = dim.getBlock(at)?.typeId;
      if (seen.placed !== id) {
        fail("trapdoor_place", id, `reads back as ${seen.placed}`);
        say("TRAPDOOR", seen);
        continue;
      }
      tally.record("trapdoor_place", id, true);
      seen.before = stateAt();
      dim.getBlock(beside).setPermutation(BlockPermutation.resolve("minecraft:redstone_block"));
      await system.waitTicks(4);
      seen.powered = stateAt();
      const on = trapdoorVerdict(true, seen.powered);
      if (on.ok) tally.record("trapdoor_power", id, true);
      else fail("trapdoor_power", id, on.problems.join("; "));
      dim.getBlock(beside).setPermutation(BlockPermutation.resolve("minecraft:air"));
      await system.waitTicks(4);
      seen.unpowered = stateAt();
      const off = trapdoorVerdict(false, seen.unpowered);
      if (off.ok) tally.record("trapdoor_unpower", id, true);
      else fail("trapdoor_unpower", id, off.problems.join("; "));
      for (const e of itemsNear(at)) e.remove();
      dim.runCommand(`setblock ${at.x} ${at.y} ${at.z} air destroy`);
      await system.waitTicks(10);
      seen.after_break = dim.getBlock(at)?.typeId;
      const got = [];
      for (const e of itemsNear(at)) {
        const stack = e.getComponent("minecraft:item")?.itemStack;
        if (stack) got.push({ item: stack.typeId, count: stack.amount });
        e.remove();
      }
      seen.drop = got;
      if (expect) {
        const verdict = dropVerdict(expect, got);
        if (verdict.ok) tally.record("trapdoor_drop", id, true);
        else fail("trapdoor_drop", id, verdict.problems.join("; "));
      }
    } catch (err) {
      fail("trapdoor", id, describe(err));
    }
    say("TRAPDOOR", seen);
  }

  // plate: one pressure plate at a time (#296)
  const PLATES = CHECKS.plates ?? [];
  for (let i = 0; i < PLATES.length; i++) {
    const { id, powered, mobs_only: mobsOnly, expect } = PLATES[i];
    const at = plateSlot(i);
    const below = { x: at.x, y: at.y - 1, z: at.z };
    const beside = { x: at.x + 1, y: at.y, z: at.z };
    const centre = { x: at.x + 0.5, y: at.y, z: at.z + 0.5 };
    const seen = { id };
    const read = () => ({
      powered: dim.getBlock(at)?.permutation.getState(powered),
      lamp: dim.getBlock(beside)?.typeId === "minecraft:lit_redstone_lamp",
    });
    const judge = (check, want, state) => {
      const verdict = plateVerdict(want, { powered: state.powered });
      if (verdict.ok) tally.record(check, id, true);
      else fail(check, id, verdict.problems.join("; "));
      if (check === "plate_press" || check === "plate_release") {
        const lamp = plateVerdict(want, { powered: want, lamp: state.lamp });
        if (lamp.ok) tally.record(`${check}_redstone`, id, true);
        else fail(`${check}_redstone`, id, lamp.problems.join("; "));
      }
    };
    try {
      for (const e of itemsNear(at)) e.remove();
      dim.getBlock(below).setPermutation(BlockPermutation.resolve("minecraft:stone"));
      dim.getBlock(beside).setPermutation(BlockPermutation.resolve("minecraft:redstone_lamp"));
      dim.getBlock(at).setPermutation(BlockPermutation.resolve(id));
      await system.waitTicks(4);
      seen.placed = dim.getBlock(at)?.typeId;
      if (seen.placed !== id) {
        fail("plate_place", id, `reads back as ${seen.placed}`);
        say("PLATE", seen);
        continue;
      }
      tally.record("plate_place", id, true);
      seen.idle = read();
      judge("plate_idle", false, seen.idle);
      const stand = dim.spawnEntity("minecraft:armor_stand", centre);
      await system.waitTicks(8);
      seen.stepped = read();
      judge("plate_press", true, seen.stepped);
      stand.remove();
      await system.waitTicks(34);
      seen.left = read();
      judge("plate_release", false, seen.left);
      const stick = dim.spawnItem(new ItemStack("minecraft:stick", 1), { x: centre.x, y: at.y + 0.05, z: centre.z });
      try { stick.clearVelocity(); } catch { /* not every build has it */ }
      await system.waitTicks(8);
      seen.item = { ...read(), at: stick.isValid ? stick.location : undefined };
      judge(mobsOnly ? "plate_item_ignored" : "plate_item", !mobsOnly, seen.item);
      if (stick.isValid) stick.remove();
      await system.waitTicks(34);
      for (const e of itemsNear(at)) e.remove();
      dim.runCommand(`setblock ${at.x} ${at.y} ${at.z} air destroy`);
      await system.waitTicks(10);
      seen.after_break = dim.getBlock(at)?.typeId;
      const got = [];
      for (const e of itemsNear(at)) {
        const stack = e.getComponent("minecraft:item")?.itemStack;
        if (stack) got.push({ item: stack.typeId, count: stack.amount });
        e.remove();
      }
      seen.drop = got;
      if (expect) {
        const verdict = dropVerdict(expect, got);
        if (verdict.ok) tally.record("plate_drop", id, true);
        else fail("plate_drop", id, verdict.problems.join("; "));
      }
      dim.getBlock(beside).setPermutation(BlockPermutation.resolve("minecraft:air"));
    } catch (err) {
      fail("plate", id, describe(err));
    }
    say("PLATE", seen);
  }

  // button: one button at a time (#280)
  const BUTTONS = CHECKS.buttons ?? [];
  for (let i = 0; i < BUTTONS.length; i++) {
    const { id, powered, ticks, arrows, event, expect } = BUTTONS[i];
    const at = buttonSlot(i);
    const below = { x: at.x, y: at.y - 1, z: at.z };
    const beside = { x: at.x + 1, y: at.y, z: at.z };
    const seen = { id, ticks, arrows };
    const read = () => ({
      powered: dim.getBlock(at)?.permutation.getState(powered),
      lamp: dim.getBlock(beside)?.typeId === "minecraft:lit_redstone_lamp",
    });
    const judge = (check, want, state, lamp) => {
      const verdict = plateVerdict(want, { powered: state.powered });
      if (verdict.ok) tally.record(check, id, true);
      else fail(check, id, verdict.problems.join("; "));
      if (lamp) {
        const lit = plateVerdict(want, { powered: want, lamp: state.lamp });
        if (lit.ok) tally.record(`${check}_redstone`, id, true);
        else fail(`${check}_redstone`, id, lit.problems.join("; "));
      }
    };
    try {
      for (const e of itemsNear(at)) e.remove();
      dim.getBlock(below).setPermutation(BlockPermutation.resolve("minecraft:stone"));
      dim.getBlock(beside).setPermutation(BlockPermutation.resolve("minecraft:redstone_lamp"));
      let placed;
      try {
        placed = BlockPermutation.resolve(id, { "minecraft:block_face": "up" });
      } catch {
        placed = BlockPermutation.resolve(id);
      }
      dim.getBlock(at).setPermutation(placed);
      await system.waitTicks(4);
      seen.placed = dim.getBlock(at)?.typeId;
      if (seen.placed !== id) {
        fail("button_place", id, `reads back as ${seen.placed}`);
        say("BUTTON", seen);
        continue;
      }
      tally.record("button_place", id, true);
      seen.idle = read();
      judge("button_idle", false, seen.idle, false);
      dim.runCommand(`scriptevent ${event} ${at.x} ${at.y} ${at.z}`);
      await system.waitTicks(2);
      seen.pressed = read();
      judge("button_press", true, seen.pressed, true);
      if (ticks > 6) {
        await system.waitTicks(ticks - 6);
        seen.held = read();
        judge("button_hold", true, seen.held, false);
        await system.waitTicks(10);
      } else {
        await system.waitTicks(ticks + 4);
      }
      seen.released = read();
      judge("button_release", false, seen.released, true);
      // Reported only: an arrow flying down onto it.
      try {
        const arrow = dim.spawnEntity("minecraft:arrow", { x: at.x + 0.5, y: at.y + 1.5, z: at.z + 0.5 });
        arrow.applyImpulse({ x: 0, y: -1.5, z: 0 });
        await system.waitTicks(6);
        seen.arrow = read();
        if (arrow.isValid) arrow.remove();
        await system.waitTicks(ticks + 4);
      } catch (err) {
        seen.arrow = { error: describe(err) };
      }
      for (const e of itemsNear(at)) e.remove();
      dim.runCommand(`setblock ${at.x} ${at.y} ${at.z} air destroy`);
      await system.waitTicks(10);
      seen.after_break = dim.getBlock(at)?.typeId;
      const got = [];
      for (const e of itemsNear(at)) {
        const stack = e.getComponent("minecraft:item")?.itemStack;
        if (stack) got.push({ item: stack.typeId, count: stack.amount });
        e.remove();
      }
      seen.drop = got;
      if (expect) {
        const verdict = dropVerdict(expect, got);
        if (verdict.ok) tally.record("button_drop", id, true);
        else fail("button_drop", id, verdict.problems.join("; "));
      }
      dim.getBlock(beside).setPermutation(BlockPermutation.resolve("minecraft:air"));
    } catch (err) {
      fail("button", id, describe(err));
    }
    say("BUTTON", seen);
  }

  // gate: one fence gate at a time (#367)
  const GATES = CHECKS.gates ?? [];
  for (let i = 0; i < GATES.length; i++) {
    const { id, states, event, wall, expect } = GATES[i];
    const at = gateSlot(i);
    const beside = { x: at.x + 1, y: at.y, z: at.z };
    const seen = { id };
    const read = () => {
      const perm = dim.getBlock(at).permutation;
      return {
        facing: perm.getState("minecraft:cardinal_direction"), open: perm.getState(states.open),
        powered: perm.getState(states.powered), in_wall: perm.getState(states.in_wall),
      };
    };
    const judge = (check, want, state) => {
      const verdict = gateVerdict(want, state);
      if (verdict.ok) tally.record(check, id, true);
      else fail(check, id, verdict.problems.join("; "));
    };
    try {
      for (const e of itemsNear(at)) e.remove();
      dim.getBlock(at).setPermutation(BlockPermutation.resolve(id));
      await system.waitTicks(2);
      seen.placed = dim.getBlock(at)?.typeId;
      if (seen.placed !== id) {
        fail("gate_place", id, `reads back as ${seen.placed}`);
        say("GATE", seen);
        continue;
      }
      tally.record("gate_place", id, true);
      seen.before = read();
      judge("gate_idle", { open: false, powered: false, in_wall: false }, seen.before);
      // A player facing the gate (looking opposite to its facing) opens it: it turns away.
      const facing = seen.before.facing;
      dim.runCommand(`scriptevent ${event} ${at.x} ${at.y} ${at.z} ${OPPOSITE[facing]}`);
      await system.waitTicks(2);
      seen.used = read();
      judge("gate_use_open", { open: true, facing: OPPOSITE[facing] }, seen.used);
      dim.runCommand(`scriptevent ${event} ${at.x} ${at.y} ${at.z} ${facing}`);
      await system.waitTicks(2);
      seen.closed = read();
      judge("gate_use_close", { open: false, facing: OPPOSITE[facing] }, seen.closed);
      dim.getBlock(beside).setPermutation(BlockPermutation.resolve("minecraft:redstone_block"));
      await system.waitTicks(4);
      seen.powered = read();
      judge("gate_power", { open: true, powered: true }, seen.powered);
      dim.getBlock(beside).setPermutation(BlockPermutation.resolve("minecraft:air"));
      await system.waitTicks(4);
      seen.unpowered = read();
      judge("gate_unpower", { open: false, powered: false }, seen.unpowered);
      for (const e of itemsNear(at)) e.remove();
      dim.runCommand(`setblock ${at.x} ${at.y} ${at.z} air destroy`);
      await system.waitTicks(10);
      seen.after_break = dim.getBlock(at)?.typeId;
      const got = [];
      for (const e of itemsNear(at)) {
        const stack = e.getComponent("minecraft:item")?.itemStack;
        if (stack) got.push({ item: stack.typeId, count: stack.amount });
        e.remove();
      }
      seen.drop = got;
      if (expect) {
        const verdict = dropVerdict(expect, got);
        if (verdict.ok) tally.record("gate_drop", id, true);
        else fail("gate_drop", id, verdict.problems.join("; "));
      }
      // Placed beside a wall across it (the default facing's side): lowered.
      const across = facing === "north" || facing === "south"
        ? { x: at.x - 1, y: at.y, z: at.z } : { x: at.x, y: at.y, z: at.z - 1 };
      dim.getBlock(across).setPermutation(BlockPermutation.resolve(wall));
      dim.getBlock(at).setPermutation(BlockPermutation.resolve(id));
      await system.waitTicks(2);
      seen.walled = read();
      judge("gate_in_wall", { in_wall: true }, seen.walled);
      dim.getBlock(at).setPermutation(BlockPermutation.resolve("minecraft:air"));
      dim.getBlock(across).setPermutation(BlockPermutation.resolve("minecraft:air"));
    } catch (err) {
      fail("gate", id, describe(err));
    }
    say("GATE", seen);
  }

  // ore: each ore feature placed into a cube of what it replaces (#281)
  const ores = CHECKS.ores ?? [];
  const countIn = async (where, x0, z0, size, y0, y1, ids) => {
    const counts = {};
    let n = 0;
    for (let x = x0; x < x0 + size; x++) {
      for (let z = z0; z < z0 + size; z++) {
        for (let y = y0; y <= y1; y++) {
          const id = where.getBlock({ x, y, z })?.typeId;
          if (ids.includes(id)) counts[id] = (counts[id] ?? 0) + 1;
          if (++n % 8192 === 0) await system.waitTicks(1);
        }
      }
    }
    return counts;
  };
  for (let i = 0; i < ores.length; i++) {
    const ore = ores[i];
    const at = oreSlot(i);
    const seen = { rule: ore.rule, feature: ore.feature };
    try {
      const top = at.y + ORE_CUBE - 1;
      dim.runCommand(`fill ${at.x} ${at.y} ${at.z} ${at.x + ORE_CUBE - 1} ${top} ${at.z + ORE_CUBE - 1} ${ore.replaces[0]}`);
      try {
        seen.placed = dim.placeFeature(ore.feature, { x: at.x + 3, y: at.y + 3, z: at.z + 3 }, true);
      } catch (err) {
        seen.placed = false;
        seen.error = describe(err);
      }
      seen.counts = await countIn(dim, at.x, at.z, ORE_CUBE, at.y, top, ore.blocks);
      seen.verdict = oreVerdict(seen.counts, ore.blocks);
    } catch (err) {
      seen.error = describe(err);
    }
    say("ORE", seen);
  }
  // ore_generate: the world generates each rule's ore in fresh chunks of its
  // dimension (the Overworld only in a generated world: the check world is flat)
  const generated = CHECKS.world === "default";
  const genDims = [...new Set(ores.map((o) => o.dimension).filter((d) => d && (d !== "overworld" || generated)))];
  for (const name of genDims) {
    const there = world.getDimension(name);
    const g = GEN_ORIGIN;
    const seen = { dimension: name };
    try {
      there.runCommand(`tickingarea add ${g} 0 ${g} ${g + GEN_SIZE - 1} 0 ${g + GEN_SIZE - 1} portkit_ore_${name}`);
      let ready = false;
      for (let tick = 0; tick < 1200 && !ready; tick += 10) {
        try {
          ready = Boolean(there.getBlock({ x: g, y: 0, z: g }) && there.getBlock({ x: g + GEN_SIZE - 1, y: 0, z: g + GEN_SIZE - 1 }));
        } catch {
          ready = false;
        }
        if (!ready) await system.waitTicks(10);
      }
      if (!ready) throw new Error(`the ${name} ticking area never loaded`);
      await system.waitTicks(40);
      const range = there.heightRange;
      seen.height = [range.min, range.max];
      for (const ore of ores.filter((o) => o.dimension === name)) {
        const span = scanRange(ore.y, range.min, range.max - 1);
        const row = { rule: ore.rule, y: span };
        if (span === null) {
          fail("ore_generate", ore.rule, `height range ${ore.y} is outside the ${name}`);
        } else {
          const hosts = ore.hosts ?? [];
          row.counts = await countIn(there, g, g, GEN_SIZE, span[0], span[1], [...ore.blocks, ...hosts]);
          const verdict = generateVerdict(row.counts, ore.blocks, hosts);
          if (verdict.ok) tally.record("ore_generate", ore.rule, true);
          else if (verdict.skipped) row.skipped = verdict.problems.join("; ");
          else fail("ore_generate", ore.rule, verdict.problems.join("; "));
        }
        say("ORE_GENERATE", row);
      }
    } catch (err) {
      fail("ore_generate", name, describe(err));
    }
    say("ORE_DIMENSION", seen);
  }

  // geode_generate (#281 slice 3): the check pack's test-only copy of each
  // geode rule places the converted geode feature once per chunk; fresh chunks
  // of its dimension are loaded and the blocks only a geode lays (its inner
  // and alternate inner layer) counted, at least one asserted, with the
  // minecraft:block_face states of the inner placements found reported.
  const geodes = CHECKS.geodes ?? [];
  const geodeDims = [...new Set(geodes.map((o) => o.dimension).filter((d) => d && (d !== "overworld" || generated)))];
  for (const name of geodeDims) {
    const there = world.getDimension(name);
    const g = GEN_ORIGIN + 2 * GEN_SIZE;
    const seen = { dimension: name, origin: g };
    try {
      there.runCommand(`tickingarea add ${g} 0 ${g} ${g + GEN_SIZE - 1} 0 ${g + GEN_SIZE - 1} portkit_geode_${name}`);
      let ready = false;
      for (let tick = 0; tick < 1200 && !ready; tick += 10) {
        try {
          ready = Boolean(there.getBlock({ x: g, y: 0, z: g }) && there.getBlock({ x: g + GEN_SIZE - 1, y: 0, z: g + GEN_SIZE - 1 }));
        } catch {
          ready = false;
        }
        if (!ready) await system.waitTicks(10);
      }
      if (!ready) throw new Error(`the ${name} ticking area never loaded`);
      await system.waitTicks(40);
      const range = there.heightRange;
      for (const geode of geodes.filter((o) => o.dimension === name)) {
        const span = scanRange(geode.y, range.min, range.max - 1);
        const row = { rule: geode.rule, check_rule: geode.check_rule, y: span };
        if (span === null) {
          fail("geode_generate", geode.rule, `height range ${geode.y} is outside the ${name}`);
        } else {
          const counts = {};
          const faces = {};
          let n = 0;
          for (let x = g; x < g + GEN_SIZE; x++) {
            for (let z = g; z < g + GEN_SIZE; z++) {
              for (let y = span[0]; y <= span[1]; y++) {
                const block = there.getBlock({ x, y, z });
                const id = block?.typeId;
                if (geode.blocks.includes(id) || geode.buds.includes(id)) {
                  counts[id] = (counts[id] ?? 0) + 1;
                  if (geode.buds.includes(id)) {
                    let face;
                    try {
                      face = block.permutation.getState("minecraft:block_face");
                    } catch {
                      face = undefined;
                    }
                    const key = `${id}=${face ?? "none"}`;
                    faces[key] = (faces[key] ?? 0) + 1;
                  }
                }
                if (++n % 8192 === 0) await system.waitTicks(1);
              }
            }
          }
          row.counts = counts;
          row.faces = faces;
          const verdict = oreVerdict(counts, geode.blocks);
          if (verdict.ok) tally.record("geode_generate", geode.rule, true);
          else fail("geode_generate", geode.rule, verdict.problems.join("; "));
        }
        say("GEODE_GENERATE", row);
      }
    } catch (err) {
      fail("geode_generate", name, describe(err));
    }
    say("GEODE_DIMENSION", seen);
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
