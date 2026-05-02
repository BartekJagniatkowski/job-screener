# Job Screener

A tool for ethical analysis of job listings. Every listing passes through six analysis layers before the question "is it worth applying?" is answered: triage, product, business, reputation, values, and skills fit against your profile.

---

## Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — environment and dependency manager
- Anthropic API key (`claude-sonnet-4-6`)

---

## Quick start (local)

```bash
# 1. Clone the repo and enter the directory
git clone https://github.com/BartekBroda/job-screener
cd job-screener

# 2. Copy and fill in the configuration
cp config.env.template config.env
# add your ANTHROPIC_API_KEY to config.env

# 3. Install dependencies and run
uv sync
bash server.sh start
```

The browser will open automatically at `http://localhost:5000`.

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
| `SECRET_KEY` | Flask session key (change on the server) |
| `INVITE_TOKEN` | Invitation token for new users |
| `PORT` | Application port (default: `5000`) |

---

## Features

- **Analysis from URL or pasted text** — scrapes the listing automatically; when the site blocks (LinkedIn, Indeed, etc.) prompts to paste the content
- **Six analysis layers** with verdict and justification; the reputation layer uses the model's knowledge about the company (Glassdoor, media, C-level history)
- **Detail modal** — clicking a row in history or dashboard opens the details in place; ← → navigation between listings, URL reflects the currently viewed listing
- **Verdicts and states** — worth considering / needs review / rejected (AI) / rejected (confirmed); mark submitted applications
- **Analysis history** — table with visual category filtering, CSV export from Settings
- **Light/dark mode** — toggle in navigation, preference saved in the browser
- **Multi-user** — each user has a separate profile, lists, and history

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
