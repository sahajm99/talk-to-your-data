"""Answer generation: Groq when a key is configured, extractive otherwise."""

from __future__ import annotations

import html
import logging
import re
import threading
from dataclasses import dataclass, field

import httpx

from app.config import Settings
from app.ingestion.retrieval import Hit

log = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
EXTRACTIVE_LEAD = "Best-supported passage:"
NO_MATCH = "No passage in the selected documents matches this question."
SYSTEM_PROMPT = (
    "You answer questions using only the numbered passages you are given. "
    "Cite every claim with its passage number in square brackets, like [1] or [2]. "
    "If the passages do not contain the answer, reply exactly: The documents do not say. "
    "Answer in at most five sentences of plain text, no headings or lists."
)
_STOPWORDS = frozenset(
    "a an and are as at be but by can did do does for from had has have how i in into is it its "
    "not of on or so than that the their them then there these they this to was were what when "
    "where which who whom why will with would you your".split()
)


@dataclass
class Answer:
    text: str
    mode: str  # "groq" | "extractive"
    model: str | None = None
    cited: list[int] = field(default_factory=list)


def query_terms(question: str) -> list[str]:
    return sorted(
        {t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2 and t not in _STOPWORDS},
        key=len,
        reverse=True,
    )


def mark_terms(text: str, question: str) -> str:
    """HTML-escape ``text`` and wrap words starting with a query term in <mark>."""
    escaped = html.escape(text)
    terms = query_terms(question)
    if not terms:
        return escaped
    pattern = re.compile(r"(?<![&#\w])(" + "|".join(map(re.escape, terms)) + r")\w*", re.IGNORECASE)
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped)


def extractive_answer(question: str, hits: list[Hit]) -> Answer:
    if not hits:
        return Answer(NO_MATCH, "extractive")
    return Answer(f"{EXTRACTIVE_LEAD} {mark_terms(hits[0].chunk.text, question)} [1]", "extractive", None, [1])


class GroqGenerator:
    """Grounded generation over Groq's OpenAI-compatible API. The model is chosen from
    the live model list on first use, because Groq retires free models without notice."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._model: str | None = None
        self._lock = threading.Lock()
        self._client = httpx.Client(
            base_url=GROQ_BASE_URL,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            timeout=20.0,
            transport=transport,
        )

    @property
    def cached_model(self) -> str | None:
        return self._model

    def model(self) -> str:
        with self._lock:
            if self._model is None:
                resp = self._client.get("/models")
                resp.raise_for_status()
                ids = [m["id"] for m in resp.json().get("data", [])]
                preferred = [self.settings.groq_model, self.settings.groq_fallback_model]
                chosen = next((m for m in preferred if m in ids), None)
                if chosen is None:
                    chosen = next((m for m in ids if "gpt-oss" in m or "llama" in m), None)
                self._model = chosen or self.settings.groq_model
                log.info("Groq model selected: %s", self._model)
            return self._model

    def generate(self, question: str, hits: list[Hit]) -> Answer:
        model = self.model()
        passages = "\n\n".join(
            f"[{i}] ({h.chunk.doc_title}, passage {h.chunk.idx + 1})\n{h.chunk.text}"
            for i, h in enumerate(hits, start=1)
        )
        payload: dict = {
            "model": model,
            "temperature": 0.1,
            "max_completion_tokens": 900,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Passages:\n\n{passages}\n\nQuestion: {question}"},
            ],
        }
        if "gpt-oss" in model:
            payload["reasoning_effort"] = "low"
        resp = self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
        if not text:
            raise ValueError("empty completion")
        cited = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", text) if 1 <= int(n) <= len(hits)})
        return Answer(text, "groq", model, cited)


_generator: GroqGenerator | None = None
_generator_lock = threading.Lock()


def get_generator(settings: Settings) -> GroqGenerator | None:
    global _generator
    if not settings.groq_api_key:
        return None
    with _generator_lock:
        if _generator is None:
            _generator = GroqGenerator(settings)
        return _generator


def generation_status(settings: Settings) -> tuple[str, str | None]:
    gen = get_generator(settings)
    return ("groq", gen.cached_model) if gen else ("extractive", None)


def answer(question: str, hits: list[Hit], settings: Settings) -> Answer:
    gen = get_generator(settings)
    if gen is not None and hits:
        try:
            return gen.generate(question, hits)
        except Exception as exc:  # network, quota, retired model: never a dead demo
            log.warning("Groq generation failed, answering extractively: %s", exc)
    return extractive_answer(question, hits)
