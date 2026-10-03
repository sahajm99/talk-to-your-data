# Talk To Your Data: design (v2, free-tier rebuild)

Ask questions of a document and get an answer with citations that open the exact
passage, plus the retrieval evidence behind it. Runs on one free-tier container with
no external services: in-process embeddings, SQLite for keyword and vector search,
Groq for generation when a key exists, extractive answers when it does not.

## What changes from v1

| v1 (2026-01) | v2 |
|---|---|
| OpenAI `text-embedding-3-large` | `fastembed` `BAAI/bge-small-en-v1.5`, 384 dims, in-process |
| Weaviate | SQLite: FTS5 for keywords, `sqlite-vec` for vectors, RRF fusion |
| OpenAI chat | Groq free tier (an open-weight model picked from the live model list, gpt-oss today), or extractive mode without a key |
| PyMuPDF page images, bounding boxes ("visual grounding") | Dropped; a citation opens and highlights the chunk text |
| Static HTML in `static/` | Jinja2 templates in `app/templates/`, assets in `app/static/` |
| `requirements.txt` | `pyproject.toml` + `uv.lock`, Python 3.12 |
| Unmeasured "40% improvement" | `python -m eval`: hit@5 and MRR for keyword, vector, hybrid over 40 questions |

## Repository layout

```
app/
  config.py                 Settings (pydantic-settings, env prefix none)
  models.py                 pydantic API models
  main.py                   FastAPI app, lifespan, routers, templates, static
  ingestion/loaders.py      RawDocument (kept from v1)
  ingestion/text_extractors.py  extract_text(raw) -> (text, meta) (kept; PDF via pdfplumber)
  ingestion/chunker.py      chunk_text(text, max_tokens, overlap_tokens) -> list[(idx, text)] (kept; enhanced chunker removed)
  ingestion/embedder.py     Embedder protocol, FastEmbedder, FakeEmbedder
  ingestion/store.py        SqliteStore
  ingestion/retrieval.py    rrf(), hybrid_search()
  ingestion/pipeline.py     ingest_raw_document(raw, scope, store, embedder) -> DocumentInfo
  ingestion/preload.py      python -m app.ingestion.preload  (build the preloaded index)
  services/generation.py    GroqGenerator, ExtractiveAnswerer, answer()
  services/ratelimit.py     RateLimiter
  services/sessions.py      SessionManager (cookie session id, upload scopes, TTL)
  api/routes_ask.py         POST /api/ask
  api/routes_ingest.py      POST /api/upload, GET /api/documents
  api/routes_health.py      GET /api/health, GET /api/about
  templates/index.html, about.html
  static/app.css, app.js, fonts/
eval/__main__.py, eval/questions.json, eval/results.json
data/preloaded/{sherlock-holmes.txt, federalist-papers.txt, nist-sp-800-63-3.pdf}, data/SOURCE.md
data/index.db               built by preload (git-ignored; built in the Docker image)
tests/                      pytest, FakeEmbedder everywhere, no model download
Dockerfile, .dockerignore, render.yaml, .github/workflows/ci.yml, pyproject.toml, uv.lock
docs/DESIGN.md, DECISIONS.md, PROGRESS.md
```

## Contracts (binding for every module)

### Settings (`app/config.py`)
`Settings(BaseSettings)` reading `.env`: `groq_api_key: str | None = None`, `groq_model: str = "openai/gpt-oss-120b"`, `groq_fallback_model: str = "openai/gpt-oss-20b"`, `embed_model: str = "BAAI/bge-small-en-v1.5"` (`"fake"` selects `FakeEmbedder`), `data_dir: Path = Path("data")`, `index_path: Path = Path("data/index.db")`, `chunk_max_tokens: int = 300`, `chunk_overlap_tokens: int = 50`, `top_k: int = 5`, `candidates_per_source: int = 20`, `rate_limit_questions: int = 10`, `rate_limit_window_seconds: int = 600`, `daily_question_cap: int = 500`, `max_upload_bytes: int = 2_000_000`, `session_ttl_minutes: int = 60`, `public_url: str = ""`. `get_settings()` cached.

### Embedder (`app/ingestion/embedder.py`)
```python
class Embedder(Protocol):
    dim: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...   # documents
    def embed_query(self, text: str) -> list[float]: ...
class FastEmbedder(Embedder)   # fastembed TextEmbedding(model_name), lazy model load, dim 384; embed_query uses the same model with the "query: " convention only if the model needs it (bge-small does not; pass through)
class FakeEmbedder(Embedder)   # dim 16, deterministic: hashed bag of words so that similar texts get similar vectors; used in tests and when EMBED_MODEL=fake
def get_embedder(settings) -> Embedder
```

### Store (`app/ingestion/store.py`)
SQLite file, `sqlite_vec` loaded, WAL. Schema:
```sql
documents(id TEXT PRIMARY KEY, title TEXT, source TEXT, scope TEXT, n_chunks INT, n_chars INT, created_at TEXT)
chunks(id INTEGER PRIMARY KEY, doc_id TEXT REFERENCES documents(id) ON DELETE CASCADE, idx INT, text TEXT)
chunks_fts USING fts5(text, content='chunks', content_rowid='id')   -- external content with insert/delete triggers
chunk_vec USING vec0(chunk_id INTEGER PRIMARY KEY, embedding float[<dim>])
```
`scope` is `"preloaded"` or a session id. Methods:
```python
class SqliteStore:
    def __init__(self, path: Path, dim: int)          # creates schema if missing; refuses to open if the stored dim differs
    def add_document(self, doc: DocumentInfo, chunks: list[str], vectors: list[list[float]]) -> None
    def keyword_search(self, query: str, scopes: list[str], k: int) -> list[tuple[int, float]]   # (chunk_id, bm25 score); query sanitised for FTS5 (quote each token, OR them)
    def vector_search(self, vector: list[float], scopes: list[str], k: int) -> list[tuple[int, float]]  # (chunk_id, cosine distance) via vec0 KNN filtered by scope
    def get_chunks(self, ids: list[int]) -> list[Chunk]    # preserves the order of ids
    def neighbours(self, chunk_id: int) -> tuple[Chunk | None, Chunk | None]
    def list_documents(self, scopes: list[str]) -> list[DocumentInfo]
    def delete_scope(self, scope: str) -> int
    def counts(self) -> dict   # documents, chunks
    def close(self)
```
Vector search filtered by scope: fetch `k * 4` nearest with `vec0` KNN (`WHERE embedding MATCH ? AND k = ?`), join to chunks and documents, keep rows whose scope is in `scopes`, truncate to k.

### Retrieval (`app/ingestion/retrieval.py`)
```python
def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]   # ids sorted by sum 1/(k+rank), rank from 1; ties by first appearance
@dataclass class Hit: chunk: Chunk; score: float; via: list[str]; keyword_rank: int | None; vector_rank: int | None
def hybrid_search(store, embedder, query, scopes, k=5, candidates=20, mode="hybrid") -> list[Hit]   # mode in {"keyword","vector","hybrid"}; hybrid = rrf of both candidate lists
```

### Models (`app/models.py`)
`Chunk(id, doc_id, doc_title, idx, text)`, `DocumentInfo(id, title, source, scope, n_chunks, n_chars, created_at)`, `AskRequest(question: str (1..500 chars), document_ids: list[str] = [] (empty = every preloaded doc plus the session's uploads), mode: Literal["hybrid","keyword","vector"] = "hybrid")`, `Citation(n: int, chunk_id: int, doc_id: str, doc_title: str, idx: int, text: str)`, `RetrievalHit(chunk_id, doc_title, idx, score, via: list[str], keyword_rank, vector_rank, preview: str (first 240 chars))`, `AskResponse(answer: str, mode: Literal["groq","extractive"], model: str | None, citations: list[Citation], retrieval: list[RetrievalHit], latency_ms: int)`, `AboutInfo(generation_mode, model, embed_model, documents: list[DocumentInfo], eval: dict | None, rate_limit: dict)`.

### Generation (`app/services/generation.py`)
```python
@dataclass class Answer: text: str; mode: str; model: str | None; cited: list[int]   # cited = 1-based citation numbers used
class ExtractiveAnswerer:   # no key: returns the top hit's text with query terms wrapped in <mark> (HTML-escaped first), text prefixed "Best-supported passage:"; cited=[1]
class GroqGenerator:        # httpx to https://api.groq.com/openai/v1; on first use GET /models and pick settings.groq_model if present else fallback else first id containing "gpt-oss" or "llama"; prompt: system rule "answer only from the numbered passages, cite as [n], say 'The documents do not say' when unsupported"; temperature 0.1; max_completion_tokens 900; reasoning_effort low for gpt-oss models; gpt-oss citation marks normalised to [n]; 20 s timeout; on any error return an ExtractiveAnswerer result with mode "extractive" and note the error in logs
def answer(question: str, hits: list[Hit], settings) -> Answer
```

### Rate limit (`app/services/ratelimit.py`)
`RateLimiter(limit, window_seconds, daily_cap, clock=time.monotonic)`: `check(ip) -> tuple[bool, str]` sliding window per ip plus a global daily counter reset at UTC midnight; the API returns 429 with the reason. Client IP from `X-Forwarded-For` first value, else the socket.

### Sessions (`app/services/sessions.py`)
Cookie `ttyd_session` (random 32 hex, HttpOnly, SameSite=Lax); `SessionManager.get_or_create(request, response) -> str`; `touch`, `expired() -> list[str]`; a background task every 5 minutes deletes expired scopes from the store. Uploads are only ever written to the store under the session scope; nothing is written to disk; nothing is logged beyond the byte count and the extension.

### API
- `POST /api/ask` (JSON `AskRequest`) → `AskResponse`; 429 on rate limit; 400 on empty question; 404 if a document id is unknown or not visible to the session.
- `POST /api/upload` (multipart `file`, ≤ 2,000,000 bytes, extensions pdf docx txt md) → `DocumentInfo`; 413 if too large; 415 if unsupported.
- `GET /api/documents` → `list[DocumentInfo]` (preloaded first, then the session's).
- `GET /api/health` → `{status:"ok", documents, chunks, generation_mode}`; `GET /api/about` → `AboutInfo` (reads `eval/results.json` if present).
- `GET /` renders `index.html`; `GET /about` renders `about.html`.

### Eval (`eval/`)
`questions.json`: `[{"id": 1, "doc": "sherlock-holmes", "question": "...", "answer_phrase": "..."}]`, 40 items, 13 or 14 per document; `answer_phrase` is a verbatim substring of the extracted document text (case-insensitive match allowed) that identifies the gold chunk(s). `python -m eval` opens `data/index.db`, resolves each question's gold chunk ids by substring over that document's chunks (fail loudly if none), runs `hybrid_search` in each mode with `k = 5`, and writes `eval/results.json`: `{"n_questions": 40, "k": 5, "modes": {"keyword": {"hit_at_5": 0.x, "mrr": 0.x}, "vector": {...}, "hybrid": {...}}, "per_question": [...], "embed_model": ..., "generated_at": ...}` plus a Markdown table to stdout.

### UI
`index.html`: document picker (checkbox list of preloaded docs plus "Upload a file" with the 2 MB limit and the ephemeral note), question box, answer with `[n]` citations rendered as buttons, a citations list, and a retrieval panel (top hits with score, via badges keyword/vector/both, preview). Clicking a citation scrolls its chunk into view and highlights it. Mode switch (hybrid, keyword, vector) in a details block. Status line shows generation mode and latency. `about.html`: how it works, the eval table, limits, source credits. Design per the `frontend-design` skill: for reading and questioning documents; light and dark; responsive to 400 px; fonts self-hosted in `app/static/fonts/`; no CDN.

## Hosting

Docker image: `python:3.12-slim`, `uv` copied from `ghcr.io/astral-sh/uv`, `uv sync --frozen --no-dev`, model pre-downloaded at build (`FASTEMBED_CACHE_PATH=/app/.fastembed`), `python -m app.ingestion.preload` at build so `data/index.db` ships in the image, `CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT`. `render.yaml`: one free web service, `healthCheckPath: /api/health`, env vars `GROQ_API_KEY` (sync false), `PUBLIC_URL`. Free tier sleeps after idle; the landing page says the first load can take up to a minute. If memory exceeds the free tier, switch to Hugging Face Spaces (Docker) and record it.

## Verification

`uv run pytest` (chunker, extractors, RRF hand case, store round trip with FakeEmbedder, rate limiter, API in extractive mode), `python -m eval` on the real index, headless QA on the live URL (ask, cite, upload, mode switch, about page, health), CI green.
