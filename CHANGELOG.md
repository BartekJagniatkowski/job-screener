# Changelog — Job Screener

A tool for ethical evaluation of job listings. Every listing passes through six analysis layers before the question "is it worth applying?" is answered.

---

## v0.40 — Terminal interface redesign

- **Redesigned** — the experimental terminal interface now shows the list and the selected listing's details together on one screen, supports quick search, and has a settings menu for editing your profile fields without leaving the terminal.

---

## v0.39 — Experimental terminal interface

- **New** — an experimental terminal-based interface for browsing and analyzing listings, separate from the web app. A side project for exploring new ways to interact with the tool.

---

## v0.38 — Dark-mode fix

- **Fix** — the dashboard's animated dot background now brightens on hover in dark mode instead of fading out

---

## v0.37 — Table and hero polish

- **Fix** — listings with a long, wrapped job title no longer misalign their status badge and layer dots in the table
- **Fix** — the dashboard subheadline no longer overflows the screen on smaller phones
- **Hero polish** — small tuning to the animated dot background's spacing and colour

---

## v0.36 — Dashboard hero, fixes

- **Dashboard hero** — the main screen now opens with an animated dotted-grid background that reacts to your cursor
- **Fix** — applying to a job and then marking it as "Interview" now correctly records the application date
- **Fix** — the registration page now correctly says passwords need at least 10 characters
- **Cleanup** — removed unused leftover code from the recent redesign

---

## v0.35 — Visual redesign, job modal rebuild

- **New look** — refreshed the visual design across the app
- **Job detail view rebuilt** — easier to scan at a glance, with status and actions always visible while you browse
- **Keyboard shortcut** — press `d` anywhere to switch between light and dark mode
- **Fix** — the theme mask behind an open job listing now matches whichever mode you're in, and gained a subtle blur

---

## v0.34 — Security hardening, cost optimization, selection fix

- **Security hardening** — closed a gap where a redirect could bypass the tool's safeguard against fetching internal/private network addresses; added a cap on request size to prevent abuse
- **Cost optimization** — long listings are now capped before analysis, and rejected listings skip unnecessary detailed output — same results, lower API cost
- **Fix** — text selection was invisible in dark mode; now visible in both themes

---

## v0.33 — JSON parse fix

- **JSON parse fix** — analysis no longer fails when the model returns multi-line findings with literal newlines; a repair pass now handles this automatically before giving up with an error

---

## v0.32 — Feed setup fixes

- **Lever/Greenhouse validation** — adding a feed now checks the value looks like a company name from the board URL, with a clear error and example if not
- **Discover error surfacing** — feed fetch failures now show an error message naming the feed, instead of silently leaving it stuck at "Never fetched"
- **Plain-language feed hints** — Settings copy for feed types rewritten to avoid jargon, with concrete examples

---

## v0.31 — Badge/button redesign and fit score badge

- **Skills fit score** — now shown as a badge in the job detail header (`Fit X.X/5`), color-coded by fit status
- **Status dropdown fix** — fixed a bug where the dropdown showed "Worth considering" while the badge showed "AI rejected"
- **Dropdown label** — "Reject" renamed to "Rejected" for clarity
- **Badges and buttons redesigned** — badges are now small pill-shaped indicators with transparent backgrounds; secondary/danger buttons use solid backgrounds, making them visually distinct from badges
- **Modal layout** — verdict/archetype/fit badges grouped together; Delete button moved to the right, separated from other actions
- **Icons** — Re-analyze, Delete, Save notes, and Download CSV buttons now show a clearer trailing icon
- **Security** — hardened against prompt injection from job listing content
- **Early duplicate check** — pasting a job listing URL now checks for duplicates immediately, before you paste the full text or click Analyze
- **Company name display** — long parenthetical explanations in the company name are now shown as a "(?)" marker with the full text on hover, instead of cluttering the table

---

## v0.30 — Re-analysis banner + yellow/zero list styling

- **Re-analysis banner** — now shows which listing is being re-analyzed (company · role) instead of a generic "Re-analysis" label
- **Yellow and zero list notices** — redesigned as highlighted cards in the Overview tab, matching the Reality check section style

---

## v0.29 — Discover feed

- **Discover page** — new nav link shows unanalyzed listings from your configured feeds; Zero Rule pre-filters matches before display; "Analyze →" per item or "Analyze all" queues the full list; "Refresh" force-fetches all feeds
- **Feed management** — new Feeds section in Settings; supports Remote OK (tag-based), Lever (company slug), Greenhouse (company slug), and RSS/Atom feeds; fetched at most once per hour when you visit Discover
- **Keyword filter** — optional comma-separated keywords per feed; only items whose title matches a keyword are saved (prevents tag-noise from broad searches)

---

## v0.28 — Unified dashboard

- **Dashboard + history merged** — the separate History page is gone; the dashboard now shows the full analysis table with filters, search, sorting, and mobile cards; no row cap
- **Navigation simplified** — separate "Analyze" and "History" nav links removed; logo click goes to `/dashboard`
- **Redirects** — `/history` and `/job/<id>` issue 301 permanent redirects to `/dashboard`; bookmarks and external links continue to work
- **Removed** — CSV export link removed from dashboard
- **Bug fix** — new accounts no longer start with pre-filled Zero List and Criteria text; fields now show real placeholders
- **Account removal** — accounts no longer needed can now be removed (admin-side tool, no UI yet)
- **Mobile fix** — job detail tabs (Overview/Layers/Skills/CV/Interview) no longer get cut off on narrow screens; the tab bar now scrolls horizontally

---

## v0.27 — Command bar + detail tabs

- **Command bar** — analyze form replaced with a clean URL input + "Analyze →" button; ⌘/Ctrl+Enter submits from anywhere; ⌘/Ctrl+K focuses the input
- **Paste job text** — collapsible textarea for pasting listing content; auto-opens on scrape error
- **Detail tabs** — job modal now has five tabs: Overview, Layers, Skills, CV, Interview
- **Banner resilience** — analysis banner stops and shows an error if the server is unreachable, instead of spinning forever

---

## v0.26 — Statistics page rebuild + settings overhaul

- **Summary stat cards** — top of statistics page shows three at-a-glance cards: Total analyzed, Applications sent, Interviews
- **Horizontal application funnel** — proportional horizontal bar rows for all pipeline stages: Qualifying, Applied, Interview, Offer, Company rejected, Rejected by Zero Rule
- **Verdict distribution rebuild** — stacked bar replaced with labelled horizontal bar rows using the same visual language as the funnel
- **Per-section settings saves** — each profile field (CV, Zero Rule, Yellow List, Criteria) now saves independently with inline status feedback

---

## v0.25 — Cycling analysis banner

- **Multi-analysis cycling** — when 2+ analyses are running simultaneously, the banner cycles through each source label every 2.5 s with a top-down slide animation (text slides up and out, next slides in from below)
- **Queue counter** — a "X of Y" counter appears beside the label when cycling; hidden when only one analysis is active

---

## v0.24 — UX label cleanup

- **Status dropdown** — "Rejected (AI)" removed from the dropdown; it is set automatically by the AI and has no meaning as a manual selection
- **Rejection labels renamed** — "Rejected (AI)" → "AI rejected", "Rejected (user)" → "User rejected" across all views: badges, filter buttons, statistics legend, and the About page
- **Dropdown action label** — manual rejection option in the status dropdown renamed to "Reject" (imperative verb, distinct from the badge label "User rejected")
- **Section order** — CV tailoring now appears before interview prep in the job detail view (tailor first, then prep)

---

## v0.23 — CV tailoring

- **CV tailoring** — new section in each job detail (same eligibility as interview prep: worth considering, applied, interview, offer). Generates targeted guidance: what to emphasise, what to cut, bullet rewrites, and a suggested CV summary. Stored per-job; regenerate any time.

---

## v0.22 — Analysis banner improvements

- **Queue indicator** — when multiple analyses are running or pending, the banner shows `+N more` so it is clear that more than one analysis is in flight
- **Dismiss done banner** — the "analysis done" banner now has a `×` button to dismiss it without opening the result; "View result →" still navigates as before

---

## v0.21 — Mobile UX

- **Hamburger navigation** — nav collapses to a ☰ button on screens ≤768 px; tap opens a vertical dropdown with all links; closes on link click, outside click, or second tap; ✕ icon when open; theme toggle stays accessible at all screen sizes
- **History card list** — below 480 px the history table is replaced by a stacked card list; each card shows company, role, verdict badge, date, and application status; tap opens the detail modal; category filters and live search cover cards and table alike; delete and status changes update both views
- **Full-screen modal** — detail modal expands to fill the screen on phones (no overlay chrome, border-radius removed, `min-height: 100dvh`); sticky header and close/nav buttons remain
- **Touch targets** — all primary/secondary/small/danger buttons have a minimum tap height of 44 px on phone
- **Container padding** — horizontal padding reduced to 16 px and bottom padding increased to 60 px on phone to avoid content touching screen edges
- **Fix: sticky table header** — restored correct overflow behaviour on the table wrapper; changing it had broken the sticky header
- **Fix: theme toggle position** — theme toggle was appearing in the centre of the nav on desktop; moved to its correct position on the right

---

## v0.20 — Zero/Yellow List conflict detection + changelog improvements

- **Conflict check in Settings** — saving the profile is blocked if any entry appears in both Zero List and Yellow List; the error flash names the conflicting entries; entries are matched case-insensitively with `-` prefix stripped
- **Inline markdown in changelog** — bold and inline code now render correctly in `/changelog` and `/about`
- **Code snippet styling** — inline code in changelog has a distinct background in both light and dark mode

---

## v0.19 — Interview prep + security fixes

- **Interview prep** — AI-generated prep brief on any worth-considering, applied, interview, or offer job; sections: company context, likely rounds, JD→CV story mapping, checklist, questions to ask, red flags to probe; stored in DB and regeneratable; rate-limited to 5 calls/hour
- **Security fix:** CSRF tokens added to AJAX calls that were missing them
- **Security fix:** Rate limit added to the re-analyze endpoint

---

## v0.18 — UX improvements

- **Password change** — new form in Settings; requires current password, enforces 10-character minimum
- **Per-listing notes** — freeform textarea on every job detail (modal and full-page view); saved instantly; max 10 000 characters
- **History search** — live search input above the history table; filters by company, role, or verdict as you type; works alongside category filters
- **Sortable history columns** — click any column header to sort; defaults to newest first; arrow indicator shows active sort
- **Settings draft protection** — profile form saves to `localStorage` as you type; restored on next visit if the page value is empty; warns before leaving with unsaved changes
- **Interview and offer stages** — two new post-application statuses in the status dropdown: "Interview" (purple) and "Offer received" (green); setting offer automatically sets interview and applied; dates stored and shown in card header; filter buttons in history
- **Tab title during analysis** — browser tab shows ⏳ while analysis runs and ✓ when complete; resets on dismiss

---

## v0.17 — Security hardening II

- Session cookies now have `Secure`, `HttpOnly`, and `SameSite=Lax` flags — cookies not readable by JS, not sent cross-site, not sent over plain HTTP
- Session lifetime set to 7 days — sessions no longer live forever
- SSRF blocked in scraper — requests to private/loopback/link-local IPs rejected before any connection is made (covers cloud metadata endpoints, internal services)
- Username enumeration prevented — failed login always increments the lockout counter regardless of whether the username exists
- Server banner suppressed — all responses return `Server: unknown`
- Password minimum raised from 6 to 10 characters

---

## v0.16 — Security hardening

- `SECRET_KEY` is now required — app raises an error at startup if the env var is missing
- `FLASK_DEBUG` defaults to `0`
- CSRF protection via Flask-WTF: all state-changing POST endpoints require a valid token
- Account lockout: 5 failed login attempts within 5 minutes locks the account for 15 minutes
- Rate limiting: `/login` 10/5min, `/register` 3/hr, `/analyze` 20/hr per IP
- Security headers on every response: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`
- Constant-time comparison for invite tokens and password verification

---

## v0.15 — About page

- New `/about` route (no login required) with project philosophy, six-layer descriptions, reality check explanation, all six verdicts/states, and inline changelog
- README expanded with "The idea" and "How the analysis works" sections covering layers, verdicts, and reality check
- "About" link added to nav; footer removed entirely

---

## v0.14.1 — Rename Analytics → Statistics

- Nav link, page title, and browser tab renamed from "Analytics" to "Statistics"

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
- Layer flags simplified to flag-count-only bars sorted by severity
- Fit score distribution and Role archetypes collapsed by default; click to expand
- Average fit score moved to TL;DR text

---

## v0.12.1 — History table fixes

- Sticky table header restored
- Layer dots now vertically centred and fill the full row height
- Table width reverted to 1280px container

---

## v0.12 — History table redesign

- Rebuilt from 12 columns to 7: Date, Role, Company, Verdict, L0, Layers, Fit
- Six analysis-layer dots collapsed into one compact dot strip with hover tooltips
- Fit score surfaced as its own column, colour-coded by fit status
- Filter bar and table header sticky on scroll
- "Show all" filter button resets all category filters at once

---

## v0.11 — Background analysis with persistent banner

- Analysis runs in a background thread — navigate away immediately after submitting
- Persistent banner below nav shows progress on every page: spinner while running; green clickable strip with company and verdict when done; red dismissible strip on error

---

## v0.10 — Full UI translation to English

- All text translated to English across every file: templates, backend, system prompt, error messages
- Layer names, status labels, company name fallback, and CSV export filename all updated

---

## v0.9.2 — Stability fixes

- Database indexes on key columns — faster queries with larger history
- API timeout increased to 120s — margin for complex analyses
- Scraper response size limit: 5 MB — protection against very large pages
- Better URL validation throughout

---

## v0.9.1 — Listing URL in modal card header

- Listing URL surfaced at the top of the modal card header — visible directly below the verdict summary

---

## v0.9 — History filtering, card redesign and visual consistency

- Category filter in analysis history: toggle buttons for each of the 6 statuses, any combination, state saved in browser
- Badges without background — border and text colour only; row highlight takes over as the colour signal
- Job card header switched to vertical layout: badge → role → company → summary → rejection reason → date
- Unknown company labelled "Unknown" instead of "—"; model required to explain the missing name in the verdict summary

---

## v0.8 — Rejection confirmation logic

- New `verdict_confirmed` field distinguishes automatic rejections (Zero List) from AI rejections requiring user confirmation
- Verdict dropdown shows two rejection states: "Rejected (AI)" and "Rejected — confirm"
- Visual row marking in history: strikethrough for confirmed rejections, lighter background for unconfirmed, green for submitted applications

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

---

## v0.5 — Evidence from listing and source verification

- Added evidence rule: model required to cite the listing for every flag and rejection
- Evidence displayed in the analysis view for each flagged layer
- Status message before analysis: green (new listing) or yellow (duplicate)

---

## v0.4 — Duplicate detection and listing source

- Duplicate detection based on SHA-256 of content/URL before sending to the API
- Analysis view: "Listing source" section with full text or link
- Duplicate banner with "Analyze again" or "View previous analysis" options

---

## v0.3 — Typography variables and analysis history

- All font sizes replaced with CSS variables — single variable to scale the entire interface
- Analysis detail view with collapsible layers
- Analysis history with status table (coloured dots per layer)
- CSV export from Settings and navigation

---

## v0.2 — Deployment and multi-user

- Multi-user support with separate profiles (CV, Zero List, criteria)
- Registration system: first account without token, subsequent accounts via invite token
- SQLite as the database

---

## v0.1 — Foundation

- Local Flask server with web interface
- Six analysis layers: triage, product, business, reputation, values, fit
- Zero List — automatic rejection without analysis
- System prompt built dynamically from user profile
- Input via URL or pasted listing text
- Identification of hidden employer behind a recruitment agency
