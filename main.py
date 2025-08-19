import logging

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

from bot.handlers import handle_message, handle_process_now_command, handle_tasks_command, handle_parse_command, handle_priority_callback, handle_downgrade_callback, handle_edit_task_callback, handle_keep_high_callback, handle_prioritize_command, handle_delete_task_callback
from bot.scheduler import setup_schedulers
from config.settings import SETTINGS
from database.models import initialize_database


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
LOGGER = logging.getLogger(__name__)


async def on_error(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.getLogger(__name__).exception("Update caused error: %s", context.error)

def main() -> None:
    LOGGER.info("Starting Telegram TaskTracker Bot")
    initialize_database()

    application = (
        ApplicationBuilder()
        .token(SETTINGS.bot_token)
        .connect_timeout(15)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(5)
        .build()
    )

    # Handlers
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND) & filters.ChatType.GROUPS, handle_message))
    application.add_handler(CommandHandler("tasks", handle_tasks_command))
    application.add_handler(CommandHandler("process_now", handle_process_now_command))
    application.add_handler(CommandHandler("parse", handle_parse_command))
    application.add_handler(CommandHandler("prioritize", handle_prioritize_command))
    application.add_handler(CallbackQueryHandler(handle_priority_callback, pattern=r"^prio:"))
    application.add_handler(CallbackQueryHandler(handle_downgrade_callback, pattern=r"^downgrade:"))
    application.add_handler(CallbackQueryHandler(handle_edit_task_callback, pattern=r"^edit:"))
    application.add_handler(CallbackQueryHandler(handle_keep_high_callback, pattern=r"^keep_high:"))
    application.add_handler(CallbackQueryHandler(handle_delete_task_callback, pattern=r"^del:"))
    application.add_error_handler(on_error)

    setup_schedulers(application)

    # run_polling is synchronous and manages lifecycle
    application.run_polling()
    LOGGER.info("Bot stopped")


if __name__ == "__main__":
    main()


