---
name: Wukong ROM Studio Hybrid
description: A build control ledger for composing, routing, and monitoring ROM work with truthful operational state.
colors:
  canvas: "#f3f1eb"
  work-surface: "#fffdfa"
  work-surface-raised: "#ffffff"
  work-surface-soft: "#eeece6"
  command-bar: "#191a1c"
  ink: "#202124"
  muted-ink: "#66676b"
  divider: "#d7d3cb"
  divider-strong: "#aaa59b"
  signal-amber: "#d97706"
  signal-amber-strong: "#b45309"
  signal-amber-soft: "#fff0d2"
  status-green: "#16775a"
  status-green-soft: "#e2f3eb"
  danger: "var(--tg-theme-destructive-text-color, #bd3f32)"
  danger-soft: "#f9e7e3"
  focus-blue: "#2563eb"
  dark-canvas: "#141516"
  dark-work-surface: "#1b1c1e"
  dark-work-surface-raised: "#202124"
  dark-work-surface-soft: "#28292c"
  dark-command-bar: "#0e0f10"
  dark-ink: "#f0eee8"
  dark-muted-ink: "#aaa8a2"
  dark-divider: "#3b3c3f"
  dark-divider-strong: "#5b5c60"
  dark-signal-amber: "#e89a34"
  dark-signal-amber-strong: "#ffc46b"
typography:
  display:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "clamp(26px, 3vw, 36px)"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  title:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "IBM Plex Sans, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  data:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.4
  label:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "9px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.06em"
rounded:
  mark: "2px"
  micro: "3px"
  sm: "4px"
  md: "6px"
  lg: "8px"
spacing:
  xs: "4px"
  sm: "7px"
  md: "10px"
  lg: "12px"
  xl: "16px"
  2xl: "20px"
  page: "28px"
components:
  button-primary:
    backgroundColor: "{colors.signal-amber}"
    textColor: "{colors.work-surface-raised}"
    typography: "{typography.title}"
    rounded: "{rounded.sm}"
    padding: "10px 15px"
    height: "46px"
  button-primary-hover:
    backgroundColor: "{colors.signal-amber-strong}"
    textColor: "{colors.work-surface-raised}"
    rounded: "{rounded.sm}"
  field:
    backgroundColor: "{colors.work-surface-raised}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "9px 11px"
    height: "44px"
  ledger-card:
    backgroundColor: "{colors.work-surface-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "20px"
  nav-active:
    backgroundColor: "{colors.signal-amber-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "54px"
---

# Design System: Wukong ROM Studio Hybrid

## Overview

**Creative North Star: "The Build Control Ledger"**

Wukong is an editorial operations ledger for real ROM work. Every surface exists to expose source truth, configuration state, execution route, pipeline status, and the next required action. Warm work sheets sit under a compact graphite command bar; amber marks interaction, green confirms valid or complete state, and red is reserved for failure and destructive work.

This is an Operate interface for technical users, not a marketing dashboard. Dense information is organized by hairline rules, compact grids, honest labels, and machine-readable measurements. It remains legible in a Telegram webview, on desktop, in dark mode, and in short landscape without floating controls covering the work.

**Key Characteristics:**

- Factual runtime state replaces decorative hero content.
- Warm neutral sheets and graphite command surfaces establish the workspace.
- One amber action signal is separated from green success and red failure.
- IBM Plex Sans explains; JetBrains Mono identifies and measures.
- Small 2–8px corners and one-pixel rules produce technical precision.
- Grouped MODs, delivery states, and readiness checks expose selection truth.

## Colors

The palette is deliberately neutral and low-chroma. Amber is scarce and operational; system green and destructive red never become decoration.

### Primary

- **Execution Amber:** Primary actions, active route markers, selected controls, focus-adjacent emphasis, and waiting state.
- **Graphite Command Bar:** Masthead, selected task tab, Smart Source analysis action, and other command surfaces.

### Secondary

- **System Green:** Valid source, connected Telegram transport, complete readiness checks, and completed delivery state.
- **Failure Red:** Invalid source, failed delivery state, destructive maintenance, and error toast only.

### Neutral

- **Warm Canvas:** The page backdrop that separates the working sheets without decorative color fields.
- **Work Surface / Raised Work Surface:** Forms, ledgers, status strips, tables, and cards.
- **Soft Work Surface:** Segmented controls, nested rows, and grouped headings.
- **Ledger Ink / Muted Ink / Divider:** Primary copy, supporting copy, indices, and structural rules.
- **Night Ledger Set:** Dark mode maps the same roles to charcoal surfaces without changing semantic signals.

### Named Rules

**The Signal Means State Rule.** Amber acts or waits, green validates or completes, and red fails or destroys. Never distribute them as decoration.

**The Neutral Majority Rule.** Most of every screen remains neutral. Accent rarity is what makes status readable.

## Typography

**Display Font:** IBM Plex Sans (with system sans-serif fallback)

**Body Font:** IBM Plex Sans (with system sans-serif fallback)

**Label/Mono Font:** JetBrains Mono (with monospace fallback)

**Character:** IBM Plex Sans keeps dense Vietnamese and English interface copy calm and legible. JetBrains Mono is reserved for URLs, device codes, runner names, stage state, counts, versions, and identifiers.

### Hierarchy

- **Display:** Bold, compact destination headings that orient without becoming hero typography.
- **Headline:** Section and work-area names.
- **Title:** Buttons, list actions, MOD group headings, and card labels.
- **Body:** Explanatory copy and standard controls, generally limited to 70 characters per line.
- **Data:** Machine-readable values and runtime facts.
- **Label:** Uppercase indices and measurement labels with tracked spacing.

### Named Rules

**The Two Registers Rule.** Sans-serif explains what the operator should understand; monospace carries what the system can identify or measure.

## Layout

The desktop workspace is capped at 1240px. A 64px sticky command bar and 48px destination rail precede a factual three-cell runtime strip. Studio uses a wide work column and a 320px sticky readiness ledger; each build section occupies the work column, while the checklist spans the recipe stages beside them.

At 860px and below, runtime facts stack, the form becomes one column, the readiness ledger returns to document flow, and navigation becomes a compact five-cell bottom bar. At 390px, source facts, catalogs, MOD groups, and maintenance actions collapse to one column. Short landscape keeps the runtime strip horizontal while reserving bottom clearance for navigation. Safe-area insets are included and no persistent build CTA overlays form fields.

Spacing follows a compact 4/7/10/12/16/20/28px rhythm. Views use a single 240ms clipped reveal; reduced-motion preference removes it.

### Named Rules

**The Runtime Before Recipe Rule.** The first work viewport exposes runner, pipeline readiness, and job access before asking the operator to configure details.

**The Work Stays Reachable Rule.** Fixed navigation always receives matching content clearance and never shares space with a floating submit control.

## Elevation & Depth

The ledger is flat by default. Depth comes from tonal surface changes, one-pixel borders, sticky positioning, and semantic state fills rather than card shadows. Toasts and Telegram-native chrome may sit above the interface through z-order, but they do not introduce decorative elevation.

### Named Rules

**The Border Before Shadow Rule.** Use a divider or tonal shift to explain hierarchy. Do not add soft card shadows to make neutral containers feel important.

## Shapes

The interface uses a strict 2–8px radius scale. Two- and three-pixel corners belong to tiny selection marks; four pixels belong to buttons, fields, and compact controls; six pixels group nested status regions; eight pixels cap major sheets. Circles are reserved for status lamps, pipeline nodes, and readiness checks.

One-pixel rules define nearly every container. Selected MODs must change border, background, and check mark together; color fill alone is insufficient.

## Components

### Buttons

- **Shape:** Compact four-pixel corners with at least a 44px practical touch target.
- **Primary:** Execution Amber with explicit action copy; hover deepens the amber and active state moves by one pixel.
- **Secondary:** Neutral surface with a one-pixel stroke; hover borrows amber only for action emphasis.
- **Focus:** A three-pixel blue focus-visible ring remains independent of semantic state color.

### Chips

- **Task tabs:** A segmented neutral group; the selected task becomes Graphite with white text.
- **MOD selector:** Unselected entries are white with an empty square. Selected entries gain an amber border, pale amber surface, and filled check SVG.
- **Pipeline choices:** Checkbox marks combine border and fill so selection is not communicated by color alone.

### Cards / Containers

- **Corner Style:** Six pixels for grouped status regions and eight pixels for major work sheets.
- **Background:** Raised Work Surface over the Warm Canvas; Soft Work Surface for nested rows.
- **Shadow Strategy:** None at rest.
- **Border:** One-pixel Divider or Divider Strong according to hierarchy.
- **Internal Padding:** Usually 16–20px, reduced to 12–15px on narrow screens.

### Inputs / Fields

- **Style:** Raised neutral surface, one-pixel strong divider, four-pixel corners, visible label, and 44px minimum height.
- **Technical content:** URLs, checksums, versions, and IDs use JetBrains Mono.
- **Focus:** Amber border plus a restrained amber outline; keyboard focus also retains the global blue ring.
- **Error / Disabled:** Red belongs next to the failing field or source state; disabled inputs retain context at reduced opacity.

### Navigation

Desktop uses a flat five-cell destination rail with one-pixel separators and a two-pixel amber active rule. Mobile uses a five-cell bottom bar with the same index and label pair; the active cell gets a pale amber surface and top rule. Both systems update together.

### Runtime Strip

Three cells expose runner, current pipeline readiness, and access to recent job state. Waiting uses an amber lamp; a valid source plus selected device changes the pipeline copy and lamp to green. Runtime state must be computed, never ornamental.

### Smart Source

The ROM URL, analysis row, and metadata facts form one bordered instrument. Idle is neutral, recognized is green-tinted, and invalid is red-tinted. Recognition reports provider and source type without implying that the ROM has been fully downloaded or validated.

### Delivery State Row

ZIP, Drive, and Telegram stages support `pending`, `running`, `complete`, `failed`, and `skipped`. Bilingual copy, node color, and state metadata update together. External orchestration adapters may update them through the documented Mini App state setter.

### Readiness Ledger

The sticky ledger is incomplete until the source is valid and a target device is selected. It shows three explicit checks, their details, a progress count, the route summary, a recovery sentence, and exactly one submit action.

## Do's and Don'ts

### Do:

- **Do** keep runtime, source, pipeline, and readiness copy bound to actual state.
- **Do** preserve Vietnamese and English labels, errors, and recovery actions together.
- **Do** group MODs by function and show selection through border, surface, and check mark.
- **Do** preserve 44px touch targets, visible keyboard focus, safe areas, dark mode, and reduced motion.
- **Do** use monospace only for data, identifiers, state, and measurement.
- **Do** keep Telegram identity at the channel boundary and treat empty `initData` as valid only for a known keyboard-button transport.

### Don't:

- **Don't** restore purple/indigo hero panels, blurred blobs, glass surfaces, or generic SaaS dashboard chrome.
- **Don't** add decorative welcome banners or abstract illustrations to an operating surface.
- **Don't** make selected and unselected MODs differ only by fill intensity.
- **Don't** use large pill radii or repeat the same soft shadow on every card and control.
- **Don't** allow fixed navigation, toast, or submit controls to obscure the form.
- **Don't** report a connection, ready recipe, running stage, or completed artifact unless the underlying state supports it.
