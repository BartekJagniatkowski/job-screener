# Job Screener CLI — Textual TUI Rewrite

Branch: `cli-tui`. Learning project — not required to ship as a finished product.
Supersedes the line-based REPL (`cmd.Cmd` + `rich`) built on branch `cli-tool`,
already merged to `main`.

## Goal

Replace `cli.py`'s line-based REPL with a full-screen, keyboard-navigable TUI
using Textual — closer to `CLI/terminal.html`'s shortcuts-row implication
(arrow-key navigation through results, single-key actions) than a REPL where
every action requires typing a full command and pressing Enter. Also adopt
`terminal.html`'s color palette (see Theming section) so the real tool looks
like the mockup, not just behaves like it.

## Architecture

- `cli.py` is rewritten around a `textual.app.App` subclass, `JobScreenerApp`.
- New dependency: `textual` (`uv add textual`). Pairs with the already-installed
  `rich` — Textual is built on top of it, same ecosystem (Textualize).
- Still imports `database.py`/`analyzer.py`/`scraper.py` directly — no HTTP
  layer, same SQLite DB, same trust model as the REPL version.
- Critical constraint: Textual runs on an asyncio event loop. The blocking
  network calls (`scraper.fetch()`, `analyzer.analyze()`) MUST run inside a
  worker thread via `self.run_worker(fn, thread=True)` (or the `@work(thread=True)`
  decorator) — calling them directly on the event loop would freeze the entire
  UI (no redraws, no input) for the duration of the scrape + API call.

## Screens

### `LoginScreen` (initial screen)
- A Textual `Input` widget for username, submitted on Enter.
- Calls `database.get_user(username)`. `None` → inline error label, input
  stays focused, retry. Valid → `self.app.push_screen(BrowseScreen(user))`
  (replacing the login screen, not stacking on top of it — use
  `switch_screen` or pop+push so login isn't reachable via Esc/back).
- No password — same trust model as the REPL version and `delete_user.py`.

### `BrowseScreen` (default/main screen after login)
- A `DataTable` widget, columns: DATE, ROLE · COMPANY, VERDICT, LAYERS, FIT, ID
  — same data and column set as the old `do_list`, sourced from
  `database.get_jobs(user_id)`.
- Arrow keys / `j`/`k` move the `DataTable`'s built-in row cursor. `Enter` on
  a focused row pushes `DetailScreen` for that job's id.
- Keybindings (via Textual `BINDINGS` class attr, also auto-shown in the
  `Footer` widget):
  - `f` — cycle the status filter: All → Rejected → Applied → Warning →
    Worth Considering → Interview → Offer → All. Filter state shown in the
    screen's title/subtitle bar so it's never ambiguous which filter is active.
  - `a` — push `AnalyzeScreen`.
  - `?` — push the help `ModalScreen` overlay.
  - `q` / `Escape` — quit the app (`self.app.exit()`).
- Re-fetches `database.get_jobs(user_id)` whenever the screen regains focus
  (e.g. returning from `AnalyzeScreen` after a successful save) so a newly
  analyzed job appears without restarting the app.

### `DetailScreen` (pushed from `BrowseScreen`)
- Replaces `show <id> [--full]`. Calls `database.get_job(id, user_id)` on mount.
- Renders: verdict summary, then layer panels (triage/product/business —
  always shown — plus reputation/values/fit toggled by a `f` keybinding,
  mirroring the old `--full` flag but as a live toggle instead of a relaunch).
- `Escape` pops back to `BrowseScreen` (preserving its filter/cursor state —
  Textual's screen stack handles this automatically as long as `BrowseScreen`
  isn't rebuilt from scratch on pop).

### `AnalyzeScreen` (pushed from `BrowseScreen` via `a`)
- An `Input` for a URL or pasted listing text, plus a status/output area below.
- On submit: if the input starts with `http://`/`https://`, normalize via
  `scraper.normalize_url()` then run `scraper.fetch()` in a worker thread;
  show "Fetching..." in the status area while it runs. Scrape failure → show
  the error code/detail inline, keep the input editable for a retry or a
  pasted-text fallback.
- Before calling the API: `database.check_duplicate(user_id, source)`. If a
  duplicate exists, replace the status area with an inline confirm
  (e.g. two buttons, "Re-analyze" / "Cancel", or a single-key y/n prompt
  rendered as text) instead of the REPL version's blocking `input("> ")`.
- On confirmed analyze: run `analyzer.analyze(...)` in a worker thread,
  status area shows "Analyzing...". On success: `database.save_job(...)`,
  status area shows "Saved #NNN — VERDICT", and a keybinding (or auto-pop
  after a short delay) returns to `BrowseScreen` with the list refreshed.
  On failure at any step (scrape/API/save): status area shows a clear error,
  input stays editable, no crash.
- `Escape` cancels and pops back to `BrowseScreen` without side effects
  (only safe before the worker has started a real API call — once "Analyzing..."
  is showing, `Escape` should be disabled or only cancel the *screen*, not the
  in-flight API call, since there's no cheap way to abort a live HTTP request
  cleanly from here).

### Help overlay (`ModalScreen`)
- Triggered by `?` from `BrowseScreen`. Lists all keybindings across screens
  in one static text block. Dismissed by any keypress.
- Textual's `Footer` widget (shown at the bottom of `BrowseScreen` and other
  screens) already surfaces the active screen's bindings automatically —
  the help overlay is a supplementary reference, not the only way to discover
  keybindings.

## Data flow (per screen, restated for clarity)

- `BrowseScreen` ← `database.get_jobs(user_id)` (on mount, on filter change,
  on refocus after `AnalyzeScreen` pop).
- `DetailScreen` ← `database.get_job(job_id, user_id)` (on mount).
- `AnalyzeScreen` → `scraper.normalize_url()` → `scraper.fetch()` (worker
  thread, URL input only) → `database.check_duplicate()` → `analyzer.analyze()`
  (worker thread) → `database.save_job()`.

## Error handling

Every failure mode that printed a `console.print("[red]...[/red]")` line in
the REPL version becomes inline screen state instead of a printed line — no
behavior is dropped, just re-homed:
- Unknown username (`LoginScreen`)
- Scrape failure: `timeout`/`notfound`/`blocked`/`network` (`AnalyzeScreen`)
- Missing `ANTHROPIC_API_KEY` (`AnalyzeScreen`, checked before any worker runs)
- `analyzer.analyze()` exception (`AnalyzeScreen`)
- `database.save_job()` exception, kept distinct from the analyze-failure
  message (carried over from the REPL version's fix — analysis-succeeded-but-
  save-failed must read differently than analysis-failed)
- Invalid/missing job id (`DetailScreen` — though `DataTable` selection means
  this mostly can't happen via normal navigation; still guard `get_job`
  returning `None` defensively)

## Testing

Still an explicitly-scoped learning project — no enforced test suite for this
branch. Textual ships `App.run_test()` for driving a TUI in tests if ever
wanted later; not required for v1. Manual testing means actually launching
the app and navigating with the keyboard, screen by screen.

## Theming — match `CLI/terminal.html`'s palette

A custom Textual `Theme` (Textual's built-in theming API,
`textual.theme.Theme`), registered on the app and set as the default, using
these exact values lifted from `CLI/terminal.html`'s `:root` CSS variables:

```python
from textual.theme import Theme

JOB_SCREENER_THEME = Theme(
    name="job-screener",
    primary="#39bae6",      # --accent (cyan) — focused widgets, headers
    secondary="#ffb454",    # --warn / --prompt (amber) — prompt, warnings
    background="#0a0e14",   # --bg
    surface="#0a0e14",      # no separate surface tone in terminal.html; reuse bg
    panel="#0a0e14",
    success="#7fd962",      # --success (green)
    warning="#ffb454",      # --warn (amber)
    error="#f07178",        # --danger (coral/red)
    foreground="#d5d8da",   # --fg
)
```

Mapped usage, mirroring `terminal.html`'s class-to-color rules:
- Verdict colors: `REJECT`/red findings → `error` (#f07178), `REVIEW`/warning
  → `warning` (#ffb454), `CONSIDER`/worth_considering → `success` (#7fd962).
  This replaces the REPL version's ad-hoc `VERDICT_COLOR`/`DOT_COLOR` dicts —
  same three-way mapping, now sourced from the theme instead of hardcoded
  Rich color names (`"red"`/`"yellow"`/`"green"` → theme tokens).
- Layer status dots in `BrowseScreen`'s `DataTable`: pass → `success`,
  partial → `warning`, fail → `error` (same as `terminal.html`'s
  `.dot.pass`/`.dot.partial`/`.dot.fail`).
- Muted/dim text (timestamps, hints, secondary labels) → `#747c84`
  (`--muted`), applied via Textual's `dim` style or a custom CSS class rather
  than the theme's named colors (Textual themes don't have a dedicated
  "muted" slot — use a TCSS rule, e.g. `.muted { color: $text-muted; }`,
  or fall back to a literal `#747c84` in a CSS class since this is a fixed
  palette, not a user-switchable theme).
- ID labels (`#001` style) → `primary` (cyan), matching `.accent` in
  `terminal.html`.
- Font: Textual runs in the user's actual terminal, so it inherits whatever
  monospace font the terminal emulator is configured with — `terminal.html`'s
  `--font-mono` stack (SF Mono / JetBrains Mono / Menlo / Monaco / Courier
  New) cannot be forced from inside a TUI. No action possible here; not a gap
  in the implementation, just an inherent limitation of terminal apps vs. a
  browser-rendered mockup.
- `terminal.html`'s blinking cursor (`.analyzing { animation: blink }`) has a
  rough equivalent: Textual's `LoadingIndicator` widget, shown in
  `AnalyzeScreen` while a worker thread is running (covers the "Fetching..."/
  "Analyzing..." states that were plain dim text in the REPL version).

This section is in scope for this branch — `JOB_SCREENER_THEME` ships in the
same `cli.py` rewrite as the screens above, not a follow-up.

## Files touched

- Rewritten: `cli.py` (the whole interaction layer changes; backend imports
  stay the same).
- Modified: `pyproject.toml`/`uv.lock` (drop nothing — `rich` stays since
  Textual depends on it anyway; add `textual`).
- Untouched: `app.py`, `database.py`, `analyzer.py`, `scraper.py`,
  `CLI/terminal.html`.

## Explicitly out of scope (v1)

- Mouse support (Textual provides it for free on most widgets, but keyboard-
  only navigation is the explicit point of this rewrite — mouse clicks
  working incidentally is fine, no extra work to support or polish them).
- Persisting filter state across app restarts.
- Any change to `database.py`/`analyzer.py`/`scraper.py`.
