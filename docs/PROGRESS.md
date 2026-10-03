# Progress log

## 2026-09-12: Milestone 0, reset

- Cloned `sahajm99/talk-to-your-data` fresh; repo-local git identity set to sahajm99.
- Probed the free-tier stack on Windows Python 3.12: fastembed 0.8.0 loads
  `BAAI/bge-small-en-v1.5` in 0.4 s (384 dims), sqlite-vec 0.1.9 and FTS5 available.
- Downloaded the three preloaded public-domain documents (`data/SOURCE.md`).
- Removed the v1 Weaviate, OpenAI and visual-grounding modules, the old static UI and
  nine obsolete setup and troubleshooting files. Wrote `docs/DESIGN.md` (the module
  and API contracts) and `docs/DECISIONS.md`.

## 2026-09-12 to 2026-09-13: Milestones 1 to 3, the rebuild

- Core: uv packaging on Python 3.12, settings, models; SQLite store (FTS5 plus sqlite-vec),
  fastembed embedder, hybrid retrieval with reciprocal rank fusion; ingestion pipeline and preload.
- Eval: 40-question retrieval set with verified answer phrases; `uv run python -m eval` measures
  hit@5 and MRR for keyword, vector and hybrid over two scopes and writes `eval/results.json`
  (hybrid hit@5 0.775, MRR 0.542 on 2026-09-13).
- UI and API: Jinja2 templates, styles, client script; ask, upload, documents, health and about
  routes; Groq generation with extractive fallback; rate limiting; sessions; document filter.
- Fix: answer from partial evidence; normalise gpt-oss citation marks.
