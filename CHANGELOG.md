# Changelog — Job Screener

Narzędzie do etycznej weryfikacji ofert pracy. Każde ogłoszenie przechodzi przez sześć warstw analizy zanim pojawi się pytanie "czy warto aplikować".

---

## v0.9.2 — Stabilność, kompatybilność Python 3.9 i poprawki techniczne

- Kompatybilność z Python 3.9: `Optional[sqlite3.Row]` zamiast operatora `|` (PEP 604 dostępny dopiero od 3.10)
- Naprawiony dekorator `login_required` — poprawny pattern `functools.wraps` z `return decorated`
- Naprawiona walidacja JSON w analizatorze — warunek `start > end - 1` eliminuje edge case z pustym lub odwróconym zakresem
- Obsługa `sqlite3.IntegrityError` w `/analyze`, `/reanalyze` i eksporcie CSV
- Indeksy bazy danych na kolumnach `user_id`, `source_hash`, `analyzed_at` — szybsze zapytania przy większej historii
- Timeout API zwiększony do 120s — margines dla złożonych analiz z rozszerzonym myśleniem
- Limit rozmiaru odpowiedzi scrapera: 5MB — ochrona przed bardzo dużymi stronami
- Lepsza walidacja URL w `normalize_url` i `scraper.fetch`
- Komunikaty błędów API wzbogacone o nazwę modelu dla łatwiejszego debugowania

---

## v0.9.1 — Link do ogłoszenia w nagłówku modala i korekta skali fontów

- Link do ogłoszenia wyciągnięty na wierzch w nagłówku karty modala — widoczny bezpośrednio pod podsumowaniem werdyktu; priorytet: `job_url`, fallback: `source_full` jeśli jest URLem
- Przywrócona skala fontów `--fs-base-scale: 16px` (omyłkowo zmniejszona do 14px w v0.9)

---

## v0.9 — Filtrowanie historii, przeprojektowanie kart i ujednolicenie wyglądu

- Filtr kategorii w historii analiz: przyciski toggle dla każdego z 6 statusów, dowolne kombinacje, stan zapamiętywany w `localStorage`
- Badge'e bez tła — wyłącznie obramowanie i kolor tekstu; podświetlenie wiersza przejmuje rolę kolorowego tła
- Nowa klasa wiersza `row-warning` (żółte tło) dla ofert "Wymaga uwagi"; `row-rejected-soft` (lekkie czerwone tło) dla odrzuconych przez model
- Nagłówek karty ogłoszenia przestawiony na układ pionowy: etykieta → stanowisko → firma → podsumowanie → powód odrzucenia → data
- Kolumny Rola i Firma zamienione miejscami w tabeli historii i ostatnich analiz na dashboardzie
- Nieznana firma oznaczana jako "Nieznana" zamiast "—"; model zobowiązany do wyjaśnienia braku nazwy w podsumowaniu werdyktu
- Atrybut `data-category` na wierszach tabeli historii — umożliwia filtrowanie bez przeglądania klas CSS

---

## v0.8 — Angielskie nazwy zmiennych i logika potwierdzenia odrzucenia

- Migracja wszystkich nazw kolumn bazy, kluczy JSON i klas CSS na angielskie
- Nowe pole `verdict_confirmed` rozróżnia automatyczne odrzucenia (Lista Zero) od odrzuceń modelu wymagających potwierdzenia
- Dropdown werdyktu pokazuje dwa stany odrzucenia: "Odrzucona (model)" i "Odrzucona — potwierdź"
- Wizualne oznaczenie wierszy w tabelach historii i dashboardu: przekreślenie dla potwierdzonych odrzuceń, lżejsze tło dla niepotwierdzonych, zielone tło dla zgłoszonych podań
- Migracje danych idempotentne — istniejące bazy aktualizowane automatycznie przy starcie

---

## v0.7 — Status aplikowania i zarządzanie rekordami

- Dodano status "Zgłoszenie wysłane" z datą w widoku analizy i kolumną w historii
- Dodano możliwość usunięcia ogłoszenia z bazy z poziomu widoku analizy
- Dodano możliwość ręcznego dodania linku do ogłoszenia po analizie z wklejonej treści
- Dodano potwierdzenie linku klawiszem Enter
- Klikalny cały wiersz w historii analiz

---

## v0.6 — Lista żółta i ręczna zmiana werdyktu

- Dodano "Listę żółtą" — kategorie graniczne które wymuszają werdykt "wymaga uwagi" bez przerywania analizy
- Lista żółta konfigurowalna per użytkownik w Ustawieniach
- Dodano dropdown do ręcznej zmiany werdyktu w widoku analizy (bez przeładowania strony)
- Dodano "Analizuj ponownie" w widoku analizy — uruchamia nową analizę z zapisanego źródła
- Nowe pole `lista_zolta_hit` i `lista_zolta_reason` w JSONie zwracanym przez API

---

## v0.5 — Dowód z ogłoszenia i weryfikacja źródła

- Dodano zasadę dowodu w system prompcie: model zobowiązany do cytatu z ogłoszenia przy każdej fladze i odrzuceniu
- Nowe pole `evidence` przy warstwach ze statusem "flaga" — wyświetlane w widoku analizy
- Dodano `lista_zero_evidence` dla identyfikacji ukrytych pracodawców
- Komunikat statusu przed analizą: zielony (nowe ogłoszenie) lub żółty (duplikat)
- Nowy endpoint `/check_source` — weryfikacja bazy bez wywoływania API

---

## v0.4 — Wykrywanie duplikatów i źródło ogłoszenia

- Wykrywanie duplikatów na podstawie SHA-256 treści/linku przed wysłaniem do API
- Nowe kolumny w bazie: `source_full` (pełna treść), `source_hash` (hash do deduplicacji)
- Widok analizy: sekcja "Źródło ogłoszenia" z pełną treścią lub linkiem
- Baner duplikatu z opcją "Analizuj ponownie" lub "Zobacz poprzednią analizę"
- Migracja bazy automatyczna przy starcie — stare rekordy zachowane

---

## v0.3 — Zmienne typograficzne i historia analiz

- Wszystkie rozmiary fontów zastąpione zmiennymi CSS (`--fs-2xs` do `--fs-4xl`) w `:root`
- Jedna zmienna `--fs-base-scale` do skalowania całego interfejsu
- Widok szczegółowy analizy (`/job/<id>`) z kolapsowalnymi warstwami
- Historia analiz z tabelą statusów (kolorowe kropki per warstwa)
- Eksport CSV z poziomu Ustawień i nawigacji

---

## v0.2 — Deployment i multi-user

- Obsługa wielu użytkowników z osobnymi profilami (CV, Lista Zero, kryteria)
- System rejestracji: pierwsze konto bez tokenu, kolejne przez `INVITE_TOKEN`
- SQLite jako baza danych zamiast CSV
- Skrypty `run.sh`, `stop.sh`, `restart.sh` dla hostingu współdzielonego
- `deploy.sh` — deployment na serwer przez SSH z rsync
- Kron co 5 minut dla auto-restartu aplikacji

---

## v0.1 — Fundament

- Lokalny Flask server z interfejsem webowym
- Sześć warstw analizy: triage, produktowa, biznesowa, reputacyjna, wartości, dopasowanie
- Lista Zero — automatyczne odrzucenie bez analizy
- System promptu budowany dynamicznie z profilu użytkownika
- Obsługa wejścia przez URL lub wklejoną treść ogłoszenia
- Identyfikacja ukrytego pracodawcy za pośrednikiem rekrutacyjnym
- `start.bat` / `start.sh` — uruchomienie lokalne jednym kliknięciem
