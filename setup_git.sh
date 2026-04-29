#!/bin/bash
# setup_git.sh — jednorazowa konfiguracja Git i GitHub
# Uruchom raz, na początku, z katalogu projektu.
# Wymagane: zainstalowane git i gh (GitHub CLI)

set -e

echo "=== Konfiguracja Git dla Job Screener ==="
echo ""

# Sprawdź czy git jest zainstalowany
if ! command -v git &> /dev/null; then
  echo "BŁĄD: git nie jest zainstalowany."
  echo "Mac: brew install git"
  exit 1
fi

# Sprawdź czy gh jest zainstalowany
if ! command -v gh &> /dev/null; then
  echo "BŁĄD: GitHub CLI (gh) nie jest zainstalowany."
  echo "Mac: brew install gh"
  echo "Następnie: gh auth login"
  exit 1
fi

# Inicjuj repo jeśli jeszcze nie istnieje
if [ ! -d ".git" ]; then
  git init
  echo "✓ Repozytorium Git zainicjowane"
else
  echo "✓ Repozytorium Git już istnieje"
fi

# Ustaw główną gałąź na main
git checkout -b main 2>/dev/null || git checkout main 2>/dev/null || true

# Dodaj wszystkie pliki (z pominięciem tych z .gitignore)
git add .

# Pierwszy commit
git commit -m "init: Job Screener v0.7" 2>/dev/null || echo "✓ Nic do commitowania"

# Utwórz prywatne repo na GitHub i wypchnij
echo ""
echo "Tworzę prywatne repozytorium na GitHub..."
gh repo create job-screener \
  --private \
  --source=. \
  --remote=origin \
  --push \
  --description "Etyczna weryfikacja ofert pracy"

echo ""
echo "=== Gotowe ==="
echo ""
echo "Twoje repozytorium:"
gh repo view --json url -q .url
echo ""
echo "Jak pracować na co dzień:"
echo ""
echo "  Po każdej zmianie:"
echo "  git add ."
echo "  git commit -m 'opis co zmieniłem'"
echo "  git push"
echo ""
echo "  Na początku sesji z Claude — podaj link do repo:"
echo "  https://github.com/TWOJA-NAZWA/job-screener"
