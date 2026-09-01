# Mini App module boundaries

The Mini App stays vanilla JavaScript and uses native ES modules. The current
release keeps the legacy feature implementation in `app.js` for runtime
compatibility while extracting shared services behind a composition seam;
feature-by-feature extraction can therefore happen without changing API or
local-storage contracts.

- `feedback.js` owns toast timing and notification haptics.
- `a11y.js` owns roving-tablist keyboard behavior and ARIA selection state.
- `motion.js` is the single source for motion durations/easing and reduced
  motion detection.

When a feature is extracted, it receives the shared context (`state`, `api`,
`t`, `telegram`, `router`, `feedback`) and exposes `bind`, `render`, `enter`,
and `leave`. `leave` must cancel timers, observers, and in-flight requests.
The Vercel build copies this directory and adds a release query to every local
JS import so Telegram WebView caches cannot mix releases.
