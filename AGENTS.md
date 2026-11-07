# AGENTS.md

Дневник силовых тренировок. Техническое задание — [spec.md](spec.md), как запустить и что уже работает — [README.md](README.md). Этот файл — правила для агента: не дублируй README, следуй командам и границам ниже.

Интерфейс, тексты ошибок API и комментарии к доменным правилам — на русском.

## Стек

- Backend: Python 3.12+, uv, FastAPI, SQLAlchemy 2 (async), asyncpg, Alembic, Pydantic, argon2, slowapi. Линтер — Ruff (длина строки 100, правила E, F, I, UP, B).
- Frontend: React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, React Router, dnd-kit. Проверки — ESLint, `tsc`, Vitest, Playwright.
- База: PostgreSQL 18. Локально через Docker Compose: API `http://localhost:8000`, сайт `http://localhost:5173`, Postgres с хоста `localhost:5433` (внутри сети Compose хост `db`, порт 5432).
- CI: Node 22, `uv sync --locked`, Postgres 18. Файл — `.github/workflows/ci.yml`.

## Команды

Рабочая база в `TEST_DATABASE_URL` будет уничтожена: `tests/schema_setup.py` пересоздаёт схему `public`. Имя базы — только латиница, цифры и `_`. По умолчанию это `fitness_test` на `127.0.0.1:5433`.

Backend, из каталога `backend` (Postgres уже доступен):

```powershell
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run alembic upgrade head
uv run alembic check
```

Один файл: `uv run pytest tests/test_plan.py`. Форматирование с правкой: `uv run ruff format .` и `uv run ruff check --fix .`.

Frontend, из каталога `frontend` (после `npm ci`):

```powershell
npm run lint
npx tsc --noEmit
npm run test
npm run build
npm run e2e
```

`npm run build` уже включает `tsc --noEmit`. E2E сам поднимает API на порту 8010 и Vite на 5174; нужен Postgres и Chromium (`npx playwright install chromium`). Сценарий — `frontend/e2e/mvp.e2e.ts`.

Из контейнеров, если стек уже поднят:

```powershell
docker compose exec backend ruff check .
docker compose exec -e TEST_DATABASE_URL=postgresql+asyncpg://fitness:fitness@db:5432/fitness_test backend pytest
```

## Куда класть код

Backend, каталог `backend/`:

- `app/api/` — HTTP: разбор запроса, коды ответов, `await db.commit()`. Без доменных расчётов.
- `app/services/` — бизнес-логика. Сессию не коммитит (исключение — снятие просроченной сессии в `app/api/deps.py`).
- `app/models/` — таблицы SQLAlchemy. `app/schemas/` — тела и ответы Pydantic.
- `app/api/deps.py` — `DbSession` и `CurrentUser`. Чужой ресурс отвечает 404, как будто его нет.
- `alembic/versions/` — только миграции. `tests/` — HTTP-тесты через `httpx` и живую схему. Каталога `app/tests` нет.

Frontend, каталог `frontend/src/`:

- `pages/` — экраны. `components/` — общие куски интерфейса.
- `features/<область>/` — хуки запросов, чистые функции и их тесты рядом с кодом.
- `api/client.ts` — вызовы API и типы из OpenAPI. `api/schema.d.ts` не править руками.
- Маршруты собраны в `App.tsx`. Пункты меню — `navigation.ts`. Неготовые разделы показывают «Скоро» (`ComingSoonPage`); питание (`/nutrition`) — такой раздел.

Новый эндпоинт: схема, сервис, роут в `app/main.py`, тест в `backend/tests`, затем `npm run generate:api` при запущенном API на порту 8000 и коммит обновлённого `schema.d.ts`.

## Домен, который легко сломать

- Каждый запрос к данным фильтруется по текущему пользователю.
- Даты плана и лога — календарные `date` без часового пояса. Моменты вроде `created_at` — `timestamptz`.
- Правка шаблона тренировки не меняет уже поставленный план и записанный факт.
- Упражнение, которое входит в шаблон, нельзя удалить — только архив.
- Сдвиг плана трогает только запланированное. Выполненное и пропущенное остаётся. Перед применением есть предпросмотр, сдвиг можно отменить.
- Подсказка прогрессии ничего не меняет сама: пользователь принимает или отклоняет её.
- Пароли — argon2. В `sessions` лежит только SHA-256 токена. Cookie `session_id` — httpOnly, SameSite=lax. `SECRET_KEY` короче 32 символов и значение-заглушка из `.env.example` отклоняются.
- Лимит входа — в памяти процесса (`slowapi`, `memory://`). Поэтому API — один процесс uvicorn. `X-Forwarded-For` учитывается только от адресов из `TRUSTED_PROXIES`.
- Удаление аккаунта сначала снимает шаблоны: пункты ссылаются на упражнения с запретом удаления, каскад от пользователя в это упирается.

## Стиль

- Повторяй соседний модуль той же области, а не общий шаблон из другого проекта.
- В Python — аннотации типов, `async` для ввода-вывода, `X | None` вместо `Optional`.
- Во фронтенде — функциональные компоненты и именованные экспорты, как в существующих страницах. Серверное состояние — TanStack Query.
- Тексты для человека — по-русски. Цель касания от 44 px. Видимый фокус `:focus-visible` в светлой и тёмной теме. Вторичный текст не светлее `slate-600` на светлом фоне и `slate-300` на тёмном.

## Тесты

- Бэкенд ходит в приложение через ASGI и Postgres. Схему поднимает Alembic, расхождение моделей и миграций ловит `alembic check`. Базу не мокать.
- Логику без HTTP клади рядом с существующими `test_*_logic.py`.
- Фронтенд: Vitest и Testing Library рядом с модулем (`*.test.ts`, `*.test.tsx`). Сквозной путь приёмки — Playwright, не дублируй его десятком мелких e2e.
- Меняешь поведение — обнови тест этого поведения. Прогони затронутый набор, а не только линтер.

## Границы

Всегда:

- Схема меняется миграцией Alembic, затем `alembic check` и тест. Модель без миграции не оставляй.
- После изменения контракта API перегенерируй `frontend/src/api/schema.d.ts`.
- Секреты читай из окружения. `.env` не коммить и не вставляй в ответы.

Сначала спроси:

- Новая production-зависимость.
- Ломающее изменение контракта API, cookie или формата экспорта JSON.
- Смена способа хранения сессий, лимита входа или числа воркеров uvicorn.

Никогда:

- Не указывай рабочую базу в `TEST_DATABASE_URL`.
- Не коммить `.env`, дампы из `backups/`, `node_modules`, `.venv`.
- Не ослабляй проверку владельца ресурса и не отдавай 403 на чужой id там, где сейчас 404.
- Не пиши бизнес-правила в роуты и не вызывай `commit` из сервисов.
- Не правь `frontend/src/api/schema.d.ts` вручную.
