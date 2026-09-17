import os
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

DATABASE_PATH = Path(__file__).resolve().parent.parent / "instance" / "account.sqlite3"
VALID_ACTIONS = {"favorite", "watched", "watch_later"}


def get_connection():
    DATABASE_PATH.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS title_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                title_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                poster_path TEXT,
                action TEXT NOT NULL CHECK (action IN ('favorite', 'watched', 'watch_later')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, media_type, title_id, action),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )


def create_user(username, email, password):
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, generate_password_hash(password)),
            )
            return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None


def get_user_by_email(email):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()


def get_user_by_id(user_id):
    with get_connection() as connection:
        return connection.execute(
            "SELECT id, username, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def password_is_valid(user, password):
    return user is not None and check_password_hash(user["password_hash"], password)


def save_title_action(user_id, media_type, title_id, title, poster_path, action):
    if action not in VALID_ACTIONS:
        raise ValueError("Unsupported title action")

    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT id FROM title_actions
            WHERE user_id = ? AND media_type = ? AND title_id = ? AND action = ?
            """,
            (user_id, media_type, title_id, action),
        ).fetchone()
        if existing:
            connection.execute("DELETE FROM title_actions WHERE id = ?", (existing["id"],))
            return False

        connection.execute(
            """
            INSERT INTO title_actions
                (user_id, media_type, title_id, title, poster_path, action)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, media_type, title_id, title, poster_path, action),
        )
        return True


def get_title_actions(user_id, media_type, title_id):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT action FROM title_actions
            WHERE user_id = ? AND media_type = ? AND title_id = ?
            """,
            (user_id, media_type, title_id),
        ).fetchall()
        return {row["action"] for row in rows}


def get_user_actions(user_id):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT media_type, title_id, title, poster_path, action
            FROM title_actions
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
