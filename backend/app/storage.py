"""Durable local state. Predictions and model versions are never edited; a finished
training run replaces the previous run as a whole (see Store.remove)."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from backend.app.config import DATA_DIR


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w") as f:
            json.dump(value, f, allow_nan=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


# Rows are never deleted one by one; only Store.remove lifts these for a whole run.
DELETE_GUARDS = """
CREATE TRIGGER IF NOT EXISTS immutable_forecast_delete BEFORE DELETE ON forecasts BEGIN SELECT RAISE(ABORT,'Immutable forecast'); END;
CREATE TRIGGER IF NOT EXISTS immutable_model_delete BEFORE DELETE ON models BEGIN SELECT RAISE(ABORT,'Immutable model'); END;
"""


class Store:
    def __init__(self, path=None):
        self.path = Path(path or DATA_DIR / "foresight.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(
                """
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT, status TEXT, created TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS models (id TEXT PRIMARY KEY, created TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS forecasts (id TEXT PRIMARY KEY, run_id TEXT, origin TEXT, model_id TEXT,
                role TEXT, created TEXT, payload TEXT, UNIQUE(run_id,origin,model_id,role));
            CREATE TABLE IF NOT EXISTS evaluations (forecast_id TEXT PRIMARY KEY, clock TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, created TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TRIGGER IF NOT EXISTS immutable_forecast_update BEFORE UPDATE ON forecasts BEGIN SELECT RAISE(ABORT,'Immutable forecast'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_model_update BEFORE UPDATE ON models BEGIN SELECT RAISE(ABORT,'Immutable model'); END;
            CREATE INDEX IF NOT EXISTS forecasts_run ON forecasts(run_id,origin);
            """
                + DELETE_GUARDS
            )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def put(self, table, record, immutable=False):
        if table not in {"models", "runs", "decisions"}:
            raise ValueError("Unsupported table")
        with self.connection() as db:
            sql = "INSERT" if immutable else "INSERT OR REPLACE"
            db.execute(
                f"{sql} INTO {table}(id,created,payload) VALUES(?,?,?)",
                (
                    record["id"],
                    record.get("created_at", now()),
                    json.dumps(record, allow_nan=False),
                ),
            )

    def get(self, table, id):
        if table not in {"models", "runs", "forecasts", "decisions"}:
            raise ValueError("Unsupported table")
        with self.connection() as db:
            row = db.execute(
                f"SELECT payload FROM {table} WHERE id=?", (id,)
            ).fetchone()
        if not row:
            raise ValueError(f"{table[:-1].title()} not found")
        return json.loads(row["payload"])

    def list(self, table, run_id=None):
        if table not in {"models", "runs", "forecasts", "decisions"}:
            raise ValueError("Unsupported table")
        with self.connection() as db:
            query = f"SELECT payload FROM {table}"
            args = ()
            if run_id is not None and table == "forecasts":
                query += ' WHERE run_id=? AND role="coordinated"'
                args = (run_id,)
            query += " ORDER BY created DESC, rowid DESC"
            rows = db.execute(query, args).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def setting(self, key, value=None):
        with self.connection() as db:
            if value is not None:
                db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, value))
            row = db.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def publish(self, specialist, coordinated):
        # One transaction: never expose only one side of a published pair.
        with self.connection() as db:
            for record in (specialist, coordinated):
                db.execute(
                    "INSERT OR IGNORE INTO forecasts VALUES(?,?,?,?,?,?,?)",
                    (
                        record["id"],
                        record["run_id"],
                        record["origin"],
                        record["model_version"],
                        record["role"],
                        record["generated_at"],
                        json.dumps(record, allow_nan=False),
                    ),
                )
            row = db.execute(
                'SELECT payload FROM forecasts WHERE run_id=? AND origin=? AND model_id=? AND role="coordinated"',
                (
                    coordinated["run_id"],
                    coordinated["origin"],
                    coordinated["model_version"],
                ),
            ).fetchone()
        return json.loads(row["payload"])

    def evaluation(self, id, record=None):
        with self.connection() as db:
            if record is not None:
                # A replay rewind must never erase mature outcomes.
                db.execute(
                    "INSERT INTO evaluations VALUES(?,?,?) ON CONFLICT(forecast_id) DO UPDATE SET clock=excluded.clock,payload=excluded.payload WHERE excluded.clock >= evaluations.clock",
                    (id, record["clock"], json.dumps(record, allow_nan=False)),
                )
            row = db.execute(
                "SELECT payload FROM evaluations WHERE forecast_id=?", (id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def remove(self, runs=(), models=(), decisions=(), jobs_kind=None, keep_job=None, symbol=None):
        """Delete whole runs and models with their forecasts and scores, in one transaction.

        Used only when a finished training run replaces the previous one. Forecasts of
        a removed run or made by a removed model go too; nothing is edited in place.
        """
        runs, models, decisions = list(runs), list(models), list(decisions)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DROP TRIGGER IF EXISTS immutable_forecast_delete")
            db.execute("DROP TRIGGER IF EXISTS immutable_model_delete")
            db.executemany("DELETE FROM forecasts WHERE run_id=?", [(r,) for r in runs])
            db.executemany("DELETE FROM forecasts WHERE model_id=?", [(m,) for m in models])
            db.execute(
                "DELETE FROM evaluations WHERE forecast_id NOT IN (SELECT id FROM forecasts)"
            )
            db.executemany("DELETE FROM models WHERE id=?", [(m,) for m in models])
            db.executemany("DELETE FROM runs WHERE id=?", [(r,) for r in runs])
            db.executemany("DELETE FROM decisions WHERE id=?", [(d,) for d in decisions])
            if jobs_kind:
                db.execute(
                    "DELETE FROM jobs WHERE kind=? AND id IS NOT ? AND status IN ('complete','failed','cancelled') "
                    "AND COALESCE(json_extract(payload,'$.symbol'),?)=?",
                    (jobs_kind, keep_job, symbol, symbol),
                )
            for statement in DELETE_GUARDS.strip().splitlines():
                db.execute(statement)

    def compact(self):
        # Reclaim the space of removed runs; must run outside a transaction.
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("VACUUM")
        finally:
            db.close()
