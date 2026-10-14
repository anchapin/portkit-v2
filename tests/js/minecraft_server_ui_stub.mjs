// A minimal stand-in for @minecraft/server-ui: the forms the waystone runtime
// shows, recorded with what they held. Each show() takes the next queued
// response (_respond), or a cancelled one. Not the real API.

export const FormCancelationReason = { UserBusy: "UserBusy", UserClosed: "UserClosed" };

const shown = [];
const responses = [];

/** Queue the response the next form shown gets. */
export function _respond(response) {
  responses.push(response);
}

/** Forms shown so far, oldest first; _reset clears them and the queue. */
export const _shown = shown;
export function _reset() {
  shown.length = 0;
  responses.length = 0;
}

class Form {
  constructor(kind) {
    this.kind = kind;
    this.parts = { buttons: [], fields: [] };
  }
  title(text) { this.parts.title = text; return this; }
  body(text) { this.parts.body = text; return this; }
  button(text, icon) { this.parts.buttons.push({ text, icon }); return this; }
  textField(label, placeholder, options) { this.parts.fields.push({ label, placeholder, options }); return this; }
  submitButton(text) { this.parts.submit = text; return this; }
  show(player) {
    shown.push({ kind: this.kind, player, ...this.parts });
    const response = responses.shift() ?? { canceled: true, cancelationReason: FormCancelationReason.UserClosed };
    return Promise.resolve(response);
  }
}

export class ActionFormData extends Form {
  constructor() { super("action"); }
}

export class ModalFormData extends Form {
  constructor() { super("modal"); }
}
