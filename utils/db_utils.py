# db_utils.py
import sqlite3
import threading
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
from typing import List, Dict, Optional, Any
from datetime import datetime


# Thread-local storage
_thread_local = SimpleNamespace() if sys.platform == "emscripten" else threading.local()


def get_db_path():
    """Obtain the database path"""
    if sys.platform == "emscripten":
        os.makedirs("/ts2r-data", exist_ok=True)
        return "/ts2r-data/app.db"
    current_path = "./app.db"
    return current_path


def get_connection():
    """Obtain the thread-local database connection"""
    if not hasattr(_thread_local, "connection"):
        _thread_local.connection = sqlite3.connect(
            get_db_path(),
            check_same_thread=False
        )
        _thread_local.connection.row_factory = sqlite3.Row
    return _thread_local.connection


@contextmanager
def get_db():
    """Database Context Manager"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e


def init_db():
    """Initialize the database tables"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Create a conversation table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create a messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
            )
        ''')

        # Create an analysis results table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                result_data TEXT NOT NULL,
                markdown_table TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
            )
        ''')

        # Create an index to improve query performance
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_messages_session_id
            ON messages(session_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_analysis_results_session_id
            ON analysis_results(session_id)
        ''')

        conn.commit()

    if sys.platform == "emscripten":
        _seed_browser_test_database(conn)


def _seed_browser_test_database(conn, sample_path=None):
    """Seed the published test case once, without replacing a user's history."""
    marker = Path(get_db_path()).with_name(".test-case-initialized")
    sample = Path(sample_path) if sample_path else Path(__file__).resolve().parent.parent / "samples/app.db"
    if marker.exists() or not sample.exists():
        return

    has_content = any(
        conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
        for table in ("messages", "analysis_results")
    )
    session_names = [row[0] for row in conn.execute("SELECT session_name FROM sessions")]
    untouched = not has_content and session_names in ([], ["Session 1"])
    if untouched:
        # SQLite backup copies the test snapshot without sharing visitor databases.
        source = sqlite3.connect(f"file:{sample}?mode=ro", uri=True)
        try:
            source.backup(conn)
        finally:
            source.close()
        conn.commit()
    # Also mark nonempty databases so clearing a conversation never reseeds it.
    marker.write_text("seeded\n" if untouched else "existing-history-preserved\n")


# ============= session management =============

def create_session(session_name: str) -> int:
    """Create a new conversation"""
    existing_session = get_session_by_name(session_name)
    if existing_session:
        return existing_session['id']

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (session_name) VALUES (?)",
            (session_name,)
        )
        return cursor.lastrowid


def get_all_sessions() -> List[Dict[str, Any]]:
    """Get all conversations"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, session_name, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_session_by_name(session_name: str) -> Optional[Dict[str, Any]]:
    """Get a session by its name"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, session_name, created_at, updated_at FROM sessions WHERE session_name = ?",
            (session_name,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def update_session_name(old_name: str, new_name: str) -> bool:
    """Update conversation name"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET session_name = ?, updated_at = CURRENT_TIMESTAMP WHERE session_name = ?",
            (new_name, old_name)
        )
        return cursor.rowcount > 0


def delete_session(session_name: str) -> bool:
    """Delete a conversation and all its messages"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM sessions WHERE session_name = ?",
            (session_name,)
        )
        return cursor.rowcount > 0


def update_session_timestamp(session_name: str):
    """Update the last updated time of a session"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_name = ?",
            (session_name,)
        )


# ============= message management =============

def add_message(session_name: str, role: str, content: str) -> int:
    """Add a message to a session"""
    # Ensure the session exists
    session = get_session_by_name(session_name)
    if not session:
        session_id = create_session(session_name)
    else:
        session_id = session['id']

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )
        # Update the session timestamp
        update_session_timestamp(session_name)
        return cursor.lastrowid


def get_messages(session_name: str) -> List[Dict[str, str]]:
    """Get all messages for a session"""
    session = get_session_by_name(session_name)
    if not session:
        return []

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session['id'],)
        )
        rows = cursor.fetchall()
        return [{"role": row['role'], "content": row['content']} for row in rows]


def clear_messages(session_name: str) -> bool:
    """Clear all messages for a session"""
    session = get_session_by_name(session_name)
    if not session:
        return False

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM messages WHERE session_id = ?",
            (session['id'],)
        )
        return cursor.rowcount > 0


def get_message_count(session_name: str) -> int:
    """Get the number of messages in a session"""
    session = get_session_by_name(session_name)
    if not session:
        return 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM messages WHERE session_id = ?",
            (session['id'],)
        )
        row = cursor.fetchone()
        return row['count'] if row else 0


# ============= session data synchronization =============

def sync_sessions_from_memory(sessions_dict: Dict[str, List[Dict[str, str]]]):
    """Sync sessions from memory to database"""
    with get_db() as conn:
        for session_name, messages in sessions_dict.items():
            session = get_session_by_name(session_name)
            if not session:
                create_session(session_name)

            clear_messages(session_name)

            for msg in messages:
                add_message(session_name, msg['role'], msg['content'])


def load_sessions_to_memory() -> Dict[str, List[Dict[str, str]]]:
    """Load all conversations from the database to memory"""
    sessions = get_all_sessions()
    sessions_dict = {}

    for session in sessions:
        session_name = session['session_name']
        messages = get_messages(session_name)
        sessions_dict[session_name] = messages

    # If no conversations exist, create a default conversation
    if not sessions_dict:
        sessions_dict["Session 1"] = []

    return sessions_dict


# ============= analysis result management =============

def save_analysis_result(session_name: str, result_data: dict, markdown_table: str) -> int:
    """Save analysis results to the database"""
    session = get_session_by_name(session_name)
    if not session:
        session_id = create_session(session_name)
    else:
        session_id = session['id']

    # First, delete the old analysis results for this session
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM analysis_results WHERE session_id = ?",
            (session_id,)
        )

        # Save the new analysis results
        result_json = json.dumps(result_data, ensure_ascii=False)
        cursor.execute(
            "INSERT INTO analysis_results (session_id, result_data, markdown_table) VALUES (?, ?, ?)",
            (session_id, result_json, markdown_table)
        )
        # Update the session timestamp
        update_session_timestamp(session_name)
        return cursor.lastrowid


def get_analysis_result(session_name: str) -> Optional[Dict[str, Any]]:
    """Get the analysis result for a session"""
    session = get_session_by_name(session_name)
    if not session:
        return None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT result_data, markdown_table, created_at FROM analysis_results WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session['id'],)
        )
        row = cursor.fetchone()
        if row:
            return {
                'result_data': json.loads(row['result_data']),
                'markdown_table': row['markdown_table'],
                'created_at': row['created_at']
            }
        return None


def delete_analysis_result(session_name: str) -> bool:
    """Delete the analysis result for a session"""
    session = get_session_by_name(session_name)
    if not session:
        return False

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM analysis_results WHERE session_id = ?",
            (session['id'],)
        )
        return cursor.rowcount > 0
