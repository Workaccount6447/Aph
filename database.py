import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Tuple

DB_PATH = os.getenv("DB_PATH", "giveaway.db")


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT DEFAULT '',
                full_name     TEXT DEFAULT '',
                referrer_id   INTEGER,
                referral_count INTEGER DEFAULT 0,
                joined_channel INTEGER DEFAULT 0,
                joined_at     TEXT DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()

    # ─── User Management ───────────────────────────────────────

    def add_user(
        self,
        user_id: int,
        username: str,
        full_name: str,
        referrer_id: Optional[int] = None,
    ) -> bool:
        """Insert user if not exists. Returns True if newly added."""
        existing = self.get_user(user_id)
        if existing:
            # Update name/username in case they changed
            self.conn.execute(
                "UPDATE users SET username=?, full_name=? WHERE user_id=?",
                (username, full_name, user_id),
            )
            self.conn.commit()
            return False

        self.conn.execute(
            """INSERT INTO users (user_id, username, full_name, referrer_id)
               VALUES (?, ?, ?, ?)""",
            (user_id, username, full_name, referrer_id),
        )
        self.conn.commit()
        return True

    def get_user(self, user_id: int) -> Optional[Tuple]:
        cur = self.conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        )
        return cur.fetchone()

    def get_referrer(self, user_id: int) -> Optional[int]:
        cur = self.conn.execute(
            "SELECT referrer_id FROM users WHERE user_id=?", (user_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def mark_channel_joined(self, user_id: int):
        self.conn.execute(
            "UPDATE users SET joined_channel=1 WHERE user_id=?", (user_id,)
        )
        self.conn.commit()

    def has_joined_channel(self, user_id: int) -> bool:
        cur = self.conn.execute(
            "SELECT joined_channel FROM users WHERE user_id=?", (user_id,)
        )
        row = cur.fetchone()
        return bool(row[0]) if row else False

    # ─── Referrals ─────────────────────────────────────────────

    def increment_referral(self, referrer_id: int):
        """Increment referral count for a user."""
        self.conn.execute(
            "UPDATE users SET referral_count = referral_count + 1 WHERE user_id=?",
            (referrer_id,),
        )
        self.conn.commit()

    def get_referral_count(self, user_id: int) -> int:
        cur = self.conn.execute(
            "SELECT referral_count FROM users WHERE user_id=?", (user_id,)
        )
        row = cur.fetchone()
        return row[0] if row else 0

    # ─── Listings ──────────────────────────────────────────────

    def get_all_users(self) -> List[Tuple]:
        """Returns (user_id, username, full_name, referral_count) for all users."""
        cur = self.conn.execute(
            "SELECT user_id, username, full_name, referral_count FROM users ORDER BY referral_count DESC"
        )
        return cur.fetchall()

    def get_eligible_users(self, min_refs: int) -> List[Tuple]:
        """Returns users who have reached the referral threshold."""
        cur = self.conn.execute(
            """SELECT user_id, username, full_name, referral_count
               FROM users WHERE referral_count >= ?
               ORDER BY referral_count DESC""",
            (min_refs,),
        )
        return cur.fetchall()

    def total_users(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]

    def close(self):
        self.conn.close()
