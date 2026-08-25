---
name: Wukong ROM Studio Hybrid
description: A chromatic technical atlas for identifying, composing, routing, and monitoring ROM builds with truthful operational state.
colors:
  canvas: "#eceef6"
  pearl-surface: "#fbfaf6"
  raised-surface: "#ffffff"
  soft-surface: "#f1f0ea"
  ink-violet: "#29255d"
  atlas-ink: "#20213a"
  muted-ink: "#67687e"
  hairline: "#d8d8e5"
  hairline-strong: "#aaa9bf"
  action-cobalt: "#3457d5"
  action-cobalt-strong: "#2745b4"
  action-cobalt-soft: "#e7ebff"
  verified-green: "#118777"
  verified-green-soft: "#ddf5ef"
  focus-aqua: "#18a89a"
  signal-coral: "#e86f5b"
  signal-coral-soft: "#ffebe6"
  signal-sun: "#efb844"
  signal-sun-soft: "#fff4ce"
  liquid-lens-accent: "#0088ff"
  liquid-lens-accent-night: "#0091ff"
  liquid-chromatic-edge: "#ff4660"
  failure-red: "var(--tg-theme-destructive-text-color, #c94f56)"
  failure-red-soft: "#fce9e8"
  night-canvas: "#111222"
  night-surface: "#1a1b31"
  night-surface-raised: "#20213a"
  night-surface-soft: "#292a46"
  night-ink-violet: "#171538"
  night-ink: "#f3f2fb"
  night-muted-ink: "#b0aec7"
  night-action-cobalt: "#6683f0"
  night-focus-aqua: "#45cbbb"
  night-signal-coral: "#f18976"
  night-signal-sun: "#f3c45c"
typography:
  display:
    fontFamily: "IBM Plex Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(32px, 4vw, 48px)"
    fontWeight: 700
    lineHeight: 0.98
    letterSpacing: "-0.045em"
  headline:
    fontFamily: "IBM Plex Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  body:
    fontFamily: "IBM Plex Sans, ui-sans-serif, system-ui, sans-serif"
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
  sm: "4px"
  md: "6px"
  lg: "8px"
  control: "10px"
  cluster: "12px"
  instrument: "14px"
  sheet: "18px"
  title-plate: "22px"
spacing:
  xs: "4px"
  sm: "7px"
  md: "10px"
  lg: "12px"
  xl: "16px"
  2xl: "22px"
  page: "28px"
  page-top: "30px"
components:
  button-primary:
    backgroundColor: "{colors.action-cobalt}"
    textColor: "{colors.raised-surface}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "10px 15px"
    height: "46px"
  button-primary-hover:
    backgroundColor: "{colors.action-cobalt-strong}"
    textColor: "{colors.raised-surface}"
    rounded: "{rounded.control}"
  field:
    backgroundColor: "{colors.raised-surface}"
    textColor: "{colors.atlas-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "9px 11px"
    height: "44px"
  dossier-sheet:
    backgroundColor: "{colors.raised-surface}"
    textColor: "{colors.atlas-ink}"
    rounded: "{rounded.sheet}"
    padding: "22px"
  title-plate:
    backgroundColor: "{colors.ink-violet}"
    textColor: "{colors.raised-surface}"
    typography: "{typography.display}"
    rounded: "{rounded.title-plate}"
    padding: "28px"
  nav-active:
    backgroundColor: "{colors.action-cobalt-soft}"
    textColor: "{colors.action-cobalt-strong}"
    rounded: "{rounded.sheet}"
    height: "54px"
---

# Design System: Wukong ROM Studio Hybrid

## Overview

**Creative North Star: "The Chromatic Technical Atlas"**

Wukong is an editorial operating instrument for real ROM work. It turns a dense sequence—identify a source, compose a build, verify its route, dispatch it, and inspect the result—into a legible atlas of numbered sections, measured facts, and truthful state. Ink-violet instruments anchor the interface; pearl work sheets carry the recipe; cobalt, aqua, coral, and sun provide a precise chromatic language instead of generic dashboard decoration.

The interface is expressive without becoming theatrical. Geometric title-plate marks, colored section spines, index numbers, and subtle asymmetry give it authorship. Dense controls remain calm through strict alignment, small type for machine data, restrained elevation, and short, smooth state transitions. It works as a Telegram Mini App first while remaining clear on desktop, dark mode, and short landscape viewports.

**Key Characteristics:**

- Editorial hierarchy and technical density share the same canvas.
- Ink-violet and pearl establish the world; cobalt acts; aqua, coral, sun, green, and red communicate distinct state roles.
- IBM Plex Sans explains, while JetBrains Mono identifies and measures.
- Numbered section markers and colored spines create an atlas-like reading path.
- Runtime, source, delivery, and readiness surfaces always report actual state.
- Motion is smooth and restrained, with a complete reduced-motion path.

## Colors

The palette combines a cool lavender canvas with pearl work surfaces and an ink-violet anchor. Saturated colors are assigned by function, never scattered to make the screen look lively.

### Primary

- **Ink Violet:** The masthead, title plates, sticky dispatch docket, dark mobile navigation, and other high-authority instruments.
- **Action Cobalt:** Primary actions, the active destination rule, selected task tabs, standard selected MODs, and running state.

### Secondary

- **Signal Aqua:** Keyboard focus, the wordmark tile, build-option spine, interface/core MOD selection, and successful source analysis accents.
- **Signal Coral:** Delivery spine, active navigation index, camera MOD selection, and geometric editorial marks.

### Tertiary

- **Signal Sun:** Incomplete readiness, active probing, limited browser inspection, and other attention-without-failure states.
- **Verified Green:** Connected transport, valid source, completed checks, completed delivery, and ready pipeline state.
- **Failure Red:** Invalid source, failed analysis, failed delivery, destructive actions, and error toasts.

### Neutral

- **Cool Atlas Canvas:** Separates the working sheets and accepts narrow aqua/coral edge fields without becoming decorative wallpaper.
- **Pearl / Raised / Soft Surfaces:** Establish three levels for instruments, controls, and nested rows.
- **Atlas Ink / Muted Ink / Hairlines:** Carry primary copy, supporting copy, table structure, and precise boundaries.
- **Night Atlas Set:** Dark mode preserves the same hierarchy with violet-charcoal surfaces and brighter semantic signals.

### Named Rules

**The Chromatic Grammar Rule.** Cobalt means action or standard selection; aqua means focus, interface, or verified analysis; coral distinguishes camera and delivery; sun means waiting or limited; green means valid or complete; red means failed or destructive.

**The Pearl Majority Rule.** Most editable space remains pearl or neutral. Saturated color appears at decisions, categories, and state transitions, never as a blanket fill across every container.

**The Solid Workspace Rule.** Work sheets, fields, ledgers, and title surfaces use solid color, borders, and tonal layering. Glass and image-derived blur are limited to the compact mobile navigation lens, the authenticated profile sheet, and the compacting masthead; they must not spread into the working canvas.

## Typography

**Display Font:** IBM Plex Sans (with UI sans-serif and system fallbacks)

**Body Font:** IBM Plex Sans (with UI sans-serif and system fallbacks)

**Label/Mono Font:** JetBrains Mono (with monospace fallback)

**Character:** IBM Plex Sans gives Vietnamese and English interface copy an editorial but practical voice. JetBrains Mono creates a second register for URLs, source facts, versions, runner names, counts, stages, and identifiers.

### Hierarchy

- **Display:** Bold, tightly tracked, compact title-plate headings. The size expands from 32px to 48px but stays short and left-aligned.
- **Headline:** Eighteen-pixel section titles that sit beside numbered atlas markers.
- **Body:** Sixteen-pixel interface prose with a 1.5 line-height; supporting explanations step down to 10–14px according to density.
- **Data:** Twelve-pixel machine-readable values with compact line-height and reliable wrapping or truncation.
- **Label:** Nine-pixel tracked labels for indexes, runtime headings, state metadata, and counts; uppercase only where the content is genuinely a label.

### Named Rules

**The Two Registers Rule.** Sans-serif explains what the operator should understand; monospace carries what the system can identify, compare, or measure.

**The Short Display Rule.** Display type names the current destination. It never becomes marketing copy or a full-width inspirational slogan.

## Layout

The desktop canvas is capped at 1280px with 28px horizontal page padding. A 64px sticky masthead and 52px four-destination contents rail—Studio, Jobs, Catalog, and System—create a persistent instrument frame. Catalog is a searchable, read-only inventory of the exact device and MOD data used by Studio and every runner. Each operational view begins with a compact destination heading; Studio adds a three-cell runtime rail that connects orientation with live state.

The Studio recipe uses a flexible work column and a 320px sticky dispatch docket separated by a 16px gutter. Numbered dossier sections remain in the work column, with four-pixel chromatic spines indicating source, build, and delivery. Controls use compact internal rhythms; source facts form a measured grid rather than separate cards.

At 860px and below, the recipe returns to document flow, runtime cells stack, and navigation becomes a five-slot floating liquid bottom instrument. Studio, Jobs, Profile, Catalog and System are equal destinations; Profile uses the authenticated Telegram avatar as its tab mark. The capsule and moving lens use locally bounded translucency, backdrop blur, vibrancy, rim highlights and subtle chromatic edge separation. The lens slides or drags among all five slots with a restrained exponential ease-out and no bounce or elastic overscroll. When Profile is active the lens disappears and the avatar gains an image-derived halo, keeping identity distinct from work destinations. The page reserves at least 108px plus the device safe area so navigation and the compact dispatch action cannot cover fields or errors. At 390px, source facts and maintenance actions collapse to a single column. Short landscape restores the three-cell runtime rail while retaining bottom clearance.

View changes use a 380ms eased rise-and-fade. Controls transition color, border, shadow, and transform in roughly 180–220ms. Hover movement is limited to one pixel for work elements and two pixels for the active mobile destination. Reduced-motion preference collapses animation and smooth scrolling.

### Named Rules

**The Atlas Path Rule.** Orient with the title plate, expose runtime truth, then lead through numbered work sections to one dispatch docket.

**The Work Stays Reachable Rule.** Every fixed or sticky control receives matching content clearance and must never obscure an input, error, toast, or submit action.

**The Density Has Structure Rule.** Prefer grids, ruled rows, and indexed groups over a collection of interchangeable cards.

## Elevation & Depth

The atlas uses a restrained hierarchy of violet-tinted shadows. Low elevation separates runtime rails, dossier sheets, and operational ledgers from the cool canvas. Medium elevation belongs to title plates and the dispatch docket. The strongest floating shadow is reserved for the mobile navigation instrument and its out-of-view dispatch shortcut. Inner highlights are limited to framed tools such as Smart Source and the liquid navigation lens.

### Shadow Vocabulary

- **Sheet Lift** (`0 8px 22px rgba(38, 34, 86, .08)`): Major work sheets, runtime rail, ledgers, and a MOD group only while hovered.
- **Instrument Lift** (`0 18px 46px rgba(38, 34, 86, .13)`): Editorial title plates and the sticky dispatch docket.
- **Floating Navigation** (`0 24px 62px rgba(30, 27, 73, .2)`): Mobile bottom navigation only.

### Named Rules

**The Lift Has a Job Rule.** Elevation identifies a working plane, authoritative instrument, or mobile overlay. Do not repeat one soft shadow on every field, row, chip, and button.

**The Border Carries Detail Rule.** One-pixel hairlines remain the primary tool for internal structure; shadow never substitutes for row boundaries or selection state.

## Shapes

The form language mixes precise controls with selectively softer instruments. Fields and compact controls use four- to ten-pixel corners. Grouped MODs and source instruments use 12–14px corners. Major sheets use 16–18px corners. The mobile navigation is a deliberate 22px floating instrument with a 17px moving lens; the compact dispatch shortcut may use a capsule because it is a transient edge action, not a global control convention.

Circles are reserved for status lamps, readiness checks, the title-plate ring, and delivery nodes. The wordmark and numbered section markers use compact rounded squares with a slightly tactile, technical feel. One-pixel borders define almost every interactive boundary.

### Named Rules

**The Selective Softness Rule.** Larger radii identify major instruments; ordinary controls stay compact. Do not turn all controls into capsules or oversized rounded cards.

**The State Needs More Than Color Rule.** A selected MOD changes border, surface, and check mark together. Runtime and delivery states combine color with copy and shape.

## Components

### Buttons

- **Shape:** Primary actions use a 10px corner and a 46px minimum height; compact source analysis remains at least 40px high.
- **Primary:** Solid Action Cobalt, white text, confident weight, and a small violet-tinted action shadow.
- **Hover / Active:** Hover deepens to strong cobalt; active moves down one pixel and contracts slightly. No elastic or ornamental motion.
- **Focus:** A three-pixel Signal Aqua focus-visible ring remains independent of the button's semantic color.
- **Secondary:** Pearl or transparent controls use a hairline border; hover may borrow cobalt or aqua only when it clarifies action.

### Chips and Selectors

- **MOD selectors:** Groups are categorized. Standard selection uses cobalt, camera uses coral, and interface/core uses aqua. Every selected item gains a matching border, pale surface, and visible check mark.
- **Release-version editor:** The MOD-pack identity and its fixed default release label remain visibly paired. Editing uses one compact field and an explicit per-job apply action; the override resets after dispatch and never changes the pack default.
- **Pipeline choices:** Small square marks pair fill and inset contrast, so selection does not depend on hue alone.

### Cards / Containers

- **Dossier sheets:** Raised pearl surfaces with 18px corners, a one-pixel hairline, a low shadow, and a four-pixel semantic spine.
- **Operational ledgers:** Rows share a container and borders instead of becoming separate cards.
- **Internal padding:** Major sheets use 20–22px on desktop and 12–15px on narrow screens.
- **Editorial title plate:** Ink-violet with solid cobalt ring and coral block geometry; never a gradient or image-backed hero.

### Inputs / Fields

- **Style:** Raised pearl surface, strong hairline, four-pixel corners, visible mono label, and 44px minimum height.
- **Technical content:** ROM URLs, checksums, versions, sizes, and identifiers use JetBrains Mono.
- **Focus:** The field border becomes cobalt, while keyboard focus retains the global aqua ring.
- **Error / Disabled:** Errors stay adjacent to the failing instrument and use red state copy plus tonal fill. Disabled controls remain readable at reduced opacity.

### Navigation

Desktop uses a sticky four-cell contents rail with consistent line icons. Mobile adapts Kyant0's LiquidBottomTabs material model as a five-slot web control: a highly translucent, low-blur capsule contains one refractive lens and a raised center avatar for the Profile destination. The top sheen is omitted so page content remains visible through the dock; labels and icons use near-black in light mode and white in dark mode. The lens settles with a smooth exponential ease-out without bounce. The Profile destination suppresses the lens and identifies its active state with an avatar-derived halo plus a partial circular rim. Reduced-motion preference removes lens travel, halo scale and rotating greeting transitions.

### Authenticated Profile

The center avatar opens a full Profile destination rather than an interrupting popup. On mobile the view fills the working canvas behind the dock. The avatar is centered and its enlarged image becomes a saturated, bounded blur behind grouped glass facts; initials use a deterministic Telegram-ID color. Highlight facts and two-column detail groups create hierarchy without table styling. Every user-facing profile field remains visible except Mini App Open count, while the raw photo URL remains visual data rather than copy.

### Masthead Greeting

The masthead rotates one short operational greeting at a time: time-of-day greeting, a restrained build wish, and current Build Allowance/job context. A single quiet status dot replaces decorative emoji. On mobile the greeting occupies the flexible space between the wordmark and language control. Copy that exceeds the available width travels horizontally at a measured pace; short copy stays still. On scroll the surface remains highly transparent and increases only to a light blur, so underlying content remains visible and the foreground controls stay crisp. The greeting stops while the document is hidden and becomes static under reduced motion.

### Runtime Rail

Three cells expose runner choice, pipeline readiness, and recent job access. Aqua, sun, and coral top rules make the cells distinguishable; dots and text communicate the actual state. Waiting may pulse subtly, while ready changes to verified green.

### Smart Source

The ROM URL, source state, analysis control, and six metadata facts form one bordered instrument. Pasting identifies supported source types immediately. “Phân tích ROM” performs a small in-place inspection and updates the same view through `probing`, `analyzed`, `probe-limited`, or `probe-failed`; it must never send a Telegram payload or return the user to the bot. Limited browser inspection explains that build preflight will continue server-side rather than pretending analysis succeeded.

### Delivery State Row

ZIP, Drive, and Telegram stages support `pending`, `running`, `complete`, `failed`, and `skipped`. Node, copy, and state metadata change together; the color assignment follows the chromatic grammar.

### Dispatch Docket

The docket is the authoritative recipe summary. It shows three readiness checks, completed count, route summary, recovery copy, and exactly one submit action. An incomplete docket receives a sun border; it does not claim readiness until both source and device are valid. On compact screens, when the docket scrolls out of view, it becomes a small glass “Build” shortcut with a direction arrow and a deliberate gap above the dock. Activating it returns focus and scroll position to the full docket; it disappears when the docket is visible.

### Job Context and Events

Every active job exposes its device and ROM facts together with MOD-pack identity, release-version label, and the actual selected MOD names as bordered chips before the event stream. During upload, the progress area identifies the current file, file percentage, transferred bytes, speed, and ETA. Events are grouped by their actual named build step in compact ledger rows, while success and failure receive distinct tonal backgrounds. The default view shows the eight newest events; “View full log” expands every retained sanitized event and its structured details rather than exposing generic “step” labels. A release label shown in history or logs is the value persisted with that job, not a live reinterpretation of the pack's current label.

## Do's and Don'ts

### Do:

- **Do** keep runtime, source, pipeline, delivery, and readiness copy bound to real state.
- **Do** preserve the atlas reading path: compact destination heading, runtime rail, numbered dossier, dispatch docket.
- **Do** use cobalt, aqua, coral, sun, green, and red according to the Chromatic Grammar Rule.
- **Do** group MODs by function and show selection through border, tonal surface, and check mark.
- **Do** keep Vietnamese and English labels, errors, and recovery actions in parity.
- **Do** keep MOD-pack identity and its fixed default or current-job release override together in selection, job context, history, and logs.
- **Do** preserve 44px touch targets, visible keyboard focus, safe-area clearance, dark mode, and reduced motion.
- **Do** keep Smart Source analysis in place and distinguish browser-limited inspection from server-side preflight.

### Don't:

- **Don't** use gradients, glass surfaces, blurred blobs, or neon glows outside the intentionally bounded navigation, authenticated profile and compacting masthead moments.
- **Don't** turn every information group into the same rounded card with the same shadow.
- **Don't** add generic welcome copy, KPI theatre, abstract illustrations, or oversized marketing typography; the masthead greeting must remain short, personal and operational.
- **Don't** use color without a defined interaction, category, or state meaning.
- **Don't** make selected and unselected MODs differ only by fill intensity.
- **Don't** allow fixed navigation, toasts, or submit controls to obscure the work.
- **Don't** report a connected transport, analyzed ROM, ready recipe, running stage, or completed artifact unless the underlying state supports it.
