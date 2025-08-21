import os
from dataclasses import dataclass


@dataclass
class Settings:
    # Bot settings
    bot_token: str = os.getenv("BOT_TOKEN", "")
    
    # OpenAI settings
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    gpt_model: str = os.getenv("GPT_MODEL", "dima/gpt-4o")
    
    # Timezone settings
    timezone: str = os.getenv("TIMEZONE", "Europe/Moscow")
    
    # Database settings (PostgreSQL)
    database_url: str = os.getenv("DATABASE_URL", "")
    database_host: str = os.getenv("DB_HOST", "localhost")
    database_port: int = int(os.getenv("DB_PORT", "5432"))
    database_name: str = os.getenv("DB_NAME", "tasktracker")
    database_user: str = os.getenv("DB_USER", "postgres")
    database_password: str = os.getenv("DB_PASSWORD", "")
    
    # Google Sheets settings
    gsheet_worksheet_name: str = os.getenv("GSHEET_WORKSHEET_NAME", "")
    gsheet_tasks_worksheet_name: str = os.getenv("GSHEET_TASKS_WORKSHEET_NAME", "")
    
    def validate(self) -> None:
        """Validate that required settings are configured"""
        if not self.bot_token:
            raise ValueError("BOT_TOKEN environment variable is required")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        if not self.gpt_model:
            raise ValueError("GPT_MODEL environment variable is required")
    
    @property
    def database_connection_string(self) -> str:
        """Generate PostgreSQL connection string"""
        if self.database_url:
            return self.database_url
        return f"postgresql://{self.database_user}:{self.database_password}@{self.database_host}:{self.database_port}/{self.database_name}"


SETTINGS = Settings()

# Validate settings on import
try:
    SETTINGS.validate()
except ValueError as e:
    import logging
    logging.error("Configuration error: %s", e)
    raise



