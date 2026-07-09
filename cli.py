import dataclasses
import json
import os

from textual import on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.command import Command, CommandPalette
from textual.containers import Container, Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.theme import Theme, ThemeProvider
from textual.widgets import (
    DataTable, Footer, HelpPanel, Input, Label, Static, TextArea,
)
from textual.widgets.data_table import CellDoesNotExist

import analyzer
import database
import scraper

# Input's built-in "right" binding description is the longest line shown
# anywhere in the help panel ("...accept the completion suggestion") --
# shortened here so the panel doesn't need to be sized for it. Mutating the
# class's BINDINGS list alone isn't enough: _merged_bindings is computed
# once at class-creation time (DOMNode.__init_subclass__), so it has to be
# explicitly recomputed for the edit to actually take effect.
Input.BINDINGS = [
    dataclasses.replace(b, description="Move cursor right or accept suggestion")
    if isinstance(b, Binding) and b.key == "right" and b.action == "cursor_right"
    else b
    for b in Input.BINDINGS
]
Input._merged_bindings = Input._merge_bindings()

JOB_SCREENER_THEME = Theme(
    name="job-screener",
    primary="#39bae6",
    secondary="#ffb454",
    background="#0a0e14",
    surface="#0a0e14",
    panel="#0a0e14",
    success="#7fd962",
    warning="#ffb454",
    error="#f07178",
    foreground="#d5d8da",
    dark=True,
)

JOB_SCREENER_LIGHT_THEME = Theme(
    name="job-screener-light",
    primary="#0084b4",
    secondary="#a86200",
    background="#fafafa",
    surface="#ffffff",
    panel="#f0f0f0",
    success="#4a8f3c",
    warning="#a86200",
    error="#c0392b",
    foreground="#1a1a1a",
    dark=False,
)

LAYER_COLUMNS = [
    "triage_status", "product_status", "business_status",
    "reputation_status", "values_status", "fit_status",
]

LAYER_PANELS = [
    ("Triage", "triage_status", "triage_findings"),
    ("Product", "product_status", "product_findings"),
    ("Business", "business_status", "business_findings"),
    ("Reputation", "reputation_status", "reputation_findings"),
    ("Values", "values_status", "values_findings"),
]

# DataTable cells render through rich.text.Text.from_markup, which does not
# resolve Textual's "$variable" theme syntax (that only works in widget CSS
# and Static/Label content) — so these use the theme's literal hex values
# instead of "$success"/"$warning"/"$error".
STATUS_DOT_COLOR = {"ok": "#7fd962", "warning": "#ffb454", "flag": "#f07178"}
VERDICT_COLOR = {
    "rejected": "#f07178", "warning": "#ffb454", "worth_considering": "#7fd962",
    "applied": "#7fd962", "offer": "#7fd962",
    "interview": "#d2a6ff", "company_rejected": "#ff8f40",
}
FILTER_CYCLE = [
    "all", "rejected", "warning", "worth_considering",
    "applied", "interview", "offer", "company_rejected",
]
# Human-readable name per status, with "^" marking the quick-select mnemonic
# letter (must match FilterBar.QUICK_SELECT_KEYS) -- single source for both
# the filter bar's Title Case chips and the VERDICT column's UPPER_SNAKE
# text, so the two surfaces can't drift out of sync with each other.
STATUS_DISPLAY_MARKED = {
    "all": "^All",
    "rejected": "User ^Rejected",
    "warning": "Warnin^g",
    "worth_considering": "^Worth Considering",
    "applied": "A^pplied",
    "interview": "^Interview",
    "offer": "^Offer",
    "company_rejected": "Rejected By ^Company",
}
STATUS_DISPLAY = {k: v.replace("^", "") for k, v in STATUS_DISPLAY_MARKED.items()}


def layer_dots(row) -> str:
    parts = []
    for col in LAYER_COLUMNS:
        status = row[col] or ""
        color = STATUS_DOT_COLOR.get(status, "")
        parts.append(f"[{color}]●[/]" if color else "○")
    return " ".join(parts)


def status_key(row) -> str:
    """Return the FILTER_CYCLE status a job row currently belongs to.

    Application-stage flags (offer/interview/company_rejected/applied)
    override the underlying analysis verdict, mirroring the web app's
    badge priority (job_partial.html) -- otherwise a job you've applied to
    or been interviewed for looks identical to a fresh, untouched verdict.
    """
    if row["offer_received"]:
        return "offer"
    if row["interview_scheduled"]:
        return "interview"
    if row["company_rejected"]:
        return "company_rejected"
    if row["applied"]:
        return "applied"
    return (row["verdict"] or "").lower()


def status_label(row) -> tuple[str, str]:
    """Return (VERDICT-column label, color) for a job row."""
    key = status_key(row)
    label = STATUS_DISPLAY.get(key, key).upper().replace(" ", "_")
    return label, VERDICT_COLOR.get(key, "")


def job_matches_filter(row, status: str) -> bool:
    if status == "all":
        return True
    # Must reuse status_key's override priority (offer > interview >
    # company_rejected > applied > verdict) instead of checking flags
    # independently -- otherwise a job with applied=1 but verdict
    # "worth_considering" matched BOTH the "applied" and
    # "worth_considering" filters, while displaying as APPLIED in the
    # table. One key, one filter bucket.
    return status_key(row) == status


CLI_STATE_DIR = "data"  # already gitignored as a whole directory


def cli_state_path(username: str) -> str:
    return os.path.join(CLI_STATE_DIR, f"cli_state_{username}.json")


def load_cli_state(username: str) -> dict:
    try:
        with open(cli_state_path(username), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cli_state(username: str, state: dict) -> None:
    try:
        os.makedirs(CLI_STATE_DIR, exist_ok=True)
        with open(cli_state_path(username), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass  # best-effort -- losing remembered state isn't worth crashing over


class LoginScreen(Screen):
    CSS = """
    LoginScreen {
        align: center middle;
    }
    #login-box {
        width: 50;
        height: auto;
        border: round $primary;
        padding: 1 2;
    }
    #login-error {
        color: $error;
        height: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="login-box"):
            yield Label("job-screener", id="login-title")
            yield Input(placeholder="username", id="username-input")
            yield Label("", id="login-error")

    def on_mount(self) -> None:
        self.query_one("#username-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        username = event.value.strip()
        error_label = self.query_one("#login-error", Label)
        if not username:
            return
        user = database.get_user(username)
        if user is None:
            error_label.update(f"No such user: {username}")
            event.input.value = ""
            return
        self.app.user = user
        self.app.switch_screen(MainScreen())


class FilterBar(Horizontal):
    """Persistent horizontal filter status row between the list and detail
    panel.

    Not focusable -- quick-select letters (MainScreen's
    action_quick_select_* methods, generated below from
    QUICK_SELECT_KEYS) work screen-wide regardless of what's focused, so
    Tab-ing into this bar to cycle filters manually is no longer needed.
    Tab instead toggles only between the job list and the detail panel.
    """

    can_focus = False

    # Quick-select: one letter per status, jumps directly there instead of
    # cycling. Mnemonics aren't all first-letter since several statuses
    # collide on first letter (warning/worth_considering/offer all start
    # differently enough, but "a"pplied vs "a"ll would clash) -- this
    # exact set was specified directly rather than derived.
    QUICK_SELECT_KEYS = {
        "a": "all",
        "r": "rejected",
        "g": "warning",
        "w": "worth_considering",
        "p": "applied",
        "i": "interview",
        "o": "offer",
        "c": "company_rejected",
    }

    def __init__(self, main_screen: "MainScreen"):
        super().__init__(id="filter-bar")
        self.main_screen = main_screen

    def compose(self) -> ComposeResult:
        for status in FILTER_CYCLE:
            before, _marker, rest = STATUS_DISPLAY_MARKED[status].partition("^")
            label = f"{before}[reverse]{rest[0]}[/]{rest[1:]}"
            yield Static(label, classes="filter-chip")

    def on_mount(self) -> None:
        self.refresh_chips()

    def refresh_chips(self) -> None:
        chips = list(self.query(".filter-chip"))
        for i, chip in enumerate(chips):
            chip.set_class(i == self.main_screen.filter_index, "selected")
        # Without this, moving left/right past the edge of a narrow
        # terminal selects a chip that's scrolled out of view -- the
        # highlight changes but you can't see which one is now active,
        # and the bar just sits there overflowed with no visual link
        # between "you pressed right" and "this is what's now selected."
        if 0 <= self.main_screen.filter_index < len(chips):
            chips[self.main_screen.filter_index].scroll_visible(
                animate=False, immediate=True
            )

    def select_filter(self, status: str) -> None:
        self.main_screen.filter_index = FILTER_CYCLE.index(status)
        self.main_screen.refresh_jobs()
        self.main_screen.save_state()
        self.refresh_chips()


class JobsTable(DataTable):
    """DataTable that re-truncates its own columns when ITS width changes.

    events.Resize doesn't bubble (confirmed: events.Resize.bubble is
    False), so MainScreen never sees this table's own resize -- only the
    screen's own size change (an actual terminal resize), not a sibling
    widget (e.g. the help panel) taking some of the available width.
    Overriding on_resize directly on the table itself is the only
    reliable way to catch that.
    """

    def __init__(self, main_screen: "MainScreen", **kwargs):
        super().__init__(**kwargs)
        self.main_screen = main_screen

    def on_resize(self, event) -> None:
        self.main_screen.refresh_jobs()


class LayerNavPanel(VerticalScroll):
    """The detail panel, focusable to navigate between its layer sections."""

    can_focus = True

    BINDINGS = [
        Binding("j", "next_layer", "Next layer", show=False),
        Binding("k", "prev_layer", "Prev layer", show=False),
        Binding("down", "next_layer", "Next layer", show=False),
        Binding("up", "prev_layer", "Prev layer", show=False),
    ]

    def __init__(self, main_screen: "MainScreen"):
        super().__init__(id="detail-body")
        self.main_screen = main_screen

    def action_next_layer(self) -> None:
        self.main_screen.move_layer(1)

    def action_prev_layer(self) -> None:
        self.main_screen.move_layer(-1)


class MainScreen(Screen):
    CSS = """
    .hidden {
        display: none;
    }
    #list-frame {
        height: 1fr;
        border: round $border-blurred;
        padding: 1;
        margin: 1 1 0 1;
    }
    #list-frame.focused-frame {
        border: round $primary;
    }
    #jobs-table {
        height: 100%;
    }
    #detail-frame {
        height: 1fr;
        border: round $border-blurred;
        padding: 1;
        margin: 1;
    }
    #detail-frame.focused-frame {
        border: round $primary;
    }
    #detail-header {
        margin-bottom: 1;
        padding: 0 1;
    }
    #detail-header.current {
        background: $primary 15%;
        border-left: thick $primary;
    }
    .layer-section {
        margin-bottom: 1;
        padding: 0 1;
    }
    .layer-section.current {
        background: $primary 15%;
        border-left: thick $primary;
    }
    #filter-bar {
        height: 3;
        margin: 0 1;
        border: round $border-blurred;
        align: center middle;
        /* Horizontal's default is "overflow: hidden hidden" -- structurally
           not scrollable, just clips. With 8 chips this overflows on
           anything narrower than ~120 cols, and selecting an off-screen
           chip via left/right had no way to bring it into view: scroll_x
           stayed 0 because the container couldn't scroll at all, despite
           calling scroll_visible() on the selected chip every time.
           scrollbar-size-horizontal: 0 keeps scrolling functional
           (scroll_visible() now works) without reserving a visible
           scrollbar row -- a visible bar at height:3 had no room and
           squished the chip text down to nothing. */
        overflow-x: auto;
        overflow-y: hidden;
        scrollbar-size-horizontal: 0;
    }
    .filter-chip {
        width: auto;
        margin: 0 1;
        padding: 0 1;
        color: $foreground 60%;
    }
    .filter-chip.selected {
        color: $primary;
        text-style: bold underline;
    }
    #prompt-input {
        margin: 0 1;
    }
    #status-line {
        margin: 0 1 1 1;
        height: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit_app", "Quit"),
        Binding("escape", "cancel_prompt_or_quit", "Back", show=False),
        Binding("j", "cursor_down", "Move", key_display="j/k"),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("tab", "cycle_focus", "Focus"),
        # Footer groups footer chips by action name and only shows one chip
        # per action -- distinct action names keep both "/" and ":" visible
        # even though they now open the same merged prompt.
        Binding("slash", "open_prompt_search", "Search", key_display="/"),
        Binding("colon", "open_prompt_command", "Command", key_display=":"),
        Binding("question_mark", "app.show_keys", "Help", key_display="?"),
    ] + [
        # Mirrors FilterBar.QUICK_SELECT_KEYS at screen level so filter
        # shortcuts work while browsing the job list, not just when the
        # filter bar itself is Tab-focused.
        Binding(key, f"quick_select_{status}", status, show=False)
        for key, status in FilterBar.QUICK_SELECT_KEYS.items()
    ]

    def __init__(self):
        super().__init__()
        saved = load_cli_state(self.app.user["username"]) if self.app.user else {}
        self.filter_index = saved.get("filter_index", 0)
        self.prompt_open = False
        self.search_term = ""
        self.awaiting_duplicate_confirm = None
        self.layer_index = -1  # -1 = summary/header, the default landing spot
        self.current_job_id = None

    def save_state(self) -> None:
        state = load_cli_state(self.app.user["username"])
        state["filter_index"] = self.filter_index
        save_cli_state(self.app.user["username"], state)

    def compose(self) -> ComposeResult:
        with Container(id="list-frame"):
            yield JobsTable(self, cursor_type="row", id="jobs-table")
        yield FilterBar(self)
        with Container(id="detail-frame"):
            with LayerNavPanel(self):
                yield Static("", id="detail-header")
                for i in range(7):
                    yield Static("", id=f"layer-section-{i}", classes="layer-section")
        yield Input(id="prompt-input", classes="hidden")
        yield Static("", id="status-line")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_jobs()
        self.update_focus_frames()
        saved = load_cli_state(self.app.user["username"])
        if saved.get("help_panel_visible"):
            self.app.action_show_help_panel()

    def on_descendant_focus(self, event) -> None:
        self.update_focus_frames()

    def on_descendant_blur(self, event) -> None:
        self.update_focus_frames()

    def update_focus_frames(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        detail = self.query_one("#detail-body")
        self.query_one("#list-frame").set_class(self.focused is table, "focused-frame")
        self.query_one("#detail-frame").set_class(self.focused is detail, "focused-frame")

    def truncate(self, text: str, max_len: int) -> str:
        return text if len(text) <= max_len else text[: max_len - 1] + "…"

    # Fixed widths for every column except ROLE · COMPANY, which gets
    # whatever's left. DataTable's *auto*-width columns only ever grow to
    # fit the widest content ever seen and never shrink back down even
    # after table.clear(columns=True) + re-adding them -- empirically
    # confirmed by querying Column.content_width before/after a resize.
    # Explicit fixed widths sidestep that entirely: every refresh_jobs()
    # call sets the exact same deterministic widths, so there's no
    # stale/stuck sizing regardless of resize timing.
    # DATE="2026-06-20"=10, VERDICT max "REJECTED_BY_COMPANY"=19,
    # LAYERS="● ● ● ● ● ●"=11, FIT="x.x/5"=5, ID="#229"=4.
    FIXED_COLUMN_WIDTHS = {"DATE": 10, "VERDICT": 19, "LAYERS": 11, "FIT": 5, "ID": 4}

    def role_company_width(self) -> int:
        # get_render_width() adds 2*cell_padding (default 1, so +2) per
        # column, for all 6 columns including this one.
        reserved = sum(self.FIXED_COLUMN_WIDTHS.values()) + 2 * 6
        table = self.query_one("#jobs-table", DataTable)
        table_width = table.size.width
        # table.size.width is the table's OUTER size -- it does NOT
        # subtract the vertical scrollbar's own gutter (confirmed live:
        # scrollbar_size_vertical=2 while a 170-row list is shown, and
        # the actual content area is 2 narrower than .size.width reports).
        # Without this, the last column lost its final 1-2 characters
        # even though the math otherwise summed exactly to table_width.
        if table.show_vertical_scrollbar:
            table_width -= table.scrollbar_size_vertical
        # A floor higher than the genuinely available space (e.g. 30 when
        # only 29 fits) forces the table 1 char past table_width every
        # time -- exactly enough to clip the last column. 15 is still
        # readable and low enough to never force that overflow at any
        # realistic terminal width.
        return max(15, table_width - reserved)

    def refresh_jobs(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        # Preserve the current selection across refreshes triggered by
        # something unrelated to the row set changing (e.g. on_resize,
        # which calls this on every width change) -- unconditionally
        # snapping back to row 0 fired RowHighlighted every time, which
        # reset the detail panel's layer navigation back to the first
        # layer on every resize (e.g. opening/closing the help panel).
        previous_job_id = None
        if table.row_count > 0:
            try:
                row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
                previous_job_id = row_key.value
            except CellDoesNotExist:
                pass
        role_company_width = self.role_company_width()
        table.clear(columns=True)
        table.add_column("DATE", width=self.FIXED_COLUMN_WIDTHS["DATE"])
        table.add_column("ROLE · COMPANY", width=role_company_width)
        table.add_column("VERDICT", width=self.FIXED_COLUMN_WIDTHS["VERDICT"])
        table.add_column("LAYERS", width=self.FIXED_COLUMN_WIDTHS["LAYERS"])
        table.add_column("FIT", width=self.FIXED_COLUMN_WIDTHS["FIT"])
        table.add_column("ID", width=self.FIXED_COLUMN_WIDTHS["ID"])
        status = FILTER_CYCLE[self.filter_index]
        self.sub_title = f"filter: {status}"
        rows = database.get_jobs(self.app.user["id"])
        term = self.search_term.lower()
        rows = [
            r for r in rows
            if job_matches_filter(r, status)
            and (not term or term in f"{r['role'] or ''} {r['company'] or ''}".lower())
        ]
        for row in rows:
            label, color = status_label(row)
            verdict_text = f"[{color}]{label}[/]" if color else label
            company = row["company"] or "Unknown"
            fit = f"{row['fit_score']:.1f}/5" if row["fit_score"] else "—"
            role_company = self.truncate(
                f"{row['role'] or '—'} · {company}", role_company_width
            )
            table.add_row(
                str(row["analyzed_at"] or "")[:10],
                role_company,
                verdict_text,
                layer_dots(row),
                fit,
                f"#{row['id']:03d}",
                key=str(row["id"]),
            )
        if table.row_count > 0:
            restored = False
            if previous_job_id is not None:
                for i, row_key in enumerate(table.rows.keys()):
                    if row_key.value == previous_job_id:
                        table.move_cursor(row=i)
                        restored = True
                        break
            if not restored:
                table.move_cursor(row=0)
        self.query_one(FilterBar).refresh_chips()

    def on_resize(self) -> None:
        self.refresh_jobs()

    def action_cycle_focus(self) -> None:
        self.focus_next()

    def action_quit_app(self) -> None:
        self.app.exit()

    def action_cursor_down(self) -> None:
        self.query_one("#jobs-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#jobs-table", DataTable).action_cursor_up()

    # Recognized command prefixes/literals -- anything else typed into the
    # prompt is treated as a list filter, not a command. Checked against
    # the raw submitted text, case as typed (filter/analyze values are
    # case-sensitive against FILTER_CYCLE; "quit"/"q" are not).
    def is_command(self, text: str) -> bool:
        return (
            text in ("quit", "q")
            or text.startswith("filter ")
            or text == "analyze"
            or text.startswith("analyze ")
        )

    def action_open_prompt_search(self) -> None:
        self.action_open_prompt()

    def action_open_prompt_command(self) -> None:
        self.action_open_prompt()

    def action_open_prompt(self) -> None:
        self.prompt_open = True
        prompt = self.query_one("#prompt-input", Input)
        prompt.remove_class("hidden")
        prompt.value = self.search_term
        prompt.focus()
        self.query_one("#status-line", Static).update(
            "[dim]enter filter/command · esc cancel[/dim]"
        )

    def close_prompt(self) -> None:
        prompt = self.query_one("#prompt-input", Input)
        prompt.add_class("hidden")
        self.prompt_open = False
        self.query_one("#jobs-table", DataTable).focus()
        self.query_one("#status-line", Static).update("")

    def on_input_changed(self, event: Input.Changed) -> None:
        if self.prompt_open:
            self.search_term = event.value
            self.refresh_jobs()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if not self.prompt_open:
            return
        text = event.value.strip()
        if self.awaiting_duplicate_confirm is not None or self.is_command(text):
            # A recognized command was the point of opening the prompt, not
            # a lingering filter -- clear search_term so it doesn't keep
            # filtering the list after the prompt closes.
            self.search_term = ""
            self.close_prompt()
            self.run_command(text)
            self.refresh_jobs()
        else:
            # Not a command -- the live filter applied via on_input_changed
            # is the whole point, just leave it in place.
            self.close_prompt()

    def run_command(self, text: str) -> None:
        status = self.query_one("#status-line", Static)
        if self.awaiting_duplicate_confirm is not None:
            pending = self.awaiting_duplicate_confirm
            self.awaiting_duplicate_confirm = None
            if text.strip().lower() == "yes":
                self.run_pipeline(*pending)
            else:
                status.update("[dim]Skipped.[/dim]")
            return
        if not text:
            return
        if text in ("quit", "q"):
            self.app.exit()
            return
        if text.startswith("filter "):
            value = text[len("filter "):].strip()
            if value in FILTER_CYCLE:
                self.filter_index = FILTER_CYCLE.index(value)
                self.save_state()
            else:
                status.update(f"[#f07178]Unknown filter: {value}[/]")
            return
        if text == "analyze" or text.startswith("analyze "):
            self.start_analysis(text[len("analyze"):].strip())
            return
        status.update(f"[#f07178]Unknown command: {text}[/]")

    def start_analysis(self, raw: str) -> None:
        status = self.query_one("#status-line", Static)
        if not raw:
            status.update("[#f07178]Usage: analyze <url|text>[/]")
            return
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            status.update("[#f07178]ANTHROPIC_API_KEY not set in environment.[/]")
            return

        source_url = ""
        source_text = ""
        if raw.startswith("http://") or raw.startswith("https://"):
            source_url = scraper.normalize_url(raw)
        else:
            source_text = raw

        existing = database.check_duplicate(self.app.user["id"], source_url or source_text)
        if existing is not None:
            self.awaiting_duplicate_confirm = (source_url, source_text or raw)
            status.update(
                f"[#ffb454]Duplicate of #{existing['id']:03d} ({existing['verdict']}). "
                f"Type 'yes' to re-analyze, anything else cancels.[/]"
            )
            return

        self.run_pipeline(source_url, source_text or raw)

    def run_pipeline(self, source_url: str, source_text: str) -> None:
        self.do_pipeline(source_url, source_text)

    @work(thread=True, exclusive=True)
    def do_pipeline(self, source_url: str, source_text: str) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        model = os.environ.get("ANTHROPIC_MODEL", analyzer.DEFAULT_MODEL)
        status = self.query_one("#status-line", Static)

        if source_url:
            self.app.call_from_thread(status.update, "[dim]Fetching...[/dim]")
            text, error_code, error_detail = scraper.fetch(source_url)
            if text is None:
                self.app.call_from_thread(
                    status.update,
                    f"[#f07178]Scrape failed ({error_code}): {error_detail}[/]",
                )
                return
            source_text = text

        self.app.call_from_thread(status.update, "[dim]Analyzing...[/dim]")
        try:
            result = analyzer.analyze(dict(self.app.user), source_text, "text", api_key, model)
        except Exception as e:
            self.app.call_from_thread(status.update, f"[#f07178]Analysis failed: {e}[/]")
            return

        try:
            job_id = database.save_job(
                self.app.user["id"], result, source_url=source_url, source_text=source_text
            )
        except Exception as e:
            self.app.call_from_thread(
                status.update,
                f"[#f07178]Analysis succeeded but saving to the database failed: {e}[/]",
            )
            return

        verdict = (result.get("verdict") or "").upper()
        self.app.call_from_thread(self.finish_analysis, job_id, verdict)

    def finish_analysis(self, job_id: int, verdict: str) -> None:
        self.query_one("#status-line", Static).update(
            f"[#7fd962]Saved #{job_id:03d} — {verdict}[/]"
        )
        self.refresh_jobs()

    def action_cancel_prompt_or_quit(self) -> None:
        if self.prompt_open:
            self.search_term = ""
            self.refresh_jobs()
            self.close_prompt()
        else:
            self.app.exit()

    def render_detail(self) -> None:
        header = self.query_one("#detail-header", Static)
        table = self.query_one("#jobs-table", DataTable)
        if table.row_count == 0:
            header.update("[dim]No jobs match this filter.[/dim]")
            for i in range(7):
                self.query_one(f"#layer-section-{i}", Static).add_class("hidden")
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        job_id = int(row_key.value)
        row = database.get_job(job_id, self.app.user["id"])
        if row is None:
            header.update(f"No job #{job_id} found.")
            for i in range(7):
                self.query_one(f"#layer-section-{i}", Static).add_class("hidden")
            return

        label, color = status_label(row)
        verdict_text = f"[{color}]{label}[/]" if color else label
        header.update(
            f"#{row['id']:03d} {row['role'] or '—'} · {row['company'] or 'Unknown'}\n"
            f"Verdict: {verdict_text}\n\n"
            f"{row['verdict_summary'] or ''}"
        )

        # Slots 0-4 are the LAYER_PANELS entries (Triage/Product/Business/
        # Reputation/Values), slot 5 is Fit, slot 6 is Gut feeling -- all
        # always visible (Gut feeling hides itself if the row has none).
        for i, (title, status_col, findings_col) in enumerate(LAYER_PANELS):
            section = self.query_one(f"#layer-section-{i}", Static)
            section.remove_class("hidden")
            status = row[status_col] or "?"
            dot_color = STATUS_DOT_COLOR.get(status, "")
            status_text = f"[{dot_color}]{status.upper()}[/]" if dot_color else status.upper()
            section.update(
                f"[bold #39bae6]{title}[/] — {status_text}\n{row[findings_col] or '(no findings)'}"
            )

        fit_section = self.query_one("#layer-section-5", Static)
        gut_section = self.query_one("#layer-section-6", Static)
        fit_status = row["fit_status"] or "?"
        fit_color = STATUS_DOT_COLOR.get(fit_status, "")
        fit_score = f"{row['fit_score']:.1f}/5" if row["fit_score"] else "—"
        fit_text = f"[{fit_color}]{fit_status.upper()}[/]" if fit_color else fit_status.upper()
        fit_section.remove_class("hidden")
        fit_section.update(
            f"[bold #39bae6]Fit ({fit_score})[/] — {fit_text}\n"
            f"Strengths: {row['fit_strengths'] or '—'}\n"
            f"Gaps: {row['fit_gaps'] or '—'}\n"
            f"Improve: {row['fit_improve'] or '—'}"
        )
        if row["gut_feeling"]:
            gut_section.remove_class("hidden")
            gut_section.update(f"[bold #39bae6]Gut feeling[/]\n{row['gut_feeling']}")
        else:
            gut_section.add_class("hidden")

        # Only reset to the first layer when this is actually a different
        # job. DataTable's cursor_coordinate is always_update=True, so
        # RowHighlighted (and this render) fires even when the cursor
        # lands back on the SAME row -- e.g. refresh_jobs() re-selecting
        # the previously-selected row after a resize. Without this check,
        # opening/closing the help panel (or any width change) snapped
        # layer navigation back to the first layer every time.
        if row["id"] != self.current_job_id:
            self.current_job_id = row["id"]
            self.layer_index = -1  # land on the summary, not Triage
        self.apply_layer_highlight()

    def visible_layer_sections(self) -> list:
        return [
            s for s in self.query(".layer-section")
            if "hidden" not in s.classes
        ]

    def apply_layer_highlight(self) -> None:
        sections = self.visible_layer_sections()
        if sections and self.layer_index >= len(sections):
            # e.g. switching to a job with no gut feeling shrinks the
            # visible set; without this, an index past the new end
            # highlights nothing.
            self.layer_index = len(sections) - 1
        for i, section in enumerate(sections):
            section.set_class(i == self.layer_index, "current")
        self.query_one("#detail-header").set_class(self.layer_index == -1, "current")
        if self.layer_index == -1:
            # -1 is the header/summary above Triage -- not one of the
            # indexed sections. Without this state, there was no keyboard
            # way back to the summary once you'd moved into the layers:
            # k/up at Triage just wrapped to the LAST layer, never up to
            # the header, leaving mouse-scroll as the only way there.
            # immediate=True -- scroll_to()'s default defers until the next
            # screen refresh, so reading scroll_y right after this call
            # (e.g. in a test, or a fast double-press) would still see the
            # pre-scroll position. Also: this method lives on MainScreen,
            # not LayerNavPanel -- self.scroll_home() was scrolling the
            # SCREEN, not the #detail-body panel, so it silently did
            # nothing useful. Must target the panel explicitly.
            self.query_one("#detail-body").scroll_home(animate=False, immediate=True)
        elif sections and 0 <= self.layer_index < len(sections):
            # animate=False -- an in-flight smooth-scroll animation from a
            # rapid previous keypress could still be resolving when the
            # next one lands, which was producing flaky/lost layer moves
            # under fast repeated j/k (confirmed via repeated headless runs
            # of the same input sequence giving different results).
            sections[self.layer_index].scroll_visible(animate=False, immediate=True)

    def move_layer(self, delta: int) -> None:
        sections = self.visible_layer_sections()
        if not sections:
            return
        # Full cycle includes the header as position -1: header -> Triage
        # -> ... -> last layer -> header -> ... in both directions, so
        # the header is always reachable by keyboard alone.
        self.layer_index = ((self.layer_index + 1 + delta) % (len(sections) + 1)) - 1
        self.apply_layer_highlight()

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.render_detail()

    def on_screen_resume(self) -> None:
        self.refresh_jobs()
        self.render_detail()


# Screen-level counterpart to the generation loop below FilterBar -- same
# reasoning: Textual resolves a binding to a literal "action_<name>" method,
# so each quick-select status needs its own real method on MainScreen too.
for _status in FilterBar.QUICK_SELECT_KEYS.values():
    setattr(
        MainScreen,
        f"action_quick_select_{_status}",
        lambda self, status=_status: self.query_one(FilterBar).select_filter(status),
    )
del _status


class FieldEditorScreen(Screen):
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "app.pop_screen", "Cancel"),
    ]

    def __init__(self, field_name: str, label: str):
        super().__init__()
        self.field_name = field_name
        self.label_text = label

    def compose(self) -> ComposeResult:
        yield Label(f"Edit {self.label_text} — Ctrl+S to save, Esc to cancel")
        yield TextArea(self.app.user[self.field_name] or "", id="field-editor")
        yield Static("", id="editor-status")

    def on_mount(self) -> None:
        self.query_one("#field-editor", TextArea).focus()

    def action_save(self) -> None:
        new_value = self.query_one("#field-editor", TextArea).text
        current = self.app.user
        fields = {
            "cv": current["cv"] or "",
            "zero_list": current["zero_list"] or "",
            "criteria": current["criteria"] or "",
            "yellow_list": current["yellow_list"] or "",
        }
        fields[self.field_name] = new_value
        database.update_user_profile(
            current["id"], fields["cv"], fields["zero_list"],
            fields["criteria"], fields["yellow_list"],
        )
        self.app.user = database.get_user(current["username"])
        self.query_one("#editor-status", Static).update("[#7fd962]Saved.[/]")


class JobScreenerApp(App):
    user: object = None
    COMMAND_PALETTE_BINDING = "ctrl+s"
    # Textual's default focus/blur border style for Input/TextArea is
    # "tall", which uses partial-block glyphs (▊ ▔ ▎ ▁ -- the same
    # Unicode range as the scrollbar thumb) that render inconsistently
    # across SVG-screenshot viewers. Override to "round" everywhere, which
    # uses plain box-drawing characters already confirmed to render
    # correctly. Applies globally so every screen's Input/TextArea is
    # covered without repeating this in each screen's CSS.
    CSS = """
    Input, TextArea {
        border: round $border-blurred;
    }
    Input:focus, TextArea:focus {
        border: round $border;
    }
    /* The Settings command palette's search bar (#--input, a Horizontal
       container -- not itself an Input, so the rule above doesn't reach
       it) gets the exact same round-border treatment as every other text
       box in the app instead of a hardcoded "black 50%" -- there's no
       real difference between typing in this search and typing in our
       own / search or : command prompt, so they should look identical. */
    CommandPalette #--input {
        border: round $border;
    }
    /* Textual's CommandPalette is otherwise just a translucent overlay
       with no box of its own -- give its content area the same round
       $primary frame as #login-box, so "Settings" reads as the same kind
       of modal as the rest of the app instead of a bare floating list. */
    CommandPalette > Vertical {
        border: round $primary;
        width: 80%;
        max-width: 100;
    }
    /* Match the filter bar's reverse-block key letters (FilterBar.compose())
       in the Footer too, instead of Footer's default themed-background
       pill -- same "letter in block reverse" treatment everywhere a
       single key is called out. */
    .footer-key--key {
        background: $foreground;
        color: $background;
        /* Footer defaults to non-compact (padding: 0 1), which pads the
           reverse block with a blank cell on each side -- the filter
           chips' reverse letters have no such padding, so trim it here
           to match: the block should cover exactly the key glyph(s). */
        padding: 0;
    }
    /* Space between the key block and its description ("tab" then a gap
       before "Focus"), instead of the two running together. */
    .footer-key--description {
        padding: 0 1 0 1;
    }
    /* "ascii" is the one border style whose middle-row glyph is a literal
       "|" -- gives each footer entry a real " | " separator from the one
       before it (margin-left supplies the leading space, the description's
       own right padding above supplies the trailing one). */
    FooterKey {
        border-left: ascii $border-blurred;
        margin-left: 1;
    }
    /* HelpPanel defaults to width:33% (capped 30-60), and KeyPanel centers
       its (auto-width) bindings table inside that box -- on a wide
       terminal this leaves a big dead gap before the text. Size the panel
       to its content instead of a fraction of screen width, and left-align
       so the table sits flush against the left edge of the panel. */
    /* Sized for the worst-case line across every screen, not just
       MainScreen's own bindings -- any Input (our prompt, CommandPalette's
       own search box) carries a built-in arrow-key description ("Move
       cursor right or accept suggestion", shortened above) that shows up
       in the panel whenever that Input has focus. Narrower wraps that line. */
    HelpPanel {
        width: auto;
        min-width: 61;
        max-width: 61;
    }
    KeyPanel#keys-help {
        align: left top;
        /* KeyPanel's own plain-class DEFAULT_CSS (_key_panel.py) sets
           max-width: 60 -- nothing in HelpPanel's nested override of this
           same #keys-help selector touches max-width, so that cap survives
           untouched no matter how wide HelpPanel itself is sized, silently
           clipping content to 60 cols regardless of our width settings above. */
        max-width: 100%;
    }
    """
    # priority=True so the screenshot binding fires even inside a ModalScreen
    # (e.g. the Settings command palette) -- ModalScreen blocks ordinary
    # App-level bindings by design, but priority bindings are checked first
    # regardless. The "Settings" binding here pre-empts App.__init__'s own
    # auto-added "ctrl+s -> command_palette" binding (description hardcoded
    # to "palette") -- it only auto-adds when no existing binding already
    # targets the command_palette action. show=False because Footer always
    # renders its own dedicated command-palette chip on the right
    # (Footer.show_command_palette, reads this binding's .description) --
    # show=True here would draw the same "^s Settings" a second time in
    # the regular key list.
    BINDINGS = [
        Binding("ctrl+p", "save_app_screenshot", "Screenshot", show=False, priority=True),
        Binding("ctrl+s", "command_palette", "Settings", show=False),
        # Base App's own ctrl+q binding has a stock tooltip ("...and return
        # to the command prompt") that doesn't describe what actually
        # happens here -- it exits the whole app, not "returns" anywhere.
        Binding("ctrl+q", "quit", "Quit", tooltip="Quit the app.", show=False, priority=True),
    ]

    def check_action(self, action, parameters):
        # The command-palette binding is a *priority* binding, which Textual
        # always checks app-first regardless of focus — so without this, the
        # palette would intercept every Ctrl+S press and FieldEditorScreen's
        # own "ctrl+s -> save" binding would never fire. Disabling the action
        # here (the standard Textual "dynamic actions" hook) lets the
        # keypress fall through to the focused screen's own binding instead.
        if action == "command_palette" and self.screen_stack and isinstance(self.screen, FieldEditorScreen):
            return False
        return True

    def on_mount(self) -> None:
        self.register_theme(JOB_SCREENER_THEME)
        self.register_theme(JOB_SCREENER_LIGHT_THEME)
        self.theme = "job-screener"
        self.push_screen(LoginScreen())

    # Titles from the base App's own get_system_commands() that we replace
    # with our own version below (state-persisting "Show keys", XML-fixed
    # "Save screenshot") -- yielding both would show two near-identical
    # entries in the picker for the same action.
    _OVERRIDDEN_SYSTEM_COMMANDS = {
        "Show keys and help panel", "Hide keys and help panel", "Save screenshot",
    }

    def get_system_commands(self, screen):
        # super()'s own commands include "Change theme", which opens
        # Textual's full theme picker -- every built-in Textual theme
        # (nord, gruvbox, dracula, etc.) plus our two registered ones.
        # Overriding get_system_commands() without this would silently
        # drop that picker down to nothing, since this method *replaces*
        # the base list rather than extending it.
        for command in super().get_system_commands(screen):
            if command.title not in self._OVERRIDDEN_SYSTEM_COMMANDS:
                yield command
        yield SystemCommand("Edit CV", "Edit your CV text", lambda: self.push_screen(FieldEditorScreen("cv", "CV")))
        yield SystemCommand("Edit Zero list", "Edit your zero-list", lambda: self.push_screen(FieldEditorScreen("zero_list", "Zero list")))
        yield SystemCommand("Edit Yellow list", "Edit your yellow-list", lambda: self.push_screen(FieldEditorScreen("yellow_list", "Yellow list")))
        yield SystemCommand("Edit criteria", "Edit your additional criteria", lambda: self.push_screen(FieldEditorScreen("criteria", "Criteria")))
        yield SystemCommand("Show keys", "Show all keybindings", self.action_show_keys)
        yield SystemCommand("Save screenshot", "Save a screenshot of the current screen", self.action_save_app_screenshot)

    def action_change_theme(self) -> None:
        # Base App.search_themes() requires Enter to apply a theme -- here
        # the theme switches the instant a different one is highlighted
        # (arrowing through the list), since trying themes is the whole
        # point of this picker and "preview" is really just "select".
        self._previewing_theme = True

        def _done(_=None) -> None:
            self._previewing_theme = False

        self.push_screen(
            CommandPalette(providers=[ThemeProvider], placeholder="Search for themes…"),
            _done,
        )

    def on_command_palette_option_highlighted(self, event: CommandPalette.OptionHighlighted) -> None:
        if not getattr(self, "_previewing_theme", False):
            return
        option = event.highlighted_event.option
        if isinstance(option, Command):
            option.hit.command()

    def action_show_keys(self) -> None:
        # Use Textual's own dockable HelpPanel (auto-built from every
        # active BINDINGS list) instead of a one-line status message --
        # this is the side panel with full key/description listing.
        try:
            self.screen.query_one(HelpPanel)
            self.action_hide_help_panel()
            visible = False
        except NoMatches:
            self.action_show_help_panel()
            visible = True
        if self.user:
            state = load_cli_state(self.user["username"])
            state["help_panel_visible"] = visible
            save_cli_state(self.user["username"], state)

    def action_save_app_screenshot(self) -> None:
        # Root cause of the garbled glyphs: export_screenshot()'s SVG has no
        # <?xml ... encoding="UTF-8"?> declaration, even though its actual
        # bytes are correctly UTF-8 (confirmed: the bullet char's bytes are
        # the right \xe2\x97\x8f for U+25CF). Without an explicit encoding
        # declaration, some SVG viewers guess a different encoding (e.g.
        # Latin-1/CP1252) and misread every multi-byte character -- box
        # borders and layer dots -- as mojibake.
        #
        # An earlier version of this fix ALSO swapped the hardcoded
        # CDN-loaded "Fira Code" web font for a local stack (JetBrains
        # Mono/SF Mono/Menlo/Consolas), to drop the network dependency.
        # That swap was reverted: it introduced a regression -- visible
        # gaps between stacked "thick" left-border block characters
        # across consecutive lines. Rich's SVG template's line-height/
        # char-height CSS values are tuned for Fira Code's specific
        # metrics; the substituted fonts don't share them, so multi-line
        # block glyphs stopped tiling seamlessly. Confirmed directly:
        # re-rendering with Fira Code restored seamless borders with the
        # encoding fix alone, no glyph corruption either, so the font
        # swap was solving nothing the encoding fix didn't already cover.
        svg = self.export_screenshot()
        svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + svg
        path = os.path.join(".", "screenshot.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        screen = self.screen
        if hasattr(screen, "query_one"):
            try:
                status = screen.query_one("#status-line", Static)
                status.update(f"[#7fd962]Saved screenshot to {path}[/]")
            except NoMatches:
                pass


def main():
    app = JobScreenerApp()
    app.run()


if __name__ == "__main__":
    main()
