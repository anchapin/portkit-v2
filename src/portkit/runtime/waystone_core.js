// portkit station runtime: Waystones waystone logic (#178).
//
// Fixed file, copied verbatim into every pack that ships waystones
// (portkit/runtime/; see docs/decisions.md). No imports, so it runs under
// node (tests/js/waystone.test.mjs). The Bedrock binding is waystone.js.
//
// Cited to Waystones v21.1.46 (TwelveIterations/Waystones @9d280c1a,
// common/src/main/java/net/blay09/mods/waystones/); the data table's header
// lists the exact lines.

/**
 * The experience points a teleport costs: the data table's warp requirement
 * modifiers applied in order to 0 (InternalMethodsImpl#resolveRequirements
 * L244-259; RequirementRegistry L122-147). Each modifier applies when every
 * condition in its `when` matches the context ({is_interdimensional, distance}).
 * Java does the arithmetic in float and casts to int (truncation toward 0),
 * which Math.fround and Math.trunc reproduce.
 */
export function cost(requirements, context) {
  let points = 0;
  for (const modifier of requirements) {
    const applies = Object.entries(modifier.when || {}).every(([name, wanted]) => !!context[name] === wanted);
    if (!applies) continue;
    const [a, b] = modifier.args;
    switch (modifier.fn) {
      case "add_xp_cost":
        points = points + a;
        break;
      case "multiply_xp_cost":
        points = Math.trunc(Math.fround(points * Math.fround(a)));
        break;
      case "scaled_add_xp_cost": {
        const value = Math.fround(context[a] ?? 0);
        points = Math.trunc(Math.fround(points + Math.fround(value * Math.fround(b))));
        break;
      }
      case "min_xp_cost":
        points = Math.max(points, a);
        break;
      case "max_xp_cost":
        points = Math.min(points, a);
        break;
      default:
        throw new Error(`unknown warp requirement ${modifier.fn}`);
    }
  }
  return points;
}

/**
 * ExperiencePointsRequirement#canAfford L17-23 (the player's total points
 * against the cost), skipped in creative (WaystoneTeleportManager
 * #validateRequirements L482: !player.getAbilities().instabuild).
 */
export function canAfford(totalXp, points, creative) {
  return creative || points <= 0 || totalXp >= points;
}

/** Distance from a location to a block position's centre (RequirementRegistry L434). */
export function distance(location, pos) {
  const dx = location.x - (pos.x + 0.5);
  const dy = location.y - (pos.y + 0.5);
  const dz = location.z - (pos.z + 0.5);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

/** WaystoneTeleportManager#canInteractWithWaystone L531: distanceToSqr(centre) <= range. */
export function inRange(location, pos, rangeSq) {
  const d = distance(location, pos);
  return d * d <= rangeSq;
}

export const OFFSETS = {
  north: { x: 0, z: -1 },
  south: { x: 0, z: 1 },
  east: { x: 1, z: 0 },
  west: { x: -1, z: 0 },
};

// Direction#toYRot, wrapped to [-180, 180) (Mth.wrapDegrees): south 0,
// west 90, north 180 (-180), east -90. Bedrock's yaw uses the same axes.
const YAW = { south: 0, west: 90, north: -180, east: -90 };

/**
 * WaystoneTeleportManager#findTeleportOffsetDirection L258-273: the facing
 * first, then east, west, south, north; the first side with room (`free`
 * says whether a side's block and the one above it leave room). null when
 * none does.
 */
export function offsetDirection(facing, free) {
  for (const candidate of [facing, "east", "west", "south", "north"]) {
    if (OFFSETS[candidate] && free(candidate)) return candidate;
  }
  return null;
}

/**
 * WaystoneTeleportManager#resolveDefaultDestination L275-284 and
 * teleportEntity L200: the centre of the block beside the waystone on that
 * side (the waystone's own block when no side has room), the player turned
 * to face the side (or the waystone's facing).
 */
export function destination(pos, side, facing) {
  const offset = side ? OFFSETS[side] : { x: 0, z: 0 };
  return {
    location: { x: pos.x + offset.x + 0.5, y: pos.y + 0.5, z: pos.z + offset.z + 0.5 },
    yaw: YAW[side || facing] ?? YAW.north,
  };
}

/**
 * EditWaystoneMessage#makeNameLegal L84-94: a blank name becomes the
 * untitled key; the edit box holds at most `max` characters
 * (WaystoneEditScreen L54). The inventory-button clash rule never applies
 * (the inventoryButton default is "" and a blank name is untitled first).
 */
export function legalName(input, max, untitledKey) {
  const text = String(input ?? "");
  if (text.trim().length === 0) return { translate: untitledKey };
  return { text: text.slice(0, max) };
}

/** A stored name as rawtext; an empty one as `emptyKey` when given (AbstractWaystoneButton L29-32). */
export function nameText(name, emptyKey) {
  if (name && name.translate) return { translate: name.translate };
  const text = (name && name.text) || "";
  if (!text && emptyKey) return { translate: emptyKey };
  return { text };
}

/**
 * WaystonePermissionManager#mayEditWaystone L35-53 at the defaults: with
 * PLAYER restricted, only the owner edits an owned waystone; a waystone
 * whose origin is restricted can't be edited. Returns "only_owner" or null.
 * (Edit-all permission and the global-visibility rule have no counterpart.)
 */
export function editError(record, playerId, restricted) {
  const owned = !!record.owner;
  if (owned && restricted.includes("PLAYER") && record.owner !== playerId) return "only_owner";
  if (record.origin !== "PLAYER" && restricted.includes(record.origin)) return "only_owner";
  return null;
}

/**
 * The menu's entries: the player's activated waystones in activation order
 * (the default MANUAL sort over the sorting index, which appends waystones
 * as they are activated: PersistentPlayerWaystoneData L270-290), those that
 * still exist, without the one in use (Java lists it disabled,
 * WaystoneList L46-48).
 */
export function targets(activated, records, fromUid) {
  const byUid = new Map(records.map((r) => [r.uid, r]));
  const seen = new Set();
  const list = [];
  for (const uid of activated) {
    if (uid === fromUid || seen.has(uid) || !byUid.has(uid)) continue;
    seen.add(uid);
    list.push(byUid.get(uid));
  }
  return list;
}

/** The player's activated list with `uid` added (PlayerWaystoneManager#activateWaystone). */
export function withActivated(activated, uid) {
  return activated.includes(uid) ? activated : [...activated, uid];
}

/** Dynamic property key of the waystone whose lower half is at `pos` in `dimensionId`. */
export function recordKey(namespace, dimensionId, pos) {
  return `${namespace}:portkit_waystone|${dimensionId}|${pos.x},${pos.y},${pos.z}`;
}

export function recordPrefix(namespace) {
  return `${namespace}:portkit_waystone|`;
}

/** Player dynamic property holding the uids the player activated, in order. */
export function activatedKey(namespace) {
  return `${namespace}:portkit_waystones`;
}

/** `setblock` that removes the block at `location` and drops its loot (Java's destroyBlock with drops). */
export function destroyCommand(location) {
  return `setblock ${location.x} ${location.y} ${location.z} air destroy`;
}
