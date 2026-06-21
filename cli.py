import os

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import Button, DataTable, Footer, Input, Label, Static

import analyzer
import database
import scraper

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
VERDICT_COLOR = {"rejected": "#f07178", "warning": "#ffb454", "worth_considering": "#7fd962"}
FILTER_CYCLE = [
    "all", "rejected", "warning", "worth_considering",
    "applied", "interview", "offer", "company_rejected",
]


def layer_dots(row) -> str:
    parts = []
    for col in LAYER_COLUMNS:
        status = row[col] or ""
        color = STATUS_DOT_COLOR.get(status, "")
        parts.append(f"[{color}]●[/]" if color else "○")
    return " ".join(parts)


def job_matches_filter(row, status: str) -> bool:
    if status == "all":
        return True
    if status == "applied":
        return bool(row["applied"])
    if status == "company_rejected":
        return bool(row["company_rejected"])
    if status == "interview":
        return bool(row["interview_scheduled"])
    if status == "offer":
        return bool(row["offer_received"])
    return (row["verdict"] or "").lower() == status


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
        self.app.switch_screen(BrowseScreen())


class HelpScreen(ModalScreen):
    CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-box {
        width: 60;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $panel;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="help-box"):
            yield Label(
                "Keybindings\n\n"
                "  up/down, j/k   move selection\n"
                "  enter          open job detail\n"
                "  f              cycle status filter\n"
                "  a              analyze a new listing\n"
                "  ?              this help\n"
                "  q / escape     quit\n\n"
                "Press any key to close."
            )

    def on_key(self, event) -> None:
        self.app.pop_screen()


class BrowseScreen(Screen):
    BINDINGS = [
        Binding("f", "cycle_filter", "Filter"),
        Binding("a", "analyze", "Analyze"),
        Binding("question_mark", "show_help", "Help", key_display="?"),
        Binding("q", "quit_app", "Quit"),
        Binding("escape", "quit_app", "Quit", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.filter_index = 0

    def compose(self) -> ComposeResult:
        yield DataTable(cursor_type="row", id="jobs-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.add_columns("DATE", "ROLE · COMPANY", "VERDICT", "LAYERS", "FIT", "ID")
        self.refresh_jobs()

    def refresh_jobs(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.clear()
        status = FILTER_CYCLE[self.filter_index]
        self.sub_title = f"filter: {status}"
        rows = database.get_jobs(self.app.user["id"])
        rows = [r for r in rows if job_matches_filter(r, status)]
        for row in rows:
            verdict = row["verdict"] or ""
            color = VERDICT_COLOR.get(verdict, "")
            verdict_text = f"[{color}]{verdict.upper()}[/]" if color else verdict.upper()
            company = row["company"] or "Unknown"
            fit = f"{row['fit_score']:.1f}/5" if row["fit_score"] else "—"
            table.add_row(
                str(row["analyzed_at"] or "")[:10],
                f"{row['role'] or '—'} · {company}",
                verdict_text,
                layer_dots(row),
                fit,
                f"#{row['id']:03d}",
                key=str(row["id"]),
            )

    def action_cycle_filter(self) -> None:
        self.filter_index = (self.filter_index + 1) % len(FILTER_CYCLE)
        self.refresh_jobs()

    def action_analyze(self) -> None:
        self.app.push_screen(AnalyzeScreen())

    def action_show_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def action_quit_app(self) -> None:
        self.app.exit()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        job_id = int(event.row_key.value)
        self.app.push_screen(DetailScreen(job_id))

    def on_screen_resume(self) -> None:
        self.refresh_jobs()


class DetailScreen(Screen):
    # Namespaced "app.pop_screen" — Screen itself has no action_pop_screen,
    # only App does; an unqualified "pop_screen" silently fails to dispatch.
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("f", "toggle_full", "Full/Brief"),
    ]

    def __init__(self, job_id: int):
        super().__init__()
        self.job_id = job_id
        self.full = False
        self.job_row = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="detail-body"):
            yield Label("Loading...", id="detail-content")
        yield Footer()

    def on_mount(self) -> None:
        self.job_row = database.get_job(self.job_id, self.app.user["id"])
        self.render_detail()

    def action_toggle_full(self) -> None:
        self.full = not self.full
        self.render_detail()

    def render_detail(self) -> None:
        content = self.query_one("#detail-content", Label)
        row = self.job_row
        if row is None:
            content.update(f"No job #{self.job_id} found.")
            return

        verdict = row["verdict"] or ""
        color = VERDICT_COLOR.get(verdict, "")
        verdict_text = f"[{color}]{verdict.upper()}[/]" if color else verdict.upper()

        lines = [
            f"#{row['id']:03d} {row['role'] or '—'} · {row['company'] or 'Unknown'}",
            f"Verdict: {verdict_text}",
            "",
            row["verdict_summary"] or "",
            "",
        ]

        panels = LAYER_PANELS if self.full else LAYER_PANELS[:3]
        for title, status_col, findings_col in panels:
            status = row[status_col] or "?"
            dot_color = STATUS_DOT_COLOR.get(status, "")
            status_text = f"[{dot_color}]{status.upper()}[/]" if dot_color else status.upper()
            lines.append(f"[bold #39bae6]{title}[/] — {status_text}")
            lines.append(row[findings_col] or "(no findings)")
            lines.append("")

        if self.full:
            fit_status = row["fit_status"] or "?"
            fit_color = STATUS_DOT_COLOR.get(fit_status, "")
            fit_score = f"{row['fit_score']:.1f}/5" if row["fit_score"] else "—"
            fit_text = f"[{fit_color}]{fit_status.upper()}[/]" if fit_color else fit_status.upper()
            lines.append(f"[bold]Fit ({fit_score})[/] — {fit_text}")
            lines.append(f"Strengths: {row['fit_strengths'] or '—'}")
            lines.append(f"Gaps: {row['fit_gaps'] or '—'}")
            lines.append(f"Improve: {row['fit_improve'] or '—'}")
            lines.append("")
            if row["gut_feeling"]:
                lines.append(f"[bold]Gut feeling[/]\n{row['gut_feeling']}")
        else:
            lines.append("[dim]Press 'f' for all 6 layers[/dim]")

        content.update("\n".join(lines))


class AnalyzeScreen(Screen):
    CSS = """
    AnalyzeScreen {
        align: center middle;
    }
    #analyze-box {
        width: 70;
        height: auto;
        border: round $primary;
        padding: 1 2;
    }
    .hidden {
        display: none;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Back")]

    def __init__(self):
        super().__init__()
        self.pending_source_url = ""
        self.pending_source_text = ""
        self.busy = False

    def compose(self) -> ComposeResult:
        with Container(id="analyze-box"):
            yield Label("Analyze a listing — paste a URL or the listing text:")
            yield Input(placeholder="https://... or pasted text", id="analyze-input")
            yield Static("", id="analyze-status")
            with Container(id="analyze-confirm", classes="hidden"):
                yield Label("Duplicate found. Re-analyze anyway?", id="dup-label")
                yield Button("Re-analyze", id="dup-yes", variant="warning")
                yield Button("Cancel", id="dup-no")
        yield Footer()

    def action_cancel(self) -> None:
        if self.busy:
            return
        self.app.pop_screen()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        if not raw or self.busy:
            return
        self.start_analysis(raw)

    def start_analysis(self, raw: str) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self.set_status("[#f07178]ANTHROPIC_API_KEY not set in environment.[/]")
            return

        source_url = ""
        source_text = ""
        if raw.startswith("http://") or raw.startswith("https://"):
            source_url = scraper.normalize_url(raw)
        else:
            source_text = raw

        existing = database.check_duplicate(
            self.app.user["id"], source_url or source_text
        )
        if existing is not None:
            self.pending_source_url = source_url
            self.pending_source_text = source_text or raw
            self.query_one("#analyze-confirm").remove_class("hidden")
            self.query_one("#dup-label", Label).update(
                f"Duplicate of #{existing['id']:03d} ({existing['verdict']}). "
                f"Re-analyze anyway?"
            )
            return

        self.run_pipeline(source_url, source_text or raw)

    @on(Button.Pressed, "#dup-yes")
    def on_dup_yes(self) -> None:
        self.query_one("#analyze-confirm").add_class("hidden")
        self.run_pipeline(self.pending_source_url, self.pending_source_text)

    @on(Button.Pressed, "#dup-no")
    def on_dup_no(self) -> None:
        self.query_one("#analyze-confirm").add_class("hidden")
        self.set_status("[dim]Skipped.[/dim]")

    def run_pipeline(self, source_url: str, source_text: str) -> None:
        self.busy = True
        self.query_one("#analyze-input", Input).disabled = True
        self.do_pipeline(source_url, source_text)

    def set_status(self, text: str) -> None:
        self.query_one("#analyze-status", Static).update(text)

    @work(thread=True)
    def do_pipeline(self, source_url: str, source_text: str) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        model = os.environ.get("ANTHROPIC_MODEL", analyzer.DEFAULT_MODEL)

        if source_url:
            self.app.call_from_thread(self.set_status, "[dim]Fetching...[/dim]")
            text, error_code, error_detail = scraper.fetch(source_url)
            if text is None:
                self.app.call_from_thread(
                    self.finish_error,
                    f"[#f07178]Scrape failed ({error_code}): {error_detail}[/]",
                )
                return
            source_text = text

        self.app.call_from_thread(self.set_status, "[dim]Analyzing...[/dim]")
        try:
            result = analyzer.analyze(
                dict(self.app.user), source_text, "text", api_key, model
            )
        except Exception as e:
            self.app.call_from_thread(self.finish_error, f"[#f07178]Analysis failed: {e}[/]")
            return

        try:
            job_id = database.save_job(
                self.app.user["id"], result, source_url=source_url, source_text=source_text
            )
        except Exception as e:
            self.app.call_from_thread(
                self.finish_error,
                f"[#f07178]Analysis succeeded but saving to the database failed: {e}[/]",
            )
            return

        verdict = (result.get("verdict") or "").upper()
        self.app.call_from_thread(self.finish_success, job_id, verdict)

    def finish_error(self, message: str) -> None:
        self.busy = False
        self.query_one("#analyze-input", Input).disabled = False
        self.set_status(message)

    def finish_success(self, job_id: int, verdict: str) -> None:
        self.busy = False
        self.set_status(f"[#7fd962]Saved #{job_id:03d} — {verdict}[/]")
        self.app.pop_screen()


class JobScreenerApp(App):
    user: object = None

    def on_mount(self) -> None:
        self.register_theme(JOB_SCREENER_THEME)
        self.theme = "job-screener"
        self.push_screen(LoginScreen())


def main():
    app = JobScreenerApp()
    app.run()


if __name__ == "__main__":
    main()
