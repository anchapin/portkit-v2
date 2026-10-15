import { existsSync } from "node:fs";

const ADAPTER_RUNTIME_DIR = /\/src\/portkit\/adapters\/[^/]+\/runtime\//;
const STUB = new URL("./minecraft_server_stub.mjs", import.meta.url).href;
const UI_STUB = new URL("./minecraft_server_ui_stub.mjs", import.meta.url).href;

// An adapter's runtime (src/portkit/adapters/<name>/runtime/, #245 pick 6a)
// ships in scripts/portkit/ beside the core runtime, so its "./station_core.js"
// is the core file; in the source tree it resolves to src/portkit/runtime/.
const ADAPTER_RUNTIME = /\/src\/portkit\/adapters\/[^/]+\/runtime\/[^/]+$/;

export async function resolve(specifier, context, next) {
  if (specifier === "@minecraft/server") return { url: STUB, shortCircuit: true };
  if (specifier === "@minecraft/server-ui") return { url: UI_STUB, shortCircuit: true };
  if (specifier.startsWith("./") && context.parentURL && ADAPTER_RUNTIME.test(new URL(context.parentURL).pathname)) {
    const own = new URL(specifier, context.parentURL);
    if (!existsSync(own)) {
      const core = new URL(context.parentURL.replace(ADAPTER_RUNTIME_DIR, "/src/portkit/runtime/"));
      return { url: new URL(specifier, core).href, shortCircuit: true };
    }
  }
  return next(specifier, context);
}

// The runtime's .js files are ES modules without a package.json saying so.
export async function load(url, context, next) {
  if (url.includes("/portkit/runtime/") || url.includes("/scripts/portkit/") || ADAPTER_RUNTIME.test(url)) {
    return next(url, { ...context, format: "module" });
  }
  return next(url, context);
}
