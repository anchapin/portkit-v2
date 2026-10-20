// The fixed button runtime (src/portkit/runtime/button.js on button_core.js), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/button.test.mjs
// (tests/test_buttons.py runs it with PORTKIT_BUTTON_TABLE set to a data
// table the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import { registerButtons } from "../../src/portkit/runtime/button.js";
import { arrowHit, check, inCell, use } from "../../src/portkit/runtime/button_core.js";
import { _fire, _permutation, _runTimeouts, _startup, system, world } from "@minecraft/server";

const FALLBACK = {
  component: "examplemod:portkit_button",
  powered: "examplemod:powered",
  press_event: "portkit:button_press",
  buttons: {
    "examplemod:oak_knob": { ticks: 30, arrows: true, on_sound: "random.wood_click", off_sound: "random.wood_click",
      on_pitch: 0.6, off_pitch: 0.5 },
    "examplemod:stone_knob": { ticks: 20, arrows: false, on_sound: "random.stone_click",
      off_sound: "random.stone_click", on_pitch: 0.6, off_pitch: 0.5 },
  },
};

async function loadTable() {
  const path = process.env.PORTKIT_BUTTON_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerButtons(table);
const component = _startup()[table.component];
const ids = Object.keys(table.buttons);

// -- the pure rules ----------------------------------------------------------

test("use: an unpowered button presses and schedules its release; a powered one does nothing", () => {
  assert.deepEqual(use(false, 30), { powered: true, sound: "on", schedule: 30 });
  assert.equal(use(true, 30), null);
});

test("checkPressed: released without an arrow, held (and rescheduled) with one where arrows count", () => {
  assert.deepEqual(check(true, false, true, 30), { powered: false, sound: "off", schedule: null });
  assert.deepEqual(check(true, true, true, 30), { powered: true, sound: null, schedule: 30 });
  assert.deepEqual(check(true, true, false, 20), { powered: false, sound: "off", schedule: null });
});

test("an arrow presses only an unpowered button its set type lets arrows press", () => {
  assert.deepEqual(arrowHit(false, true, 30), { powered: true, sound: "on", schedule: 30 });
  assert.equal(arrowHit(true, true, 30), null);
  assert.equal(arrowHit(false, false, 20), null);
});

test("inCell", () => {
  assert.ok(inCell({ x: 1, y: 2, z: 3 }, { x: 1.5, y: 2.9, z: 3.0 }, 0));
  assert.ok(!inCell({ x: 1, y: 2, z: 3 }, { x: 2.3, y: 2.5, z: 3.5 }, 0.1));
});

// -- the binding -------------------------------------------------------------

function place(typeId, at, entities = []) {
  const sounds = [];
  const dim = {
    id: "minecraft:overworld",
    playSound: (id, _loc, opts) => sounds.push([id, opts?.pitch]),
    getEntities: () => entities,
    getBlock: () => block,
  };
  const block = {
    typeId, location: at, dimension: dim,
    permutation: _permutation(typeId, { [table.powered]: false }),
    setPermutation(p) { this.permutation = p; },
    center: () => ({ x: at.x + 0.5, y: at.y + 0.5, z: at.z + 0.5 }),
  };
  return { block, sounds, dim };
}
const powered = (b) => b.permutation.getState(table.powered);

test("the component takes a player's use and ticks", () => {
  assert.equal(typeof component.onPlayerInteract, "function");
  assert.equal(typeof component.onTick, "function");
});

for (const id of ids) {
  const b = table.buttons[id];
  test(`${id}: a use presses it for ${b.ticks} ticks with its clicks`, () => {
    _runTimeouts();
    const { block, sounds } = place(id, { x: 0, y: 64, z: 0 });
    component.onPlayerInteract({ block });
    assert.equal(powered(block), true);
    assert.deepEqual(sounds[0], [b.on_sound, b.on_pitch]);
    component.onPlayerInteract({ block });
    assert.equal(sounds.length, 1, "a powered button does nothing");
    assert.deepEqual(_runTimeouts(), [b.ticks]);
    assert.equal(powered(block), false);
    assert.deepEqual(sounds[1], [b.off_sound, b.off_pitch]);
  });

  test(`${id}: an arrow ${b.arrows ? "presses it and holds it while inside" : "doesn't press it"}`, () => {
    _runTimeouts();
    const arrow = { typeId: "minecraft:arrow", location: { x: 4.5, y: 64.5, z: 0.05 } };
    const { block } = place(id, { x: 4, y: 64, z: 0 }, [arrow]);
    _fire("after", "projectileHitBlock", { projectile: arrow, getBlockHit: () => ({ block }) });
    assert.equal(powered(block), b.arrows);
    if (!b.arrows) return;
    assert.deepEqual(_runTimeouts(), [b.ticks]);
    assert.equal(powered(block), true, "the arrow is still in it");
    block.dimension.getEntities = () => [];
    _runTimeouts();
    assert.equal(powered(block), false);
  });
}

test("a powered button whose timer a reload dropped is released by its tick", () => {
  _runTimeouts();
  const { block } = place(ids[0], { x: 8, y: 64, z: 0 });
  block.permutation = block.permutation.withState(table.powered, true);
  component.onTick({ block });
  assert.equal(powered(block), false);
});

test("the scriptevent presses the button at x y z", () => {
  _runTimeouts();
  const { block, dim } = place(ids[0], { x: 12, y: 64, z: 0 });
  _fire("system", "scriptEventReceive", { id: table.press_event, message: "12 64 0", sourceBlock: { dimension: dim } });
  assert.equal(powered(block), true);
  _fire("system", "scriptEventReceive", { id: "other:event", message: "12 64 0" });
  _runTimeouts();
  assert.equal(powered(block), false);
});

test("a block that is no longer a button is left alone", () => {
  const { block } = place("minecraft:air", { x: 0, y: 64, z: 0 });
  component.onPlayerInteract({ block });
  assert.equal(powered(block), false);
});
void world;
