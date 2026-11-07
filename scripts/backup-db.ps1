# Резервная копия Postgres из контейнера Compose.
# Запуск из любой папки: pwsh scripts/backup-db.ps1
# Файл custom-формата pg_dump кладётся в backups/ и не коммитится.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$OutDir = Join-Path $Root "backups"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Name = "fitness-{0}.dump" -f (Get-Date -Format "yyyyMMdd-HHmmss")
$Remote = "/tmp/$Name"
$Local = Join-Path $OutDir $Name

docker compose exec -T db pg_dump -U fitness -d fitness --format=custom --file=$Remote
if ($LASTEXITCODE -ne 0) { throw "pg_dump завершился с кодом $LASTEXITCODE" }

docker compose cp "db:${Remote}" $Local
if ($LASTEXITCODE -ne 0) { throw "Не удалось скопировать дамп из контейнера" }

docker compose exec -T db rm -f $Remote
Write-Host "Сохранено: $Local"
