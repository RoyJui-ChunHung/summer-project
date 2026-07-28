import sqlite3
from abc import ABC, abstractmethod
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


class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    def __call__(self, arg):
        ...


class SQLExecutor(Tool):
    name = "sql_executor"
    description = "Execute a SQLite SQL query and return the result rows or an error message."

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def execute(self, sql: str) -> ExecutionResult:
        try:
            conn   = sqlite3.connect(str(self.db_path))
            cursor = conn.execute(sql)
            rows   = cursor.fetchall()
            conn.close()
            return ExecutionResult(rows=frozenset(rows), error=None)
        except Exception as e:
            return ExecutionResult(rows=None, error=str(e))

    def __call__(self, arg: str) -> ExecutionResult:
        return self.execute(arg)
