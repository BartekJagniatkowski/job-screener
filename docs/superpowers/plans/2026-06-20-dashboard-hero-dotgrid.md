# Dashboard Hero Dot-Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hero section above the dashboard's command bar with a headline, subhead, and an interactive dot-grid canvas background that grows/brightens dots near the mouse cursor.

**Architecture:** Pure vanilla JS/CSS, no new dependencies. A `<canvas>` absolutely positioned behind the hero's text content draws an even grid of dots; a `mousemove` listener scoped to the hero element drives per-frame redraws only while the cursor is inside the hero (idle otherwise).

**Tech Stack:** Flask/Jinja2 template (`dashboard.html`), `static/style.css`, inline `<script>` (this codebase has zero standalone `.js` files — every page's JS lives inline in its template; this plan follows that convention instead of the spec's literal `static/hero-dots.js` path).

## Global Constraints

- Zero inline styles in templates — all CSS in `static/style.css` (CLAUDE.md rule)
- No new JS/CSS dependencies, no build step (project uses none)
- Dashboard page only — no other page gets this treatment
- Dot grid: even spacing (~28px), base radius 1.5px, no density variation — "dot-grid notebook paper" look, not a halftone
- Static (no animation) until mouse enters the hero; no idle/ambient motion ever
- Mouse proximity effect: grow (to ~4px) + brighten toward `var(--accent)`, linear falloff over a 140px radius
- Must respect `prefers-reduced-motion: reduce` — static grid only, no listeners/rAF loop
- Headline: "Screen before you apply." / Subhead: "Paste a listing. Six layers of analysis tell you if it's worth your time."
- Theme-aware colors via existing CSS custom properties (`--border-light`, `--accent`) — no new hardcoded hex values
- Branch: `feature/dashboard-hero-dotgrid` (already checked out)

---

### Task 1: Hero markup and layout CSS (no canvas animation yet)

**Files:**
- Modify: `templates/dashboard.html:46-49` (insert hero wrapper before the existing `.cmd-zone`, close it after `.cmd-zone`'s closing tag at line 93)
- Modify: `static/style.css` (add `.dashboard-hero`, `.hero-title`, `.hero-sub`, `.hero-dots` rules)

**Interfaces:**
- Produces: `.dashboard-hero` (wrapper, `position: relative`), `.hero-dots` (canvas, `aria-hidden="true"`, absolutely positioned, `z-index: 0`) — Task 2's JS targets `document.querySelector('.hero-dots')` and `document.querySelector('.dashboard-hero')` by these exact class names.

- [ ] **Step 1: Insert the hero wrapper in `dashboard.html`**

Current content at lines 46-49 (end of the no-CV notice block, start of `.cmd-zone`):

```html
{% endif %}

<div class="cmd-zone">
```

Replace with:

```html
{% endif %}

<div class="dashboard-hero">
    <canvas class="hero-dots" aria-hidden="true"></canvas>
    <h1 class="hero-title">Screen before you apply.</h1>
    <p class="hero-sub">Paste a listing. Six layers of analysis tell you if it's worth your time.</p>
    <div class="cmd-zone">
```

Then find the existing closing `</div>` for `.cmd-zone` (currently at line 93, right after the `.cmd-text-zone` block closes) and add one more `</div>` immediately after it to close `.dashboard-hero`:

```html
    </div>
</div>
</div>

<div id="source-status" class="source-status"></div>
```

(The middle `</div>` closes `.cmd-zone`, the new outer one closes `.dashboard-hero`.)

- [ ] **Step 2: Add layout CSS**

Add to `static/style.css` (new section, e.g. after the `.cmd-zone`/`.cmd-bar` rules):

```css
/* ── dashboard hero ──────────────────────────────────────────────────────── */
.dashboard-hero {
    position: relative;
    overflow: hidden;
    padding: 72px 24px 56px;
    margin-bottom: 40px;
    border-radius: var(--radius-lg);
    text-align: center;
}
.hero-dots {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    z-index: 0;
}
.hero-title {
    position: relative;
    z-index: 1;
    font-family: var(--fd);
    font-size: 40px;
    font-weight: var(--fw-normal);
    letter-spacing: -0.02em;
    margin-bottom: 12px;
}
.hero-sub {
    position: relative;
    z-index: 1;
    color: var(--muted);
    font-size: var(--fs-lg);
    max-width: 480px;
    margin: 0 auto 40px;
}
.dashboard-hero .cmd-zone {
    position: relative;
    z-index: 1;
    max-width: 640px;
    margin: 0 auto;
}
```

- [ ] **Step 3: Restart the dev server and verify layout manually**

```bash
pkill -f "app.py" 2>/dev/null; sleep 1
cd "/Users/bartekjagniatkowski/Library/Mobile Documents/com~apple~CloudDocs/Work/Development/job-screener"
nohup uv run --env-file config.env python app.py > /tmp/screener-dev.log 2>&1 &
sleep 2
tail -5 /tmp/screener-dev.log
```

Expected: no Jinja/template errors in the log, server listening on `:5001`.

Then load `/dashboard` in a browser (or via the Playwright pattern used earlier this session) and confirm:
- Headline "Screen before you apply." and subhead render above the command bar
- Command bar is visually centered, narrower than full width, with clear space above and below
- No console errors (empty canvas is expected — no drawing code yet)

- [ ] **Step 4: Commit**

```bash
cd "/Users/bartekjagniatkowski/Library/Mobile Documents/com~apple~CloudDocs/Work/Development/job-screener"
git add templates/dashboard.html static/style.css
git commit -m "feat: add dashboard hero section with headline and centered command bar"
```

---

### Task 2: Static dot-grid rendering

**Files:**
- Modify: `templates/dashboard.html` (add a new `<script>` block immediately after the `.dashboard-hero` closing `</div>` from Task 1, before `<div id="source-status">`)

**Interfaces:**
- Consumes: `.hero-dots` canvas and `.dashboard-hero` element from Task 1 (exact class names)
- Produces: module-scope functions `resize()`, `draw()`, `readColors()` (not exported — IIFE-local; Task 3 extends this same IIFE, so the function names below must match exactly)

- [ ] **Step 1: Add the dot-grid script**

Insert immediately after `.dashboard-hero`'s closing `</div>` (right before `<div id="source-status" class="source-status"></div>`):

```html
<script>
(function() {
  var canvas = document.querySelector('.hero-dots');
  if (!canvas) return;
  var hero = document.querySelector('.dashboard-hero');
  var ctx = canvas.getContext('2d');

  var SPACING = 28;
  var BASE_RADIUS = 1.5;

  var dots = [];
  var baseColor = '';

  function readColors() {
    var cs = getComputedStyle(document.documentElement);
    baseColor = cs.getPropertyValue('--border-light').trim();
  }

  function buildGrid(width, height) {
    dots = [];
    for (var y = SPACING / 2; y < height; y += SPACING) {
      for (var x = SPACING / 2; x < width; x += SPACING) {
        dots.push({ x: x, y: y });
      }
    }
  }

  function resize() {
    var rect = hero.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
    buildGrid(rect.width, rect.height);
    draw();
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (var i = 0; i < dots.length; i++) {
      var dot = dots[i];
      ctx.beginPath();
      ctx.arc(dot.x, dot.y, BASE_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = baseColor;
      ctx.fill();
    }
  }

  readColors();
  resize();
  window.addEventListener('resize', resize);

  var themeObserver = new MutationObserver(function() {
    readColors();
    draw();
  });
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
})();
</script>
```

- [ ] **Step 2: Restart server and verify the static grid renders**

```bash
pkill -f "app.py" 2>/dev/null; sleep 1
cd "/Users/bartekjagniatkowski/Library/Mobile Documents/com~apple~CloudDocs/Work/Development/job-screener"
nohup uv run --env-file config.env python app.py > /tmp/screener-dev.log 2>&1 &
sleep 2
```

Load `/dashboard`, confirm:
- An even grid of small dots is visible behind the headline/command bar
- Toggle theme (click the toggle or press `d`) — dot color updates to match the new theme's `--border-light` without a page reload
- Resize the browser window — grid re-tiles to fill the hero, no stretched/cut-off dots at the edges
- Browser console: zero errors

- [ ] **Step 3: Commit**

```bash
cd "/Users/bartekjagniatkowski/Library/Mobile Documents/com~apple~CloudDocs/Work/Development/job-screener"
git add templates/dashboard.html
git commit -m "feat: render static theme-aware dot grid behind dashboard hero"
```

---

### Task 3: Mouse-reactive growth and color blend

**Files:**
- Modify: `templates/dashboard.html` (extend the IIFE added in Task 2 — same `<script>` block)

**Interfaces:**
- Consumes: `dots`, `baseColor`, `draw()`, `ctx`, `canvas`, `hero` from Task 2 (same IIFE scope, no signature changes to existing functions other than `draw()`'s internals)
- Produces: `startLoop()`, `stopLoop()`, module-scope `mouseX`/`mouseY`, `accentColor`, `reduceMotion` — Task 4 reads `reduceMotion` to decide whether to attach listeners at all

- [ ] **Step 1: Replace the script block with the mouse-reactive version**

Replace the entire `<script>` block from Task 2 with:

```html
<script>
(function() {
  var canvas = document.querySelector('.hero-dots');
  if (!canvas) return;
  var hero = document.querySelector('.dashboard-hero');
  var ctx = canvas.getContext('2d');

  var SPACING = 28;
  var BASE_RADIUS = 1.5;
  var MAX_RADIUS = 4;
  var PROXIMITY = 140;

  var dots = [];
  var mouseX = -9999;
  var mouseY = -9999;
  var rafId = null;
  var baseColor = '';
  var accentColor = '';

  function readColors() {
    var cs = getComputedStyle(document.documentElement);
    baseColor = cs.getPropertyValue('--border-light').trim();
    accentColor = cs.getPropertyValue('--accent').trim();
  }

  function hexToRgb(hex) {
    hex = hex.replace('#', '');
    if (hex.length === 3) {
      hex = hex.split('').map(function(c) { return c + c; }).join('');
    }
    var num = parseInt(hex, 16);
    return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 };
  }

  function lerpColor(c1, c2, t) {
    var rgb1 = hexToRgb(c1);
    var rgb2 = hexToRgb(c2);
    var r = Math.round(rgb1.r + (rgb2.r - rgb1.r) * t);
    var g = Math.round(rgb1.g + (rgb2.g - rgb1.g) * t);
    var b = Math.round(rgb1.b + (rgb2.b - rgb1.b) * t);
    return 'rgb(' + r + ',' + g + ',' + b + ')';
  }

  function buildGrid(width, height) {
    dots = [];
    for (var y = SPACING / 2; y < height; y += SPACING) {
      for (var x = SPACING / 2; x < width; x += SPACING) {
        dots.push({ x: x, y: y });
      }
    }
  }

  function resize() {
    var rect = hero.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
    buildGrid(rect.width, rect.height);
    draw();
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (var i = 0; i < dots.length; i++) {
      var dot = dots[i];
      var radius = BASE_RADIUS;
      var color = baseColor;
      var dx = dot.x - mouseX;
      var dy = dot.y - mouseY;
      var dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < PROXIMITY) {
        var t = 1 - dist / PROXIMITY;
        radius = BASE_RADIUS + (MAX_RADIUS - BASE_RADIUS) * t;
        color = lerpColor(baseColor, accentColor, t);
      }
      ctx.beginPath();
      ctx.arc(dot.x, dot.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    }
  }

  function loop() {
    draw();
    rafId = requestAnimationFrame(loop);
  }

  function startLoop() {
    if (rafId === null) loop();
  }

  function stopLoop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    mouseX = -9999;
    mouseY = -9999;
    draw();
  }

  readColors();
  resize();
  window.addEventListener('resize', resize);

  hero.addEventListener('mouseenter', startLoop);
  hero.addEventListener('mouseleave', stopLoop);
  hero.addEventListener('mousemove', function(e) {
    var rect = canvas.getBoundingClientRect();
    mouseX = e.clientX - rect.left;
    mouseY = e.clientY - rect.top;
  });

  var themeObserver = new MutationObserver(function() {
    readColors();
    draw();
  });
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
})();
</script>
```

- [ ] **Step 2: Restart server and verify interactively**

```bash
pkill -f "app.py" 2>/dev/null; sleep 1
cd "/Users/bartekjagniatkowski/Library/Mobile Documents/com~apple~CloudDocs/Work/Development/job-screener"
nohup uv run --env-file config.env python app.py > /tmp/screener-dev.log 2>&1 &
sleep 2
```

Load `/dashboard`, move the mouse over the hero, confirm:
- Dots near the cursor grow and shift color toward the accent blue, fading back to normal with distance
- Moving the mouse away from the hero reverts all dots to the static base grid (no dots stuck enlarged)
- Moving the mouse outside the browser window entirely (or to another part of the page) also reverts the grid — `mouseleave` fires correctly
- CPU usage (Activity Monitor / dev tools Performance tab) drops to ~0% for this tab when the mouse is away from the hero, confirming the rAF loop actually stops

- [ ] **Step 3: Commit**

```bash
cd "/Users/bartekjagniatkowski/Library/Mobile Documents/com~apple~CloudDocs/Work/Development/job-screener"
git add templates/dashboard.html
git commit -m "feat: grow and brighten dots near cursor in dashboard hero"
```

---

### Task 4: Reduced motion + accessibility + final pass

**Files:**
- Modify: `templates/dashboard.html` (same script block — gate the interactive listeners behind a `prefers-reduced-motion` check)

**Interfaces:**
- Consumes: `startLoop`, `stopLoop`, `hero` from Task 3 (same names, no changes)
- Produces: nothing new consumed elsewhere — this is the final task in the plan

- [ ] **Step 1: Add the reduced-motion guard**

In the same script block, add `var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;` near the top (after the `var accentColor = '';` line), and wrap the three `hero.addEventListener(...)` calls in an `if (!reduceMotion) { ... }` block:

```javascript
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
```

Replace:

```javascript
  hero.addEventListener('mouseenter', startLoop);
  hero.addEventListener('mouseleave', stopLoop);
  hero.addEventListener('mousemove', function(e) {
    var rect = canvas.getBoundingClientRect();
    mouseX = e.clientX - rect.left;
    mouseY = e.clientY - rect.top;
  });
```

with:

```javascript
  if (!reduceMotion) {
    hero.addEventListener('mouseenter', startLoop);
    hero.addEventListener('mouseleave', stopLoop);
    hero.addEventListener('mousemove', function(e) {
      var rect = canvas.getBoundingClientRect();
      mouseX = e.clientX - rect.left;
      mouseY = e.clientY - rect.top;
    });
  }
```

The canvas already has `aria-hidden="true"` from Task 1 — no further markup change needed there.

- [ ] **Step 2: Verify reduced motion is respected**

Using Chrome DevTools: open the Rendering tab (Cmd+Shift+P → "Show Rendering"), set "Emulate CSS media feature `prefers-reduced-motion`" to `reduce`, reload `/dashboard`.

Confirm:
- The static dot grid still renders
- Moving the mouse over the hero does **not** grow or brighten any dots
- No `mouseenter`/`mouseleave`/`mousemove` listeners fire (check via a temporary `console.log` if needed, then remove it — don't commit debug logging)

- [ ] **Step 3: Full manual regression pass**

With `prefers-reduced-motion` reset back to "No preference":
- Confirm the existing command bar still works: type a URL, press the existing keyboard shortcuts (Cmd+Enter, Cmd+K), click Analyze — all unchanged from before this feature
- Confirm the history table, filter bar, and search below the hero are unaffected and have clear separation from the hero above them
- Check both light and dark themes
- Check at a narrow viewport (~480px) — hero text wraps reasonably, command bar doesn't overflow

- [ ] **Step 4: Commit**

```bash
cd "/Users/bartekjagniatkowski/Library/Mobile Documents/com~apple~CloudDocs/Work/Development/job-screener"
git add templates/dashboard.html
git commit -m "feat: respect prefers-reduced-motion for dashboard hero dot grid"
```
