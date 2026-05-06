# Background Analysis + Persistent Banner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run job analysis in a background thread so users can navigate the app freely, with a persistent banner below the nav showing live status on every page.

**Architecture:** `POST /analyze` creates an `analyses` DB record and spawns a daemon thread, returning `{analysis_id}` immediately. The thread runs the Claude API call, writes the result to `jobs`, and updates `analyses`. A polling IIFE in `base.html` reads `localStorage` on every page load and drives a fixed banner through running → done → error states. Any gunicorn worker can serve status polls by reading the shared SQLite DB.

**Tech Stack:** Python `threading`, SQLite (new `analyses` table), `pytest` + Flask test client, vanilla JS (`localStorage`, `setInterval`, `fetch`), CSS custom properties.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `database.py` | Modify | `analyses` table in SCHEMA; `create_analysis()`, `update_analysis_status()`, `get_analysis()`; stuck-job cleanup in `init_db()`; `save_job()` returns job id |
| `app.py` | Modify | `_run_analysis_bg()` thread fn; modify `run_analyze()` + `reanalyze()`; add `GET /analysis_status/<id>` |
| `static/style.css` | Modify | `.analysis-banner` and state variant classes |
| `templates/base.html` | Modify | `#analysis-banner` element + polling IIFE |
| `templates/dashboard.html` | Modify | `runAnalysis()` handles `{analysis_id}`; dispatches `analysisStarted` event |
| `templates/history.html` | Modify | `reanalyze()` handles `{analysis_id}` |
| `tests/__init__.py` | Create | Empty package marker |
| `tests/conftest.py` | Create | Flask test client + temp DB fixture |
| `tests/test_analyses_db.py` | Create | Unit tests for new DB functions |
| `tests/test_analysis_endpoints.py` | Create | Integration tests for new/modified endpoints |

---

### Task 1: Test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Install pytest**

```bash
uv add --dev pytest
```

Expected: `pyproject.toml` and `uv.lock` updated.

- [ ] **Step 2: Create `tests/__init__.py`**

Empty file:
```python
```

- [ ] **Step 3: Create `tests/conftest.py`**

`database.DB_PATH` must be patched before `app.py` is imported, because `app.py` calls `init_db()` at module level.

```python
import os
import tempfile
import pathlib
import pytest

# Create temp DB and patch DB_PATH before app is imported
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)

import database
database.DB_PATH = pathlib.Path(_db_path)

from app import app as flask_app


@pytest.fixture(scope="session")
def app():
    flask_app.config.update({"TESTING": True, "SECRET_KEY": "test-secret"})
    from database import init_db
    init_db()
    # Create a test user (user_id=1)
    from database import create_user
    try:
        create_user("testuser", "testpass")
    except Exception:
        pass  # already exists from a prior run
    yield flask_app
    os.unlink(_db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in_client(client):
    client.post("/login", data={"username": "testuser", "password": "testpass"})
    return client
```

- [ ] **Step 4: Verify pytest discovers tests**

```bash
uv run pytest tests/ --collect-only
```

Expected: `0 items` collected, no import errors.

- [ ] **Step 5: Commit**

```bash
git add tests/ pyproject.toml uv.lock
git commit -m "test: set up pytest with Flask test client and temp DB"
```

---

### Task 2: `analyses` table and DB functions

**Files:**
- Modify: `database.py`
- Create: `tests/test_analyses_db.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_analyses_db.py`:

```python
import pytest
from database import create_analysis, update_analysis_status, get_analysis, init_db, get_conn


def test_create_analysis_returns_uuid(app):
    analysis_id = create_analysis(user_id=1, source_label="Senior PM · Figma")
    assert len(analysis_id) == 36
    assert analysis_id.count("-") == 4


def test_create_analysis_initial_status(app):
    analysis_id = create_analysis(user_id=1, source_label="Test label")
    row = get_analysis(analysis_id, user_id=1)
    assert row["status"] == "pending"
    assert row["source_label"] == "Test label"
    assert row["result_job_id"] is None
    assert row["error"] is None


def test_update_to_running(app):
    analysis_id = create_analysis(user_id=1, source_label="Test")
    update_analysis_status(analysis_id, "running")
    row = get_analysis(analysis_id, user_id=1)
    assert row["status"] == "running"
    assert row["finished_at"] is None


def test_update_to_done(app):
    analysis_id = create_analysis(user_id=1, source_label="Test")
    update_analysis_status(analysis_id, "done", result_job_id=99)
    row = get_analysis(analysis_id, user_id=1)
    assert row["status"] == "done"
    assert row["result_job_id"] == 99
    assert row["finished_at"] is not None


def test_update_to_error(app):
    analysis_id = create_analysis(user_id=1, source_label="Test")
    update_analysis_status(analysis_id, "error", error="API timeout")
    row = get_analysis(analysis_id, user_id=1)
    assert row["status"] == "error"
    assert row["error"] == "API timeout"
    assert row["finished_at"] is not None


def test_get_analysis_wrong_user_returns_none(app):
    analysis_id = create_analysis(user_id=1, source_label="Test")
    assert get_analysis(analysis_id, user_id=999) is None


def test_init_db_cleans_stuck_analyses(app):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analyses (id, user_id, status, source_label, started_at) "
            "VALUES ('stuck-uuid', 1, 'running', 'stuck', datetime('now', '-10 minutes'))"
        )
    init_db()
    row = get_analysis("stuck-uuid", user_id=1)
    assert row["status"] == "error"
    assert row["error"] == "Server restarted"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_analyses_db.py -v
```

Expected: `ImportError: cannot import name 'create_analysis' from 'database'`

- [ ] **Step 3: Add `analyses` table to SCHEMA in `database.py`**

In `database.py`, find the closing `);` of the `jobs` table and the closing `"""` of `SCHEMA`. Insert before the `"""`:

```sql

CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    source_label TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    result_job_id INTEGER,
    error TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

- [ ] **Step 4: Add `import uuid` to the imports at the top of `database.py`**

Add after `import datetime`:
```python
import uuid
```

- [ ] **Step 5: Add the three DB functions to `database.py`**

Add after the existing `check_duplicate()` function (or at the end of the file, before `get_analytics()`):

```python
def create_analysis(user_id: int, source_label: str) -> str:
    analysis_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analyses (id, user_id, status, source_label) VALUES (?, ?, 'pending', ?)",
            (analysis_id, user_id, source_label),
        )
    return analysis_id


def update_analysis_status(
    analysis_id: str,
    status: str,
    result_job_id: int = None,
    error: str = None,
) -> None:
    with get_conn() as conn:
        if status == "done":
            conn.execute(
                "UPDATE analyses SET status=?, result_job_id=?, finished_at=datetime('now') WHERE id=?",
                (status, result_job_id, analysis_id),
            )
        elif status == "error":
            conn.execute(
                "UPDATE analyses SET status=?, error=?, finished_at=datetime('now') WHERE id=?",
                (status, error, analysis_id),
            )
        else:
            conn.execute(
                "UPDATE analyses SET status=? WHERE id=?",
                (status, analysis_id),
            )


def get_analysis(analysis_id: str, user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """SELECT a.*, j.company, j.role, j.verdict
               FROM analyses a
               LEFT JOIN jobs j ON j.id = a.result_job_id
               WHERE a.id = ? AND a.user_id = ?""",
            (analysis_id, user_id),
        ).fetchone()
```

- [ ] **Step 6: Add stuck-job cleanup to `init_db()`**

Inside `init_db()`, in the `with get_conn() as conn:` block, after all the existing `ALTER TABLE` and `RENAME COLUMN` migrations, add:

```python
        try:
            conn.execute(
                """UPDATE analyses SET status='error', error='Server restarted'
                   WHERE status IN ('pending', 'running')
                   AND started_at < datetime('now', '-5 minutes')"""
            )
        except Exception:
            pass  # analyses table may not exist in very old DBs yet
```

- [ ] **Step 7: Make `save_job()` return the inserted job id**

In `save_job()`, find the `conn.execute("""INSERT INTO jobs ...""", (...))` call (currently the last statement in the `with get_conn() as conn:` block). Assign it and return the rowid:

```python
        conn.execute("""INSERT INTO jobs ...""", (...))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
```

Change the function signature line from `-> None:` to `-> int:`.

- [ ] **Step 8: Run tests**

```bash
uv run pytest tests/test_analyses_db.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add database.py tests/test_analyses_db.py
git commit -m "feat: analyses table and DB functions for background job tracking"
```

---

### Task 3: Background thread + modified `/analyze` + new `/analysis_status`

**Files:**
- Modify: `app.py`
- Create: `tests/test_analysis_endpoints.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_analysis_endpoints.py`:

```python
from unittest.mock import patch, MagicMock
from database import create_analysis, update_analysis_status, get_conn


def test_analyze_returns_analysis_id(logged_in_client):
    with patch("app._run_analysis_bg"):
        with patch("app.threading") as mock_threading:
            mock_threading.Thread.return_value = MagicMock()
            resp = logged_in_client.post("/analyze", data={"text": "Some job listing text here"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "analysis_id" in data
    assert len(data["analysis_id"]) == 36
    assert "result" not in data


def test_analyze_spawns_thread(logged_in_client):
    with patch("app.threading") as mock_threading:
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        logged_in_client.post("/analyze", data={"text": "Some job listing"})
    mock_threading.Thread.assert_called_once()
    mock_thread.start.assert_called_once()


def test_analysis_status_pending(logged_in_client, app):
    analysis_id = create_analysis(user_id=1, source_label="Figma PM")
    resp = logged_in_client.get(f"/analysis_status/{analysis_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "pending"
    assert data["source_label"] == "Figma PM"
    assert data["result_job_id"] is None


def test_analysis_status_done_includes_job_fields(logged_in_client, app):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (user_id, company, role, verdict, verdict_confirmed) "
            "VALUES (1, 'Figma', 'Senior PM', 'worth_considering', 1)"
        )
        job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    analysis_id = create_analysis(user_id=1, source_label="Figma PM")
    update_analysis_status(analysis_id, "done", result_job_id=job_id)
    resp = logged_in_client.get(f"/analysis_status/{analysis_id}")
    data = resp.get_json()
    assert data["status"] == "done"
    assert data["result_job_id"] == job_id
    assert data["company"] == "Figma"
    assert data["verdict"] == "worth_considering"


def test_analysis_status_wrong_user_returns_404(logged_in_client, app):
    analysis_id = create_analysis(user_id=999, source_label="Other user")
    resp = logged_in_client.get(f"/analysis_status/{analysis_id}")
    assert resp.status_code == 404


def test_analysis_status_nonexistent_returns_404(logged_in_client):
    resp = logged_in_client.get("/analysis_status/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_analysis_endpoints.py -v
```

Expected: FAIL — `analysis_id` not in response, `/analysis_status` route not found.

- [ ] **Step 3: Add `import threading` to `app.py`**

Add with the stdlib imports at the top:
```python
import threading
```

- [ ] **Step 4: Add `create_analysis`, `update_analysis_status`, `get_analysis` to the `from database import ...` line in `app.py`**

```python
from database import (
    init_db, get_user, create_user, get_user_by_id,
    update_user_profile, save_job, get_jobs, get_job,
    export_csv, user_count, check_duplicate, update_verdict, update_job_url, delete_job, update_applied,
    update_company_rejected, update_job_status, verify_password, get_analytics,
    create_analysis, update_analysis_status, get_analysis,
)
```

- [ ] **Step 5: Add `_run_analysis_bg()` to `app.py`**

Add this function directly before the `@app.route("/analyze", ...)` route definition:

```python
def _run_analysis_bg(
    analysis_id: str,
    user: dict,
    input_text: str,
    url: str,
    scraped: bool,
) -> None:
    try:
        update_analysis_status(analysis_id, "running")
        result = analyze(user, input_text, "text", API_KEY)
        job_id = save_job(user["id"], result, source_url=url, source_text=input_text)
        update_analysis_status(analysis_id, "done", result_job_id=job_id)
    except Exception as e:
        update_analysis_status(analysis_id, "error", error=str(e))
```

- [ ] **Step 6: Modify `run_analyze()` in `app.py`**

Replace the entire `try: ... except Exception as e: return jsonify({"error": str(e)}), 500` block at the end of `run_analyze()` with:

```python
    source_label = url or (input_text or "")[:60].replace("\n", " ")
    analysis_id = create_analysis(user["id"], source_label)
    t = threading.Thread(
        target=_run_analysis_bg,
        args=(analysis_id, {k: user[k] for k in user.keys()}, input_text, url, scraped),
        daemon=True,
    )
    t.start()
    return jsonify({"analysis_id": analysis_id})
```

Note: `{k: user[k] for k in user.keys()}` converts `sqlite3.Row` to a plain dict so the thread doesn't share a live DB row reference.

- [ ] **Step 7: Add `GET /analysis_status/<analysis_id>` endpoint to `app.py`**

Add immediately after `run_analyze()`:

```python
@app.route("/analysis_status/<analysis_id>")
@login_required
def analysis_status(analysis_id: str):
    user = current_user()
    row = get_analysis(analysis_id, user["id"])
    if row is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "status": row["status"],
        "source_label": row["source_label"],
        "result_job_id": row["result_job_id"],
        "company": row["company"],
        "role": row["role"],
        "verdict": row["verdict"],
        "error": row["error"],
    })
```

- [ ] **Step 8: Run tests**

```bash
uv run pytest tests/test_analysis_endpoints.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add app.py tests/test_analysis_endpoints.py
git commit -m "feat: async /analyze with background thread and /analysis_status endpoint"
```

---

### Task 4: Modify `/reanalyze/<id>`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Replace the synchronous analysis block in `reanalyze()` in `app.py`**

Find the `try:` block at the end of `reanalyze()` (starting at `result = analyze(user, input_text, "text", API_KEY)`). Replace the entire `try/except` with:

```python
    source_label = saved_url or (saved_text or "")[:60].replace("\n", " ") or "Re-analysis"
    analysis_id = create_analysis(user["id"], source_label)
    t = threading.Thread(
        target=_run_analysis_bg,
        args=(analysis_id, {k: user[k] for k in user.keys()}, input_text, saved_url, bool(saved_url)),
        daemon=True,
    )
    t.start()
    return jsonify({"analysis_id": analysis_id})
```

- [ ] **Step 2: Restart server and check for import errors**

```bash
bash server.sh restart && sleep 2 && tail -10 /tmp/screener-error.log
```

Expected: workers boot cleanly, no tracebacks.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: async /reanalyze with background thread"
```

---

### Task 5: Banner CSS

**Files:**
- Modify: `static/style.css`

- [ ] **Step 1: Find the nav styles section in `style.css`**

```bash
grep -n "nav\|\.nav" static/style.css | head -20
```

Note the line number where nav styles end.

- [ ] **Step 2: Add banner CSS after nav styles**

```css
/* ── analysis banner ─────────────────────────────────────────────── */
.analysis-banner {
  display: none;
  width: 100%;
  padding: 8px 20px;
  font-family: var(--fm);
  font-size: var(--fs-xs);
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid var(--border);
  box-sizing: border-box;
}
.analysis-banner.is-visible { display: flex; }
.analysis-banner.is-running {
  background: #161a1f;
  border-bottom-color: #1e2428;
  color: var(--muted);
}
.analysis-banner.is-done {
  background: #0f1a12;
  border-bottom-color: #1a2e1c;
  color: var(--muted);
  cursor: pointer;
}
.analysis-banner.is-error {
  background: #1a0f0f;
  border-bottom-color: #2e1a1a;
  color: var(--muted);
}
.analysis-banner-spinner {
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  border: 1.5px solid var(--accent);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin-banner 0.8s linear infinite;
  display: inline-block;
}
.analysis-banner-icon { flex-shrink: 0; font-size: 14px; }
.analysis-banner-label { color: var(--muted); }
.analysis-banner-source { color: var(--dim); }
.analysis-banner-badge {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: var(--fs-2xs);
  border: 1px solid currentColor;
  margin-left: 4px;
}
.analysis-banner-badge.badge-worth_considering { color: #4a9eff; }
.analysis-banner-badge.badge-warning { color: #f0c040; }
.analysis-banner-badge.badge-rejected { color: #e74c3c; }
.analysis-banner-action { margin-left: auto; color: var(--dim); font-size: var(--fs-xs); }
.analysis-banner-dots {
  margin-left: auto;
  display: flex;
  gap: 5px;
  align-items: center;
}
.analysis-banner-dot {
  width: 22px;
  height: 3px;
  background: var(--accent);
  border-radius: 2px;
  display: inline-block;
}
@keyframes spin-banner { to { transform: rotate(360deg); } }
@keyframes pulse-dot { 0%,100%{opacity:0.15} 50%{opacity:1} }
```

- [ ] **Step 3: Commit**

```bash
git add static/style.css
git commit -m "style: analysis-banner CSS classes"
```

---

### Task 6: Banner HTML + polling IIFE in `base.html`

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Add banner element to `base.html`**

Find the closing `{% endif %}` of the `{% if session.user_id %}` nav block (the line just before `<div class="container">`). Insert after it:

```html
<div id="analysis-banner" class="analysis-banner" role="status" aria-live="polite"></div>
```

- [ ] **Step 2: Add the polling IIFE to `base.html`**

Insert a new `<script>` block immediately before the `{% block scripts %}{% endblock %}` line:

```html
<script>
(function () {
  var POLL_MS = 3000;
  var banner = document.getElementById('analysis-banner');
  if (!banner) return;
  var timer = null;

  function vLabel(v) {
    return v === 'worth_considering' ? 'worth considering'
         : v === 'warning' ? 'needs review'
         : v === 'rejected' ? 'rejected' : (v || '');
  }

  function showRunning(src) {
    banner.className = 'analysis-banner is-running is-visible';
    banner.onclick = null;
    banner.innerHTML =
      '<span class="analysis-banner-spinner"></span>' +
      '<span class="analysis-banner-label">Analyzing — </span>' +
      '<span class="analysis-banner-source">' + (src || '') + '</span>' +
      '<span class="analysis-banner-dots">' +
        '<span class="analysis-banner-dot" style="animation:pulse-dot 1.2s ease-in-out 0s infinite"></span>' +
        '<span class="analysis-banner-dot" style="animation:pulse-dot 1.2s ease-in-out 0.4s infinite"></span>' +
        '<span class="analysis-banner-dot" style="animation:pulse-dot 1.2s ease-in-out 0.8s infinite"></span>' +
      '</span>';
  }

  function showDone(d) {
    banner.className = 'analysis-banner is-done is-visible';
    var bc = 'analysis-banner-badge badge-' + (d.verdict || '');
    banner.innerHTML =
      '<span class="analysis-banner-icon">✓</span>' +
      '<span class="analysis-banner-label">Analysis done — </span>' +
      '<span class="analysis-banner-source">' + (d.company || '') + (d.role ? ' · ' + d.role : '') + '</span>' +
      '<span class="' + bc + '">' + vLabel(d.verdict) + '</span>' +
      '<span class="analysis-banner-action">View result →</span>';
    banner.onclick = function () {
      localStorage.removeItem('activeAnalysis');
      window.location.href = '/job/' + d.result_job_id;
    };
  }

  function showError(msg) {
    banner.className = 'analysis-banner is-error is-visible';
    banner.onclick = null;
    banner.innerHTML =
      '<span class="analysis-banner-icon">✕</span>' +
      '<span class="analysis-banner-label">Analysis failed — </span>' +
      '<span class="analysis-banner-source">' + (msg || 'Unknown error') + '</span>' +
      '<span class="analysis-banner-action" id="ab-dismiss">Dismiss ×</span>';
    var btn = document.getElementById('ab-dismiss');
    if (btn) btn.onclick = function (e) {
      e.stopPropagation();
      localStorage.removeItem('activeAnalysis');
      banner.className = 'analysis-banner';
      banner.innerHTML = '';
      if (timer) clearInterval(timer);
    };
  }

  function poll(id, src) {
    fetch('/analysis_status/' + id)
      .then(function (r) {
        if (r.status === 404) {
          localStorage.removeItem('activeAnalysis');
          banner.className = 'analysis-banner';
          if (timer) clearInterval(timer);
          return null;
        }
        return r.json();
      })
      .then(function (d) {
        if (!d) return;
        if (d.status === 'pending' || d.status === 'running') {
          showRunning(d.source_label || src);
        } else if (d.status === 'done') {
          if (timer) clearInterval(timer);
          showDone(d);
        } else if (d.status === 'error') {
          if (timer) clearInterval(timer);
          localStorage.removeItem('activeAnalysis');
          showError(d.error);
        }
      })
      .catch(function () { /* silent retry */ });
  }

  function startPolling(id, src) {
    showRunning(src);
    poll(id, src);
    timer = setInterval(function () { poll(id, src); }, POLL_MS);
  }

  var stored = localStorage.getItem('activeAnalysis');
  if (stored) {
    try {
      var active = JSON.parse(stored);
      if (active && active.id) startPolling(active.id, active.source_label || '');
    } catch (e) { localStorage.removeItem('activeAnalysis'); }
  }

  window.addEventListener('analysisStarted', function (e) {
    if (timer) clearInterval(timer);
    startPolling(e.detail.id, e.detail.source_label || '');
  });
})();
</script>
```

- [ ] **Step 3: Manual smoke test — banner visible on non-dashboard pages**

1. Paste job text on dashboard → click Analyze
2. Immediately navigate to History
3. Confirm banner shows below nav in running state (spinner + pulsing dots)
4. Wait for completion → banner turns green

- [ ] **Step 4: Commit**

```bash
git add templates/base.html
git commit -m "feat: persistent analysis banner with localStorage polling in base.html"
```

---

### Task 7: Update `dashboard.html` and `history.html`

**Files:**
- Modify: `templates/dashboard.html`
- Modify: `templates/history.html`

- [ ] **Step 1: Find the `if (data.ok)` branch in `runAnalysis()` in `dashboard.html`**

```bash
grep -n "data\.ok\|data\.result\|renderResult" templates/dashboard.html | head -10
```

Note the line numbers of the block that handles a successful analysis result.

- [ ] **Step 2: Replace the `if (data.ok)` branch in `runAnalysis()`**

Find:
```js
    if (data.ok) {
      // ... lines rendering result via renderResult() ...
    }
```

Replace with:
```js
    if (data.analysis_id) {
      document.getElementById('loading').style.display = 'none';
      statusEl.style.display = 'none';
      document.getElementById('result-box').innerHTML =
        '<div class="notice ok">Analysis started — you can navigate away. ' +
        'The banner above will update when done.</div>';
      var active = {
        id: data.analysis_id,
        source_label: url || (text || '').slice(0, 60).replace(/\n/g, ' ')
      };
      localStorage.setItem('activeAnalysis', JSON.stringify(active));
      window.dispatchEvent(new CustomEvent('analysisStarted', { detail: active }));
    }
```

Keep the `data.scrape_error`, `data.duplicate`, and `catch(e)` branches exactly as they are — those endpoints still respond synchronously.

- [ ] **Step 3: Find the `reanalyze` function in `dashboard.html`**

```bash
grep -n "reanalyze\|new_job_id" templates/dashboard.html | head -10
```

- [ ] **Step 4: Replace the response handling inside `reanalyze()` in `dashboard.html`**

Find the `const data = await resp.json();` block and the lines that handle `data.ok` / `data.new_job_id`. Replace with:

```js
  const data = await resp.json();
  if (data.analysis_id) {
    const active = { id: data.analysis_id, source_label: 'Re-analysis' };
    localStorage.setItem('activeAnalysis', JSON.stringify(active));
    window.dispatchEvent(new CustomEvent('analysisStarted', { detail: active }));
    if (statusEl) statusEl.style.display = 'none';
  } else if (data.error) {
    if (statusEl) { statusEl.textContent = data.error; statusEl.style.display = 'block'; }
  }
```

- [ ] **Step 5: Apply same `reanalyze()` change to `history.html`**

```bash
grep -n "reanalyze\|new_job_id" templates/history.html | head -10
```

Find and replace the response-handling block for the reanalyze fetch in `history.html` with the same code as Step 4.

- [ ] **Step 6: Full end-to-end manual test**

1. Paste a job listing on dashboard → Analyze
2. Result box shows "Analysis started — you can navigate away"
3. Banner appears immediately with spinner + source label
4. Navigate to History — banner persists
5. Wait for completion — banner turns green with company + verdict
6. Click banner → navigates to `/job/<id>`, banner clears
7. Refresh any page — banner gone (localStorage cleared)
8. Test error path: disconnect network mid-analysis → banner shows red error + dismiss

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard.html templates/history.html
git commit -m "feat: dashboard and history handle async analysis_id response"
```

---

### Task 8: Docs update

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add entry to `CHANGELOG.md`** (before the existing v0.10.1 entry):

```markdown
## v0.11 — Background analysis with persistent banner

- Analysis runs in a background thread — user can navigate away immediately after submitting
- New `analyses` table tracks job lifecycle: `pending → running → done / error`
- Persistent banner below nav shows progress on every page: spinner + source label + pulsing dots while running; green clickable strip with company and verdict when done; red dismissible strip on error
- Stuck analyses from killed workers auto-cleaned on startup after 5 minutes
- New `GET /analysis_status/<id>` polling endpoint
- `/reanalyze/<id>` also runs asynchronously

---
```

- [ ] **Step 2: Add new endpoint to the endpoints table in `CLAUDE.md`**

In the `## Endpoints (app.py)` section, add:
```
GET      /analysis_status/<id>    — background analysis status poll (pending/running/done/error)
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md CLAUDE.md
git commit -m "docs: document v0.11 background analysis and banner"
```
