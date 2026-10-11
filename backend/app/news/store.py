"""Additive immutable news records and transactional inference reservations."""
import hashlib
import json
import math
import uuid
from backend.app.storage import now, atomic_json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


class NewsStore:
    def __init__(self, store, root):
        self.store, self.root = store, root
        with store.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS news_records (
                    kind TEXT, id TEXT, created TEXT, payload TEXT, PRIMARY KEY(kind,id));
                CREATE TRIGGER IF NOT EXISTS news_immutable_update BEFORE UPDATE ON news_records
                    BEGIN SELECT RAISE(ABORT,'Immutable news record'); END;
                CREATE TRIGGER IF NOT EXISTS news_immutable_delete BEFORE DELETE ON news_records
                    BEGIN SELECT RAISE(ABORT,'Immutable news record'); END;
                CREATE TABLE IF NOT EXISTS news_budgets (id TEXT PRIMARY KEY, limit_usd REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS news_reservations (
                    id TEXT PRIMARY KEY, budget_id TEXT, reserved_usd REAL, actual_usd REAL,
                    status TEXT, created TEXT);
            """)
            columns = {r["name"] for r in db.execute("PRAGMA table_info(news_reservations)")}
            if "provider" not in columns:
                db.execute("ALTER TABLE news_reservations ADD COLUMN provider TEXT")

    def put(self, kind, value):
        value = dict(value)
        value.setdefault("id", digest(value))
        value.setdefault("created_at", now())
        payload = json.dumps(value, allow_nan=False)
        folder = {"article": "bundles/news", "packet": "evidence", "features": "features/news"}.get(kind, "news/" + kind)
        artifact = self.root / folder / value["id"] / "record.json"
        with self.store.connection() as db:
            existing = db.execute("SELECT payload FROM news_records WHERE kind=? AND id=?", (kind, value["id"])).fetchone()
            if existing:
                old = json.loads(existing["payload"])
                # Deterministic identities may be retried at another wall-clock time.
                if {k: v for k, v in old.items() if k != "created_at"} != {k: v for k, v in value.items() if k != "created_at"}:
                    raise ValueError("Immutable news identity conflict")
                if not artifact.exists():
                    atomic_json(artifact, old)
                elif json.loads(artifact.read_text()) != old:
                    raise ValueError("News artifact integrity mismatch")
                return old
            # Publish artifacts before the durable row becomes visible. A failed
            # database commit can leave an orphan file, never a missing live one.
            atomic_json(artifact, value)
            db.execute("INSERT INTO news_records VALUES(?,?,?,?)", (kind, value["id"], value["created_at"], payload))
        return value

    def get(self, kind, id):
        with self.store.connection() as db:
            row = db.execute("SELECT payload FROM news_records WHERE kind=? AND id=?", (kind, id)).fetchone()
        if not row:
            raise ValueError(f"News {kind} not found")
        return json.loads(row["payload"])

    def list(self, kind):
        with self.store.connection() as db:
            rows = db.execute("SELECT payload FROM news_records WHERE kind=? ORDER BY created DESC,rowid DESC", (kind,)).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def budget(self, id, limit=None):
        with self.store.connection() as db:
            if limit is not None:
                if not math.isfinite(limit) or not 0 < limit <= 100:
                    raise ValueError("Budget must be finite, positive, and at most $100 per experiment")
                db.execute("INSERT OR IGNORE INTO news_budgets VALUES(?,?)", (id, limit))
            row = db.execute("SELECT limit_usd FROM news_budgets WHERE id=?", (id,)).fetchone()
            if not row:
                raise ValueError("Budget not found")
            used = db.execute("SELECT COALESCE(SUM(COALESCE(actual_usd,reserved_usd)),0) FROM news_reservations WHERE budget_id=?", (id,)).fetchone()[0]
        if limit is not None and row[0] != limit:
            raise ValueError("An existing experiment budget cannot be changed")
        return {"id": id, "limit_usd": row[0], "charged_or_reserved_usd": used, "remaining_usd": max(0, row[0] - used)}

    def provider_budget(self, provider, limit):
        with self.store.connection() as db:
            used = db.execute("SELECT COALESCE(SUM(COALESCE(actual_usd,reserved_usd)),0) FROM news_reservations WHERE provider=?", (provider,)).fetchone()[0]
        return {"limit_usd": limit, "charged_or_reserved_usd": used, "remaining_usd": max(0, limit - used), "scope": "All provider experiments in this database; not reset on restart"}

    def reserve(self, budget_id, amount, provider=None, provider_limit=None):
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Invalid reservation")
        id = uuid.uuid4().hex
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT limit_usd FROM news_budgets WHERE id=?", (budget_id,)).fetchone()
            used = db.execute("SELECT COALESCE(SUM(COALESCE(actual_usd,reserved_usd)),0) FROM news_reservations WHERE budget_id=?", (budget_id,)).fetchone()[0]
            if not row or used + amount > row[0]:
                raise ValueError("Budget exhausted; no provider request sent")
            if provider is not None:
                if provider_limit is None or not math.isfinite(provider_limit) or provider_limit <= 0:
                    raise ValueError("Provider spending disabled")
                total = db.execute("SELECT COALESCE(SUM(COALESCE(actual_usd,reserved_usd)),0) FROM news_reservations WHERE provider=?", (provider,)).fetchone()[0]
                if total + amount > provider_limit:
                    raise ValueError("Cumulative provider cap exhausted; no request sent")
            db.execute("INSERT INTO news_reservations (id,budget_id,reserved_usd,actual_usd,status,created,provider) VALUES(?,?,?,?,?,?,?)", (id, budget_id, amount, None, "reserved", now(), provider))
        return id

    def reconcile(self, id, actual=None):
        # Ambiguous network failures retain their reservation, including after restart.
        with self.store.connection() as db:
            db.execute("UPDATE news_reservations SET actual_usd=?,status=? WHERE id=?", (actual, "recorded" if actual is not None else "uncertain", id))
