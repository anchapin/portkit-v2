// The fixed block drop runtime (src/portkit/runtime/block_drops.js on block_drops_core.js), offline under node.
// Run: node --import tests/js/register.mjs --test tests/js/block_drops.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";

import { registerBlockDrops } from "../../src/portkit/runtime/block_drops.js";
import { between, rollCount } from "../../src/portkit/runtime/block_drops_core.js";
import { _dimension, _fire, _permutation, _player, ItemStack } from "@minecraft/server";

// Quark 4.1-487 inject/blocks/glass: uniform 2-4, Fortune uniform_bonus_count x1, limit 1-4, not with Silk Touch.
const ROW = { item: "quark:clear_shard", no_silk_touch: true, steps: [
  { op: "set", min: 2, max: 4 }, { op: "fortune_uniform", multiplier: 1 }, { op: "limit", min: 1, max: 4 }] };

const seq = (...xs) => { let i = 0; return () => xs[i++ % xs.length]; };

test("between is a uniform integer over [lo, hi]", () => {
  assert.equal(between(2, 4, () => 0), 2);
  assert.equal(between(2, 4, () => 0.999), 4);
  assert.equal(between(3, 3, () => 0.5), 3);
});

test("rollCount follows Java's order: set, Fortune bonus, then the limit", () => {
  assert.equal(rollCount(ROW, 0, 0, () => 0), 2);
  assert.equal(rollCount(ROW, 0, 0, () => 0.999), 4);
  // Fortune III can't push it past the limit of 4.
  assert.equal(rollCount(ROW, 3, 0, () => 0.999), 4);
  // 2 + a bonus of 1 (of 0..1 at Fortune I).
  assert.equal(rollCount(ROW, 1, 0, seq(0, 0.9)), 3);
  // Never more than Java's 4, whatever the roll.
  for (let f = 0; f <= 5; f++) for (const r of [0, 0.3, 0.6, 0.999]) assert.ok(rollCount(ROW, f, 0, () => r) <= 4);
});

test("Silk Touch gives none, and an unknown step gives none rather than a guess", () => {
  assert.equal(rollCount(ROW, 0, 1, () => 0.5), 0);
  assert.equal(rollCount({ item: "x", steps: [{ op: "mystery" }] }, 0, 0, () => 0.5), 0);
});

test("a player's break of a listed vanilla block spawns the drop; Creative and other blocks don't", () => {
  registerBlockDrops({ blocks: { "minecraft:glass": [ROW] } });
  const dim = _dimension();
  const block = { location: { x: 1, y: 2, z: 3 }, center: () => ({ x: 1.5, y: 2.5, z: 3.5 }) };
  const event = (id, player, tool) => ({ brokenBlockPermutation: _permutation(id), player, block, dimension: dim,
    itemStackBeforeBreak: tool });
  _fire("after", "playerBreakBlock", event("minecraft:glass", _player(dim, undefined), undefined));
  assert.equal(dim.spawned.length, 1);
  assert.equal(dim.spawned[0].stack.typeId, "quark:clear_shard");
  assert.ok(dim.spawned[0].stack.amount >= 2 && dim.spawned[0].stack.amount <= 4);
  _fire("after", "playerBreakBlock", event("minecraft:glass", _player(dim, undefined, { creative: true }), undefined));
  _fire("after", "playerBreakBlock", event("minecraft:stone", _player(dim, undefined), undefined));
  const silk = new ItemStack("minecraft:iron_pickaxe");
  silk._enchantments.push({ id: "silk_touch", level: 1 });
  _fire("after", "playerBreakBlock", event("minecraft:glass", _player(dim, silk), silk));
  assert.equal(dim.spawned.length, 1);
});
