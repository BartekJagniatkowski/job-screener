import sqlite3
from typing import Optional
import hashlib
import secrets
import json as _json
import datetime
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
"""

DEFAULT_ZERO_LIST = """- Alkohol, papierosy, hazard, seks industry
- Uzbrojenie i obronność (dostawcy komponentów militarnych, AI dla wojska, fundusze defense tech)
- Big pharma, ubezpieczenia, finanse (banki, fintechy, trading)
- Marketing i e-commerce jako core business (napędzanie niekontrolowanej konsumpcji)

Uwaga: powiązanie przez bezpośredniego inwestora/współzałożyciela aktywnie zarządzającego firmą z powyższych kategorii = czerwona flaga (nie automatyczne odrzucenie). Powiązanie przez inwestora inwestora = zbyt daleko.""".strip()

DEFAULT_CRITERIA = """Szukam ról na przecięciu product discovery, strategy i ludzkiego wymiaru produktu.
Preferuję: healthcare, science, social impact, AI ethics, edtech.
Unikam: execution PM bez komponentu discovery, growth PM (A/B testy jako core), technical PM od integracji narzędzi.
Czerwona flaga kulturowa: kwartalny rytm zwolnień, toksyczny leadership (Glassdoor < 3.5 z wyraźnym trendem spadkowym).""".strip()


def get_conn() -> sqlite3.Connection:
    """
    Otwórz połączenie z bazą danych w trybie WAL.
    
    Returns:
        Połączenie SQLite z ustawioną row_factory na Row
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """
    Inicjalizuj bazę danych i wykonaj migracje.
    
    Funkcja jest idempotentna — można ją wywołać wielokrotnie bez ryzyka duplikacji
    kolumn lub danych. Obsługuje migrację z polskimi nazwami kolumn na angielskie,
    a także backfill wartości dla istniejących rekordów.
    
    Migracje obejmują:
    - Dodanie nowych kolumn (idempotentne ALTER TABLE ADD COLUMN)
    - Przemianowanie kolumn z polskich na angielskie nazwy
    - Migracja wartości werdyktów i statusów z polskich na angielskie
    - Backfill verdict_confirmed dla istniejących rekordów
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


def hash_password(password: str) -> str:
    """
    Zasoli hasło przy użyciu SHA-256.
    
    Args:
        password: Hasło do zasolenia
    
    Returns:
        String w formacie "salt:hash" gdzie salt to 16-hex znaków
    """
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{h}"


def verify_password(password: str, stored: str) -> bool:
    """
    Sprawdź czy podane hasło pasuje do zasolonego hashu.
    
    Args:
        password: Podane hasło
        stored: Zasolony hash z bazy (format: "salt:hash")
    
    Returns:
        True jeśli hasła się zgadzają, False w przeciwnym przypadku
    """
    try:
        salt, h = stored.split(":", 1)
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == h
    except Exception:
        return False


def create_user(username: str, password: str) -> bool:
    """
    Stwórz nowe konto użytkownika.
    
    Args:
        username: Nazwa użytkownika (będzie zapisana w lowercase)
        password: Hasło do zasolenia
    
    Returns:
        True jeśli konto zostało utworzone, False jeśli nazwa użytkownika jest już zajęta
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
    Pobierz użytkownika po nazwie użytkownika.
    
    Args:
        username: Nazwa użytkownika
    
    Returns:
        sqlite3.Row z danymi użytkownika lub None jeśli nie znaleziono
    """
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username=?",
            (username.lower().strip(),)
        ).fetchone()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    """
    Pobierz użytkownika po ID.
    
    Args:
        user_id: ID użytkownika
    
    Returns:
        sqlite3.Row z danymi użytkownika lub None jeśli nie znaleziono
    """
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def update_user_profile(user_id: int, cv: str, zero_list: str, criteria: str, yellow_list: str = "") -> None:
    """
    Zaktualizuj profil użytkownika.
    
    Args:
        user_id: ID użytkownika
        cv: Treść CV
        zero_list: Treść listy zero
        criteria: Dodatkowe kryteria
        yellow_list: Treść listy żółtej (opcjonalne, domyślnie puste)
    """
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET cv=?, zero_list=?, criteria=?, yellow_list=? WHERE id=?",
            (cv.strip(), zero_list.strip(), criteria.strip(), yellow_list.strip(), user_id)
        )


def compute_hash(text: str) -> str:
    """
    Oblicz SHA-256 hash z podanego tekstu.
    
    Args:
        text: Tekst do zhashowania (nieważne czy URL czy treść)
    
    Returns:
        64-hex znakowy SHA-256 hash
    """
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()


def check_duplicate(user_id: int, source: str) -> Optional[sqlite3.Row]:
    """
    Sprawdź czy już istnieje analiza z tym samym źródłem.
    
    source może być URL lub treść. Hash jest obliczany po usunięciu białych znaków.
    
    Args:
        user_id: ID użytkownika
        source: URL lub treść ogłoszenia
    
    Returns:
        Rekord z bazą jeśli istnieje duplikat, None inaczej
    """
    clean_source = source.strip() if source else ""
    h = compute_hash(clean_source)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE user_id=? AND source_hash=? ORDER BY id DESC LIMIT 1",
            (user_id, h)
        ).fetchone()
    return dict(row) if row else None


def save_job(
    user_id: int,
    result: AnalysisResult,
    source_url: str = "",
    source_text: str = ""
) -> None:
    """
    Zapisz wynik analizy do bazy danych.
    
    source_url — job listing URL (stored as job_url and used for deduplication)
    source_text — listing content (scraped or pasted by the user)
    
    Args:
        user_id: ID użytkownika
        result: Wynik analizy z JSON
        source_url: URL ogłoszenia (lub pusty)
        source_text: Treść ogłoszenia (scraped lub wklejona)
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
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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


def get_jobs(user_id: int, limit: int = 100) -> list[dict]:
    """
    Pobierz ostatnie n rekordów z bazy.
    
    Args:
        user_id: ID użytkownika
        limit: Maksymalna liczba rekordów (domyślnie 100)
    
    Returns:
        Lista słowników z danymi z bazy
    """
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()


def get_job(job_id: int, user_id: int) -> Optional[sqlite3.Row]:
    """
    Pobierz konkretny rekord z bazy.
    
    Args:
        job_id: ID wpisu z bazy
        user_id: ID użytkownika
    
    Returns:
        sqlite3.Row z danymi lub None jeśli nie znaleziono
    """
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE id=? AND user_id=?",
            (job_id, user_id)
        ).fetchone()


def update_verdict(job_id: int, user_id: int, verdict: str) -> bool:
    """
    Ręczna zmiana werdyktu.
    
    Args:
        job_id: ID wpisu z bazy
        user_id: ID użytkownika
        verdict: Nowy werdykt (rejected, warning, worth_considering)
    
    Returns:
        True jeśli rekord został zaktualizowany, False inaczej
    
    Notes:
        'rejected_soft' ustawia verdict='rejected', verdict_confirmed=0
        (opinia AI, niepotwierdzona). Wszystkie inne wartości ustawiają
        verdict_confirmed=1 (potwierdzone przez użytkownika).
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
    Ręczne dołączenie URL do wpisu.
    
    Args:
        job_id: ID wpisu z bazy
        user_id: ID użytkownika
        url: URL do zapisania
    
    Returns:
        True jeśli rekord został zaktualizowany
    """
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET job_url=? WHERE id=? AND user_id=?",
            (url.strip(), job_id, user_id)
        )
        return cur.rowcount > 0


def delete_job(job_id: int, user_id: int) -> bool:
    """
    Usuń wpis z bazy.
    
    Args:
        job_id: ID wpisu z bazy
        user_id: ID użytkownika
    
    Returns:
        True jeśli wpis istniał i należał do użytkownika, False inaczej
    """
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM jobs WHERE id=? AND user_id=?",
            (job_id, user_id)
        )
        return cur.rowcount > 0


def update_applied(job_id: int, user_id: int, applied: bool) -> bool:
    """
    Ustaw lub usuń status wysłania aplikacji.
    
    Args:
        job_id: ID wpisu z bazy
        user_id: ID użytkownika
        applied: True jeśli aplikacja została wysłana
    
    Returns:
        True jeśli rekord został zaktualizowany
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
    Ustaw lub usuń status odmowy ze strony firmy.
    
    Args:
        job_id: ID wpisu z bazy
        user_id: ID użytkownika
        rejected: True jeśli firma odmówiła
    
    Returns:
        True jeśli rekord został zaktualizowany
    """
    date = datetime.date.today().isoformat() if rejected else None
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET company_rejected=?, company_rejected_at=? WHERE id=? AND user_id=?",
            (1 if rejected else 0, date, job_id, user_id)
        )
        return cur.rowcount > 0


def update_job_status(job_id: int, user_id: int, status: str) -> bool:
    """
    Zjednoczona aktualizacja statusu z dropdownu.
    
    Verdict values (worth_considering, warning, rejected_soft, rejected):
      set verdict + verdict_confirmed, clear applied and company_rejected.
    Application values (applied, company_rejected):
      set application fields, leave verdict unchanged.
    
    Args:
        job_id: ID wpisu z bazy
        user_id: ID użytkownika
        status: Nowy status (worth_considering, warning, rejected_soft, rejected,
                applied, company_rejected)
    
    Returns:
        True jeśli rekord został zaktualizowany
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
    Eksportuj dane do CSV.
    
    Args:
        user_id: ID użytkownika
    
    Returns:
        String CSV lub pusty string jeśli brak danych
    
    Notes:
        Eksportuje max 10 000 rekordów (konfiguracja: limit=10000)
    """
    rows = get_jobs(user_id, limit=10000)
    if not rows:
        return ""
    out = io.StringIO()
    fields = [k for k in rows[0].keys() if k not in ("id", "user_id", "raw_json")]
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    try:
        for row in rows:
            w.writerow({k: row[k] for k in fields})
    except sqlite3.IntegrityError as e:
        print(f"Warning: Integrity error during CSV export for user {user_id}: {e}")
    return out.getvalue()


def user_count() -> int:
    """
    Pobierz liczbę użytkowników w bazie.
    
    Returns:
        Liczba użytkowników
    """
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
