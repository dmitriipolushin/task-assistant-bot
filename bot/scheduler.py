import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Sequence

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from config.settings import SETTINGS
from database.operations import (
    get_all_chat_ids,
    get_chats_with_unprocessed_messages_last_hour,
    get_tasks_by_date,
    get_total_tasks_count,
    get_unprocessed_messages_last_hour,
    get_unprocessed_messages_between,
    mark_messages_processed,
    save_processed_task_batch,
)
from utils.formatters import format_daily_report
from .gpt_processor import process_messages_batch_with_gpt


LOGGER = logging.getLogger(__name__)


SCHEDULER: AsyncIOScheduler | None = None


def setup_schedulers(application: Application) -> AsyncIOScheduler:
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

    # Daily reports at configured time, Moscow default
    hour, minute = map(int, SETTINGS.daily_report_time.split(":"))
    scheduler.add_job(
        send_daily_report,
        trigger=CronTrigger(hour=hour, minute=minute),
        args=[application],
        id="daily_report",
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
    for t in tasks:
        save_processed_task_batch(chat_id=chat_id, task_text=t, source_message_ids=[m["id"] for m in messages])
    mark_messages_processed([m["id"] for m in messages])
    LOGGER.info("Chat %s: processed %s tasks from %s messages", chat_id, len(tasks), len(messages))
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
    messages = get_unprocessed_messages_between(chat_id, since_utc, until_utc)
    if not messages:
        return 0, 0
    try:
        tasks = await process_messages_batch_with_gpt(messages)
    except Exception:
        LOGGER.exception("GPT processing failed for chat %s in range", chat_id)
        return 0, len(messages)
    for t in tasks:
        save_processed_task_batch(chat_id=chat_id, task_text=t, source_message_ids=[m["id"] for m in messages])
    mark_messages_processed([m["id"] for m in messages])
    LOGGER.info(
        "Chat %s: processed %s tasks from %s messages (range %s - %s)",
        chat_id,
        len(tasks),
        len(messages),
        since_utc.isoformat(),
        until_utc.isoformat(),
    )
    return len(tasks), len(messages)


async def send_daily_report(application: Application) -> None:
    chat_ids = get_all_chat_ids()
    if not chat_ids:
        return
    # previous day date string YYYY-MM-DD
    today = datetime.now().date()
    prev_day = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    for chat_id in chat_ids:
        try:
            tasks = get_tasks_by_date(chat_id, prev_day)
            total = get_total_tasks_count(chat_id)
            text = format_daily_report(chat_id, prev_day, tasks, total)
            # split
            for i in range(0, len(text), 4096):
                try:
                    await application.bot.send_message(chat_id=chat_id, text=text[i : i + 4096])
                except Exception as err:
                    LOGGER.warning("Daily report send_message failed: %s; retrying once", err)
                    try:
                        await application.bot.send_message(chat_id=chat_id, text=text[i : i + 4096])
                    except Exception:
                        LOGGER.exception("Daily report send_message retry failed")
        except Exception:
            LOGGER.exception("Failed to send daily report to chat %s", chat_id)


