import aiosqlite
import os
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.getenv("SQLITE_PATH", "data/interactions.db")


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                user_id         TEXT,
                course_id       TEXT,
                exercise_id     TEXT,
                srl_phase       TEXT,
                strategy        TEXT,
                question_text   TEXT,
                student_code    TEXT,
                test_results    TEXT,
                custom_question TEXT,
                response_text   TEXT,
                latency_ms      INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS response_sessions (
                session_key      TEXT PRIMARY KEY,
                user_id          TEXT,
                course_id        TEXT,
                exercise_id      TEXT,
                last_response_id TEXT,
                updated_at       TEXT NOT NULL
            )
        """)
        await db.commit()
        # Safe column migrations for existing SQLite databases.
        for statement in (
            "ALTER TABLE interactions ADD COLUMN rating TEXT",
            "ALTER TABLE interactions ADD COLUMN session_key TEXT",
            "ALTER TABLE interactions ADD COLUMN previous_response_id TEXT",
            "ALTER TABLE interactions ADD COLUMN openai_response_id TEXT",
            "ALTER TABLE interactions ADD COLUMN preferred_language TEXT",
            "ALTER TABLE interactions ADD COLUMN exercise_label TEXT",
        ):
            try:
                await db.execute(statement)
                await db.commit()
            except aiosqlite.OperationalError:
                pass  # column already exists


async def log_interaction(
    user_id: str,
    course_id: str,
    exercise_id: str,
    srl_phase: str,
    strategy: str,
    question_text: str,
    student_code: str,
    test_results: str,
    custom_question: str,
    response_text: str,
    latency_ms: int,
    session_key: Optional[str] = None,
    previous_response_id: Optional[str] = None,
    openai_response_id: Optional[str] = None,
    preferred_language: str = "",
    exercise_label: str = "",
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO interactions (
                timestamp, user_id, course_id, exercise_id,
                srl_phase, strategy, question_text, student_code,
                test_results, custom_question, response_text, latency_ms,
                session_key, previous_response_id, openai_response_id,
                preferred_language, exercise_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                user_id, course_id, exercise_id,
                srl_phase, strategy, question_text, student_code,
                test_results, custom_question, response_text, latency_ms,
                session_key, previous_response_id, openai_response_id,
                preferred_language, exercise_label,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def fetch_logs(limit: int = 50, offset: int = 0) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, timestamp, user_id, course_id, exercise_id,
                   srl_phase, strategy, latency_ms
            FROM interactions
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def update_rating(interaction_id: int, rating: Optional[str]) -> bool:
    """Update the rating for an interaction. Returns True if found, False if not."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE interactions SET rating = ? WHERE id = ?",
            (rating, interaction_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def fetch_last_response_id(session_key: Optional[str]) -> Optional[str]:
    """Return the most recent OpenAI response id for a tutoring session."""
    if not session_key:
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            """
            SELECT last_response_id
            FROM response_sessions
            WHERE session_key = ?
            """,
            [session_key],
        )
        if not rows:
            return None
        return rows[0][0]


async def upsert_response_session(
    session_key: Optional[str],
    user_id: str,
    course_id: str,
    exercise_id: str,
    last_response_id: Optional[str],
) -> None:
    """Create or update the session tracking row for a student-question thread."""
    if not session_key or not last_response_id:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO response_sessions (
                session_key, user_id, course_id, exercise_id, last_response_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_key) DO UPDATE SET
                user_id = excluded.user_id,
                course_id = excluded.course_id,
                exercise_id = excluded.exercise_id,
                last_response_id = excluded.last_response_id,
                updated_at = excluded.updated_at
            """,
            (
                session_key,
                user_id,
                course_id,
                exercise_id,
                last_response_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await db.commit()
