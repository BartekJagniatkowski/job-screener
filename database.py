import sqlite3
from typing import Optional
import hashlib
import secrets
import json as _json
import datetime
import uuid
import csv
import io
from pathlib import Path
from analyzer import AnalysisResult

# Row type for sqlite3.Row
Row = sqlite3.Row

DB_PATH = Path(__file__).parent / "data" / "screener.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    cv TEXT DEFAULT '',
    zero_list TEXT DEFAULT '',
    criteria TEXT DEFAULT '',
    yellow_list TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    analyzed_at DATE DEFAULT (date('now')),
    company TEXT,
    role TEXT,
    verdict TEXT,
    verdict_confirmed INTEGER DEFAULT 0,
    zero_list_hit INTEGER DEFAULT 0,
    zero_list_reason TEXT,
    triage_status TEXT,
    product_status TEXT,
    business_status TEXT,
    reputation_status TEXT,
    values_status TEXT,
    fit_status TEXT,
    verdict_summary TEXT,
    triage_findings TEXT,
    product_findings TEXT,
    business_findings TEXT,
    reputation_findings TEXT,
    values_findings TEXT,
    fit_strengths TEXT,
    fit_gaps TEXT,
    fit_improve TEXT,
    gut_feeling TEXT,
    source TEXT,
    raw_json TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    source_label TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    result_job_id INTEGER,
    error TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (result_job_id) REFERENCES jobs(id)
);
"""

DEFAULT_ZERO_LIST = """- Alcohol, tobacco, gambling, sex industry
- Weapons and defense (military component suppliers, AI for defense, defense tech funds)
- Big pharma, insurance, finance (banks, fintechs, trading)
- Marketing and e-commerce as core business (driving uncontrolled consumption)

Note: connection through a direct investor/co-founder actively managing a company from the above categories = red flag (not automatic rejection). Connection through an investor's investor = too distant.""".strip()

DEFAULT_CRITERIA = """Looking for roles at the intersection of product discovery, strategy, and the human dimension of products.
Prefer: healthcare, science, social impact, AI ethics, edtech.
Avoid: execution PM without discovery component, growth PM (A/B testing as core), technical PM focused on tool integrations.
Cultural red flag: quarterly layoff cycles, toxic leadership (Glassdoor < 3.5 with a clear downward trend).""".strip()


def get_conn() -> sqlite3.Connection:
    """
    Open a database connection in WAL mode.

    Returns:
        SQLite connection with row_factory set to Row
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """
    Initialize the database and run migrations.

    Idempotent — safe to call multiple times without risk of duplicate columns or data.
    Handles migration from Polish column names to English,
    as well as backfilling values for existing records.

    Migrations include:
    - Adding new columns (idempotent ALTER TABLE ADD COLUMN)
    - Renaming columns from Polish to English names
    - Migrating verdict and status values from Polish to English
    - Backfilling verdict_confirmed for existing records
    """
    with get_conn() as conn:  # type: ignore
        conn.executescript(SCHEMA)

        # Add columns that were introduced after the initial schema
        for col, tbl in [
            ("source_full TEXT", "jobs"),
            ("source_hash TEXT", "jobs"),
            ("reasoning TEXT", "jobs"),
            ("job_url TEXT", "jobs"),
            ("applied INTEGER DEFAULT 0", "jobs"),
            ("applied_at DATE", "jobs"),
            ("verdict_confirmed INTEGER DEFAULT 0", "jobs"),
            ("company_rejected INTEGER DEFAULT 0", "jobs"),
            ("company_rejected_at DATE", "jobs"),
            ("role_archetype TEXT", "jobs"),
            ("fit_score REAL", "jobs"),
            ("notes TEXT DEFAULT ''", "jobs"),
            ("interview_scheduled INTEGER DEFAULT 0", "jobs"),
            ("interview_at DATE", "jobs"),
            ("offer_received INTEGER DEFAULT 0", "jobs"),
            ("offer_at DATE", "jobs"),
            ("interview_prep TEXT", "jobs"),
            ("cv_tailoring TEXT", "jobs"),
            # kept for migration chain: old DBs may not have this yet before rename
            ("lista_zolta TEXT DEFAULT ''", "users"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col}")
            except Exception:
                pass

        # Rename Polish column names to English (idempotent — fails silently if already renamed)
        for old, new in [
            ("firma", "company"),
            ("rola", "role"),
            ("werdykt", "verdict"),
            ("lista_zero_hit", "zero_list_hit"),
            ("lista_zero_reason", "zero_list_reason"),
            ("produktowa_status", "product_status"),
            ("biznesowa_status", "business_status"),
            ("reputacyjna_status", "reputation_status"),
            ("wartosci_status", "values_status"),
            ("dopasowanie_status", "fit_status"),
            ("produktowa_findings", "product_findings"),
            ("biznesowa_findings", "business_findings"),
            ("reputacyjna_findings", "reputation_findings"),
            ("wartosci_findings", "values_findings"),
            ("dopasowanie_mocne", "fit_strengths"),
            ("dopasowanie_luki", "fit_gaps"),
            ("dopasowanie_wzmocnij", "fit_improve"),
        ]:
            try:
                conn.execute(f"ALTER TABLE jobs RENAME COLUMN {old} TO {new}")
            except Exception:
                pass

        for old, new in [
            ("lista_zero", "zero_list"),
            ("lista_zolta", "yellow_list"),
            ("kryteria", "criteria"),
        ]:
            try:
                conn.execute(f"ALTER TABLE users RENAME COLUMN {old} TO {new}")
            except Exception:
                pass

        # Migrate verdict values from Polish to English
        conn.execute("UPDATE jobs SET verdict = 'rejected' WHERE verdict = 'odrzucona'")
        conn.execute("UPDATE jobs SET verdict = 'warning' WHERE verdict = 'uwaga'")
        conn.execute("UPDATE jobs SET verdict = 'worth_considering' WHERE verdict = 'warta_rozwazenia'")

        # Migrate layer status values from Polish to English
        for col in ["triage_status", "product_status", "business_status",
                    "reputation_status", "values_status", "fit_status"]:
            try:
                conn.execute(f"UPDATE jobs SET {col} = 'warning' WHERE {col} = 'uwaga'")
                conn.execute(f"UPDATE jobs SET {col} = 'flag' WHERE {col} = 'flaga'")
            except Exception:
                pass

        # Backfill verdict_confirmed for existing records:
        # zero_list_hit = true → auto-confirmed; all other rejected = unconfirmed (stays 0)
        try:
            conn.execute(
                "UPDATE jobs SET verdict_confirmed = 1 WHERE verdict = 'rejected' AND zero_list_hit = 1"
            )
        except Exception:
            pass

        # Add indexes for frequently queried columns
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_source_hash ON jobs(source_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_analyzed_at ON jobs(analyzed_at)")
        except Exception:
            pass

        try:
            conn.execute(
                """UPDATE analyses SET status='error', error='Server restarted'
                   WHERE status IN ('pending', 'running')
                   AND started_at < datetime('now', '-5 minutes')"""
            )
        except Exception:
            pass  # analyses table may not exist in very old DBs yet


def hash_password(password: str) -> str:
    """
    Hash a password with SHA-256 and a random salt.

    Args:
        password: Password to hash

    Returns:
        String in format "salt:hash" where salt is 16 hex characters
    """
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{h}"


def verify_password(password: str, stored: str) -> bool:
    """
    Check whether a password matches a stored salted hash.

    Args:
        password: Provided password
        stored: Stored salted hash (format: "salt:hash")

    Returns:
        True if the passwords match, False otherwise
    """
    try:
        salt, h = stored.split(":", 1)
        computed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return secrets.compare_digest(computed, h)
    except Exception:
        return False


def create_user(username: str, password: str) -> bool:
    """
    Create a new user account.

    Args:
        username: Username (stored in lowercase)
        password: Password to hash

    Returns:
        True if the account was created, False if the username is already taken
    """
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, zero_list, criteria) VALUES (?,?,?,?)",
                (username.lower().strip(), hash_password(password),
                 DEFAULT_ZERO_LIST, DEFAULT_CRITERIA)
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_user(username: str) -> Optional[sqlite3.Row]:
    """
    Fetch a user by username.

    Args:
        username: Username

    Returns:
        sqlite3.Row with user data, or None if not found
    """
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username=?",
            (username.lower().strip(),)
        ).fetchone()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    """
    Fetch a user by ID.

    Args:
        user_id: User ID

    Returns:
        sqlite3.Row with user data, or None if not found
    """
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def update_user_profile(user_id: int, cv: str, zero_list: str, criteria: str, yellow_list: str = "") -> None:
    """
    Update a user's profile.

    Args:
        user_id: User ID
        cv: CV content
        zero_list: Zero list content
        criteria: Additional criteria
        yellow_list: Yellow list content (optional, empty by default)
    """
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET cv=?, zero_list=?, criteria=?, yellow_list=? WHERE id=?",
            (cv.strip(), zero_list.strip(), criteria.strip(), yellow_list.strip(), user_id)
        )


def update_password(user_id: int, new_password: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(new_password), user_id),
        )


def compute_hash(text: str) -> str:
    """
    Compute a SHA-256 hash of the given text.

    Args:
        text: Text to hash (URL or listing content)

    Returns:
        64-hex-character SHA-256 hash
    """
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()


def check_duplicate(user_id: int, source: str) -> Optional[sqlite3.Row]:
    """
    Check whether an analysis already exists for the same source.

    source can be a URL or content text. Hash is computed after stripping whitespace.

    Args:
        user_id: User ID
        source: URL or listing content

    Returns:
        Record from the database if a duplicate exists, None otherwise
    """
    clean_source = source.strip() if source else ""
    h = compute_hash(clean_source)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE user_id=? AND source_hash=? ORDER BY id DESC LIMIT 1",
            (user_id, h)
        ).fetchone()
    return dict(row) if row else None


def create_analysis(user_id: int, source_label: str) -> str:
    analysis_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analyses (id, user_id, status, source_label) VALUES (?, ?, 'pending', ?)",
            (analysis_id, user_id, source_label),
        )
    return analysis_id


def update_analysis_status(
    analysis_id: str,
    status: str,
    result_job_id: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    with get_conn() as conn:
        if status == "done":
            cur = conn.execute(
                "UPDATE analyses SET status=?, result_job_id=?, finished_at=datetime('now') WHERE id=?",
                (status, result_job_id, analysis_id),
            )
        elif status == "error":
            cur = conn.execute(
                "UPDATE analyses SET status=?, error=?, finished_at=datetime('now') WHERE id=?",
                (status, error, analysis_id),
            )
        else:
            cur = conn.execute(
                "UPDATE analyses SET status=? WHERE id=?",
                (status, analysis_id),
            )
        if cur.rowcount == 0:
            raise ValueError(f"analysis_id not found: {analysis_id}")


def count_active_analyses(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM analyses WHERE user_id=? AND status IN ('pending', 'running')",
            (user_id,),
        ).fetchone()
        return row[0] if row else 0


def get_active_analyses_labels(user_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT source_label FROM analyses WHERE user_id=? AND status IN ('pending', 'running') ORDER BY started_at",
            (user_id,),
        ).fetchall()
        return [r["source_label"] or "" for r in rows]


def get_analysis(analysis_id: str, user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """SELECT a.*, j.company, j.role, j.verdict
               FROM analyses a
               LEFT JOIN jobs j ON j.id = a.result_job_id
               WHERE a.id = ? AND a.user_id = ?""",
            (analysis_id, user_id),
        ).fetchone()


def save_job(
    user_id: int,
    result: AnalysisResult,
    source_url: str = "",
    source_text: str = ""
) -> int:
    """
    Save an analysis result to the database.

    source_url — job listing URL (stored as job_url and used for deduplication)
    source_text — listing content (scraped or pasted by the user)

    Args:
        user_id: User ID
        result: Analysis result from JSON
        source_url: Job listing URL (or empty)
        source_text: Job listing content (scraped or pasted)
    """
    import json as _json
    d = result.get
    l = (result.get("layers") or {})
    fit = (result.get("fit") or {})

    # deduplication: prefer URL if available, otherwise use text
    dedup_source = (source_url or source_text or "").strip()
    # source_full = full listing text that was analyzed
    full_text = source_text.strip() if source_text else source_url.strip()
    # source = short identifier for display
    source_display = (source_url or source_text or "")[:300]

    zero_list_hit = 1 if d("zero_list_hit") else 0
    # auto-confirm when rejected by zero list; manual confirmation required otherwise
    verdict_confirmed = 1 if (zero_list_hit and d("verdict") == "rejected") else 0

    with get_conn() as conn:
        try:
            conn.execute("""
                INSERT INTO jobs (
                    user_id, company, role, verdict, verdict_confirmed, zero_list_hit, zero_list_reason,
                    triage_status, product_status, business_status,
                    reputation_status, values_status, fit_status,
                    verdict_summary, triage_findings, product_findings,
                    business_findings, reputation_findings, values_findings,
                    fit_strengths, fit_gaps, fit_improve,
                    gut_feeling, source, source_full, source_hash, reasoning, job_url,
                    role_archetype, fit_score, raw_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                user_id,
                d("company_name", ""),
                d("role_title", ""),
                d("verdict", ""),
                verdict_confirmed,
                zero_list_hit,
                d("zero_list_reason", ""),
                (result.get("triage") or {}).get("status", ""),
                l.get("product", {}).get("status", ""),
                l.get("business", {}).get("status", ""),
                l.get("reputation", {}).get("status", ""),
                l.get("values", {}).get("status", ""),
                fit.get("status", ""),
                d("verdict_summary", ""),
                (result.get("triage") or {}).get("findings", ""),
                l.get("product", {}).get("findings", ""),
                l.get("business", {}).get("findings", ""),
                l.get("reputation", {}).get("findings", ""),
                l.get("values", {}).get("findings", ""),
                fit.get("strengths", ""),
                fit.get("gaps", ""),
                fit.get("improve", ""),
                d("gut_feeling", ""),
                source_display,
                full_text,
                compute_hash(dedup_source),
                d("_reasoning", ""),
                source_url.strip() or "",
                (result.get("triage") or {}).get("role_archetype", None),
                fit.get("score", None),
                _json.dumps(result, ensure_ascii=False),
            ))
        except sqlite3.IntegrityError as e:
            raise Exception(f"Database integrity error: {e}")
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_jobs(user_id: int, limit: Optional[int] = None) -> list[dict]:
    """
    Fetch the most recent n records from the database.

    Args:
        user_id: User ID
        limit: Maximum number of records (None = all records)

    Returns:
        List of dictionaries with data from the database
    """
    with get_conn() as conn:
        if limit is None:
            return conn.execute(
                "SELECT * FROM jobs WHERE user_id=? ORDER BY id DESC",
                (user_id,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def get_job(job_id: int, user_id: int) -> Optional[sqlite3.Row]:
    """
    Fetch a specific record from the database.

    Args:
        job_id: Database record ID
        user_id: User ID

    Returns:
        sqlite3.Row with data, or None if not found
    """
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE id=? AND user_id=?",
            (job_id, user_id)
        ).fetchone()


def update_verdict(job_id: int, user_id: int, verdict: str) -> bool:
    """
    Manually update the verdict.

    Args:
        job_id: Database record ID
        user_id: User ID
        verdict: New verdict (rejected, warning, worth_considering)

    Returns:
        True if the record was updated, False otherwise

    Notes:
        'rejected_soft' sets verdict='rejected', verdict_confirmed=0
        (AI opinion, unconfirmed). All other values set
        verdict_confirmed=1 (confirmed by the user).
    """
    confirmed = True
    if verdict == "rejected_soft":
        verdict = "rejected"
        confirmed = False
    allowed = {"rejected", "warning", "worth_considering"}
    if verdict not in allowed:
        return False
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET verdict=?, verdict_confirmed=? WHERE id=? AND user_id=?",
            (verdict, 1 if confirmed else 0, job_id, user_id)
        )
        return cur.rowcount > 0


def update_job_url(job_id: int, user_id: int, url: str) -> bool:
    """
    Manually attach a URL to a job record.

    Args:
        job_id: Database record ID
        user_id: User ID
        url: URL to save

    Returns:
        True if the record was updated
    """
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET job_url=? WHERE id=? AND user_id=?",
            (url.strip(), job_id, user_id)
        )
        return cur.rowcount > 0


def delete_job(job_id: int, user_id: int) -> bool:
    """
    Delete a job record from the database.

    Args:
        job_id: Database record ID
        user_id: User ID

    Returns:
        True if the record existed and belonged to the user, False otherwise
    """
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM jobs WHERE id=? AND user_id=?",
            (job_id, user_id)
        )
        return cur.rowcount > 0


def update_applied(job_id: int, user_id: int, applied: bool) -> bool:
    """
    Set or clear the application-sent status.

    Args:
        job_id: Database record ID
        user_id: User ID
        applied: True if the application was sent

    Returns:
        True if the record was updated
    """
    date = datetime.date.today().isoformat() if applied else None
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET applied=?, applied_at=? WHERE id=? AND user_id=?",
            (1 if applied else 0, date, job_id, user_id)
        )
        return cur.rowcount > 0


def update_company_rejected(job_id: int, user_id: int, rejected: bool) -> bool:
    """
    Set or clear the company-rejected status.

    Args:
        job_id: Database record ID
        user_id: User ID
        rejected: True if the company rejected the application

    Returns:
        True if the record was updated
    """
    date = datetime.date.today().isoformat() if rejected else None
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET company_rejected=?, company_rejected_at=? WHERE id=? AND user_id=?",
            (1 if rejected else 0, date, job_id, user_id)
        )
        return cur.rowcount > 0


def update_job_notes(job_id: int, user_id: int, notes: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET notes=? WHERE id=? AND user_id=?",
            (notes.strip(), job_id, user_id),
        )
        return cur.rowcount > 0


def save_interview_prep(job_id: int, user_id: int, content: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET interview_prep=? WHERE id=? AND user_id=?",
            (content.strip(), job_id, user_id),
        )
        return cur.rowcount > 0


def get_interview_prep(job_id: int, user_id: int) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT interview_prep FROM jobs WHERE id=? AND user_id=?",
            (job_id, user_id),
        ).fetchone()
    return row["interview_prep"] if row and row["interview_prep"] else None


def save_cv_tailoring(job_id: int, user_id: int, content: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET cv_tailoring=? WHERE id=? AND user_id=?",
            (content.strip(), job_id, user_id),
        )
        return cur.rowcount > 0


def get_cv_tailoring(job_id: int, user_id: int) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT cv_tailoring FROM jobs WHERE id=? AND user_id=?",
            (job_id, user_id),
        ).fetchone()
    return row["cv_tailoring"] if row and row["cv_tailoring"] else None


def update_job_status(job_id: int, user_id: int, status: str) -> bool:
    """
    Unified status update from the dropdown.

    Verdict values (worth_considering, warning, rejected_soft, rejected):
      set verdict + verdict_confirmed, clear applied and company_rejected.
    Application values (applied, company_rejected):
      set application fields, leave verdict unchanged.

    Args:
        job_id: Database record ID
        user_id: User ID
        status: New status (worth_considering, warning, rejected_soft, rejected,
                applied, company_rejected)

    Returns:
        True if the record was updated
    """
    today = datetime.date.today().isoformat()

    if status == "applied":
        sql = (
            "UPDATE jobs SET applied=1, applied_at=?, company_rejected=0, company_rejected_at=NULL"
            " WHERE id=? AND user_id=?"
        )
        params = (today, job_id, user_id)
    elif status == "company_rejected":
        # also ensure applied=1 (can't be rejected without having applied)
        sql = (
            "UPDATE jobs SET company_rejected=1, company_rejected_at=?,"
            " applied=1, applied_at=COALESCE(applied_at, ?)"
            " WHERE id=? AND user_id=?"
        )
        params = (today, today, job_id, user_id)
    elif status == "rejected_soft":
        sql = (
            "UPDATE jobs SET verdict='rejected', verdict_confirmed=0,"
            " applied=0, applied_at=NULL, company_rejected=0, company_rejected_at=NULL"
            " WHERE id=? AND user_id=?"
        )
        params = (job_id, user_id)
    elif status == "rejected":
        sql = (
            "UPDATE jobs SET verdict='rejected', verdict_confirmed=1,"
            " applied=0, applied_at=NULL, company_rejected=0, company_rejected_at=NULL"
            " WHERE id=? AND user_id=?"
        )
        params = (job_id, user_id)
    elif status == "interview":
        sql = (
            "UPDATE jobs SET interview_scheduled=1, interview_at=date('now'),"
            " applied=1, company_rejected=0, company_rejected_at=NULL"
            " WHERE id=? AND user_id=?"
        )
        params = (job_id, user_id)
    elif status == "offer":
        sql = (
            "UPDATE jobs SET offer_received=1, offer_at=date('now'),"
            " interview_scheduled=1, applied=1,"
            " company_rejected=0, company_rejected_at=NULL"
            " WHERE id=? AND user_id=?"
        )
        params = (job_id, user_id)
    elif status in ("worth_considering", "warning"):
        sql = (
            "UPDATE jobs SET verdict=?, verdict_confirmed=1,"
            " applied=0, applied_at=NULL, company_rejected=0, company_rejected_at=NULL"
            " WHERE id=? AND user_id=?"
        )
        params = (status, job_id, user_id)
    else:
        return False

    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.rowcount > 0


def export_csv(user_id: int) -> str:
    """
    Export data to CSV.

    Args:
        user_id: User ID

    Returns:
        CSV string or empty string if no data

    Notes:
        Exports up to 10,000 records (config: limit=10000)
    """
    rows = get_jobs(user_id, limit=10000)
    if not rows:
        return ""
    out = io.StringIO()
    fields = [k for k in rows[0].keys() if k not in ("id", "user_id", "raw_json")]
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for row in rows:
        w.writerow({k: row[k] for k in fields})
    return out.getvalue()




def get_statistics(user_id: int) -> dict:
    """
    Aggregate job analysis data for the statistics dashboard.

    Returns a dict with:
      verdict_distribution: counts per verdict category
      funnel: total / applied / company_rejected / interview_scheduled / offer_received
      layer_flags: per-layer counts of ok / warning / flag
      fit_score_avg: average fit score (None if no scored records)
      fit_score_distribution: list of (range_label, count) tuples
      archetype_distribution: counts per role_archetype value
      zero_list_hits: count of zero_list_hit=1 records
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE user_id=?", (user_id,)
        ).fetchall()

    verdict_distribution = {
        'worth_considering': 0,
        'warning': 0,
        'rejected_confirmed': 0,
        'rejected_soft': 0,
    }
    funnel = {'total': 0, 'applied': 0, 'company_rejected': 0, 'interview_scheduled': 0, 'offer_received': 0}
    layers = ['triage', 'product', 'business', 'reputation', 'values', 'fit']
    layer_flags = {l: {'ok': 0, 'warning': 0, 'flag': 0, 'unknown': 0} for l in layers}
    fit_scores = []
    archetype_distribution = {}
    zero_list_hits = 0

    for row in rows:
        funnel['total'] += 1
        if row['applied']:
            funnel['applied'] += 1
        if row['company_rejected']:
            funnel['company_rejected'] += 1
        if row['interview_scheduled']:
            funnel['interview_scheduled'] += 1
        if row['offer_received']:
            funnel['offer_received'] += 1
        if row['zero_list_hit']:
            zero_list_hits += 1

        v = row['verdict'] or ''
        vc = row['verdict_confirmed'] or 0
        if v == 'worth_considering':
            verdict_distribution['worth_considering'] += 1
        elif v == 'warning':
            verdict_distribution['warning'] += 1
        elif v == 'rejected' and vc:
            verdict_distribution['rejected_confirmed'] += 1
        elif v == 'rejected' and not vc:
            verdict_distribution['rejected_soft'] += 1

        for layer in layers:
            col = f"{layer}_status"
            status = (row[col] or 'unknown') if col in row.keys() else 'unknown'
            if status not in layer_flags[layer]:
                status = 'unknown'
            layer_flags[layer][status] += 1

        fs = row['fit_score'] if 'fit_score' in row.keys() else None
        if fs is not None:
            try:
                fit_scores.append(float(fs))
            except (TypeError, ValueError):
                pass

        arch = row['role_archetype'] if 'role_archetype' in row.keys() else None
        if arch:
            archetype_distribution[arch] = archetype_distribution.get(arch, 0) + 1

    funnel['qualifying'] = verdict_distribution['worth_considering'] + verdict_distribution['warning']

    layer_labels = {
        'triage': 'Triage', 'product': 'Product', 'business': 'Business',
        'reputation': 'Reputation', 'values': 'Values', 'fit': 'Skills fit',
    }
    most_flagged_layer = None
    max_flags = 0
    for _layer in layers:
        fc = layer_flags[_layer]['flag']
        if fc > max_flags:
            max_flags = fc
            most_flagged_layer = (layer_labels[_layer], fc)

    layer_flag_counts = sorted(
        [(layer_labels[l], layer_flags[l]['flag']) for l in layers],
        key=lambda x: -x[1],
    )

    fit_score_avg = round(sum(fit_scores) / len(fit_scores), 2) if fit_scores else None

    buckets = [('1.0–2.0', 0), ('2.0–3.0', 0), ('3.0–4.0', 0), ('4.0–5.0', 0)]
    for s in fit_scores:
        if s < 2.0:
            buckets[0] = (buckets[0][0], buckets[0][1] + 1)
        elif s < 3.0:
            buckets[1] = (buckets[1][0], buckets[1][1] + 1)
        elif s < 4.0:
            buckets[2] = (buckets[2][0], buckets[2][1] + 1)
        else:
            buckets[3] = (buckets[3][0], buckets[3][1] + 1)

    return {
        'verdict_distribution': verdict_distribution,
        'funnel': funnel,
        'layer_flags': layer_flags,
        'most_flagged_layer': most_flagged_layer,
        'layer_flag_counts': layer_flag_counts,
        'fit_score_avg': fit_score_avg,
        'fit_score_distribution': buckets,
        'archetype_distribution': dict(sorted(archetype_distribution.items(), key=lambda x: -x[1])),
        'zero_list_hits': zero_list_hits,
    }
def user_count() -> int:
    """
    Return the number of users in the database.

    Returns:
        User count
    """
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
