# Reality Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Reality check" section to each job analysis that translates corpo-speak into plain English — a short summary of what the role actually is plus up to six phrase callouts decoded inline.

**Architecture:** New field `reality_check` added to the model's JSON response via prompt additions in `analyzer.py`. No new DB column needed — `raw_json` already stores the full response and `app.py` already parses it into a `raw` dict passed to both detail templates. CSS classes and HTML blocks added to both `job_partial.html` and `job_detail.html`. Section renders before the layer accordions; absent for old records where `raw.get('reality_check')` returns `None`.

**Tech Stack:** Python, Jinja2, vanilla CSS. No new dependencies.

---

## File Map

| File | Action |
|---|---|
| `analyzer.py` | Add REALITY CHECK instruction block before FORMAT; add `reality_check` field to JSON schema |
| `static/style.css` | Add `.reality-check-*` CSS classes |
| `templates/job_partial.html` | Add reality check block between card-header close and layer macro |
| `templates/job_detail.html` | Same addition |
| `tests/test_reality_check.py` | New test file: prompt structure + template rendering |
| `CHANGELOG.md` | Add v0.14 entry |

---

### Task 1: `analyzer.py` — add reality_check to prompt and JSON schema

**Files:**
- Modify: `analyzer.py` (lines 91–144)
- Test: `tests/test_reality_check.py` (create)

Context: `SYSTEM_TEMPLATE` is a plain Python string used with `.format(cv=..., zero_list=..., yellow_list=..., criteria=...)`. All literal braces in the JSON schema are doubled (`{{`, `}}`) to escape the `.format()` call. The REALITY CHECK instruction block goes between the EVIDENCE RULE section and the FORMAT block. The `reality_check` JSON field goes after `gut_feeling`, before the closing `}}"""`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reality_check.py`:

```python
from analyzer import SYSTEM_TEMPLATE


def test_system_template_has_reality_check_section():
    assert 'REALITY CHECK' in SYSTEM_TEMPLATE


def test_system_template_has_reality_check_json_field():
    assert '"reality_check"' in SYSTEM_TEMPLATE


def test_system_template_has_callouts_field():
    assert '"callouts"' in SYSTEM_TEMPLATE


def test_system_template_has_phrase_and_plain_fields():
    assert '"phrase"' in SYSTEM_TEMPLATE
    assert '"plain"' in SYSTEM_TEMPLATE
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/bartekjagniatkowski/Library/Mobile Documents/com~apple~CloudDocs/Work/Development/job-screener"
uv run pytest tests/test_reality_check.py -v
```

Expected: all 4 tests FAIL (strings not yet in template).

- [ ] **Step 3: Add REALITY CHECK instruction block to `analyzer.py`**

Find this exact text (around line 91):

```
══════════════════════════════════════════════════
FORMAT — ONLY this JSON, nothing else
══════════════════════════════════════════════════
```

Insert immediately before it:

```
══════════════════════════════════════════════════
REALITY CHECK
══════════════════════════════════════════════════
Translate the listing's language into plain statements.

summary: 2-3 sentences synthesising what the language and framing signal
         about what this role actually is day-to-day.

callouts: up to 6 specific phrases from the listing decoded into plain English.
  - "phrase": exact quote or close paraphrase from the listing
  - "plain": what it actually means — direct, slightly wry, accurate
  - Only include phrases that genuinely obscure meaning
  - If the listing uses clear language, return an empty list []
  - Do not invent signals that are not in the text

```

- [ ] **Step 4: Add `reality_check` to the JSON schema**

Find this exact text at the end of `SYSTEM_TEMPLATE` (around line 143):

```python
  "gut_feeling": "Synthetic observation — what triggers intuition that the analysis doesn't capture directly"
}}"""
```

Replace with:

```python
  "gut_feeling": "Synthetic observation — what triggers intuition that the analysis doesn't capture directly",
  "reality_check": {{
    "summary": "2-3 sentences on what the language signals about the actual role",
    "callouts": [
      {{"phrase": "exact quote or close paraphrase", "plain": "what it actually means"}}
    ]
  }}
}}"""
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_reality_check.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add analyzer.py tests/test_reality_check.py
git commit -m "feat: add reality_check field to analysis prompt and JSON schema"
```

---

### Task 2: `static/style.css` — add reality-check CSS classes

**Files:**
- Modify: `static/style.css` (append after the collapsible section)

Context: `var(--green)` is `#2e8b57` and `var(--green-bg)` is `#0d1a12` — both already defined in the `:root` block. The reality check block sits inside the main `.card` div in both detail templates, so no outer border is added — only a left accent border and a subtle green background tint.

- [ ] **Step 1: Add CSS classes at the end of `static/style.css`**

Find the last line of the collapsible section:

```css
.collapsible-body { padding: 14px 16px; }
```

Add immediately after it:

```css

/* ── reality check ──────────────────────────────────────────────────────── */
.reality-check-card {
  border-left: 3px solid var(--green);
  background: var(--green-bg);
  padding: 12px 12px 8px;
  margin-bottom: 8px;
}
.reality-check-label {
  font-family: var(--fm);
  font-size: var(--fs-2xs);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--green);
  margin-bottom: 8px;
}
.reality-check-summary {
  font-size: var(--fs-sm);
  color: var(--muted);
  line-height: 1.65;
}
.reality-check-divider { border-top: 1px solid var(--border); margin: 10px 0; }
.reality-check-callout {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin-bottom: 5px;
  font-size: var(--fs-sm);
}
.reality-check-phrase { font-style: italic; color: var(--dim); flex-shrink: 0; }
.reality-check-arrow  { color: var(--green); flex-shrink: 0; }
.reality-check-plain  { color: var(--muted); }
```

- [ ] **Step 2: Commit**

```bash
git add static/style.css
git commit -m "style: add reality-check CSS classes"
```

---

### Task 3: Templates — add reality check block

**Files:**
- Modify: `templates/job_partial.html` (line 65–67)
- Modify: `templates/job_detail.html` (line 72–74)
- Test: `tests/test_reality_check.py` (add tests)

Context: both templates receive a `raw` dict (parsed from `raw_json`) via their respective routes in `app.py`. The block goes inside the existing `.card` div, between the closing `</div>` of `.card-header--vertical` and the `{% macro layer(...) %}` definition.

The `app.py` routes that render these templates are:
- `/job/<id>` → `render_template("job_detail.html", job=job, raw=raw)`
- `/job/<id>/partial` → `render_template("job_partial.html", job=job, raw=raw)`

- [ ] **Step 1: Add template rendering tests to `tests/test_reality_check.py`**

Append to `tests/test_reality_check.py`:

```python
import json
from database import get_conn


def _insert_job(raw_dict):
    """Insert a minimal job row and return its id."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (user_id, company, role, verdict, verdict_confirmed, raw_json) "
            "VALUES (1, 'Acme', 'Test Role', 'worth_considering', 1, ?)",
            (json.dumps(raw_dict),),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_partial_renders_reality_check_when_present(logged_in_client, app):
    rc = {
        "summary": "A role for someone who enjoys writing documents no one will read.",
        "callouts": [
            {"phrase": "scalable and repeatable", "plain": "writing processes nobody currently follows"},
            {"phrase": "principal-level IC", "plain": "senior title, no budget, no team"},
        ],
    }
    job_id = _insert_job({"reality_check": rc, "triage": {}, "layers": {}, "fit": {}})
    resp = logged_in_client.get(f"/job/{job_id}/partial")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Reality check" in html
    assert "reality-check-card" in html
    assert "scalable and repeatable" in html
    assert "writing processes nobody currently follows" in html
    assert "principal-level IC" in html


def test_partial_omits_reality_check_when_absent(logged_in_client, app):
    job_id = _insert_job({"triage": {}, "layers": {}, "fit": {}})
    resp = logged_in_client.get(f"/job/{job_id}/partial")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Reality check" not in html
    assert "reality-check-card" not in html


def test_partial_renders_summary_only_when_callouts_empty(logged_in_client, app):
    rc = {
        "summary": "Clear job description, no decoding needed.",
        "callouts": [],
    }
    job_id = _insert_job({"reality_check": rc, "triage": {}, "layers": {}, "fit": {}})
    resp = logged_in_client.get(f"/job/{job_id}/partial")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Reality check" in html
    assert "Clear job description, no decoding needed." in html
    assert "reality-check-divider" not in html
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_reality_check.py::test_partial_renders_reality_check_when_present tests/test_reality_check.py::test_partial_omits_reality_check_when_absent tests/test_reality_check.py::test_partial_renders_summary_only_when_callouts_empty -v
```

Expected: FAIL — `"Reality check" not in html` (block not in template yet).

- [ ] **Step 3: Add reality check block to `templates/job_partial.html`**

Find this exact text (lines 65–67):

```html
  </div>

  {% macro layer(id, name, status, findings, evidence=None) %}
```

Replace with:

```html
  </div>

  {% set rc = raw.get('reality_check') %}
  {% if rc %}
  <div class="reality-check-card">
    <div class="reality-check-label">Reality check</div>
    <div class="reality-check-summary">{{ rc.summary }}</div>
    {% if rc.callouts %}
    <div class="reality-check-divider"></div>
    {% for item in rc.callouts %}
    <div class="reality-check-callout">
      <span class="reality-check-phrase">"{{ item.phrase }}"</span>
      <span class="reality-check-arrow">→</span>
      <span class="reality-check-plain">{{ item.plain }}</span>
    </div>
    {% endfor %}
    {% endif %}
  </div>
  {% endif %}

  {% macro layer(id, name, status, findings, evidence=None) %}
```

- [ ] **Step 4: Add reality check block to `templates/job_detail.html`**

Find this exact text (lines 72–74):

```html
  </div>

  {% macro layer(id, name, status, findings, evidence=None) %}
```

Replace with:

```html
  </div>

  {% set rc = raw.get('reality_check') %}
  {% if rc %}
  <div class="reality-check-card">
    <div class="reality-check-label">Reality check</div>
    <div class="reality-check-summary">{{ rc.summary }}</div>
    {% if rc.callouts %}
    <div class="reality-check-divider"></div>
    {% for item in rc.callouts %}
    <div class="reality-check-callout">
      <span class="reality-check-phrase">"{{ item.phrase }}"</span>
      <span class="reality-check-arrow">→</span>
      <span class="reality-check-plain">{{ item.plain }}</span>
    </div>
    {% endfor %}
    {% endif %}
  </div>
  {% endif %}

  {% macro layer(id, name, status, findings, evidence=None) %}
```

- [ ] **Step 5: Run the new template tests**

```bash
uv run pytest tests/test_reality_check.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add templates/job_partial.html templates/job_detail.html tests/test_reality_check.py
git commit -m "feat: render reality check section in job detail and partial views"
```

---

### Task 4: CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add v0.14 entry**

Find:

```markdown
## v0.13 — Analytics redesign
```

Insert immediately before it:

```markdown
## v0.14 — Reality check

- New "Reality check" section in job detail view, before the layer analysis
- Plain-English summary of what the role actually is, synthesised from the listing language
- Up to 6 corpo-speak phrase callouts decoded inline: `"phrase" → what it actually means`
- Purely informational — no verdict impact
- Absent for analyses run before this version

---

```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add v0.14 reality check to CHANGELOG"
```
