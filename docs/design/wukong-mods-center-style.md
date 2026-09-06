# Wukong Mini App — monochrome interface specification

Status: implementation source of truth

Reference density: `8dededd`
Visual references: [Mods Center](https://modscenter.org/), [Modules](https://modscenter.org/modules), [Patcher](https://modscenter.org/patcher)

## Direction

Wukong uses a white, black and neutral gray foundation with a restrained lavender accent. The interface keeps the compact rhythm of the established Studio while adopting the clear hierarchy, hairline borders, quiet surfaces and strong type of Mods Center. Wukong artwork, the five-slot dock and its center avatar remain product identifiers. No third-party artwork, copy or layout source is reused.

The runtime stays HTML, CSS and JavaScript. This document records the intended result and owns design decisions; it is not a runtime UI format.

## Baseline

The pre-redesign production source uses IBM Plex Sans and JetBrains Mono, a warm `#f3f1eb` canvas, cobalt `#315f9e` actions and an initial CSS bundle of 118,503 bytes / 21,134 gzip bytes. The four existing WOFF2 subsets total 106,780 bytes. Baseline screenshots are captured by the Playwright fixture at exact viewports; `8dededd` remains the density comparison.

## Tokens

| Role | Light | Dark |
|---|---|---|
| Canvas | `#fafafa` | `#0a0a0a` |
| Surface | `#ffffff` | `#141414` |
| Soft surface | `#f5f5f5` | `#262626` |
| Text | `#0a0a0a` | `#fafafa` |
| Muted text | `#737373` | `#a3a3a3` |
| Border | `#e5e5e5` | `rgba(255,255,255,.10)` |
| Strong border | `#d4d4d4` | `rgba(255,255,255,.18)` |
| Lavender | `#a7b2f7` | `#d3dbff` |
| Lavender text | `#5967bb` | `#d3dbff` |

Primary actions are black with white text in light mode and white with black text in dark mode. Lavender marks selection, focus, progress and dock illumination. Green, amber and red are reserved for operational state.

Spacing uses 4, 8, 12, 16, 20, 24 and 32 px. Cards use 12–16 px radii, controls 8–10 px and pills only for badges or capsule actions. Ordinary cards use a one-pixel border and no shadow. Shadows belong to dialogs, the mobile action and the liquid dock.

## Typography

Geist Sans is the interface face and Geist Mono is used for identifiers, versions, checksums and event data. Both are served locally as WOFF2 with Vietnamese glyphs and `font-display: swap`.

| Element | Mobile | Desktop |
|---|---:|---:|
| Body | 14 px | 15 px |
| Form control | 16 px | 14–15 px |
| Informational label | 11–12 px | 11–12 px |
| Technical data | 11–12 px | 11–12 px |
| H1 | 28 px | 38–40 px |
| H2 | 18–20 px | 18–20 px |
| H3 | 15–16 px | 15–16 px |
| Dock label | 10 px minimum | 11 px |

Every primary interactive target is at least 44 × 44 px. Compact controls reduce visual padding while preserving that hit box.

## Component ownership

- `tokens.css` owns color, type, radius, shadow, safe-area and motion tokens.
- `fonts.css` owns local font faces.
- `components.css` owns shared controls, cards, status, dialogs, jobs and library primitives.
- `screens.css` owns responsive screen composition and dark-mode mappings.
- `dock.css` owns masthead, desktop navigation, dock, profile and admin detail surfaces.
- `studio.css` owns the source → configuration → delivery → review workflow.

Selectors are changed in their owning file. New catch-all override blocks at the end of the cascade are not accepted.

## Layout

### Header and navigation

Desktop uses a 64 px header: wordmark and page breadcrumb at left, the four workspace destinations in the center, and connection/language/profile controls at right. The active destination uses strong text and a short lavender underline. The five-slot dock remains available as the persistent direct navigator on both desktop and mobile; mobile uses a 56–60 px header with the wordmark, a single-line greeting and language control.

### Liquid dock

The dock keeps five equal slots with the avatar in slot three on desktop and mobile. It remains 68–72 px high and retains the moving liquid lens, blur, glow and haptics. Its glass becomes neutral white/black and its chromatic illumination becomes lavender. Animations pause when the page is hidden and collapse under reduced-motion preferences.

### Studio

The workflow remains three numbered sections: ROM source, ROM configuration and build delivery. Desktop keeps a two-column workbench with a sticky review docket. Mobile uses one compact column, 14–16 px card padding, 44 px controls and a solid primary action above the dock. Preset, edition and MOD release appear before advanced MOD, debloat and pipeline controls. Important ROM facts use a two-column summary and technical facts remain disclosed.

### Jobs and library

The active job leads with state, current stage, last update and next action. History uses bordered cards; filters collapse on mobile. Logs use Geist Mono and remain bounded to 500 rendered events.

The library follows the Mods Center browsing rhythm: desktop filter rail plus a two/three-column card grid, and a one-column mobile list with compact filters. Every card keeps its title, short description, compatibility metadata and full-width detail action in a stable layout.

### System, admin and profile

System health uses a monochrome ledger with semantic status dots. Admin tables become cards on narrow screens and preserve selections after failures. Profile uses a solid surface with an avatar focal point instead of a full-screen blurred photo. Authentication, maintenance and empty states use a centered card with one primary recovery action.

## Interaction states

- Hover changes border or soft surface; it never moves the layout.
- Pressed state uses a one-pixel visual compression or darker fill.
- Selected state uses lavender surface/border plus an icon or label change.
- Disabled state keeps readable text at reduced contrast and removes shadow.
- Loading uses stable skeleton dimensions.
- Focus uses a three-pixel visible ring with two-pixel offset.
- Error copy is adjacent to its control and never clears user input.

Motion is 120–200 ms with the existing ease curve. Reduced motion limits transitions and animations to effectively zero. Blur is restricted to the scrolled masthead, dialogs and the liquid dock.

## Acceptance matrix

Required viewports are 320 × 720, 390 × 844, 768 × 1024, 1280 × 800 and 844 × 390. Studio, Jobs, Library, System/Admin and Profile are checked in Vietnamese and English, light and dark, reduced motion, loading/error/empty states and with long data. Exact `innerWidth`, no horizontal overflow, visible focus, 44 px hit targets, mobile 16 px inputs and unobscured keyboard interactions are release gates.

Initial JavaScript may not grow by more than five percent. CSS gzip may grow by at most 15 KB, local WOFF2 assets remain below 200 KB total, and admin/ZIP code stays lazy. Local interaction p95 remains below 200 ms under the established Chromium 4× CPU profile.

## Implementation evidence — 2026-09-06

The shipped source now follows this specification across Studio, Jobs, Library, System/Admin and Profile. Desktop navigation is part of the masthead; the liquid dock is the five-slot navigator on desktop and mobile. Studio uses a compact three-cell runtime strip, a four-fact ROM summary, disclosed technical metadata and disclosed advanced build controls. Profile is a solid card and no longer renders the Telegram photo as a blurred page background.

Reference captures from the authenticated deterministic fixture:

| Screen | 390 × 844 | 1280 × 800 |
|---|---|---|
| Studio | [mobile](screenshots/mods-center-style/build-390.png) | [desktop](screenshots/mods-center-style/build-1280.png) |
| Jobs | [mobile](screenshots/mods-center-style/jobs-390.png) | [desktop](screenshots/mods-center-style/jobs-1280.png) |
| Library | [mobile](screenshots/mods-center-style/catalog-390.png) | [desktop](screenshots/mods-center-style/catalog-1280.png) |
| System | [mobile](screenshots/mods-center-style/system-390.png) | [desktop](screenshots/mods-center-style/system-1280.png) |
| Admin | [mobile](screenshots/mods-center-style/admin-390.png) | [desktop](screenshots/mods-center-style/admin-1280.png) |
| Profile | [mobile](screenshots/mods-center-style/profile-390.png) | [desktop](screenshots/mods-center-style/profile-1280.png) |

The repository budget tool measured the first-party static import closure with `python tools/mini_app_bundle_budget.py --baseline 8dededd`. Initial JavaScript changed from 336,297 raw / 87,864 gzip bytes to 185,540 raw / 56,094 gzip bytes: reductions of 44.8% raw and 36.2% gzip. CSS changed from 109,578 raw / 19,062 gzip bytes to 117,074 raw / 20,564 gzip bytes, an increase of 1,502 gzip bytes. Geist Sans and Geist Mono total 141,020 bytes. The clean build contains nine versioned assets; admin, ZIP metadata and fflate remain separate lazy chunks.
