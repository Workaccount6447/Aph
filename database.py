import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "/app/data/bot.db")

class Database:
    def __init__(self):
        # Ensure the directory exists before opening the file
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._init_tables()

    def _init_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT    DEFAULT '',
                full_name   TEXT    DEFAULT '',
                referrer_id INTEGER DEFAULT NULL,
                ref_count   INTEGER DEFAULT 0,
                joined      INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    # ── Write ──────────────────────────────────────────────

    def add_user(self, user_id: int, username: str, full_name: str, referrer_id=None):
        self.conn.execute("""
            INSERT INTO users (user_id, username, full_name, referrer_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name
        """, (user_id, username, full_name, referrer_id))
        self.conn.commit()

    def mark_channel_joined(self, user_id: int):
        self.conn.execute(
            "UPDATE users SET joined = 1 WHERE user_id = ?", (user_id,)
        )
        self.conn.commit()

    def increment_referral(self, user_id: int):
        self.conn.execute(
            "UPDATE users SET ref_count = ref_count + 1 WHERE user_id = ?", (user_id,)
        )
        self.conn.commit()

    def recover_user(self, username: str, full_name: str, ref_count: int):
        """Upsert a user from recovered leaderboard data.
        Uses a negative synthetic user_id (hash) so real IDs are never clobbered.
        If a real user with the same username already exists, their ref_count is updated.
        """
        # Try to find existing user by username first
        row = self.conn.execute(
            "SELECT user_id FROM users WHERE username = ?", (username,)
        ).fetchone() if username else None

        if row:
            self.conn.execute(
                "UPDATE users SET ref_count = ?, full_name = CASE WHEN full_name = '' THEN ? ELSE full_name END "
                "WHERE user_id = ?",
                (ref_count, full_name, row[0]),
            )
        else:
            # Generate a stable synthetic negative ID from the username/name string
            key = username if username else full_name
            synthetic_id = -(abs(hash(key)) % (10 ** 15))
            self.conn.execute(
                """
                INSERT INTO users (user_id, username, full_name, ref_count, joined)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    username  = excluded.username,
                    full_name = excluded.full_name,
                    ref_count = excluded.ref_count
                """,
                (synthetic_id, username, full_name, ref_count),
            )
        self.conn.commit()

    # ── Read ───────────────────────────────────────────────

    def get_referral_count(self, user_id: int) -> int:
        row = self.conn.execute(
            "SELECT ref_count FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else 0

    def get_referrer(self, user_id: int):
        row = self.conn.execute(
            "SELECT referrer_id FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else None

    def get_rank(self, user_id: int):
        """Returns (rank, total_users, top_ref_count)."""
        rows = self.conn.execute(
            "SELECT user_id, ref_count FROM users ORDER BY ref_count DESC"
        ).fetchall()
        total = len(rows)
        top_count = rows[0][1] if rows else 0
        rank = next((i + 1 for i, (uid, _) in enumerate(rows) if uid == user_id), total)
        return rank, total, top_count

    def get_all_users(self):
        """Returns list of (user_id, username, full_name, ref_count) sorted DESC."""
        return self.conn.execute(
            "SELECT user_id, username, full_name, ref_count "
            "FROM users ORDER BY ref_count DESC"
        ).fetchall()
