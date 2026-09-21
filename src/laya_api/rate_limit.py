from __future__ import annotations

import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, rpm: int) -> None:
        self.rpm = max(1, int(rpm))
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        window = self._hits[key]
        cutoff = now - 60.0
        window[:] = [t for t in window if t > cutoff]
        if len(window) >= self.rpm:
            retry_after = max(1, int(60 - (now - window[0])) + 1)
            return False, retry_after
        window.append(now)
        return True, 0
