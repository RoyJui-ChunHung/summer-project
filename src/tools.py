import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ExecutionResult:
    rows:  Optional[frozenset]
    error: Optional[str]

    @property
    def ok(self) -> bool:
        return self.error is None


class SQLExecutor:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def execute(self, sql: str) -> ExecutionResult:
        """Run SQL and return an ExecutionResult with rows or error message."""
        try:
            conn   = sqlite3.connect(str(self.db_path))
            cursor = conn.execute(sql)
            rows   = cursor.fetchall()
            conn.close()
            return ExecutionResult(rows=frozenset(rows), error=None)
        except Exception as e:
            return ExecutionResult(rows=None, error=str(e))
