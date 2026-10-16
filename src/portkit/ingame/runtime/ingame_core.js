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
