# Analytics Redesign

**Date:** 2026-05-06
**Status:** Approved

## Problem

The analytics page presents all information at equal visual weight with no narrative. Flat stat cards give numbers without interpretation. Verdict distribution uses four individual bars that convey proportion poorly. Layer flags show ok/warning/flag stacked bars — the ok and warning segments add noise; only flag counts matter at a glance. Fit score occupies a dedicated stat card disproportionate to its analytical value. Fit distribution and role archetypes are always expanded despite being secondary data.

## Goal

Rebuild analytics for readability: a plain-English summary at the top, a visual application funnel replacing the stat cards, verdict distribution as a single stacked bar, layer flags simplified to flag-count-only sorted by severity, and secondary sections collapsed by default.

---

## Architecture

Pure front-end change — no new endpoints, no schema changes.

| File | Action |
|---|---|
| `database.py` | Add `qualifying` and `most_flagged_layer` to `get_analytics()` return dict |
| `static/style.css` | Add new classes; existing bar classes kept |
| `templates/analytics.html` | Full rebuild of `{% block content %}` |

---

## Data Layer — `get_analytics()` additions

Two new keys added to the return dict. No existing keys removed.

### `funnel.qualifying`

Count of jobs with verdict `worth_considering` or `warning` (listings that passed the filter). Added alongside existing `funnel.total`, `funnel.applied`, `funnel.company_rejected`.

```python
funnel['qualifying'] = verdict_distribution['worth_considering'] + verdict_distribution['warning']
```

### `most_flagged_layer`

Tuple `(label: str, count: int)` for the layer with the highest flag count, or `None` if all layers have zero flags.

```python
layer_labels = {
    'triage': 'Triage', 'product': 'Product', 'business': 'Business',
    'reputation': 'Reputation', 'values': 'Values', 'fit': 'Skills fit'
}
most_flagged_layer = None
max_flags = 0
for layer in layers:
    fc = layer_flags[layer]['flag']
    if fc > max_flags:
        max_flags = fc
        most_flagged_layer = (layer_labels[layer], fc)
```

Return dict addition:
```python
'most_flagged_layer': most_flagged_layer,
```

---

## Page Layout

```
┌─────────────────────────────────────────────────────┐
│ Summary (TL;DR)                                      │  ← gold left-border card
├─────────────────────────────────────────────────────┤
│ Application pipeline                                 │  ← section title
│ [Analyzed] › [Qualifying] › [Applied] › [Co.rej]    │  ← funnel row
│ N auto-rejected by Zero Rule — not included above.  │  ← zero note
├─────────────────────────────────────────────────────┤
│ Breakdown                                            │  ← section title
│ ┌──────────────────┐  ┌──────────────────┐          │
│ │ Verdict dist.    │  │ Layer flags      │          │  ← .grid2 two-col
│ │ stacked bar      │  │ flag bars only   │          │
│ └──────────────────┘  └──────────────────┘          │
├─────────────────────────────────────────────────────┤
│ ▶ Fit score distribution          8 scored          │  ← collapsible
│ ▶ Role archetypes                 4 types           │  ← collapsible
└─────────────────────────────────────────────────────┘
```

---

## Section Designs

### 1. TL;DR Summary Card

Gold left-border card immediately below the page subtitle. Text generated in Jinja2.

**Template logic:**
```html
<div class="analytics-tldr">
  <div class="analytics-tldr-label">Summary</div>
  <div class="analytics-tldr-text">
    You've analyzed <strong>{{ data.funnel.total }}</strong> jobs
    {% if data.funnel.applied > 0 %}
      and applied to <strong>{{ data.funnel.applied }}</strong>
      {% if data.funnel.qualifying > 0 %}
        — a <strong>{{ (data.funnel.applied / data.funnel.qualifying * 100)|round|int }}%</strong> follow-through rate on qualifying listings
      {% endif %}
    {% endif %}.
    {% if data.most_flagged_layer %}
      <strong>{{ data.most_flagged_layer[0] }}</strong> is your most common blocker ({{ data.most_flagged_layer[1] }} flag{{ 's' if data.most_flagged_layer[1] != 1 else '' }}).
    {% endif %}
    {% if data.fit_score_avg is not none %}
      Average fit score across scored analyses is <strong>{{ "%.1f"|format(data.fit_score_avg) }}/5</strong>.
    {% endif %}
  </div>
</div>
```

**CSS:**
```css
.analytics-tldr {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-sm);
  padding: 14px 18px;
  margin-bottom: 28px;
}
.analytics-tldr-label {
  font-family: var(--fm);
  font-size: var(--fs-2xs);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
  margin-bottom: 6px;
}
.analytics-tldr-text {
  font-size: var(--fs-sm);
  color: var(--muted);
  line-height: 1.65;
}
.analytics-tldr-text strong { color: var(--text); }
```

---

### 2. Application Pipeline (Funnel)

Four horizontal blocks connected by `›` arrows. Each block shows a number + label. Below each (except the first): percentage relative to the previous step.

**Percentage rules:**
- Qualifying: `qualifying / total * 100` — show only if `total > 0`
- Applied: `applied / qualifying * 100` — show only if `qualifying > 0`
- Co. rejected: `company_rejected / applied * 100` — show only if `applied > 0`

**Colours:**
- Analyzed: `var(--text)` (white)
- Qualifying: `#4a9eff` (blue — matches `bar-worth`)
- Applied: `#3dba73` (green)
- Co. rejected: `#e07b39` (orange)

**Zero Rule note** (below funnel, always shown if `zero_list_hits > 0`):
```html
<p class="zero-rule-note">
  <strong>{{ data.zero_list_hits }}</strong> auto-rejected by Zero Rule — not included above.
</p>
```

**CSS:**
```css
.analytics-funnel {
  display: flex;
  align-items: stretch;
  gap: 0;
  margin-bottom: 10px;
}
.funnel-step { flex: 1; text-align: center; }
.funnel-block {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px 8px 12px;
  margin: 0 4px;
}
.funnel-num {
  font-family: var(--fd);
  font-size: var(--fs-3xl);
  font-weight: 200;
  line-height: 1;
}
.funnel-lbl {
  font-family: var(--fm);
  font-size: var(--fs-2xs);
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-top: 6px;
}
.funnel-pct {
  font-size: var(--fs-xs);
  margin-top: 6px;
  min-height: 1.4em;
}
.funnel-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  padding-bottom: 28px;
  color: var(--border-light);
  font-size: var(--fs-xl);
  flex-shrink: 0;
  width: 18px;
}
.zero-rule-note {
  font-size: var(--fs-xs);
  color: var(--dim);
  margin-bottom: 28px;
  padding-left: 4px;
}
.zero-rule-note strong { color: var(--muted); }
```

---

### 3. Breakdown Grid

`.grid2` two-column card row (existing class — becomes single column on mobile).

#### 3a. Verdict Distribution Card

Single stacked horizontal bar with legend below. The bar's segments are proportional to each verdict category. Rendered with `width` inline style on each segment (structural invariant — inline style exception).

**Segment colours:**
- Worth considering: `#4a9eff`
- Needs review: `#c9a96e`
- Rejected: `#e74c3c`
- Rejected (AI): `var(--muted)`

**CSS:**
```css
.stacked-bar {
  height: 16px;
  border-radius: 4px;
  overflow: hidden;
  display: flex;
  margin-bottom: 12px;
}
.stacked-bar-seg { height: 100%; }
.stacked-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
}
.stacked-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.stacked-legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  flex-shrink: 0;
}
```

**Empty state:** if `vd_total == 0`, show `<div class="td-dim">No verdict data.</div>` (same as current).

#### 3b. Layer Flags Card

Bars showing **flag count only** for each layer, sorted descending by flag count. Layers with `flag == 0` are omitted. Uses existing `.bar-row`, `.bar-label`, `.bar-track`, `.bar-fill.bar-flag`, `.bar-count` classes.

The `.bar-label` width needs to be narrower inside a grid card. The breakdown cards get class `analytics-breakdown-card` (in addition to the existing `.card` class) so the override is scoped: `.analytics-breakdown-card .bar-label { width: 90px; }`.

**Sort:** Python-side in template via `data.layer_flags` — sort in Jinja2:
```jinja2
{% set sorted_layers = [
  ('triage','Triage'), ('product','Product'), ('business','Business'),
  ('reputation','Reputation'), ('values','Values'), ('fit','Skills fit')
] | sort(attribute=0) %}
```
Actually sort by flag count descending in the template:
```jinja2
{% set layer_order = [
  ('triage','Triage'),('product','Product'),('business','Business'),
  ('reputation','Reputation'),('values','Values'),('fit','Skills fit')
] %}
{% set sorted_layers = layer_order | sort(key=lambda x: -data.layer_flags[x[0]].flag) %}
```

Jinja2 doesn't support lambda in sort. Use a different approach — sort in `get_analytics()` by returning a pre-sorted list:

Add to `get_analytics()` return dict:
```python
layer_flag_counts = sorted(
    [(layer_labels[l], layer_flags[l]['flag']) for l in layers],
    key=lambda x: -x[1]
)
```

New key: `layer_flag_counts` — list of `(label, count)` tuples, sorted descending by count.

**Template:**
```html
{% for label, count in data.layer_flag_counts %}
{% if count > 0 %}
<div class="bar-row">
  <div class="bar-label">{{ label }}</div>
  <div class="bar-track">
    <div class="bar-fill bar-flag" style="width:{{ (count / max_flag * 100)|round }}%"></div>
  </div>
  <div class="bar-count" style="color:#e74c3c">{{ count }}</div>
</div>
{% endif %}
{% endfor %}
```

`max_flag` = first item's count (list is sorted). Compute in template: `{% set max_flag = data.layer_flag_counts[0][1] if data.layer_flag_counts else 1 %}`.

The `style="width:..."` on `.bar-fill` is an existing pattern throughout the page — not a new inline style exception.

**CSS addition (scoped to breakdown cards):**
```css
.analytics-breakdown-card .bar-label { width: 90px; }
```

**Template:** the breakdown grid cards use `class="card analytics-breakdown-card"` so the selector above applies.

---

### 4. Collapsible Sections

Both "Fit score distribution" and "Role archetypes" collapse by default. Click the header row to expand/collapse. State is **not** persisted to localStorage — sections always start collapsed.

**HTML structure:**
```html
<div class="collapsible">
  <div class="collapsible-header" onclick="toggleCollapsible(this)">
    <span class="collapsible-label">Fit score distribution</span>
    <div class="collapsible-right">
      <span class="collapsible-meta">{{ data.fit_score_distribution | sum(attribute=1) }} scored</span>
      <span class="collapsible-arrow">▶</span>
    </div>
  </div>
  <div class="collapsible-body">
    <!-- existing bar chart content -->
  </div>
</div>
```

**JS (inline in `{% block scripts %}`):**
```js
function toggleCollapsible(header) {
  const body = header.nextElementSibling;
  const arrow = header.querySelector('.collapsible-arrow');
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  arrow.textContent = open ? '▶' : '▼';
}
```

Bodies start with `style="display:none"` (JS-managed dynamic state — permitted inline style exception).

**CSS:**
```css
.collapsible {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
  overflow: hidden;
}
.collapsible-header {
  background: var(--surface);
  padding: 11px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
}
.collapsible-header:hover { background: color-mix(in srgb, var(--surface) 90%, white 10%); }
.collapsible-label {
  font-size: var(--fs-sm);
  color: var(--muted);
}
.collapsible-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.collapsible-meta {
  font-size: var(--fs-xs);
  color: var(--dim);
}
.collapsible-arrow {
  font-family: var(--fm);
  font-size: var(--fs-2xs);
  color: var(--dim);
}
.collapsible-body { padding: 14px 16px; }
```

---

## Removed from analytics page

- `.analytics-grid` stat cards (Total analyzed, Applied, Rejected by company, Zero rule hits, Avg. fit score) — replaced by funnel + TL;DR
- Stacked ok/warning/flag layer bars — replaced by flag-count-only bars
- Always-expanded Fit score distribution — now collapsible
- Always-expanded Role archetypes — now collapsible

The CSS classes `.analytics-grid`, `.stat-card`, `.stat-card-label`, `.stat-card-value`, `.stat-card-sub` are only used on `analytics.html`. They can be removed from `style.css` along with the rebuild.

---

## Light Mode

All new components use CSS variables — no extra light-mode overrides needed. The gold accent (`var(--accent)`) and existing token colours work in both themes.

`color-mix()` in `.collapsible-header:hover` is supported in all modern browsers (Chrome 111+, Firefox 113+, Safari 16.2+).

---

## Out of Scope

- Time-based trends (analyses over time)
- Sorting or filtering in analytics
- Exporting analytics data
- Any new DB columns or endpoints
