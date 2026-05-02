# Job Screener — kontekst projektu dla Claude Code

Narzędzie do etycznej weryfikacji ofert pracy. Każde ogłoszenie przechodzi przez
sześć warstw analizy zanim pojawi się pytanie "czy warto aplikować".

---

## Stack i zależności

- **Backend:** Python >= 3.9, Flask >= 3.1.3
- **Baza danych:** SQLite (plik `data/screener.db`)
- **AI:** Anthropic Claude API (model: `claude-sonnet-4-6`)
- **Frontend:** Jinja2 + vanilla JS + zewnętrzny CSS
- **Menedżer środowiska:** uv (plik `pyproject.toml` + `uv.lock`)
- **Zależności Python:** tylko `flask` — zero zewnętrznych bibliotek do CSS/Markdown
- **Nie używamy:** npm, webpack, żadnych frameworków JS
- **`main.py`** — CLI entry point z `argparse` (port, host, debug)

## Uruchamianie

```bash
# produkcja — daemon gunicorn
bash server.sh start       # gunicorn -w 2, PID w /tmp/screener.pid
bash server.sh stop        # zatrzymanie daemona
bash server.sh restart     # stop → sleep 1 → start
bash server.sh status      # czy działa i jaki PID

# deweloper (bez daemona)
uv run --env-file config.env python app.py

# zarządzanie zależnościami
uv add nazwa-biblioteki    # dodanie nowej zależności
uv sync                    # odtworzenie środowiska (np. po sklonowaniu repo)
```

`server.sh start` uruchamia gunicorn z 2 workerami jako daemon; logi w `/tmp/screener-access.log`
i `/tmp/screener-error.log`. PID zapisywany w `/tmp/screener.pid`.

`uv.lock` jest commitowany do Gita — gwarantuje identyczne wersje na każdym środowisku.
`.venv/` jest ignorowany przez Git — uv tworzy je lokalnie automatycznie.

---

## Struktura projektu

```
job-screener/
├── app.py              — Flask: routing, auth, wszystkie endpointy
├── analyzer.py         — Claude API, system prompt z metodyką analizy
├── database.py         — SQLite: schemat, migracje, operacje na danych
├── scraper.py          — pobieranie treści URL, normalize_url, blokowane domeny
├── main.py             — stub wygenerowany przez uv init (nieużywany)
├── 11DESIGN.md         — wzorce design systemu ElevenLabs (referencja stylistyczna, nie commitowany)
├── CHANGELOG.md        — historia wersji (edytuj tekstowo, renderowana przez /changelog)
├── CLAUDE.md           — ten plik
├── config.env          — klucz API i SECRET_KEY (nigdy nie commitować)
├── config.env.template — szablon konfiguracji
├── pyproject.toml      — zależności i metadane projektu (zastąpił requirements.txt)
├── uv.lock             — zablokowane wersje zależności (commitowany)
├── server.sh           — zarządzanie serwerem: start|stop|restart|status
├── static/
│   ├── style.css       — WSZYSTKIE style aplikacji (zero inline stylów w szablonach)
│   └── fonts/
│       └── Nohemi-VF.ttf — variable font używany w nagłówkach i nazwie aplikacji
├── templates/
│   ├── base.html       — layout, <link> do style.css, nawigacja, stopka
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html  — formularz analizy + ostatnie wyniki + modal dla ostatnich analiz
│   ├── history.html    — tabela wszystkich analiz + modal szczegółów z nawigacją
│   ├── job_partial.html — czysty HTML (bez extends) ładowany przez AJAX do modala
│   ├── job_detail.html — pełnostronicowy widok szczegółowy analizy
│   ├── settings.html   — CV, Reguła Zero, Lista Żółta, kryteria
│   └── changelog.html  — renderuje CHANGELOG.md przez własny parser
└── data/
    └── screener.db     — baza SQLite (nigdy nie commitować)
```

---

## Baza danych

### Tabela `users`
```
id, username, password_hash, cv, zero_list, criteria, yellow_list, created_at
```

### Tabela `jobs`
```
id, user_id, analyzed_at, company, role, verdict,
verdict_confirmed,      — 0 = werdykt modelu (niepotwierdzony), 1 = potwierdzony
zero_list_hit, zero_list_reason,
triage_status, product_status, business_status,
reputation_status, values_status, fit_status,
verdict_summary, triage_findings, product_findings,
business_findings, reputation_findings, values_findings,
fit_strengths, fit_gaps, fit_improve,
gut_feeling,
source,                 — krótki identyfikator (URL lub pierwsze 300 znaków treści)
source_full,            — pełna treść ogłoszenia (scraped lub wklejona)
source_hash,            — SHA-256 do deduplicacji
job_url,                — URL ogłoszenia (zapisywany osobno od treści)
applied,                — 0/1 status zgłoszenia
applied_at,             — data zgłoszenia
company_rejected,       — 0/1 odmowa ze strony firmy
company_rejected_at,    — data odmowy
reasoning,              — wewnętrzne rozumowanie modelu
raw_json                — pełny JSON odpowiedzi modelu
```

### Migracje
`init_db()` wykonuje `ALTER TABLE RENAME COLUMN` dla kolumn z polskimi nazwami oraz
`ALTER TABLE ADD COLUMN` dla brakujących kolumn przy każdym starcie.
Bezpieczne dla istniejących baz — idempotentne, nie usuwa danych.

### Kluczowe funkcje database.py
```python
save_job(user_id, result, source_url="", source_text="")
# source_url  → job_url i source_hash (deduplicacja)
# source_text → source_full (treść do analizy)

check_duplicate(user_id, source)  # hash po URL lub treści
update_verdict(job_id, user_id, verdict)     # zawsze ustawia verdict_confirmed=1
update_applied(job_id, user_id, applied)
update_company_rejected(job_id, user_id, rejected)
update_job_status(job_id, user_id, status)   # obsługuje wszystkie 6 statusów
update_job_url(job_id, user_id, url)
delete_job(job_id, user_id)
```

---

## Scraper (scraper.py)

### Kody błędów
- `timeout` — serwer nie odpowiedział w czasie (fallback: wklej treść)
- `notfound` — strona nie istnieje 404 (brak fallbacku — ogłoszenie usunięte)
- `blocked` — strona istnieje ale blokuje dostęp (fallback: wklej treść)
- `network` — inny błąd sieciowy (fallback: wklej treść)

### Domeny blokowane bez próby połączenia
LinkedIn, Indeed, Glassdoor, Pracuj.pl, NoFluffJobs, JustJoin.it

### normalize_url()
Usuwa parametry śledzące przed scrapowaniem i deduplikacją:
`utm_*`, `refid`, `trackingid`, `fbclid`, `gclid`, `ref`, `source`, `from`, `vjk` itp.
Zachowuje parametry specyficzne dla ogłoszeń (np. `id`, `jobId`).
Usuwa fragment `#...`.

---

## Endpointy app.py

```
GET/POST /login
GET/POST /register              — token przez ?token=INVITE_TOKEN
GET      /dashboard
POST     /analyze               — url + text (oba opcjonalne, min. jedno wymagane)
POST     /check_source          — url lub text, sprawdza duplikat
POST     /reanalyze/<id>
GET      /history_latest        — zwraca {id} ostatniego wpisu
GET      /history
GET      /job/<id>
GET      /job/<id>/partial      — HTML bez layoutu, ładowany przez AJAX do modala
POST     /job/<id>/verdict      — zmiana werdyktu
POST     /job/<id>/status       — zmiana statusu (wszystkie 6 wartości)
POST     /job/<id>/url          — dodanie/zmiana URL
POST     /job/<id>/applied      — status zgłoszenia
POST     /job/<id>/company_rejected — odmowa ze strony firmy
POST     /job/<id>/delete
GET      /settings
GET      /export/csv
GET      /changelog
GET      /logout
```

### System statusów (6 wartości)
Dropdown `#status-select` z grupami `<optgroup>`:

| Wartość | Etykieta | Efekt w DB |
|---|---|---|
| `worth_considering` | Do rozważenia | verdict, confirmed=1 |
| `warning` | Wymaga uwagi | verdict, confirmed=1 |
| `rejected_soft` | Odrzucona (model) | verdict=rejected, confirmed=0 |
| `rejected` | Odrzucona | verdict=rejected, confirmed=1 |
| `applied` | Zgłoszono | applied=1 |
| `company_rejected` | Odmowa | company_rejected=1, applied=1 |

Obsługiwane przez `update_job_status()` w `database.py`.

### Badge w kartach i tabeli
Badge odzwierciedla status aplikacji, nie tylko werdykt:
- `applied` → zielony badge "ZGŁOSZONO" (`badge-applied`)
- `company_rejected` → pomarańczowy badge "ODMOWA" (`badge-company_rejected`)
- pozostałe → badge na podstawie verdict (`badge-rejected`, `badge-warning`, `badge-worth_considering`)

Atrybut `data-verdict` na elemencie badge przechowuje underlying verdict
(używany przez `readCurrentState()` w JS modala).

### Modal szczegółów ogłoszenia
- `history.html` i `dashboard.html` mają identyczny modal overlay (`#job-modal`)
- Kliknięcie wiersza → `openModal(jobId)` → fetch `/job/<id>/partial` → wstrzyknięcie HTML do `#modal-body`
- Nawigacja ← → między ogłoszeniami (klawiatura i przyciski na ekranie)
- URL management: `pushState` przy otwarciu (`?job=<id>`), `replaceState` przy nawigacji, `replaceState` przy zamknięciu
- Cofnięcie przeglądarki (back) zamyka modal; bezpośredni link `?job=<id>` auto-otwiera modal
- Funkcje JS (`tog`, `setStatus`, `confirmDelete`, `reanalyze`, `showUrlEdit`, `saveUrl`) są globalami zdefiniowanymi w szablonie-rodzicu (history/dashboard), nie w partial

### Logika /analyze
1. `normalize_url(url)` — zawsze przed użyciem
2. Jeśli jest `text` → użyj tekstu bezpośrednio
3. Jeśli tylko `url` → próba scrapowania
4. Jeśli scraping się nie powiódł → zwróć `scrape_error` z kodem
5. Sprawdź duplikat (chyba że `force=1`)
6. `analyze()` → `save_job()` z `source_url` i `source_text` osobno

---

## Metodyka analizy (analyzer.py)

### Sześć warstw
1. **Triage** — dopasowanie roli do trajektorii, pierwsze sygnały, ukryty pracodawca
2. **Produktowa** — produkt, claims, AI-washing, weryfikowalność
3. **Biznesowa** — model przychodowy, finansowanie, inwestorzy, PE/VC
4. **Reputacyjna** — aktywnie korzysta z wiedzy treningowej (nie tylko z treści ogłoszenia): Glassdoor/Indeed/Blind ocena i trend, dominujące tematy recenzji pracowników, historia C-level, layoffs pattern, media i regulacje; dla nieznanych firm jawnie zaznacza brak danych
5. **Wartości** — spójność misji, pułapki etyczne, dostępność vs deklaracje
6. **Dopasowanie kompetencyjne** — mocne strony, luki, co wzmocnić w aplikacji

### Nazwa firmy
Pole `company_name` w JSON odpowiedzi modelu musi zawierać rzeczywistą nazwę firmy (nie pośrednika).
Jeśli firmy nie da się zidentyfikować — model używa dokładnie `"Nieznana"`.
W polu `verdict_summary` pierwsze zdanie musi wyjaśniać dlaczego firma jest nieznana.
Szablony wyświetlają `job.company or 'Nieznana'` — nie używają `'—'` dla pustej nazwy.

### Lista Zero
Automatyczne odrzucenie bez analizy. Konfigurowana per użytkownik w Ustawieniach.

### Potwierdzenie odrzucenia
`verdict_confirmed` rozróżnia dwa stany odrzucenia:
- `zero_list_hit = true` → `verdict_confirmed = 1` ustawiane automatycznie przez `save_job()`
- AI zwraca `verdict: rejected` bez `zero_list_hit` → `verdict_confirmed = 0` (wymaga akcji użytkownika)
- Użytkownik wybiera „Odrzucona" w dropdownie → `verdict_confirmed = 1` przez `update_job_status()`

### Lista Żółta
Wymusza werdykt "uwaga" ale kontynuuje analizę. Konfigurowana per użytkownik.

### Zasada dowodu
Przy każdej fladze (`status: "flag"`) i każdym odrzuceniu model musi podać
pole `evidence` z konkretnym cytatem z treści ogłoszenia.
Bez dowodu → obniż do "warning", opisz wątpliwość.

**Wyjątek — warstwa reputacyjna:** korzysta z wiedzy modelu spoza treści ogłoszenia;
`evidence` = konkretna wiedza (liczby, nazwy, daty), nie cytat z ogłoszenia.
Ogólne stwierdzenia bez konkretów nadal niedozwolone.

### Format JSON odpowiedzi
```json
{
  "company_name", "role_title",
  "verdict": "rejected|warning|worth_considering",
  "verdict_summary",
  "zero_list_hit", "zero_list_reason", "zero_list_evidence",
  "yellow_list_hit", "yellow_list_reason",
  "triage": { "status", "findings", "evidence" },
  "layers": {
    "product":    { "status", "findings", "evidence" },
    "business":   { "status", "findings", "evidence" },
    "reputation": { "status", "findings", "evidence" },
    "values":     { "status", "findings", "evidence" }
  },
  "fit": { "status", "strengths", "gaps", "improve" },
  "gut_feeling"
}
```

---

## CSS — zasady bezwzględne

**Zero inline stylów w szablonach HTML.** Jedynym wyjątkiem jest `display:none`
jako stan dynamiczny zarządzany przez JS.

Wszystkie style w `static/style.css`. Nowa klasa → nowy wpis w odpowiedniej
sekcji pliku z komentarzem sekcji (np. `/* ── nowa sekcja ───── */`).

### Design tokens
```css
--bg, --surface, --border, --border-light   — neutralna chłodna czerń (#0d0d0d / #1a1a1a)
--text, --muted, --dim                      — skala szarości tekstu
--accent, --accent-dim                      — złoty (#c9a96e) — tylko dla nav-brand
--radius-sm: 8px; --radius-md: 18px; --radius-lg: 22px
--fd: 'Nohemi'   — nagłówki, logo (font-weight: 200)
--fb: 'DM Sans'  — body text
--fm: 'DM Mono'  — etykiety, mono, przyciski
```

### Zmienne typograficzne
```css
--fs-base-scale: 16px;  /* zmień tylko tę jedną wartość */
--fs-2xs przez --fs-4xl — calc() oparte na base-scale
```

### Tryb jasny / ciemny
- Atrybut `data-theme="light"` na `<html>` aktywuje jasną paletę (#f2f2f2 tło, białe karty)
- Przełącznik: `<button id="theme-toggle">` w nawigacji (`base.html`) — ikona ☀/☾
- Preferencja zapisywana w `localStorage`; wczytywana przez IIFE w `<head>` przed CSS (zero mignięcia)
- Kolory o słabym kontraście na jasnym tle nadpisane przez reguły `[data-theme="light"] .klasa { ... }`

### Kolorystyka statusów (wiersze tabeli i badge)

Wszystkie badge'e mają **transparentne tło** — tylko obramowanie i kolor tekstu.
Podświetlenie tła wiersza jest jedynym sygnałem kolorowym na poziomie kategorii.

| Status | Klasa wiersza | Badge | Kolor |
|---|---|---|---|
| Do rozważenia | `row-worth-considering` | `badge-worth_considering` | niebieski |
| Wymaga uwagi | `row-warning` | `badge-warning` | żółty |
| Odrzucona (model) | `row-rejected-soft` | `badge-rejected` | czerwony, słabe tło wiersza |
| Odrzucona | `row-rejected` | `badge-rejected` | czerwony, pełne tło wiersza |
| Zgłoszono | `row-applied` | `badge-applied` | zielony |
| Odmowa | `row-company-rejected` | `badge-company_rejected` | pomarańczowy, brak tła wiersza |

Hover na kolorowych wierszach: `box-shadow: inset 0 0 0 9999px var(--hover-overlay)`
zamiast `filter: brightness()` — nie wpływa na kolory badge'y i kropek.

### Kluczowe klasy użytkowe
`.page-title`, `.page-sub` — nagłówek i podtytuł strony (Nohemi font-weight 200)
`.field`, `.field-hint` — wrapper pola formularza i jego etykieta
`.flash`, `.flash.info`, `.flash.error` — komunikaty flash z serwera
`.nav-brand`, `.nav-links` — logo i linki nawigacji
`.btn-primary`, `.btn-secondary`, `.btn-sm`, `.btn-danger`
`.btn-theme-toggle` — przycisk ☀/☾ przełączający tryb jasny/ciemny
`.btn-applied`, `.btn-applied.is-applied` — przycisk "Zgłoszono" (zielony gdy aktywny)
`.btn-company-rejected.is-rejected` — przycisk odmowy (niebieski gdy aktywny)
`.dot`, `.dot-ok`, `.dot-warning`, `.dot-flag`, `.dot-unknown` — kolorowe kropki statusu warstw
`.spinner` — animowany wskaźnik ładowania
`.source-status` — wynik walidacji źródła (duplikat / ok / błąd scrapera)
`.source-url-section` — wrapper sekcji URL ogłoszenia
`.source-preview-text`, `.source-preview-label-gap` — podgląd treści źródłowej
`.grid2` — dwukolumnowy układ grid (staje się 1-kolumnowy na mobile)
`.link-accent` — link w kolorze accent (złoty)
`.auth-hint` — dodatkowy tekst pod formularzem logowania/rejestracji
`.text-red`, `.text-yellow`, `.text-green`, `.text-accent`
`.td-date`, `.td-role`, `.td-mono`, `.fw-500`
`.td-dim`, `.td-red`, `.td-green`, `.td-orange`, `.td-blue`
`.card-body`, `.card-mb`, `.card-header-body`
`.card-sub`, `.card-meta` — podtytuł i metadane w nagłówku karty
`.card-header--vertical` — pionowy układ nagłówka karty: badge → rola → firma → summary → daty (używany w modal i widoku szczegółowym)
`.card-company` — nazwa firmy pod tytułem roli w pionowym nagłówku karty
`.card-source-url` — link do ogłoszenia w nagłówku karty, pod podsumowaniem; ucięty wielokropkiem
`.duplicate-notice`, `.duplicate-label`, `.duplicate-title`, `.duplicate-meta`, `.duplicate-actions`
`.evidence`, `.evidence-label`, `.evidence-text`
`.source-text`, `.source-url-label`, `.source-url-link`, `.source-url-hint`
`.source-url-input-row`, `.source-url-input`, `.source-inline-link`
`.btn-inline`, `.source-old-text`, `.source-old-hint`, `.source-none`
`.detail-nav`, `.detail-nav-back`, `.detail-nav-actions`
`.verdict-select-wrap`, `.verdict-select`, `.verdict-select-label`
`.changelog`, `.auth-wrap`, `.auth-brand`, `.auth-sub`
`.recent-more`, `.dashboard-recent`, `.export-section`
`.notice`, `.notice.warn`, `.notice.ok`
`.clickable` — wiersz tabeli klikalny (cursor:pointer + hover)
`.modal-overlay`, `.modal-container`, `.modal-header`, `.modal-nav-btn`, `.modal-counter`, `.modal-close`, `.modal-body`, `.modal-actions`, `.modal-loading`
`.filter-bar`, `.filter-label` — pasek filtrów kategorii w historii
`.filter-btn`, `.filter-btn.active`, `.filter-btn.fb-<category>` — przyciski toggle filtrów; stan zapamiętywany w `localStorage` pod kluczem `history_hidden_categories`

---

## Konwencje

- Język UI: **polski** (etykiety, komunikaty, błędy)
- Komentarze w kodzie: angielski lub polski — bez mieszania w jednym pliku
- Werdykty w bazie: `rejected`, `warning`, `worth_considering`
- Etykieta "Do rozważenia" odpowiada wartości `worth_considering` w DB
- Statusy warstw: `ok`, `warning`, `flag`
- Nazwy zmiennych: angielskie (kolumny DB, klucze JSON, zmienne Python, klasy CSS)
- Daty w bazie: ISO (`date('now')` SQLite)
- Hasła: `sha256(salt:password)` przez `hash_password()` / `verify_password()`
- Multi-user: pierwsze konto bez tokenu, kolejne przez `?token=INVITE_TOKEN`

---

## Git

Repo: `https://github.com/BartekBroda/job-screener` (prywatne)

### Nigdy nie commitować
- `config.env` (klucze API)
- `data/` i `*.db` (baza z danymi użytkowników)
- `venv/`, `__pycache__/`, `.DS_Store`

### Konwencja commitów (po polsku)
```
feat: opis nowej funkcji
fix: opis poprawki
refactor: opis zmiany struktury bez nowej funkcji
style: zmiany CSS/formatowania
docs: aktualizacja dokumentacji
```

---

## Znane ograniczenia

- LinkedIn, Indeed i większość job boardów blokuje scraping — użytkownik musi
  wkleić treść ręcznie
- Model jest niedeterministyczny — dwa runy tego samego ogłoszenia mogą dać
  różne wyniki; to jest właściwość narzędzia, nie błąd
- Stare rekordy (sprzed v0.4) nie mają `source_full` — sekcja źródła w widoku
  wyświetla komunikat o braku danych
- `raw_json` starych rekordów nie zawiera pola `evidence` — blok dowodu
  po prostu się nie renderuje

---

## Kontekst strategiczny — Job Screener jako projekt pilotażowy

### Geneza tej sekcji

Ta sekcja powstała przy okazji szerszej eksploracji pomysłów na micro-SaaS (kwiecień 2026).
Job Screener wyłonił się w tej rozmowie nie jako kandydat na rentowny produkt, ale jako
coś cenniejszego: projekt pilotażowy dla metodologii etycznego budowania produktów.

### Dwa równoległe wątki — celowo rozdzielone

**Wątek 1 — micro-SaaS jako dodatkowy przychód**
Osobna eksploracja, prowadzona równolegle. Główny kandydat na tym etapie:
narzędzie do ekstrakcji danych transakcyjnych z PDF-ów bankowych, z wbudowaną
anonimizacją. Rynek polski jako naturalny start (zróżnicowane formaty wyciągów,
realne obawy RODO wśród małych firm i freelancerów). V1 zakłada ręczny upload
bez integracji z API banków.

**Wątek 2 — Job Screener jako studium przypadku i metodologia**
Job Screener to produkt, który działa przeciwko logice rynku rekrutacyjnego —
pomaga użytkownikowi odfiltrować oferty według kryteriów etycznych, zamiast
maksymalizować liczbę aplikacji. Ta "anty-rynkowa" cecha jest jego wartością,
nie słabością.

Projekt służy jako:
- studium przypadku do portfolio (narracja o tym, jak podejmuję decyzje projektowe)
- test procesu etycznego i humanistycznego podejścia do discovery produktowego
- materiał do budowania narracji o sobie w kontekście rynku pracy, tworzenia
  produktów i treści, edukacji emocjonalnej i etyki technologii

### Pytania otwarte — do eksploracji w kolejnych sesjach

Jak wygląda metodologia etycznego product discovery, gdy jest opisana wprost?
Jakie pytania zadaje się zamiast "jak duży jest rynek"?
Przykładowe pytania alternatywne:
- Kto jest naturalnym wrogiem tego produktu? (a więc: kto jest naturalnym sojusznikiem?)
- Gdzie rynek aktywnie ignoruje problem, bo rozwiązanie go byłoby niekorzystne dla dominujących graczy?
- Jaki jest minimalny rozmiar społeczności uzasadniający utrzymanie produktu?
- Czy twórca ma naturalny dostęp do tej społeczności?

### Rozróżnienie kluczowe

"Niemarketowalne" ≠ "nierentowne". Job Screener może nie mieć naturalnego sponsora
(żaden gracz rynkowy nie chce go promować), ale może mieć lojalnych użytkowników
dokładnie dlatego, że działa przeciwko czemuś. Przed odrzuceniem pomysłu jako
"niesprzedawalnego" warto rozdzielić te dwa pojęcia.