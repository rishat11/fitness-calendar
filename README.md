# Фитнес-календарь

Дневник силовых тренировок: календарь, сдвиг плана, лог подходов, периодизация и питание по замерам InBody. Техническое задание — в [spec.md](spec.md).

Стек: FastAPI, PostgreSQL, React + TypeScript.

Этап 1 (MVP) закрыт. Работают:
- база и проверка `/health`;
- регистрация, вход, выход, удаление аккаунта и проверка сессии (`/api/auth/*`);
- профиль и настройки (цель, рост, возраст, пол, единицы, тема);
- справочник упражнений и конструктор тренировок;
- календарь: месяц и неделя, цикл по дням недели, перетаскивание, сдвиг плана с предпросмотром и отменой;
- лог подходов (вес, дополнительный вес, повторы, RIR) с автосохранением;
- экран «Сегодня»: тренировка дня и сдвиг;
- экспорт и импорт JSON, CSV записанных тренировок;
- адаптивный каркас от 360 px: нижняя навигация на телефоне, боковая на десктопе, светлая и тёмная тема.

Питание (`/nutrition`): текущие белки, жиры и углеводы, калории считаются сами. Целевое БЖУ — заглушка, пока нет замера InBody.

Справочник упражнений (`/api/exercises`, экран «Упражнения»): создание, быстрое создание, редактирование, архив, поиск. Упражнение, входящее в тренировку, нельзя удалить, его можно только архивировать.

Конструктор тренировок (`/api/workouts`, экран «Тренировки»): список, создание, переименование, копирование, удаление, порядок упражнений и свои подходы (повторы, RIR, отдых) для каждого упражнения. Упражнение можно создать прямо в конструкторе. Правка шаблона не меняет уже поставленный план и записанный факт.

## Что нужно на машине

Проверено на этой машине:

| Инструмент | Версия |
| --- | --- |
| Docker | 29.5.3, Compose v5.1.4 |
| Python | 3.13.7 (также установлен 3.12.3) |
| uv | 0.11.7 |
| Node.js | 22.18.0, npm 10.9.3 |

Нужны Docker Desktop, Python 3.12 или новее, [uv](https://docs.astral.sh/uv/) и Node.js 22 (на этой версии работает CI).

## Окружение

```powershell
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Вставьте сгенерированную строку в `SECRET_KEY` внутри `.env`. Заготовка `change-me-to-a-long-random-string` не даст приложению запуститься. Файл `.env` не коммитится.

Переменные в `.env`:

- `DATABASE_URL` — в Compose хост `db`, для запуска API на хосте `127.0.0.1:5433`.
- `SECRET_KEY` — ключ подписи cookie сессии, минимум 32 символа.
- `COOKIE_SECURE` — в `.env` стоит `false`: локальный сайт открывается по HTTP, и без этого браузер не сохранит cookie. В коде по умолчанию `true`, за HTTPS оставьте его.
- `TRUSTED_PROXIES` — IP или CIDR обратного прокси через запятую. Пусто — заголовок `X-Forwarded-For` не читается.

## Запуск в Docker

Из корня проекта, при уже созданном `.env`:

```powershell
docker compose up --build
```

- Сайт: http://localhost:5173 — откроется экран входа, а если вы уже вошли, экран «Сегодня».
- API: http://localhost:8000/health — ответ `{"status":"ok"}`. Если база недоступна, ответ `503` и `{"status":"unavailable"}`.
- Postgres с хоста: `localhost:5433`, пользователь и база `fitness`, пароль `fitness`. Внутри сети Compose порт по-прежнему 5432, хост в `DATABASE_URL` — `db`. На хост публикуется 5433, чтобы не занимать локальный Postgres на 5432.

При каждом старте backend-контейнер сам применяет миграции (`alembic upgrade head`).

Остановить и удалить контейнеры: `docker compose down`. Данные Postgres остаются в томе `pgdata`. Вместе с томом: `docker compose down -v`.

Исходники смонтированы в контейнеры, API и Vite перезагружаются при сохранении файлов. После изменения `backend/pyproject.toml` или `frontend/package.json` пересоберите образы: `docker compose up --build`. Если фронтенд не видит новые пакеты, удалите том `frontend_node_modules`.

Образ backend ставит и dev-зависимости, поэтому из контейнера запускаются тесты и линтер:

```powershell
docker compose exec backend ruff check .
docker compose exec -e TEST_DATABASE_URL=postgresql+asyncpg://fitness:fitness@db:5432/fitness_test backend pytest
```

## Локально без Docker

Postgres должен быть доступен. Удобно поднять только базу: `docker compose up -d db`, затем в том же сеансе PowerShell переопределить адрес. Файл `.env` не меняйте: Compose читает из него хост `db`.

```powershell
cd backend
uv sync
$env:DATABASE_URL = "postgresql+asyncpg://fitness:fitness@127.0.0.1:5433/fitness"
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Во втором окне:

```powershell
cd frontend
npm ci
npm run dev
```

Прокси Vite по умолчанию смотрит на `http://127.0.0.1:8000`. В Compose для этого задано `API_PROXY_TARGET=http://backend:8000`.

## Тесты и линтер

Из каталога `backend`. Адрес по умолчанию — `127.0.0.1:5433`, база `fitness_test`.

```powershell
cd backend
uv sync
$env:TEST_DATABASE_URL = "postgresql+asyncpg://fitness:fitness@127.0.0.1:5433/fitness_test"
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

`TEST_DATABASE_URL` можно не задавать, если подходит адрес по умолчанию.

> **Внимание:** перед тестами `tests/schema_setup.py` удаляет и заново создаёт схему `public` в базе из `TEST_DATABASE_URL`. Не указывайте в этой переменной рабочую базу. Имя базы должно состоять из латинских букв, цифр и `_`.

Тесты поднимают схему через `alembic upgrade head` и проверяют, что модели не расходятся с миграциями (`alembic check`). Покрыто:
- регистрация, вход, выход, `/api/auth/me` без cookie и с подписанной cookie;
- регистрация с уже занятым email (без учёта регистра);
- истёкшая сессия удаляется;
- лимит попыток входа отдельно по IP и по email;
- `X-Forwarded-For` принимается только от доверенного прокси;
- placeholder-значение `SECRET_KEY` отклоняется;
- `/health` отвечает `503`, если база недоступна.

Каталог тестов — `backend/tests`, не `backend/app/tests`.

Фронтенд, из каталога `frontend` (после `npm ci`):

```powershell
cd frontend
npm run lint
npx tsc --noEmit
npm run test
npm run build
```

Скрипт `npm run build` вызывает `tsc --noEmit` и `vite build`. Тесты на Vitest и Testing Library лежат рядом с кодом, например `src/pages/LoginPage.test.tsx`.

### Сквозной сценарий (Playwright)

Из каталога `frontend`, когда Postgres уже доступен (для локального запуска — `docker compose up -d db`). Playwright сам применяет миграции и поднимает API на порту 8010 и Vite на 5174, чтобы не задеть сайт на 5173.

```powershell
cd frontend
npm ci
npx playwright install chromium
npm run e2e
```

Сценарий `e2e/mvp.e2e.ts` проходит ключевой путь приёмки: регистрация, шаблон, цикл в календаре, запись подхода на ширине 360 px, перезагрузка, перетаскивание, сдвиг на +1 день с предпросмотром и отменой, импорт JSON и удаление аккаунта. Отдельная проверка: фокус с клавиатуры на экране входа.

В CI тот же сценарий запускается job `e2e` на чистой базе Postgres.

### CI

Файл `.github/workflows/ci.yml` запускается на `push` и `pull_request`:

- **backend** (Postgres 18 в сервисе): `uv sync --locked`, `ruff check`, `ruff format --check`, `alembic upgrade head`, `pytest`.
- **frontend** (Node 22): `npm ci`, `npm run lint`, `npx tsc --noEmit`, `npx vitest run`, `npx vite build`.
- **e2e** (Postgres 18, Chromium): `npm run e2e` — Playwright поднимает API и Vite и проходит ключевой путь MVP.

## Типы API для фронтенда

Файл `frontend/src/api/schema.d.ts` генерируется из OpenAPI-схемы работающего backend. Перед генерацией поднимите API (`docker compose up -d` или `uv run uvicorn app.main:app --port 8000` в `backend`), затем выполните:

```powershell
cd frontend
npm run generate:api
```

Скрипт читает `http://127.0.0.1:8000/openapi.json`. Перегенерируйте файл после изменения эндпоинтов или схем в backend.

## Миграции

Команды из каталога `backend`. Для запуска на хосте нужен тот же `DATABASE_URL`, что и у локального API. В контейнере переменная уже указывает на сервис `db`.

```powershell
uv run alembic upgrade head
uv run alembic check
uv run alembic revision --autogenerate -m "описание изменения"
```

## Авторизация

API:

- `POST /api/auth/register` — регистрация и сразу вход, `201`;
- `POST /api/auth/login` — вход, `200`, или `401` при неверных данных, `429` при превышении лимита;
- `POST /api/auth/logout` — выход, `204`;
- `GET /api/auth/me` — текущий пользователь, `200` или `401`.

Префикс `/api` нужен, чтобы Vite проксировал запросы и браузер работал с одним origin: cookie не упирается в CORS.

Экраны фронтенда: `/login`, `/register`, `/` («Сегодня»), `/calendar`, `/workouts`, `/workouts/:id`, `/log/:plannedId`, `/exercises`, `/nutrition`, `/settings`. Без входа защищённые экраны редиректят на `/login`.

**Удаление аккаунта.** `DELETE /api/auth/account` с телом `{ "password": "..." }`. Неверный пароль — `401`, тот же лимит попыток, что у входа. Верный пароль удаляет пользователя и все его данные, снимает cookie сессии. Сначала удаляются шаблоны тренировок: пункты шаблона ссылаются на упражнения с запретом удаления, и каскад от пользователя сам по себе упёрся бы в это ограничение. Выгрузка перед удалением — `GET /api/export` на экране «Настройки».

## Доступность

Интерфейс на русском. Цели касания не меньше 44 px. У фокуса с клавиатуры видимое кольцо (`:focus-visible`) в светлой и тёмной теме. Вторичный текст не светлее `slate-600` на светлом фоне и `slate-300` на тёмном, чтобы контраст был не ниже WCAG AA. Календарь переключается кнопками «Месяц» и «Неделя» с клавиатуры; карточку тренировки можно перетащить мышью или пальцем.

## Резервная копия базы

Скрипт вызывает `pg_dump` внутри контейнера Postgres и кладёт custom-дамп в каталог `backups/` (он не коммитится). Compose должен быть запущен (`docker compose up -d db` достаточно).

```powershell
pwsh scripts/backup-db.ps1
```

На Linux и macOS: `sh scripts/backup-db.sh`.

Восстановление в ту же базу `fitness` (текущие данные в базе будут перезаписаны):

```powershell
docker compose cp backups/fitness-ГГГГММДД-ЧЧММСС.dump db:/tmp/restore.dump
docker compose exec -T db pg_restore -U fitness -d fitness --clean --if-exists /tmp/restore.dump
docker compose exec -T db rm -f /tmp/restore.dump
```

`--clean` удаляет объекты перед загрузкой. Если часть команд восстановления сообщит, что объекта ещё нет, это ожидаемо для пустой схемы: смотрите, что в конце нет ошибки подключения и что `/health` снова отвечает `ok`. После восстановления перезапустите backend, если он держит старые соединения: `docker compose restart backend`.

**Сессия.** Cookie `session_id` — случайный токен, подписанный HMAC на `SECRET_KEY`. Cookie `httpOnly`, `SameSite=lax`, `Path=/`. В базу пишется только SHA-256 хеш токена, пароли хранятся как хеши argon2. Без `SECRET_KEY` подделать cookie нельзя, даже если есть доступ на запись в таблицу `sessions`.

**Лимит попыток входа.** Реализован на `slowapi`: `Limiter` с хранилищем `memory://` и стратегией moving-window, правило `10 per 5 minutes` из библиотеки `limits`.

- Лимит проверяется отдельно по IP клиента и по email. Превышение — `429`.
- Считаются только неудачные входы: успешный вход счётчик не увеличивает.
- Счётчики живут в памяти процесса. При перезапуске они сбрасываются, а при нескольких воркерах не разделяются. Поэтому в Compose запущен один процесс uvicorn. Для нескольких воркеров понадобится общее хранилище, например Redis.

**Адрес клиента.** Берётся адрес TCP-соединения. Заголовок `X-Forwarded-For` учитывается только если соединение пришло от адреса из `TRUSTED_PROXIES` (IP или CIDR). Тогда берётся последний адрес в заголовке. Без этого клиент мог бы подменять свой IP и обходить лимит.

**Регистрация.** Повторная регистрация того же email отвечает `409` и прямо говорит, что адрес занят. Для личного сервиса так понятнее. Обратная сторона: по ответу видно, есть ли такой пользователь.
