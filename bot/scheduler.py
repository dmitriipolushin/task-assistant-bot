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


async def setup_schedulers(application: Application) -> AsyncIOScheduler:
    global SCHEDULER
    if SCHEDULER is not None and SCHEDULER.running:
        return SCHEDULER
    try:
        from zoneinfo import ZoneInfo
        tzinfo = ZoneInfo(SETTINGS.timezone)
    except Exception:
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

    scheduler.start()
    LOGGER.info("Schedulers configured and started")
    SCHEDULER = scheduler
    return scheduler


async def process_chat_messages_now(application: Application, chat_id: int) -> int:
    now = datetime.now(timezone.utc)
    messages = get_unprocessed_messages_last_hour(chat_id, now)
    if not messages:
        return 0
    try:
        tasks = await process_messages_batch_with_gpt(messages)
    except Exception:
        LOGGER.exception("GPT processing failed for chat %s", chat_id)
        return 0
    
    # Сохраняем задачи и ставим в очередь приоритизации
    # НЕ помечаем сообщения как обработанные - это произойдет только после выбора приоритета
    for t in tasks:
        save_processed_task_batch(chat_id=chat_id, task_text=t, source_message_ids=[m["id"] for m in messages])
        pending_id = enqueue_pending_prioritization(chat_id, t)
        await _prompt_priority_selection(application, chat_id, pending_id, t)
    
    LOGGER.info("Chat %s: queued %s tasks for prioritization from %s messages", chat_id, len(tasks), len(messages))
    return len(tasks)


async def process_messages_hourly(application: Application) -> None:
    chat_ids = get_chats_with_unprocessed_messages_last_hour()
    if not chat_ids:
        return
    for chat_id in chat_ids:
        try:
            await process_chat_messages_now(application, chat_id)
            await asyncio.sleep(0)  # yield control
        except Exception:
            LOGGER.exception("Failed to process hourly messages for chat %s", chat_id)


async def process_chat_messages_range(application: Application, chat_id: int, since_utc: datetime, until_utc: datetime):
    # Для команды /parse используем get_all_messages_between (игнорирует is_processed)
    # Для обычной обработки используем get_unprocessed_messages_between
    messages = get_all_messages_between(chat_id, since_utc, until_utc)
    if not messages:
        return 0, 0
    try:
        tasks = await process_messages_batch_with_gpt(messages)
    except Exception:
        LOGGER.exception("GPT processing failed for chat %s in range", chat_id)
        return 0, len(messages)
    
    # Сохраняем задачи и ставим в очередь приоритизации
    # НЕ помечаем сообщения как обработанные - это произойдет только после выбора приоритета
    for t in tasks:
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


