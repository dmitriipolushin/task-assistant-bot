import logging
import sqlite3
from typing import Optional

from config.settings import SETTINGS


LOGGER = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(SETTINGS.database_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    """Create tables and indices if they don't exist."""
    with get_connection() as conn:
        cur = conn.cursor()
        LOGGER.info("Initializing database schema at %s", SETTINGS.database_path)
        # Tables
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                client_username TEXT,
                client_first_name TEXT,
                message_text TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_processed BOOLEAN DEFAULT 0
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                task_text TEXT NOT NULL,
                source_messages TEXT,
                processing_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_date DATE DEFAULT (DATE('now'))
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_prioritization (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                task_text TEXT NOT NULL,
                selected_priority TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS staff_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                user_id INTEGER UNIQUE
            );
            """
        )

        # Indices
        cur.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_chat_id ON raw_messages(chat_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_timestamp ON raw_messages(timestamp);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_raw_messages_is_processed ON raw_messages(is_processed);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_processed_tasks_chat_id ON processed_tasks(chat_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_processed_tasks_created_date ON processed_tasks(created_date);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pending_chat_id ON pending_prioritization(chat_id);")

        conn.commit()
        LOGGER.info("Database schema initialized")



