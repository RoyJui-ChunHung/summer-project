import os
import re
import time
from abc import ABC, abstractmethod

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI

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
    if resp is None or not resp.choices:
        return "", ""
    msg = resp.choices[0].message
    # Qwen3 sometimes puts the answer in reasoning when content is truncated
    raw = msg.content or getattr(msg, "reasoning", None) or ""

    # Try code-fenced block first (cleanest case)
    fence = re.search(r"```(?:sql)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        return raw, fence.group(1).strip()

    # Strip any unclosed fence markers
    text = re.sub(r"```(?:sql)?\s*", "", raw, flags=re.IGNORECASE).replace("```", "").strip()

    # Qwen3 often prepends reasoning prose; find first top-level SQL statement
    match = re.search(r"^(SELECT|WITH)\b", text, re.IGNORECASE | re.MULTILINE)
    sql = text[match.start():].strip() if match else text
    return raw, sql


def _is_sql(s: str) -> bool:
    return bool(re.match(r"\s*(SELECT|WITH|INSERT|UPDATE|DELETE)\b", s, re.IGNORECASE))


def _chat(client: OpenAI, messages: list, model: str, max_retries: int = 6) -> object:
    """Call chat.completions.create with exponential backoff on transient errors."""
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, max_tokens=2048, temperature=0.0,
                timeout=60,
            )
            if resp and resp.choices:
                return resp
            # OpenRouter occasionally returns HTTP 200 with null choices; treat as transient
            err = "empty choices"
        except (APIConnectionError, APIStatusError) as e:
            err = f"{type(e).__name__}"
            resp = None
        if attempt == max_retries - 1:
            break
        wait = 5 * (2 ** attempt)  # 5, 10, 20, 40, 80s
        print(f"  [retry {attempt+1}/{max_retries-1}] {err} — retrying in {wait}s")
        time.sleep(wait)
    return resp  # caller gets None/empty; _parse_response handles it


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
        _, sql = _parse_response(_chat(self.client, messages, self.model))
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
            raw, sql = _parse_response(_chat(self.client, messages, self.model))
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


_REVIEW_PROMPTS = {
    "generic": (
        "Does this SQL correctly answer the question given the schema? "
        "If not, fix it and return only the corrected SQL, no explanation. /no-think"
    ),
    "gentle": (
        "Take a careful second look at this SQL. "
        "Check that JOINs, subqueries, GROUP BY, and filter conditions match the question exactly. "
        "Return only the corrected SQL, no explanation. /no-think"
    ),
}


class BlindCorrectionAgent(Agent):
    def __init__(self, model: str = MODEL, max_retries: int = 3, flavor: str = "generic"):
        self.model = model
        self.max_retries = max_retries
        self.flavor = flavor
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )

    def predict(self, question: str, db_id: str, executor: SQLExecutor, schema: dict) -> str:
        schema_str = format_schema(db_id, schema)
        messages = [
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user", "content": f"Schema:\n{schema_str}\n\nQuestion: {question}\n\nSQL: /no-think"},
        ]

        # Pass 1: generate
        raw, sql = _parse_response(_chat(self.client, messages, self.model))

        # Passes 2..max_retries: blind review (no execution, fresh call each time)
        review_prompt = _REVIEW_PROMPTS[self.flavor]
        for _ in range(self.max_retries - 1):
            review_messages = [
                {"role": "system", "content": _SYSTEM_MSG},
                {"role": "user", "content": (
                    f"Schema:\n{schema_str}\n\n"
                    f"Question: {question}\n\n"
                    f"Current SQL:\n{sql}\n\n"
                    f"{review_prompt}"
                )},
            ]
            _, revised = _parse_response(_chat(self.client, review_messages, self.model))
            if not _is_sql(revised):
                break  # model returned non-SQL; keep current
            if " ".join(revised.lower().split()) == " ".join(sql.lower().split()):
                break
            sql = revised

        return sql
