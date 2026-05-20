import os
import secrets
import functools
import pathlib
import re
import sqlite3
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
    update_company_rejected, update_job_status, verify_password, get_statistics,
    create_analysis, update_analysis_status, get_analysis,
)
from analyzer import analyze
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

from datetime import timedelta
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

def current_user() -> Optional[sqlite3.Row]:
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
        if not session.get("user_id"):
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
        HTML szablon logowania
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
        HTML szablon rejestracji
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
        HTML szablon dashboarda
    """
    user = current_user()
    jobs = get_jobs(user["id"], limit=50)
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
) -> None:
    try:
        update_analysis_status(analysis_id, "running")
        result = analyze(user, input_text, "text", API_KEY, MODEL)
        job_id = save_job(user["id"], result, source_url=url, source_text=input_text)
        update_analysis_status(analysis_id, "done", result_job_id=job_id)
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
    source_label = saved_url or (saved_text or "")[:60].replace("\n", " ") or "Re-analysis"
    analysis_id = create_analysis(user["id"], source_label)
    t = threading.Thread(
        target=_run_analysis_bg,
        args=(analysis_id, {k: user[k] for k in user.keys()}, input_text, saved_url),
        daemon=True,
    )
    t.start()
    return jsonify({"analysis_id": analysis_id})


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
            out.append(f"<h2>{line_esc[3:]}</h2>")
        elif line_esc.startswith("# "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h1>{line_esc[2:]}</h1>")
        elif re.match(r"^-{3,}$", line_esc.strip()):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append("<hr>")
        elif line_esc.startswith("- "):
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{line_esc[2:]}</li>")
        elif line_esc.strip() == "":
            if in_ul: out.append("</ul>"); in_ul = False
            out.append("")
        else:
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<p>{line_esc}</p>")
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
    user = current_user()
    jobs = get_jobs(user["id"], limit=200)
    return render_template("history.html", user=user, jobs=jobs)


@app.route("/job/<int:job_id>")
@login_required
def job_detail(job_id):
    user = current_user()
    job = get_job(job_id, user["id"])
    if not job:
        flash("Analysis not found.")
        return redirect(url_for("history"))
    raw = {}
    try:
        raw = _json.loads(job["raw_json"] or "{}")
    except Exception:
        pass
    return render_template("job_detail.html", user=user, job=job, raw=raw)


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
    return render_template("job_partial.html", job=job, raw=raw)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user = current_user()
    if request.method == "POST":
        cv = request.form.get("cv", "")
        zero_list = request.form.get("zero_list", "")
        yellow_list = request.form.get("yellow_list", "")
        criteria = request.form.get("criteria", "")
        update_user_profile(user["id"], cv, zero_list, criteria, yellow_list)
        flash("Profile saved.")
        return redirect(url_for("settings"))
    return render_template("settings.html", user=current_user())


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

    if not verify_password(current_pw, user["password_hash"]):
        return _settings_error("Current password is incorrect.")
    if new_pw != new_pw2:
        return _settings_error("New passwords do not match.")
    if len(new_pw) < 8:
        return _settings_error("New password must be at least 8 characters.")

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