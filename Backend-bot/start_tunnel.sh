#!/usr/bin/env bash
# Запускает Cloudflare туннель для порта 8000, обновляет WEBAPP_URL в .env

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
LOG_FILE="/tmp/cloudflared_tunnel.log"

echo "Запускаю Cloudflare туннель..."
cloudflared tunnel --url http://localhost:8000 > "$LOG_FILE" 2>&1 &
TUNNEL_PID=$!

# Ждём пока в логе появится URL (до 30 секунд)
TUNNEL_URL=""
for i in $(seq 1 30); do
    TUNNEL_URL=$(grep -oP 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$LOG_FILE" 2>/dev/null | head -1)
    if [ -n "$TUNNEL_URL" ]; then
        break
    fi
    sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
    echo "Не удалось получить URL туннеля. Лог:"
    cat "$LOG_FILE"
    kill $TUNNEL_PID 2>/dev/null
    exit 1
fi

echo "Туннель запущен: $TUNNEL_URL"

# Обновляем WEBAPP_URL в .env
if grep -q "^WEBAPP_URL=" "$ENV_FILE"; then
    sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=$TUNNEL_URL|" "$ENV_FILE"
else
    echo "WEBAPP_URL=$TUNNEL_URL" >> "$ENV_FILE"
fi

echo "WEBAPP_URL обновлён в .env -> $TUNNEL_URL"
echo ""
echo "Теперь перезапусти бота: python -m app.bot.main"
echo "Нажми Ctrl+C чтобы остановить туннель."
echo ""

wait $TUNNEL_PID
