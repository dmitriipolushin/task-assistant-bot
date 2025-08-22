import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from config.settings import SETTINGS
from database.operations import (
    get_chats_with_unprocessed_messages_last_hour,
    get_unprocessed_messages_between,
    get_all_messages_between,
    get_unprocessed_messages_last_hour,
    save_processed_task_batch,
    enqueue_pending_prioritization,
)
from .gpt_processor import process_messages_batch_with_gpt


LOGGER = logging.getLogger(__name__)


SCHEDULER: AsyncIOScheduler | None = None


def _truncate(text: str, limit: int = 160) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def _message_preview(msg: dict) -> str:
    return f"id={msg.get('id')}, mid={msg.get('message_id')}, ts={msg.get('timestamp')} | {_truncate(msg.get('message_text', ''))}"


def setup_schedulers(application: Application) -> AsyncIOScheduler:
    global SCHEDULER
    if SCHEDULER is not None and SCHEDULER.running:
        return SCHEDULER
    
    try:
        from zoneinfo import ZoneInfo
        tzinfo = ZoneInfo(SETTINGS.timezone)
        LOGGER.info("Using timezone: %s", SETTINGS.timezone)
    except Exception as e:
        LOGGER.warning("Failed to parse timezone %s, using fallback: %s", SETTINGS.timezone, e)
        tzinfo = SETTINGS.timezone  # fallback, APScheduler may resolve
    
    scheduler = AsyncIOScheduler(timezone=tzinfo)

    # Hourly processing at minute 0
    scheduler.add_job(
        process_messages_hourly,
        trigger=CronTrigger(minute=0),
        args=[application],
        id="hourly_processing",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    # Store the scheduler globally but don't start it yet
    # It will be started automatically when the application gets access to event loop
    SCHEDULER = scheduler
    LOGGER.info("Schedulers configured (will start automatically with application)")
    return scheduler


async def process_chat_messages_now(application: Application, chat_id: int) -> int:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=1)
    LOGGER.info("Hourly window for chat %s: %s → %s", chat_id, since.isoformat(), now.isoformat())
    messages = get_unprocessed_messages_last_hour(chat_id, now)
    if not messages:
        LOGGER.info("No messages to process for chat %s in the last hour", chat_id)
        return 0
    LOGGER.info("Fetched %s messages for chat %s", len(messages), chat_id)
    for preview in messages[:5]:
        LOGGER.info("Message: %s", _message_preview(preview))
    try:
        LOGGER.info("Sending %s messages to GPT for chat %s", len(messages), chat_id)
        LOGGER.info("Messages to process: %s", [_message_preview(msg) for msg in messages])
        tasks = await process_messages_batch_with_gpt(messages)
    except Exception as e:
        LOGGER.exception("GPT processing failed for chat %s: %s", chat_id, e)
        return 0
    
    # Сохраняем задачи и ставим в очередь приоритизации
    # НЕ помечаем сообщения как обработанные - это произойдет только после выбора приоритета
    for t in tasks:
        LOGGER.info("Task extracted: %s", _truncate(t))
        save_processed_task_batch(chat_id=chat_id, task_text=t, source_message_ids=[m["id"] for m in messages])
        pending_id = enqueue_pending_prioritization(chat_id, t)
        await _prompt_priority_selection(application, chat_id, pending_id, t)
    
    LOGGER.info("Chat %s: queued %s tasks for prioritization from %s messages", chat_id, len(tasks), len(messages))
    return len(tasks)


async def process_messages_hourly(application: Application) -> None:
    chat_ids = get_chats_with_unprocessed_messages_last_hour()
    if not chat_ids:
        LOGGER.info("Hourly run: no chats with unprocessed messages in the last hour")
        return
    LOGGER.info("Hourly run: %s chat(s) to process: %s", len(chat_ids), ", ".join(str(c) for c in chat_ids[:10]))
    for chat_id in chat_ids:
        try:
            await process_chat_messages_now(application, chat_id)
            await asyncio.sleep(0)  # yield control
        except Exception as e:
            LOGGER.exception("Failed to process hourly messages for chat %s: %s", chat_id, e)


async def process_chat_messages_range(application: Application, chat_id: int, since_utc: datetime, until_utc: datetime):
    # Для команды /parse используем get_all_messages_between (игнорирует is_processed)
    # Для обычной обработки используем get_unprocessed_messages_between
    LOGGER.info("/parse window for chat %s: %s → %s", chat_id, since_utc.isoformat(), until_utc.isoformat())
    messages = get_all_messages_between(chat_id, since_utc, until_utc)
    if not messages:
        LOGGER.info("/parse: no messages found for chat %s in the specified window", chat_id)
        return 0, 0
    LOGGER.info("/parse: fetched %s messages for chat %s", len(messages), chat_id)
    for preview in messages[:10]:
        LOGGER.info("/parse message: %s", _message_preview(preview))
    try:
        LOGGER.info("/parse: sending %s messages to GPT for chat %s", len(messages), chat_id)
        LOGGER.info("/parse messages to process: %s", [_message_preview(msg) for msg in messages])
        tasks = await process_messages_batch_with_gpt(messages)
    except Exception as e:
        LOGGER.exception("GPT processing failed for chat %s in range: %s", chat_id, e)
        return 0, len(messages)
    
    # Сохраняем задачи и ставим в очередь приоритизации
    # НЕ помечаем сообщения как обработанные - это произойдет только после выбора приоритета
    for t in tasks:
        LOGGER.info("/parse task extracted: %s", _truncate(t))
        save_processed_task_batch(chat_id=chat_id, task_text=t, source_message_ids=[m["id"] for m in messages])
        pending_id = enqueue_pending_prioritization(chat_id, t)
        await _prompt_priority_selection(application, chat_id, pending_id, t)
    
    LOGGER.info(
        "Chat %s: queued %s tasks for prioritization from %s messages (range %s - %s)",
        chat_id,
        len(tasks),
        len(messages),
        since_utc.isoformat(),
        until_utc.isoformat(),
    )
    return len(tasks), len(messages)


async def _prompt_priority_selection(application: Application, chat_id: int, pending_id: int, task_text: str) -> None:
    kb = [
        [InlineKeyboardButton("Critical", callback_data=f"prio:{pending_id}:critical"), InlineKeyboardButton("Blocker", callback_data=f"prio:{pending_id}:blocker")],
        [InlineKeyboardButton("High", callback_data=f"prio:{pending_id}:high"), InlineKeyboardButton("Medium", callback_data=f"prio:{pending_id}:medium"), InlineKeyboardButton("Low", callback_data=f"prio:{pending_id}:low")],
        [InlineKeyboardButton("Редактировать", callback_data=f"edit:{pending_id}")],
        [InlineKeyboardButton("Удалить", callback_data=f"del:{pending_id}")],
    ]
    await application.bot.send_message(
        chat_id=chat_id,
        text=f"Новая задача:\n{task_text}\nВыберите приоритет:",
        reply_markup=InlineKeyboardMarkup(kb),
    )


