"""Turn query results into a short narrative, and verify every number in it.

The facts handed to the narrator are computed in code (values, deltas, rankings), formatted
once, and are the only numbers allowed in the answer. The verifier then checks each number
in the text — from the template or from an LLM — against those facts. This is the guard
against "chain-reaction errors": a wrong number in an insight is caught before a user acts on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..semantic.catalog import Metric

# ------------------------------------------------------------------ formatting


def fmt(value: float | None, unit: str) -> str:
    if value is None:
        return "n/a"
    match unit:
        case "percent":
            return f"{value * 100:.1f}%"
        case "eur":
            return f"€{value:,.0f}"
        case "eur_per_kg":
            return f"€{value:.2f}/kg"
        case "tonnes":
            return f"{value:,.1f} t"
        case "hours":
            return f"{value:,.1f} h"
    return f"{value:,.2f}"


def fmt_change(cur: float | None, prev: float | None, unit: str) -> str | None:
    if cur is None or prev is None:
        return None
    if unit == "percent":
        return f"{(cur - prev) * 100:+.1f} pp"
    if prev == 0 or abs((cur - prev) / prev) > 10:
        return None  # a percentage on a near-zero base misleads more than it informs
    return f"{(cur - prev) / abs(prev) * 100:+.1f}%"


@dataclass
class Facts:
    """Everything the narrator may say, already computed and formatted."""

    period_label: str
    previous_label: str | None
    metrics: list[Metric]
    overall: dict[str, float | None]
    previous: dict[str, float | None] | None
    rows: list[dict]
    dimensions: list[str]
    dimension_labels: dict[str, str]
    previous_rows: list[dict] | None = None
    context: list[dict] = field(default_factory=list)

    def numbers(self) -> list[float]:
        """Every number a correct answer could legitimately contain (raw and derived)."""
        out: list[float] = []
        for m in self.metrics:
            cur = self.overall.get(m.name)
            prev = (self.previous or {}).get(m.name)
            for v in (cur, prev):
                if v is not None:
                    out.append(v)
            if cur is not None and prev is not None:
                out += [cur - prev, abs(cur - prev)]
                if prev:
                    out += [(cur - prev) / abs(prev), abs(cur - prev) / abs(prev)]
            for r in self.rows + (self.previous_rows or []):
                if r.get(m.name) is not None:
                    out.append(r[m.name])
            for _key, (c, p) in self.changes(m).items():
                out += [c - p, abs(c - p)] + ([(c - p) / abs(p), abs(c - p) / abs(p)] if p else [])
        out += [len(self.rows)]
        return out

    def changes(self, m: Metric) -> dict[str, tuple[float, float]]:
        if not self.previous_rows or not self.dimensions:
            return {}
        d = self.dimensions[0]
        prev = {r[d]: r[m.name] for r in self.previous_rows if r.get(m.name) is not None}
        return {r[d]: (r[m.name], prev[r[d]]) for r in self.rows if r.get(m.name) is not None and r[d] in prev}

    def as_prompt(self) -> dict:
        m0 = self.metrics[0]
        data: dict = {"period": self.period_label, "comparison_period": self.previous_label, "metrics": []}
        for m in self.metrics:
            entry = {"metric": m.label, "unit": m.unit, "good_direction": m.direction, "overall": fmt(self.overall.get(m.name), m.unit)}
            if self.previous:
                entry["overall_previous"] = fmt(self.previous.get(m.name), m.unit)
                entry["change"] = fmt_change(self.overall.get(m.name), self.previous.get(m.name), m.unit)
            data["metrics"].append(entry)
        if self.dimensions:
            data["breakdown_by"] = [self.dimension_labels[d] for d in self.dimensions]
            data["rows"] = [
                {**{self.dimension_labels[d]: r[d] for d in self.dimensions}, **{m.label: fmt(r.get(m.name), m.unit) for m in self.metrics}}
                for r in self.rows
            ]
            ch = self.changes(m0)
            if ch:
                data["changes"] = {k: fmt_change(c, p, m0.unit) for k, (c, p) in ch.items()}
        if self.context:
            data["context"] = [{"id": c["id"], "text": c["text"]} for c in self.context]
        return data


# ------------------------------------------------------------------ template narrator


def narrate_template(f: Facts) -> str:
    """Deterministic narrative used offline and as the fallback when an LLM answer fails verification."""
    parts: list[str] = []
    for i, m in enumerate(f.metrics):
        cur = f.overall.get(m.name)
        if cur is None:
            parts.append(f"There is no {m.label.lower()} data for {f.period_label}.")
            continue
        s = f"{m.label} was {fmt(cur, m.unit)} for {f.period_label}" if i == 0 else f"{m.label} was {fmt(cur, m.unit)}"
        if f.previous and f.previous.get(m.name) is not None:
            prev = f.previous[m.name]
            change = fmt_change(cur, prev, m.unit)
            s += f", compared with {fmt(prev, m.unit)} for {f.previous_label}"
            verdict = _verdict(cur, prev, m.direction)
            if change or verdict:
                s += f" ({', '.join(x for x in (change, verdict) if x)})"
        parts.append(s + ".")

    m0 = f.metrics[0]
    rows = [r for r in f.rows if r.get(m0.name) is not None]
    if f.dimensions and rows:
        d = f.dimensions[0]
        label = f.dimension_labels[d].lower()
        if d in ("year", "quarter", "month", "week"):
            hi = max(rows, key=lambda r: r[m0.name])
            lo = min(rows, key=lambda r: r[m0.name])
            parts.append(
                f"By {label}, it ranged from {fmt(lo[m0.name], m0.unit)} in {lo[d]} to {fmt(hi[m0.name], m0.unit)} in {hi[d]}; the latest {label} ({rows[-1][d]}) was {fmt(rows[-1][m0.name], m0.unit)}."
            )
        elif len(rows) == 1:
            parts.append(f"{rows[0][d]} is the only {label} in scope.")
        else:
            first, last = rows[0], rows[-1]
            parts.append(
                f"Across {len(rows)} {_plural(label)}, {first[d]} was highest at {fmt(first[m0.name], m0.unit)} and {last[d]} lowest at {fmt(last[m0.name], m0.unit)}."
                if _sorted_desc(rows, m0.name)
                else f"Across {len(rows)} {_plural(label)}, {first[d]} was lowest at {fmt(first[m0.name], m0.unit)} and {last[d]} highest at {fmt(last[m0.name], m0.unit)}."
            )
            ch = f.changes(m0)
            if ch:
                key, (c, p) = max(ch.items(), key=lambda kv: abs(kv[1][0] - kv[1][1]))
                parts.append(
                    f"The biggest change versus {f.previous_label} was {key}: {fmt(p, m0.unit)} to {fmt(c, m0.unit)} ({fmt_change(c, p, m0.unit)})."
                )

    if f.context:
        c = f.context[0]
        parts.append(f"Context from the operations notes: {c['summary'].rstrip('.')} [{c['id']}].")
    return " ".join(parts)


def _plural(word: str) -> str:
    if word.endswith("y") and not word.endswith("ey"):
        return word[:-1] + "ies"
    return word if word.endswith("s") else word + "s"


def _sorted_desc(rows: list[dict], key: str) -> bool:
    return rows[0][key] >= rows[-1][key]


def _verdict(cur: float, prev: float, direction: str) -> str:
    if direction == "neutral" or cur == prev:
        return ""
    better = cur > prev if direction == "up" else cur < prev
    return "an improvement" if better else "a deterioration"


# ------------------------------------------------------------------ LLM narrator

NARRATOR_PROMPT = """You write short, plain-English insights for business users (procurement, manufacturing, sales) at a snack manufacturer.
Use ONLY the facts in the JSON. Copy every number exactly as formatted there — never calculate, round or invent a number.
Start with the direct answer, then the most important difference or change. If context notes are given and explain the change, mention them and cite the id, e.g. [N1].
At most 5 sentences. No headings, no bullet points, no recommendations that are not supported by the facts."""


def narrate_live(f: Facts, question: str, llm) -> str:
    import json

    msg = llm.invoke([("system", NARRATOR_PROMPT), ("human", f"Question: {question}\n\nFacts:\n{json.dumps(f.as_prompt(), default=str, indent=1)}")])
    return msg.content if isinstance(msg.content, str) else str(msg.content)


# ------------------------------------------------------------------ verification

NUMBER = re.compile(r"(?<![\w-])([-+−]?)(€?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s?(%|pp|t\b|h\b|/kg)?")
DATEISH = re.compile(
    r"\b\d{4}-\d{2}(-\d{2})?\b|\b\d{4}-W\d{2}\b|\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\b|\bQ[1-4]\s+\d{4}\b|\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b|\b(19|20)\d{2}\b|\[N\d+\]"
)


@dataclass
class Verification:
    status: str  # "verified" | "corrected" | "replaced"
    checked: int
    ungrounded: list[str]


def verify_numbers(text: str, facts: Facts, question: str = "") -> tuple[str, Verification]:
    """Check every number in the narrative against the facts. Sentences with an unsupported number are removed."""
    allowed = facts.numbers()
    question_numbers = {m.group(3).replace(",", "") for m in NUMBER.finditer(DATEISH.sub(" ", question))}
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept: list[str] = []
    bad: list[str] = []
    checked = 0
    context_text = " ".join(c["text"] for c in facts.context)
    for s in sentences:
        scrubbed = s
        for label in (facts.period_label, facts.previous_label):
            if label:
                scrubbed = scrubbed.replace(label, " ")  # "last 12 months (Oct 2025–Sep 2026)" is a period, not a figure
        scrubbed = DATEISH.sub(" ", scrubbed)
        cites_context = bool(re.search(r"\[N\d+\]", s))
        ok = True
        for m in NUMBER.finditer(scrubbed):
            sign, euro, whole, dec, suffix = m.groups()
            raw = whole.replace(",", "")
            if not euro and not suffix and not dec and raw in question_numbers:
                continue  # e.g. "top 3" repeated from the question
            if cites_context and m.group(0).strip() in context_text:
                continue  # quoted from a cited operations note, not a computed figure
            checked += 1
            value = float(raw + ("." + dec if dec else "")) * (-1 if sign in ("-", "−") else 1)
            decimals = len(dec or "")
            if not _grounded(value, decimals, suffix, allowed):
                ok = False
                bad.append(m.group(0).strip())
        (kept if ok else []).append(s)
    if not bad:
        return text, Verification("verified", checked, [])
    return " ".join(kept), Verification("corrected", checked, bad)


def _grounded(value: float, decimals: int, suffix: str | None, allowed: list[float]) -> bool:
    tol = 0.5 * 10 ** (-decimals) + 1e-9
    candidates = [value / 100] if suffix in ("%", "pp") else [value]
    if suffix in ("%", "pp"):
        tol /= 100
    for c in candidates:
        for a in allowed:
            if abs(abs(a) - abs(c)) <= tol * (1.0001):
                return True
    return False
