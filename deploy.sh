#!/bin/bash
# deploy.sh — deployment na hosting współdzielony (lh.pl, DirectAdmin)
# Użycie: ./deploy.sh lhpl /pelna/sciezka/na/serwerze
#
# Przed użyciem skonfiguruj ~/.ssh/config:
#   Host lhpl
#     HostName TWOJE-IP
#     User TWOJ-LOGIN-FTP
#     Port 40022

set -e

SSH_TARGET="${1:-lhpl}"
REMOTE_DIR="${2:-}"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$REMOTE_DIR" ]; then
  echo "BŁĄD: Podaj ścieżkę na serwerze jako drugi argument."
  echo "Użycie: ./deploy.sh lhpl /home/login/jobscreener"
  exit 1
fi

if [[ "$REMOTE_DIR" != /* ]]; then
  echo "BŁĄD: Ścieżka musi zaczynać się od /  (np. /home/login/jobscreener)"
  echo "Podałeś: $REMOTE_DIR"
  exit 1
fi

echo "=== Job Screener Deploy ==="
echo "Cel: $SSH_TARGET:$REMOTE_DIR"
echo ""

echo "→ Tworzę katalogi..."
ssh "$SSH_TARGET" "mkdir -p $REMOTE_DIR/data $REMOTE_DIR/templates"

echo "→ Kopiuję pliki..."
rsync -az \
  --exclude='data/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.git/' \
  --exclude='venv/' \
  --exclude='*.db' \
  "$LOCAL_DIR/" "$SSH_TARGET:$REMOTE_DIR/"
echo "→ Pliki skopiowane."

echo "→ Nadaję uprawnienia do skryptów (jeśli możliwe)..."
ssh "$SSH_TARGET" "chmod +x $REMOTE_DIR/run.sh $REMOTE_DIR/stop.sh $REMOTE_DIR/restart.sh 2>/dev/null || true"
echo "   (jeśli noexec — użyj 'bash run.sh' zamiast './run.sh')"

echo "→ Instaluję zależności Python..."
ssh "$SSH_TARGET" "cd $REMOTE_DIR && python3 -m venv venv && venv/bin/python3 -m pip install --upgrade pip --quiet && venv/bin/python3 -m pip install flask gunicorn --quiet && echo 'OK'"

echo "→ Konfiguruję cron..."
CRON_LINE="*/5 * * * * [ ! -f $REMOTE_DIR/data/app.pid ] && bash $REMOTE_DIR/run.sh >> $REMOTE_DIR/data/cron.log 2>&1"
ssh "$SSH_TARGET" "( crontab -l 2>/dev/null | grep -v '$REMOTE_DIR' ; echo '$CRON_LINE' ) | crontab -"
echo "→ Cron skonfigurowany."

SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null || echo "zmien-na-losowy-ciag")
INVITE=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))' 2>/dev/null || echo "twoj-token")

echo ""
echo "=== Deploy zakończony ==="
echo ""
echo "Następny krok — utwórz config.env na serwerze:"
echo ""
echo "  ssh $SSH_TARGET"
echo "  nano $REMOTE_DIR/config.env"
echo ""
echo "  Zawartość:"
echo "  ANTHROPIC_API_KEY=sk-ant-TWOJ-KLUCZ-TUTAJ"
echo "  SECRET_KEY=$SECRET"
echo "  INVITE_TOKEN=$INVITE"
echo "  NO_BROWSER=1"
echo "  PORT=5000"
echo ""
echo "Potem uruchom aplikację:"
echo "  ssh $SSH_TARGET 'bash $REMOTE_DIR/run.sh'"
echo ""
echo "Przydatne komendy:"
echo "  Uruchom:   ssh $SSH_TARGET 'bash $REMOTE_DIR/run.sh'"
echo "  Zatrzymaj: ssh $SSH_TARGET 'bash $REMOTE_DIR/stop.sh'"
echo "  Restart:   ssh $SSH_TARGET 'bash $REMOTE_DIR/restart.sh'"
echo "  Logi:      ssh $SSH_TARGET 'tail -50 $REMOTE_DIR/data/error.log'"