import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

import aiosqlite

class DBManager:
    def __init__(self, db_path: str = "database.db"):
        self.db_path = db_path 
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self): 
        if not self._connection: 
            self._connection = await aiosqlite.connect(self.db_path) 
            self._connection.row_factory = aiosqlite.Row

            await self._connection.execute("PRAGMA foreign_keys = ON;")
            await self._connection.commit() 

    async def disconnect(self) -> None:
        """Close the database connection safely."""
        if self._connection:
            await self._connection.close()
            self._connection = None
 
    async def init_database(self):
        await self._connection.execute(
            """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    msg TEXT NOT NULL,
                    date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    role TEXT NOT NULL
                )
            """
        ) 
        await self._connection.commit()

    async def save_chat_message(self, msg_id: int | str, text: str, role: str = "user") -> str:
        
        await self._connection.execute(
            """
            INSERT INTO messages (msg, role) 
            VALUES (?, ?)
            """,
            (text, role)
        )
        await self._connection.commit()
        return str(msg_id)

    async def get_chat_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch latest messages ordered by date."""
        async with self._connection.execute(
            "SELECT id, msg, date, role FROM messages ORDER BY date DESC LIMIT ?", 
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            # aiosqlite.Row objects can be converted directly into standard dictionaries
            return [dict(row) for row in rows]
