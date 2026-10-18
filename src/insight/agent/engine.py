"""The insight agent: a LangGraph state machine over the semantic layer.

    guard → plan ─┬─ metric ─────→ execute → context → narrate → verify
                  ├─ definition ─→ define  → context → narrate → verify
                  └─ out of scope → abstain

Every answer carries what a business user and an auditor need to trust it: the KPI
definitions and owners, the SQL that ran, lineage back to the source extracts, the data
as-of date, data-quality status, and the result of the number verification.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ..semantic.catalog import Catalog, trace
from ..semantic.compiler import CompiledQuery, MetricQuery, QueryError, compile_query, validate
from ..semantic.periods import previous
from ..warehouse import Warehouse
from .guard import screen
from .narrate import Facts, Verification, fmt, narrate_live, narrate_template, verify_numbers
from .plan import Plan, plan_live, plan_offline
from .rag import KnowledgeIndex

WHY = re.compile(r"\b(why|cause[sd]?|reason|explain|what happened|driver|drivers|behind)\b", re.I)

ABSTAIN = (
    "I can only answer questions about the governed KPIs (procurement, manufacturing and sales). "
    "Try for example: “Which supplier had the worst OTIF last quarter?”, “OEE by line at PL01 in August 2026” or "
    "“Net revenue by country this year vs last year”."
)


@dataclass
class User:
    id: str
    name: str
    roles: list[str]
    countries: list[str] | None  # None = all countries


class State(TypedDict, total=False):
    question: str
    user: User
    guard: dict
    plan: Plan
    plan_error: str | None
    query: MetricQuery
    compiled: list[CompiledQuery]
    facts: Facts
    context: list[dict]
    draft: str
    answer: str
    verification: Verification
    status: str
    definition: dict
    access_note: str


class InsightEngine:
    def __init__(self, catalog: Catalog, warehouse: Warehouse, knowledge: KnowledgeIndex, lineage: dict[str, dict], llm=None):
        self.catalog = catalog
        self.wh = warehouse
        self.kb = knowledge
        self.lineage = lineage
        self.llm = llm
        self.mode = "live" if llm is not None else "offline"
        self.as_of = warehouse.as_of()
        self.values = warehouse.dimension_values(catalog)
        self.graph = self._build()

    # ---------------------------------------------------------------- nodes

    def _guard(self, s: State) -> State:
        g = screen(s["question"])
        return {"guard": {"flagged": g.flagged, "patterns": g.patterns}}

    def _plan(self, s: State) -> State:
        q = s["question"]
        plan: Plan
        error: str | None = None
        if self.llm is not None:
            try:
                plan = plan_live(q, self.catalog, self.values, self.as_of, self.llm)
                error = self._check(plan)
                if error:  # one repair attempt with the validation error
                    plan = plan_live(q, self.catalog, self.values, self.as_of, self.llm, error=error)
                    error = self._check(plan)
            except Exception as exc:  # LLM down or malformed: fall back to the deterministic planner
                plan, error = plan_offline(q, self.catalog, self.values, self.as_of), f"llm planner unavailable: {type(exc).__name__}"
                error = self._check(plan)
        else:
            plan = plan_offline(q, self.catalog, self.values, self.as_of)
            error = self._check(plan)
        out: State = {"plan": plan, "plan_error": error}
        if plan.intent == "metric" and not error:
            out["query"] = plan.query.to_query(self.as_of)
        return out

    def _check(self, plan: Plan) -> str | None:
        if plan.intent == "metric":
            if plan.query is None:
                return "metric intent without a query"
            try:
                validate(plan.query.to_query(self.as_of), self.catalog, self.values)
            except (QueryError, ValueError) as exc:
                return str(exc)
        if plan.intent == "definition" and plan.definition_metric not in self.catalog.metrics:
            return f"unknown metric {plan.definition_metric}"
        return None

    def _route(self, s: State) -> str:
        if s.get("plan_error"):
            return "abstain"
        return {"metric": "execute", "definition": "define"}.get(s["plan"].intent, "abstain")

    def _abstain(self, s: State) -> State:
        err = s.get("plan_error")
        text = ABSTAIN if not err or s["plan"].intent == "out_of_scope" else f"I couldn't build a valid query: {err}"
        return {"answer": text, "status": "abstained", "verification": Verification("verified", 0, [])}

    def _execute(self, s: State) -> State:
        q = s["query"]
        countries = s["user"].countries
        if countries is not None:
            asked = {v for f in q.filters if f.dimension == "country" for v in f.values} | {
                v[:2] for f in q.filters if f.dimension == "plant" for v in f.values
            }
            if asked and not asked & set(countries):
                return {
                    "access_note": f"You don't have access to data for {', '.join(sorted(asked))}. Your access covers {', '.join(countries) or 'no countries'}.",
                    "compiled": [],
                }
        overall_q = q.model_copy(update={"dimensions": [], "order": "desc"})
        compiled = [compile_query(overall_q, self.catalog, countries, known_values=self.values)]
        overall = (self.wh.run(compiled[0]) or [{}])[0]
        prev_overall = prev_rows = None
        prev_period = previous(q.period) if q.compare_previous else None
        if prev_period:
            c = compile_query(overall_q, self.catalog, countries, period=prev_period, known_values=self.values)
            compiled.append(c)
            prev_overall = (self.wh.run(c) or [{}])[0]
        rows: list[dict] = []
        if q.dimensions:
            c = compile_query(q, self.catalog, countries, known_values=self.values)
            compiled.append(c)
            rows = self.wh.run(c)
            if prev_period:
                c = compile_query(q.model_copy(update={"limit": 50}), self.catalog, countries, period=prev_period, known_values=self.values)
                compiled.append(c)
                prev_rows = self.wh.run(c)
        metrics = [self.catalog.metrics[m] for m in q.metrics]
        facts = Facts(
            period_label=q.period.label,
            previous_label=prev_period.label if prev_period else None,
            metrics=metrics,
            overall={m.name: overall.get(m.name) for m in metrics},
            previous={m.name: prev_overall.get(m.name) for m in metrics} if prev_overall is not None else None,
            rows=rows,
            previous_rows=prev_rows,
            dimensions=q.dimensions,
            dimension_labels={d: self.catalog.dimensions[d].label for d in q.dimensions},
        )
        return {"compiled": compiled, "facts": facts}

    def _define(self, s: State) -> State:
        m = self.catalog.metrics[s["plan"].definition_metric]
        return {"definition": self.metric_card(m.name)}

    def _context(self, s: State) -> State:
        q = s["question"]
        wants = s["plan"].intent == "definition" or bool(WHY.search(q)) or bool(s.get("query") and s["query"].compare_previous)
        if not wants:
            return {"context": []}
        terms = q
        if s.get("query"):
            terms += (
                " " + " ".join(f.values[0] for f in s["query"].filters) + " " + " ".join(self.catalog.metrics[m].label for m in s["query"].metrics)
            )
        hits = self.kb.search(terms, k=3)
        if s["plan"].intent == "metric":
            # Only operations notes that mention something this answer is about (a plant, supplier,
            # material, country...) — a generic glossary hit would explain nothing.
            entities = self._entities(s)
            hits = [(p, sc) for p, sc in hits if p.doc == "operations-notes" and any(e in p.text.lower() for e in entities)]
        ctx = [
            {"id": f"N{i + 1}", "source": p.id, "title": p.title, "section": p.section, "text": p.text, "summary": _first_sentence(p.text)}
            for i, (p, _) in enumerate(hits)
        ]
        if s.get("facts"):
            s["facts"].context = ctx[:1] if s["plan"].intent == "metric" else ctx
        return {"context": ctx}

    def _entities(self, s: State) -> set[str]:
        names = {"DE": "germany", "NL": "netherlands", "PL": "pl01", "FR": "france", "DE01": "rhine valley", "NL01": "polderland", "PL01": "vistula"}
        out: set[str] = set()
        q = s.get("query")
        values = [v for f in (q.filters if q else []) for v in f.values]
        facts = s.get("facts")
        if facts and facts.dimensions and facts.rows:
            d = facts.dimensions[0]
            values += [str(facts.rows[0][d]), str(facts.rows[-1][d])]
            values += list(facts.changes(facts.metrics[0]))[:1]
        for v in values:
            out.add(str(v).lower())
            if str(v) in names:
                out.add(names[str(v)])
        return {e for e in out if len(e) > 2}

    def _narrate(self, s: State) -> State:
        if s.get("access_note"):
            return {"draft": s["access_note"]}
        if s["plan"].intent == "definition":
            card = s["definition"]
            text = f"{card['label']}: {card['description']} It is calculated as {card['formula_text']} and owned by {card['owner']}."
            if s.get("context"):
                c = s["context"][0]
                text += f" From the glossary: {c['summary'].rstrip('.')} [{c['id']}]."
            return {"draft": text}
        facts = s["facts"]
        if self.llm is not None:
            try:
                return {"draft": narrate_live(facts, s["question"], self.llm)}
            except Exception:
                pass
        return {"draft": narrate_template(facts)}

    def _verify(self, s: State) -> State:
        draft = s["draft"]
        if s.get("access_note"):
            return {"answer": draft, "status": "restricted", "verification": Verification("verified", 0, [])}
        if s["plan"].intent == "definition":
            return {"answer": draft, "status": "answered", "verification": Verification("verified", 0, [])}
        facts = s["facts"]
        text, v = verify_numbers(draft, facts, s["question"])
        if v.ungrounded and (not text.strip() or self.llm is None):
            text, v = narrate_template(facts), Verification("replaced", v.checked, v.ungrounded)
        elif v.ungrounded and len(text) < 40:
            text, v = narrate_template(facts), Verification("replaced", v.checked, v.ungrounded)
        if s["guard"]["flagged"]:
            text = "Note: parts of the question asked me to change my rules or widen data access; that was ignored. " + text
        return {"answer": text, "status": "answered", "verification": v}

    def _build(self):
        g = StateGraph(State)
        g.add_node("guard", self._guard)
        g.add_node("plan", self._plan)
        g.add_node("abstain", self._abstain)
        g.add_node("execute", self._execute)
        g.add_node("define", self._define)
        g.add_node("context", self._context)
        g.add_node("narrate", self._narrate)
        g.add_node("verify", self._verify)
        g.add_edge(START, "guard")
        g.add_edge("guard", "plan")
        g.add_conditional_edges("plan", self._route, {"execute": "execute", "define": "define", "abstain": "abstain"})
        g.add_edge("execute", "context")
        g.add_edge("define", "context")
        g.add_edge("context", "narrate")
        g.add_edge("narrate", "verify")
        g.add_edge("verify", END)
        g.add_edge("abstain", END)
        return g.compile()

    # ---------------------------------------------------------------- public

    def metric_card(self, name: str) -> dict:
        m = self.catalog.metrics[name]
        fact = self.catalog.facts[m.fact]
        chain = trace(m.fact, self.lineage)
        return {
            "name": m.name,
            "label": m.label,
            "description": m.description,
            "owner": m.owner,
            "unit": m.unit,
            "direction": m.direction,
            "formula": m.expression,
            "formula_text": _readable(m.expression),
            "source_table": f"marts.{m.fact}",
            "time_column": fact.time_column,
            "dimensions": m.dimensions,
            "lineage": chain,
            "landing_files": sorted({f for step in chain for f in step["landing_files"]}),
        }

    def ask(self, question: str, user: User) -> dict[str, Any]:
        t0 = time.perf_counter()
        s: State = self.graph.invoke({"question": question, "user": user})
        plan = s["plan"]
        q = s.get("query")
        facts = s.get("facts")
        metric_names = q.metrics if q else ([plan.definition_metric] if plan.intent == "definition" and plan.definition_metric else [])
        sources = {self.catalog.metrics[m].fact for m in metric_names}
        dq = [r for r in self.wh.data_quality() if any(_source_feeds(r["source"], f) for f in sources)]
        return {
            "answer": s["answer"],
            "status": s["status"],
            "intent": plan.intent,
            "mode": self.mode,
            "query": q.model_dump(mode="json") if q else None,
            "period": q.period.label if q else None,
            "comparison_period": facts.previous_label if facts else None,
            "overall": {m.name: {"value": facts.overall.get(m.name), "formatted": fmt(facts.overall.get(m.name), m.unit)} for m in facts.metrics}
            if facts
            else {},
            "rows": facts.rows if facts else [],
            "sql": [c.sql for c in s.get("compiled", [])],
            "metrics": [self.metric_card(m) for m in metric_names],
            "context": [{k: c[k] for k in ("id", "source", "title", "section", "text")} for c in s.get("context", [])],
            "verification": {
                "status": s["verification"].status,
                "numbers_checked": s["verification"].checked,
                "ungrounded": s["verification"].ungrounded,
            },
            "guard": s["guard"],
            "access": {"countries": user.countries or "all"},
            "data_as_of": self.as_of.isoformat(),
            "data_quality": dq,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=\.)\s+", text.strip(), maxsplit=1)[0]


def _readable(expr: str) -> str:
    e = re.sub(r"\bfct\.", "", expr)
    e = re.sub(r"nullif\(([^,]+), 0\)", r"\1", e)
    return e.replace("avg(case when is_otif then 1.0 else 0.0 end)", "share of deliveries that were on time and in full").replace("_", " ")


def _source_feeds(source: str, fact: str) -> bool:
    return {
        "fct_purchase_deliveries": "erp.purchase_orders",
        "fct_production": "mes.production_runs",
        "fct_downtime": "mes.downtime_events",
        "fct_sales": "oms.sales_order_lines",
    }.get(fact) == source
