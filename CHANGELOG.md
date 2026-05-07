# Changelog — Job Screener

A tool for ethical evaluation of job listings. Every listing passes through six analysis layers before the question "is it worth applying?" is answered.

---

## v0.14.1 — Rename Analytics → Statistics

- Nav link, page title, and browser tab renamed from "Analytics" to "Statistics"
- Route (`/analytics`) and CSS class names unchanged

---

## v0.14 — Reality check

- New "Reality check" section in job detail view, before the layer analysis
- Plain-English summary of what the role actually is, synthesised from the listing language
- Up to 6 corpo-speak phrase callouts decoded inline: `"phrase" → what it actually means`
- Purely informational — no verdict impact
- Absent for analyses run before this version

---

## v0.13 — Analytics redesign

- Plain-English TL;DR summary card at top: total analyzed, applied + follow-through %, most-flagged layer, average fit score
- Application pipeline funnel replaces stat cards: Analyzed → Qualifying → Applied → Co. rejected, each with percentage relative to prior step
- Verdict distribution replaced with single proportional stacked bar (Worth considering / Needs review / Rejected / Rejected AI)
- Layer flags simplified to flag-count-only bars sorted by severity — ok/warning segments removed
- Fit score distribution and Role archetypes collapsed by default; click to expand
- Average fit score moved to TL;DR text — no longer a dedicated stat card

---

## v0.12.1 — History table fixes

- Sticky table header restored — `overflow-x: auto` on the table wrapper was creating a scroll container that trapped `position: sticky`, preventing the header from sticking to the viewport
- Layer dots now vertically centred and fill the full row height — `display: flex` on `<td>` overrides table-cell height stretching; flex layout moved to an inner `.dot-row` wrapper
- Table width reverted to 1280px container — full-viewport width was too wide for the current column count

---

## v0.12 — History table redesign

- Rebuilt from 12 columns to 7: Date, Role, Company, Verdict, L0, Layers, Fit
- Classification badge always single-line; "Rejected by company" fits without wrapping
- Six analysis-layer dots collapsed into one compact dot strip with hover tooltips (Triage · Product · Business · Reputation · Values)
- Fit score surfaced as its own column (`X.X/5`, colour-coded by fit status)
- Status column removed (badge already encodes applied/company-rejected state)
- Filter bar and table header sticky on scroll — both remain visible on long lists
- "Show all" filter button resets all category filters at once

---

## v0.11 — Background analysis with persistent banner

- Analysis runs in a background thread — user can navigate away immediately after submitting
- New `analyses` table tracks job lifecycle: `pending → running → done / error`
- Persistent banner below nav shows progress on every page: spinner + source label + pulsing dots while running; green clickable strip with company and verdict when done; red dismissible strip on error
- Stuck analyses from killed workers auto-cleaned on startup after 5 minutes
- New `GET /analysis_status/<id>` polling endpoint
- `/reanalyze/<id>` also runs asynchronously

---

## v0.10.1 — Gunicorn stability fixes

- `init_db()` moved to module level — migrations now run when gunicorn imports `app:app` (previously only ran in `__main__`, so new columns like `role_archetype` were missing in production)
- Gunicorn worker timeout raised to 180s — prevents workers being killed mid-analysis (default 30s was shorter than the 120s API timeout)
- `login_required` returns JSON 401 for XHR requests instead of an HTML redirect — prevents "Unexpected token '<'" JSON parse errors in the browser when a session expires
- Global `fetch` wrapper in `base.html` adds `X-Requested-With: XMLHttpRequest` header and redirects to `/login` on 401 — no per-call handling needed

---

## v0.10 — Full UI translation to English

- All Polish text translated to English across every file: templates, Python backend, system prompt, error messages, docstrings, inline comments
- Layer names: "Warstwa produktowa/biznesowa/reputacyjna/wartości" → Product/Business/Reputation/Values layer
- Status labels: "Do rozważenia/Wymaga uwagi/Odrzucona/Zgłoszono/Odmowa" → Worth considering/Needs review/Rejected/Applied/Rejected by company
- Company name fallback: "Nieznana" → "Unknown"
- CSV export filename: `oferty_<user>.csv` → `jobs_<user>.csv`
- Default Zero List and Criteria templates rewritten in English for new accounts
- System prompt (analyzer.py) fully translated — analysis logic and JSON format unchanged
- Blocked-domain error messages translated to English
- `Accept-Language` header updated to `en,pl;q=0.9`

---

## v0.9.2 — Stability, Python 3.9 compatibility and technical fixes

- Python 3.9 compatibility: `Optional[sqlite3.Row]` instead of the `|` operator (PEP 604 available from 3.10 only)
- Fixed `login_required` decorator — correct `functools.wraps` pattern with `return decorated`
- Fixed JSON validation in the analyzer — `start > end - 1` condition eliminates edge case with empty or inverted range
- `sqlite3.IntegrityError` handling in `/analyze`, `/reanalyze` and CSV export
- Database indexes on `user_id`, `source_hash`, `analyzed_at` columns — faster queries with larger history
- API timeout increased to 120s — margin for complex analyses with extended thinking
- Scraper response size limit: 5MB — protection against very large pages
- Better URL validation in `normalize_url` and `scraper.fetch`
- API error messages enriched with model name for easier debugging

---

## v0.9.1 — Listing URL in modal card header and font scale correction

- Listing URL surfaced at the top of the modal card header — visible directly below the verdict summary; priority: `job_url`, fallback: `source_full` if it is a URL
- Restored font scale `--fs-base-scale: 16px` (accidentally reduced to 14px in v0.9)

---

## v0.9 — History filtering, card redesign and visual consistency

- Category filter in analysis history: toggle buttons for each of the 6 statuses, any combination, state saved in `localStorage`
- Badges without background — border and text color only; row highlight takes over as the color signal
- New row class `row-warning` (yellow background) for "Needs review" listings; `row-rejected-soft` (light red) for AI-rejected
- Job card header switched to vertical layout: badge → role → company → summary → rejection reason → date
- Role and Company columns swapped in history table and recent analyses on dashboard
- Unknown company labelled "Unknown" instead of "—"; model required to explain the missing name in the verdict summary
- `data-category` attribute on history table rows — enables filtering without inspecting CSS classes

---

## v0.8 — English variable names and rejection confirmation logic

- All database column names, JSON keys and CSS classes migrated to English
- New `verdict_confirmed` field distinguishes automatic rejections (Zero List) from AI rejections requiring confirmation
- Verdict dropdown shows two rejection states: "Rejected (AI)" and "Rejected — confirm"
- Visual row marking in history and dashboard tables: strikethrough for confirmed rejections, lighter background for unconfirmed, green background for submitted applications
- Idempotent data migrations — existing databases updated automatically on startup

---

## v0.7 — Application status and record management

- Added "Application sent" status with date in the analysis view and a column in history
- Added the ability to delete a listing from the analysis view
- Added the ability to manually attach a listing URL after analyzing pasted text
- Added Enter key confirmation for the URL input
- Entire row is clickable in the analysis history

---

## v0.6 — Yellow list and manual verdict change

- Added "Yellow list" — borderline categories that force verdict "needs review" without stopping the analysis
- Yellow list is configurable per user in Settings
- Added dropdown for manual verdict change in the analysis view (no page reload)
- Added "Re-analyze" in the analysis view — triggers a new analysis from the saved source
- New fields `yellow_list_hit` and `yellow_list_reason` in the JSON returned by the API

---

## v0.5 — Evidence from listing and source verification

- Added evidence rule in the system prompt: model required to cite the listing for every flag and rejection
- New `evidence` field on layers with status "flag" — displayed in the analysis view
- Added `zero_list_evidence` for identifying hidden employers
- Status message before analysis: green (new listing) or yellow (duplicate)
- New endpoint `/check_source` — database check without calling the API

---

## v0.4 — Duplicate detection and listing source

- Duplicate detection based on SHA-256 of content/URL before sending to the API
- New database columns: `source_full` (full text), `source_hash` (hash for deduplication)
- Analysis view: "Listing source" section with full text or link
- Duplicate banner with "Analyze again" or "View previous analysis" options
- Automatic database migration on startup — old records preserved

---

## v0.3 — Typography variables and analysis history

- All font sizes replaced with CSS variables (`--fs-2xs` to `--fs-4xl`) in `:root`
- Single `--fs-base-scale` variable to scale the entire interface
- Analysis detail view (`/job/<id>`) with collapsible layers
- Analysis history with status table (colored dots per layer)
- CSV export from Settings and navigation

---

## v0.2 — Deployment and multi-user

- Multi-user support with separate profiles (CV, Zero List, criteria)
- Registration system: first account without token, subsequent accounts via `INVITE_TOKEN`
- SQLite as the database instead of CSV
- `run.sh`, `stop.sh`, `restart.sh` scripts for shared hosting
- `deploy.sh` — deployment to server via SSH with rsync
- Cron every 5 minutes for auto-restart

---

## v0.1 — Foundation

- Local Flask server with web interface
- Six analysis layers: triage, product, business, reputation, values, fit
- Zero List — automatic rejection without analysis
- System prompt built dynamically from user profile
- Input via URL or pasted listing text
- Identification of hidden employer behind a recruitment agency
- `start.bat` / `start.sh` — one-click local startup
