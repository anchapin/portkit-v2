// The fixed toggle runtime (src/portkit/runtime/toggle.js), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/toggle.test.mjs
// (tests/test_facing_boolean.py runs it with PORTKIT_TOGGLE_TABLE set to a data
// table the converter just generated; without it a small table here is used.)
import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import { flipped, registerToggles } from "../../src/portkit/runtime/toggle.js";
import { _permutation, _startup } from "@minecraft/server";

const FALLBACK = {
  component: "examplemod:portkit_toggle",
  blocks: { "examplemod:toggle_lamp": "examplemod:lit" },
};

async function loadTable() {
  const path = process.env.PORTKIT_TOGGLE_TABLE;
  if (!path) return FALLBACK;
  return (await import(pathToFileURL(path).href)).default;
}

const table = await loadTable();
registerToggles(table);
const component = _startup()[table.component];

function block(typeId, states) {
  return {
    typeId,
    permutation: _permutation(typeId, { "minecraft:cardinal_direction": "east", ...states }),
    setPermutation(p) { this.permutation = p; },
  };
}

test("the component is registered under the table's name", () => {
  assert.ok(component && component.onPlayerInteract);
});

test("each use flips the table's state and keeps the others", () => {
  for (const [id, state] of Object.entries(table.blocks)) {
    const b = block(id, { [state]: false });
    component.onPlayerInteract({ block: b, player: {} });
    assert.equal(b.permutation.getState(state), true);
    assert.equal(b.permutation.getState("minecraft:cardinal_direction"), "east");
    component.onPlayerInteract({ block: b, player: {} });
    assert.equal(b.permutation.getState(state), false);
  }
});

test("a block outside the table, or without the state, is left alone", () => {
  const other = block("examplemod:vase", { "examplemod:lit": false });
  assert.equal(flipped(table, other), null);
  component.onPlayerInteract({ block: other, player: {} });
  assert.equal(other.permutation.getState("examplemod:lit"), false);
  const [id] = Object.keys(table.blocks);
  assert.equal(flipped(table, block(id, {})), null);
});
