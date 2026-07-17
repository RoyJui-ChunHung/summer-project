import os
import re
from abc import ABC, abstractmethod

from dotenv import load_dotenv
from openai import OpenAI

from tools import SQLExecutor

load_dotenv()

MODEL = "qwen/qwen3.5-9b"  # or "openai/gpt-4o-mini"

_SYSTEM_MSG = (
    "You are an expert SQL assistant. Given a database schema and a question, "
    "write a single SQLite SQL query that answers the question. "
    "Return ONLY the SQL query — no explanation, no markdown, no code fences."
)


def format_schema(db_id: str, schema: dict) -> str:
    if not schema:
        return f"Database: {db_id}\n(schema not available)"

    table_names  = schema.get("table_names_original", [])
    col_names    = schema.get("column_names_original", [])  # [[table_idx, col_name], ...]
    col_types    = schema.get("column_types", [])
    primary_keys = set(schema.get("primary_keys", []))
    foreign_keys = schema.get("foreign_keys", [])           # [[col_idx, col_idx], ...]

    tables = {}
    for idx, (tbl_idx, col_name) in enumerate(col_names):
        if tbl_idx == -1:
            continue
        tables.setdefault(tbl_idx, []).append((idx, col_name, col_types[idx]))

    lines = [f"Database: {db_id}", ""]
    for tbl_idx, tbl_name in enumerate(table_names):
        col_defs = []
        for col_idx, col_name, col_type in tables.get(tbl_idx, []):
            pk = " PRIMARY KEY" if col_idx in primary_keys else ""
            col_defs.append(f"  {col_name} {col_type.upper()}{pk}")
        lines.append(f"CREATE TABLE {tbl_name} (\n" + ",\n".join(col_defs) + "\n);")
        lines.append("")

    if foreign_keys:
        lines.append("-- Foreign keys:")
        for src_idx, dst_idx in foreign_keys:
            src_tbl = table_names[col_names[src_idx][0]]
            src_col = col_names[src_idx][1]
            dst_tbl = table_names[col_names[dst_idx][0]]
            dst_col = col_names[dst_idx][1]
            lines.append(f"--   {src_tbl}.{src_col} -> {dst_tbl}.{dst_col}")

    return "\n".join(lines)


def _parse_response(resp) -> tuple:
    """Return (raw_text, cleaned_sql) from an OpenAI chat completion."""
    msg = resp.choices[0].message
    # Qwen3 sometimes puts the answer in reasoning when content is truncated
    raw = msg.content or getattr(msg, "reasoning", None) or ""
    sql = re.sub(r"```(?:sql)?\s*", "", raw, flags=re.IGNORECASE).replace("```", "").strip()
    return raw, sql


class Agent(ABC):
    model: str
    max_retries: int

    @abstractmethod
    def predict(self, question: str, db_id: str, executor: SQLExecutor, schema: dict) -> str:
        ...


class SingleShotAgent(Agent):
    max_retries = 1

    def __init__(self, model: str = MODEL):
        self.model = model
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )

    def predict(self, question: str, db_id: str, executor: SQLExecutor, schema: dict) -> str:
        messages = [
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user", "content": f"Schema:\n{format_schema(db_id, schema)}\n\nQuestion: {question}\n\nSQL: /no-think"},
        ]
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, max_tokens=2048, temperature=0.0,
        )
        _, sql = _parse_response(resp)
        return sql


class FeedbackLoopAgent(Agent):
    def __init__(self, model: str = MODEL, max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )

    def predict(self, question: str, db_id: str, executor: SQLExecutor, schema: dict) -> str:
        messages = [
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user", "content": f"Schema:\n{format_schema(db_id, schema)}\n\nQuestion: {question}\n\nSQL: /no-think"},
        ]

        last_sql = ""
        for attempt in range(self.max_retries):
            resp = self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=2048, temperature=0.0,
            )
            raw, sql = _parse_response(resp)
            last_sql = sql

            result = executor.execute(sql)
            if result.ok:
                return sql
            if attempt < self.max_retries - 1:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": f"That SQL raised an error: {result.error}\nPlease fix it and return only the corrected SQL.",
                })

        return last_sql
