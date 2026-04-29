# Workflow Git — Job Screener

## Jednorazowa konfiguracja (robisz to raz)

```bash
cd ~/Developer/job-search-due-diligence-tool
chmod +x setup_git.sh
./setup_git.sh
```

Skrypt zapyta o nazwę użytkownika GitHub i utworzy prywatne repozytorium. Jeśli nie masz jeszcze GitHub CLI, zainstaluj: `brew install gh`, a potem `gh auth login`.

---

## Codzienna praca

### Gdy coś zmieniasz lokalnie

```bash
cd ~/Developer/job-search-due-diligence-tool
git add .
git commit -m "co zmieniłem"
git push
```

Kilka przykładów dobrego opisu commita:
- `fix: rozmiar fontów w historii`
- `feat: dodaj filtrowanie po werdykcie`
- `style: zmień kolor tła nagłówka`

### Gdy dostajesz nowe pliki ode mnie

Pobierz plik, zamień lokalnie, a potem:

```bash
git add .
git commit -m "feat: [nazwa funkcji]"
git push
```

---

## Na początku sesji ze mną

Podaj mi link do repozytorium:

```
https://github.com/TWOJA-NAZWA/job-screener
```

Powiem "przeczytaj pliki projektu" — pobiorę aktualne wersje i będę wiedział co się zmieniło od ostatniej sesji.

---

## Przydatne komendy

```bash
# Co się zmieniło od ostatniego commita?
git status

# Historia commitów
git log --oneline

# Wróć do poprzedniej wersji jednego pliku
git checkout HEAD~1 -- templates/base.html

# Sprawdź różnice przed commitem
git diff
```

---

## Czego NIE commitować

Plik `.gitignore` już to obsługuje automatycznie:

- `config.env` — klucz API nigdy nie trafia na GitHub
- `data/screener.db` — dane użytkowników zostają lokalnie
- `venv/` — środowisko Python odtwarza się przez `pip install -r requirements.txt`
