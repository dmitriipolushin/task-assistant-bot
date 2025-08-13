import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence, Tuple

from config.staff_list import STAFF_USER_IDS, STAFF_USERNAMES
from .models import get_connection


LOGGER = logging.getLogger(__name__)


@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        yield conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        LOGGER.exception("Database operation failed; rolled back")
        raise
    finally:
        conn.close()


def save_task(
    chat_id: int,
    message_id: int,
    client_username: Optional[str],
    client_first_name: Optional[str],
    original_message: str,
    processed_task: str,
) -> int:
    """Save a processed task using a single source message id as origin.

    Returns inserted task id.
    """
    source_messages = json.dumps([message_id])
    with db_cursor() as cur:
        LOGGER.info("Saving processed task for chat_id=%s from message_id=%s", chat_id, message_id)
        cur.execute(
            """
            INSERT INTO processed_tasks (chat_id, task_text, source_messages)
            VALUES (?, ?, ?)
            """,
            (chat_id, processed_task, source_messages),
        )
        return cur.lastrowid


def save_processed_task_batch(chat_id: int, task_text: str, source_message_ids: Sequence[int]) -> int:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO processed_tasks (chat_id, task_text, source_messages)
            VALUES (?, ?, ?)
            """,
            (chat_id, task_text, json.dumps(list(source_message_ids))),
        )
        return cur.lastrowid


def save_raw_message(
    chat_id: int,
    message_id: int,
    client_username: Optional[str],
    client_first_name: Optional[str],
    message_text: str,
    timestamp: Optional[datetime] = None,
) -> int:
    ts = timestamp or datetime.now(timezone.utc)
    with db_cursor() as cur:
        LOGGER.debug("Saving raw message chat_id=%s message_id=%s", chat_id, message_id)
        cur.execute(
            """
            INSERT INTO raw_messages (chat_id, message_id, client_username, client_first_name, message_text, timestamp, is_processed)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (chat_id, message_id, client_username, client_first_name, message_text, ts.isoformat()),
        )
        return cur.lastrowid


def get_tasks_by_date(chat_id: int, date_str: str) -> List[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, chat_id, task_text, source_messages, processing_timestamp, created_date
            FROM processed_tasks
            WHERE chat_id = ? AND created_date = ?
            ORDER BY processing_timestamp ASC
            """,
            (chat_id, date_str),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def get_all_tasks(chat_id: int) -> List[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, chat_id, task_text, source_messages, processing_timestamp, created_date
            FROM processed_tasks
            WHERE chat_id = ?
            ORDER BY processing_timestamp DESC
            """,
            (chat_id,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def get_total_tasks_count(chat_id: int) -> int:
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(1) FROM processed_tasks WHERE chat_id = ?",
            (chat_id,),
        )
        (count,) = cur.fetchone()
        return int(count)


def is_staff_member(username: Optional[str], user_id: Optional[int]) -> bool:
    """Check if user is a staff member via hardcoded lists or DB table."""
    if username and username in STAFF_USERNAMES:
        return True
    if user_id and user_id in STAFF_USER_IDS:
        return True
    with db_cursor() as cur:
        if username:
            cur.execute("SELECT 1 FROM staff_members WHERE username = ? LIMIT 1", (username,))
            if cur.fetchone():
                return True
        if user_id:
            cur.execute("SELECT 1 FROM staff_members WHERE user_id = ? LIMIT 1", (user_id,))
            if cur.fetchone():
                return True
    return False


def get_all_chat_ids() -> List[int]:
    """Return distinct chat ids observed in raw_messages or processed_tasks."""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT chat_id FROM (
                SELECT chat_id FROM raw_messages
                UNION
                SELECT chat_id FROM processed_tasks
            )
            """
        )
        rows = cur.fetchall()
        return [int(r[0]) for r in rows]


def get_unprocessed_messages_last_hour(chat_id: int, now_utc: Optional[datetime] = None) -> List[dict]:
    now = now_utc or datetime.now(timezone.utc)
    since = now - timedelta(hours=1)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, chat_id, message_id, client_username, client_first_name, message_text, timestamp
            FROM raw_messages
            WHERE chat_id = ? AND is_processed = 0 AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
            """,
            (chat_id, since.isoformat(), now.isoformat()),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def get_chats_with_unprocessed_messages_last_hour(now_utc: Optional[datetime] = None) -> List[int]:
    now = now_utc or datetime.now(timezone.utc)
    since = now - timedelta(hours=1)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT chat_id
            FROM raw_messages
            WHERE is_processed = 0 AND timestamp >= ? AND timestamp <= ?
            """,
            (since.isoformat(), now.isoformat()),
        )
        rows = cur.fetchall()
        return [int(r[0]) for r in rows]


def get_unprocessed_messages_between(
    chat_id: int,
    since_utc: datetime,
    until_utc: datetime,
) -> List[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, chat_id, message_id, client_username, client_first_name, message_text, timestamp
            FROM raw_messages
            WHERE chat_id = ? AND is_processed = 0 AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
            """,
            (chat_id, since_utc.isoformat(), until_utc.isoformat()),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def mark_messages_processed(message_ids: Iterable[int]) -> int:
    ids = list(message_ids)
    if not ids:
        return 0
    qmarks = ",".join(["?"] * len(ids))
    with db_cursor() as cur:
        cur.execute(
            f"UPDATE raw_messages SET is_processed = 1 WHERE id IN ({qmarks})",
            ids,
        )
        return cur.rowcount



