# History Table Redesign

**Date:** 2026-05-06
**Status:** Approved

## Problem

The history table has 12 columns, causing layout pressure and wrapping. Classification badges can wrap to two lines. The six analysis-layer columns are individually labelled but occupy excessive header space. The fit score (`fit_score REAL`) exists in the DB but is not shown. The filter bar and table header scroll away on long lists. No way to reset all filters at once.

## Goal

Rebuild the history table to 7 focused columns, make both the filter bar and table header sticky on scroll, add a "Show all" filter reset, surface the fit score, and remove the container width ceiling so the table scales on wide screens and horizontal-scrolls on narrow ones.

---

## Layout & Container

The history page overrides the shared container to go full-width:

```css
.container-full { max-width: none; padding: 40px 24px 80px; }
```

`history.html` uses `<div class="container-full">` instead of `<div class="container">`. This is the only page that opts out of the 1280px ceiling — other pages are unaffected.

The `<table>` is wrapped in `<div class="table-wrap">` which has `overflow-x: auto` for horizontal scroll on narrow viewports.

The table uses `table-layout: fixed; width: 100%` with explicit `<col>` widths:

| Column | Width |
|---|---|
| Date | 90px |
| Role | — (flex) |
| Company | — (flex) |
| Badge | 200px |
| L0 | 44px |
| Layers | 100px |
| Fit | 75px |

Role and Company share all remaining space equally via `width: auto` (browser splits flex equally under `table-layout: fixed` when both are `auto`).

---

## Sticky Filter Bar + Table Header

### Filter bar

```css
.filter-bar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: var(--bg);
  padding-top: 12px;
  padding-bottom: 12px;
}
```

Sticks to the top of the viewport as soon as the nav scrolls away. The analysis banner (`z-index: 50`) sits above it when active — no conflict.

### Table header

```css
thead th {
  position: sticky;
  top: var(--filter-bar-h, 48px);
  z-index: 10;
  background: var(--surface);
}
```

A JS snippet in `history.html` measures the filter bar height on load and sets the CSS variable:

```js
(function () {
  var fb = document.querySelector('.filter-bar');
  if (fb) document.documentElement.style.setProperty('--filter-bar-h', fb.offsetHeight + 'px');
})();
```

Fallback `48px` covers the case where JS hasn't run yet.

---

## Filter Bar — "Show all" Button

A "Show all" button is prepended to the filter bar before the six category buttons:

```html
<button class="filter-btn fb-all" onclick="showAll()">Show all</button>
```

`showAll()` in JS:
```js
function showAll() {
  hiddenCategories.clear();
  localStorage.setItem(FILTER_STORAGE_KEY, '[]');
  document.querySelectorAll('.filter-btn[data-cat]').forEach(b => b.classList.add('active'));
  applyFilter();
}
```

Each category button gets a `data-cat="<category>"` attribute so `showAll()` can target them without fragile class selectors.

The "Show all" button has no persistent active/inactive state — it is a reset action. Styled as `.filter-btn` with neutral border (no category colour variant). No new CSS class needed beyond `.fb-all` for specificity if needed.

---

## Column Designs

### Badge (Verdict column)

Column width 200px is sufficient to display "Rejected by company" (the longest label) at `var(--fs-2xs)` monospace without wrapping. No CSS changes to the badge itself — the column width does the work. `white-space: nowrap` added to `td` containing the badge to guarantee single-line.

### Layers column

Five dots rendered with native `title` tooltip:

```html
<td class="td-layers">
  <span class="dot dot-{{ j.triage_status or 'unknown' }}"     title="Triage: {{ j.triage_status or 'unknown' }}"></span>
  <span class="dot dot-{{ j.product_status or 'unknown' }}"    title="Product: {{ j.product_status or 'unknown' }}"></span>
  <span class="dot dot-{{ j.business_status or 'unknown' }}"   title="Business: {{ j.business_status or 'unknown' }}"></span>
  <span class="dot dot-{{ j.reputation_status or 'unknown' }}" title="Reputation: {{ j.reputation_status or 'unknown' }}"></span>
  <span class="dot dot-{{ j.values_status or 'unknown' }}"     title="Values: {{ j.values_status or 'unknown' }}"></span>
</td>
```

Column header: "Layers". Cell uses `display: flex; gap: 4px; align-items: center` via new class `.td-layers`.

Fit is no longer in this strip — it has its own column.

### Fit score column

```html
<td class="td-mono {% if j.fit_score is not none %}{% if j.fit_status == 'ok' %}td-green{% elif j.fit_status == 'warning' %}td-warning{% elif j.fit_status == 'flag' %}td-red{% else %}td-dim{% endif %}{% else %}td-dim{% endif %}">
  {% if j.fit_score is not none %}{{ "%.1f"|format(j.fit_score) }}/5{% else %}—{% endif %}
</td>
```

Uses existing `td-green`, `td-red`, `td-dim` classes. Warning state uses inline colour `#f0c040` via a new `.td-warning` class added to `style.css` (consistent with the yellow used elsewhere in the codebase for warning states).

### L0 column

Unchanged logic (`YES` / `—`), column width reduced to 44px.

### Status column

**Removed.** The badge already encodes Applied / Rejected by company.

---

## Files Changed

| File | Change |
|---|---|
| `templates/history.html` | Column structure, container class, filter bar enhancements, sticky JS, dot strip, fit score cell |
| `static/style.css` | `.container-full`, `.table-wrap`, sticky `.filter-bar` update, sticky `thead th`, `.td-layers` |

No backend changes. No new endpoints. No DB changes.

---

## Out of Scope

- Sorting by column
- Pagination
- Search/text filter
- Mobile card layout (horizontal scroll handles narrow viewports)
