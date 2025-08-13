import logging
from typing import Optional

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from database.operations import (
    get_all_tasks,
    is_staff_member,
    save_raw_message,
)
from utils.formatters import format_tasks_list


LOGGER = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.text is None:
        return
    if message.text.startswith("/"):
        return
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    username: Optional[str] = user.username
    user_id: Optional[int] = user.id
    if is_staff_member(username, user_id):
        LOGGER.debug("Ignoring staff message from user_id=%s username=%s", user_id, username)
        return

    try:
        save_raw_message(
            chat_id=chat.id,
            message_id=message.message_id,
            client_username=username,
            client_first_name=user.first_name,
            message_text=message.text,
            timestamp=message.date,
        )
        LOGGER.info("Saved raw message chat_id=%s message_id=%s", chat.id, message.message_id)
    except Exception:
        LOGGER.exception("Failed to save raw message")


async def handle_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    page = 1
    try:
        if context.args and len(context.args) >= 1:
            page = max(1, int(context.args[0]))
    except Exception:
        page = 1

    try:
        LOGGER.info("/tasks received in chat_id=%s page=%s", chat.id, page)
        tasks = get_all_tasks(chat.id)
        text = format_tasks_list(tasks, page=page)
        # Split into chunks if needed with retry on timeout
        for i in range(0, len(text), 4096):
            chunk = text[i : i + 4096]
            try:
                await context.bot.send_message(chat_id=chat.id, text=chunk)
            except Exception as err:
                LOGGER.warning("/tasks send_message failed: %s; retrying once", err)
                try:
                    await context.bot.send_message(chat_id=chat.id, text=chunk)
                except Exception:
                    LOGGER.exception("/tasks send_message retry failed")
    except Exception:
        LOGGER.exception("Failed to handle /tasks command")


async def handle_process_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return
    if not is_staff_member(user.username, user.id):
        return
    try:
        from .scheduler import process_chat_messages_now

        LOGGER.info("/process_now received in chat_id=%s by user_id=%s", chat.id, user.id)
        processed = await process_chat_messages_now(context.application, chat.id)
        try:
            await context.bot.send_message(chat_id=chat.id, text=f"Обработано задач: {processed}")
        except Exception as err:
            LOGGER.warning("/process_now send_message failed: %s; retrying once", err)
            await context.bot.send_message(chat_id=chat.id, text=f"Обработано задач: {processed}")
    except Exception:
        LOGGER.exception("Failed to process now for chat %s", chat.id)


async def handle_parse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return
    if not is_staff_member(user.username, user.id):
        return
    # parse days argument
    days = 1
    try:
        if context.args and len(context.args) >= 1:
            days = max(1, int(context.args[0]))
    except Exception:
        days = 1

    try:
        from datetime import datetime, timezone, timedelta
        from .scheduler import process_chat_messages_range

        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        LOGGER.info("/parse received in chat_id=%s by user_id=%s days=%s", chat.id, user.id, days)
        processed, received = await process_chat_messages_range(context.application, chat.id, since, now)
        try:
            text = f"Диапазон: {days} дн.\nПолучено сообщений: {received}\nОбработано задач: {processed}"
            await context.bot.send_message(chat_id=chat.id, text=text)
        except Exception as err:
            LOGGER.warning("/parse send_message failed: %s; retrying once", err)
            await context.bot.send_message(chat_id=chat.id, text=text)
    except Exception:
        LOGGER.exception("Failed to parse range for chat %s", chat.id)


# /import_history command removed. History import is integrated into /parse when no unprocessed messages found.



