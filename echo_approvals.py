"""Echo AI Employee Approval System."""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB = Path(__file__).with_name("echo_approvals.db")


def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)
    db.commit()
    return db


def request_approval(employee, action, reason):
    """Request permission before taking action."""

    with connect() as db:
        result = db.execute("""
            INSERT INTO approvals
            (employee, action, reason, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            employee,
            action,
            reason,
            datetime.now(timezone.utc).isoformat()
        ))

        return result.lastrowid


def pending_approvals():
    """Show requests waiting for approval."""

    with connect() as db:
        rows = db.execute("""
            SELECT * FROM approvals
            WHERE status = 'pending'
            ORDER BY id DESC
        """).fetchall()

        return [dict(row) for row in rows]


def decide(request_id, decision):
    """Approve or reject a request."""

    if decision not in ("approved", "rejected"):
        raise ValueError("Invalid decision")

    with connect() as db:
        result = db.execute("""
            UPDATE approvals
            SET status = ?
            WHERE id = ? AND status = 'pending'
        """, (decision, request_id))

        return result.rowcount > 0


def is_approved(request_id):
    """Check whether permission was granted."""

    with connect() as db:
        row = db.execute("""
            SELECT status FROM approvals
            WHERE id = ?
        """, (request_id,)).fetchone()

        return bool(row and row["status"] == "approved")


if __name__ == "__main__":
    print("Echo Approval System Ready")
    print("Pending:", pending_approvals())
