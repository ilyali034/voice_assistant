from pathlib import Path
from typing import Any

import aiosqlite


class DBManager:
    def __init__(self, db_path: str | Path = "database.db") -> None:
        self.db_path = Path(db_path)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._connection is None:
            if str(self.db_path) != ":memory:":
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = await aiosqlite.connect(str(self.db_path))
            self._connection.row_factory = aiosqlite.Row
            await self._connection.execute("PRAGMA foreign_keys = ON")
            await self._connection.commit()

    async def disconnect(self) -> None:
        """Close the database connection safely."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    def _require_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not connected; call connect() first")
        return self._connection

    async def init_database(self) -> None:
        connection = self._require_connection()
        await connection.execute(
            """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    msg TEXT NOT NULL,
                    date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    role TEXT NOT NULL
                )
            """
        ) 
        await connection.commit()

    async def save_chat_message(self, text: str, role: str = "user") -> int:
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            INSERT INTO messages (msg, role) 
            VALUES (?, ?)
            """,
            (text, role),
        )
        await connection.commit()
        return int(cursor.lastrowid)

    async def get_chat_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch latest messages ordered by date."""
        connection = self._require_connection()
        async with connection.execute(
            "SELECT id, msg, date, role FROM messages ORDER BY date DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
