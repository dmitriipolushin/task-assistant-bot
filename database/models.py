import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional

from config.settings import SETTINGS


LOGGER = logging.getLogger(__name__)


def get_connection():
    """Get PostgreSQL connection"""
    try:
        conn = psycopg2.connect(
            SETTINGS.database_connection_string,
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        LOGGER.error(f"Failed to connect to PostgreSQL: {e}")
        raise


def initialize_database() -> None:
    """Create tables and indices if they don't exist."""
    with get_connection() as conn:
        cur = conn.cursor()
        LOGGER.info("Initializing PostgreSQL database schema")
        
        # Tables
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw_messages (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                client_username TEXT,
                client_first_name TEXT,
                message_text TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_processed BOOLEAN DEFAULT FALSE
            );
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_tasks (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                task_text TEXT NOT NULL,
                source_messages TEXT,
                processing_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_date DATE DEFAULT CURRENT_DATE
            );
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_prioritization (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                task_text TEXT NOT NULL,
                selected_priority TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS staff_members (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE,
                user_id BIGINT UNIQUE
            );
        """)

        # Indices
        cur.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_chat_id ON raw_messages(chat_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_timestamp ON raw_messages(timestamp);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_is_processed ON raw_messages(is_processed);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_processed_tasks_chat_id ON processed_tasks(chat_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_processed_tasks_created_date ON processed_tasks(created_date);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pending_chat_id ON pending_prioritization(chat_id);")

        conn.commit()
        LOGGER.info("PostgreSQL database schema initialized")



