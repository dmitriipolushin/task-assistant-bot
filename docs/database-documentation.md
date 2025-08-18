# Документация базы данных Telegram бота

## 1. Обзор

База данных Telegram бота построена на SQLite3 и предназначена для хранения сообщений от клиентов, извлеченных задач и управления процессом их приоритизации.

## 2. Архитектура базы данных

### 2.1 Технологии
- **СУБД**: SQLite3
- **Типы данных**: Поддержка DATETIME, BOOLEAN, TEXT, INTEGER
- **Индексы**: Оптимизированные индексы для быстрого поиска
- **Соединения**: Автоматическое управление через контекстные менеджеры

### 2.2 Структура файлов
- **models.py**: Схема базы данных и инициализация
- **operations.py**: Операции CRUD и бизнес-логика
- **База данных**: SQLite файл (по умолчанию `./data/bot.db`)

## 3. Схема базы данных

### 3.1 Таблица `raw_messages`

Хранит все входящие сообщения от клиентов до их обработки.

```sql
CREATE TABLE raw_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    client_username TEXT,
    client_first_name TEXT,
    message_text TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_processed BOOLEAN DEFAULT 0
);
```

**Поля:**
- `id` - Уникальный идентификатор записи
- `chat_id` - ID чата Telegram
- `message_id` - ID сообщения в Telegram
- `client_username` - Username клиента (может быть NULL)
- `client_first_name` - Имя клиента (может быть NULL)
- `message_text` - Текст сообщения
- `timestamp` - Время получения сообщения (UTC)
- `is_processed` - Флаг обработки (0 - не обработано, 1 - обработано)

**Индексы:**
- `idx_raw_messages_chat_id` - по полю `chat_id`
- `idx_raw_messages_timestamp` - по полю `timestamp`
- `idx_raw_messages_is_processed` - по полю `is_processed`

### 3.2 Таблица `processed_tasks`

Хранит задачи, извлеченные из сообщений с помощью GPT.

```sql
CREATE TABLE processed_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    task_text TEXT NOT NULL,
    source_messages TEXT,
    processing_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_date DATE DEFAULT (DATE('now'))
);
```

**Поля:**
- `id` - Уникальный идентификатор задачи
- `chat_id` - ID чата, где была извлечена задача
- `task_text` - Текст извлеченной задачи
- `source_messages` - JSON массив ID исходных сообщений
- `processing_timestamp` - Время обработки задачи
- `created_date` - Дата создания задачи (YYYY-MM-DD)

**Индексы:**
- `idx_processed_tasks_chat_id` - по полю `chat_id`
- `idx_processed_tasks_created_date` - по полю `created_date`

### 3.3 Таблица `pending_prioritization`

Хранит задачи, ожидающие выбора приоритета сотрудниками.

```sql
CREATE TABLE pending_prioritization (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    task_text TEXT NOT NULL,
    selected_priority TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Поля:**
- `id` - Уникальный идентификатор записи
- `chat_id` - ID чата
- `task_text` - Текст задачи
- `selected_priority` - Выбранный приоритет (может быть NULL)
- `created_at` - Время создания записи

**Индексы:**
- `idx_pending_chat_id` - по полю `chat_id`

### 3.4 Таблица `staff_members`

Хранит список сотрудников студии с правами доступа.

```sql
CREATE TABLE staff_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    user_id INTEGER UNIQUE
);
```

**Поля:**
- `id` - Уникальный идентификатор сотрудника
- `username` - Username в Telegram (уникальный)
- `user_id` - ID пользователя в Telegram (уникальный)

## 4. Основные операции

### 4.1 Управление сообщениями

#### Сохранение сырого сообщения
```python
def save_raw_message(
    chat_id: int,
    message_id: int,
    client_username: Optional[str],
    client_first_name: Optional[str],
    message_text: str,
    timestamp: Optional[datetime] = None
) -> int
```

#### Получение необработанных сообщений за час
```python
def get_unprocessed_messages_last_hour(
    chat_id: int, 
    now_utc: Optional[datetime] = None
) -> List[dict]
```

#### Получение необработанных сообщений в диапазоне
```python
def get_unprocessed_messages_between(
    chat_id: int,
    since_utc: datetime,
    until_utc: datetime
) -> List[dict]
```

#### Отметка сообщений как обработанных
```python
def mark_messages_processed(message_ids: Iterable[int]) -> int
```

### 4.2 Управление задачами

#### Сохранение обработанной задачи
```python
def save_processed_task_batch(
    chat_id: int, 
    task_text: str, 
    source_message_ids: Sequence[int]
) -> int
```

#### Получение задач по дате
```python
def get_tasks_by_date(chat_id: int, date_str: str) -> List[dict]
```

#### Получение всех задач чата
```python
def get_all_tasks(chat_id: int) -> List[dict]
```

#### Подсчет общего количества задач
```python
def get_total_tasks_count(chat_id: int) -> int
```

### 4.3 Управление приоритизацией

#### Постановка задачи в очередь приоритизации
```python
def enqueue_pending_prioritization(chat_id: int, task_text: str) -> int
```

#### Установка приоритета для задачи
```python
def set_pending_priority(item_id: int, priority: str) -> None
```

#### Получение задач, ожидающих приоритизации
```python
def get_pending_for_chat(chat_id: int) -> List[dict]
```

#### Получение задачи по ID
```python
def get_pending_by_id(item_id: int) -> Optional[dict]
```

#### Удаление задачи из очереди
```python
def delete_pending(item_id: int) -> None
```

### 4.4 Управление сотрудниками

#### Проверка статуса сотрудника
```python
def is_staff_member(username: Optional[str], user_id: Optional[int]) -> bool
```

**Логика проверки:**
1. Проверка по hardcoded спискам (`STAFF_USER_IDS`, `STAFF_USERNAMES`)
2. Проверка по базе данных (`staff_members` таблица)
3. Возврат `True` если пользователь найден в любом из источников

### 4.5 Аналитические запросы

#### Получение всех ID чатов
```python
def get_all_chat_ids() -> List[int]
```

#### Получение чатов с необработанными сообщениями
```python
def get_chats_with_unprocessed_messages_last_hour(
    now_utc: Optional[datetime] = None
) -> List[int]
```

## 5. Управление соединениями

### 5.1 Контекстный менеджер
```python
@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        yield conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        LOGGER.exception("Database operation failed; rolled back")
        raise
    finally:
        conn.close()
```

**Особенности:**
- Автоматическое управление транзакциями
- Автоматический rollback при ошибках
- Гарантированное закрытие соединения

### 5.2 Получение соединения
```python
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        SETTINGS.database_path, 
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    conn.row_factory = sqlite3.Row
    return conn
```

**Настройки:**
- Автоматическое определение типов данных
- Использование `sqlite3.Row` для удобного доступа к полям

## 6. Инициализация базы данных

### 6.1 Автоматическое создание схемы
```python
def initialize_database() -> None:
    """Create tables and indices if they don't exist."""
```

**Функции:**
- Создание всех таблиц при первом запуске
- Создание индексов для оптимизации
- Логирование процесса инициализации

### 6.2 Создание директории данных
```python
# Ensure data directory exists
try:
    os.makedirs(os.path.dirname(database_path), exist_ok=True)
except Exception as exc:
    logging.getLogger(__name__).warning(
        "Failed to ensure database directory exists: %s", exc
    )
```

## 7. Оптимизация и производительность

### 7.1 Индексы
- **Составные индексы** для часто используемых комбинаций полей
- **Индексы по времени** для быстрого поиска по диапазонам
- **Индексы по статусу** для фильтрации обработанных/необработанных сообщений

### 7.2 Запросы
- **Пакетные операции** для массовых обновлений
- **Оптимизированные JOIN** для сложных запросов
- **Использование LIMIT** для ограничения результатов

### 7.3 Транзакции
- **Автоматические транзакции** для каждой операции
- **Rollback при ошибках** для обеспечения целостности
- **Минимальное время блокировки** соединений

## 8. Безопасность

### 8.1 Валидация данных
- Проверка типов данных перед вставкой
- Валидация обязательных полей
- Санитизация текстовых данных

### 8.2 Управление доступом
- Проверка прав сотрудников перед выполнением операций
- Логирование всех критических операций
- Изоляция данных между чатами

## 9. Мониторинг и логирование

### 9.1 Логирование операций
- Все операции с базой данных логируются
- Отслеживание времени выполнения запросов
- Логирование ошибок с полным стектрейсом

### 9.2 Метрики производительности
- Количество операций в секунду
- Время выполнения запросов
- Размер базы данных и таблиц

## 10. Резервное копирование и восстановление

### 10.1 Автоматическое резервное копирование
- Рекомендуется настроить регулярное копирование SQLite файла
- Использование `VACUUM` для оптимизации размера
- Проверка целостности базы данных

### 10.2 Восстановление данных
- Восстановление из резервной копии
- Проверка целостности после восстановления
- Валидация данных после восстановления

## 11. Расширение схемы

### 11.1 Добавление новых таблиц
```python
def add_new_table():
    with db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS new_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        """)
```

### 11.2 Миграции данных
- Версионирование схемы базы данных
- Скрипты миграции для обновления структуры
- Обратная совместимость при изменениях

## 12. Примеры использования

### 12.1 Получение статистики по чату
```python
def get_chat_statistics(chat_id: int) -> dict:
    with db_cursor() as cur:
        # Общее количество сообщений
        cur.execute(
            "SELECT COUNT(*) FROM raw_messages WHERE chat_id = ?", 
            (chat_id,)
        )
        total_messages = cur.fetchone()[0]
        
        # Количество обработанных задач
        cur.execute(
            "SELECT COUNT(*) FROM processed_tasks WHERE chat_id = ?", 
            (chat_id,)
        )
        total_tasks = cur.fetchone()[0]
        
        return {
            "total_messages": total_messages,
            "total_tasks": total_tasks,
            "processing_efficiency": total_tasks / total_messages if total_messages > 0 else 0
        }
```

### 12.2 Поиск задач по ключевым словам
```python
def search_tasks_by_keyword(chat_id: int, keyword: str) -> List[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, task_text, created_date 
            FROM processed_tasks 
            WHERE chat_id = ? AND task_text LIKE ?
            ORDER BY created_date DESC
            """,
            (chat_id, f"%{keyword}%")
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
```
