# Retrieval evaluation set

`questions.json` holds 40 questions over the three preloaded documents, each answerable
from a single passage. `python -m eval` (the runner, written separately) resolves the gold
chunk(s) for every question by substring match of `answer_phrase` over that document's
chunks, runs `hybrid_search` in keyword, vector and hybrid mode with `k = 5`, and reports
hit@5 and MRR per mode. Every `answer_phrase` below was verified programmatically against
the text the ingestion pipeline actually extracts (see [Verification](#verification)).

## Schema

```json
{"id": 1, "doc": "sherlock-holmes", "question": "...", "answer_phrase": "...", "kind": "entity"}
```

| field | meaning |
|---|---|
| `id` | 1..40, unique, in file order |
| `doc` | `sherlock-holmes`, `federalist-papers` or `nist-sp-800-63-3`: the stem of the file in `data/preloaded/` |
| `question` | what a visitor would type; 1 to 500 characters so the set can also be replayed through `POST /api/ask` (`AskRequest.question` limit) |
| `answer_phrase` | 4 to 12 words copied verbatim from the extracted text of `doc`; it answers the question and identifies the gold chunk(s). Occurs 1 to 3 times in the document. Match case-insensitively after collapsing whitespace |
| `kind` | `lexical`, `paraphrase` or `entity` (below) |

Kinds, so the results can be split by what each retriever is good at:

- `lexical`: the question reuses distinctive words from the gold passage. Keyword search
  should find these.
- `paraphrase`: the question is worded to avoid the passage's distinctive words, so vector
  search has to earn its keep.
- `entity`: the question turns on a proper name, date or number; the phrase carries the
  specific value, and the entity gives both retrievers an anchor.

## Distribution

| doc | lexical | paraphrase | entity | total |
|---|---:|---:|---:|---:|
| sherlock-holmes | 4 | 5 | 5 | 14 |
| federalist-papers | 5 | 5 | 3 | 13 |
| nist-sp-800-63-3 | 4 | 5 | 4 | 13 |
| **total** | **13** | **15** | **12** | **40** |

## How a phrase maps to a chunk

- The text is what `app.ingestion.text_extractors.extract_text` returns: the PDF through
  pdfplumber with `--- Page N ---` separators, the `.txt` files decoded as UTF-8. Preload
  strips the Project Gutenberg wrapper from the two `.txt` files first: everything before a
  line starting with `*** START OF` and from the line starting with `*** END OF` onwards.
- `chunk_text` splits on whitespace and joins with single spaces, so a chunk is a
  single-spaced word sequence. Collapse runs of whitespace in the phrase to one space,
  lowercase both sides, and test `phrase in chunk.text`. Punctuation stays attached to
  words exactly as in the source, which is why the phrases carry their commas, colons and
  the Gutenberg `_italics_` markers verbatim.
- Chunks are 300 words with 50 words of overlap, so chunk *i* covers words
  `[250i, 250i + 300)`. Any phrase of at most 50 words starting at word *w* lies wholly inside
  chunk `floor(w / 250)`. All phrases here are 12 words or fewer, so each one is inside at
  least one chunk; a phrase that sits in the overlap region matches two adjacent chunks,
  and both count as gold.
- Four NIST phrases (ids 28, 32, 33, 36) occur twice in the document, once in the executive
  summary or front matter and once in the body, so they have two gold chunks. Every other
  phrase occurs exactly once.
- If a phrase matches no chunk, the runner must fail loudly (DESIGN.md): it means the
  extractor, the Gutenberg stripping or the chunker changed, not that the question is bad.

## Verification

Save the script below as `verify_phrases.py` (anywhere; it reads `eval/questions.json` and
`data/preloaded/` relative to the current directory) and run it from the repository root:

```
uv run --with pdfplumber --with beautifulsoup4 --with python-docx --with pydantic --with fastapi python verify_phrases.py
```

The `--with` flags only matter while the project environment lacks those packages. The
script imports the repository's own extractor; if the `app` package cannot be imported
(for instance mid-rewrite) it falls back to pdfplumber and plain file reads, which are the
same operations, and prints which path it took. It exits non-zero if any phrase is outside
4 to 12 words, occurs fewer than 1 or more than 3 times, has an unknown kind, has a
question outside 1 to 500 characters, or if the ids or per-document counts are off.

```python
"""Verify every answer_phrase in eval/questions.json against the extracted document text.

Run from the repository root:
  uv run --with pdfplumber --with beautifulsoup4 --with python-docx --with pydantic --with fastapi python verify_phrases.py
"""
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
DOCS = {
    "sherlock-holmes": "sherlock-holmes.txt",
    "federalist-papers": "federalist-papers.txt",
    "nist-sp-800-63-3": "nist-sp-800-63-3.pdf",
}
EXPECTED = {"sherlock-holmes": 14, "federalist-papers": 13, "nist-sp-800-63-3": 13}
KINDS = {"lexical", "paraphrase", "entity"}


def strip_gutenberg(text: str) -> str:
    """Drop everything before a '*** START OF' line and from a '*** END OF' line onwards."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("*** START OF")), None)
    end = next((i for i, line in enumerate(lines) if line.startswith("*** END OF")), None)
    if start is not None:
        lines = lines[start + 1 : end if end is not None else len(lines)]
    return "\n".join(lines)


def extract(path: Path) -> tuple[str, str]:
    try:
        from app.ingestion.file_types import FileType
        from app.ingestion.loaders import RawDocument
        from app.ingestion.text_extractors import extract_text

        file_type = FileType.PDF if path.suffix == ".pdf" else FileType.TXT
        raw = RawDocument(project_id="eval", source_id=path.stem, file_type=file_type,
                          file_name=path.name, bytes=path.read_bytes())
        text, _ = extract_text(raw)
        how = "app.ingestion.text_extractors"
    except Exception as exc:  # app package unavailable: same operations, done directly
        import pdfplumber

        if path.suffix == ".pdf":
            with pdfplumber.open(io.BytesIO(path.read_bytes())) as pdf:
                text = "".join(f"\n\n--- Page {i} ---\n\n{page.extract_text() or ''}"
                               for i, page in enumerate(pdf.pages, 1))
        else:
            text = path.read_bytes().decode("utf-8", errors="ignore")
        how = f"fallback ({type(exc).__name__}: {exc})"
    if path.suffix == ".txt":
        text = strip_gutenberg(text)
    return text, how


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


questions = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
texts: dict[str, str] = {}
for doc, name in DOCS.items():
    text, how = extract(ROOT / "data" / "preloaded" / name)
    texts[doc] = norm(text)
    print(f"{doc}: {len(text.split())} words via {how}")

problems: list[str] = []
ids = [q["id"] for q in questions]
if ids != list(range(1, len(questions) + 1)):
    problems.append(f"ids are not 1..{len(questions)}: {ids}")
per_doc = Counter(q["doc"] for q in questions)
if per_doc != Counter(EXPECTED):
    problems.append(f"per-document counts {dict(per_doc)} != {EXPECTED}")

print()
print("| id | doc | kind | words | count |")
print("|---:|---|---|---:|---:|")
for q in questions:
    words = len(q["answer_phrase"].split())
    count = texts[q["doc"]].count(norm(q["answer_phrase"]))
    print(f"| {q['id']} | {q['doc']} | {q['kind']} | {words} | {count} |")
    if not 4 <= words <= 12:
        problems.append(f"id {q['id']}: answer_phrase has {words} words (need 4-12)")
    if not 1 <= count <= 3:
        problems.append(f"id {q['id']}: answer_phrase occurs {count} times (need 1-3)")
    if q["kind"] not in KINDS:
        problems.append(f"id {q['id']}: unknown kind {q['kind']!r}")
    if not 1 <= len(q["question"]) <= 500:
        problems.append(f"id {q['id']}: question length {len(q['question'])} (AskRequest allows 1-500)")

print()
print("kinds:", dict(sorted(Counter(q["kind"] for q in questions).items())))
if problems:
    print("FAILED:", *problems, sep="\n  ")
    sys.exit(1)
print(f"OK: all {len(questions)} answer phrases verified")
```

### Result on 2026-09-12

Extracted through `app.ingestion.text_extractors` (sherlock-holmes 104,506 words after
Gutenberg stripping, federalist-papers 192,347, nist-sp-800-63-3 21,121):

| id | doc | kind | words | count |
|---:|---|---|---:|---:|
| 1 | sherlock-holmes | entity | 9 | 1 |
| 2 | sherlock-holmes | paraphrase | 6 | 1 |
| 3 | sherlock-holmes | lexical | 8 | 1 |
| 4 | sherlock-holmes | lexical | 7 | 1 |
| 5 | sherlock-holmes | entity | 8 | 1 |
| 6 | sherlock-holmes | entity | 8 | 1 |
| 7 | sherlock-holmes | paraphrase | 11 | 1 |
| 8 | sherlock-holmes | paraphrase | 9 | 1 |
| 9 | sherlock-holmes | lexical | 9 | 1 |
| 10 | sherlock-holmes | entity | 6 | 1 |
| 11 | sherlock-holmes | paraphrase | 5 | 1 |
| 12 | sherlock-holmes | lexical | 7 | 1 |
| 13 | sherlock-holmes | entity | 5 | 1 |
| 14 | sherlock-holmes | paraphrase | 7 | 1 |
| 15 | federalist-papers | paraphrase | 7 | 1 |
| 16 | federalist-papers | lexical | 9 | 1 |
| 17 | federalist-papers | lexical | 7 | 1 |
| 18 | federalist-papers | paraphrase | 9 | 1 |
| 19 | federalist-papers | lexical | 9 | 1 |
| 20 | federalist-papers | paraphrase | 7 | 1 |
| 21 | federalist-papers | lexical | 11 | 1 |
| 22 | federalist-papers | paraphrase | 12 | 1 |
| 23 | federalist-papers | paraphrase | 11 | 1 |
| 24 | federalist-papers | entity | 12 | 1 |
| 25 | federalist-papers | entity | 7 | 1 |
| 26 | federalist-papers | entity | 10 | 1 |
| 27 | federalist-papers | lexical | 12 | 1 |
| 28 | nist-sp-800-63-3 | lexical | 12 | 2 |
| 29 | nist-sp-800-63-3 | entity | 8 | 1 |
| 30 | nist-sp-800-63-3 | entity | 10 | 1 |
| 31 | nist-sp-800-63-3 | lexical | 7 | 1 |
| 32 | nist-sp-800-63-3 | paraphrase | 10 | 2 |
| 33 | nist-sp-800-63-3 | lexical | 12 | 2 |
| 34 | nist-sp-800-63-3 | lexical | 11 | 1 |
| 35 | nist-sp-800-63-3 | paraphrase | 10 | 1 |
| 36 | nist-sp-800-63-3 | entity | 8 | 2 |
| 37 | nist-sp-800-63-3 | paraphrase | 8 | 1 |
| 38 | nist-sp-800-63-3 | paraphrase | 11 | 1 |
| 39 | nist-sp-800-63-3 | paraphrase | 8 | 1 |
| 40 | nist-sp-800-63-3 | entity | 9 | 1 |

`kinds: {'entity': 12, 'lexical': 13, 'paraphrase': 15}`, `OK: all 40 answer phrases verified`.

## Authoring notes

Things about the source text that shaped the phrases, so nobody "fixes" them:

- The Gutenberg files use curly quotes, `_underscores_` for italics and `£`; the PDF uses
  curly apostrophes and repeats a vertical watermark ("This publication is available free
  of charge from: https://doi.org/...") on every page, which lands inside chunks. Phrases
  avoid quotation marks, apostrophes and `£` so they survive retyping. Id 3 keeps
  `_the_` because that is how the extracted text reads. Id 4 starts at `4` because the
  advertisement reads `£ 4 a week`.
- The PDF extractor sometimes breaks a hyphenated word across a line (`hardware-` /
  `based`), which whitespace collapsing turns into `hardware- based`. Id 31 is taken from
  the executive summary, where `hardware-based` is intact.
- Phrases changed during authoring (occurrences in parentheses):
  - `four pounds a week` (0) became `4 a week for purely nominal services`; the text
    writes the salary as `£ 4 a week`.
  - `thirty-nine beryls` (0) became `There are thirty-nine enormous beryls`.
  - `American Encyclopaedia` (0, the text uses the æ ligature) was never a phrase, but
    question 8 was reworded to "the encyclopaedia entry" so the question text is accurate.
  - `a more advanced age and a longer term of citizenship` (0, the text says "longer
    period of citizenship") became `A senator must be thirty years of age at least`.
  - `the unique representation of a subject engaged in an online transaction` (3:
    executive summary, Section 2, Section 4.1) was swapped for `Identity proofing
    establishes that a subject is who they claim to be` (2) to keep the gold set tight.
  - Rejected for frequency: `K. K. K.` (6), `Lone Star` (6), `a cheetah and a baboon` (3),
    `great body of the people` (12), `Montesquieu` (12), `Hosmer Angel` (17).
- Replaying the questions through `POST /api/ask` is a reasonable smoke test of the
  generation path, but the numbers in `results.json` are retrieval numbers only.
