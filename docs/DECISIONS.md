# Decisions

| # | Decision | Why |
|---|----------|-----|
| D1 | No external services: fastembed `bge-small-en-v1.5` in-process, SQLite FTS5 plus `sqlite-vec`, RRF fusion. | The v1 needed Weaviate and a paid key, so it was never hosted; one container on a free tier is the whole point. Probe on 2026-09-12: model loads in 0.4 s, 8 embeddings in 0.05 s, `sqlite-vec` 0.1.9 and FTS5 available. |
| D2 | Visual grounding (PyMuPDF page crops, bounding boxes) is removed. | It doubled the dependencies and memory for a feature the demo does not need; a citation that scrolls to and highlights the chunk text carries the same trust signal. |
| D3 | Generation through Groq's OpenAI-compatible endpoint with `httpx`, model chosen at first use from the live model list; without a key the app answers extractively. | Groq's free models get retired without notice; the demo must never be dead because a model name changed or a key is missing. |
| D4 | Rate limit 10 questions per 10 minutes per IP plus a daily cap from the environment; uploads capped at 2 MB, session-scoped, never written to disk, deleted after 60 idle minutes and on every restart. | A public demo with a free key must not be an open proxy; visitor documents are not the site's to keep. |
| D5 | Retrieval quality is measured, not asserted: 40 questions with verbatim answer phrases over the three preloaded documents, hit@5 and MRR for keyword, vector and hybrid, published in the README and on the About page whatever they show. | The portfolio card said "40% improvement" with nothing behind it. |
| D6 | Preloaded documents: The Adventures of Sherlock Holmes (Gutenberg 1661), The Federalist Papers (Gutenberg 1404), NIST SP 800-63-3 (US government work). | Public domain, three different registers (fiction, argument, technical standard), and the last one is a PDF so the PDF path is exercised in production. |
| D7 | Chunks of 300 words with 50 overlap; hybrid takes 20 candidates per source and returns 5. | Small enough for the embedding model's context, large enough to hold an answer; RRF with k = 60 as published. |
| D8 | Tests use a deterministic `FakeEmbedder`; the real model runs only in preload, eval and production. | CI stays under a minute and needs no model download. |
| D9 | Jinja2 templates plus vanilla JavaScript and self-hosted fonts; no build step, no CDN. | One process serves everything; nothing to break when a CDN or a bundler changes. |
| D10 | Render free tier from the Dockerfile with the index and model baked into the image; Hugging Face Spaces is the recorded fallback if memory is short. | The account exists and Groundscope already runs there; baking the index means a cold start serves immediately after the process boots. |
| D11 | Process: fresh implementer per task in parallel on disjoint files, no per-task reviews, one controller QA on the live URL. | The user asked for accelerated delivery. |
| D12 | Every commit authored as `sahajm99` with no co-author trailer. | Standing instruction for all portfolio repos. |
