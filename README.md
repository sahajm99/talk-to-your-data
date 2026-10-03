# Talk To Your Data

[![CI](https://github.com/sahajm99/talk-to-your-data/actions/workflows/ci.yml/badge.svg)](https://github.com/sahajm99/talk-to-your-data/actions/workflows/ci.yml)

Ask a question of a document and get an answer whose citations open the exact passage they came from, next to the retrieval evidence that produced it. The whole thing runs in one free-tier container with no external services: embeddings are computed in-process, SQLite does both keyword (FTS5) and vector (sqlite-vec) search, the two rankings are fused with reciprocal rank fusion, and an open-weight model on Groq's free tier writes the answer when a key is present or the best-supported passage is returned when it is not. Retrieval quality is measured, not asserted: every number below is copied from `eval/results.json`, which `uv run python -m eval` regenerates.

**Live:** https://talk-to-your-data.onrender.com (free tier; the first load after idle can take up to a minute)

## What you can do

- Ask questions of three preloaded documents in three registers: The Adventures of Sherlock Holmes, The Federalist Papers and NIST SP 800-63-3 (a PDF).
- Click any `[n]` citation in the answer and the cited passage scrolls into view and is highlighted; the retrieval panel shows the top five passages with their scores, whether keyword search, vector search or both found them, and their rank in each.
- Switch retrieval between hybrid, keyword and vector and see how the ranking changes for the same question.
- Upload your own PDF, DOCX, TXT or Markdown file (up to 2 MB) and question it; it lives in your session only and is deleted after an hour.

## Measured retrieval

Forty questions, each answered by one known passage of one preloaded document (13 or 14 per document), split by what they test: `lexical` questions reuse distinctive words from the passage, `paraphrase` questions avoid them, `entity` questions turn on a name, date or number. Hit@5 is the share of questions whose gold passage lands in the top five; MRR is the mean of 1/rank of that passage, 0 when it is absent. Embedding model `BAAI/bge-small-en-v1.5`, k = 5, 20 candidates per retriever.

Across all three documents, which is what a visitor gets with every document ticked:

| mode | hit@5 | MRR |
|---|---:|---:|
| keyword | 0.750 | 0.588 |
| vector | 0.575 | 0.372 |
| hybrid | 0.775 | 0.542 |

Within the gold document only:

| mode | hit@5 | MRR |
|---|---:|---:|
| keyword | 0.750 | 0.588 |
| vector | 0.575 | 0.372 |
| hybrid | 0.775 | 0.546 |

By question kind, across all three documents:

| kind | n | keyword hit@5 | keyword MRR | vector hit@5 | vector MRR | hybrid hit@5 | hybrid MRR |
|---|---:|---:|---:|---:|---:|---:|---:|
| entity | 12 | 0.833 | 0.662 | 0.667 | 0.413 | 0.833 | 0.603 |
| lexical | 13 | 0.846 | 0.744 | 0.462 | 0.301 | 0.769 | 0.515 |
| paraphrase | 15 | 0.600 | 0.394 | 0.600 | 0.402 | 0.733 | 0.516 |

What the numbers show: hybrid finds the passage most often (31 of 40 questions, against 30 for keyword and 23 for vector), but keyword search ranks it higher when it does find it, so keyword keeps the better MRR; fusion pays off on paraphrase questions, where hybrid beats both retrievers, and costs a little on lexical questions, where mixing in the weaker vector list pushes keyword's first-place hits down. Restricting search to the right document changes almost nothing, because the three documents are distinct enough that the top five nearly always come from the right one already; the misses are inside the document, not caused by the other two. Per-question ranks, a per-document breakdown and the gold chunk ids are in `eval/results.json`; the question set and how each gold passage was verified are in `eval/README.md`.

## How it works

1. Ingest. Text is extracted (pdfplumber for PDF, python-docx for DOCX, plain text and Markdown as they are), Project Gutenberg wrappers are stripped, and the text is cut into 300-word windows that overlap by 50 words so an answer is rarely split in two.
2. Index. Each window is embedded with `BAAI/bge-small-en-v1.5` through fastembed (ONNX, in-process, 384 dimensions) and written to one SQLite file: an FTS5 table for BM25 keyword search and a sqlite-vec table for cosine nearest neighbours.
3. Retrieve. The question goes to both indexes, restricted to the passages the visitor can see (preloaded plus their own session's uploads), and each returns 20 candidates.
4. Fuse. Reciprocal rank fusion (k = 60) merges the two lists and the top five become the numbered passages. Keyword-only and vector-only modes skip this step.
5. Generate or extract. With `GROQ_API_KEY` set, an open-weight model on Groq's free tier (gpt-oss-120b today, picked from Groq's live model list because free models are retired without notice) answers from the numbered passages only, cites them as `[n]` and says so when they do not support an answer; without a key, or when Groq fails, the top passage is returned with the question's terms highlighted.

The contracts every module follows are in `docs/DESIGN.md`; the reasoning behind the choices is in `docs/DECISIONS.md`.

## Run it locally

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run python -m app.ingestion.preload    # downloads the embedding model on first use, builds data/index.db
uv run uvicorn app.main:app --reload       # http://127.0.0.1:8000
```

Optional: put `GROQ_API_KEY=...` in a `.env` file to get generated answers instead of extractive ones. Then:

```
uv run pytest                             # tests with a fake embedder, no model download
uv run python -m eval                     # retrieval evaluation on the real index, rewrites eval/results.json
```

## Hosting

Deployed on Render's free tier from the `Dockerfile`: the image bakes in the embedding model and the prebuilt `data/index.db`, so a fresh container serves as soon as the process boots. The service sleeps when idle, so the first load after a quiet spell can take up to a minute. `render.yaml` describes the service and its two environment variables, `GROQ_API_KEY` and `PUBLIC_URL`.

## Limits

- Ten questions per ten minutes per IP address, plus a daily cap across all visitors, so a free Groq key cannot be drained through the demo.
- Uploads are capped at 2 MB and must be PDF, DOCX, TXT or Markdown; they are held in the session's scope only and deleted after sixty idle minutes and on every restart.
- Scanned PDFs yield no text: there is no OCR, and images, tables and layout are not interpreted.
- The embedding model is small and English-only; questions phrased very differently from the passage can miss, as the vector column above shows.
- Answers are grounded in single passages of 300 words; a question whose answer is spread across several parts of a document may get a partial answer or "The documents do not say".
- Generation depends on Groq's free tier; if the key is missing, a model is retired or a request fails, the app returns the best-supported passage rather than an error.

## Data

- The Adventures of Sherlock Holmes, Arthur Conan Doyle: Project Gutenberg eBook #1661, public domain in the United States.
- The Federalist Papers, Hamilton, Madison and Jay: Project Gutenberg eBook #1404, public domain in the United States.
- NIST Special Publication 800-63-3, Digital Identity Guidelines: a work of the United States Government, not subject to copyright in the United States.

The Gutenberg header and licence text are stripped before indexing. Visitor uploads are never written to disk, never logged beyond their size and extension, and never kept beyond the session.

## Layout

```
app/
  config.py, models.py, main.py    settings, pydantic models, FastAPI app
  ingestion/                       loaders, text extraction, chunker, embedder, SQLite store, retrieval, preload
  services/                        generation (Groq or extractive), rate limiter, sessions
  api/                             /api/ask, /api/upload, /api/documents, /api/health, /api/about
  templates/, static/              Jinja2 pages, CSS, JS, self-hosted fonts
eval/                              questions.json, __main__.py (the runner), results.json, README.md
data/preloaded/                    the three source documents; data/index.db is built from them
tests/                             pytest with a fake embedder
docs/                              DESIGN.md, DECISIONS.md, PROGRESS.md
Dockerfile, render.yaml, .github/workflows/ci.yml, pyproject.toml, uv.lock
```

## Licence

MIT, see `LICENSE`.
