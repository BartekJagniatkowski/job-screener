# Dashboard hero with interactive dot-grid background

Branch: `feature/dashboard-hero-dotgrid`

## Problem

The dashboard's main entry point — the URL/text command bar — currently has no
visual prominence. It sits directly below a couple of conditional notices with
no heading, no breathing room, and nothing to draw the eye. The ask is to make
it the clear focal point of the page: pushed down a bit, more space around it,
and a "dot-grid notebook paper" background that reacts to mouse movement for a
modern feel.

## Scope

Dashboard page only (`templates/dashboard.html`). No other page gets this
treatment in this pass.

## Design

### Layout

A new `.dashboard-hero` section replaces the current bare jump from notices
straight into `.cmd-zone`:

```
[ existing conditional notices: no-api-key / no-cv ]

.dashboard-hero
  ├─ canvas.hero-dots          (absolutely positioned, full hero width/height, behind content)
  ├─ h1.hero-title             "Screen before you apply."
  ├─ p.hero-sub                "Paste a listing. Six layers of analysis tell you if it's worth your time."
  └─ .cmd-zone                 (existing command bar, unchanged markup)

[ existing: source-status / loading / error-box / result-box ]
[ existing: history-search-wrap / filter-bar / table ]
```

`.dashboard-hero` gets generous vertical padding (~64–80px top/bottom) so the
dot grid reads as a band, not a sliver. `.cmd-zone`'s bottom margin increases
for more separation from the filter bar/table below. The notices (no-api-key,
no-cv), when present, stay above the hero — they're warnings, not part of the
inviting "main entry point."

### Dot grid mechanics

Plain vanilla JS, no dependencies. **Note:** this codebase has zero standalone
`.js` files — every page's JS lives inline in its own template. This section
originally proposed `static/hero-dots.js`; the implementation plan follows
the established convention instead and adds the logic as an inline
`<script>` block in `dashboard.html`, right after the `.dashboard-hero`
markup.

- Canvas sized to match `.dashboard-hero`'s bounding box, resized on window
  `resize` (and on `DOMContentLoaded`).
- Grid: dots every `28px` in both axes, base radius `1.5px` — even spacing,
  reads like dot-grid notebook paper, not a density-varying halftone.
- Base color: read from `var(--border-light)` via
  `getComputedStyle(document.documentElement)` so it's theme-correct
  automatically; re-read whenever the `data-theme` attribute changes (the
  existing theme-toggle script already flips this attribute — `hero-dots.js`
  listens for the click/keydown that does it, or simpler: a `MutationObserver`
  on `documentElement`'s `data-theme` attribute).
- Mouse proximity: on `mousemove` within the hero, dots within a `140px`
  radius of the cursor scale up to `4px` and blend color toward
  `var(--accent)`, falloff by distance (linear interpolation is enough — no
  need for easing curves).
- The animation loop (`requestAnimationFrame`) only runs between
  `mouseenter`/`mouseleave` on the hero element. Outside that, the canvas
  paints the static grid once and the script does nothing — zero idle CPU.
- `window.matchMedia('(prefers-reduced-motion: reduce)').matches` → skip the
  mousemove listener and rAF loop entirely; static grid only, no JS work
  beyond the initial paint.

### Accessibility

- Canvas is purely decorative: `aria-hidden="true"`, no interactive semantics.
- Respects `prefers-reduced-motion` as above.
- Headline/subhead are normal `<h1>`/`<p>` — no contrast issues since the dot
  grid is low-opacity and sits behind text, not under it directly (or if
  directly behind, dots are subtle enough — `var(--border-light)` is already
  calibrated for low contrast against `var(--bg)`).

### Out of scope

- No idle/ambient animation when the mouse is away (confirmed: static until
  interaction).
- No mouse-tracking on any other page.
- No new dependencies, no build step, no ASCII character rendering (plain
  dots only).

## Files touched

- `templates/dashboard.html` — new `.dashboard-hero` markup wrapping the
  existing `.cmd-zone`, plus an inline `<script>` block for the canvas/
  animation logic (see note above)
- `static/style.css` — `.dashboard-hero`, `.hero-title`, `.hero-sub`, canvas
  positioning/z-index, adjusted `.cmd-zone` spacing

## Testing

Manual verification only (per project convention — no JS test suite exists):
- Visual check in both themes, dot color matches `--border-light`/`--accent`
  correctly in each
- Mouse movement over the hero grows/brightens nearby dots; moving away
  reverts them
- `prefers-reduced-motion` (toggle via browser devtools) shows a static grid,
  no console errors, no listeners firing
- Resize the window — canvas/grid stays aligned, no stretching artifacts
- Existing dashboard functionality (analyze button, command bar, history
  table/filters) unaffected
