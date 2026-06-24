"""Thread-safe token-bucket rate limiter shared across scraper workers."""

import time
import threading


class RateLimiter:
    """Token bucket limiting the total request rate across all threads.

    A single instance is shared by every worker parser so that the
    aggregate request rate against the server stays bounded regardless of
    how many worker threads are running.
    """

    def __init__(self, rate: float, capacity: float = None):
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.rate = rate
        self.capacity = capacity if capacity is not None else max(1.0, rate)
        self._tokens = self.capacity  # start full: first request is immediate
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until a token is available, then consume one."""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._updated
                self._updated = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                # time until one token accrues
                wait = (1.0 - self._tokens) / self.rate
            time.sleep(wait)
