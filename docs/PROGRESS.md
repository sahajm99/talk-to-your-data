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

## 2026-10-03: Milestone 4, deployment

- Found that `data/` was ignored wholesale, so the three preloaded documents never reached
  GitHub and a cloud build would have shipped an empty index. Un-ignored `data/preloaded/`
  and `data/SOURCE.md` (provenance for the three documents) and committed them.
- Committed the Dockerfile, `.dockerignore`, Render blueprint and CI workflow that had sat
  untracked since 2026-09-13. Aligned README and DESIGN with the shipped generator: gpt-oss on
  Groq picked from the live model list, 900 completion tokens, citation-mark normalisation.
- First local image build: 827 MB; `/api/health` answers about four seconds after start with
  three documents and 1,273 chunks; about 265 MiB resident after a query; extractive mode
  without a key.
- Pushed `main` to GitHub, 13 commits since v1. The first CI run failed before the tests
  because `astral-sh/setup-uv` has no floating `v10` tag; pinned to `v10.2.0`. Run
  37090241302 is green: 51 tests in 11 s, then the Docker build and boot check in 3 m 40 s
  from the GitHub clone, which confirms the data fix.
- Render service `srv-db081e2d0e5s73aftkpg` created through the API with the blueprint's settings
  (free, Oregon, Docker, health check `/api/health`, `GROQ_API_KEY`, `PUBLIC_URL`,
  `DAILY_QUESTION_CAP`). Render assigned the suffixed hostname
  https://talk-to-your-data-9pvq.onrender.com, so README, `render.yaml` and the portfolio card
  were updated to it. First deploy went live about six minutes after creation.
- Verified live against the DESIGN list: health reports three documents, 1,273 chunks and Groq
  generation with `openai/gpt-oss-120b`; landing and about pages answer 200; hybrid and keyword
  questions return grounded answers with five citations in 0.6 to 1.8 s; a 140-byte upload is
  indexed into its session and answered with a citation; the session sees its own upload and the
  three preloaded documents only. A third question fired within five seconds fell back to
  extractive mode, which is the designed response to a Groq rejection (free-tier per-minute limit).
- `RENDER_API_KEY` and `RENDER_SERVICE_ID` are GitHub Actions secrets on the repo for future
  API-driven deploys; the local key lives only in the gitignored `.env`.
