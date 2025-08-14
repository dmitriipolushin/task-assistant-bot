import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Tuple

import gspread

from config.settings import SETTINGS


LOGGER = logging.getLogger(__name__)


RUS_HEADERS = ["Проект", "Задача", "Статус", "Ссылка", "Приоритет", "Тип", "Plan"]
ENG_HEADERS = ["Title", "Priority", "CreatedAt"]


def _open_worksheet():
    if not SETTINGS.google_service_account_json_path or not SETTINGS.gsheet_spreadsheet_id:
        raise RuntimeError("Google Sheets is not configured. Set GOOGLE_SERVICE_ACCOUNT_JSON_PATH and GSHEET_SPREADSHEET_ID in .env")
    LOGGER.info("Opening Google Sheet id=%s", SETTINGS.gsheet_spreadsheet_id)
    # Build client from file path or from JSON string
    creds_path_or_json = SETTINGS.google_service_account_json_path
    gc = None
    try:
        required_fields = {"type", "project_id", "private_key_id", "private_key", "client_email", "client_id", "auth_uri", "token_uri"}
        if os.path.isfile(creds_path_or_json):
            # Validate JSON file has required fields (without logging secrets)
            try:
                with open(creds_path_or_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                missing = [k for k in required_fields if k not in data]
                if missing:
                    raise RuntimeError(f"Service account JSON missing required fields: {', '.join(missing)}")
            except Exception as exc:
                LOGGER.error("Failed to read or validate service account file: %s", exc)
                raise
            gc = gspread.service_account(filename=creds_path_or_json)
        else:
            # Try to parse as inline JSON (env may store JSON content)
            try:
                data = json.loads(creds_path_or_json)
                missing = [k for k in required_fields if k not in data]
                if missing:
                    raise RuntimeError(f"Inline service account JSON missing required fields: {', '.join(missing)}")
                LOGGER.info("Using inline JSON credentials from GOOGLE_SERVICE_ACCOUNT_JSON_PATH env")
                gc = gspread.service_account_from_dict(data)
            except Exception as exc:
                LOGGER.error("GOOGLE_SERVICE_ACCOUNT_JSON_PATH is neither a file nor valid JSON: %s", exc)
                raise
    except Exception:
        # Re-raise to caller; caller logs stacktrace
        raise
    sh = gc.open_by_key(SETTINGS.gsheet_spreadsheet_id)
    ws_name = SETTINGS.gsheet_worksheet_name or "Tasks"
    try:
        ws = sh.worksheet(ws_name)
        LOGGER.info("Using worksheet '%s'", ws_name)
    except gspread.WorksheetNotFound:
        LOGGER.info("Worksheet '%s' not found. Creating with default headers", ws_name)
        ws = sh.add_worksheet(title=ws_name, rows=1000, cols=10)
        # Initialize with Russian headers per spec
        ws.append_row(RUS_HEADERS)
    return ws


def _get_header_map(ws) -> Dict[str, int]:
    """Return {header_name: 1-based index} for the first row.

    Supports both the Russian spec (Проект, Задача, ...) and previous English minimal header.
    """
    try:
        headers = [h.strip() for h in ws.row_values(1)]
    except Exception:
        headers = []
    return {name: idx for idx, name in enumerate(headers, start=1) if name}


def read_all_tasks() -> List[dict]:
    ws = _open_worksheet()
    LOGGER.info("Reading all tasks from worksheet")
    records = ws.get_all_records()
    return records


def count_important(tasks: List[dict]) -> int:
    important = {"HIGH", "BLOCKER", "CRITICAL"}
    count = 0
    for t in tasks:
        # Prefer Russian header, fallback to English
        pr = str(t.get("Приоритет", t.get("Priority", ""))).strip().upper()
        if pr in important:
            count += 1
    return count


def list_high_tasks_with_rows() -> List[Tuple[int, str]]:
    ws = _open_worksheet()
    LOGGER.info("Listing High tasks with row indices")
    values = ws.get_all_values()
    if not values:
        return []
    header_map = {name: idx for idx, name in enumerate(values[0], start=1)}
    prio_idx = header_map.get("Приоритет") or header_map.get("Priority")
    title_idx = header_map.get("Задача") or header_map.get("Title") or 1
    if not prio_idx:
        return []
    result: List[Tuple[int, str]] = []
    for idx, row in enumerate(values[1:], start=2):
        pr = (row[prio_idx - 1] if len(row) >= prio_idx else "").strip().upper()
        if pr == "HIGH":
            title = row[title_idx - 1] if len(row) >= title_idx else ""
            result.append((idx, title))
    return result


def downgrade_row_to_medium(row_index: int) -> None:
    ws = _open_worksheet()
    LOGGER.info("Downgrading row %s to Medium", row_index)
    header_map = _get_header_map(ws)
    prio_idx = header_map.get("Приоритет") or header_map.get("Priority")
    if not prio_idx:
        # Fallback to column 2
        prio_idx = 2
    ws.update_cell(row_index, prio_idx, "Medium")


def add_task_row(
    title: str,
    priority: str,
    project: str | None = None,
    status: str | None = None,
    link: str | None = None,
    task_type: str | None = None,
    plan: str | None = None,
) -> None:
    """Append a new task row.

    Adapts to the worksheet header:
    - If Russian spec is present, fills: Проект, Задача, Статус, Ссылка, Приоритет, Тип, Plan
    - Else falls back to minimal English header: Title, Priority, CreatedAt
    """
    ws = _open_worksheet()
    header_map = _get_header_map(ws)

    # Detect Russian schema
    if header_map.get("Задача") and (header_map.get("Приоритет") or header_map.get("Priority")):
        values = [
            project or "",
            title,
            status or "ToDo",
            link or "",
            priority.capitalize(),
            task_type or "",
            plan or "Unplanned",
        ]
        # Reorder according to actual header order if needed
        ordered: List[str] = []
        for header in ["Проект", "Задача", "Статус", "Ссылка", "Приоритет", "Тип", "Plan"]:
            if header in ("Проект", "Задача", "Статус", "Ссылка", "Приоритет", "Тип", "Plan"):
                # Map to our values by fixed position
                idx = ["Проект", "Задача", "Статус", "Ссылка", "Приоритет", "Тип", "Plan"].index(header)
                ordered.append(values[idx])
        LOGGER.info("Appending Russian-schema row: title='%s' priority='%s'", title, priority)
        ws.append_row(ordered)
    else:
        # Minimal header fallback
        LOGGER.info("Appending minimal row: title='%s' priority='%s'", title, priority)
        ws.append_row([title, priority.capitalize(), datetime.utcnow().isoformat() + "Z"])


def is_important_limit_exceeded(max_count: int = 10) -> bool:
    """Return True if count of important (Critical|Blocker|High) exceeds max_count.

    Does not modify the sheet.
    """
    ws = _open_worksheet()
    values = ws.get_all_values()
    if not values:
        return False
    header_map = {name: idx for idx, name in enumerate(values[0], start=1)}
    prio_idx = header_map.get("Приоритет") or header_map.get("Priority")
    if not prio_idx:
        return False
    important = {"CRITICAL", "BLOCKER", "HIGH"}
    count = 0
    for row in values[1:]:
        pr = (row[prio_idx - 1] if len(row) >= prio_idx else "").strip().upper()
        if pr in important:
            count += 1
    LOGGER.info("Important tasks count=%s (limit=%s)", count, max_count)
    return count > max_count


def delete_first_row_by_title(title: str) -> int:
    """Delete the first row after header where title matches exactly (by 'Задача' or 'Title').

    Returns deleted row index, or 0 if not found.
    """
    ws = _open_worksheet()
    LOGGER.info("Deleting first row by title='%s'", title)
    values = ws.get_all_values()
    if not values:
        return 0
    header_map = {name: idx for idx, name in enumerate(values[0], start=1)}
    title_idx = header_map.get("Задача") or header_map.get("Title") or 1
    for idx, row in enumerate(values[1:], start=2):
        cell_title = row[title_idx - 1] if len(row) >= title_idx else ""
        if cell_title == title:
            ws.delete_rows(idx)
            LOGGER.info("Deleted worksheet row %s for title match", idx)
            return idx
    LOGGER.info("No worksheet row found for title match")
    return 0



