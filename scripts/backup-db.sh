#!/bin/sh
# Резервная копия Postgres из контейнера Compose.
# Запуск из любой папки: sh scripts/backup-db.sh
# Файл custom-формата pg_dump кладётся в backups/ и не коммитится.

set -eu
cd "$(dirname "$0")/.."

mkdir -p backups
name="fitness-$(date +%Y%m%d-%H%M%S).dump"
remote="/tmp/$name"

docker compose exec -T db pg_dump -U fitness -d fitness --format=custom --file="$remote"
docker compose cp "db:${remote}" "backups/$name"
docker compose exec -T db rm -f "$remote"
echo "Сохранено: backups/$name"
