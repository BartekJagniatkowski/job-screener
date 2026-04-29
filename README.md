# Job Screener

Narzędzie do etycznej analizy ofert pracy. Każde ogłoszenie przechodzi przez sześć warstw analizy zanim pojawi się pytanie „czy warto aplikować": triage, produktową, biznesową, reputacyjną, wartości i dopasowanie kompetencyjne do Twojego profilu.

---

## Wymagania

- Python 3.9+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — menedżer środowiska i zależności
- Klucz API Anthropic (`claude-sonnet-4-6`)

---

## Szybki start (lokalnie)

```bash
# 1. Sklonuj repo i przejdź do katalogu
git clone https://github.com/BartekBroda/job-screener
cd job-screener

# 2. Skopiuj i uzupełnij konfigurację
cp config.env.template config.env
# wpisz swój ANTHROPIC_API_KEY w config.env

# 3. Zainstaluj zależności i uruchom
uv sync
bash run.sh
```

Przeglądarka otworzy się automatycznie pod adresem `http://localhost:5000`.

---

## Pierwsze uruchomienie

Przy pierwszym uruchomieniu aplikacja poprosi o utworzenie konta administratora.

Po zalogowaniu przejdź do **Ustawień** i uzupełnij:

| Pole | Opis |
|---|---|
| **CV** | Twoje doświadczenie i kompetencje — im dokładniejsze, tym lepsze dopasowanie |
| **Lista Zero** | Firmy, branże lub kategorie powodujące automatyczne odrzucenie bez dalszej analizy |
| **Lista Żółta** | Sygnały wymuszające werdykt „wymaga uwagi", nawet gdy pozostałe warstwy są zielone |
| **Dodatkowe kryteria** | Preferowane sektory, czerwone flagi kulturowe, priorytety w ocenie ofert |

---

## Zarządzanie aplikacją

```bash
bash run.sh        # lokalne uruchomienie z hot-reload (deweloper)
bash start.sh      # produkcja: gunicorn daemon, 2 workery
bash stop.sh       # zatrzymanie daemona
bash restart.sh    # restart (stop → run)
```

Logi produkcyjne: `/tmp/screener-access.log`, `/tmp/screener-error.log`

---

## Deployment na serwer

```bash
./deploy.sh user@twojserwer.pl /var/www/job-screener
```

Skrypt skopiuje pliki, zainstaluje zależności przez `uv` i uruchomi serwis. Po deploymencie:

1. Utwórz `/var/www/job-screener/config.env` z kluczem API
2. `sudo systemctl restart job-screener`
3. Skonfiguruj nginx (przykład w output skryptu)

---

## Zapraszanie nowych użytkowników

Ustaw `INVITE_TOKEN` w `config.env`. Nowe konta można tworzyć tylko przez link:

```
https://twoja.domena.pl/register?token=TWOJ_TOKEN
```

---

## Konfiguracja (`config.env`)

| Zmienna | Opis |
|---|---|
| `ANTHROPIC_API_KEY` | Klucz API Anthropic (wymagany) |
| `SECRET_KEY` | Klucz sesji Flask (zmień na serwerze) |
| `INVITE_TOKEN` | Token zaproszenia dla nowych użytkowników |
| `PORT` | Port aplikacji (domyślnie: `5000`) |

---

## Funkcje

- **Analiza z URL lub wklejonej treści** — scrapuje ogłoszenie automatycznie; gdy strona blokuje (LinkedIn, Indeed itp.) prosi o wklejenie treści
- **Sześć warstw analizy** z werdyktem i uzasadnieniem; warstwa reputacyjna korzysta z wiedzy modelu o firmie (Glassdoor, media, historia C-level)
- **Modal szczegółów** — kliknięcie wiersza w historii lub dashboardzie otwiera szczegóły w miejscu; nawigacja ← → między ogłoszeniami, URL odzwierciedla aktualnie oglądane ogłoszenie
- **Werdykty i stany** — warta rozważenia / wymaga uwagi / odrzucona przez model / odrzucona (potwierdzona); oznaczanie wysłanych zgłoszeń
- **Historia analiz** — tabela z filtrowaniem wizualnym według kategorii, eksport do CSV
- **Tryb jasny/ciemny** — przełącznik w nawigacji, preferencja zapisywana w przeglądarce
- **Multi-user** — każdy użytkownik ma oddzielny profil, listy i historię

---

## Struktura plików

```
job-screener/
├── app.py              — routing Flask, auth, endpointy
├── analyzer.py         — prompt i integracja z Claude API
├── database.py         — schemat SQLite, migracje, operacje
├── scraper.py          — pobieranie treści URL, normalizacja
├── static/style.css    — wszystkie style (zero inline CSS w szablonach)
├── templates/          — szablony Jinja2
├── data/screener.db    — baza danych (tworzona automatycznie, nie commitować)
├── config.env          — konfiguracja lokalna (nie commitować)
├── config.env.template — szablon konfiguracji
├── pyproject.toml      — zależności projektu (uv)
├── run.sh              — uruchomienie lokalne
├── start.sh / stop.sh / restart.sh — zarządzanie daemonem
└── deploy.sh           — deployment na serwer
```

---

## Eksport danych

Historia → **Pobierz CSV** — plik zawiera wszystkie warstwy analizy i otwiera się w Excelu i Google Sheets.
