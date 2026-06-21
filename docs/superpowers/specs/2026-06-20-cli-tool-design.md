# Job Screener CLI — Design Spec

Branch: `cli-tool`. Learning project — not required to ship as a finished product.

## Goal

A REPL-style command-line front end for the existing job-screener app, reusing the
real backend (`database.py`, `analyzer.py`, `scraper.py`) against the same SQLite
DB — no HTTP layer, no Flask dependency at runtime. Visual/UX inspiration:
`CLI/terminal.html` (a static, non-functional mockup already in the repo).

## Architecture

- New file: `cli.py` at repo root. Run via `uv run --env-file config.env python cli.py`.
- Built on stdlib `cmd.Cmd` for the REPL loop (prompt, command dispatch, history).
- `rich` for colored table/panel output (`uv add rich` — one new dependency).
- Imports `database.py`/`analyzer.py`/`scraper.py` directly. No new abstraction layer
  between the CLI and those modules — commands call the existing functions as-is.
- Config (Anthropic API key, model) read from the environment the same way `app.py`
  reads it — via `config.env`, loaded by `--env-file`.

## Startup flow

1. Prompt for username (plain input, no password — local trusted tool, same trust
   model as `delete_user.py`).
2. `database.get_user(username)`. Unknown username → print error, prompt again.
   Three failed attempts → exit.
3. Enter REPL loop with prompt `job-screener> `.

## Commands (v1)

All commands operate on the user resolved at startup (`user["id"]`).

### `list [--status=STATUS]`
- Calls `database.get_jobs(user_id)`.
- `--status` is a client-side filter on the returned list (verdict or
  applied/company_rejected/interview/offer flags) — no new DB query function.
- Renders a `rich.Table`: columns DATE, ROLE · COMPANY, VERDICT, LAYERS (six colored
  dots: pass/warn/flag per layer status), FIT (`x/5` or `—`), ID.
- No results → "No jobs analyzed yet. Try: analyze <url>".

### `show <id> [--full]`
- Calls `database.get_job(id, user_id)`. Not found or belongs to another user →
  error message, no traceback.
- Renders verdict summary + per-layer panel (status + findings) via `rich.Panel`.
- Default: triage + first 2 layers. `--full`: all 6 layers + fit section.

### `analyze <url-or-text>`
- If the argument starts with `http://` or `https://` → `input_mode="url"`,
  call `scraper.fetch(url)` first; scrape failure prints the error code
  (`timeout`/`notfound`/`blocked`/`network`) and suggests pasting text instead.
- Otherwise → `input_mode="text"`, argument used as-is as the listing body.
- Calls `analyzer.analyze(user, text, input_mode, api_key, model)`, then
  `database.save_job(user_id, result, source_url=..., source_text=...)`.
- Synchronous — no background job/polling (CLI has no concurrent UI to keep
  responsive). Prints a "analyzing…" line before the (blocking) API call.
- Duplicate check via `database.check_duplicate(user_id, source)` before calling
  the API — same dedup behavior as the web app's `/analyze` route. Duplicate found
  → print existing job's id/verdict, ask to skip or re-analyze (only inline
  yes/no, no `--force` flag needed for v1).

### `help` / `clear` / `exit`
- `help` — list commands (cmd.Cmd's built-in `do_help` is sufficient, optionally
  overridden for nicer formatting).
- `clear` — clear terminal screen (`os.system('cls' if os.name == 'nt' else 'clear')`).
- `exit` / `quit` / Ctrl-D — exit the REPL.

## Explicitly out of scope (v1)

- `filter`, `export` commands from the mockup.
- Editing CV / Zero List / Yellow List / criteria from the CLI.
- Discover/feed integration.
- Multi-user session switching without restarting the CLI.
- Any background/async analysis — CLI blocks during `analyze`.

## Files touched

- New: `cli.py`.
- Modified: `pyproject.toml`/`uv.lock` (rich dependency).
- Untouched: `app.py`, `database.py`, `analyzer.py`, `scraper.py`,
  `CLI/terminal.html` (kept as visual reference, not deleted).

## Testing

Given the explicit "this is a learning exercise" framing, no enforced TDD/test
suite requirement for this branch — manual REPL testing is enough. If the user
wants test coverage later, `tests/test_cli.py` could drive `cmd.Cmd.onecmd()`
against a temp DB, following the existing `tests/conftest.py` fixture pattern.
