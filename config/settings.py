import os
from dataclasses import dataclass


@dataclass
class Settings:
    # Bot settings
    bot_token: str = os.getenv("BOT_TOKEN", "")
    
    # OpenAI settings
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    
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
    
    @property
    def database_connection_string(self) -> str:
        """Generate PostgreSQL connection string"""
        if self.database_url:
            return self.database_url
        return f"postgresql://{self.database_user}:{self.database_password}@{self.database_host}:{self.database_port}/{self.database_name}"


SETTINGS = Settings()



