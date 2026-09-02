/**
 * Mini App composition root.
 *
 * Runtime/domain code lives in modules/runtime.js. Keeping this entrypoint
 * intentionally small gives the browser and Vercel build a stable script URL
 * while the runtime is split into native ES modules incrementally.
 */
import "./modules/runtime.js";
