#!/usr/bin/env bash
# Пересобирает фронтенд и копирует в папку бэкенда

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../booking-bot-frontend"
BUILD_DST="$SCRIPT_DIR/frontend_build"

echo "Сборка фронтенда..."
cd "$FRONTEND_DIR"
npm run build

echo "Копирование в $BUILD_DST..."
rm -rf "$BUILD_DST"
cp -r build "$BUILD_DST"

echo "Готово. Перезапусти uvicorn если нужно."
