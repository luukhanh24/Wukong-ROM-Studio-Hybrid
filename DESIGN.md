# Wukong ROM Studio design system

## Direction

The Telegram Mini App uses the **Build Flight Deck** operating model: one
continuous, inspectable route from source ROM to runner, MOD plan and delivery.
It inherits the Windows application's Fluent graphite/blue visual language and
does not introduce a separate Telegram brand.

The surface is an Operate interface. Clarity, touch reach, truthful system
state and recovery from errors take precedence over decorative expression.

## Visual tokens

- Background: Telegram `secondary_bg_color`, with `#eef1f4` fallback.
- Surface: Telegram `bg_color`, with white fallback.
- Text and muted text: Telegram `text_color` and `hint_color`.
- Accent: Telegram `button_color`, with Wukong blue `#0878d1` fallback.
- Success: `#16853b`; destructive actions use Telegram's destructive color.
- Radius: 14 px for sections, 9–11 px for controls.
- Typography: system UI stack headed by Segoe UI Variable on Windows and the
  native platform font in Telegram.
- Dividers are thin and low contrast; shadows only establish sticky launch and
  app-bar elevation.

## Structure

The build surface is ordered as a flight plan:

1. Source ROM and task.
2. Runner, edition, private content-pack, MODs and advanced pipeline stages.
3. Packaging, Drive publishing and Telegram notification.
4. A sticky launch summary that always names device, edition/task and runner.

Jobs, Cloud and System are peer destinations in a four-item bottom navigation.
Their actions return authenticated results to the Telegram chat, where longer
logs and artifact links remain readable and shareable.

## Responsive behavior

- Mobile is the primary layout: single-column fields, two-column MOD grid above
  390 px, one column below it, full-width launch action and safe-area padding.
- Desktop keeps the same mental model in a centered 1060 px workspace, using
  two/three-column field groups and a three-column MOD grid.
- The launch bar and bottom navigation remain reachable without obscuring the
  final content; reduced-motion preferences remove nonessential animation.

## Interaction and content rules

- Vietnamese is the default; English is a complete parallel vocabulary.
- Presets select real MOD defaults exported from verified content-pack
  manifests. Users may choose defaults, all or none, then inspect the exact
  selected count.
- Source mirror hides build-only controls. Runner and selection changes update
  the launch summary immediately.
- Validation errors identify the field and stay in the current view. Requests
  above Telegram's 4096-byte limit are rejected before transmission.
- Mini App payloads never include identity or credentials. Telegram chat
  identity remains the authority for job ownership and permissions.
- The chat menu creates a one-time reply-keyboard Web App button. This is the
  Telegram transport that delivers `sendData` to the long-polling daemon; an
  inline or persistent menu-button launch must not replace it without a public
  backend that verifies Telegram `initData`.

## Accessibility floor

All controls use native form elements or semantic buttons, visible focus rings,
44 px-class touch targets where practical, live status messages and sufficient
contrast through Telegram theme variables. Icons supplement text and never
carry an action's meaning alone.
