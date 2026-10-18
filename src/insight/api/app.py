"""HTTP API: the copilot for business users, a governed query endpoint for BI tools and
power users, the KPI catalog with lineage, data-quality status and the AI's own KPIs."""

import csv
import hashlib
import io
import logging
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Annotated, Literal

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import generate_latest
from pydantic import BaseModel, Field

from ..agent.engine import InsightEngine, User
from ..agent.plan import PeriodSpec
from ..config import ROOT, Settings
from ..observability import Observability
from ..semantic.compiler import Filter, MetricQuery, QueryError, compile_query

log = logging.getLogger("insight.api")


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class QueryBody(BaseModel):
    metrics: list[str] = Field(min_length=1, max_length=4)
    dimensions: list[str] = Field(default_factory=list, max_length=2)
    filters: list[Filter] = Field(default_factory=list, max_length=5)
    period: PeriodSpec = Field(default_factory=PeriodSpec)
    order: Literal["desc", "asc"] = "desc"
    limit: int = Field(default=50, ge=1, le=50)
    format: Literal["json", "csv"] = "json"


class FeedbackBody(BaseModel):
    interaction_id: str = Field(min_length=36, max_length=36)
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)


def load_users(path: Path) -> dict[str, User]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {u["key_sha256"]: User(id=u["id"], name=u["name"], roles=u["roles"], countries=u.get("countries")) for u in raw["users"]}


class RateLimiter:
    """Sliding window per user. In a multi-instance deployment this moves to the API gateway."""

    def __init__(self, limit: int, window_s: float = 60):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Too many questions — wait a minute and try again.")
        q.append(now)


def create_app(settings: Settings, engine: InsightEngine, obs: Observability, ask_limit_per_min: int = 30) -> FastAPI:
    users = load_users(settings.users_path)
    limiter = RateLimiter(ask_limit_per_min)
    app = FastAPI(title="FMCG Insight Copilot", version="1.0.0", docs_url="/docs", redoc_url=None)

    def current_user(x_api_key: Annotated[str | None, Header()] = None) -> User:
        if not x_api_key:
            raise HTTPException(401, "Missing X-API-Key header")
        user = users.get(hashlib.sha256(x_api_key.encode()).hexdigest())
        if user is None:
            raise HTTPException(401, "Invalid API key")
        return user

    def admin(user: Annotated[User, Depends(current_user)]) -> User:
        if "admin" not in user.roles:
            raise HTTPException(403, "Requires the admin role")
        return user

    @app.middleware("http")
    async def headers_and_metrics(request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        t0 = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        obs.http.labels(getattr(route, "path", "unmatched"), request.method, str(response.status_code)).observe(time.perf_counter() - t0)
        response.headers["x-request-id"] = rid
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["x-frame-options"] = "DENY"
        if not request.url.path.startswith("/docs"):
            response.headers["content-security-policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
            )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 422: "bad_request", 429: "rate_limited"}.get(
            exc.status_code, "error"
        )
        return JSONResponse({"error": {"code": code, "message": exc.detail}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse({"error": {"code": "bad_request", "message": "Invalid request", "details": details}}, status_code=400)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse({"error": {"code": "internal", "message": "Internal error"}}, status_code=500)

    # ------------------------------------------------------------ operations

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def readyz():
        try:
            engine.wh.scalar("select count(*) from marts.dim_date")
            return {"status": "ready", "data_as_of": engine.as_of.isoformat(), "mode": engine.mode}
        except Exception:
            return JSONResponse({"status": "not_ready"}, status_code=503)

    @app.get("/ops/prometheus", include_in_schema=False)
    def prometheus():
        return Response(generate_latest(obs.registry), media_type="text/plain; version=0.0.4")

    # ------------------------------------------------------------ API

    @app.post("/v1/ask", tags=["copilot"])
    def ask(body: AskBody, user: Annotated[User, Depends(current_user)]):
        limiter.check(user.id)
        result = engine.ask(body.question, user)
        result["interaction_id"] = obs.record(user.id, body.question, result)
        return result

    @app.post("/v1/query", tags=["governed query"])
    def query(body: QueryBody, user: Annotated[User, Depends(current_user)]):
        """Governed KPI query for BI tools, notebooks and power users: same definitions and access rules as the copilot."""
        try:
            q = MetricQuery(
                metrics=body.metrics,
                dimensions=body.dimensions,
                filters=body.filters,
                period=body.period.resolve(engine.as_of),
                order=body.order,
                limit=body.limit,
            )
            compiled = compile_query(q, engine.catalog, user.countries, known_values=engine.values)
        except (QueryError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        rows = engine.wh.run(compiled)
        if body.format == "csv":
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=compiled.columns)
            w.writeheader()
            w.writerows(rows)
            return PlainTextResponse(buf.getvalue(), media_type="text/csv")
        return {"period": q.period.label, "data_as_of": engine.as_of.isoformat(), "columns": compiled.columns, "rows": rows, "sql": compiled.sql}

    @app.get("/v1/metrics", tags=["catalog"])
    def metrics(user: Annotated[User, Depends(current_user)]):
        return {
            "items": [
                {"name": m.name, "label": m.label, "unit": m.unit, "owner": m.owner, "description": m.description, "dimensions": m.dimensions}
                for m in engine.catalog.metrics.values()
            ]
        }

    @app.get("/v1/metrics/{name}", tags=["catalog"])
    def metric(name: str, user: Annotated[User, Depends(current_user)]):
        if name not in engine.catalog.metrics:
            raise HTTPException(404, f"No metric called {name}")
        return engine.metric_card(name)

    @app.get("/v1/data-quality", tags=["catalog"])
    def data_quality(user: Annotated[User, Depends(current_user)]):
        return {"data_as_of": engine.as_of.isoformat(), "sources": engine.wh.data_quality()}

    @app.post("/v1/feedback", status_code=204, tags=["copilot"])
    def feedback(body: FeedbackBody, user: Annotated[User, Depends(current_user)]):
        if obs.owner_of(body.interaction_id) != user.id:
            raise HTTPException(404, "No such answer")
        obs.feedback(body.interaction_id, user.id, body.rating, body.comment)
        return Response(status_code=204)

    @app.get("/v1/me", tags=["copilot"])
    def me(user: Annotated[User, Depends(current_user)]):
        return {"id": user.id, "name": user.name, "roles": user.roles, "countries": user.countries or "all"}

    @app.get("/v1/ai-kpis", tags=["AI performance"])
    def ai_kpis(user: Annotated[User, Depends(admin)]):
        return obs.kpis()

    web = ROOT / "web"
    if web.exists():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app
