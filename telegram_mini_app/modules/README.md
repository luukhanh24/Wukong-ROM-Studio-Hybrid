# Mini App module boundaries

The Mini App stays vanilla JavaScript and uses native ES modules. The current
release keeps the legacy feature implementation in `app.js` for runtime
compatibility while extracting shared services behind a composition seam;
feature-by-feature extraction can therefore happen without changing API or
local-storage contracts.

- `feedback.js` owns toast timing and opt-in notification haptics; automatic
  status, polling, and reconnect messages stay silent unless a caller passes
  an explicit haptic token.
- `a11y.js` owns roving-tablist keyboard behavior and ARIA selection state.
- `motion.js` is the single source for motion durations/easing and reduced
  motion detection.
- `feature-registry.js` provides the shared lifecycle seam.
- `features/source.js` and `features/catalog.js` own their event binding;
  `features/build.js`, `features/jobs.js`, `features/profile.js`, and
  `features/admin.js` expose the remaining surface lifecycle and shared
  render seams during the mechanical migration.

When a feature is extracted, it receives the shared context (`state`, `api`,
`t`, `telegram`, `router`, `feedback`, `dom`, and `actions`) and exposes
`bind`, `render`, `enter`, and `leave`. `leave` must cancel timers, observers,
and in-flight requests.
The Vercel build copies this directory and adds a release query to every local
JS import so Telegram WebView caches cannot mix releases. The legacy domain
functions remain in `app.js` until each adapter can move them without changing
API, local-storage, or signed-session behavior.
