---
name: Wukong ROM Studio
description: Warm, quiet technical workbench for identifying ROMs, composing builds, and monitoring jobs.
---

# Wukong ROM Studio design system

The Mini App is an operate surface: one page leads through **ROM source → configuration → review and build**. The interface serves everyday builders and administrators, with advanced controls collapsed until needed. The Wukong logo, warm neutral canvas, graphite text, cobalt action color, and five position dock with a centered avatar are shared on mobile and desktop.

## Tokens

```css
--canvas: #f3f1eb;
--surface: #f8f7f2;
--surface-raised: #ffffff;
--surface-soft: #eeece6;
--ink: #252830;
--muted: #656861;
--line: #d8d5cc;
--line-strong: #aaa79d;
--accent: #315f9e;
--accent-strong: #244a7c;
--success: #2f765b;
--danger: #c94f56;
--focus: #4f76a6;
--font-body: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
--font-data: "JetBrains Mono", ui-monospace, monospace;
--target-size: 44px;
```

Body text is 14–16px, labels are at least 12px, and interactive controls use a 44px minimum hitbox. IBM Plex Sans carries prose and controls; JetBrains Mono is reserved for IDs, paths, versions, and measurements. Cobalt is the only chromatic accent, while focus rings use `--focus` and status colors communicate state rather than decoration. Both color schemes keep the same semantic roles and readable contrast.

## Surface rules

- Source analysis shows device, version, Android version, and size first. Remaining metadata lives in a `Thông tin chi tiết` disclosure.
- Preset and MOD version remain visible. MOD selection, debloat paths, pipeline steps, publication, and runner controls live in `Tùy chọn nâng cao`; a summary remains visible beside the controls.
- The desktop review docket stays beside the workbench. Mobile receives the same review content in flow, with reserved space above the dock and a keyboard state that hides floating actions.
- Jobs foreground status, current step, updated time, and next action. Technical facts are disclosed separately. Event rendering is bounded to 500 items, paged for older history, and only follows the tail when the reader is already there.
- The dock always contains Studio, Jobs, centered profile avatar, Library, and System. Telegram safe-area values, `visualViewport`, reduced motion, older Telegram bridges, and ordinary browser fallbacks are handled by `modules/viewport.js`.
- Error, offline, expired session, maintenance, and uncertain submission states preserve the last useful data and provide a nearby recovery action.

## Asset and performance rules

`build.mjs` creates hashed ES module chunks with esbuild. Admin controls and ZIP inflation are lazy chunks. Fonts are bundled under `assets/fonts` with their licenses; the Mini App has no chained external font dependency. CSS is split into fonts, tokens, components, screens, dock, and Studio layout files, then bundled for deployment. Vercel serves hashed assets with immutable caching while the HTML remains revalidated.

The shared transport uses a 15-second default timeout, bounded read retries, `Retry-After`, request scopes, and abort-on-supersede. Artifact metadata is computed once and passed through publishing adapters. Build metrics record stage duration, bytes, cache state, checksum, checkpoint, and upload measurements.
