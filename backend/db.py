import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from .config import DB_PATH

RUN_STATUSES = ("running", "paused", "success", "failed", "blocked", "cancelled")
STEP_STATUSES = ("pending", "running", "paused", "passed", "failed", "blocked", "cancelled")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
        conn.commit()
    finally:
        conn.close()


def _table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not row:
        return ""
    return str(row[0] or "")


def _foreign_parents(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    parents: set[str] = set()
    for r in rows:
        try:
            parents.add(str(r[2]))
        except Exception:
            pass
    return parents


def _migrate_runs_if_needed(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "runs")
    if not sql:
        return
    if "paused" in sql and "cancelled" in sql:
        return

    conn.execute("PRAGMA foreign_keys=OFF;")
    conn.execute("ALTER TABLE runs RENAME TO runs_old;")
    conn.execute(
        """
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal TEXT NOT NULL,
            global_context TEXT NOT NULL DEFAULT '',
            last_done_thing TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK(status IN ('running','paused','success','failed','blocked','cancelled')),
            profile_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(profile_id) REFERENCES prompt_profiles(id)
        );
        """
    )
    conn.execute(
        """
        INSERT INTO runs(id, goal, global_context, last_done_thing, status, profile_id, created_at, updated_at)
        SELECT id, goal, COALESCE(global_context,''), COALESCE(last_done_thing,''), status, profile_id, created_at, updated_at
        FROM runs_old;
        """
    )
    conn.execute("DROP TABLE runs_old;")
    conn.execute("PRAGMA foreign_keys=ON;")


def _migrate_run_steps_if_needed(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "run_steps")
    if not sql:
        return

    parents = _foreign_parents(conn, "run_steps")
    needs_status = ("paused" not in sql) or ("cancelled" not in sql)
    needs_fk = (not parents) or ("runs" not in parents) or ("runs_old" in parents)

    if not needs_status and not needs_fk:
        return

    conn.execute("PRAGMA foreign_keys=OFF;")
    conn.execute("ALTER TABLE run_steps RENAME TO run_steps_old;")
    conn.execute(
        """
        CREATE TABLE run_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            step_name TEXT NOT NULL CHECK(step_name IN ('planner','worker','reviewer')),
            attempt INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL CHECK(status IN ('pending','running','paused','passed','failed','blocked','cancelled')),
            input_payload TEXT NOT NULL,
            output_payload TEXT,
            error TEXT,
            agent_context_id TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            FOREIGN KEY(run_id) REFERENCES runs(id)
        );
        """
    )
    conn.execute(
        """
        INSERT INTO run_steps(
            id, run_id, step_name, attempt, status, input_payload, output_payload, error, agent_context_id, started_at, ended_at
        )
        SELECT
            id, run_id, step_name, attempt, status, input_payload, output_payload, error, agent_context_id, started_at, ended_at
        FROM run_steps_old;
        """
    )
    conn.execute("DROP TABLE run_steps_old;")
    conn.execute("PRAGMA foreign_keys=ON;")


def _migrate_run_events_if_needed(conn: sqlite3.Connection) -> None:
    sql = _table_sql(conn, "run_events")
    if not sql:
        return

    parents = _foreign_parents(conn, "run_events")
    needs_fk = (not parents) or ("runs" not in parents) or ("runs_old" in parents)
    if not needs_fk:
        return

    conn.execute("PRAGMA foreign_keys=OFF;")
    conn.execute("ALTER TABLE run_events RENAME TO run_events_old;")
    conn.execute(
        """
        CREATE TABLE run_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            level TEXT NOT NULL CHECK(level IN ('info','warn','error')),
            message TEXT NOT NULL,
            meta TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES runs(id)
        );
        """
    )
    conn.execute(
        """
        INSERT INTO run_events(id, run_id, level, message, meta, created_at)
        SELECT id, run_id, level, message, meta, created_at
        FROM run_events_old;
        """
    )
    conn.execute("DROP TABLE run_events_old;")
    conn.execute("PRAGMA foreign_keys=ON;")


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS prompt_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                planner_prompt TEXT NOT NULL,
                worker_inject_prompt TEXT NOT NULL,
                reviewer_inject_prompt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT NOT NULL,
                global_context TEXT NOT NULL DEFAULT '',
                last_done_thing TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('running','paused','success','failed','blocked','cancelled')),
                profile_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES prompt_profiles(id)
            );

            CREATE TABLE IF NOT EXISTS run_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                step_name TEXT NOT NULL CHECK(step_name IN ('planner','worker','reviewer')),
                attempt INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL CHECK(status IN ('pending','running','paused','passed','failed','blocked','cancelled')),
                input_payload TEXT NOT NULL,
                output_payload TEXT,
                error TEXT,
                agent_context_id TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                level TEXT NOT NULL CHECK(level IN ('info','warn','error')),
                message TEXT NOT NULL,
                meta TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );
            """
        )

        _migrate_runs_if_needed(conn)
        _migrate_run_steps_if_needed(conn)
        _migrate_run_events_if_needed(conn)

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_profile ON runs(profile_id);
            CREATE INDEX IF NOT EXISTS idx_steps_run_name_attempt ON run_steps(run_id, step_name, attempt);
            CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id, created_at);
            """
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(r) for r in rows if r is not None]  # type: ignore[arg-type]


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(query, params).fetchone()
        return row_to_dict(row)


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return rows_to_dicts(rows)


def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    with get_conn() as conn:
        conn.execute(query, params)


def insert_and_get_id(query: str, params: tuple[Any, ...] = ()) -> int:
    with get_conn() as conn:
        cur = conn.execute(query, params)
        return int(cur.lastrowid)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
