// portkit station runtime: Waystones waystones, sharestones and portstones, Bedrock binding (#178).
//
// Fixed file, copied verbatim into every pack that ships waystones
// (portkit/runtime/; see docs/decisions.md). The generated entry
// scripts/portkit/main.js calls registerWaystones(table) with the mod's data
// table. Script API: @minecraft/server 2.0.0 (custom components v2:
// beforeOnPlayerPlace, onPlayerInteract, onPlayerBreak; world and entity
// dynamic properties; Entity.teleport; world.afterEvents.playerPlaceBlock) and
// @minecraft/server-ui 2.0.0 (ActionFormData, ModalFormData).
//
// Storage: a waystone is one world dynamic property keyed by its dimension
// and lower-half position (JSON: uid, type, order, dimension, pos, facing,
// name, owner, origin); a player's activated waystones are a player dynamic
// property (JSON list of uids, in activation order). Java keeps the same facts
// in WaystoneManagerImpl and PlayerWaystoneManager's saved data.
//
// Networks: the table maps each block to its Java waystone type and each type
// to a network. A waystone's (not shared) lists the waystones the player
// activated; a sharestone's (shared, one per colour) lists every sharestone of
// its type and has nothing to activate. A portstone (table.portstones) is no
// waystone: it stores nothing, and using it opens the menu of the network it
// targets with no waystone in use, so nothing is left out and no distance is
// checked.

import { GameMode, system, world } from "@minecraft/server";
import { ActionFormData, FormCancelationReason, ModalFormData } from "@minecraft/server-ui";
import * as core from "./waystone_core.js";
import { centre, loadStored, play, saveStored } from "./station_storage.js";

// A form shown while the player is still busy (the use that opened it) is
// cancelled with UserBusy; it is shown again on the next tick, this often.
const BUSY_RETRIES = 20;

function show(form, player, retries = BUSY_RETRIES) {
  return form.show(player).then((response) => {
    if (response.canceled && response.cancelationReason === FormCancelationReason.UserBusy && retries > 0) {
      return new Promise((resolve) => system.run(() => resolve(show(form, player, retries - 1))));
    }
    return response;
  });
}

function free(block) {
  // hasSpaceToTeleport L249-253 asks for blocks that don't suffocate; scripts
  // can't read that, so only air and liquid count as room.
  return !!block && (block.isAir || block.isLiquid);
}

function blockAt(dimension, pos) {
  try {
    return dimension.getBlock(pos);
  } catch {
    return undefined; // an unloaded chunk
  }
}

function typeOf(table, record) {
  return core.recordType(record, table.default_type);
}

function network(table, record) {
  return table.networks[typeOf(table, record)];
}

/** The table's entry for a portstone block, or undefined for a waystone or sharestone. */
function portstoneOf(table, typeId) {
  return (table.portstones || {})[typeId];
}

function lowerPos(table, block, permutation) {
  const half = permutation.getState(table.half_state);
  const { x, y, z } = block.location;
  return half === "upper" ? { x, y: y - 1, z } : { x, y, z };
}

function records(table) {
  const prefix = core.recordPrefix(table.namespace);
  return world.getDynamicPropertyIds()
    .filter((key) => key.startsWith(prefix))
    .map((key) => loadStored(key))
    .filter((record) => record && record.uid);
}

function activated(table, player) {
  const raw = player.getDynamicProperty(core.activatedKey(table.namespace));
  try {
    const list = typeof raw === "string" ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function activate(table, player, uid) {
  const next = core.withActivated(activated(table, player), uid);
  player.setDynamicProperty(core.activatedKey(table.namespace), JSON.stringify(next));
}

/** The next placement number (a world counter), so sharestones list in the order they were placed. */
function nextOrder(table) {
  const key = core.orderKey(table.namespace);
  const raw = world.getDynamicProperty(key);
  const next = (typeof raw === "number" ? raw : 0) + 1;
  world.setDynamicProperty(key, next);
  return next;
}

function newUid() {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 0x7fffffff).toString(36)}`;
}

/**
 * The waystone at a lower-half position, created when there is none (a block
 * not placed by a player: WaystoneBlockEntityBase initializes one with no
 * owner and the state's origin, UNKNOWN by default).
 */
function recordAt(table, dimension, pos, permutation, placer, typeId) {
  const key = core.recordKey(table.namespace, dimension.id, pos);
  const type = table.block_types[typeId] || table.default_type;
  let record = loadStored(key);
  // A record of another type is stale (its block was swapped without a
  // player breaking it); this block is a new waystone, as Java's block
  // entity would be.
  if (!record || typeOf(table, record) !== type) {
    record = {
      uid: newUid(),
      type,
      order: nextOrder(table),
      dimension: dimension.id,
      pos,
      facing: permutation.getState("minecraft:cardinal_direction") || "north",
      name: { text: "" },
      owner: placer ? placer.id : null,
      owner_name: placer ? placer.name : null,
      origin: placer ? "PLAYER" : "UNKNOWN",
    };
    saveStored(key, record);
  }
  return record;
}

function message(table, role, args) {
  const msg = { translate: table.messages[role] };
  if (args) msg.with = { rawtext: args };
  return { rawtext: [msg] };
}

/** WaystoneBlockBase#getStateForPlacement L160-173: a replaceable block above, inside the world. */
function beforePlace(event) {
  const above = event.block.above();
  if (!free(above)) event.cancel = true;
}

/**
 * WaystoneBlockBase#setPlacedBy L286-339: the upper half above with the
 * same facing, a new waystone owned by the placer, activated for them (no
 * message), and the settings screen opened to name it.
 */
function placed(table, event) {
  const { block, player } = event;
  if (!table.blocks.includes(block.typeId)) return;
  const permutation = block.permutation;
  if (permutation.getState(table.half_state) !== "lower") return;
  const above = block.above();
  if (above) above.setPermutation(permutation.withState(table.half_state, "upper"));
  // setPlacedBy L299: a portstone's block entity is no waystone, so placing
  // one makes nothing else (no owner, no name, nothing activated).
  if (portstoneOf(table, block.typeId)) return;
  const pos = { ...block.location };
  // A fresh waystone replaces anything stale stored at this spot.
  saveStored(core.recordKey(table.namespace, block.dimension.id, pos), undefined);
  const record = recordAt(table, block.dimension, pos, permutation, player, block.typeId);
  // activateWaystone L60: only a waystone joins the player's activated list.
  if (!network(table, record).shared) activate(table, player, record.uid);
  system.run(() => rename(table, player, record));
}

/** The settings screen, name only (WaystoneEditScreen; EditWaystoneMessage#handle). */
function rename(table, player, record) {
  const form = new ModalFormData()
    // getSettingsMenuProvider L297: "Edit %s" with the block entity's name
    // (WaystoneBlockEntity / SharestoneBlockEntity#getName).
    .title(message(table, "settings", [{ translate: table.messages[network(table, record).name] }]))
    // Java's name box has no label (WaystoneEditScreen L53, Component.empty()).
    .textField("", "", { defaultValue: record.name && record.name.text ? record.name.text : "" })
    .submitButton({ translate: table.messages.save });
  show(form, player).then((response) => {
    if (response.canceled || !response.formValues) return;
    const key = core.recordKey(table.namespace, record.dimension, record.pos);
    const current = loadStored(key);
    if (!current || current.uid !== record.uid) return;
    if (core.editError(current, player.id, table.restricted_origins)) return;
    if (player.dimension.id !== current.dimension || !core.inRange(player.location, current.pos, table.range_sq)) return;
    current.name = core.legalName(response.formValues[0], table.name_max_length, table.messages.untitled);
    saveStored(key, current);
  });
}

function interact(table, event) {
  const { block, dimension, player } = event;
  if (!player) return;
  const permutation = block.permutation;
  if (permutation.getState(table.half_state) === "upper") {
    const below = block.below();
    if (!below || below.typeId !== block.typeId) return; // a lone upper half is no waystone
  }
  // PortstoneBlock#useWithoutItem L133-143: the menu of its target network,
  // sneaking or not, with no source waystone.
  const port = portstoneOf(table, block.typeId);
  if (port) {
    system.run(() => menu(table, player, {
      type: port.target,
      requirements: port.requirements,
      title: { translate: port.title },
      from: null,
    }));
    return;
  }
  const pos = lowerPos(table, block, permutation);
  const record = recordAt(table, dimension, pos, permutation, null, block.typeId);
  // handleEditActions L196-205: sneaking opens the settings.
  if (player.isSneaking) {
    if (core.editError(record, player.id, table.restricted_origins)) {
      player.onScreenDisplay.setActionBar(message(table, "only_owner"));
      return;
    }
    system.run(() => rename(table, player, record));
    return;
  }
  // SharestoneBlock#handleActivation L74-82: the menu, nothing to activate.
  // WaystoneBlock#handleActivation L81-123.
  if (network(table, record).shared || activated(table, player).includes(record.uid)) {
    system.run(() => menu(table, player, {
      type: typeOf(table, record),
      requirements: network(table, record).requirements,
      title: { translate: table.messages.title },
      from: record,
    }));
    return;
  }
  activate(table, player, record.uid);
  player.sendMessage(message(table, "activated", [core.nameText(record.name)]));
  play(dimension, centre(block), table.sounds.activate);
}

function context(player, target) {
  return {
    is_interdimensional: player.dimension.id !== target.dimension,
    distance: core.distance(player.location, target.pos),
  };
}

/**
 * The selection menu (WaystoneSelectionScreen), then the teleport. `source`
 * is {type, requirements, title, from}: the network listed, the cost rules,
 * the form title, and the waystone in use (null from a portstone: Java's
 * screen then has no "Current Location" header, L333-337).
 */
function menu(table, player, source) {
  const { from } = source;
  const net = table.networks[source.type];
  const list = core.menuTargets(net.shared, activated(table, player), records(table), source.type,
    from ? from.uid : null, table.default_type);
  const body = [];
  if (from) body.push(message(table, "current_location", [core.nameText(from.name, table.messages.unnamed)]));
  if (list.length === 0) {
    if (body.length) body.push({ text: "\n" });
    body.push(message(table, net.none));
  }
  const form = new ActionFormData().title(source.title).body(body.length ? { rawtext: body } : "");
  for (const target of list) {
    const points = core.cost(source.requirements, context(player, target));
    const label = [core.nameText(target.name, table.messages.unnamed)];
    if (points > 0) label.push({ text: "\n" }, message(table, "xp_cost", [{ text: String(points) }]));
    form.button({ rawtext: label });
  }
  show(form, player).then((response) => {
    if (response.canceled || response.selection === undefined) return;
    const target = list[response.selection];
    if (target) teleport(table, player, source, target);
  });
}

/** SelectWaystoneMessage -> WaystoneTeleportManager#tryTeleport. */
function teleport(table, player, source, target) {
  const { from } = source;
  const fail = (role) => player.onScreenDisplay.setActionBar(message(table, role));
  // validateTeleportStart L449-452: still near the waystone used; with no
  // waystone in use (a portstone) there is nothing to be near (L523-528).
  if (from && (player.dimension.id !== from.dimension || !core.inRange(player.location, from.pos, table.range_sq))) {
    return fail("out_of_range");
  }
  const key = core.recordKey(table.namespace, target.dimension, target.pos);
  const current = loadStored(key);
  if (!current || current.uid !== target.uid || typeOf(table, current) !== source.type) return fail("missing");
  const dimension = world.getDimension(current.dimension);
  const lower = blockAt(dimension, current.pos);
  if (lower && table.block_types[lower.typeId] !== typeOf(table, current)) {
    // The block went without a player breaking it; Java's onRemove drops it.
    saveStored(key, undefined);
    return fail("missing");
  }
  const points = core.cost(source.requirements, context(player, current));
  const creative = player.getGameMode() === GameMode.Creative;
  if (!core.canAfford(player.getTotalXp(), points, creative)) return fail("not_enough_xp");
  let side = current.facing;
  if (lower) {
    side = core.offsetDirection(current.facing, (direction) => {
      const offset = core.OFFSETS[direction];
      const at = { x: current.pos.x + offset.x, y: current.pos.y, z: current.pos.z + offset.z };
      return free(blockAt(dimension, at)) && free(blockAt(dimension, { ...at, y: at.y + 1 }));
    });
  }
  const destination = core.destination(current.pos, side, current.facing);
  // consumeRequirements L490-494: giveExperiencePoints(-points), creative too.
  if (points > 0) player.addExperience(-points);
  const departure = { ...player.location };
  const sourceDimension = player.dimension;
  player.teleport(destination.location, {
    dimension,
    rotation: { x: player.getRotation().x, y: destination.yaw },
  });
  // performTeleport L161-162.
  play(sourceDimension, departure, table.sounds.depart);
  play(dimension, destination.location, table.sounds.arrive);
}

/**
 * WaystoneBlockBase#playerWillDestroy L96-137 and onRemove L217-237: the
 * other half goes too, and with it the waystone. Only the lower half drops
 * (its loot table); breaking the upper half outside creative destroys the
 * lower one with its drops, as Java drops the lower state's loot.
 */
function broken(table, event) {
  const { block, brokenBlockPermutation: permutation, dimension, player } = event;
  const half = permutation.getState(table.half_state);
  const other = half === "upper" ? block.below() : block.above();
  const pos = half === "upper" ? { ...block.location, y: block.location.y - 1 } : { ...block.location };
  if (other && other.typeId === permutation.type.id && other.permutation.getState(table.half_state) !== half) {
    const creative = player && player.getGameMode() === GameMode.Creative;
    if (half === "upper" && !creative) {
      dimension.runCommand(core.destroyCommand(other.location));
    } else {
      other.setType("minecraft:air");
    }
  }
  // A portstone stores nothing; whatever is stored at its spot is stale.
  saveStored(core.recordKey(table.namespace, dimension.id, pos), undefined);
}

/** Register the waystones' custom component for one mod's data table. */
export function registerWaystones(table) {
  system.beforeEvents.startup.subscribe((init) => {
    init.blockComponentRegistry.registerCustomComponent(table.component, {
      beforeOnPlayerPlace: (event) => beforePlace(event),
      onPlayerInteract: (event) => interact(table, event),
      onPlayerBreak: (event) => broken(table, event),
    });
  });
  world.afterEvents.playerPlaceBlock.subscribe((event) => placed(table, event));
}
