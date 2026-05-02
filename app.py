import os
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
from database import (
    init_db, get_user, create_user, get_user_by_id,
    update_user_profile, save_job, get_jobs, get_job,
    export_csv, user_count, check_duplicate, update_verdict, update_job_url, delete_job, update_applied,
    update_company_rejected, update_job_status, verify_password, get_analytics
)
from analyzer import analyze
from scraper import fetch as scrape_url, normalize_url

app: Flask = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))
app.config['TEMPLATES_AUTO_RELOAD'] = True

API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")


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
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_user(username)
        if user and verify_password(password, user["password_hash"]):
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
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
    if invite_token and token_from_url == invite_token:
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
        elif len(password) < 6:
            flash("Password must be at least 6 characters.")
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


@app.route("/analyze", methods=["POST"])
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

    try:
        result = analyze(user, input_text, "text", API_KEY)
        save_job(user["id"], result, source_url=url, source_text=input_text)
        return jsonify({"ok": True, "result": result, "scraped": scraped,
                        "source_url": url, "source_text": input_text})
    except sqlite3.IntegrityError as e:
        return jsonify({"error": f"Database integrity error: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    try:
        result = analyze(user, input_text, "text", API_KEY)
        save_job(user["id"], result, source_url=saved_url, source_text=input_text)
        # return the new entry's id
        new_job = get_jobs(user["id"], limit=1)[0]
        return jsonify({"ok": True, "new_job_id": new_job["id"]})
    except sqlite3.IntegrityError as e:
        return jsonify({"error": f"Database integrity error: {e}"}), 500
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


@app.route("/changelog")
def changelog():
    md_path = pathlib.Path(__file__).parent / "CHANGELOG.md"
    md_text = md_path.read_text(encoding="utf-8") if md_path.exists() else "CHANGELOG.md not found"

    def md_to_html(text):
        lines = text.split("\n")
        out = []
        in_ul = False
        for line in lines:
            # escape HTML
            line_esc = _html.escape(line)
            # h2
            if line_esc.startswith("## "):
                if in_ul: out.append("</ul>"); in_ul = False
                out.append(f"<h2>{line_esc[3:]}</h2>")
            # h1
            elif line_esc.startswith("# "):
                if in_ul: out.append("</ul>"); in_ul = False
                out.append(f"<h1>{line_esc[2:]}</h1>")
            # hr
            elif re.match(r"^-{3,}$", line_esc.strip()):
                if in_ul: out.append("</ul>"); in_ul = False
                out.append("<hr>")
            # li
            elif line_esc.startswith("- "):
                if not in_ul: out.append("<ul>"); in_ul = True
                out.append(f"<li>{line_esc[2:]}</li>")
            # empty
            elif line_esc.strip() == "":
                if in_ul: out.append("</ul>"); in_ul = False
                out.append("")
            # p
            else:
                if in_ul: out.append("</ul>"); in_ul = False
                out.append(f"<p>{line_esc}</p>")
        if in_ul:
            out.append("</ul>")
        return "\n".join(out)

    return render_template("changelog.html", content=md_to_html(md_text))


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




@app.route("/analytics")
@login_required
def analytics():
    user = current_user()
    data = get_analytics(user["id"])
    return render_template("analytics.html", user=user, data=data)

# ── startup ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"

    if not os.environ.get("NO_BROWSER"):
        def open_browser():
            time.sleep(1.2)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=open_browser, daemon=True).start()

    app.run(host="0.0.0.0", port=port, debug=debug)