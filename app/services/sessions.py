"""Visitor sessions: a cookie id that scopes uploads, with an idle TTL.

Uploads are stored only under the session's scope; ``sweep`` deletes the scopes of
sessions idle for longer than the TTL, and ``purge_all`` removes every non-preloaded
scope (run at startup, so visitor documents never survive a restart).
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from collections.abc import Callable

from fastapi import Request, Response

from app.ingestion.store import SqliteStore

COOKIE_NAME = "ttyd_session"
PRELOADED_SCOPE = "preloaded"
_SESSION_ID = re.compile(r"[0-9a-f]{32}")


def is_https(request: Request | None) -> bool:
    if request is None:
        return False
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto.split(",")[0].strip().lower() == "https"


class SessionManager:
    """Tracks the last activity of each session id; ``clock`` is monotonic seconds."""

    def __init__(self, ttl_minutes: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl = int(ttl_minutes) * 60
        self.clock = clock
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def new_id() -> str:
        return secrets.token_hex(16)

    # -- request plumbing ---------------------------------------------------

    def resolve(self, request: Request) -> tuple[str, bool]:
        """``(session_id, is_new)``. A well-formed cookie is honoured even when the
        server has not seen it (after a restart); anything else gets a fresh id."""
        raw = request.cookies.get(COOKIE_NAME, "")
        if _SESSION_ID.fullmatch(raw):
            self.touch(raw)
            return raw, False
        sid = self.new_id()
        self.touch(sid)
        return sid, True

    def set_cookie(self, response: Response, session_id: str, request: Request | None = None) -> None:
        response.set_cookie(
            COOKIE_NAME,
            session_id,
            max_age=self.ttl,
            path="/",
            httponly=True,
            samesite="lax",
            secure=is_https(request),
        )

    def get_or_create(self, request: Request, response: Response) -> str:
        """The request's session id, touched; the cookie is (re)set on every response
        so its expiry in the browser tracks the idle TTL on the server."""
        sid, _ = self.resolve(request)
        self.set_cookie(response, sid, request)
        return sid

    # -- bookkeeping --------------------------------------------------------

    def touch(self, session_id: str) -> None:
        with self._lock:
            self._last_seen[session_id] = self.clock()

    def forget(self, session_id: str) -> None:
        with self._lock:
            self._last_seen.pop(session_id, None)

    def active(self) -> int:
        with self._lock:
            return len(self._last_seen)

    def expired(self) -> list[str]:
        now = self.clock()
        with self._lock:
            return [sid for sid, seen in self._last_seen.items() if now - seen > self.ttl]

    def sweep(self, store: SqliteStore) -> int:
        """Delete the documents of every expired session; returns the document count."""
        deleted = 0
        for sid in self.expired():
            deleted += store.delete_scope(sid)
            self.forget(sid)
        return deleted


def purge_all(store: SqliteStore) -> int:
    """Delete every document that is not preloaded; returns the document count."""
    scopes = [
        row[0]
        for row in store.conn.execute(
            "SELECT DISTINCT scope FROM documents WHERE scope != ?", (PRELOADED_SCOPE,)
        ).fetchall()
    ]
    return sum(store.delete_scope(scope) for scope in scopes)
