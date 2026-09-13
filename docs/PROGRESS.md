# Progress log

## 2026-09-12: Milestone 0, reset

- Cloned `sahajm99/talk-to-your-data` fresh; repo-local git identity set to sahajm99.
- Probed the free-tier stack on Windows Python 3.12: fastembed 0.8.0 loads
  `BAAI/bge-small-en-v1.5` in 0.4 s (384 dims), sqlite-vec 0.1.9 and FTS5 available.
- Downloaded the three preloaded public-domain documents (`data/SOURCE.md`).
- Removed the v1 Weaviate, OpenAI and visual-grounding modules, the old static UI and
  nine obsolete setup and troubleshooting files. Wrote `docs/DESIGN.md` (the module
  and API contracts) and `docs/DECISIONS.md`.
