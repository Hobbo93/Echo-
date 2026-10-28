"""Permanent memory for Echo."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).with_name("echo_memory.db")


def connect():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    db.commit()
    return db


def remember(category, content):
    """Save information permanently."""
    if not isinstance(content, str):
        content = json.dumps(content)

    with connect() as db:
        cursor = db.execute(
            """INSERT INTO memories
            (category, content, created_at)
            VALUES (?, ?, ?)""",
            (
                category,
                content,
                datetime.now(timezone.utc).isoformat()
            )
        )
        return cursor.lastrowid


def recall(category=None, limit=20):
    """Retrieve saved information."""
    limit = max(1, min(int(limit), 500))

    with connect() as db:
        db.row_factory = sqlite3.Row

        if category is None:
            rows = db.execute(
                """SELECT * FROM memories
                ORDER BY id DESC LIMIT ?""",
                (limit,)
            )
        else:
            rows = db.execute(
                """SELECT * FROM memories
                WHERE category = ?
                ORDER BY id DESC LIMIT ?""",
                (category, limit)
            )

        return [dict(row) for row in rows]


def forget(memory_id):
    """Delete a specific memory."""
    with connect() as db:
        result = db.execute(
            "DELETE FROM memories WHERE id = ?",
            (memory_id,)
        )
        return result.rowcount > 0


if __name__ == "__main__":
    remember("system", "Echo memory initialized")
    print("Echo memory ready!")
    print(recall(limit=1))
