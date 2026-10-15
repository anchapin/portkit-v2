// portkit station kit: showing a @minecraft/server-ui form (#245).
//
// Fixed file, copied verbatim into every pack whose runtime shows a form
// (portkit/runtime/; see docs/decisions.md, 2026-10-15). It names no mod.
// Before #245 the same function was copied in waystone.js and book.js.
//
// Script API: @minecraft/server 2.0.0 (system.run) and @minecraft/server-ui
// 2.0.0 (a form shown while the player is busy is cancelled with UserBusy).

import { system } from "@minecraft/server";
import { FormCancelationReason } from "@minecraft/server-ui";

// A form shown while the player is still busy (the use that opened it) is
// cancelled with UserBusy; it is shown again on the next tick, this often.
export const BUSY_RETRIES = 20;

/** Show `form` to `player`; a UserBusy cancel shows it again next tick, up to `retries` times. */
export function show(form, player, retries = BUSY_RETRIES) {
  return form.show(player).then((response) => {
    if (response.canceled && response.cancelationReason === FormCancelationReason.UserBusy && retries > 0) {
      return new Promise((resolve) => system.run(() => resolve(show(form, player, retries - 1))));
    }
    return response;
  });
}
