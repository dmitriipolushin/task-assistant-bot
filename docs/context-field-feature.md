# Поле "Контекст" в Google таблице

## Обзор

Поле "Контекст" - это новая функциональность, добавленная в версии 1.3.0, которая автоматически добавляет в Google таблицу ссылки на исходные сообщения в чате. Это позволяет разработчикам быстро переходить к первоисточнику задачи для лучшего понимания требований клиента.

## Функциональность

### Основные возможности

1. **Автоматическое формирование ссылок** - ссылки создаются автоматически при выборе приоритета задачи
2. **Кликабельные ссылки** - прямые переходы к сообщениям в Telegram
3. **Контекстная информация** - полная картина запроса клиента
4. **Безопасность** - ссылки доступны только участникам чата

### Формат ссылок

Ссылки формируются в стандартном формате Telegram:
```
https://t.me/c/{chat_id}/{message_id}
```

Где:
- `{chat_id}` - ID чата (без знака минус для групповых чатов)
- `{message_id}` - ID конкретного сообщения

### Примеры содержимого

**Одно сообщение:**
```
https://t.me/c/1234567890/123
```

**Несколько сообщений:**
```
https://t.me/c/1234567890/123 | https://t.me/c/1234567890/124
```

## Техническая реализация

### Архитектура

```
Сообщения → GPT обработка → Сохранение в БД → Выбор приоритета → Формирование контекста → Google Sheets
```

### Ключевые компоненты

#### 1. Функция `format_message_links`

```python
def format_message_links(chat_id: int, message_ids: list) -> str:
    """Format message IDs into clickable Telegram links."""
    if not message_ids:
        return ""
    
    links = []
    for msg_id in message_ids:
        # Формируем ссылку вида: https://t.me/c/1234567890/123
        # где 1234567890 - это chat_id, а 123 - message_id
        # Для групповых чатов нужно убрать знак минус из chat_id
        formatted_chat_id = str(chat_id).replace("-", "")
        link = f"https://t.me/c/{formatted_chat_id}/{msg_id}"
        links.append(link)
    
    return " | ".join(links)
```

**Особенности:**
- Обработка групповых чатов (убирает знак минус из chat_id)
- Объединение множественных ссылок через ` | `
- Возврат пустой строки при отсутствии message_ids

#### 2. Обновленная функция `add_task_row`

```python
def add_task_row(
    title: str,
    priority: str,
    project: str | None = None,
    status: str | None = None,
    link: str | None = None,
    task_type: str | None = None,
    plan: str | None = None,
    context: str | None = None,
) -> None:
    """Append a new task row to the tasks worksheet."""
    ws = _open_tasks_worksheet()
    
    values = [
        "Calzen",  # Проект
        title,     # Описание
        priority.capitalize(),  # Приоритет
        context or "",  # Контекст (ссылки на сообщения)
    ]
    
    ws.append_row(values)
```

**Изменения:**
- Добавлен параметр `context`
- Контекст помещается в четвертый столбец таблицы
- Поддержка обратной совместимости

#### 3. Интеграция в обработчик приоритетов

```python
# Получаем source_message_ids для формирования контекста
context = ""
try:
    from database.operations import get_processed_task_by_text
    task_info = get_processed_task_by_text(item["chat_id"], item["task_text"])
    if task_info and task_info.get("source_messages"):
        import json
        source_ids = json.loads(task_info["source_messages"])
        if source_ids:
            from utils.gsheets import format_message_links
            context = format_message_links(item["chat_id"], source_ids)
except Exception:
    LOGGER.warning("Failed to get source messages for context, proceeding without context")

add_task_row(item["task_text"], priority, context=context)
```

**Логика работы:**
1. Получение информации о задаче из базы данных
2. Извлечение source_messages (JSON строка с ID сообщений)
3. Парсинг JSON и формирование ссылок
4. Передача контекста в Google Sheets

### Структура данных

#### База данных

Поле `source_messages` в таблице `processed_tasks` хранит JSON массив ID исходных сообщений:

```sql
CREATE TABLE processed_tasks (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    task_text TEXT NOT NULL,
    source_messages TEXT,  -- JSON массив ID сообщений
    processing_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_date DATE DEFAULT CURRENT_DATE
);
```

**Пример содержимого:**
```json
[123, 124, 125]
```

#### Google Sheets

Структура таблицы обновлена:
- **Столбец A**: Проект (всегда "Calzen")
- **Столбец B**: Описание задачи
- **Столбец C**: Приоритет
- **Столбец D**: Контекст (ссылки на сообщения)

## Обработка ошибок

### Стратегии восстановления

1. **Отсутствие source_messages** - контекст остается пустым
2. **Ошибки парсинга JSON** - логируется предупреждение, контекст не формируется
3. **Проблемы с базой данных** - задача добавляется без контекста
4. **Ошибки Google Sheets** - основная функциональность не нарушается

### Логирование

```python
LOGGER.warning("Failed to get source messages for context, proceeding without context")
LOGGER.info("Appending to Google Sheets: title='%s' priority='%s' context='%s'", 
            item.get("task_text"), priority, context or "нет")
```

## Конфигурация

### Заголовки таблицы

Бот автоматически создает заголовки на русском языке:
```python
RUS_HEADERS = ["Проект", "Описание", "Приоритет", "Контекст"]
ENG_HEADERS = ["Project", "Description", "Priority", "Context"]
```

### Переменные окружения

Поле "Контекст" не требует дополнительных настроек - оно работает автоматически при включенной интеграции с Google Sheets.

## Ограничения

### Текущие ограничения

1. **Только для новых задач** - существующие задачи не получают контекст
2. **Зависимость от source_messages** - если ID сообщений не сохранены, контекст не формируется
3. **Доступность ссылок** - ссылки работают только для участников чата

### Планы развития

1. **Ретроактивное добавление** - возможность добавить контекст к существующим задачам
2. **Расширенная информация** - добавление метаданных сообщений (время, автор)
3. **Фильтрация контекста** - возможность скрыть контекст для определенных типов задач

## Тестирование

### Проверка функциональности

1. **Создание новой задачи** - убедиться, что контекст добавляется
2. **Множественные сообщения** - проверить корректность разделения ссылок
3. **Групповые чаты** - убедиться в правильности формирования chat_id
4. **Обработка ошибок** - проверить graceful degradation при проблемах

### Примеры тестов

```python
# Тест формирования ссылок
assert format_message_links(1234567890, [123, 124]) == \
       "https://t.me/c/1234567890/123 | https://t.me/c/1234567890/124"

# Тест группового чата
assert format_message_links(-1234567890, [123]) == \
       "https://t.me/c/1234567890/123"

# Тест пустого списка
assert format_message_links(1234567890, []) == ""
```

## Заключение

Поле "Контекст" значительно улучшает пользовательский опыт разработчиков, предоставляя быстрый доступ к исходным сообщениям клиентов. Реализация выполнена с минимальными изменениями в существующей архитектуре, обеспечивая обратную совместимость и надежность работы системы.
