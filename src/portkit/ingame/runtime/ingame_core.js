// Pure helpers for the in-game check pack (#238): no imports, tested with node
// (tests/js/ingame_core.test.mjs). The Bedrock binding is ingame.js.

// Every tagged line the pack prints starts with this, so the runner can tell
// its own output from the server's and from the content log.
export const TAG = "PORTKIT-INGAME";

// The ticking area the checks run in: chunks 0..3 by 0..3 (x, z 0..63).
export const AREA = 64;
// Blocks sit two apart so no two placed blocks touch (a block's own neighbour
// update must not decide another block's check).
export const SPACING = 2;
// The layer the placement grid starts on (air in a flat world) and the layers
// the connection and item checks use, above it.
export const PLACE_Y = 0;
export const CONNECTION_Y = 100;
export const ITEM_Y = 120;
// The drop check's layer (#299): each block on a stone floor, eight apart so
// what one block drops is never counted for another.
export const DROP_Y = 80;
export const DROP_SPACING = 8;
export const DROP_BATCH = (AREA / DROP_SPACING) ** 2;

const PER_ROW = AREA / SPACING;
const PER_LAYER = PER_ROW * PER_ROW;

/** Where the i-th placement goes: a grid two apart, a new layer every 1024. */
export function slot(i, y0 = PLACE_Y) {
  const inLayer = i % PER_LAYER;
  return {
    x: (inLayer % PER_ROW) * SPACING,
    y: y0 + Math.floor(i / PER_LAYER) * SPACING,
    z: Math.floor(inLayer / PER_ROW) * SPACING,
  };
}

/**
 * Where the i-th connection check goes: four apart both ways (room for the
 * same-kind neighbour to the east and the stone to the north, with air left
 * south and west of every checked block), starting at z = 1 so the stone
 * (z - 1) stays inside the ticking area; 256 a layer.
 */
export function connectionSlot(i) {
  const inLayer = i % 256;
  return {
    x: (inLayer % 16) * 4,
    y: CONNECTION_Y + Math.floor(i / 256) * 2,
    z: Math.floor(inLayer / 16) * 4 + 1,
  };
}

/** The four cardinal connection states (the `minecraft:connection` trait). */
export const CONNECTION_STATES = [
  "minecraft:connection_north",
  "minecraft:connection_east",
  "minecraft:connection_south",
  "minecraft:connection_west",
];

/**
 * The connection check's verdict. The block under test has a block of its own
 * kind to the east and air to the south and west; north is a vanilla stone
 * block, reported but not asserted (which blocks the trait joins to is
 * Bedrock's rule, not something portkit claims).
 * `states` maps state name -> value as read back, or undefined when absent.
 */
export function connectionVerdict(states) {
  const problems = [];
  for (const name of CONNECTION_STATES) {
    if (typeof states[name] !== "boolean") problems.push(`${name} missing`);
  }
  if (problems.length) return { ok: false, problems };
  if (states["minecraft:connection_east"] !== true) problems.push("east (same block) not connected");
  if (states["minecraft:connection_south"] !== false) problems.push("south (air) connected");
  if (states["minecraft:connection_west"] !== false) problems.push("west (air) connected");
  return { ok: problems.length === 0, problems };
}

/** Where the i-th block of a drop batch goes (64 a batch, reused per batch). */
export function dropSlot(i) {
  const k = i % DROP_BATCH;
  const per = AREA / DROP_SPACING;
  return { x: (k % per) * DROP_SPACING + 2, y: DROP_Y, z: Math.floor(k / per) * DROP_SPACING + 2 };
}

/**
 * The drop check's verdict (#299): what breaking the block left, as
 * [{item, count}] item entities, against what its loot table gives. Counts are
 * summed per item id; any item not expected, or a count off, fails.
 */
export function dropVerdict(expect, got) {
  const sum = (rows) => {
    const out = {};
    for (const { item, count } of rows) out[item] = (out[item] ?? 0) + count;
    return out;
  };
  const want = sum(expect);
  const have = sum(got);
  const problems = [];
  for (const item of Object.keys({ ...want, ...have }).sort()) {
    const w = want[item] ?? 0;
    const h = have[item] ?? 0;
    if (w !== h) problems.push(`dropped ${h} ${item}, expected ${w}`);
  }
  return { ok: problems.length === 0, problems };
}

// The paired check's layer (#296 multi_block doors and two-tall plants): eight
// apart like the drops (room for a redstone block beside each and its drop),
// a new layer four up every 64.
export const PAIRED_Y = 40;
export const PAIRED_PART = "minecraft:multi_block_part";

/** Where the i-th paired block's lower part goes. */
export function pairedSlot(i) {
  const per = AREA / DROP_SPACING;
  const k = i % (per * per);
  return {
    x: (k % per) * DROP_SPACING + 2,
    y: PAIRED_Y + Math.floor(i / (per * per)) * 4,
    z: Math.floor(k / per) * DROP_SPACING + 2,
  };
}

/**
 * Whether the two parts read back as one block: `lower` and `upper` are
 * {typeId, part} as read (part undefined when the state is absent).
 */
export function pairedVerdict(id, lower, upper) {
  const problems = [];
  if (lower.typeId !== id || lower.part !== 0) problems.push(`lower reads ${lower.typeId} part ${lower.part}`);
  if (upper.typeId !== id || upper.part !== 1) problems.push(`upper reads ${upper.typeId} part ${upper.part}`);
  return { ok: problems.length === 0, problems };
}

/** A door's two halves after a power change: both `want` open and powered. */
export function doorVerdict(want, halves) {
  const problems = [];
  halves.forEach((h, i) => {
    const name = i === 0 ? "lower" : "upper";
    if (h.open !== want) problems.push(`${name} open=${h.open}, expected ${want}`);
    if (h.powered !== want) problems.push(`${name} powered=${h.powered}, expected ${want}`);
  });
  return { ok: problems.length === 0, problems };
}

// The trapdoor check's layer (#296): one block each, laid out like the paired
// check (eight apart, room for a redstone block beside it), a new layer four
// up every 64.
export const TRAPDOOR_Y = 60;

/** Where the i-th trapdoor goes. */
export function trapdoorSlot(i) {
  const at = pairedSlot(i);
  return { ...at, y: at.y - PAIRED_Y + TRAPDOOR_Y };
}

/** A trapdoor after a power change: `want` open and powered. */
export function trapdoorVerdict(want, state) {
  const problems = [];
  if (state.open !== want) problems.push(`open=${state.open}, expected ${want}`);
  if (state.powered !== want) problems.push(`powered=${state.powered}, expected ${want}`);
  return { ok: problems.length === 0, problems };
}

// The fence gate check's layer (#367): one gate each, laid out like the paired
// check (a redstone block or a wall beside it), a new layer four up every 64;
// above the drop layer, below the connection layer.
export const GATE_Y = 90;
export const OPPOSITE = { north: "south", south: "north", east: "west", west: "east" };

/** Where the i-th fence gate goes. */
export function gateSlot(i) {
  const at = pairedSlot(i);
  return { ...at, y: at.y - PAIRED_Y + GATE_Y };
}

/** A gate read back against `want`: only the states `want` names are compared. */
export function gateVerdict(want, state) {
  const problems = [];
  for (const [k, v] of Object.entries(want)) {
    if (state[k] !== v) problems.push(`${k}=${state[k]}, expected ${v}`);
  }
  return { ok: problems.length === 0, problems };
}

// The pressure plate check's layer (#296): one plate each on a stone block,
// laid out like the paired check (a redstone lamp beside it), a new layer
// four up every 64; between the trapdoor and drop layers for 128 plates.
export const PLATE_Y = 66;

/** Where the i-th pressure plate goes (the stone goes one below). */
export function plateSlot(i) {
  const at = pairedSlot(i);
  return { ...at, y: at.y - PAIRED_Y + PLATE_Y };
}

// The button check's layer (#280): one button each on a stone block, laid
// out like the paired check (a redstone lamp beside it), a new layer four up
// every 64; above the plate layers, below the drop layer.
export const BUTTON_Y = 74;

/** Where the i-th button goes (the stone goes one below). */
export function buttonSlot(i) {
  const at = pairedSlot(i);
  return { ...at, y: at.y - PAIRED_Y + BUTTON_Y };
}

/** A plate read back: `want` pressed; `seen` {powered, lamp} (lamp undefined: not asked). */
export function plateVerdict(want, seen) {
  const problems = [];
  if (seen.powered !== want) problems.push(`powered=${seen.powered}, expected ${want}`);
  if (seen.lamp !== undefined && seen.lamp !== want) problems.push(`lamp lit=${seen.lamp}, expected ${want}`);
  return { ok: problems.length === 0, problems };
}

/** The container check's verdict: the slot count the converter wrote. */
export function containerVerdict(expected, size) {
  if (size === undefined) return { ok: false, problems: ["no minecraft:inventory component"] };
  if (size !== expected) return { ok: false, problems: [`${size} slots, expected ${expected}`] };
  return { ok: true, problems: [] };
}

/** Tally per check: {check: {run, failed}}, plus every failure in order. */
export class Tally {
  constructor() {
    this.checks = {};
    this.failures = [];
  }
  record(check, id, ok, detail) {
    const row = (this.checks[check] ??= { run: 0, failed: 0 });
    row.run += 1;
    if (!ok) {
      row.failed += 1;
      this.failures.push({ check, id, detail });
    }
  }
  summary() {
    return { checks: this.checks, failed: this.failures.length };
  }
}

/** One tagged line: TAG KIND {json}. */
export function line(kind, payload) {
  return `${TAG} ${kind} ${JSON.stringify(payload)}`;
}

/** An exception or value as short text for a failure detail. */
export function describe(err) {
  if (err === undefined) return "undefined";
  if (err instanceof Error) return `${err.name}: ${err.message}`;
  return String(err);
}

// The ore check (#281). Each ore feature is placed into a cube of the block it
// replaces, eight apart on layer ORE_Y (below the paired and drop layers).
export const ORE_Y = 20;
export const ORE_SPACING = 8;
export const ORE_CUBE = 7;
// The generation check loads fresh chunks of a dimension this far out (blocks,
// both axes), GEN_SIZE wide: nothing else has touched them.
export const GEN_ORIGIN = 4096;
export const GEN_SIZE = 48;

/** The corner of the i-th ore cube: eight apart, 64 a layer. */
export function oreSlot(i) {
  const per = AREA / ORE_SPACING;
  const k = i % (per * per);
  return { x: (k % per) * ORE_SPACING, y: ORE_Y, z: Math.floor(k / per) * ORE_SPACING };
}

/** The y range to scan for a rule: its extent clipped to the dimension's. */
export function scanRange(y, lowest, highest) {
  const lo = Math.max(Math.min(y[0], y[1]), lowest);
  const hi = Math.min(Math.max(y[0], y[1]), highest);
  return lo <= hi ? [lo, hi] : null;
}

/**
 * The ore verdict: counts (block id -> blocks found) against the ore's blocks.
 * At least one of them must be there.
 */
export function oreVerdict(counts, blocks) {
  const found = blocks.reduce((n, b) => n + (counts?.[b] ?? 0), 0);
  return found > 0 ? { ok: true, problems: [] } : { ok: false, problems: [`none of ${blocks.join(", ")} found`] };
}

/**
 * The generation verdict (#281): an ore found in the scanned range passes; none
 * fails, unless the range held none of the blocks it may replace (``hosts``),
 * where nothing could have generated: then it is skipped, with the reason.
 */
export function generateVerdict(counts, blocks, hosts) {
  const verdict = oreVerdict(counts, blocks);
  if (verdict.ok || !hosts || hosts.length === 0) return { ...verdict, skipped: false };
  const room = hosts.reduce((n, b) => n + (counts?.[b] ?? 0), 0);
  if (room > 0) return { ...verdict, skipped: false };
  return { ok: false, skipped: true, problems: [`none of ${hosts.join(", ")} in the scanned range`] };
}
