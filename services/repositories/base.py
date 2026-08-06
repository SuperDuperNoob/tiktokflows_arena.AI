"""Base repository class."""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional
import sqlite3


class BaseRepository(ABC):
    """Base repository with common database operations."""

    def __init__(self, db_path: str):
        self._db_path = db_path

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query and return cursor."""
        with self.connection() as conn:
            return conn.execute(query, params)

    def fetchone(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row."""
        with self.connection() as conn:
            cur = conn.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def fetchall(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows."""
        with self.connection() as conn:
            cur = conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """Insert a row and return the ID."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        with self.connection() as conn:
            cur = conn.execute(query, tuple(data.values()))
            return cur.lastrowid or 0

    def update(self, table: str, data: Dict[str, Any], where: str, where_params: tuple) -> int:
        """Update rows and return count."""
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"
        params = tuple(data.values()) + where_params
        with self.connection() as conn:
            cur = conn.execute(query, params)
            return cur.rowcount

    def delete(self, table: str, where: str, where_params: tuple) -> int:
        """Delete rows and return count."""
        query = f"DELETE FROM {table} WHERE {where}"
        with self.connection() as conn:
            cur = conn.execute(query, where_params)
            return cur.rowcount

    @abstractmethod
    def get_table_name(self) -> str:
        """Return the table name for this repository."""
        pass