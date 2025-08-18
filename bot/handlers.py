import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from database.operations import (
    get_all_tasks,
    is_staff_member,
    save_raw_message,
    get_pending_by_id,
    get_pending_for_chat,
    set_pending_priority,
    delete_pending,
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



async def handle_priority_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    user = update.effective_user
    if user is None:
        return
    LOGGER.info("Priority callback received from user_id=%s username=%s data=%s", getattr(user, "id", None), getattr(user, "username", None), getattr(query, "data", None))

    data = query.data or ""
    # Expected: prio:{pending_id}:{priority}
    try:
        parts = data.split(":", 2)
        if len(parts) != 3 or parts[0] != "prio":
            return
        pending_id = int(parts[1])
        priority = parts[2].strip().lower()
        if priority not in {"critical", "blocker", "high", "medium", "low"}:
            priority = "medium"
    except Exception:
        return

    item = get_pending_by_id(pending_id)
    if not item:
        try:
            await query.edit_message_reply_markup(None)
        except Exception:
            pass
        return

    # Проверка лимита срочных задач для Critical/Blocker/High
    if priority.lower() in {"critical", "blocker", "high"}:
        try:
            from utils.gsheets import get_high_priority_tasks, format_tasks_message, is_high_priority_limit_exceeded
            if is_high_priority_limit_exceeded():
                # Превышен лимит - показываем сообщение с выбором действий
                existing_tasks, _ = get_high_priority_tasks()
                message_text = format_tasks_message(existing_tasks, item["task_text"])
                
                # Новые кнопки для выбора действия
                kb = [
                    [InlineKeyboardButton("Medium", callback_data=f"downgrade:{pending_id}:medium")],
                    [InlineKeyboardButton("Low", callback_data=f"downgrade:{pending_id}:low")],
                    [InlineKeyboardButton("Оставить высокий", callback_data=f"keep_high:{pending_id}")],
                ]
                
                await query.edit_message_text(
                    text=message_text,
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                LOGGER.info("High priority limit exceeded for pending_id=%s, showing downgrade options", pending_id)
                return
        except Exception:
            LOGGER.exception("Failed to check high priority limit for pending_id=%s", pending_id)
            # При ошибке продолжаем как обычно

    try:
        LOGGER.info("Setting priority for pending_id=%s to %s", pending_id, priority)
        set_pending_priority(pending_id, priority)
    except Exception:
        LOGGER.exception("Failed to set pending priority pending_id=%s", pending_id)

    # Try to store to Google Sheets if configured
    cap_note: str | None = None
    try:
        from utils.gsheets import add_task_row, is_important_limit_exceeded
        LOGGER.info("Appending to Google Sheets: title='%s' priority='%s'", item.get("task_text"), priority)
        add_task_row(item["task_text"], priority)
        # If selected priority is important, check cap of 10 and only notify
        if priority.lower() in {"critical", "blocker", "high"}:
            if is_important_limit_exceeded(10):
                cap_note = "Превышен лимит срочных задач (Critical/Blocker/High > 10)"
                LOGGER.info("Important cap exceeded; notifying in chat without modifying sheet")
    except Exception:
        LOGGER.exception("Failed to append to Google Sheets or enforce cap")

    try:
        LOGGER.info("Deleting pending record id=%s", pending_id)
        delete_pending(pending_id)
        
        # Помечаем исходные сообщения как обработанные ПОСЛЕ выбора приоритета
        try:
            from database.operations import mark_messages_processed
            # Получаем source_message_ids из processed_tasks
            from database.operations import get_processed_task_by_text
            task_info = get_processed_task_by_text(item["chat_id"], item["task_text"])
            if task_info and task_info.get("source_messages"):
                import json
                source_ids = json.loads(task_info["source_messages"])
                if source_ids:
                    mark_messages_processed(source_ids)
                    LOGGER.info("Marked %s source messages as processed for task %s", len(source_ids), pending_id)
        except Exception:
            LOGGER.exception("Failed to mark source messages as processed for pending_id=%s", pending_id)
        
    except Exception:
        LOGGER.exception("Failed to delete pending record id=%s", pending_id)

    # Update message text and remove keyboard
    try:
        original_text = query.message.text if query.message and query.message.text else "Новая задача"
        new_text = f"{original_text}\n\nВыбран приоритет: {priority.capitalize()}"
        if cap_note:
            new_text += f"\n{cap_note}"
        await query.edit_message_text(text=new_text)
        LOGGER.info("Edited message to confirm selected priority for pending_id=%s", pending_id)
    except Exception:
        try:
            await query.edit_message_reply_markup(None)
        except Exception:
            pass


async def handle_downgrade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    user = update.effective_user
    if user is None:
        return
    LOGGER.info("Downgrade callback received from user_id=%s username=%s data=%s", getattr(user, "id", None), getattr(user, "username", None), getattr(query, "data", None))

    data = query.data or ""
    try:
        prefix, pending_id_str, priority = data.split(":", 2)
        if prefix != "downgrade":
            return
        pending_id = int(pending_id_str)
        if priority not in {"medium", "low"}:
            return
    except Exception:
        return

    item = get_pending_by_id(pending_id)
    if not item:
        try:
            await query.edit_message_reply_markup(None)
        except Exception:
            pass
        return

    try:
        LOGGER.info("Setting downgraded priority for pending_id=%s to %s", pending_id, priority)
        set_pending_priority(pending_id, priority)
    except Exception:
        LOGGER.exception("Failed to set pending priority pending_id=%s", pending_id)

    # Добавляем задачу в Google Sheets с пониженным приоритетом
    try:
        from utils.gsheets import add_task_row
        LOGGER.info("Appending downgraded task to Google Sheets: title='%s' priority='%s'", item.get("task_text"), priority)
        add_task_row(item["task_text"], priority)
    except Exception:
        LOGGER.exception("Failed to append downgraded task to Google Sheets")

    try:
        LOGGER.info("Deleting pending record id=%s", pending_id)
        delete_pending(pending_id)
        
        # Помечаем исходные сообщения как обработанные ПОСЛЕ выбора приоритета
        try:
            from database.operations import mark_messages_processed
            # Получаем source_message_ids из processed_tasks
            from database.operations import get_processed_task_by_text
            task_info = get_processed_task_by_text(chat_id, item["task_text"])
            if task_info and task_info.get("source_messages"):
                import json
                source_ids = json.loads(task_info["source_messages"])
                if source_ids:
                    mark_messages_processed(source_ids)
                    LOGGER.info("Marked %s source messages as processed for downgraded task %s", len(source_ids), pending_id)
        except Exception:
            LOGGER.exception("Failed to mark source messages as processed for downgraded task %s", pending_id)
        
    except Exception:
        LOGGER.exception("Failed to delete pending record id=%s", pending_id)

    # Обновляем сообщение
    try:
        original_text = query.message.text if query.message and query.message.text else "Новая задача"
        new_text = f"{original_text}\n\nВыбран пониженный приоритет: {priority.capitalize()}"
        await query.edit_message_text(text=new_text)
        LOGGER.info("Edited message to confirm downgraded priority for pending_id=%s", pending_id)
    except Exception:
        try:
            await query.edit_message_reply_markup(None)
        except Exception:
            pass


async def handle_keep_high_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    user = update.effective_user
    if user is None:
        return
    LOGGER.info("Keep high callback received from user_id=%s username=%s data=%s", getattr(user, "id", None), getattr(user, "username", None), getattr(query, "data", None))

    data = query.data or ""
    try:
        prefix, pending_id_str = data.split(":", 1)
        if prefix != "keep_high":
            return
        pending_id = int(pending_id_str)
    except Exception:
        return

    item = get_pending_by_id(pending_id)
    if not item:
        try:
            await query.edit_message_reply_markup(None)
        except Exception:
            pass
        return

    # Отправляем сообщение о необходимости определить задачу для понижения
    try:
        message_text = "Необходимо определить задачу, приоритет которой будет понижен"
        await query.edit_message_text(text=message_text)
        LOGGER.info("Kept high priority task pending_id=%s, waiting for priority downgrade decision", pending_id)
    except Exception:
        try:
            await query.edit_message_reply_markup(None)
        except Exception:
            pass


async def handle_delete_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    user = update.effective_user
    if user is None:
        return
    LOGGER.info("Delete callback received from user_id=%s username=%s data=%s", getattr(user, "id", None), getattr(user, "username", None), getattr(query, "data", None))

    data = query.data or ""
    try:
        prefix, payload = data.split(":", 1)
        if prefix != "del":
            return
        pending_id = int(payload)
    except Exception:
        return

    item = get_pending_by_id(pending_id)
    if not item:
        try:
            await query.edit_message_reply_markup(None)
        except Exception:
            pass
        return

    # Remove from DB (pending + processed approximated by text)
    try:
        LOGGER.info("Deleting pending id=%s and matching processed task(s)", pending_id)
        delete_pending(pending_id)
    except Exception:
        LOGGER.exception("Failed to delete pending id=%s", pending_id)
    try:
        from database.operations import delete_processed_tasks_by_text
        deleted = delete_processed_tasks_by_text(item["chat_id"], item["task_text"])
        LOGGER.info("Deleted %s processed task(s) for chat_id=%s by text match", deleted, item.get("chat_id"))
    except Exception:
        LOGGER.exception("Failed to delete processed task(s) by text")

    try:
        await query.edit_message_text(text="Задача удалена")
    except Exception:
        try:
            await query.edit_message_reply_markup(None)
        except Exception:
            pass


async def handle_prioritize_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return
    LOGGER.info("/prioritize received in chat_id=%s by user_id=%s", getattr(chat, "id", None), getattr(user, "id", None))
    try:
        items = get_pending_for_chat(chat.id)
    except Exception:
        LOGGER.exception("Failed to load pending for chat %s", getattr(chat, "id", None))
        return

    if not items:
        try:
            await context.bot.send_message(chat_id=chat.id, text="Нет задач, требующих выбора приоритета")
        except Exception:
            LOGGER.exception("Failed to send /prioritize empty message")
        return

    for it in items:
        try:
            kb = [
                [InlineKeyboardButton("Critical", callback_data=f"prio:{it['id']}:critical"), InlineKeyboardButton("Blocker", callback_data=f"prio:{it['id']}:blocker")],
                [InlineKeyboardButton("High", callback_data=f"prio:{it['id']}:high"), InlineKeyboardButton("Medium", callback_data=f"prio:{it['id']}:medium"), InlineKeyboardButton("Low", callback_data=f"prio:{it['id']}:low")],
                [InlineKeyboardButton("Удалить", callback_data=f"del:{it['id']}")],
            ]
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"Задача:\n{it['task_text']}\n\nВыберите приоритет:",
                reply_markup=InlineKeyboardMarkup(kb),
            )
        except Exception:
            LOGGER.exception("Failed to send prioritize keyboard for pending id=%s", it.get("id"))


