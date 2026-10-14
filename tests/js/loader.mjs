const STUB = new URL("./minecraft_server_stub.mjs", import.meta.url).href;
const UI_STUB = new URL("./minecraft_server_ui_stub.mjs", import.meta.url).href;

export async function resolve(specifier, context, next) {
  if (specifier === "@minecraft/server") return { url: STUB, shortCircuit: true };
  if (specifier === "@minecraft/server-ui") return { url: UI_STUB, shortCircuit: true };
  return next(specifier, context);
}

// The runtime's .js files are ES modules without a package.json saying so.
export async function load(url, context, next) {
  if (url.includes("/portkit/runtime/") || url.includes("/scripts/portkit/")) {
    return next(url, { ...context, format: "module" });
  }
  return next(url, context);
}
