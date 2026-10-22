# Horizon Realty — dashboard design system

The source of truth for the staff dashboard (`/dashboard/**`), `/login` and the landing page
(`/home`). Tokens live in `styles/globals.css`; this file explains them and the patterns built on
them. The voice/chat widget (the public site's chat bubble and the standalone chat page at
`/chat`, which also hosts answered scheduled calls) deliberately keeps the original LiveKit starter look (see "Widget
isolation").

## Direction

Horizon Realty is a Dhaka agency whose AI agent answers buyers and renters by chat, voice and
phone, and calls leads back. Staff use the dashboard all day to read conversations, manage
listings and follow up on leads, so the interface is calm, dense and legible; the brand shows up
in one place only.

- **Evergreen** is the brand colour: the green of the river and the trees between the towers.
  It is the primary action colour and the sidebar surface.
- **Brass** is the sun sitting on the horizon. It is rare on purpose: the logo sun, the active
  nav marker, "featured" listings and chart series 2. Never for buttons or body text.
- Neutrals are **cool concrete** greys with a faint green cast. Not cream, not pure grey.
- The one memorable element is the **evergreen sidebar with the brass horizon mark** (and, on
  `/login`, the skyline brand panel). Everything else stays quiet: flat cards with hairline
  borders, no gradients as decoration, no drop shadows on cards.

## Colour tokens

shadcn variable names are kept so every `components/ui/*` file works unchanged. Values are oklch.

| Token                            | Light                               | Dark                                  | Use                                 |
| -------------------------------- | ----------------------------------- | ------------------------------------- | ----------------------------------- |
| `--background`                   | `0.975 0.004 175` concrete          | `0.17 0.012 200` night river          | page                                |
| `--foreground`                   | `0.22 0.02 190` ink                 | `0.95 0.008 175`                      | body text                           |
| `--card` / `--popover`           | white                               | `0.205 0.014 198` / `0.225 0.015 198` | panels, menus                       |
| `--primary`                      | `0.42 0.07 185` evergreen           | `0.8 0.1 175` mint evergreen          | primary buttons, links, focus       |
| `--primary-foreground`           | `0.985 0.005 175`                   | `0.2 0.03 190`                        | text on primary                     |
| `--secondary`                    | `0.94 0.012 175`                    | `0.26 0.018 195`                      | secondary buttons, neutral pills    |
| `--muted` / `--muted-foreground` | `0.955 0.006 175` / `0.5 0.018 190` | `0.24 0.014 198` / `0.72 0.015 185`   | table heads, hints                  |
| `--accent`                       | `0.94 0.018 178`                    | `0.28 0.025 190`                      | hover / selected rows               |
| `--destructive`                  | `0.55 0.2 27`                       | `0.7 0.17 25`                         | delete, errors                      |
| `--border` / `--input`           | `0.905 0.008 180` / `0.88 0.01 180` | white 9% / 14%                        | hairlines, inputs                   |
| `--ring`                         | `0.55 0.08 185`                     | `0.7 0.09 178`                        | focus ring (use at /50)             |
| `--brass`                        | `0.7 0.125 75`                      | `0.8 0.12 78`                         | sun, featured, active marker        |
| `--success`                      | `0.5 0.12 152`                      | `0.78 0.14 152`                       | completed, ready, confirmed         |
| `--warning`                      | `0.52 0.13 60`                      | `0.8 0.13 70`                         | missed, stale, needs attention      |
| `--info`                         | `0.5 0.12 245`                      | `0.76 0.1 240`                        | dispatched, in progress, processing |

Tailwind classes: `bg-brass`, `text-success`, `bg-warning/12`, `text-info`, etc. Status
colours are text-safe (≥4.5:1) on their own 12% tint over the card in both modes.

### Sidebar

| Token                  | Light                            | Dark                                 |
| ---------------------- | -------------------------------- | ------------------------------------ |
| `--sidebar`            | `0.285 0.045 190` deep evergreen | `0.145 0.012 200` (darker than page) |
| `--sidebar-foreground` | `0.95 0.01 175`                  | `0.93 0.01 175`                      |
| `--sidebar-primary`    | brass `0.8 0.12 78`              | same                                 |
| `--sidebar-accent`     | white 9%                         | white 7%                             |
| `--sidebar-border`     | white 10%                        | white 8%                             |

The sidebar is dark in both themes.

### Charts

`--chart-1` evergreen (main series), `--chart-2` brass, `--chart-3` blue, `--chart-4` rose,
`--chart-5` slate. Single-series charts use chart-1 only. Area fill: chart-1 at 28% → 0%.
Gridlines `stroke-border`, axis labels `fill-muted-foreground` 10–11px.

## Typography

- **Bricolage Grotesque** (`font-display`, weights 500/600/700): page titles, KPI figures,
  the wordmark, the login and landing headlines. Tracking `-0.02em` at 24px and up.
- **Public Sans** (`font-sans`, default): everything else. Kept from the widget, so `/` is
  unchanged.
- **Commit Mono** (`font-mono`): only for IDs, room names and code-like values. Not for labels.
- Numbers in tables and KPIs use `tabular-nums`.

Scale (px): 12 caption · 13 table/meta · 14 UI body (`text-sm`, default in the dashboard) ·
16 prose · 20 section title · 24 card headline · 30 page title (`text-3xl`, Bricolage 600) ·
44–56 login/landing headline. Sentence case everywhere; no all-caps labels, no eyebrow
labels above headings.

## Shape, space, elevation

- `--radius-base: 0.5rem`. Scale: `rounded-sm` 4px (tags), `rounded-md` 6px (buttons,
  inputs), `rounded-lg` 8px (cards, panels, tables), `rounded-xl` 12px (dialogs, sheets),
  `rounded-full` (status pills, avatars only).
- Spacing on a 4px grid. Page padding `px-4 sm:px-8`, `py-6 sm:py-8`; page max width
  `max-w-6xl`. Gaps: 8 inside controls, 16 between related fields, 24 between sections.
- Elevation: cards are flat (`border`, no shadow). Only popovers, menus and dialogs get a
  shadow. The topbar is `bg-background/85` with `backdrop-blur-sm`.
- Density: table rows 44px (`h-11`), controls 36px (`h-9`), touch targets ≥ 40px on phones.

## Layout

```
┌──────────┬──────────────────────────────────────────────┐
│ ☀ Horizon│ Agent / Conversations          ◐  Sign out  │  topbar (h-14, sticky)
│          ├──────────────────────────────────────────────┤
│ Overview │ Page title (Bricolage 30)        [actions]   │  PageHeader
│ Agent    │ description                                   │
│  Chatbot │ ┌──────────────────────────────────────────┐ │
│  ...     │ │ panel / table                            │ │
│ CRM      │ └──────────────────────────────────────────┘ │
│  Leads   │                                              │
└──────────┴──────────────────────────────────────────────┘
```

- Sidebar 240px from `md`; a 56px icon rail below it (labels in `title` + `sr-only`, a short
  rule in place of each group name). A rail rather than a drawer keeps every page one tap away
  with no open/close state.
- Content left-aligned; actions right-aligned in the PageHeader, wrapping under the title on a
  phone. No horizontal page scroll at 320px: tables scroll inside their panel.
- Hidden routes (`/dashboard/incoming/[id]`, `/dashboard/listen`) render in the shell but are
  not in the nav. `/dashboard/voice` redirects to `/dashboard/chatbot?tab=model`.

## Components (`components/dashboard/`)

| Component              | Pattern                                                                                                                                          |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `PageHeader`           | The page's single `<h1>` (same words as its nav label), optional description and actions.                                                        |
| `StatusPill`           | Dot + word, tones `neutral success warning danger info accent brass muted`. Never colour alone. `pulse` for in-flight states (motion-safe).      |
| `SwitchRow`            | Label + description on the left, `Switch` on the right; whole row is the label.                                                                  |
| `ConfirmDialog`        | `role="alertdialog"`, Cancel first, confirm button names the action ("Delete call").                                                             |
| `TableState` + `Panel` | Skeleton rows while loading, error + "Try again", or an empty state that says what to do next. `Panel` is the bordered card every table sits on. |
| `SecretKeyField`       | Write-only key input: empty = keep, "Remove saved key" = clear on save.                                                                          |
| `AreaChart`            | Inline SVG single-series area chart with hover tooltip; no chart library.                                                                        |
| `SectionCard`          | Titled card for pages with several panels (Overview, Chatbot tabs); heading, optional action, body.                                              |
| `FormField`            | Label, control, then hint or inline error (`aria-describedby`/`aria-invalid` wired through a render prop).                                       |
| `KpiTile`              | Label, Bricolage figure, optional sublabel/link; skeleton and "unavailable" variants. A fetch failure shows "—", never a fake 0.                 |

Status mapping (keep consistent across pages):

- Calls: pending → neutral, dispatched/in progress → info (pulse), completed → success,
  missed → warning, cancelled → muted, failed → danger.
- Bookings: proposed → info, confirmed → success, cancelled → muted.
- Leads: new → info, contacted → neutral, qualified → accent, booked → success,
  closed → muted, lost → danger.
- KB sources: pending/processing → info (pulse), ready → success, stale → warning,
  failed → danger, disabled → muted.
- Conversations: active → success (pulse), ended → muted.

## Writing

Sentence case. Buttons say what happens ("Add lead", "Schedule call", "Delete call"), and the
toast repeats the verb ("Lead added"). Errors say what failed and what to do; they don't
apologise. Empty states invite the next action.

## Accessibility and motion

Visible focus everywhere (`focus-visible:ring-ring/50 ring-[3px]`). Icon-only buttons have an
`aria-label`. Motion only answers an action (dialog open, menu, row added); `motion-safe:` for
pulses. Contrast ≥ 4.5:1 for text in both themes.

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

- Brass is the agent's voice: avatar ripples, the waveform while the agent speaks and the
  thinking arc. It is never used on buttons.
- Evergreen (`--primary`) is the caller: the halo and waveform while they speak, the open chat
  bubble and Send.
- The ripples and waveform are the only ambient motion, and they always mean that someone is
  speaking. With reduced motion, they change opacity only.
- The Call UI follows its own width (`@container`). From `@5xl` up, results sit in a 420px
  column on the left and the agent shifts right to stay clear of them. Below that, results rise
  as a sheet from the bottom.
- The chat bubble's panel goes fullscreen when a call starts. A call has no docked size.
