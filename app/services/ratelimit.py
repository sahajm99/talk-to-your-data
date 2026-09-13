"""Rate limiting: a sliding window per client address plus a global UTC-daily cap."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, date, datetime


def _utc_today() -> date:
    return datetime.now(UTC).date()


class RateLimiter:
    """``check(ip)`` answers ``(allowed, reason)``.

    Per address: at most ``limit`` questions in any ``window_seconds``. Globally: at
    most ``daily_cap`` questions per UTC day. Refused requests are not counted.
    ``clock`` (monotonic seconds) and ``today`` (UTC date) are injectable for tests.
    A limit or cap of 0 or less disables that check.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        daily_cap: int,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] | None = None,
    ) -> None:
        self.limit = int(limit)
        self.window = float(window_seconds)
        self.daily_cap = int(daily_cap)
        self.clock = clock
        self.today = today or _utc_today
        self._hits: dict[str, deque[float]] = {}
        self._day: date = self.today()
        self._day_count = 0
        self._checks = 0
        self._lock = threading.Lock()

    # -- public -------------------------------------------------------------

    def check(self, ip: str) -> tuple[bool, str]:
        now = self.clock()
        with self._lock:
            self._roll_day()
            if self.daily_cap > 0 and self._day_count >= self.daily_cap:
                return False, (
                    f"the site's daily limit of {self.daily_cap:,} questions has been reached"
                )
            q = self._window_for(ip, now)
            if self.limit > 0 and len(q) >= self.limit:
                return False, f"{self.limit} questions per {self.window_label()} reached"
            q.append(now)
            self._day_count += 1
            self._checks += 1
            if self._checks % 256 == 0:
                self._prune(now)
            return True, ""

    def retry_after(self, ip: str) -> int:
        """Seconds until ``ip`` may ask again (0 when it may ask now)."""
        now = self.clock()
        with self._lock:
            self._roll_day()
            if self.daily_cap > 0 and self._day_count >= self.daily_cap:
                midnight = datetime.combine(self.today(), datetime.min.time(), tzinfo=UTC)
                seconds = 86_400 - (datetime.now(UTC) - midnight).total_seconds()
                return max(1, int(seconds))
            q = self._window_for(ip, now)
            if self.limit <= 0 or len(q) < self.limit:
                return 0
            return max(1, int(q[0] + self.window - now) + 1)

    def daily_used(self) -> int:
        with self._lock:
            self._roll_day()
            return self._day_count

    def window_label(self) -> str:
        secs = int(self.window)
        if secs % 3600 == 0:
            n = secs // 3600
            return f"{n} hour" + ("" if n == 1 else "s")
        if secs % 60 == 0:
            n = secs // 60
            return f"{n} minute" + ("" if n == 1 else "s")
        return f"{secs} seconds"

    # -- internals ----------------------------------------------------------

    def _roll_day(self) -> None:
        today = self.today()
        if today != self._day:
            self._day = today
            self._day_count = 0

    def _window_for(self, ip: str, now: float) -> deque[float]:
        q = self._hits.get(ip)
        if q is None:
            q = self._hits[ip] = deque()
        cutoff = now - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        for ip in [ip for ip, q in self._hits.items() if not q or q[-1] <= cutoff]:
            del self._hits[ip]
