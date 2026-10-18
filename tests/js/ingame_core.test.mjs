// The in-game check pack's pure core (#238).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  PAIRED_Y, PLATE_Y, TRAPDOOR_Y, doorVerdict, pairedSlot, pairedVerdict, plateSlot, plateVerdict,
  trapdoorSlot, trapdoorVerdict,
  AREA, CONNECTION_STATES, DROP_BATCH, DROP_Y, Tally, connectionSlot, connectionVerdict, containerVerdict,
  describe, dropSlot, dropVerdict, line, slot,
} from "../../src/portkit/ingame/runtime/ingame_core.js";

test("slots stay two apart inside the ticking area", () => {
  const seen = new Set();
  for (let i = 0; i < 2048; i++) {
    const { x, y, z } = slot(i);
    assert.ok(x >= 0 && x < AREA && z >= 0 && z < AREA);
    assert.equal(x % 2, 0);
    assert.equal(z % 2, 0);
    const key = `${x},${y},${z}`;
    assert.ok(!seen.has(key));
    seen.add(key);
  }
  assert.deepEqual(slot(0), { x: 0, y: 0, z: 0 });
  assert.deepEqual(slot(1), { x: 2, y: 0, z: 0 });
  assert.deepEqual(slot(32), { x: 0, y: 0, z: 2 });
  assert.deepEqual(slot(1024), { x: 0, y: 2, z: 0 });
  assert.deepEqual(slot(0, 100), { x: 0, y: 100, z: 0 });
});

const states = (n, e, s, w) => Object.fromEntries(CONNECTION_STATES.map((k, i) => [k, [n, e, s, w][i]]));

test("connection verdict: joined east, not to air; north reported only", () => {
  assert.deepEqual(connectionVerdict(states(true, true, false, false)), { ok: true, problems: [] });
  assert.deepEqual(connectionVerdict(states(false, true, false, false)), { ok: true, problems: [] });
  assert.equal(connectionVerdict(states(true, false, false, false)).ok, false);
  assert.equal(connectionVerdict(states(true, true, true, false)).ok, false);
  const missing = connectionVerdict(states(undefined, true, false, false));
  assert.deepEqual(missing.problems, ["minecraft:connection_north missing"]);
});

test("container verdict", () => {
  assert.equal(containerVerdict(27, 27).ok, true);
  assert.deepEqual(containerVerdict(27, 9).problems, ["9 slots, expected 27"]);
  assert.deepEqual(containerVerdict(27, undefined).problems, ["no minecraft:inventory component"]);
});

test("tally and lines", () => {
  const t = new Tally();
  t.record("place", "a:b", true);
  t.record("place", "a:c", false, "x");
  assert.deepEqual(t.summary(), { checks: { place: { run: 2, failed: 1 } }, failed: 1 });
  assert.deepEqual(t.failures, [{ check: "place", id: "a:c", detail: "x" }]);
  assert.equal(line("DONE", {}), "PORTKIT-INGAME DONE {}");
  assert.equal(describe(new TypeError("no")), "TypeError: no");
});

test("connection slots: neighbours inside the area, air south and west of each block", () => {
  const used = new Map();
  const blocks = [];
  for (let i = 0; i < 512; i++) {
    const { x, y, z } = connectionSlot(i);
    blocks.push({ x, y, z });
    for (const [px, pz, what] of [[x, z, "block"], [x + 1, z, "east"], [x, z - 1, "stone"]]) {
      assert.ok(px >= 0 && px < AREA && pz >= 0 && pz < AREA, `${i}: ${px},${pz}`);
      const key = `${px},${y},${pz}`;
      assert.ok(!used.has(key), `${i}: ${key} taken`);
      used.set(key, what);
    }
  }
  for (const { x, y, z } of blocks) {
    assert.ok(!used.has(`${x},${y},${z + 1}`), "south is not air");
    assert.ok(!used.has(`${x - 1},${y},${z}`), "west is not air");
  }
  assert.deepEqual(connectionSlot(0), { x: 0, y: 100, z: 1 });
  assert.deepEqual(connectionSlot(256), { x: 0, y: 102, z: 1 });
});

test("drop slots: eight apart, inside the ticking area, one batch reused", () => {
  const seen = new Set();
  for (let i = 0; i < DROP_BATCH; i++) {
    const { x, y, z } = dropSlot(i);
    assert.ok(x >= 0 && x < AREA && z >= 0 && z < AREA);
    assert.equal(y, DROP_Y);
    seen.add(`${x},${z}`);
  }
  assert.equal(seen.size, DROP_BATCH);
  assert.deepEqual(dropSlot(0), dropSlot(DROP_BATCH));
  assert.equal(dropSlot(1).x - dropSlot(0).x, 8);
});

test("drop verdict: counts summed per item, extras and shortfalls fail", () => {
  const root = [{ item: "demo:living_root", count: 4 }];
  assert.deepEqual(dropVerdict(root, [{ item: "demo:living_root", count: 3 }, { item: "demo:living_root", count: 1 }]),
    { ok: true, problems: [] });
  assert.deepEqual(dropVerdict(root, [{ item: "demo:root", count: 1 }]).problems,
    ["dropped 0 demo:living_root, expected 4", "dropped 1 demo:root, expected 0"]);
  assert.deepEqual(dropVerdict([], []), { ok: true, problems: [] });
  assert.equal(dropVerdict([], [{ item: "minecraft:dirt", count: 1 }]).ok, false);
});

test("paired slots: eight apart in x and z, a layer four up every 64, inside the area", () => {
  const seen = new Set();
  for (let i = 0; i < 128; i++) {
    const at = pairedSlot(i);
    assert.ok(at.x >= 0 && at.x + 1 < AREA && at.z >= 0 && at.z < AREA, JSON.stringify(at));
    assert.ok(!seen.has(`${at.x},${at.y},${at.z}`));
    seen.add(`${at.x},${at.y},${at.z}`);
  }
  assert.deepEqual(pairedSlot(0), { x: 2, y: PAIRED_Y, z: 2 });
  assert.deepEqual(pairedSlot(1), { x: 10, y: PAIRED_Y, z: 2 });
  assert.equal(pairedSlot(64).y, PAIRED_Y + 4);
});

test("paired verdict: both parts the block, part 0 below part 1", () => {
  assert.deepEqual(pairedVerdict("d:x", { typeId: "d:x", part: 0 }, { typeId: "d:x", part: 1 }), { ok: true, problems: [] });
  const lone = pairedVerdict("d:x", { typeId: "d:x", part: 0 }, { typeId: "minecraft:air", part: undefined });
  assert.equal(lone.ok, false);
  assert.match(lone.problems[0], /upper reads minecraft:air/);
});

test("door verdict: both halves open and powered together", () => {
  assert.equal(doorVerdict(true, [{ open: true, powered: true }, { open: true, powered: true }]).ok, true);
  const half = doorVerdict(false, [{ open: false, powered: false }, { open: true, powered: false }]);
  assert.deepEqual(half.problems, ["upper open=true, expected false"]);
});

test("trapdoor slots: the paired layout on their own layers, clear of the paired and drop layers", () => {
  assert.deepEqual(trapdoorSlot(0), { x: 2, y: TRAPDOOR_Y, z: 2 });
  assert.equal(trapdoorSlot(64).y, TRAPDOOR_Y + 4);
  for (let i = 0; i < 256; i++) {
    const at = trapdoorSlot(i);
    assert.ok(at.x + 1 < AREA && at.z < AREA && at.y < DROP_Y, JSON.stringify(at));
  }
  assert.ok(TRAPDOOR_Y > pairedSlot(255).y + 1);
});

test("trapdoor verdict: open and powered both as wanted", () => {
  assert.deepEqual(trapdoorVerdict(true, { open: true, powered: true }), { ok: true, problems: [] });
  assert.deepEqual(trapdoorVerdict(false, { open: true, powered: false }).problems, ["open=true, expected false"]);
  assert.deepEqual(trapdoorVerdict(true, { open: undefined, powered: true }).problems, ["open=undefined, expected true"]);
});

test("ore cubes sit eight apart inside the ticking area, below the paired layer (#281)", async () => {
  const { ORE_CUBE, ORE_SPACING, ORE_Y, oreSlot } = await import("../../src/portkit/ingame/runtime/ingame_core.js");
  const seen = new Set();
  for (let i = 0; i < 64; i++) {
    const { x, y, z } = oreSlot(i);
    assert.ok(x >= 0 && x + ORE_CUBE <= AREA && z >= 0 && z + ORE_CUBE <= AREA);
    assert.equal(y, ORE_Y);
    assert.ok(ORE_CUBE < ORE_SPACING);
    seen.add(`${x},${z}`);
  }
  assert.equal(seen.size, 64);
  assert.ok(ORE_Y + ORE_CUBE <= PAIRED_Y);
});

test("ore scan range is the rule's extent clipped to the dimension; verdict needs one ore", async () => {
  const { oreVerdict, scanRange } = await import("../../src/portkit/ingame/runtime/ingame_core.js");
  assert.deepEqual(scanRange([8, 32], 0, 127), [8, 32]);
  assert.deepEqual(scanRange([8, 247], 0, 127), [8, 127]);
  assert.deepEqual(scanRange([32, 8], 0, 127), [8, 32]);
  assert.equal(scanRange([200, 247], 0, 127), null);
  assert.equal(oreVerdict({ "a:ore": 3 }, ["a:ore"]).ok, true);
  assert.equal(oreVerdict({ "a:deep": 1 }, ["a:ore", "a:deep"]).ok, true);
  assert.deepEqual(oreVerdict({}, ["a:ore"]), { ok: false, problems: ["none of a:ore found"] });
  assert.equal(oreVerdict(undefined, ["a:ore"]).ok, false);
  const { generateVerdict } = await import("../../src/portkit/ingame/runtime/ingame_core.js");
  assert.deepEqual(generateVerdict({ "a:ore": 2, "minecraft:stone": 9 }, ["a:ore"], ["minecraft:stone"]),
    { ok: true, problems: [], skipped: false });
  assert.deepEqual(generateVerdict({ "minecraft:stone": 9 }, ["a:ore"], ["minecraft:stone"]),
    { ok: false, problems: ["none of a:ore found"], skipped: false });
  assert.deepEqual(generateVerdict({}, ["a:ore"], ["minecraft:calcite"]),
    { ok: false, skipped: true, problems: ["none of minecraft:calcite in the scanned range"] });
  assert.equal(generateVerdict({}, ["a:ore"], []).skipped, false);
});

test("plate slots: the paired layout on their own layers, between the trapdoors and the drops", () => {
  assert.deepEqual(plateSlot(0), { x: 2, y: PLATE_Y, z: 2 });
  assert.equal(plateSlot(64).y, PLATE_Y + 4);
  for (let i = 0; i < 128; i++) {
    const at = plateSlot(i);
    // the stone below, the lamp beside, clear of the drop layer and of the trapdoors
    assert.ok(at.x + 1 < AREA && at.z < AREA && at.y < DROP_Y, JSON.stringify(at));
    assert.ok(at.y - 1 > trapdoorSlot(127).y, JSON.stringify(at));
  }
});

test("plate verdict: pressed as wanted, and the lamp when asked", () => {
  assert.deepEqual(plateVerdict(true, { powered: true, lamp: true }), { ok: true, problems: [] });
  assert.deepEqual(plateVerdict(false, { powered: false }), { ok: true, problems: [] });
  assert.deepEqual(plateVerdict(true, { powered: true, lamp: false }).problems, ["lamp lit=false, expected true"]);
  assert.deepEqual(plateVerdict(false, { powered: undefined }).problems, ["powered=undefined, expected false"]);
});
