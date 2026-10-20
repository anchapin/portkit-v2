// portkit runtime: the pure rules of a button (#280). No imports; tested with
// node (tests/js/button.test.mjs). The Bedrock binding is button.js.
//
// Ported from vanilla Java ButtonBlock, read from Mojang's 1.21.1 client jar
// (through Mojang's client.txt) and checked against 1.20.1:
//   useWithoutItem -> a powered button does nothing (CONSUME); otherwise
//                     press(): powered, neighbours updated, a tick scheduled
//                     ticksToStayPressed later, buttonClickOn played
//   tick           -> a powered button runs checkPressed
//   entityInside   -> an arrow in an unpowered button whose set type lets
//                     arrows press it runs checkPressed
//   checkPressed   -> pressed = arrows allowed && an AbstractArrow is inside;
//                     when that differs from powered the state follows (with
//                     buttonClickOn / Off); while pressed, the next check is
//                     scheduled ticksToStayPressed later
// What Bedrock can't give: Java presses on an arrow entering the shape; here
// the projectile hit event presses it (button.js).

/** A player's use. Returns { powered, sound, schedule } or null (nothing happens). */
export function use(powered, ticks) {
  if (powered) return null;
  return { powered: true, sound: "on", schedule: ticks };
}

/** checkPressed: `arrowInside` whether an arrow is in the button now. */
export function check(powered, arrowInside, arrows, ticks) {
  const pressed = arrows === true && arrowInside === true;
  const out = { powered: pressed, sound: null, schedule: pressed ? ticks : null };
  if (pressed !== powered) out.sound = pressed ? "on" : "off";
  return out;
}

/** entityInside for an arrow: only an unpowered button that arrows press checks. */
export function arrowHit(powered, arrows, ticks) {
  if (arrows !== true || powered) return null;
  return check(powered, true, arrows, ticks);
}

/** Whether an entity at `loc` is inside the block cell at `at` (with `margin` blocks around it). */
export function inCell(at, loc, margin) {
  return ["x", "y", "z"].every((a) => loc[a] >= at[a] - margin && loc[a] <= at[a] + 1 + margin);
}
