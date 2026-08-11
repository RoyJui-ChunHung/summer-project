import json
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


def _chat(client: OpenAI, messages: list, model: str, max_retries: int = 6, tools=None) -> object:
    """Call chat.completions.create with exponential backoff on transient errors."""
    for attempt in range(max_retries):
        try:
            kwargs = dict(model=model, messages=messages, max_tokens=2048, temperature=0.0, timeout=60)
            if tools:
                kwargs["tools"] = tools
            resp = client.chat.completions.create(**kwargs)
            if resp and resp.choices:
                return resp
            # OpenRouter occasionally returns HTTP 200 with null choices; treat as transient
            err = "empty choices"
        except (APIConnectionError, APIStatusError, ValueError) as e:
            # ValueError covers json.JSONDecodeError (malformed response body from OpenRouter)
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


_VERIFY_SYSTEM = (
    "You are a SQL result auditor. "
    "Your job is not to write SQL — only to judge whether a result correctly answers a question."
)

_VERIFY_PROMPT = """\
Question: {question}

Database schema:
{schema_str}

SQL that was executed:
{sql}

Rows returned:
{rows_str}

Does this result correctly and completely answer the question?
Reply with exactly one of:
  YES
  NO: <one sentence explaining what is wrong or missing>

/no-think"""

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


def _verify_result(client, model, question: str, schema_str: str, sql: str, rows) -> dict:
    """Call the verifier LLM. Returns {correct: bool, reason: str}."""
    rows_list = list(rows)
    total = len(rows_list)
    if total == 0:
        rows_str = "(empty result set)"
    else:
        sample = rows_list[:10]
        rows_str = "\n".join(str(r) for r in sample)
        if total > 10:
            rows_str += f"\n({total} rows total, showing first 10)"

    prompt = _VERIFY_PROMPT.format(
        question=question, schema_str=schema_str, sql=sql, rows_str=rows_str,
    )
    resp = _chat(client, [
        {"role": "system", "content": _VERIFY_SYSTEM},
        {"role": "user",   "content": prompt},
    ], model)
    raw, _ = _parse_response(resp)

    m = re.search(r'\b(YES|NO)\b', raw, re.IGNORECASE)
    if m is None:
        return {"correct": True, "reason": ""}
    if m.group(1).upper() == "YES":
        return {"correct": True, "reason": ""}
    rest = raw[m.end():].strip()
    reason = re.sub(r'^[:\s]+', '', rest).strip()
    first_sentence = re.split(r'[.\n]', reason)[0].strip() if reason else ""
    return {"correct": False, "reason": first_sentence or "result does not match the question"}


class VerifyAndReviseAgent(Agent):
    def __init__(self, model: str = MODEL, max_retries: int = 3):
        self.model = model
        self.max_retries = max_retries
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
        self._last_calls = 0
        self._last_verify_called = False
        self._last_verify_flagged = False

    def predict(self, question: str, db_id: str, executor: SQLExecutor, schema: dict) -> str:
        self._last_calls = 0
        self._last_verify_called = False
        self._last_verify_flagged = False

        schema_str = format_schema(db_id, schema)
        messages = [
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user", "content": f"Schema:\n{schema_str}\n\nQuestion: {question}\n\nSQL: /no-think"},
        ]

        last_sql = ""
        last_clean_sql = ""  # fallback: if a verify-triggered revision errors, return the last clean result

        for attempt in range(self.max_retries):
            raw, sql = _parse_response(_chat(self.client, messages, self.model))
            self._last_calls += 1
            last_sql = sql

            result = executor.execute(last_sql)

            if not result.ok:
                if attempt < self.max_retries - 1:
                    messages.append({"role": "assistant", "content": last_sql})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"That SQL raised an error: {result.error}\n"
                            "Please fix it and return only the corrected SQL. /no-think"
                        ),
                    })
                continue

            # SQL ran clean — save as fallback, then verify
            last_clean_sql = last_sql
            self._last_verify_called = True
            verdict = self._verify(question, schema_str, last_sql, result.rows)
            self._last_calls += 1

            if verdict["correct"]:
                print(f"  [verify] YES")
                break

            print(f"  [verify] NO: {verdict['reason']}")
            self._last_verify_flagged = True
            if attempt < self.max_retries - 1:
                messages.append({"role": "assistant", "content": last_sql})
                messages.append({
                    "role": "user",
                    "content": (
                        "The query ran without errors but the result appears incorrect.\n"
                        f"Verifier feedback: {verdict['reason']}\n"
                        "Revise the SQL to fix this and return only the corrected SQL. /no-think"
                    ),
                })

        # If all verify-triggered revisions errored, return the last clean execution rather
        # than an errored SQL — execution errors should only occur when every attempt failed.
        return last_clean_sql if last_clean_sql else last_sql

    def _verify(self, question: str, schema_str: str, sql: str, rows) -> dict:
        return _verify_result(self.client, self.model, question, schema_str, sql, rows)


class PipelineAgent(Agent):
    """Three-stage pipeline: error feedback → blind review → verify + revise.
    Each stage has a fixed slot; _last_stage_changed records which one (if any) altered the SQL.
    """

    def __init__(self, model: str = MODEL, error_retries: int = 2):
        self.model = model
        self.error_retries = error_retries
        self.max_retries = error_retries + 3  # upper bound on total calls per example
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
        self._last_stage_changed = None  # None | "error_feedback" | "blind_review" | "verify"

    def predict(self, question: str, db_id: str, executor: SQLExecutor, schema: dict) -> str:
        self._last_stage_changed = None
        schema_str = format_schema(db_id, schema)

        # ── Stage 1: error feedback ──────────────────────────────────────────
        messages = [
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user",   "content": f"Schema:\n{schema_str}\n\nQuestion: {question}\n\nSQL: /no-think"},
        ]
        raw, sql = _parse_response(_chat(self.client, messages, self.model))
        initial_sql = sql
        for _ in range(self.error_retries - 1):
            if executor.execute(sql).ok:
                break
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"That SQL raised an error: {executor.execute(sql).error}\nPlease fix it and return only the corrected SQL. /no-think",
            })
            raw, sql = _parse_response(_chat(self.client, messages, self.model))
        if sql != initial_sql:
            self._last_stage_changed = "error_feedback"

        # ── Stage 2: blind review (1 pass, only when stage 1 produced clean SQL) ──
        if executor.execute(sql).ok:
            review_messages = [
                {"role": "system", "content": _SYSTEM_MSG},
                {"role": "user", "content": (
                    f"Schema:\n{schema_str}\n\n"
                    f"Question: {question}\n\n"
                    f"Current SQL:\n{sql}\n\n"
                    f"{_REVIEW_PROMPTS['generic']}"
                )},
            ]
            _, revised = _parse_response(_chat(self.client, review_messages, self.model))
            norm = lambda s: " ".join(s.lower().split())
            if _is_sql(revised) and norm(revised) != norm(sql) and executor.execute(revised).ok:
                sql = revised
                self._last_stage_changed = "blind_review"

        # ── Stage 3: verify + 1 revision (only when we have clean SQL) ──────
        result = executor.execute(sql)
        if not result.ok:
            return sql
        verdict = _verify_result(self.client, self.model, question, schema_str, sql, result.rows)
        if verdict["correct"]:
            return sql

        revision_messages = [
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user", "content": (
                f"Schema:\n{schema_str}\n\n"
                f"Question: {question}\n\n"
                f"Current SQL:\n{sql}\n\n"
                "The query ran without errors but the result appears incorrect.\n"
                f"Verifier feedback: {verdict['reason']}\n"
                "Revise the SQL to fix this and return only the corrected SQL. /no-think"
            )},
        ]
        _, revised = _parse_response(_chat(self.client, revision_messages, self.model))
        if _is_sql(revised) and executor.execute(revised).ok:
            if " ".join(revised.lower().split()) != " ".join(sql.lower().split()):
                self._last_stage_changed = "verify"
            return revised
        return sql


_REACT_SYSTEM_MSG = (
    "You are an expert SQL assistant. You may call tools to explore the database "
    "before writing your answer. When you are ready, respond with only the SQL query "
    "— no explanation, no markdown, no code fences."
)

_REACT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "Execute a SQL query against the database. Returns rows on success or an error message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "The SQL query to execute."}
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sample_rows",
            "description": "Return up to 5 sample rows from a table to understand its contents and column values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "The name of the table to sample."}
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "Return column names and types for a table using PRAGMA table_info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "The name of the table to describe."}
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_distinct_values",
            "description": "Return up to 20 distinct values from a column to see exact string formats and enumerations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "The table containing the column."},
                    "column_name": {"type": "string", "description": "The column to get distinct values from."},
                },
                "required": ["table_name", "column_name"],
            },
        },
    },
]


class ReActAgent(Agent):
    def __init__(self, model: str = MODEL, max_retries: int = 8):
        self.model = model
        self.max_retries = max_retries
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )

    def predict(self, question: str, db_id: str, executor: SQLExecutor, schema: dict) -> str:
        schema_str = format_schema(db_id, schema)
        messages = [
            {"role": "system", "content": _REACT_SYSTEM_MSG},
            {"role": "user", "content": f"Schema:\n{schema_str}\n\nQuestion: {question} /no-think"},
        ]

        last_sql = ""
        for _ in range(self.max_retries):
            resp = _chat(self.client, messages, self.model, tools=_REACT_TOOLS)
            if not (resp and resp.choices):
                break

            msg = resp.choices[0].message

            if not msg.tool_calls:
                _, sql = _parse_response(resp)
                # Guard 1: prose response — fall back to last clean execute_sql result.
                if not _is_sql(sql):
                    return last_sql
                # Guard 2: final SQL may still error (e.g. wrong column name). Execute it
                # before returning; if it fails, fall back to last_clean_sql so we never
                # return a known-failing query.
                if executor.execute(sql).ok:
                    return sql
                return last_sql

            # Append assistant turn (with tool_calls) as a dict so the SDK serialises it cleanly
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                tool_result = self._dispatch(tc, executor)

                # Only save SQL from execute_sql when it ran cleanly — same idea as
                # last_clean_sql in VerifyAndReviseAgent, so the fallback never returns
                # a known-failing query.
                if tc.function.name == "execute_sql" and not tool_result.startswith("Error:"):
                    try:
                        last_sql = json.loads(tc.function.arguments).get("sql", last_sql)
                    except (json.JSONDecodeError, AttributeError):
                        pass
                print(f"  [tool] {tc.function.name}({tc.function.arguments[:60]}) → {tool_result[:80]}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

        # Fallback: if model never called execute_sql, generate SQL directly from original context
        if not last_sql:
            _, last_sql = _parse_response(_chat(self.client, messages[:2], self.model))
        return last_sql

    def _dispatch(self, tc, executor: SQLExecutor) -> str:
        try:
            args = json.loads(tc.function.arguments)
        except (json.JSONDecodeError, AttributeError):
            return "Error: could not parse tool arguments"

        if tc.function.name == "execute_sql":
            result = executor.execute(args.get("sql", ""))
            if result.ok:
                rows = list(result.rows)[:10]
                return f"{len(result.rows)} row(s): {rows}"
            return f"Error: {result.error}"

        if tc.function.name == "sample_rows":
            table = re.sub(r"\W", "", args.get("table_name", ""))
            result = executor.execute(f"SELECT * FROM {table} LIMIT 5")
            if result.ok:
                return f"{len(result.rows)} row(s): {list(result.rows)}"
            return f"Error: {result.error}"

        if tc.function.name == "describe_table":
            table = re.sub(r"\W", "", args.get("table_name", ""))
            result = executor.execute(f"PRAGMA table_info({table})")
            if result.ok:
                cols = [(r[1], r[2]) for r in result.rows]  # (name, type)
                return f"Columns: {cols}"
            return f"Error: {result.error}"

        if tc.function.name == "get_distinct_values":
            table = re.sub(r"\W", "", args.get("table_name", ""))
            col   = re.sub(r"\W", "", args.get("column_name", ""))
            result = executor.execute(f"SELECT DISTINCT {col} FROM {table} LIMIT 20")
            if result.ok:
                values = [r[0] for r in result.rows]
                return f"{len(values)} distinct value(s): {values}"
            return f"Error: {result.error}"

        return f"Unknown tool: {tc.function.name}"
