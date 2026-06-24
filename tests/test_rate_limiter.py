"""Tests for the shared rate limiter."""

import time
import threading
import pytest
from testudo.rate_limiter import RateLimiter


def test_single_acquire_is_immediate():
    limiter = RateLimiter(rate=5.0)
    start = time.monotonic()
    limiter.acquire()
    assert time.monotonic() - start < 0.1


def test_acquires_are_rate_limited():
    # 5 acquires at 10/sec, starting empty, should take ~ (5-1)/10 = 0.4s
    limiter = RateLimiter(rate=10.0, capacity=1)
    start = time.monotonic()
    for _ in range(5):
        limiter.acquire()
    elapsed = time.monotonic() - start
    assert 0.3 < elapsed < 0.7


def test_concurrent_acquires_respect_rate():
    # 10 tokens across 5 threads at 10/sec, capacity 1 -> ~0.9s, no deadlock
    limiter = RateLimiter(rate=10.0, capacity=1)
    counter = {"n": 0}
    lock = threading.Lock()

    def worker():
        for _ in range(2):
            limiter.acquire()
            with lock:
                counter["n"] += 1

    threads = [threading.Thread(target=worker) for _ in range(5)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    elapsed = time.monotonic() - start
    assert counter["n"] == 10
    assert 0.6 < elapsed < 1.5
