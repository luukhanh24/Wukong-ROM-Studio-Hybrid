---
name: Wukong ROM Studio Hybrid
description: A chromatic technical atlas for composing and monitoring ROM builds with confidence.
colors:
  canvas: "#ececf3"
  work-surface: "#ffffff"
  work-surface-soft: "#f5f5fa"
  hardware-violet: "#201d3d"
  ink: "#1d1b2e"
  muted-ink: "#68677a"
  divider: "#d9d8e5"
  signal-violet: "var(--tg-theme-button-color, #5146e5)"
  signal-violet-strong: "#4037c4"
  signal-text: "var(--tg-theme-button-text-color, #ffffff)"
  aqua: "#42c9b7"
  coral: "#f47761"
  sun: "#f2bd4b"
  success: "#18845a"
  danger: "var(--tg-theme-destructive-text-color, #c63d4d)"
  dark-canvas: "#11101b"
  dark-work-surface: "#1c1a29"
  dark-work-surface-soft: "#252333"
  dark-hardware-violet: "#0b0a13"
  dark-ink: "#f4f2ff"
  dark-muted-ink: "#aaa7bb"
  dark-divider: "#373447"
typography:
  display:
    fontFamily: "Sora, sans-serif"
    fontSize: "clamp(40px, 5.5vw, 68px)"
    fontWeight: 600
    lineHeight: 1.02
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Sora, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Sora, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Manrope, ui-sans-serif, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "IBM Plex Mono, monospace"
    fontSize: "10px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.06em"
rounded:
  sm: "10px"
  compact: "12px"
  control: "13px"
  md: "16px"
  lg: "20px"
  panel: "24px"
  hero: "28px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  2xl: "24px"
  page: "34px"
components:
  button-primary:
    backgroundColor: "{colors.signal-violet}"
    textColor: "{colors.signal-text}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "11px 17px"
    height: "50px"
  button-primary-hover:
    backgroundColor: "{colors.signal-violet-strong}"
    textColor: "{colors.signal-text}"
    rounded: "{rounded.control}"
  field:
    backgroundColor: "{colors.work-surface-soft}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "12px 14px"
    height: "50px"
  card:
    backgroundColor: "{colors.work-surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "24px"
  nav-active:
    backgroundColor: "{colors.hardware-violet}"
    textColor: "{colors.signal-text}"
    rounded: "{rounded.compact}"
    padding: "8px 14px"
    height: "46px"
---

# Design System: Wukong ROM Studio Hybrid

## Overview

**Creative North Star: "The Chromatic Technical Atlas"**

Wukong turns dense ROM operations into a connected control atlas. Deep-violet hardware panels establish the instrument layer; pearl work surfaces hold forms, ledgers, and catalogs; aqua, coral, and sun signals make source, delivery, and readiness states immediately legible. The result is technical and information-rich without feeling like a generic admin dashboard.

This is an Operate interface. Color, depth, and large display type establish orientation, while native controls, explicit labels, sequential numbering, and honest status copy preserve auditability. The visual world must support one-handed Telegram use and the same orchestration truth expressed through Windows, chat, CLI, and GitHub Actions.

**Key Characteristics:**

- Deep-violet instrument panels floating over pearl work surfaces.
- Violet for selection and action; aqua, coral, and sun for distinct semantic signals.
- Sora for orientation, Manrope for operation, and IBM Plex Mono for measurements and identifiers.
- Soft physical shadows and a rounded 10–28px hierarchy.
- A dark Smart Source instrument that recognizes source state before dispatch.
- A live readiness docket that changes only when the URL is valid and a device is selected.

## Colors

The palette combines cool pearl neutrals with a deep violet chassis and four tightly assigned chromatic signals. Telegram theme variables may supply the primary and destructive colors; the documented fallbacks preserve the atlas character outside Telegram.

### Primary

- **Signal Violet:** Selection, active navigation, primary actions, and caret color. Its stronger companion is reserved for hover emphasis.
- **Hardware Violet:** Masthead, hero plates, Smart Source, readiness docket, floating mobile navigation, and toast surfaces.

### Secondary

- **Atlas Aqua:** Source recognition, active section markers, connection health, checked micro-indicators, and the global focus outline.
- **Dispatch Coral:** Delivery markers and the ready-to-dispatch docket action. Coral is never a substitute for destructive red.

### Tertiary

- **Readiness Sun:** Runner stamps, build-option markers, catalog totals, and the incomplete-docket state.
- **System Green:** Success and healthy connection states only.
- **Destructive Red:** Cancel, invalid source, failed toast, and destructive maintenance only.

### Neutral

- **Cool Canvas:** The app backdrop; pale chromatic blocks may edge the desktop canvas but disappear on mobile.
- **Pearl Work Surface:** Primary cards, forms, catalogs, and ledgers.
- **Soft Pearl:** Nested controls and quiet grouped regions.
- **Atlas Ink / Muted Ink / Divider:** Primary copy, explanatory copy, and structural separation.
- **Night Atlas Set:** System dark mode swaps the canvas, work surfaces, hardware, text, and divider tokens while retaining signal meanings.

### Named Rules

**The Signal Has a Job Rule.** Violet acts, aqua recognizes, coral dispatches, sun warns or summarizes, green succeeds, and red destroys or fails. Never use these colors as interchangeable decoration.

**The Chassis and Desk Rule.** Dark violet belongs to hardware-like instrument surfaces; pearl belongs to work surfaces. Preserve that material contrast in every new view.

## Typography

**Display Font:** Sora (with sans-serif fallback)

**Body Font:** Manrope (with system sans-serif fallbacks)

**Label/Mono Font:** IBM Plex Mono (with monospace fallback)

**Character:** Sora gives the atlas decisive wayfinding, Manrope keeps dense operational copy humane, and IBM Plex Mono marks machine-readable facts without making the whole interface resemble a terminal.

### Hierarchy

- **Display:** Large Sora headlines orient each destination and balance tightly; on mobile they scale down while retaining their short measure.
- **Headline:** Sora names sections and work-surface groups.
- **Title:** Sora identifies Smart Source state, routes, and prominent card actions.
- **Body:** Manrope carries controls and explanatory text; supporting paragraphs generally stay within 62–72 characters.
- **Label:** IBM Plex Mono carries indices, status kickers, IDs, measurements, counts, and uppercase field labels.

### Named Rules

**The Three Voices Rule.** Use Sora to orient, Manrope to operate, and IBM Plex Mono to measure. Do not let mono type expand into paragraphs or general controls.

## Layout

The desktop atlas centers within a 1240px main frame. A sticky 1180px destination rail sits beneath the masthead; the Studio form uses a wide work column and a narrower sticky dispatch docket. Major page heads are asymmetric dark plates with geometric signal forms, while operational content is divided into discrete pearl sheets.

At 860px and below, the interface becomes one column. The horizontal rail becomes a five-cell floating bottom navigation, and Studio gains a floating dispatch action above it; safe-area insets are included in both controls and in page padding. The full dispatch docket remains in document flow as the truthful final recipe summary. At 390px, dense two-column inventories collapse to one. In short mobile landscape, the floating dispatch action is removed and only bottom navigation remains, preventing the work surface from being obscured.

Views enter with a brief clipped reveal (420ms using the atlas ease). System reduced-motion preference collapses animations, transitions, and smooth scrolling to effectively instantaneous behavior.

### Named Rules

**The Work Must Stay Reachable Rule.** Floating navigation and dispatch controls require matching bottom clearance; landscape removes the extra CTA when vertical room is scarce.

**The Docket Remains in the Record Rule.** The mobile floating CTA accelerates action but never replaces the in-flow readiness docket.

## Elevation & Depth

This system uses soft physical elevation rather than hard outlines alone. Pearl cards sit lightly above the canvas, navigation and hero panels take a firmer ambient lift, and floating controls receive the strongest shadow. Nested controls use tonal separation and fine dividers so depth remains calm rather than glossy.

### Shadow Vocabulary

- **Work Surface:** `0 8px 22px rgba(31, 28, 62, .08)` for cards and ledgers.
- **Instrument Panel:** `0 18px 48px rgba(31, 28, 62, .13)` for the destination rail, hero plates, and Smart Source.
- **Floating Control:** `0 24px 60px rgba(31, 28, 62, .2)` for the dispatch docket, mobile navigation, CTA, and toast.
- **Night Work Surface / Instrument / Float:** Dark mode raises opacity to `.22`, `.34`, and `.48` respectively against black.

### Named Rules

**The Soft Hardware Rule.** Shadows communicate physical layer and persistence, not ornament. Use the smallest established shadow that explains the surface's position.

## Shapes

Corners form a deliberate 10–28px hierarchy. Dense list cells and compact controls use the smallest radii; inputs and buttons sit around 12–13px; grouped controls and source states use 14–20px; cards and dockets use 20–24px; hero plates reach 28px. Circular forms are reserved for status lamps and the large geometric signal shapes in hero panels.

Borders are quiet, usually one pixel, and strengthen on hover or focus. Keyboard focus is always a 3px aqua outline with visible offset; focused fields additionally shift to Signal Violet and receive a restrained four-pixel halo.

**The Radius Follows Scale Rule.** Larger containing surfaces receive larger corners. Do not apply one universal radius or return to the obsolete square editorial system.

## Components

### Buttons

- **Shape:** Tactile rounded controls with at least a 44–50px target for primary actions.
- **Primary:** Signal Violet with bold Manrope copy and a restrained colored shadow; hover deepens the violet and lifts two pixels, while active returns to rest.
- **Dispatch:** Coral when ready. The same location becomes sun on a muted-violet docket while incomplete, and its label changes from dispatch to completion guidance.
- **Secondary / Ghost:** Pearl or transparent controls use a divider stroke and gain signal color on hover.
- **Focus:** Every button retains the global aqua focus-visible ring.

### Chips

- **Task tabs:** Three choices sit inside a Soft Pearl segmented group; the selected choice becomes Signal Violet with white text.
- **MOD and pipeline choices:** Compact rounded cells show selection through violet fill, aqua marks, or aqua-soft state rather than checkmarks alone.
- **State:** Hover may lift a cell by one pixel, but status colors keep their assigned meanings.

### Cards / Containers

- **Corner Style:** Work cards use the 20–24px end of the radius scale; hero plates use the 28px maximum.
- **Background:** Pearl for work, Soft Pearl for nested groups, Hardware Violet for instruments.
- **Shadow Strategy:** Work Surface by default; Instrument Panel and Floating Control only when position requires them.
- **Internal Padding:** Typically 20–24px, reduced to 15–18px on narrow screens.

### Inputs / Fields

- **Style:** Soft Pearl fill, one-pixel divider, 13px radius, Manrope content, and an uppercase mono label.
- **Focus:** Pearl fill, Signal Violet border, violet halo, and visible aqua keyboard outline.
- **Error / Disabled:** Invalid source uses Destructive Red; disabled controls retain context at reduced opacity and a not-allowed cursor.

### Navigation

Desktop navigation floats as a pearl rail with numbered destinations; the active destination becomes Hardware Violet and its number tile becomes aqua. Mobile navigation becomes a five-cell Hardware Violet dock with a Signal Violet active cell. Destination changes update both systems together.

### Smart Source

Smart Source is the signature dark instrument panel. The URL field, source-state marker, optional analysis action, and four metadata facts form one contained unit. Idle, detected, and invalid states alter the marker and copy truthfully; recognition never implies that the whole ROM has been downloaded or validated.

### Readiness Docket

The docket is a live recipe summary, not a decorative CTA. It is incomplete until source classification is valid and a device is selected. The label, guidance, summary, button copy, background, and action color update together; mobile mirrors the same summary in its floating CTA.

### GitHub Actions Adapter

Actions is the same operational truth rendered as a log: setup and pipeline stages use numbered bilingual titles; runtime stages open log groups; completions emit notices with duration when available; failures emit an error annotation with the stage title. The Job Summary records job ID, device, task, runner, recipe digest, MOD pack, preset, selected MOD count, and artifact size, SHA, and link. This presentation remains an adapter—the orchestrator and manifest own state, progress, validation, and ownership.

## Do's and Don'ts

### Do:

- **Do** preserve the dark-hardware / pearl-work-surface contrast in every destination.
- **Do** bind readiness styling and dispatch language to real validation state.
- **Do** keep Vietnamese and English labels, errors, and recovery actions complete together.
- **Do** preserve safe-area clearance, 44px practical touch targets, visible focus, dark mode, and reduced motion.
- **Do** use sequential numbers only for meaningful order: recipe sections, pipeline stages, job actions, and canonical states.
- **Do** keep GitHub Actions presentation aligned with the same orchestration events and summary facts.

### Don't:

- **Don't** revive the Minimalist Editorial direction: square zero-radius controls, paper-dossier styling, and a no-shadow rule are obsolete.
- **Don't** flatten every surface into the same light card or spread semantic colors decoratively.
- **Don't** let floating navigation or CTA controls obscure fields, especially in mobile landscape.
- **Don't** signal a ready build from preset or MOD selection alone; valid source plus device is the current readiness gate.
- **Don't** expose credentials, signed URLs, tokens, or ownership fields in browser state, recipes, logs, or messages.
- **Don't** replace explicit action labels with unlabeled icons.
