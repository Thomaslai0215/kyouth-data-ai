"""MCP server for SQLite access via SQL scripts in queries/."""

import json
import os
import sqlite3
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("SQLite-Service")
QUERIES_DIR = Path(__file__).resolve().parent / "queries"


def _db_path() -> str:
    return os.environ.get("DB_PATH", "data/jobs_d1.db")


def _load_sql(script_name: str) -> str:
    path = QUERIES_DIR / script_name
    if not path.exists():
        raise FileNotFoundError(f"SQL script not found: {script_name}")
    return path.read_text(encoding="utf-8")


@mcp.tool
def run_sql_script(script_name: str, params_json: str = "[]") -> str:
    """Execute a SQL script from queries/ with optional JSON parameter list."""
    try:
        sql = _load_sql(script_name)
        params = json.loads(params_json)
        with sqlite3.connect(_db_path()) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if sql.strip().upper().startswith("SELECT"):
                cursor.execute(sql, params)
                rows = [dict(row) for row in cursor.fetchall()]
                return json.dumps(rows)
            cursor.execute(sql, params)
            conn.commit()
            return json.dumps({"rows_affected": cursor.rowcount})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    mcp.run()
