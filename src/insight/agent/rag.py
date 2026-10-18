"""Retrieval over the business glossary, operations notes and reporting guide.

Hybrid: ChromaDB vector search + BM25, fused with reciprocal rank fusion. The vector side
uses deterministic hashing embeddings offline (no model download, reproducible in CI) and
OpenAI-compatible embeddings when configured.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi

STOP = set(
    "a an and are as at be by for from has have how i in is it its of on or our the this to was we what when where which who why will with "
    "did does do show me tell give much many vs versus than".split()
)


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", text.lower())
    return [t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t for t in toks if t not in STOP and len(t) > 1]


def hash_embed(text: str, dims: int = 512) -> list[float]:
    v = [0.0] * dims
    toks = tokenize(text)
    for f in toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]:
        h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "big")
        v[(h >> 1) % dims] += 1.0 if h & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


@dataclass(frozen=True)
class Passage:
    id: str
    doc: str
    title: str
    section: str
    text: str


def load_passages(directory: Path) -> list[Passage]:
    out: list[Passage] = []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta = dict(re.findall(r"^(\w+):\s*(.+)$", raw.split("---")[1], re.M)) if raw.startswith("---") else {}
        body = raw.split("---", 2)[2] if raw.startswith("---") else raw
        doc = meta.get("id", path.stem)
        for i, block in enumerate(re.split(r"^## ", body, flags=re.M)[1:]):
            heading, _, text = block.partition("\n")
            out.append(Passage(id=f"{doc}#{i}", doc=doc, title=meta.get("title", doc), section=heading.strip(), text=text.strip()))
    return out


class KnowledgeIndex:
    def __init__(self, directory: Path, persist_dir: Path | None = None, embed=hash_embed):
        self.passages = load_passages(directory)
        self._by_id = {p.id: p for p in self.passages}
        self._embed = embed
        docs = [tokenize(f"{p.section} {p.text}") for p in self.passages]
        self._bm25 = BM25Okapi(docs)
        client = chromadb.PersistentClient(path=str(persist_dir)) if persist_dir else chromadb.EphemeralClient()
        self._coll = client.get_or_create_collection("knowledge", embedding_function=None, configuration={"hnsw": {"space": "cosine"}})
        existing = set(self._coll.get(include=[])["ids"])
        stale = sorted(existing - set(self._by_id))
        if stale:
            self._coll.delete(ids=stale)
        self._coll.upsert(
            ids=[p.id for p in self.passages],
            embeddings=[self._embed(f"{p.section}\n{p.text}") for p in self.passages],
            documents=[p.text for p in self.passages],
            metadatas=[{"doc": p.doc, "section": p.section} for p in self.passages],
        )

    def search(self, query: str, k: int = 3, min_bm25: float = 1.5) -> list[tuple[Passage, float]]:
        """Top-k passages. Requires lexical evidence (BM25 >= min_bm25) so off-topic questions retrieve nothing."""
        q = tokenize(query)
        if not q:
            return []
        bm = self._bm25.get_scores(q)
        lex = sorted(((s, p.id) for s, p in zip(bm, self.passages, strict=True) if s >= min_bm25), reverse=True)[:10]
        vec = self._coll.query(query_embeddings=[self._embed(query)], n_results=min(10, len(self.passages)))["ids"][0]
        fused: dict[str, float] = {}
        for rank, (_, pid) in enumerate(lex):
            fused[pid] = fused.get(pid, 0) + 1 / (60 + rank + 1)
        allowed = {pid for _, pid in lex}
        for rank, pid in enumerate(vec):
            if pid in allowed:  # vectors re-rank; they never introduce a passage with no lexical support
                fused[pid] = fused.get(pid, 0) + 1 / (60 + rank + 1)
        best = sorted(fused.items(), key=lambda x: -x[1])[:k]
        return [(self._by_id[pid], score) for pid, score in best]
