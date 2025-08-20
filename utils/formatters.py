import math
from datetime import datetime
from typing import Iterable, List, Sequence


TELEGRAM_MESSAGE_LIMIT = 4096


def _format_dt(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return dt_str


def format_tasks_list(tasks: Sequence[dict], page: int = 1, page_size: int = 20) -> str:
    if page < 1:
        page = 1
    total = len(tasks)
    if total == 0:
        return "Задач пока нет"
    pages = max(1, math.ceil(total / page_size))
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    lines: List[str] = [f"📄 Список задач (страница {page}/{pages}):"]
    for idx, t in enumerate(tasks[start:end], start=start + 1):
        dt_str = _format_dt(t.get("processing_timestamp", ""))
        task_text = t.get("task_text", "")
        lines.append(f"{idx}. [{dt_str}] {task_text}")
    if page < pages:
        lines.append("")
        lines.append("Для следующей страницы: /tasks {next_page}")
    text = "\n".join(lines)
    return text[:TELEGRAM_MESSAGE_LIMIT]


def format_messages_for_processing(messages_list: Sequence[dict]) -> str:
    if not messages_list:
        return "(нет сообщений)"
    parts: List[str] = []
    for m in messages_list:
        ts = m.get("timestamp")
        username = m.get("client_username") or "unknown"
        first_name = m.get("client_first_name") or ""
        text = m.get("message_text") or ""
        ts_fmt = _format_dt(str(ts))
        who = f"{first_name} (@{username})" if username else first_name or "Клиент"
        parts.append(f"[{ts_fmt}] {who}: {text}")
    blob = "\n".join(parts)
    return blob[:TELEGRAM_MESSAGE_LIMIT]



