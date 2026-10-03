"""Retrieval evaluation: ``uv run python -m eval``.

Opens the preloaded index (building it first if it is missing), resolves the gold
chunk ids for every question in ``eval/questions.json`` by substring match of its
``answer_phrase`` over that document's chunks, runs ``hybrid_search`` in keyword,
vector and hybrid mode with ``k = 5`` and ``candidates = 20``, and writes
``eval/results.json`` plus a Markdown summary to stdout.

Two scopes are measured:

- ``all_documents``: the query runs over every preloaded chunk, exactly what a
  visitor gets with all three documents ticked. These are the headline numbers and
  fill the DESIGN.md ``modes`` block.
- ``within_document``: the query is restricted to the question's own document.
  ``hybrid_search`` has no document filter, so the runner retrieves the full
  corpus ranking (``k = candidates = number of chunks``), keeps only the hits from
  the gold document and truncates to ``k``. For keyword and vector mode that is
  identical to searching the document alone; for hybrid mode the RRF ranks are the
  corpus-wide ones, not a re-fusion of per-document lists.

Metrics: hit@5 (any gold chunk in the top five) and MRR (1 / rank of the first
gold chunk, 0 when absent).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.ingestion.embedder import get_embedder
from app.ingestion.retrieval import MODES, Hit, hybrid_search
from app.ingestion.store import SqliteStore
from app.models import Chunk, DocumentInfo

HERE = Path(__file__).resolve().parent
QUESTIONS_PATH = HERE / "questions.json"
RESULTS_PATH = HERE / "results.json"
PRELOADED = "preloaded"
K = 5
CANDIDATES = 20
SCOPES: dict[str, str] = {
    "all_documents": (
        "Query over every preloaded chunk (all three documents), k = 5, candidates = 20."
    ),
    "within_document": (
        "Full corpus ranking filtered to the question's own document, then top 5. "
        "Keyword and vector ranks equal a single-document search; hybrid keeps the "
        "corpus-wide RRF order."
    ),
}
_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Collapse whitespace runs to one space, strip, lowercase."""
    return _WS.sub(" ", text).strip().lower()


def load_questions(path: Path) -> list[dict[str, Any]]:
    questions = json.loads(path.read_text(encoding="utf-8"))
    required = ("id", "doc", "question", "answer_phrase", "kind")
    problems = []
    for i, q in enumerate(questions):
        missing = [f for f in required if f not in q]
        if missing:
            problems.append(f"item {i}: missing {missing}")
    ids = [q.get("id") for q in questions]
    if len(set(ids)) != len(ids):
        problems.append(f"duplicate ids: {[i for i, n in Counter(ids).items() if n > 1]}")
    if problems:
        raise SystemExit(f"{path} is malformed:\n  " + "\n  ".join(problems))
    return questions


def ensure_index(settings: Settings) -> None:
    """Build the preloaded index with the real embedder if it does not exist yet."""
    if settings.index_path.exists():
        return
    print(
        f"{settings.index_path} not found; building it with app.ingestion.preload",
        file=sys.stderr,
    )
    from app.ingestion import preload

    preload.build(settings, out=sys.stderr)


def document_chunks(store: SqliteStore, doc: DocumentInfo) -> list[Chunk]:
    """Every chunk of ``doc`` in index order (the store has no per-document reader)."""
    rows = store.conn.execute(
        "SELECT id FROM chunks WHERE doc_id = ? ORDER BY idx", (doc.id,)
    ).fetchall()
    return store.get_chunks([r["id"] for r in rows])


def map_documents(
    questions: list[dict[str, Any]], docs: list[DocumentInfo]
) -> dict[str, DocumentInfo]:
    """``question["doc"]`` is the file stem of the preloaded source file."""
    by_stem = {Path(d.source).stem: d for d in docs}
    keys = sorted({q["doc"] for q in questions})
    missing = [k for k in keys if k not in by_stem]
    if missing:
        raise SystemExit(
            f"no preloaded document for {missing}; index has {sorted(by_stem)} "
            "(run: uv run python -m app.ingestion.preload)"
        )
    return {k: by_stem[k] for k in keys}


def resolve_gold(
    questions: list[dict[str, Any]], chunks_by_doc: dict[str, list[Chunk]]
) -> dict[int, list[int]]:
    """Gold chunk ids per question id: chunks whose normalised text contains the phrase."""
    gold: dict[int, list[int]] = {}
    unmatched: list[str] = []
    for q in questions:
        phrase = normalise(q["answer_phrase"])
        ids = [c.id for c in chunks_by_doc[q["doc"]] if phrase in normalise(c.text)]
        if not ids:
            unmatched.append(f"id {q['id']} ({q['doc']}): {q['answer_phrase']!r}")
        gold[q["id"]] = ids
    if unmatched:
        raise SystemExit(
            f"{len(unmatched)} answer phrase(s) match no chunk of their document; the "
            "extractor, Gutenberg stripping or chunker changed, or the index is stale:\n  "
            + "\n  ".join(unmatched)
        )
    return gold


def search(
    store: SqliteStore,
    embedder: Any,
    question: str,
    mode: str,
    scope: str,
    doc_id: str,
    total_chunks: int,
) -> list[Hit]:
    if scope == "all_documents":
        return hybrid_search(
            store, embedder, question, [PRELOADED], k=K, candidates=CANDIDATES, mode=mode
        )
    hits = hybrid_search(
        store,
        embedder,
        question,
        [PRELOADED],
        k=total_chunks,
        candidates=total_chunks,
        mode=mode,
    )
    return [h for h in hits if h.chunk.doc_id == doc_id][:K]


def first_gold_rank(hits: list[Hit], gold: list[int]) -> int | None:
    gold_set = set(gold)
    for rank, hit in enumerate(hits, start=1):
        if hit.chunk.id in gold_set:
            return rank
    return None


def summarise(ranks: list[int | None]) -> dict[str, float | int]:
    n = len(ranks)
    if n == 0:
        return {"hit_at_5": 0.0, "mrr": 0.0, "hits": 0, "n": 0}
    hits = sum(1 for r in ranks if r is not None and r <= K)
    mrr = sum(1.0 / r for r in ranks if r is not None and r <= K) / n
    return {"hit_at_5": round(hits / n, 3), "mrr": round(mrr, 3), "hits": hits, "n": n}


def breakdown(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    """``{value: {"n": ..., mode: {"hit_at_5", "mrr", "hits", "n"}}}`` for one scope's rows."""
    out: dict[str, dict[str, Any]] = {}
    for value in sorted({r[field] for r in rows}):
        block: dict[str, Any] = {"n": len({r["id"] for r in rows if r[field] == value})}
        for mode in MODES:
            block[mode] = summarise(
                [r["rank"] for r in rows if r[field] == value and r["mode"] == mode]
            )
        out[value] = block
    return out


def evaluate(
    store: SqliteStore,
    embedder: Any,
    questions: list[dict[str, Any]],
    docs: dict[str, DocumentInfo],
    gold: dict[int, list[int]],
) -> list[dict[str, Any]]:
    total = store.counts()["chunks"]
    rows: list[dict[str, Any]] = []
    for q in questions:
        for scope in SCOPES:
            for mode in MODES:
                hits = search(store, embedder, q["question"], mode, scope, docs[q["doc"]].id, total)
                rows.append(
                    {
                        "id": q["id"],
                        "kind": q["kind"],
                        "doc": q["doc"],
                        "scope": scope,
                        "mode": mode,
                        "rank": first_gold_rank(hits, gold[q["id"]]),
                    }
                )
    return rows


def build_results(
    settings: Settings,
    store: SqliteStore,
    questions: list[dict[str, Any]],
    docs: dict[str, DocumentInfo],
    gold: dict[int, list[int]],
    rows: list[dict[str, Any]],
    elapsed: float,
) -> dict[str, Any]:
    scopes: dict[str, Any] = {}
    for scope, description in SCOPES.items():
        scope_rows = [r for r in rows if r["scope"] == scope]
        scopes[scope] = {
            "description": description,
            "modes": {
                mode: summarise([r["rank"] for r in scope_rows if r["mode"] == mode])
                for mode in MODES
            },
            "by_kind": breakdown(scope_rows, "kind"),
            "by_doc": breakdown(scope_rows, "doc"),
        }
    headline = "all_documents"
    counts = store.counts()
    return {
        "n_questions": len(questions),
        "k": K,
        "candidates": CANDIDATES,
        "embed_model": settings.embed_model,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 1),
        "scope": headline,
        "modes": {
            mode: {
                "hit_at_5": scopes[headline]["modes"][mode]["hit_at_5"],
                "mrr": scopes[headline]["modes"][mode]["mrr"],
            }
            for mode in MODES
        },
        "scopes": scopes,
        "kinds": dict(sorted(Counter(q["kind"] for q in questions).items())),
        "index": {
            "path": settings.index_path.as_posix(),
            "documents": counts["documents"],
            "chunks": counts["chunks"],
        },
        "documents": [
            {"key": key, "id": d.id, "title": d.title, "n_chunks": d.n_chunks}
            for key, d in docs.items()
        ],
        "questions": [
            {"id": q["id"], "doc": q["doc"], "kind": q["kind"], "gold_chunk_ids": gold[q["id"]]}
            for q in questions
        ],
        "per_question": rows,
    }


def _fmt(x: float) -> str:
    return f"{x:.3f}"


TITLES = {
    "all_documents": "Across all three documents",
    "within_document": "Within the gold document",
}


def markdown(results: dict[str, Any]) -> str:
    heading = (
        f"## Retrieval evaluation: {results['n_questions']} questions, k = {results['k']}, "
        f"{results['embed_model']}"
    )
    lines = [heading, ""]
    for scope, block in results["scopes"].items():
        lines += [
            f"### {TITLES.get(scope, scope)}",
            "",
            "| mode | hit@5 | MRR |",
            "|---|---:|---:|",
        ]
        for mode in MODES:
            m = block["modes"][mode]
            lines.append(f"| {mode} | {_fmt(m['hit_at_5'])} | {_fmt(m['mrr'])} |")
        lines.append("")
    for scope, block in results["scopes"].items():
        for field, label in (("by_kind", "kind"), ("by_doc", "document")):
            lines += [
                f"### By {label}, {TITLES.get(scope, scope).lower()}",
                "",
                f"| {label} | n | " + " | ".join(f"{m} hit@5 | {m} MRR" for m in MODES) + " |",
                "|---|---:|" + "---:|---:|" * len(MODES),
            ]
            for value, b in block[field].items():
                cells = " | ".join(f"{_fmt(b[m]['hit_at_5'])} | {_fmt(b[m]['mrr'])}" for m in MODES)
                lines.append(f"| {value} | {b['n']} | {cells} |")
            lines.append("")
    return "\n".join(lines)


def run(questions_path: Path, out_path: Path, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    questions = load_questions(questions_path)
    ensure_index(settings)
    embedder = get_embedder(settings)
    store = SqliteStore(settings.index_path, embedder.dim)
    started = time.perf_counter()
    try:
        docs = map_documents(questions, store.list_documents([PRELOADED]))
        chunks_by_doc = {key: document_chunks(store, d) for key, d in docs.items()}
        gold = resolve_gold(questions, chunks_by_doc)
        rows = evaluate(store, embedder, questions, docs, gold)
        results = build_results(
            settings, store, questions, docs, gold, rows, time.perf_counter() - started
        )
    finally:
        store.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m eval", description="Retrieval evaluation over the preloaded index."
    )
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH)
    parser.add_argument("--out", type=Path, default=RESULTS_PATH)
    args = parser.parse_args(argv)
    results = run(args.questions, args.out)
    print(markdown(results))
    print(
        f"wrote {args.out.as_posix()} "
        f"({results['n_questions']} questions x {len(SCOPES)} scopes x {len(MODES)} modes "
        f"in {results['elapsed_seconds']} s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
