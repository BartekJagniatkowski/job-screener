# Job Screener TUI v2 — Combined List/Detail/Command-Line Redesign

Branch: `cli-tui-v2`. Learning project — not required to ship as a finished product.
Supersedes the multi-screen TUI (`LoginScreen` → `BrowseScreen` → push/pop to
`DetailScreen`/`AnalyzeScreen`/`HelpScreen`) built on branch `cli-tui`, already
merged to `main`.

## Goal

Replace the push/pop screen-stack navigation with one combined screen
(`MainScreen`) showing the job list and the selected job's detail together,
plus a vim-style `/` search and `:` command prompt — closer to a real terminal
workflow than navigating between separate full-screen views for every action.
Also: fix horizontal overflow in the list, repurpose the default command
palette into an app-specific "Settings" menu, and add full-text search.

## Architecture

- `LoginScreen` unchanged, switches to `MainScreen` instead of `BrowseScreen`.
- `MainScreen` replaces `BrowseScreen` + `DetailScreen` + `AnalyzeScreen` +
  `HelpScreen` entirely. Those four classes are deleted, not kept alongside.
- `App.COMMAND_PALETTE_BINDING = "ctrl+s"` and `App.get_system_commands()`
  overridden to replace Textual's default palette entries with app-specific
  ones (see Settings section). The footer's auto-generated label for this
  binding may still read "palette" rather than "Settings" — Textual's
  built-in command-palette UI doesn't expose a title override in the version
  installed (6.2.1); if a workaround surfaces during implementation, take it,
  but it's not worth blocking on.
- Still imports `database.py`/`analyzer.py`/`scraper.py` directly — same
  SQLite DB, same trust model as v1.
- Same worker-thread constraint as v1: `scraper.fetch()`/`analyzer.analyze()`
  run inside `@work(thread=True)`, UI updates marshalled through
  `App.call_from_thread()`.
- Theme: same `JOB_SCREENER_THEME` (dark) as v1, plus a second
  `JOB_SCREENER_LIGHT_THEME` for the "Change theme" Settings entry to toggle
  between (see Settings section for exact values).

## `MainScreen` layout (top to bottom)

1. **Title bar** — current filter state (existing `sub_title` pattern from v1's
   `BrowseScreen`).
2. **List** — a `DataTable` with a fixed height (header + 7 visible data
   rows; Textual's built-in viewport scrolling handles anything beyond that,
   so cursor movement past row 7 scrolls the table exactly like before —
   no custom pagination logic needed). Columns: DATE, ROLE · COMPANY, VERDICT,
   LAYERS, FIT, ID — same six columns as v1.
   - **Row-text truncation**: ROLE · COMPANY is built from `role` and
     `company` strings concatenated with " · " as before, but now truncated
     to a fixed max length (40 characters) with a trailing `…` if longer,
     computed in Python before `add_row()` — not relying on `DataTable`'s
     own per-column `width`/wrap behavior, which would require auto-height
     rows and complicate the fixed-7-row layout. This removes the horizontal
     scrolling seen in real-terminal testing of v1.
3. **Detail panel** — a `Static`/`Label` below the list (in a
   `VerticalScroll`, matching v1's `DetailScreen` pattern), showing the
   currently *highlighted* row's job. Updates live on every cursor move via
   `DataTable.RowHighlighted` (fires on arrow/`j`/`k` movement, not just
   `Enter` — so the panel always reflects the selected row without an
   explicit "open" step). `f` toggles brief (3-layer) / full (5-layer + fit +
   gut feeling) — same content and toggle behavior as v1's `DetailScreen`.
4. **Legend bar** — one line showing context-valid actions, replacing v1's
   modal `HelpScreen` entirely (no overlay popup in v2):
   - List-navigation mode (default): `j/k move · enter open · f layers ·
     / search · : command · ctrl+s settings · q quit`
   - Search mode (prompt focused via `/`): `enter apply · esc cancel`
   - Command mode (prompt focused via `:`): `enter submit · esc cancel`
   - Duplicate-confirm pending: `type 'yes' to re-analyze · esc cancel`
5. **Command/search prompt** — one `Input` widget, hidden/unfocused by
   default, repurposed by which key opened it:
   - `/` focuses it in **search mode** — typing live-filters the list by
     substring match on `role`/`company` (case-insensitive), updates the
     `DataTable` on every keystroke via `Input.Changed`. `Enter` keeps the
     filter applied and returns focus to the list. `Esc` clears the search
     and returns focus to the list.
   - `:` focuses it in **command mode** — typing a command, `Enter` submits
     and parses it (see Commands below), `Esc` cancels (clears input, no
     side effect) and returns focus to the list.
   - The two modes share one `Input` instance; a `self.prompt_mode: str`
     attribute (`"search"` or `"command"`) set when focusing determines how
     `Input.Submitted`/`Input.Changed` are interpreted.
6. **Status line** — analyze progress ("Fetching…"/"Analyzing…"), errors,
   duplicate-confirm prompts, "Saved #NNN — VERDICT" — same messages as v1's
   `AnalyzeScreen`, rendered inline here instead of on a separate screen.

## Commands (typed in `:` command mode)

- `analyze <url|text>` — same scrape → duplicate-check → analyze → save
  pipeline as v1's `AnalyzeScreen`, all in a `@work(thread=True)` worker,
  status messages in the status line (item 6 above) instead of a separate
  screen. Duplicate confirmation becomes typed: status line shows "Duplicate
  of #NNN (verdict). Type 'yes' to re-analyze, anything else cancels" — the
  *next* submitted command-mode input is read as that yes/no answer (a
  `self.awaiting_duplicate_confirm: Optional[tuple]` holds the pending
  source until then), not buttons.
- `filter <status>` — jumps directly to a status (`all`/`rejected`/`warning`/
  `worth_considering`/`applied`/`interview`/`offer`/`company_rejected`),
  same `FILTER_CYCLE` values as v1, same `job_matches_filter()` logic. `f`
  (single-key, list-navigation mode) still *cycles* through them in order;
  `:filter <status>` jumps directly to one.
- `full` / `brief` — same as pressing `f` in the detail panel; typed
  equivalents for discoverability.
- `quit` — same as `q`/`Esc` in list-navigation mode.
- Unrecognized command → status line shows "Unknown command: <text>".

`/` search and `:` commands are independent — searching doesn't clear an
active status filter, and vice versa; both predicates apply together
(`job_matches_filter(row, status) and search_term in (role+company).lower()`).

## Settings (`Ctrl+S`)

Replaces Textual's default command palette (`ctrl+p` → `ctrl+s`, default
entries replaced via `get_system_commands()` override). Entries:

- **Edit CV** — pushes a small `Screen` with a `TextArea` pre-filled with
  `self.app.user["cv"]`, a "Save" keybinding (e.g. `ctrl+s` again, or a
  visible Save action) that calls
  `database.update_user_profile(user_id, cv=<new text>, zero_list=<unchanged>,
  criteria=<unchanged>, yellow_list=<unchanged>)` — **all four fields must be
  passed together**, since `update_user_profile`'s signature has no partial-
  update mode; the three unedited fields are read from `self.app.user` and
  passed through unchanged. On success, updates `self.app.user` in memory
  (re-fetch via `database.get_user(username)` is simplest and avoids drift)
  and pops back to `MainScreen`.
- **Edit Zero list** / **Edit Yellow list** / **Edit criteria** — same
  pattern, editing a different one of the four fields each time.
- **Change theme** — toggles `self.app.theme` between `"job-screener"` (dark,
  existing `JOB_SCREENER_THEME`) and a new `"job-screener-light"` theme:
  `primary="#0084b4"` (darker cyan for light-bg contrast), `secondary="#a86200"`,
  `background="#fafafa"`, `surface="#ffffff"`, `panel="#f0f0f0"`,
  `success="#4a8f3c"`, `warning="#a86200"`, `error="#c0392b"`,
  `foreground="#1a1a1a"`, `dark=False` — values chosen to keep the same hue
  identity as the dark palette while meeting light-background contrast,
  not lifted from `terminal.html` (which has no light variant).
- **Show keys** — same content as v1's deleted `HelpScreen`, shown as plain
  text in the status line area (item 6) rather than a popup, or as a simple
  one-off `Static` overlay if status-line space is too cramped for the full
  list — implementer's call at build time, either is acceptable, but it must
  not be a blocking modal that swallows unrelated keys the way v1's bug did
  (see Tab/Escape note below).
- **Save screenshot** — calls `self.app.save_screenshot()` (Textual's
  built-in SVG export), writes to a fixed path (e.g. `./screenshot.svg` in
  the cwd) and shows "Saved screenshot to ./screenshot.svg" in the status
  line.
- **Quit** — same as the `quit` command / `q` key.

## Tab key

No special handling needed. `MainScreen` has two focusable widgets (the
`DataTable` and the prompt `Input`), so Textual's built-in Tab focus-cycling
(which had nothing to cycle to in v1's single-widget `BrowseScreen`, hence
"does nothing") now functions automatically. Not implemented as a feature —
just stops being a dead binding as a side effect of the new layout.

## Lesson carried forward from v1's real-terminal bug

v1 shipped with a bug (`q` while the help modal was open quit the whole app
instead of closing the modal) that 4 rounds of headless `Pilot` testing and
code review missed, only caught by manually driving the app in a real `tmux`
session. v2's design removes the modal screen-stack pattern that caused
it (no more `HelpScreen` to get this wrong), but the **Settings sub-screens**
(Edit CV/Zero list/Yellow list/criteria) are pushed screens too — implementers
on this plan must explicitly test that `Escape`/`q` typed *while editing a
TextArea* doesn't accidentally bubble to `MainScreen`'s quit binding, the
same class of bug, and must verify it in a real terminal (`tmux`), not just
headless `Pilot`, before considering any task in this plan done.

## Error handling

Same failure modes as v1, all routed to the status line (item 6) instead of
a separate screen: unknown username (`LoginScreen`, unchanged), scrape
failure, missing `ANTHROPIC_API_KEY`, `analyzer.analyze()` exception,
`database.save_job()` exception (kept as a distinct message from analyze
failure, per v1's fix), invalid `:filter`/unknown command.

## Testing

Still an explicitly-scoped learning project — no enforced test suite.
Manual testing means launching the app and navigating with the keyboard,
in a real terminal (see the Tab/Escape lesson above) — headless `Pilot`
testing alone is not sufficient verification for this plan, given v1's
experience.

## Files touched

- Rewritten: `cli.py` (the whole interaction layer changes again;
  `LoginScreen` and the backend imports stay structurally the same).
- Modified: `pyproject.toml`/`uv.lock` — no new dependency expected (`textual`
  already present; `TextArea` is a stdlib-to-Textual built-in widget, no
  extra package).
- Untouched: `app.py`, `database.py`, `analyzer.py`, `scraper.py`,
  `CLI/terminal.html`.

## Explicitly out of scope (v2)

- The web app's zero/yellow-list cross-validation rule ("blocks save if any
  entry appears in both lists") — `app.py`'s `/settings` route enforces this,
  `database.update_user_profile()` itself does not. The TUI's Settings
  editors call `update_user_profile()` directly without replicating that
  validation. Acceptable for a learning project; flagged here so it's a
  conscious omission, not a missed requirement.
- Multi-select or bulk actions on the list (e.g. analyze multiple at once).
- Persisting search/filter state across app restarts.
- Any change to `database.py`/`analyzer.py`/`scraper.py`.
