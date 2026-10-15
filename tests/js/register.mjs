// Maps "@minecraft/server" to the test stub, so the fixed runtime runs under node.
import { register } from "node:module";

register("./loader.mjs", import.meta.url);
