# telco. design system

The source of truth for the customer portal (`/portal/**`, public home page at `/`, log in at `/signin`), the admin portal
(`/dashboard/**`) and `/login`. Tokens live in `styles/globals.css`; this file explains them and
the patterns built on them. The voice/chat widget (the standalone `/chat` page and the chat
bubble panel) deliberately keeps the original LiveKit starter look (see "Widget isolation").

## Direction

telco. is a Bangladeshi mobile operator whose AI agent answers customers by chat and voice. Customers check balance, buy
packs and raise cases in the portal; staff run the network, support queue, offers and nudges
from the admin portal. Both share one look: calm panels, one indigo brand colour, and the
status accents carrying meaning.

- **Indigo** (`--brand` `#4f46e5`, `--brand2` `#756cf6` as the dark-mode primary) is the brand and
  the primary action colour.
- **Mint** (`#20b89a`), **orange** (`#ff9b55`) and **red** (`#e45b73`) are data and status accents,
  also chart series 2 to 4.
- Neutrals are cool blue-greys: page `#f5f7fb`, panels `--surface` white (dark `#141b2d`),
  hairlines `--line`.
- The memorable elements are the indigo gradient balance hero and the navy admin sidebar.
  Everything else is quiet: panel radius 17px, soft panel shadow, no decorative gradients.

## Colour tokens

Never hard-code a brand colour in a component; use a token class. shadcn names are kept so
`components/ui/*` works unchanged, and the reference palette names are added beside them.
Every token has a light value in `:root` and, where it differs, a dark value in `.dark`; each
is exposed to Tailwind as `--color-<name>` in the `@theme inline` block.

| Group | Tokens | Use |
| --- | --- | --- |
| Palette | `brand`, `brand2`, `mint`, `orange`, `red` | Brand and accents (`bg-brand`, `text-mint`) |
| Surfaces | `background`, `surface`, `surface2`, `line`, `card`, `muted`, `accent` | Page, panels, hairlines, hover and selected rows |
| Brand text | `brand-text` | Indigo text that stays readable in dark (`#a9a3ff`); use instead of `text-brand` for links and icons |
| Tints | `tint-purple`, `tint-green`, `tint-orange`, `tint-pink`, `tint-selected` | Icon wells, soft badges, selected option backgrounds |
| Status chips | `status-success`, `status-pending`, `status-failed`, `status-open` (+ `-foreground`) | Transaction and case statuses |
| Featured | `featured-border`, `featured-from`, `featured-to`, `featured-fg`, `featured-muted`, `featured-chip`, `featured-chip-fg` | The highlighted package or offer card |
| Hero | `hero-from`, `hero-via`, `hero-to`, `hero-soft`, `hero-muted`, `hero-dot` | Balance hero gradient and its text |
| Promo | `promo-from`, `promo-to`, `promo-foreground`, `promo-ink` | Sidebar upgrade card and white link buttons |
| Overlays | `scrim`, `toast`, `toast-foreground`, `chat-canvas`, `chip-border` | Dialog scrim, SMS toast, assistant canvas, suggestion chips |
| Third party | `bkash`, `nagad` | Payment option marks |
| Avatars | `persona-1-from` to `persona-5-to`, `brand-start` | Persona and logo gradients (same in both themes) |
| Sidebar | `sidebar*` | Admin sidebar, dark in both themes |

Only drop-shadow alpha literals such as `shadow-[0_25px_70px_#0003]` stay inline.

## Typography

**Inter** for everything (`font-sans`, `font-display`); Commit Mono (`font-mono`) only for IDs
and code-like values. Numbers in tables and KPIs use `tabular-nums`. Sentence case, no all-caps
labels.

## Shape, space, elevation

- Radii: `rounded-panel` 17px, `rounded-metric` 16px, `rounded-hero` 20px, `rounded-button`
  10px. `--shadow-panel` is the only card shadow; dialogs and menus use larger ones.
- Breakpoints (custom variants): `tablet:` at 1100px and below, `phone:` at 760px and below
  (the off-canvas sidebar), `narrow:` at 390px and below. No horizontal page scroll at 390px.
- Touch targets at least 40px on phones.

## Layout

- Portal: left sidebar, topbar with the notification bell and profile menu, content panels in a
  responsive grid. The assistant is a full page at `/portal/assistant` and a bubble elsewhere.
- Admin: navy sidebar from `components/dashboard/shell/nav-items.ts`, page header with the
  single `<h1>`, tables and panels reusing `components/portal/ui/*`. The Support queue item
  carries an open-case badge.

## Writing

Sentence case. Buttons say what happens ("Run nudges now", "Resolve case") and the toast
repeats the verb. Money is shown as `৳ 486.50`. Errors say what failed and what to do; empty
states invite the next action.

## Accessibility and motion

Visible focus everywhere (`focus-visible:ring-ring/60 ring-[3px]`). Icon-only buttons have an
`aria-label`. Motion answers an action and is wrapped in `motion-safe:`. Text contrast at least
4.5:1 in both themes.

## Widget isolation

`app/(widget)/layout.tsx` (the `/chat` page) renders `<div data-surface="widget">`. While it is mounted,
`:root:has([data-surface='widget'])` in `globals.css` restores the original neutral tokens for
the whole document (so its portals match), and `getStyles()` injects the configurable accent at
the same specificity. The chat bubble's panel (`components/chat-bubble/`) is mounted on every
public page, so it uses `data-surface="widget-panel"` instead: the same tokens and accent
(`getStyles(config, 'panel')`), scoped to the panel element so the page around it keeps the
brand look. Don't add brand styling to the widget through these tokens.

### Call screen

The in-call view (`components/agents-ui/blocks/agent-session-view-01`, pieces in
`components/app/call/`) is the exception: it is always dark and uses the brand tokens. Its
section carries `.dark` and `data-surface="call"`, which override the widget tokens above (and
the configurable accent) inside the call only. It has two parts:

- **Call UI**: the agent's avatar, Mic / End call / Speaker, and the latest search result or a
  booking form over the call. A new search fades the previous result out.
- **Conversation UI**: the transcript and message box. The chat bubble in the call's corner
  opens it as a 400px pane on the right, like a meeting's chat. On a narrow screen it covers the
  call instead.

The rules for this screen:

- Orange is the agent's voice: avatar ripples, the waveform while the agent speaks and the
  thinking arc. It is never used on buttons.
- Indigo (`--primary`) is the caller: the halo and waveform while they speak, the open chat
  bubble and Send.
- The ripples and waveform are the only ambient motion, and they always mean that someone is
  speaking. With reduced motion, they change opacity only.
- The Call UI follows its own width (`@container`). From `@5xl` up, results sit in a 420px
  column on the left and the agent shifts right to stay clear of them. Below that, results rise
  as a sheet from the bottom.
- The chat bubble's panel goes fullscreen when a call starts. A call has no docked size.
