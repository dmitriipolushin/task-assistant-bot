# Документация базы данных Telegram бота

## Обзор

Telegram бот использует **PostgreSQL** базу данных для хранения всех данных о сообщениях, задачах и пользователях. База данных автоматически создается при первом запуске приложения.

## Подключение к базе данных

### Переменные окружения

Бот поддерживает два способа настройки подключения к PostgreSQL:

#### Способ 1: Единая строка подключения
```bash
DATABASE_URL=postgresql://username:password@host:port/database_name
```

#### Способ 2: Отдельные параметры
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=tasktracker
DB_USER=postgres
DB_PASSWORD=your_password
```

### Автоматическое создание схемы

При первом запуске бот автоматически:
- Создает все необходимые таблицы
- Создает индексы для оптимизации
- Инициализирует схему базы данных

## Структура таблиц

### 1. Таблица `raw_messages`

Хранит все входящие сообщения от клиентов.

```sql
CREATE TABLE raw_messages (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    client_username TEXT,
    client_first_name TEXT,
    message_text TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_processed BOOLEAN DEFAULT FALSE
);
```

**Поля:**
- `id` - Уникальный идентификатор сообщения (SERIAL)
- `chat_id` - ID чата в Telegram
- `message_id` - ID сообщения в Telegram
- `client_username` - Username клиента (может быть NULL)
- `client_first_name` - Имя клиента (может быть NULL)
- `message_text` - Текст сообщения
- `timestamp` - Время получения сообщения
- `is_processed` - Флаг обработки сообщения

**Индексы:**
```sql
CREATE INDEX idx_raw_messages_chat_id ON raw_messages(chat_id);
CREATE INDEX idx_raw_messages_timestamp ON raw_messages(timestamp);
CREATE INDEX idx_raw_messages_is_processed ON raw_messages(is_processed);
```

### 2. Таблица `processed_tasks`

Хранит задачи, извлеченные из сообщений с помощью GPT.

```sql
CREATE TABLE processed_tasks (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    task_text TEXT NOT NULL,
    source_messages TEXT,
    processing_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_date DATE DEFAULT CURRENT_DATE
);
```

**Поля:**
- `id` - Уникальный идентификатор задачи (SERIAL)
- `chat_id` - ID чата, где была создана задача
- `task_text` - Текст извлеченной задачи
- `source_messages` - JSON массив ID исходных сообщений
- `processing_timestamp` - Время обработки GPT
- `created_date` - Дата создания задачи

**Индексы:**
```sql
CREATE INDEX idx_processed_tasks_chat_id ON processed_tasks(chat_id);
CREATE INDEX idx_processed_tasks_created_date ON processed_tasks(created_date);
```

### 3. Таблица `pending_prioritization`

Хранит задачи, ожидающие выбора приоритета.

```sql
CREATE TABLE pending_prioritization (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    task_text TEXT NOT NULL,
    selected_priority TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Поля:**
- `id` - Уникальный идентификатор (SERIAL)
- `chat_id` - ID чата
- `task_text` - Текст задачи
- `selected_priority` - Выбранный приоритет (может быть NULL)
- `created_at` - Время создания записи

**Индексы:**
```sql
CREATE INDEX idx_pending_chat_id ON pending_prioritization(chat_id);
```

### 4. Таблица `staff_members`

Хранит список сотрудников студии.

```sql
CREATE TABLE staff_members (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE,
    user_id BIGINT UNIQUE
);
```

**Поля:**
- `id` - Уникальный идентификатор (SERIAL)
- `username` - Username сотрудника (уникальный)
- `user_id` - ID пользователя в Telegram (уникальный)

## Основные операции

### Инициализация базы данных

```python
from database.models import initialize_database

# Создает все таблицы и индексы
initialize_database()
```

### Получение соединения

```python
from database.models import get_connection

# Получает соединение с PostgreSQL
conn = get_connection()
```

### Контекстный менеджер для операций

```python
from database.operations import db_cursor

with db_cursor() as cur:
    cur.execute("SELECT * FROM raw_messages WHERE chat_id = %s", (chat_id,))
    # Автоматический commit и закрытие соединения
```

## Ключевые функции

### Обработка сообщений

- `save_raw_message()` - Сохранение входящего сообщения
- `get_unprocessed_messages_last_hour()` - Получение необработанных сообщений за час
- `get_unprocessed_messages_between()` - Получение сообщений за период

### Управление задачами

- `save_processed_task_batch()` - Сохранение обработанной задачи
- `enqueue_pending_prioritization()` - Постановка задачи в очередь приоритизации
- `set_pending_priority()` - Установка приоритета для задачи
- `update_pending_task_text()` - Обновление текста задачи
- `delete_pending()` - Удаление задачи из очереди

### Просмотр данных

- `get_all_tasks()` - Получение всех задач для чата
- `get_pending_for_chat()` - Получение задач в очереди приоритизации
- `get_tasks_by_date()` - Получение задач за определенную дату

### Управление персоналом

- `is_staff_member()` - Проверка, является ли пользователь сотрудником
- `get_all_chat_ids()` - Получение всех активных чатов

## Логика обработки сообщений

### Жизненный цикл сообщения

1. **Получение**: Сообщение сохраняется в `raw_messages` с `is_processed = FALSE`
2. **Обработка GPT**: Сообщения анализируются пакетно с помощью GPT
3. **Извлечение задач**: Задачи сохраняются в `processed_tasks`
4. **Очередь приоритизации**: Задачи помещаются в `pending_prioritization`
5. **Выбор приоритета**: Пользователь выбирает приоритет через inline-кнопки
6. **Завершение**: После выбора приоритета задача добавляется в Google Sheets

### Важные особенности

- **Сообщения НЕ помечаются как обработанные** сразу после GPT
- **Сообщения помечаются как обработанные** только после выбора приоритета
- **Команда `/parse`** игнорирует флаг `is_processed`
- **Команда `/process_now`** обрабатывает сообщения за последний час

## Производительность

### Индексы

Все основные запросы оптимизированы с помощью индексов:
- По `chat_id` для фильтрации по чатам
- По `timestamp` для временных диапазонов
- По `is_processed` для фильтрации необработанных сообщений
- По `created_date` для отчетов по датам

### Оптимизации

- Использование `SERIAL` для автоинкрементных ID
- `BIGINT` для Telegram ID (поддержка больших чисел)
- `TIMESTAMP` для точного времени
- `BOOLEAN` для флагов состояния

## Безопасность

### Защита от SQL-инъекций

Все запросы используют параметризованные запросы:
```python
cur.execute("SELECT * FROM raw_messages WHERE chat_id = %s", (chat_id,))
```

### Права доступа

- Проверка сотрудников через `is_staff_member()`
- Разграничение доступа к командам по ролям
- Валидация входных данных

## Мониторинг и логирование

### Логирование операций

Все операции с базой данных логируются:
- Успешные операции (INFO)
- Ошибки подключения (ERROR)
- Проблемы с запросами (ERROR)

### Отслеживание производительности

- Время выполнения запросов
- Количество обработанных сообщений
- Статистика по чатам и задачам
