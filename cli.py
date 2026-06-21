import os

from textual import on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import DataTable, Footer, Input, Label, Static, TextArea

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
        self.app.switch_screen(MainScreen())


class MainScreen(Screen):
    CSS = """
    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        Binding("f", "toggle_full", "Layers"),
        Binding("q", "quit_app", "Quit"),
        Binding("escape", "cancel_prompt_or_quit", "Back", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("slash", "open_search", "Search", key_display="/"),
        Binding("colon", "open_command", "Command", key_display=":"),
    ]

    def __init__(self):
        super().__init__()
        self.filter_index = 0
        self.full = False
        self.prompt_mode = None
        self.search_term = ""
        self.awaiting_duplicate_confirm = None

    def compose(self) -> ComposeResult:
        table = DataTable(cursor_type="row", id="jobs-table")
        table.styles.height = 9  # header + 7 visible data rows
        yield table
        with VerticalScroll(id="detail-body"):
            yield Label("", id="detail-content")
        yield Static("", id="legend-bar")
        yield Input(id="prompt-input", classes="hidden")
        yield Static("", id="status-line")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.add_columns("DATE", "ROLE · COMPANY", "VERDICT", "LAYERS", "FIT", "ID")
        self.refresh_jobs()
        self.update_legend()

    def truncate(self, text: str, max_len: int = 40) -> str:
        return text if len(text) <= max_len else text[: max_len - 1] + "…"

    def refresh_jobs(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.clear()
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
            verdict = row["verdict"] or ""
            color = VERDICT_COLOR.get(verdict, "")
            verdict_text = f"[{color}]{verdict.upper()}[/]" if color else verdict.upper()
            company = row["company"] or "Unknown"
            fit = f"{row['fit_score']:.1f}/5" if row["fit_score"] else "—"
            role_company = self.truncate(f"{row['role'] or '—'} · {company}")
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
            table.move_cursor(row=0)

    def update_legend(self) -> None:
        legend = self.query_one("#legend-bar", Static)
        if self.prompt_mode == "search":
            legend.update("[dim]enter apply · esc cancel[/dim]")
        elif self.prompt_mode == "command":
            legend.update("[dim]enter submit · esc cancel[/dim]")
        else:
            legend.update(
                "[dim]j/k move · enter select · f layers · "
                "/ search · : command · q quit[/dim]"
            )

    def action_toggle_full(self) -> None:
        self.full = not self.full
        self.render_detail()

    def action_quit_app(self) -> None:
        self.app.exit()

    def action_cursor_down(self) -> None:
        self.query_one("#jobs-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#jobs-table", DataTable).action_cursor_up()

    def action_open_search(self) -> None:
        self.prompt_mode = "search"
        prompt = self.query_one("#prompt-input", Input)
        prompt.remove_class("hidden")
        prompt.value = self.search_term
        prompt.focus()
        self.update_legend()

    def action_open_command(self) -> None:
        self.prompt_mode = "command"
        prompt = self.query_one("#prompt-input", Input)
        prompt.remove_class("hidden")
        prompt.value = ""
        prompt.focus()
        self.update_legend()

    def close_prompt(self) -> None:
        prompt = self.query_one("#prompt-input", Input)
        prompt.add_class("hidden")
        self.prompt_mode = None
        self.query_one("#jobs-table", DataTable).focus()
        self.update_legend()

    def on_input_changed(self, event: Input.Changed) -> None:
        if self.prompt_mode == "search":
            self.search_term = event.value
            self.refresh_jobs()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.prompt_mode == "search":
            self.close_prompt()
        elif self.prompt_mode == "command":
            self.run_command(event.value.strip())
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
        if text in ("full", "brief"):
            self.full = text == "full"
            self.render_detail()
            return
        if text in ("quit", "q"):
            self.app.exit()
            return
        if text.startswith("filter "):
            value = text[len("filter "):].strip()
            if value in FILTER_CYCLE:
                self.filter_index = FILTER_CYCLE.index(value)
                self.refresh_jobs()
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
        if self.prompt_mode is not None:
            if self.prompt_mode == "search":
                self.search_term = ""
                self.refresh_jobs()
            self.close_prompt()
        else:
            self.app.exit()

    def render_detail(self) -> None:
        content = self.query_one("#detail-content", Label)
        table = self.query_one("#jobs-table", DataTable)
        if table.row_count == 0:
            content.update("[dim]No jobs match this filter.[/dim]")
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        job_id = int(row_key.value)
        row = database.get_job(job_id, self.app.user["id"])
        if row is None:
            content.update(f"No job #{job_id} found.")
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

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.render_detail()

    def on_screen_resume(self) -> None:
        self.refresh_jobs()
        self.render_detail()


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

    def get_system_commands(self, screen):
        yield SystemCommand("Edit CV", "Edit your CV text", lambda: self.push_screen(FieldEditorScreen("cv", "CV")))
        yield SystemCommand("Edit Zero list", "Edit your zero-list", lambda: self.push_screen(FieldEditorScreen("zero_list", "Zero list")))
        yield SystemCommand("Edit Yellow list", "Edit your yellow-list", lambda: self.push_screen(FieldEditorScreen("yellow_list", "Yellow list")))
        yield SystemCommand("Edit criteria", "Edit your additional criteria", lambda: self.push_screen(FieldEditorScreen("criteria", "Criteria")))
        yield SystemCommand("Change theme", "Toggle dark/light theme", self.action_toggle_app_theme)
        yield SystemCommand("Show keys", "Show all keybindings", self.action_show_keys)
        yield SystemCommand("Save screenshot", "Save a screenshot of the current screen", self.action_save_app_screenshot)
        yield SystemCommand("Quit", "Quit the application", self.action_quit)

    def action_toggle_app_theme(self) -> None:
        self.theme = "job-screener-light" if self.theme == "job-screener" else "job-screener"

    def action_show_keys(self) -> None:
        screen = self.screen
        if hasattr(screen, "query_one"):
            try:
                status = screen.query_one("#status-line", Static)
                status.update(
                    "[dim]j/k move · enter select · f layers · / search · "
                    ": command · ctrl+s settings · q quit[/dim]"
                )
            except Exception:
                pass

    def action_save_app_screenshot(self) -> None:
        path = self.save_screenshot(filename="screenshot.svg")
        screen = self.screen
        if hasattr(screen, "query_one"):
            try:
                status = screen.query_one("#status-line", Static)
                status.update(f"[#7fd962]Saved screenshot to {path}[/]")
            except Exception:
                pass


def main():
    app = JobScreenerApp()
    app.run()


if __name__ == "__main__":
    main()
