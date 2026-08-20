# Wukong ROM Studio design system

## Direction

The Telegram Mini App is a **Minimalist Editorial technical dossier**. It
treats a ROM build like a numbered production document: source, configuration,
delivery, result. It deliberately rejects the soft cards, rounded dashboard
chrome, gradients, glass and interchangeable “AI SaaS” look.

The product remains an Operate interface. The editorial system exists to make
complex choices easier to audit, never to hide state or replace familiar form
controls.

## Material and typography

- Light mode uses warm technical stock `#f1efe8`, a near-white working sheet
  `#fbfaf5`, and carbon ink `#151515`.
- Dark mode preserves the paper/ink relationship with `#171716`, `#222220`
  and `#f0eee6`; it is selected by the user's system.
- One cobalt signal comes from Telegram's button color, with `#1756d8` as the
  fallback. It is reserved for selection, active navigation and dispatch.
- Success and destructive state retain semantic green and red. Neither is
  used decoratively.
- Literata carries only primary editorial headlines. Archivo Narrow carries
  interface copy; tabular identifiers, hashes and measurements use its
  numeric forms rather than decorative monospace.
- Borders are square 1–3 px rules. Controls have zero radius. There are no
  shadows, gradients, blur layers or glass surfaces.

## Information architecture

Five indexed destinations map the Windows operating model to mobile:

1. **Studio** — source library entry, task choice, runner, preset, complete MOD
   selection, pipeline, packaging, Drive publishing and Telegram notification.
2. **Jobs** — list, inspect, events, artifact, cancel and checkpoint resume.
3. **Library** — sources, artifacts, source mirror and retention policy.
4. **Catalog** — searchable devices, verified content-pack versions and the
   complete MOD inventory exported from the shared catalog.
5. **System** — diagnostics, connection status, cache inspection/clear and
   local Mini App defaults.

Credentials remain outside the Mini App. GitHub, Telegram and rclone secrets
are managed through Windows DPAPI or GitHub Secrets; this security boundary is
stated in the System screen rather than represented by disabled password
fields.

## Composition and interaction

- Desktop uses a 1180 px editorial sheet, a horizontal contents index and a
  sticky dispatch docket beside the build form.
- Mobile uses one column and a five-cell bottom index. A compact persistent
  dispatch action sits above that index while the full docket remains the final
  recipe section; extra bottom spacing prevents either control obscuring fields.
- Real sequential numbers are used only where order matters: recipe sections,
  pipeline stages, job actions and canonical job states.
- The complete MOD list is visible on mobile. Desktop may scroll the bounded
  list while still showing the selected count and bulk selection controls.
- One reveal motion uses clip-path when changing destinations. Reduced-motion
  preference removes it.
- Vietnamese is the default and English is maintained as a complete parallel
  vocabulary. Language and default preset persist per browser profile.

## GitHub Actions presentation

Actions is the same product surface expressed as an operational log:

- Jobs and setup steps use numbered Vietnamese/English titles.
- Runtime pipeline events open GitHub log groups for source download, payload,
  partitions, MOD, metadata, repack, super/vbmeta/vendor_boot, ZIP, upload and
  final publication.
- Each completed stage emits a GitHub notice with duration where available;
  failures emit an error annotation carrying the stage title.
- Job Summary records job ID, device, task, runner, recipe digest, MOD pack,
  preset, selected MOD count and artifact size/SHA/link.
- Presentation is an adapter only. The orchestrator and manifest remain the
  source of truth for state, progress and ownership.

## Accessibility floor

Native inputs and semantic buttons retain keyboard behavior. Focus is a 3 px
cobalt outline; touch controls target 44 px where practical. Text contrast is
at least 4.5:1, icons never replace action labels, status messages are live,
and horizontal overflow is tested at 390 px and 1440 px.
