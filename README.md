# Job Screener

A tool for ethical evaluation of job listings. Every listing passes through six analysis layers before the question "is it worth applying?" is answered: triage, product, business, reputation, values, and skills fit against your profile.

---

## The idea

Most job search tools optimise for more applications. This one optimises for fewer, better ones.

Job Screener runs every listing through a structured analysis before you decide whether to apply. The goal is not to maximise throughput — it is to protect your time and attention by surfacing what the listing language reveals about the company and the role.

The tool works against the logic of the recruitment market: it helps you filter by ethical and practical criteria instead of chasing volume.

---

## How the analysis works

Each listing is evaluated across six layers:

| Layer | What it checks |
|---|---|
| **Triage** | Role fit against your trajectory, initial signals, whether the employer is hidden behind a recruiter |
| **Product** | What the product actually does, marketing claims vs. reality, AI-washing, verifiability of the mission |
| **Business** | Revenue model, funding structure, investors, PE/VC involvement |
| **Reputation** | Uses the model's knowledge: Glassdoor/Indeed/Blind ratings and trends, dominant review themes, C-level history, layoff patterns, media, regulatory issues |
| **Values** | Mission coherence, ethical traps, gap between stated values and observable behaviour |
| **Skills fit** | Your strengths against the role requirements, gaps, what to address in the application |

Each layer returns a status: **ok**, **warning** (caution signal), or **flag** (serious concern). The final verdict:

- **Worth considering** — no serious blockers
- **Needs review** — at least one warning layer or yellow-list hit
- **Rejected** — a flag, zero-list match, or AI assessment

### Reality check

Before the layer analysis, the tool synthesises what the listing language actually signals about the role. Corpo-speak is decoded into plain English — phrases like "fast-paced environment" or "wear many hats" are translated to what they typically mean in practice. Purely informational; does not affect the verdict.

---

## Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — environment and dependency manager
- Anthropic API key (`claude-sonnet-4-6`)

---

## Quick start (local)

```bash
# 1. Clone the repo and enter the directory
git clone https://github.com/BartekJagniatkowski/job-screener
cd job-screener

# 2. Copy and fill in the configuration
cp config.env.template config.env
# add ANTHROPIC_API_KEY and SECRET_KEY to config.env
# generate SECRET_KEY: python -c "import secrets; print(secrets.token_hex(32))"

# 3. Install dependencies and run
uv sync
bash server.sh start
```

Open `http://localhost:5001` (or the port set in `config.env`).

---

## First run

On first launch the app will prompt you to create an admin account.

After logging in go to **Settings** and fill in:

| Field | Description |
|---|---|
| **CV** | Your experience and skills — the more detail, the better the matching |
| **Zero Rule** | Companies, industries, or categories that trigger automatic rejection without further analysis |
| **Yellow List** | Signals that force a "needs review" verdict even when all other layers are green |
| **Additional criteria** | Preferred sectors, cultural red flags, priorities in evaluating listings |

> **Conflict check:** saving is blocked if any entry appears in both Zero Rule and Yellow List. Entries are matched case-insensitively with list prefixes (`- `) stripped.

---

## Managing the server

```bash
bash server.sh start    # production: gunicorn daemon, 2 workers
bash server.sh stop     # stop the daemon
bash server.sh restart  # restart (stop → start)
bash server.sh status   # check if running and which PID

uv run --env-file config.env python app.py  # development (no daemon, hot-reload)
```

Production logs: `/tmp/screener-access.log`, `/tmp/screener-error.log`

### If restart doesn't pick up new code

`server.sh restart` kills the PID stored in `/tmp/screener.pid`. If gunicorn was started outside of `server.sh` (manually or via a different script), the PID file won't match the actual master process — the kill silently hits the wrong target and old workers keep serving.

Verify before restarting:

```bash
cat /tmp/screener.pid
ps aux | grep gunicorn | grep -v grep | awk '{print $2}'
```

If the PIDs don't match, wipe all instances first:

```bash
pkill -f "gunicorn.*app:app" && sleep 2 && bash server.sh start
```

Always use `server.sh` exclusively — never start gunicorn manually.

---

## Terminal interface (experimental)

```bash
uv run --env-file config.env python cli.py
```

A Textual-based TUI for browsing and analyzing listings without the web app — job list, live detail panel, and a Settings menu, all from the terminal. `j`/`k` to navigate, `/` or `:` to search/run commands, `Ctrl+S` for settings. Experimental side project, not a production entry point — the web app (`app.py`) is the supported way to run Job Screener.

---

## Deployment to a server

```bash
./deploy.sh user@yourserver.com /var/www/job-screener
```

The script copies files, installs dependencies via `uv`, and starts the service. After deployment:

1. Create `/var/www/job-screener/config.env` with your API key
2. `sudo systemctl restart job-screener`
3. Configure nginx (example in the script output)

---

## Inviting new users

Set `INVITE_TOKEN` in `config.env`. New accounts can only be created via:

```
https://your.domain.com/register?token=YOUR_TOKEN
```

---

## Configuration (`config.env`)

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (required) |
| `ANTHROPIC_MODEL` | Model ID (default: `claude-sonnet-4-6`); must support extended thinking |
| `INTERVIEW_PREP_MODEL` | Model for interview prep (default: same as `ANTHROPIC_MODEL`). Use `claude-haiku-4-5-20251001` to reduce cost. |
| `CV_TAILORING_MODEL` | Model for CV tailoring (default: `claude-haiku-4-5-20251001`). Use `claude-sonnet-4-6` for richer output. |
| `SECRET_KEY` | Flask session key — **required**, app won't start without it. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `INVITE_TOKEN` | Invitation token for new users |
| `PORT` | Application port (default: `5001`) |
| `FLASK_DEBUG` | Set to `1` for local development only — never in production (default: `0`) |
| `SESSION_COOKIE_SECURE` | Defaults to `True` (cookies only sent over HTTPS). Set to `False` for local dev without HTTPS. |

---

## Features

- **Analysis from URL or pasted text** — scrapes the listing automatically; when the site blocks (LinkedIn, Indeed, etc.) prompts to paste the content
- **Six analysis layers** with verdict and justification; the reputation layer uses the model's knowledge about the company (Glassdoor, media, C-level history)
- **Reality check** — plain-English decoding of listing language before the layer analysis; corpo-speak translated to what it actually means
- **Detail modal** — clicking a row in history or dashboard opens the details in place; ← → navigation between listings, URL reflects the currently viewed listing
- **Verdicts and states** — worth considering / needs review / rejected (AI) / rejected (confirmed); applied / interview / offer / rejected by company
- **Per-listing notes** — freeform notes on every job detail; saved via AJAX
- **Analysis history** — table with live search, sortable columns, visual category filtering, CSV export
- **Statistics dashboard** — aggregated statistics: verdict distribution, application funnel, per-layer flag counts, fit score averages
- **Mobile UX** — hamburger navigation at ≤768 px; card-based history list and full-screen detail modal at ≤480 px; 44 px touch targets
- **CV tailoring** — targeted rewrite guidance for each job: what to emphasise, what to cut, bullet rewrites, and a suggested CV summary; generated on demand from the job detail view
- **Analysis banner** — persistent progress banner cycles through each queued analysis label with a slide animation and an "X of Y" counter when multiple analyses run simultaneously; done banner can be dismissed without opening the result
- **Light/dark mode** — toggle in navigation, preference saved in the browser
- **Multi-user** — each user has a separate profile, lists, and history; password change in Settings

---

## File structure

```
job-screener/
├── app.py              — Flask routing, auth, endpoints
├── analyzer.py         — system prompt and Claude API integration
├── database.py         — SQLite schema, migrations, operations
├── scraper.py          — URL content fetching, normalisation
├── static/style.css    — all styles (zero inline CSS in templates)
├── templates/          — Jinja2 templates
├── data/screener.db    — database (created automatically, do not commit)
├── config.env          — local configuration (do not commit)
├── config.env.template — configuration template
├── pyproject.toml      — project dependencies (uv)
├── server.sh           — server management: start|stop|restart|status
└── deploy.sh           — deployment script
```

---

## Data export

Settings → **Download CSV** — the file contains all analysis layers and opens in Excel and Google Sheets.
