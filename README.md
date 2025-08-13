## Telegram TaskTracker Bot

Бот для сбора клиентских задач в групповых чатах, пакетной обработки раз в час через GPT-5 и ежедневных отчетов.

### Требования
- Python 3.11+

### Установка
1. Создай и активируй виртуальное окружение
   - macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`
   - Windows: `py -3 -m venv .venv && .venv\\Scripts\\activate`
2. Установка зависимостей
   - `pip install -r requirements.txt`
3. Создай `.env` по примеру `.env.example`

### Запуск
```
python main.py
```

### Переменные окружения
- `BOT_TOKEN` — токен Telegram бота
- `OPENAI_API_KEY` — ключ OpenAI
- `GPT_MODEL` — модель OpenAI, настройте доступную для вашего проекта
- `TIMEZONE` — временная зона (по умолчанию Europe/Moscow)
- `DAILY_REPORT_TIME` — время ежедневного отчета, формат HH:MM (по умолчанию 09:00)
- `DATABASE_PATH` — путь к SQLite базе (по умолчанию ./data/bot.db)
  

### Docker
Запуск локально:
```
docker compose up --build
```

### Докплой (Dokploy)
- Создай приложение (Dockerfile или Compose)
- Добавь переменные окружения
- Подключи volume для `/app/data`

### Команды бота
- `/tasks [page]` — список задач с пагинацией (20 на страницу)
- `/process_now` — форсировать обработку часа (только сотрудники)
- `/parse <days>` — обработать все необработанные сообщения за последние N дней (только сотрудники)

### Функциональность
- Сбор сообщений: текст из групповых чатов сохраняется в `raw_messages`; сообщения сотрудников из `config/staff_list.py` игнорируются.
- Пакетная обработка (GPT-5): раз в час берутся сообщения за последний час, объединяются в контекст, отправляются в GPT; извлеченные задачи сохраняются в `processed_tasks`, исходные сообщения помечаются обработанными.
- Ежедневные отчеты: в `DAILY_REPORT_TIME` по `TIMEZONE` бот отправляет сводку задач за предыдущий день в каждый активный чат.
- Ограничения Telegram: длинные ответы автоматически бьются на сообщения по 4096 символов.

### Архитектура
- `main.py` — точка входа, регистрация хендлеров, запуск планировщика, graceful shutdown.
- `bot/handlers.py` — обработка текстов, `/tasks`, `/process_now`, `/parse`.
- `bot/scheduler.py` — ежечасная обработка и ежедневные отчеты, а также обработка произвольного диапазона для `/parse`.
- `bot/gpt_processor.py` — форматирование контекста и вызов OpenAI (модель `gpt-5`) с retry (exponential backoff).
- `database/models.py` — инициализация SQLite, индексы.
- `database/operations.py` — CRUD и выборки (по дате, диапазону, необработанные, подсчет).
- `utils/formatters.py` — форматирование списков задач и отчетов.

### База данных (SQLite)
- `raw_messages(id, chat_id, message_id, client_username, client_first_name, message_text, timestamp, is_processed)`
- `processed_tasks(id, chat_id, task_text, source_messages(JSON), processing_timestamp, created_date)`
- `staff_members(id, username UNIQUE, user_id UNIQUE)`
- Индексы: по `chat_id`, `timestamp`, `is_processed`, `created_date`.

### Планировщик
- Ежечасная задача: обрабатывает накопившиеся сообщения за последний час для каждого чата.
- Ежедневный отчет: отправляет отчет за предыдущий день по чату.
- `/process_now`: немедленная обработка последнего часа.
- `/parse <days>`: обработка за диапазон `[now - days, now]`.

### Логирование и запуск в контейнере
- Логи — в stdout c уровнями; Dockerfile содержит healthcheck для SQLite.
- Персистентность БД — volume на `/app/data`.

### Примеры
```
/tasks
/tasks 2
/process_now
/parse 3
```


