// portkit runtime: the pure rules of a drop a mod's loot modifier adds to a
// vanilla block (#280). No imports; tested with node
// (tests/js/block_drops_core.test.mjs). The Bedrock binding is block_drops.js.
//
// Java (NeoForge 1.21.1 AddTableLootModifier#doApply) rolls the added table
// with the block's own loot context and adds what it gives to what the block
// drops. portkit converts only tables whose every pool is one roll of one
// item entry (converters/loot_modifiers.py), so a row here is that entry:
//   { item, no_silk_touch, steps: [...] }
// no_silk_touch: the entry's condition is `inverted(match_tool silk_touch >= 1)`.
// steps, in Java's order (the entry's functions, then the pool's):
//   { op: "set", min, max }      minecraft:set_count, a constant (min == max)
//                                or minecraft:uniform with integer bounds:
//                                a uniform integer in [min, max]
//   { op: "fortune_uniform", multiplier }
//                                minecraft:apply_bonus, minecraft:fortune,
//                                minecraft:uniform_bonus_count: with Fortune
//                                level L > 0, count += a uniform integer in
//                                [0, multiplier * L]
//   { op: "limit", min, max }    minecraft:limit_count: clamp (either bound
//                                may be null)
// explosion_decay and survives_explosion only act when an explosion broke the
// block; a player's break never is one, so the converter drops them.

/** A uniform integer in [lo, hi] from `random` (a () => [0, 1) function). */
export function between(lo, hi, random) {
  if (hi <= lo) return lo;
  return lo + Math.floor(random() * (hi - lo + 1));
}

/** How many of the row's item one roll gives (0: none). */
export function rollCount(row, fortune, silkTouch, random) {
  if (row.no_silk_touch && silkTouch > 0) return 0;
  let count = 1;
  for (const step of row.steps ?? []) {
    if (step.op === "set") count = between(step.min, step.max, random);
    else if (step.op === "fortune_uniform") {
      if (fortune > 0) count += between(0, step.multiplier * fortune, random);
    } else if (step.op === "limit") {
      if (step.min !== null && step.min !== undefined) count = Math.max(count, step.min);
      if (step.max !== null && step.max !== undefined) count = Math.min(count, step.max);
    } else return 0; // a step this runtime doesn't know adds nothing rather than a guess
  }
  return count > 0 ? count : 0;
}
