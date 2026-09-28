import sqlite3
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.config import settings

def get_connection():
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                prompt TEXT NOT NULL,
                models_queried TEXT NOT NULL,
                judge_model TEXT,
                winner TEXT,
                evaluation_summary TEXT,
                judge_reason TEXT,
                user_rating INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                response_text TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                word_count INTEGER DEFAULT 0,
                char_count INTEGER DEFAULT 0,
                code_blocks INTEGER DEFAULT 0,
                elapsed_seconds REAL DEFAULT 0.0,
                FOREIGN KEY (query_id) REFERENCES queries (id) ON DELETE CASCADE
            )
        """)
        conn.commit()

def save_query_record(
    prompt: str,
    models_queried: List[str],
    judge_model: Optional[str] = None,
    winner: Optional[str] = None,
    evaluation_summary: Optional[str] = None,
    judge_reason: Optional[str] = None
) -> int:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO queries (created_at, prompt, models_queried, judge_model, winner, evaluation_summary, judge_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                prompt,
                json.dumps(models_queried),
                judge_model,
                winner,
                evaluation_summary,
                judge_reason
            )
        )
        query_id = cursor.lastrowid
        conn.commit()
        return query_id

def save_response_record(
    query_id: int,
    model_name: str,
    response_text: Optional[str],
    status: str,
    error_message: Optional[str] = None,
    word_count: int = 0,
    char_count: int = 0,
    code_blocks: int = 0,
    elapsed_seconds: float = 0.0
):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO responses (query_id, model_name, response_text, status, error_message, word_count, char_count, code_blocks, elapsed_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query_id,
                model_name,
                response_text,
                status,
                error_message,
                word_count,
                char_count,
                code_blocks,
                elapsed_seconds
            )
        )
        conn.commit()

def update_query_evaluation(
    query_id: int,
    winner: str,
    evaluation_summary: str,
    judge_reason: str,
    judge_model: str
):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE queries
            SET winner = ?, evaluation_summary = ?, judge_reason = ?, judge_model = ?
            WHERE id = ?
            """,
            (winner, evaluation_summary, judge_reason, judge_model, query_id)
        )
        conn.commit()

def get_history(limit: int = 20) -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM queries ORDER BY id DESC LIMIT ?", (limit,))
        queries = [dict(row) for row in cursor.fetchall()]
        
        for q in queries:
            q["models_queried"] = json.loads(q["models_queried"])
            cursor.execute("SELECT * FROM responses WHERE query_id = ?", (q["id"],))
            q["responses"] = [dict(r) for r in cursor.fetchall()]
            
        return queries

def get_query_by_id(query_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM queries WHERE id = ?", (query_id,))
        row = cursor.fetchone()
        if not row:
            return None
        q = dict(row)
        q["models_queried"] = json.loads(q["models_queried"])
        cursor.execute("SELECT * FROM responses WHERE query_id = ?", (query_id,))
        q["responses"] = [dict(r) for r in cursor.fetchall()]
        return q
