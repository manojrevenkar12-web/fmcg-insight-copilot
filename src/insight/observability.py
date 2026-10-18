"""Technical KPIs for the AI application itself: every interaction is recorded with its outcome,
verification result and latency, so the AI team can show — not claim — how well it works."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from prometheus_client import CollectorRegistry, Counter, Histogram

SCHEMA = """
create table if not exists interactions (
    id text primary key,
    at text not null,
    user_id text not null,
    question text not null,
    intent text,
    status text not null,
    metrics text,
    verification text,
    ungrounded integer not null default 0,
    guard_flagged integer not null default 0,
    latency_ms real,
    mode text
);
create table if not exists feedback (
    interaction_id text not null,
    user_id text not null,
    rating text not null check (rating in ('up', 'down')),
    comment text,
    at text not null,
    primary key (interaction_id, user_id)
);
"""


class Observability:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()
        self.registry = CollectorRegistry()
        self.asks = Counter("insight_questions_total", "Questions by outcome", ["status", "mode"], registry=self.registry)
        self.verification = Counter("insight_verification_total", "Answers by number-verification result", ["result"], registry=self.registry)
        self.guard = Counter("insight_guard_flags_total", "Questions flagged by the injection screen", registry=self.registry)
        self.latency = Histogram("insight_answer_seconds", "Time to answer", buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30), registry=self.registry)
        self.http = Histogram("http_request_seconds", "HTTP latency", ["route", "method", "status"], registry=self.registry)

    def record(self, user_id: str, question: str, result: dict) -> str:
        iid = str(uuid.uuid4())
        v = result["verification"]
        with self._lock:
            self._db.execute(
                "insert into interactions values (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    iid,
                    datetime.now(UTC).isoformat(),
                    user_id,
                    question[:500],
                    result.get("intent"),
                    result["status"],
                    json.dumps([m["name"] for m in result.get("metrics", [])]),
                    v["status"],
                    len(v["ungrounded"]),
                    int(result["guard"]["flagged"]),
                    result.get("latency_ms"),
                    result.get("mode"),
                ),
            )
            self._db.commit()
        self.asks.labels(result["status"], result.get("mode", "")).inc()
        self.verification.labels(v["status"]).inc()
        if result["guard"]["flagged"]:
            self.guard.inc()
        self.latency.observe((result.get("latency_ms") or 0) / 1000)
        return iid

    def owner_of(self, interaction_id: str) -> str | None:
        row = self._db.execute("select user_id from interactions where id = ?", (interaction_id,)).fetchone()
        return row[0] if row else None

    def feedback(self, interaction_id: str, user_id: str, rating: str, comment: str | None) -> None:
        with self._lock:
            self._db.execute(
                "insert into feedback values (?,?,?,?,?) on conflict(interaction_id, user_id) do update set rating=excluded.rating, comment=excluded.comment, at=excluded.at",
                (interaction_id, user_id, rating, comment, datetime.now(UTC).isoformat()),
            )
            self._db.commit()

    def kpis(self) -> dict:
        q = self._db.execute
        total = q("select count(*) from interactions").fetchone()[0]
        by_status = dict(q("select status, count(*) from interactions group by status").fetchall())
        by_verification = dict(q("select verification, count(*) from interactions where status = 'answered' group by verification").fetchall())
        lat = [r[0] for r in q("select latency_ms from interactions where latency_ms is not null order by latency_ms").fetchall()]
        fb = dict(q("select rating, count(*) from feedback group by rating").fetchall())
        answered = by_status.get("answered", 0)
        pct = lambda n, d: round(n / d, 3) if d else None  # noqa: E731
        return {
            "questions": total,
            "answered_rate": pct(answered, total),
            "abstained_rate": pct(by_status.get("abstained", 0), total),
            "restricted_rate": pct(by_status.get("restricted", 0), total),
            "numbers_verified_rate": pct(by_verification.get("verified", 0), answered),
            "answers_corrected_or_replaced": by_verification.get("corrected", 0) + by_verification.get("replaced", 0),
            "guard_flags": q("select count(*) from interactions where guard_flagged = 1").fetchone()[0],
            "latency_ms_p50": lat[len(lat) // 2] if lat else None,
            "latency_ms_p95": lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None,
            "feedback_up": fb.get("up", 0),
            "feedback_down": fb.get("down", 0),
            "helpful_rate": pct(fb.get("up", 0), fb.get("up", 0) + fb.get("down", 0)),
        }
