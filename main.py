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
    if hasattr(context, 'error') and context.error:
        logging.getLogger(__name__).error("Error details: %s", str(context.error))


async def start_scheduler(application):
    """Start the scheduler after the application has access to event loop"""
    from bot.scheduler import SCHEDULER
    try:
        if SCHEDULER and not SCHEDULER.running:
            SCHEDULER.start()
            LOGGER.info("Scheduler started successfully with application")
        else:
            LOGGER.info("Scheduler already running or not configured")
    except Exception as e:
        LOGGER.error("Failed to start scheduler: %s", e)

def main() -> None:
    LOGGER.info("Starting Telegram TaskTracker Bot")
    
    # Validate configuration before starting
    try:
        SETTINGS.validate()
        LOGGER.info("Configuration validated successfully")
    except ValueError as e:
        LOGGER.error("Configuration validation failed: %s", e)
        return
    
    try:
        initialize_database()
        LOGGER.info("Database initialized successfully")
    except Exception as e:
        LOGGER.error("Failed to initialize database: %s", e)
        return

    try:
        application = (
            ApplicationBuilder()
            .token(SETTINGS.bot_token)
            .connect_timeout(15)
            .read_timeout(30)
            .write_timeout(30)
            .pool_timeout(5)
            .build()
        )
        LOGGER.info("Application built successfully")
    except Exception as e:
        LOGGER.error("Failed to build application: %s", e)
        return

    # Handlers
    try:
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
        LOGGER.info("Handlers registered successfully")
    except Exception as e:
        LOGGER.error("Failed to register handlers: %s", e)
        return
    
    # Setup schedulers before starting the application
    try:
        scheduler = setup_schedulers(application)
        LOGGER.info("Scheduler setup completed successfully")
    except Exception as e:
        LOGGER.error("Failed to setup schedulers: %s", e)
        return
    
    # Add post_init callback to start scheduler when application is ready
    try:
        application.post_init = start_scheduler
        LOGGER.info("Post-init callback set successfully")
    except Exception as e:
        LOGGER.error("Failed to set post-init callback: %s", e)
        return
    
    LOGGER.info("Scheduler configured, will start with application")

    # run_polling is synchronous and manages lifecycle
    try:
        application.run_polling()
        LOGGER.info("Bot stopped")
    except Exception as e:
        LOGGER.error("Bot failed to run: %s", e)
        raise


if __name__ == "__main__":
    main()


