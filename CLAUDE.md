# Job Screener — project context for Claude Code

A tool for ethical evaluation of job listings. Every listing passes through six analysis layers before the question "is it worth applying?" is answered.

---

## Stack and dependencies

- **Backend:** Python >= 3.9, Flask >= 3.1.3
- **Database:** SQLite (file `data/screener.db`)
- **AI:** Anthropic Claude API (default model: `claude-sonnet-4-6`; override with `ANTHROPIC_MODEL` env var — model must support extended thinking)
- **Frontend:** Jinja2 + vanilla JS + external CSS
- **Environment manager:** uv (files `pyproject.toml` + `uv.lock`)
- **Python dependencies:** `flask`, `flask-wtf` (CSRF), `flask-limiter` (rate limiting), `requests` (feed fetching) — zero external CSS/Markdown libraries; `textual`/`rich` used only by `cli.py` (experimental TUI), never imported by the Flask app
- **Not used:** npm, webpack, any JS frameworks

## Running the app

```bash
# production — gunicorn daemon
bash server.sh start       # gunicorn -w 2, PID in /tmp/screener.pid
bash server.sh stop        # stop the daemon
bash server.sh restart     # stop → sleep 1 → start
bash server.sh status      # whether running and which PID

# development (no daemon)
uv run --env-file config.env python app.py

# dependency management
uv add package-name        # add a new dependency
uv sync                    # recreate the environment (e.g. after cloning)
```

`server.sh start` launches gunicorn with 2 workers, 180s worker timeout, as a daemon; logs in `/tmp/screener-access.log`
and `/tmp/screener-error.log`. PID saved in `/tmp/screener.pid`. Timeout must exceed the 120s Anthropic API timeout.

**Stale PID trap:** `server.sh restart` kills the PID in `/tmp/screener.pid`. If gunicorn was ever started outside `server.sh`, that PID won't match the real master — the kill silently misses and old workers keep serving new code never loads. Always use `server.sh` exclusively. If in doubt: `pkill -f "gunicorn.*app:app" && sleep 2 && bash server.sh start`.

`uv.lock` is committed to Git — guarantees identical versions across all environments.
`.venv/` is ignored by Git — uv creates it locally automatically.

---

## Project structure

```
job-screener/
├── app.py              — Flask: routing, auth, all endpoints
├── analyzer.py         — Claude API, system prompt with analysis methodology
├── database.py         — SQLite: schema, migrations, data operations
├── scraper.py          — URL content fetching, normalize_url, blocked domains
├── fetcher.py          — job feed fetching: fetch_remoteok, fetch_lever, fetch_greenhouse, fetch_rss; SSRF guard on RSS URLs
├── delete_user.py      — CLI: delete a user account and all associated data (`uv run python delete_user.py <username>`, type-username confirmation, no UI)
├── cli.py              — experimental Textual TUI (learning project). Combined view: job list + persistent filter bar + live detail panel with all six layers. `j`/`k` navigate list; Tab cycles list→filter bar→detail panel; `/`/`:` open a merged search/command prompt. `Ctrl+S` opens Settings (theme picker, CV/lists editor); `Ctrl+P` saves screenshot. State persists per-user in `data/cli_state_<username>.json` (gitignored). Wraps database.py/analyzer.py/scraper.py directly, no HTTP. Run via `uv run --env-file config.env python cli.py`. Not a production entry point.
├── 11DESIGN.md         — ElevenLabs design system patterns (style reference, not committed)
├── CHANGELOG.md        — version history (edit as plain text, rendered by /changelog and embedded in /about)
├── CHANGELOG.public.md — user-facing changelog (strips dev-only details); used by push-public.sh
├── CLAUDE.md           — this file
├── config.env          — API key and SECRET_KEY (never commit)
├── config.env.template — configuration template
├── pyproject.toml      — project dependencies and metadata (replaced requirements.txt)
├── uv.lock             — locked dependency versions (committed)
├── server.sh           — server management: start|stop|restart|status
├── push-public.sh      — push to public remote with CHANGELOG.public.md substituted as CHANGELOG.md (synthetic commit, no force-push)
├── static/
│   └── style.css       — ALL application styles (zero inline styles in templates)
├── templates/
│   ├── base.html       — layout, <link> to style.css, navigation (no footer)
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html  — unified view: command bar + full analysis table (filters, search, sort, mobile cards) + modal; `/history` and `/job/<id>` redirect here
│   ├── job_partial.html — clean HTML (no extends) loaded via AJAX into modal; has five tabs: Overview / Layers / Skills / CV / Interview
│   ├── discover.html   — Discover page: feed items list, per-item analyze, analyze-all, refresh
│   ├── settings.html   — CV, Zero Rule, Yellow List, criteria, Feeds management
│   ├── about.html      — project overview, six layers, reality check, verdicts, inline changelog
│   └── changelog.html  — renders CHANGELOG.md via a custom parser (`_md_to_html` + `_inline_md` in app.py; supports `**bold**` and `` `code` ``)
└── data/
    └── screener.db     — SQLite database (never commit)
```

---

## Database

### Table `users`
```
id, username, password_hash, cv, zero_list, criteria, yellow_list, created_at
```

### Table `jobs`
```
id, user_id, analyzed_at, company, role, verdict,
verdict_confirmed,      — 0 = AI verdict (unconfirmed), 1 = confirmed
zero_list_hit, zero_list_reason,
triage_status, product_status, business_status,
reputation_status, values_status, fit_status,
verdict_summary, triage_findings, product_findings,
business_findings, reputation_findings, values_findings,
fit_strengths, fit_gaps, fit_improve,
gut_feeling,
source,                 — short identifier (URL or first 300 chars of content)
source_full,            — full listing text (scraped or pasted)
source_hash,            — SHA-256 for deduplication
job_url,                — listing URL (stored separately from content)
applied,                — 0/1 application status
applied_at,             — application date
company_rejected,       — 0/1 company rejection
company_rejected_at,    — rejection date
interview_scheduled,    — 0/1 interview stage
interview_at,           — interview date
offer_received,         — 0/1 offer stage
offer_at,               — offer date
notes,                  — freeform user notes (max 10 000 chars)
interview_prep,         — AI-generated interview prep markdown (may be NULL)
reasoning,              — model's internal reasoning
raw_json                — full JSON response from the model
```

### Migrations
`init_db()` runs `ALTER TABLE RENAME COLUMN` (old Polish names) and `ALTER TABLE ADD COLUMN` on every startup — idempotent. Called at module level in `app.py` so gunicorn workers run migrations on import.

### Table `feeds`
```
id, user_id, type, source, label, keywords, active, last_fetched_at, created_at
```

### Table `feed_items`
```
id, feed_id, user_id, external_id, title, company, url, description,
source_hash,    — SHA-256 of URL (deduplication via UNIQUE(user_id, source_hash))
fetched_at, analyzed, job_id
```

---

## Fetcher (fetcher.py)

Four sources: `remoteok`, `lever`, `greenhouse`, `rss`. Returns `{external_id, title, company, url, description}`.

**Keyword filter:** `feeds.keywords` (comma-separated). Applied in `save_feed_items` before INSERT — items with no title match are discarded. Empty = save all.

---

## Scraper (scraper.py)

Error codes: `timeout`, `notfound`, `blocked`, `network` (see scraper.py for fallback behaviour).

**Domains blocked without attempting a connection:** LinkedIn, Indeed, Glassdoor, Pracuj.pl, NoFluffJobs, JustJoin.it

`normalize_url()` strips tracking params (`utm_*`, `fbclid`, `gclid`, `ref`, `source`, `from`, `vjk`, …) and fragment before scraping/deduplication; preserves listing-specific params (`id`, `jobId`).

---

## Endpoints (app.py)

```
GET/POST /login
GET/POST /register              — token via ?token=INVITE_TOKEN
GET      /dashboard
POST     /analyze               — url + text (both optional, at least one required); rejects with 429 if user already has 3 pending/running analyses
POST     /check_source          — url or text, checks for duplicate
POST     /reanalyze/<id>
GET      /analysis_status/<id>    — background analysis status poll (pending/running/done/error); returns `active_labels`, `active_count`, and when done: full `job_data` dict (all jobs columns) for live table injection
GET      /history_latest        — returns {id} of the most recent entry
GET      /history               — 301 redirect to /dashboard
GET      /job/<id>              — 301 redirect to /dashboard?job=<id> (modal auto-opens)
GET      /job/<id>/partial      — HTML without layout, loaded via AJAX into modal
POST     /job/<id>/verdict      — change verdict
POST     /job/<id>/status       — change status (all 6 values)
POST     /job/<id>/url          — add/change URL
POST     /job/<id>/applied      — application status
POST     /job/<id>/company_rejected — company rejection
POST     /job/<id>/notes
POST     /job/<id>/interview_prep — generate AI interview prep brief (5/hr rate limit)
POST     /job/<id>/cv_tailoring     — generate AI CV tailoring guidance (5/hr rate limit)
POST     /job/<id>/delete
GET      /discover              — fetches stale feeds (>1h) on load; shows unanalyzed items pre-filtered by Zero Rule
POST     /feeds/refresh        — force-fetch all active feeds; returns {new, errors}
POST     /feeds/add            — add feed (type, source, label, keywords); redirects to /settings#feeds
POST     /feeds/<id>/delete    — remove feed + its items; redirects to /settings#feeds
POST     /discover/<id>/analyze — analyze a feed item via existing background pipeline (20/hr); marks item analyzed on completion
GET      /statistics
GET      /settings
POST     /settings             — saves CV, zero list, yellow list, criteria; blocks save if any entry appears in both zero and yellow list (case-insensitive, strips `- ` prefix)
POST     /settings/password
GET      /export/csv
GET      /changelog
GET      /about               — no login required; project overview + inline changelog
GET      /logout
```

### Status system (6 values)
Dropdown `#status-select` with `<optgroup>` groups:

| Value | Label | DB effect |
|---|---|---|
| `worth_considering` | Worth considering | verdict, confirmed=1 |
| `warning` | Needs review | verdict, confirmed=1 |
| `rejected_soft` | AI rejected | verdict=rejected, confirmed=0 — not shown in dropdown (AI-only state) |
| `rejected` | Rejected (dropdown) / User rejected (badge) | verdict=rejected, confirmed=1 |
| `applied` | Applied | applied=1 |
| `company_rejected` | Rejected by company | company_rejected=1, applied=1 |
| `interview` | Interview | interview_scheduled=1, interview_at=now, applied=1, clears company_rejected |
| `offer` | Offer received | offer_received=1, offer_at=now, interview_scheduled=1, applied=1, clears company_rejected |

Handled by `update_job_status()` in `database.py`.

### Job detail modal
Non-obvious gotchas:
- JS functions (`tog`, `setStatus`, `confirmDelete`, `reanalyze`, `showUrlEdit`, `saveUrl`, `switchJobTab`) are globals defined in `dashboard.html`, not in the partial — `<script>` tags in AJAX-loaded partials do not execute
- The `d` theme-toggle is a *separate* global `keydown` listener in `base.html` (not the dashboard-only handler) — works on every page, guarded against field focus
- `.modal-body` has **zero** padding — every inner section manages its own (past bug: double 24px inset when both had it)

---

## Security (app.py + database.py)

### Environment requirements
`SECRET_KEY` **must** be set in `config.env` — app raises `RuntimeError` at startup if missing.
`FLASK_DEBUG` defaults to `0`; set to `1` only for local dev.

Generate a key: `python -c "import secrets; print(secrets.token_hex(32))"`

### CSRF protection (Flask-WTF)
`CSRFProtect(app)` validates all POST/PUT/PATCH/DELETE requests.
- HTML forms: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`
- AJAX fetch() calls: `headers: {'X-CSRFToken': csrfToken()}` — token read from `<meta name="csrf-token">` in `base.html`
- Tests: `WTF_CSRF_ENABLED=False` in `conftest.py` disables CSRF for the test suite

### Rate limiting (Flask-Limiter)
In-memory per-worker storage (2 gunicorn workers = independent counters, acceptable for small groups).
- `/login` — 10 requests / 5 minutes per IP
- `/register` — 3 requests / hour per IP
- `/analyze` — 20 requests / hour per user IP
- Tests: `limiter.enabled=False` set in `conftest.py`; individual rate limit tests toggle it on temporarily

### Account lockout
Module-level `_login_attempts` dict: `{username_lower: [failure_timestamps]}`.
- Lock triggers after 5 failures within 5-minute window
- Lockout duration: 15 minutes
- Only tracks existing usernames — unknown usernames never get an entry
- Cleared on successful login
- Not shared across gunicorn workers (accepted tradeoff)

### Session cookies
```python
SESSION_COOKIE_SECURE = True      # only sent over HTTPS — set False in local config.env for dev
SESSION_COOKIE_HTTPONLY = True     # not readable by JS
SESSION_COOKIE_SAMESITE = "Lax"   # not sent cross-site
PERMANENT_SESSION_LIFETIME = timedelta(days=7)
```
`session.permanent = True` set on login.

### Security headers
`@app.after_request` adds to every response:
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Server: unknown` (suppresses gunicorn banner)

### SSRF protection (scraper.py)
`_is_internal_host(url)` resolves the hostname and rejects private/loopback/link-local IPs before any HTTP connection is made. Covers `10.x`, `172.16–31.x`, `192.168.x`, `127.x`, `169.254.x`, IPv6 equivalents. Called in `fetch()` after the blocked-domain check.

### Username enumeration
Failed login always calls `_record_failure(username)` regardless of whether the user exists. Prevents timing-based username probing via lockout state differences.

### Password policy
Minimum 10 characters enforced in the `/register` route.

### Password hashing
SHA-256 with random salt (`secrets.token_hex(16)`), stored as `salt:hash`.
Verified with `secrets.compare_digest()` (constant-time, prevents timing attacks).

---

## Analysis methodology (analyzer.py)

### Six layers
1. **Triage** — role fit against trajectory, initial signals, hidden employer
2. **Product** — product, claims, AI-washing, verifiability
3. **Business** — revenue model, funding, investors, PE/VC
4. **Reputation** — actively uses training knowledge (not just listing content): Glassdoor/Indeed/Blind rating and trend, dominant review themes, C-level history, layoff patterns, media and regulations; for unknown companies explicitly notes lack of data
5. **Values** — mission coherence, ethical traps, accessibility vs stated values
6. **Skills fit** — strengths, gaps, what to strengthen in the application

### Company name
The `company_name` field in the model's JSON response must contain the actual company name (not the recruiter).
If the company cannot be identified — the model uses exactly `"Unknown"`.
The `verdict_summary` first sentence must explain why the company is unknown.
Templates display `job.company or 'Unknown'` — never use `'—'` for an empty name.

### Zero List
Automatic rejection without analysis. Configured per user in Settings.

### Rejection confirmation
`verdict_confirmed` distinguishes two rejection states:
- `zero_list_hit = true` → `verdict_confirmed = 1` set automatically by `save_job()`
- AI returns `verdict: rejected` without `zero_list_hit` → `verdict_confirmed = 0` (requires user action)
- User selects "Rejected" in dropdown → `verdict_confirmed = 1` via `update_job_status()`

### Yellow List
Forces verdict "warning" but continues analysis. Configured per user.

### Prompt injection mitigation
Job listing content (pasted or scraped) is wrapped in `<job_listing>` tags in the user message.
`SYSTEM_TEMPLATE` instructs the model to treat content inside those tags as data only,
never as instructions — even if it contains text resembling commands or requests to
change the verdict/output format.
User profile fields (`cv`, `zero_list`, `yellow_list`, `criteria`) are brace-escaped
(`{` → `{{`, `}` → `}}`) in `build_system()` before `.format()`, so a `{`/`}` in user
text cannot raise a `KeyError`/crash.

### Evidence rule
For every flag (`status: "flag"`) and every rejection the model must provide
an `evidence` field with a specific quote from the listing text.
No evidence → downgrade to "warning", describe the concern.

**Exception — reputation layer:** uses model knowledge outside the listing text;
`evidence` = specific knowledge (numbers, names, dates), not a quote from the listing.
Generic statements without specifics are still not allowed.

### JSON response format
```json
{
  "company_name", "role_title",
  "verdict": "rejected|warning|worth_considering",
  "verdict_summary",
  "zero_list_hit", "zero_list_reason", "zero_list_evidence",
  "yellow_list_hit", "yellow_list_reason",
  "triage": { "status", "findings", "evidence" },
  "layers": {
    "product":    { "status", "findings", "evidence" },
    "business":   { "status", "findings", "evidence" },
    "reputation": { "status", "findings", "evidence" },
    "values":     { "status", "findings", "evidence" }
  },
  "fit": { "status", "strengths", "gaps", "improve" },
  "gut_feeling",
  "reality_check": {
    "summary": "2-3 sentences on what the language signals about the actual role",
    "callouts": [
      {"phrase": "exact quote or close paraphrase", "plain": "what it actually means"}
    ]
  }
}
```

---

## CSS — absolute rules

**Zero inline styles in HTML templates.** The only exception is `display:none`
as a dynamic state managed by JS.

All styles in `static/style.css`. New class → new entry in the appropriate
section of the file with a section comment (e.g. `/* ── new section ───── */`).

### Design tokens
Untitled UI–inspired system (mockup reference: `untitledui-mockup.html` in repo root, not part of the app).
```css
--bg, --surface, --surface-2, --border, --border-light   — neutral cool black (dark) / neutral grey (light)
--text, --muted, --dim                                   — text greyscale
--accent, --accent-dim                                    — blue (#5c5cff dark / #0000ff light) — primary buttons, links, active tab, focus ring
--danger, --danger-hover                                  — theme-invariant solid red, used only for `.btn-danger` fill
--shadow-xs, --shadow-sm                                   — soft drop shadows (cards, modal) — replaced the old heavy inset-black-shadow look
--radius-sm: 8px; --radius-md: 12px; --radius-lg: 16px
--fd: 'Inter'           — headings, logo
--fb: 'Inter'           — body text
--fm: 'JetBrains Mono'  — labels, mono, eyebrow text
```

Six status colours are each a `text` / `bg` / `border` triple (`--blue`/`--blue-bg`/`--blue-border`, and
the same pattern for `--yellow`, `--red`, `--green`, `--violet`, `--orange`) — theme-aware, so a component
that reads `var(--red)` etc. never needs a `[data-theme="light"]` override. Light theme's `*-bg` values are
Tailwind-50-style soft tints (e.g. `#fef3f2`), not saturated — badges and any future tinted surface should
reuse these tokens rather than inventing new hex values.

### Typography variables
```css
--fs-base-scale: 16px;  /* change only this one value */
--fs-2xs through --fs-4xl — calc() based on base-scale
--fs-tiny: 9px   — legacy, mostly superseded by literal 11px on `.badge`
--fs-icon: 14px  — icon glyphs
--fw-display: 600; --fw-normal: 400; --fw-medium: 500
```
`--fw-display` replaced the old `--fw-light` (200) — Inter 200 isn't loaded, so headings rendered flat;
600 gives real visual hierarchy. Used by `.page-title`-adjacent headings, `.stat-card-value`, etc.
`.page-title` itself is a fixed `32px` / `--fw-normal`, not token-scaled — set directly per design request.

### Light / dark mode
- `data-theme="light"` attribute on `<html>` activates the light palette (neutral `#fafafa` bg / white cards — not warm cream)
- Toggle: `<button id="theme-toggle">` in navigation (`base.html`) — ☀/☾ icon
- Preference saved in `localStorage`; loaded by IIFE in `<head>` before CSS (zero flash)
- Per-component colour overrides are mostly gone now that status colours are theme-aware tokens (see Design tokens) — only a handful of genuinely one-off cases remain under `[data-theme="light"] .class { ... }`

### Status colours (badges and filter pills)

Badges and filter pills are soft-tinted pills: border + text colour (the status's `--*` token) + background
(the matching `--*-bg` token) + a small coloured dot (`.badge::before` / `.filter-btn::before`, `background: currentColor`).
Table rows no longer carry a background tint — the badge is the only colour signal in a row, matching the
Untitled UI reference (loud per-row highlight colour-washing was removed; it read as dated next to soft badges).

| Status | Badge class | Colour token |
|---|---|---|
| Worth considering | `badge-worth_considering` | blue |
| Needs review | `badge-warning` | yellow |
| Rejected (AI or user) | `badge-rejected` | red |
| Applied | `badge-applied` | green |
| Rejected by company | `badge-company_rejected` | orange |
| Interview | `badge-interview` | violet |
| Offer received | `badge-offer` | green |

Hover on table rows: `box-shadow: inset 0 0 0 9999px var(--hover-overlay)`.

### Key utility classes (non-obvious only — read style.css for the full list)

`.modal-body` — **zero** padding; every inner section manages its own (past bug: double 24px inset when both had it)
`.tab-section` inside `.job-tab-content` — padding/border stripped to 0; flex `gap` does spacing
`.company-note` — "(?)" after shortened company name; `title` holds full string
`.badge` — 11px pill with `::before` dot; soft-tinted `--*-bg` + `--*-border` + `--*` text
`.btn-danger` — theme-invariant `--danger` token (not a status colour triple)
`.stats-hfunnel-fill` — width set inline `style="width:N%"` (permitted exception to no-inline-styles rule)
`.collapsible` — native `<details>`/`<summary>`, no JS; used for listing source section
`.hero-dots` — `<canvas>` in dashboard hero; animated dotted-grid, cursor-reactive, `prefers-reduced-motion` aware
`.is-blurred` — applied to table/cards/search/filter while `#cmd-input` has focus
`.filter-btn` — filter state saved in `localStorage` under key `history_hidden_categories`
`.nav-toggle` — hamburger, hidden by default; `display: flex` at ≤768px; `margin-left: auto` takes over from `.nav-links` (which hides) to push it right
`.analysis-banner-counter` — "X of Y" cycling indicator; hidden when only 1 analysis active
`.analysis-banner-dismiss` — `×` on done banner; clears without navigating
`.flash` — pass `"error"` as flash category for red; omit category (defaults to `"message"`) for blue

---

## Conventions

- UI language: **English** (labels, messages, errors)
- Code comments: English
- DB verdicts: `rejected`, `warning`, `worth_considering`
- Label "Worth considering" maps to `worth_considering` in DB
- Layer statuses: `ok`, `warning`, `flag`
- Variable names: English (DB columns, JSON keys, Python variables, CSS classes)
- Dates in DB: ISO (`date('now')` SQLite)
- Passwords: `sha256(salt:password)` via `hash_password()` / `verify_password()`
- Multi-user: first account without token, subsequent accounts via `?token=INVITE_TOKEN`

---

## Git

Dev repo (private): `https://github.com/BartekJagniatkowski/job-screener-dev`
Public repo: `https://github.com/BartekJagniatkowski/job-screener`

Push workflow:
- `git push` — pushes to dev remote (`origin`)
- `bash push-public.sh` — pushes to public remote with clean `CHANGELOG.md`; run after every dev push that should go public
- When updating CHANGELOG.md, also update `CHANGELOG.public.md` (strip dev-only bullets)

Rsync iCloud → local dev (run as single unbroken line — line-wrapping splits `--exclude` args and breaks rsync):
```bash
SRC="/Users/bartekjagniatkowski/Library/Mobile Documents/com~apple~CloudDocs/Work/Development/job-screener"; rsync -a --delete --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' --exclude='*.pyc' --exclude='.DS_Store' --exclude='data/' --exclude='.claude/' "$SRC/" "$HOME/Development/job-screener/"
```

### Never commit
- `config.env` (API keys)
- `data/` and `*.db` (database with user data)
- `venv/`, `__pycache__/`, `.DS_Store`

### Commit convention (in English)
```
feat: description of new feature
fix: description of bug fix
refactor: structural change without new feature
style: CSS/formatting changes
docs: documentation update
```

### Version convention
`x.xx` only (e.g. `v0.26`, `v0.27`). No patch segment (`v0.26.1` is wrong). Fixes and tweaks fold into the current minor version entry in CHANGELOG.md.

---

## Known limitations

- LinkedIn, Indeed and most job boards block scraping — user must paste content manually
- The model is non-deterministic — two runs on the same listing may produce different results; this is a property of the tool, not a bug
- Old records (before v0.4) do not have `source_full` — the source section in the view shows a "no data" message
- `raw_json` of old records does not contain the `evidence` field — the evidence block simply does not render

---

## Strategic context

Job Screener works against the logic of the recruitment market — it helps filter listings by ethical criteria instead of maximising applications. This "anti-market" property is its value, not its weakness. The project is a portfolio case study and test of an ethical product-building methodology, not primarily a commercial product.
