"""SQLite job reservation, cancellation and restart recovery for local workers."""

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from backend.app.storage import Store, now

TERMINAL = {"complete", "failed", "cancelled"}


class Cancelled(Exception):
    pass


class Jobs:
    def __init__(self, store=None):
        self.store = store or Store()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="foresight")
        self.events = {}

    def recover(self):
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT payload FROM jobs WHERE status NOT IN ('complete','failed','cancelled')"
            ).fetchall()
            for row in rows:
                job = json.loads(row["payload"])
                job.update(
                    status="failed",
                    error="Process restarted; retry explicitly. Verified archives and saved forecasts are retained.",
                    finished_at=now(),
                )
                db.execute(
                    "UPDATE jobs SET status=?,payload=? WHERE id=?",
                    ("failed", json.dumps(job), job["job_id"]),
                )

    def get(self, id=None, kind=None):
        with self.store.connection() as db:
            if id:
                row = db.execute(
                    "SELECT payload FROM jobs WHERE id=?", (id,)
                ).fetchone()
            elif kind:
                row = db.execute(
                    "SELECT payload FROM jobs WHERE kind=? ORDER BY created DESC LIMIT 1",
                    (kind,),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT payload FROM jobs ORDER BY created DESC LIMIT 1"
                ).fetchone()
        return json.loads(row["payload"]) if row else None

    def update(self, id, **fields):
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM jobs WHERE id=?", (id,)).fetchone()
            job = json.loads(row["payload"])
            job.update(fields)
            db.execute(
                "UPDATE jobs SET status=?,payload=? WHERE id=?",
                (job["status"], json.dumps(job), id),
            )
        return job

    def check(self, id):
        if self.events.get(id, threading.Event()).is_set():
            raise Cancelled("Cancelled by user")

    def cancel(self, id):
        job = self.get(id)
        if not job:
            raise ValueError("Job not found")
        if job["status"] not in TERMINAL:
            event = self.events.get(id)
            if event is None:
                return self.get(id)
            event.set()
            self.update(id, current_step="Cancellation requested")
        return self.get(id)

    def start(self, kind, fn, symbol="BTCUSDT", config=None):
        id = uuid.uuid4().hex
        record = dict(
            job_id=id,
            kind=kind,
            symbol=symbol,
            status="pending",
            progress_percentage=0,
            current_step="Queued",
            total_files=0,
            completed_files=0,
            error=None,
            started_at=now(),
            finished_at=None,
            config=config or {},
            agents={},
        )
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Import cannot race a training snapshot; mutations are serialized.
            if db.execute(
                "SELECT id FROM jobs WHERE status NOT IN ('complete','failed','cancelled')"
            ).fetchone():
                raise ValueError("Another job is already running")
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?)",
                (id, kind, "pending", record["started_at"], json.dumps(record)),
            )
        self.events[id] = threading.Event()

        def worker():
            try:
                self.check(id)
                self.update(id, status="running")
                result = fn(id)
                self.check(id)
                self.update(
                    id,
                    status="complete",
                    progress_percentage=100,
                    current_step="Complete",
                    result=result,
                    finished_at=now(),
                )
            except Cancelled:
                self.update(
                    id,
                    status="cancelled",
                    current_step="Cancelled; previous results kept",
                    finished_at=now(),
                )
            except Exception as e:
                self.update(
                    id,
                    status="failed",
                    error=str(e),
                    current_step=str(e),
                    finished_at=now(),
                )
            finally:
                self.events.pop(id, None)

        self.pool.submit(worker)
        return record


jobs = Jobs()
