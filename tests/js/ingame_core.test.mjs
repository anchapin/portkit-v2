// The in-game check pack's pure core (#238).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  AREA, CONNECTION_STATES, Tally, connectionVerdict, containerVerdict, describe, line, slot,
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
