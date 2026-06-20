import os
import secrets
import functools
import pathlib
import re
from typing import Optional
import threading
import time
import webbrowser
import html as _html
import json as _json
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, make_response, flash
)
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from database import (
    init_db, get_user, create_user, get_user_by_id,
    update_user_profile, update_password, save_job, get_jobs, get_job,
    export_csv, user_count, check_duplicate, update_verdict, update_job_url, delete_job, update_applied,
    update_company_rejected, update_job_status, update_job_notes, verify_password, get_statistics,
    create_analysis, update_analysis_status, get_analysis, get_active_analyses_labels,
    save_interview_prep, get_interview_prep,
    save_cv_tailoring, get_cv_tailoring,
    add_feed, get_feeds, delete_feed, save_feed_items, get_feed_items, get_feed_item,
    mark_feed_item_analyzed, update_feed_fetched,
)
from fetcher import fetch_feed
from analyzer import analyze, interview_prep, cv_tailoring
from scraper import fetch as scrape_url, normalize_url

app: Flask = Flask(__name__)
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.secret_key = _secret_key
app.config["WTF_CSRF_SECRET_KEY"] = _secret_key
csrf = CSRFProtect(app)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'True').lower() not in ('false', '0', 'no')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 1_000_000))  # 1MB

from datetime import datetime, timedelta
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

init_db()

# Account lockout: {username_lower: [timestamp_of_failure, ...]}
_login_attempts: dict = {}
_LOCKOUT_THRESHOLD = 5      # failures before lockout
_LOCKOUT_WINDOW = 300       # seconds — window in which failures are counted
_LOCKOUT_DURATION = 900     # seconds — how long the lockout lasts


def _is_locked_out(username: str) -> bool:
    attempts = _login_attempts.get(username, [])
    if len(attempts) < _LOCKOUT_THRESHOLD:
        return False
    lockout_start = attempts[_LOCKOUT_THRESHOLD - 1]
    return (time.time() - lockout_start) < _LOCKOUT_DURATION


def _record_failure(username: str) -> None:
    now = time.time()
    attempts = _login_attempts.setdefault(username, [])
    attempts[:] = [t for t in attempts if now - t < _LOCKOUT_WINDOW]
    attempts.append(now)


def _clear_attempts(username: str) -> None:
    _login_attempts.pop(username, None)


@app.after_request
def security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Server"] = "unknown"
    return response

# ── auth helpers ────────────────────────────────────────────────────────────

def current_user() -> Optional[dict]:
    """
    Return the current user from the session.

    Returns:
        sqlite3.Row with user data, or None
    """
    uid = session.get("user_id")
    return get_user_by_id(uid) if uid else None


def login_required(f):
    """Decorator that requires an authenticated session."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id") or not current_user():
            session.clear()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
               request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
                return jsonify({"error": "Session expired. Please log in again."}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index() -> str:
    """
    Root route — redirect to dashboard or login.
    
    Returns:
        Redirect to dashboard if logged in, login otherwise
    """
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per 5 minutes")
def login() -> str:
    """
    Login page.

    Returns:
        Rendered login template
    """
    # first run: show registration instead
    if user_count() == 0:
        return redirect(url_for("register"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        if _is_locked_out(username):
            flash("Account is temporarily locked due to too many failed attempts. Try again in 15 minutes.")
            return render_template("login.html")

        user = get_user(username)
        if user and verify_password(password, user["password_hash"]):
            _clear_attempts(username)
            session.permanent = True
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        _record_failure(username)
        flash("Invalid username or password.")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("3 per hour")
def register() -> str:
    """
    Registration page.

    Returns:
        Rendered registration template
    """
    # only allow registration if no users exist yet OR invite token matches
    allow = user_count() == 0
    invite_token = os.environ.get("INVITE_TOKEN", "")
    token_from_url = request.args.get("token", "") or request.form.get("token", "")
    if invite_token and secrets.compare_digest(token_from_url, invite_token):
        allow = True

    if not allow:
        flash("Registration is disabled. Contact the administrator.")
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        if not username or not password:
            flash("Please fill in all fields.")
        elif password != password2:
            flash("Passwords do not match.")
        elif len(password) < 10:
            flash("Password must be at least 10 characters.")
        elif not create_user(username, password):
            flash("That username is already taken.")
        else:
            user = get_user(username)
            session["user_id"] = user["id"]
            flash("Account created. Complete your profile in Settings.")
            return redirect(url_for("settings"))
    return render_template("register.html", token=token_from_url)


@app.route("/logout")
def logout() -> str:
    """
    Log out the current user.

    Returns:
        Redirect to login page
    """
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard() -> str:
    """
    User dashboard page.

    Returns:
        Rendered dashboard template
    """
    user = current_user()
    jobs = get_jobs(user["id"])
    has_cv = bool((user["cv"] or "").strip())
    has_api_key = bool(API_KEY)
    return render_template("dashboard.html",
                           user=user, jobs=jobs,
                           has_cv=has_cv, has_api_key=has_api_key)


def _run_analysis_bg(
    analysis_id: str,
    user: dict,
    input_text: str,
    url: str,
    feed_item_id: Optional[int] = None,
) -> None:
    try:
        update_analysis_status(analysis_id, "running")
        result = analyze(user, input_text, "text", API_KEY, MODEL)
        job_id = save_job(user["id"], result, source_url=url, source_text=input_text)
        update_analysis_status(analysis_id, "done", result_job_id=job_id)
        if feed_item_id is not None:
            mark_feed_item_analyzed(feed_item_id, job_id)
    except Exception as e:
        try:
            update_analysis_status(analysis_id, "error", error=str(e))
        except Exception:
            app.logger.exception("Failed to persist error status for analysis %s", analysis_id)


@app.route("/analyze", methods=["POST"])
@limiter.limit("20 per hour")
@login_required
def run_analyze():
    user = current_user()
    if not API_KEY:
        return jsonify({"error": "No API key configured. Contact the administrator."}), 400

    url = normalize_url(request.form.get("url", "").strip())
    text = request.form.get("text", "").strip()
    force = request.form.get("force", "0")

    if not url and not text:
        return jsonify({"error": "Provide a URL or job description text."}), 400

    input_text = None
    scraped = False

    if text:
        # user provided text — use directly
        input_text = text
    elif url:
        # URL only — attempt scraping
        scraped_text, err_code, err_detail = scrape_url(url)
        if scraped_text:
            input_text = scraped_text
            scraped = True
        else:
            return jsonify({
                "scrape_error": True,
                "error_code": err_code,
                "error_detail": err_detail,
            })

    # deduplicate by URL if available, otherwise by text
    dedup_key = url or text
    if force != "1":
        duplicate = check_duplicate(user["id"], dedup_key)
        if duplicate:
            return jsonify({
                "duplicate": True,
                "previous": {
                    "id": duplicate["id"],
                    "company": duplicate["company"],
                    "role": duplicate["role"],
                    "verdict": duplicate["verdict"],
                    "analyzed_at": duplicate["analyzed_at"],
                }
            })

    source_label = url or (input_text or "")[:60].replace("\n", " ")
    analysis_id = create_analysis(user["id"], source_label)
    t = threading.Thread(
        target=_run_analysis_bg,
        args=(analysis_id, {k: user[k] for k in user.keys()}, input_text, url),
        daemon=True,
    )
    t.start()
    return jsonify({"analysis_id": analysis_id})


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
        "active_labels": get_active_analyses_labels(user["id"]),
    })


@app.route("/check_source", methods=["POST"])
@login_required
def check_source():
    user = current_user()
    url = normalize_url(request.form.get("url", "").strip())
    text = request.form.get("text", "").strip()
    key = url or text
    if not key:
        return jsonify({"exists": False}), 200
    duplicate = check_duplicate(user["id"], key)
    if duplicate:
        return jsonify({"exists": True, "analyzed_at": duplicate["analyzed_at"]})
    return jsonify({"exists": False})


@app.route("/reanalyze/<int:job_id>", methods=["POST"])
@limiter.limit("20 per hour")
@login_required
def reanalyze(job_id):
    user = current_user()
    if not API_KEY:
        return jsonify({"error": "No API key configured."}), 400
    job = get_job(job_id, user["id"])
    if not job:
        return jsonify({"error": "Analysis not found."}), 404
    source = (job["source_full"] or job["source"] or "").strip()
    if not source:
        return jsonify({"error": "No saved listing content — cannot re-analyze."}), 400
    # re-analyze: source is URL, source_full is text
    saved_url = job["job_url"] or (source if source.startswith("http") else "")
    saved_text = job["source_full"] or ""
    if saved_text and not saved_text.startswith("http"):
        input_text = saved_text
    elif saved_url:
        scraped_text, err_code, err_detail = scrape_url(saved_url)
        if scraped_text:
            input_text = scraped_text
        else:
            return jsonify({
                "scrape_error": True,
                "error_code": err_code,
                "error_detail": err_detail,
            })
    else:
        input_text = saved_text or source
    job_label = " · ".join(p for p in (job["company"], job["role"]) if p)
    source_label = f"Re-analysis: {job_label}" if job_label else (
        saved_url or (saved_text or "")[:60].replace("\n", " ") or "Re-analysis"
    )
    analysis_id = create_analysis(user["id"], source_label)
    t = threading.Thread(
        target=_run_analysis_bg,
        args=(analysis_id, {k: user[k] for k in user.keys()}, input_text, saved_url),
        daemon=True,
    )
    t.start()
    return jsonify({"analysis_id": analysis_id})


@app.route("/job/<int:job_id>/interview_prep", methods=["POST"])
@limiter.limit("5 per hour")
@login_required
def generate_interview_prep(job_id):
    user = current_user()
    if not API_KEY:
        return jsonify({"error": "No API key configured."}), 400
    job = get_job(job_id, user["id"])
    if not job:
        return jsonify({"error": "Analysis not found."}), 404
    eligible = (
        job["verdict"] == "worth_considering"
        or job["applied"]
        or job["interview_scheduled"]
        or job["offer_received"]
    )
    if not eligible:
        return jsonify({"error": "Interview prep not available for this job status."}), 400
    source = (job["source_full"] or "").strip()
    if not source or source.startswith("http"):
        return jsonify({"error": "No job description text saved — cannot generate interview prep."}), 400
    try:
        content = interview_prep(
            dict(user),
            source,
            job["company"] or "Unknown",
            job["role"] or "Unknown",
            API_KEY,
        )
        save_interview_prep(job_id, user["id"], content)
        return jsonify({"ok": True, "content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/job/<int:job_id>/cv_tailoring", methods=["POST"])
@limiter.limit("5 per hour")
@login_required
def generate_cv_tailoring(job_id):
    user = current_user()
    if not API_KEY:
        return jsonify({"error": "No API key configured."}), 400
    job = get_job(job_id, user["id"])
    if not job:
        return jsonify({"error": "Analysis not found."}), 404
    eligible = (
        job["verdict"] == "worth_considering"
        or job["applied"]
        or job["interview_scheduled"]
        or job["offer_received"]
    )
    if not eligible:
        return jsonify({"error": "CV tailoring not available for this job status."}), 400
    source = (job["source_full"] or "").strip()
    if not source or source.startswith("http"):
        return jsonify({"error": "No job description text saved — cannot generate CV tailoring."}), 400
    try:
        content = cv_tailoring(
            dict(user),
            source,
            job["company"] or "Unknown",
            job["role"] or "Unknown",
            API_KEY,
        )
        save_cv_tailoring(job_id, user["id"], content)
        return jsonify({"ok": True, "content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/job/<int:job_id>/verdict", methods=["POST"])
@login_required
def set_verdict(job_id):
    user = current_user()
    verdict = request.form.get("verdict", "").strip()
    if update_verdict(job_id, user["id"], verdict):
        # normalize for response — rejected_soft maps to rejected in DB
        actual = "rejected" if verdict == "rejected_soft" else verdict
        return jsonify({"ok": True, "verdict": actual})
    return jsonify({"error": "Invalid verdict or access denied."}), 400


@app.route("/job/<int:job_id>/url", methods=["POST"])
@login_required
def set_job_url(job_id):
    user = current_user()
    url = request.form.get("url", "").strip()
    if not url.startswith("http"):
        return jsonify({"error": "Please enter a valid URL (must start with http)."}), 400
    if update_job_url(job_id, user["id"], url):
        return jsonify({"ok": True})
    return jsonify({"error": "Access denied or record not found."}), 400


@app.route("/job/<int:job_id>/delete", methods=["POST"])
@login_required
def remove_job(job_id):
    user = current_user()
    if delete_job(job_id, user["id"]):
        return jsonify({"ok": True})
    return jsonify({"error": "Access denied or record not found."}), 400


@app.route("/job/<int:job_id>/applied", methods=["POST"])
@login_required
def set_applied(job_id):
    user = current_user()
    applied = request.form.get("applied", "0") == "1"
    if update_applied(job_id, user["id"], applied):
        return jsonify({"ok": True, "applied": applied})
    return jsonify({"error": "Access denied or record not found."}), 400


@app.route("/job/<int:job_id>/status", methods=["POST"])
@login_required
def set_job_status(job_id):
    user = current_user()
    status = request.form.get("status", "").strip()
    if update_job_status(job_id, user["id"], status):
        return jsonify({"ok": True})
    return jsonify({"error": "Invalid status or access denied."}), 400


@app.route("/job/<int:job_id>/company_rejected", methods=["POST"])
@login_required
def set_company_rejected(job_id):
    user = current_user()
    rejected = request.form.get("rejected", "0") == "1"
    if update_company_rejected(job_id, user["id"], rejected):
        return jsonify({"ok": True, "rejected": rejected})
    return jsonify({"error": "Access denied or record not found."}), 400


@app.route("/job/<int:job_id>/notes", methods=["POST"])
@login_required
def set_job_notes(job_id):
    user = current_user()
    notes = request.form.get("notes", "")[:10000]
    ok = update_job_notes(job_id, user["id"], notes)
    return jsonify({"ok": ok})


def _inline_md(s: str) -> str:
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    return s


def _md_to_html(text: str, skip_h1: bool = False) -> str:
    lines = text.split("\n")
    out = []
    in_ul = False
    past_preamble = not skip_h1
    for line in lines:
        line_esc = _html.escape(line)
        if not past_preamble:
            if re.match(r"^-{3,}$", line_esc.strip()):
                past_preamble = True
            continue
        if line_esc.startswith("## "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h2>{_inline_md(line_esc[3:])}</h2>")
        elif line_esc.startswith("# "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h1>{_inline_md(line_esc[2:])}</h1>")
        elif re.match(r"^-{3,}$", line_esc.strip()):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append("<hr>")
        elif line_esc.startswith("- "):
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{_inline_md(line_esc[2:])}</li>")
        elif line_esc.strip() == "":
            if in_ul: out.append("</ul>"); in_ul = False
            out.append("")
        else:
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<p>{_inline_md(line_esc)}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


@app.route("/changelog")
def changelog():
    md_path = pathlib.Path(__file__).parent / "CHANGELOG.md"
    md_text = md_path.read_text(encoding="utf-8") if md_path.exists() else "CHANGELOG.md not found"
    return render_template("changelog.html", content=_md_to_html(md_text))


@app.route("/about")
def about():
    md_path = pathlib.Path(__file__).parent / "CHANGELOG.md"
    md_text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    return render_template("about.html", changelog_html=_md_to_html(md_text, skip_h1=True))


@app.route("/history_latest")
@login_required
def history_latest():
    user = current_user()
    jobs = get_jobs(user["id"], limit=1)
    if jobs:
        return jsonify({"id": jobs[0]["id"]})
    return jsonify({"id": None})


@app.route("/history")
@login_required
def history():
    return redirect(url_for("dashboard"), 301)


@app.route("/job/<int:job_id>")
@login_required
def job_detail(job_id):
    return redirect(url_for("dashboard") + f"?job={job_id}", 301)


@app.route("/job/<int:job_id>/partial")
@login_required
def job_partial(job_id):
    user = current_user()
    job = get_job(job_id, user["id"])
    if not job:
        return "", 404
    raw = {}
    try:
        raw = _json.loads(job["raw_json"] or "{}")
    except Exception:
        pass
    prep_content = get_interview_prep(job_id, user["id"])
    tailoring_content = get_cv_tailoring(job_id, user["id"])
    return render_template("job_partial.html", job=job, raw=raw, prep_content=prep_content, tailoring_content=tailoring_content)


def _parse_settings_list(text):
    entries = set()
    for line in text.splitlines():
        entry = line.strip().lstrip("-").strip().lower()
        if entry:
            entries.add(entry)
    return entries


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user = current_user()
    if request.method == "POST":
        section = request.form.get("section", "")

        if section:
            if section == "cv":
                cv = request.form.get("cv", "").strip()
                update_user_profile(user["id"], cv, user["zero_list"] or "", user["criteria"] or "", user["yellow_list"] or "")
                return jsonify({"ok": True})

            if section == "zero_list":
                zero_list = request.form.get("zero_list", "")
                conflicts = _parse_settings_list(zero_list) & _parse_settings_list(user["yellow_list"] or "")
                if conflicts:
                    return jsonify({"ok": False, "error": f"Conflict with Yellow List: {', '.join(sorted(conflicts))}"})
                update_user_profile(user["id"], user["cv"] or "", zero_list, user["criteria"] or "", user["yellow_list"] or "")
                return jsonify({"ok": True})

            if section == "yellow_list":
                yellow_list = request.form.get("yellow_list", "")
                conflicts = _parse_settings_list(user["zero_list"] or "") & _parse_settings_list(yellow_list)
                if conflicts:
                    return jsonify({"ok": False, "error": f"Conflict with Zero List: {', '.join(sorted(conflicts))}"})
                update_user_profile(user["id"], user["cv"] or "", user["zero_list"] or "", user["criteria"] or "", yellow_list)
                return jsonify({"ok": True})

            if section == "criteria":
                criteria = request.form.get("criteria", "").strip()
                update_user_profile(user["id"], user["cv"] or "", user["zero_list"] or "", criteria, user["yellow_list"] or "")
                return jsonify({"ok": True})

            return jsonify({"ok": False, "error": "Unknown section"}), 400

        # Full save (non-JS fallback)
        cv = request.form.get("cv", "")
        zero_list = request.form.get("zero_list", "")
        yellow_list = request.form.get("yellow_list", "")
        criteria = request.form.get("criteria", "")
        conflicts = _parse_settings_list(zero_list) & _parse_settings_list(yellow_list)
        if conflicts:
            flash(
                f"Conflict: the following entries appear in both Zero List and Yellow List — {', '.join(sorted(conflicts))}. "
                f"Remove them from one list before saving.",
                "error",
            )
            return render_template("settings.html", user=user, feeds=get_feeds(user["id"]))
        update_user_profile(user["id"], cv, zero_list, criteria, yellow_list)
        flash("Profile saved.")
        return redirect(url_for("settings"))
    return render_template("settings.html", user=current_user(), feeds=get_feeds(current_user()["id"]))


@app.route("/settings/password", methods=["POST"])
@login_required
def change_password():
    user = current_user()
    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    new_pw2 = request.form.get("new_password2", "")

    def _settings_error(msg):
        flash(msg)
        return render_template("settings.html", user=user), 200

    if not current_pw or not verify_password(current_pw, user["password_hash"]):
        return _settings_error("Current password is incorrect.")
    if new_pw != new_pw2:
        return _settings_error("New passwords do not match.")
    if len(new_pw) < 10:
        return _settings_error("New password must be at least 10 characters.")

    update_password(user["id"], new_pw)
    flash("Password updated.")
    return redirect(url_for("settings"))


@app.route("/export/csv")
@login_required
def export():
    user = current_user()
    csv_data = export_csv(user["id"])
    resp = make_response(csv_data)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = \
        f"attachment; filename=jobs_{user['username']}.csv"
    return resp




@app.route("/statistics")
@login_required
def statistics():
    user = current_user()
    data = get_statistics(user["id"])
    return render_template("statistics.html", user=user, data=data)

@app.route("/discover")
@login_required
def discover():
    user = current_user()
    user_id = user["id"]
    feeds = get_feeds(user_id)

    if feeds:
        fetch_errors = []
        for feed in feeds:
            if not feed["active"]:
                continue
            last = feed["last_fetched_at"]
            if last:
                try:
                    if datetime.now() - datetime.fromisoformat(last) < timedelta(hours=1):
                        continue
                except Exception:
                    pass
            try:
                items = fetch_feed(dict(feed))
                save_feed_items(feed["id"], user_id, items, feed["keywords"] or "")
                update_feed_fetched(feed["id"])
            except Exception as e:
                fetch_errors.append(f"{feed['label']}: {e}")
        if fetch_errors:
            flash("Some feeds failed to fetch — " + "; ".join(fetch_errors), "error")

    feed_items = get_feed_items(user_id, analyzed=False)

    zero_entries = [
        e.strip().lstrip("-").strip().lower()
        for e in (user["zero_list"] or "").splitlines()
        if e.strip().lstrip("-").strip()
    ]

    normal = []
    filtered = []
    for item in feed_items:
        company_lc = (item["company"] or "").lower()
        title_lc = (item["title"] or "").lower()
        hit = any(z and (z in company_lc or z in title_lc) for z in zero_entries)
        (filtered if hit else normal).append(item)

    return render_template("discover.html", items=normal, filtered=filtered, feeds=feeds)


@app.route("/feeds/refresh", methods=["POST"])
@login_required
def feeds_refresh():
    user = current_user()
    user_id = user["id"]
    count = 0
    errors = []
    for feed in get_feeds(user_id):
        if not feed["active"]:
            continue
        try:
            items = fetch_feed(dict(feed))
            count += save_feed_items(feed["id"], user_id, items, feed["keywords"] or "")
            update_feed_fetched(feed["id"])
        except Exception as e:
            errors.append(feed["label"])
    return jsonify({"new": count, "errors": errors})


@app.route("/feeds/add", methods=["POST"])
@login_required
def feeds_add():
    user = current_user()
    feed_type = request.form.get("type", "").strip()
    source = request.form.get("source", "").strip()
    label = request.form.get("label", "").strip()
    keywords = request.form.get("keywords", "").strip()

    if feed_type not in ("remoteok", "lever", "greenhouse", "rss"):
        flash("Invalid feed type.", "error")
        return redirect(url_for("settings") + "#feeds")
    if not source:
        flash("Source is required.", "error")
        return redirect(url_for("settings") + "#feeds")
    if feed_type in ("lever", "greenhouse") and not re.fullmatch(r"[a-z0-9-]+", source):
        board_url = "jobs.lever.co/stripe" if feed_type == "lever" else "boards.greenhouse.io/stripe"
        flash(
            f"\"{source}\" doesn't look like a company name from a {feed_type.capitalize()} job board URL "
            f"(e.g. \"stripe\" from {board_url}). "
            f"{feed_type.capitalize()} feeds pull listings from one company at a time, not a search term.",
            "error",
        )
        return redirect(url_for("settings") + "#feeds")
    if not label:
        label = f"{feed_type.capitalize()} — {source}"

    add_feed(user["id"], feed_type, source, label, keywords)
    flash("Feed added.")
    return redirect(url_for("settings") + "#feeds")


@app.route("/feeds/<int:feed_id>/delete", methods=["POST"])
@login_required
def feeds_delete(feed_id):
    user = current_user()
    delete_feed(feed_id, user["id"])
    flash("Feed removed.")
    return redirect(url_for("settings") + "#feeds")


@app.route("/discover/<int:item_id>/analyze", methods=["POST"])
@limiter.limit("20 per hour")
@login_required
def discover_analyze(item_id):
    user = current_user()
    if not API_KEY:
        return jsonify({"error": "No API key configured."}), 400

    item = get_feed_item(item_id, user["id"])
    if not item:
        return jsonify({"error": "Item not found."}), 404

    item = dict(item)
    url = item["url"]
    text = item.get("description", "") or ""

    dedup_key = url or text
    duplicate = check_duplicate(user["id"], dedup_key)
    if duplicate:
        mark_feed_item_analyzed(item_id, duplicate["id"])
        return jsonify({
            "duplicate": True,
            "previous": {
                "id": duplicate["id"],
                "company": duplicate["company"],
                "role": duplicate["role"],
                "verdict": duplicate["verdict"],
                "analyzed_at": duplicate["analyzed_at"],
            },
        })

    input_text = text if text else url
    source_label = url or (text[:60].replace("\n", " "))
    analysis_id = create_analysis(user["id"], source_label)
    t = threading.Thread(
        target=_run_analysis_bg,
        args=(analysis_id, {k: user[k] for k in user.keys()}, input_text, url, item_id),
        daemon=True,
    )
    t.start()
    return jsonify({"analysis_id": analysis_id})


# ── startup ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    if not os.environ.get("NO_BROWSER"):
        def open_browser():
            time.sleep(1.2)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=open_browser, daemon=True).start()

    app.run(host="0.0.0.0", port=port, debug=debug)