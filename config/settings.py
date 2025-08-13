import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    openai_api_key: str
    gpt_model: str
    timezone: str
    daily_report_time: str
    database_path: str
    gsheet_spreadsheet_id: str | None
    gsheet_worksheet_name: str | None
    google_service_account_json_path: str | None


def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    gpt_model = os.getenv("GPT_MODEL")
    timezone = os.getenv("TIMEZONE", "Europe/Moscow")
    daily_report_time = os.getenv("DAILY_REPORT_TIME", "09:00")
    database_path = os.getenv("DATABASE_PATH", os.path.join(".", "data", "bot.db"))
    gsheet_spreadsheet_id = os.getenv("GSHEET_SPREADSHEET_ID")
    gsheet_worksheet_name = os.getenv("GSHEET_WORKSHEET_NAME", "Tasks")
    google_service_account_json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH")

    missing = []
    if not bot_token:
        missing.append("BOT_TOKEN")
    if not openai_api_key:
        missing.append("OPENAI_API_KEY")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    # Ensure data directory exists
    try:
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to ensure database directory exists: %s", exc)

    return Settings(
        bot_token=bot_token,
        openai_api_key=openai_api_key,
        gpt_model=gpt_model,
        timezone=timezone,
        daily_report_time=daily_report_time,
        database_path=database_path,
        gsheet_spreadsheet_id=gsheet_spreadsheet_id,
        gsheet_worksheet_name=gsheet_worksheet_name,
        google_service_account_json_path=google_service_account_json_path,
    )


SETTINGS = load_settings()



