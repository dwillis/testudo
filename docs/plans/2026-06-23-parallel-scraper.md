# Threaded Department-Level Scraping Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Parallelize `TestudoScraper.scrape_full` across departments using a thread pool, with a single shared token-bucket rate limiter capping total request rate (~5 req/sec) regardless of worker count.

**Architecture:** A new thread-safe `RateLimiter` (token bucket) is shared by all worker threads. Each worker builds its own `TestudoParser` (own non-thread-safe `HTMLSession`) and accumulates a local `ScrapingStats` that is merged into the main stats as futures complete. A `_throttle()` hook in the parser calls the limiter when present and falls back to `time.sleep(request_delay)` otherwise (preserving sequential behavior).

**Tech Stack:** Python 3.9+, `concurrent.futures.ThreadPoolExecutor`, `threading.Lock`, `requests_html`, `pytest`.

Run tests with `uv run pytest` (project uses `uv`).

---

### Task 1: RateLimiter token bucket

**Files:**
- Create: `testudo/rate_limiter.py`
- Test: `tests/test_rate_limiter.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rate_limiter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'testudo.rate_limiter'`

**Step 3: Write minimal implementation**

```python
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
        self._tokens = 0.0  # start empty so the first burst is also throttled
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
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rate_limiter.py -v`
Expected: PASS (3 passed)

**Step 5: Commit**

```bash
git add testudo/rate_limiter.py tests/test_rate_limiter.py
git commit -m "feat: add thread-safe token-bucket RateLimiter"
```

---

### Task 2: ScrapingStats.merge

**Files:**
- Modify: `testudo/models.py` (ScrapingStats, after `elapsed_time`)
- Test: `tests/test_testudo.py` (add a `TestScrapingStats` class)

**Step 1: Write the failing test**

Add to `tests/test_testudo.py`:

```python
class TestScrapingStats:
    """Test ScrapingStats merging for parallel workers."""

    def test_merge_sums_counters(self):
        from testudo import ScrapingStats
        a = ScrapingStats(start_time=0.0, total_courses=3,
                          successful_courses=2, failed_courses=1,
                          departments_processed=1)
        b = ScrapingStats(start_time=0.0, total_courses=5,
                          successful_courses=5, failed_courses=0,
                          departments_processed=1)
        a.merge(b)
        assert a.total_courses == 8
        assert a.successful_courses == 7
        assert a.failed_courses == 1
        assert a.departments_processed == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_testudo.py::TestScrapingStats -v`
Expected: FAIL with `AttributeError: 'ScrapingStats' object has no attribute 'merge'`

**Step 3: Write minimal implementation**

Add to `ScrapingStats` in `testudo/models.py`:

```python
    def merge(self, other: "ScrapingStats") -> None:
        """Add another stats object's counters into this one."""
        self.total_courses += other.total_courses
        self.successful_courses += other.successful_courses
        self.failed_courses += other.failed_courses
        self.departments_processed += other.departments_processed
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_testudo.py::TestScrapingStats -v`
Expected: PASS

**Step 5: Commit**

```bash
git add testudo/models.py tests/test_testudo.py
git commit -m "feat: add ScrapingStats.merge for combining worker stats"
```

---

### Task 3: Config options

**Files:**
- Modify: `testudo/config.py` (ScraperConfig dataclass)
- Test: `tests/test_testudo.py` (TestScraperConfig)

**Step 1: Write the failing test**

Add to `TestScraperConfig` in `tests/test_testudo.py`:

```python
    def test_parallel_defaults(self):
        config = ScraperConfig()
        assert config.workers == 8
        assert config.requests_per_second == 5.0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_testudo.py::TestScraperConfig::test_parallel_defaults -v`
Expected: FAIL with `AttributeError: 'ScraperConfig' object has no attribute 'workers'`

**Step 3: Write minimal implementation**

In `testudo/config.py`, add two fields to `ScraperConfig` (after `extract_syllabi`):

```python
    workers: int = 8                      # worker threads for full scrape
    requests_per_second: float = 5.0      # global request-rate cap
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_testudo.py::TestScraperConfig -v`
Expected: PASS

**Step 5: Commit**

```bash
git add testudo/config.py tests/test_testudo.py
git commit -m "feat: add workers and requests_per_second config options"
```

---

### Task 4: Parser throttle hook

**Files:**
- Modify: `testudo/parser.py` (`__init__`, `get_courses`, `get_sections`)
- Test: `tests/test_parser_throttle.py`

**Step 1: Write the failing test**

```python
"""Tests for the parser's throttle hook."""

from unittest.mock import MagicMock
from testudo import ScraperConfig, TestudoParser


def test_throttle_uses_rate_limiter_when_present():
    limiter = MagicMock()
    parser = TestudoParser(ScraperConfig(request_delay=0.0), rate_limiter=limiter)
    parser._throttle()
    limiter.acquire.assert_called_once()


def test_throttle_falls_back_to_sleep(monkeypatch):
    calls = []
    monkeypatch.setattr("testudo.parser.time.sleep", lambda s: calls.append(s))
    parser = TestudoParser(ScraperConfig(request_delay=0.7))
    parser._throttle()
    assert calls == [0.7]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parser_throttle.py -v`
Expected: FAIL — `TestudoParser.__init__` has no `rate_limiter` param / no `_throttle`.

**Step 3: Write minimal implementation**

In `testudo/parser.py`:

- Add `import time` at top (module-level; remove the local `import time` inside `get_sections`).
- Change `__init__` signature:

```python
    def __init__(self, config: ScraperConfig, rate_limiter=None):
        self.config = config
        self.rate_limiter = rate_limiter
        self.session = HTMLSession()
        self.session.headers['user-agent'] = config.user_agent
        self._syllabus_cache = {}  # Cache syllabus results per department
```

- Add the helper method:

```python
    def _throttle(self) -> None:
        """Pace outbound requests: shared limiter if set, else fixed delay."""
        if self.rate_limiter is not None:
            self.rate_limiter.acquire()
        elif self.config.request_delay:
            time.sleep(self.config.request_delay)
```

- In `get_sections`, replace the trailing block:

```python
        # Be nice and sleep between requests
        if self.config.request_delay:
            import time
            time.sleep(self.config.request_delay)
```

with nothing, and instead call `self._throttle()` immediately **before** the
section request (just before `r = self.session.get(url)` in `get_sections`).

- In `get_courses`, call `self._throttle()` immediately before
  `r = self.session.get(url)`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_parser_throttle.py -v`
Expected: PASS

Also run the full suite to confirm no regressions:
Run: `uv run pytest -v`
Expected: PASS (all existing tests still green)

**Step 5: Commit**

```bash
git add testudo/parser.py tests/test_parser_throttle.py
git commit -m "feat: add throttle hook to parser (rate limiter or delay)"
```

---

### Task 5: Parallel scrape_full orchestration

**Files:**
- Modify: `testudo/scraper.py` (`scrape_full`, `_scrape_department`, imports)
- Test: `tests/test_parallel_scrape.py`

**Step 1: Write the failing test**

```python
"""Tests for parallel department-level scraping orchestration."""

from unittest.mock import patch, MagicMock
from testudo import TestudoScraper, ScraperConfig, Department


def _make_scraper(workers):
    config = ScraperConfig(workers=workers, request_delay=0.0,
                           requests_per_second=1000.0)
    return TestudoScraper(config)


def test_scrape_full_fans_out_over_departments():
    scraper = _make_scraper(workers=4)
    depts = [Department(id=f"D{i}", name=f"Dept {i}") for i in range(6)]
    seen = []

    def fake_scrape_one(dept, term, limiter):
        from testudo.models import ScrapingStats
        seen.append(dept.id)
        s = ScrapingStats(start_time=0.0, total_courses=1,
                          successful_courses=1, departments_processed=1)
        return (dept.id, s, None)

    with patch.object(scraper.parser, "get_terms", return_value=["202508"]), \
         patch.object(scraper.parser, "get_departments", return_value=depts), \
         patch.object(scraper, "_scrape_department_worker", side_effect=fake_scrape_one):
        scraper.scrape_full(term="202508")

    assert sorted(seen) == [d.id for d in depts]
    assert scraper.stats.successful_courses == 6
    assert scraper.stats.departments_processed == 6


def test_one_failing_department_does_not_abort_others():
    scraper = _make_scraper(workers=4)
    depts = [Department(id=f"D{i}", name=f"Dept {i}") for i in range(4)]

    def fake_scrape_one(dept, term, limiter):
        from testudo.models import ScrapingStats
        if dept.id == "D1":
            return (dept.id, ScrapingStats(start_time=0.0), RuntimeError("boom"))
        s = ScrapingStats(start_time=0.0, successful_courses=1,
                          departments_processed=1)
        return (dept.id, s, None)

    with patch.object(scraper.parser, "get_terms", return_value=["202508"]), \
         patch.object(scraper.parser, "get_departments", return_value=depts), \
         patch.object(scraper, "_scrape_department_worker", side_effect=fake_scrape_one):
        scraper.scrape_full(term="202508")

    # 3 successful departments still counted despite D1 failing
    assert scraper.stats.successful_courses == 3
    assert scraper.stats.departments_processed == 3
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parallel_scrape.py -v`
Expected: FAIL — `_scrape_department_worker` does not exist; `scrape_full` not parallel.

**Step 3: Write minimal implementation**

In `testudo/scraper.py`:

- Add imports near the top:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from .rate_limiter import RateLimiter
```

- Replace `scrape_full` with:

```python
    def scrape_full(self, term: Optional[str] = None) -> None:
        """Run a full scrape of all departments (threaded across departments)."""
        terms = self.parser.get_terms(active_only=True, term=term)

        for term in terms:
            logger.info(f"Starting scrape for term {term}")
            term_start = time.time()

            try:
                departments = self.parser.get_departments()
                logger.info(f"Found {len(departments)} departments to process")
            except Exception as e:
                logger.error(f"Error processing term {term}: {e}")
                continue

            if self.config.workers <= 1:
                for i, dept in enumerate(departments, 1):
                    self._scrape_department(dept, term, i, len(departments))
            else:
                self._scrape_term_parallel(departments, term)

            term_time = time.time() - term_start
            logger.info(f"Completed term {term} in {term_time:.1f}s")

    def _scrape_term_parallel(self, departments, term: str) -> None:
        """Scrape all departments for a term using a thread pool."""
        limiter = RateLimiter(rate=self.config.requests_per_second)
        total = len(departments)
        completed = 0

        with ThreadPoolExecutor(max_workers=self.config.workers) as executor:
            futures = {
                executor.submit(self._scrape_department_worker, dept, term, limiter): dept
                for dept in departments
            }
            try:
                for future in as_completed(futures):
                    dept = futures[future]
                    completed += 1
                    dept_id, local_stats, error = future.result()
                    if error is not None:
                        logger.error(f"Department {dept_id} failed: {error}")
                    self.stats.merge(local_stats)
                    logger.info(
                        f"Completed {completed}/{total}: {dept_id} "
                        f"({local_stats.successful_courses} courses)"
                    )
            except KeyboardInterrupt:
                logger.warning("Interrupted; cancelling remaining departments...")
                for f in futures:
                    f.cancel()
                raise

    def _scrape_department_worker(self, dept: Department, term: str, limiter: RateLimiter):
        """Worker: scrape one department with its own parser and local stats."""
        from .parser import TestudoParser
        local_stats = ScrapingStats(start_time=time.time())
        parser = TestudoParser(self.config, rate_limiter=limiter)
        try:
            for course in parser.get_courses(dept, term):
                local_stats.total_courses += 1
                if course and self._save_course(course, term):
                    local_stats.successful_courses += 1
                else:
                    local_stats.failed_courses += 1
            local_stats.departments_processed += 1
            return (dept.id, local_stats, None)
        except Exception as e:
            return (dept.id, local_stats, e)
```

Note: `_scrape_department` (sequential path) and `_save_course` stay as-is.
`_save_course` writes to a per-department path, so concurrent workers never
write the same file.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_parallel_scrape.py -v`
Expected: PASS (2 passed)

Full suite:
Run: `uv run pytest -v`
Expected: PASS

**Step 5: Commit**

```bash
git add testudo/scraper.py tests/test_parallel_scrape.py
git commit -m "feat: parallelize scrape_full across departments with shared rate limiter"
```

---

### Task 6: Wire CLI flags

**Files:**
- Modify: `cli.py` (argparse + ScraperConfig construction)

**Step 1: Write the failing test**

Add `tests/test_cli_args.py`:

```python
"""Tests for CLI argument wiring."""

import sys
from unittest.mock import patch
import cli


def test_workers_and_rate_flow_into_config():
    captured = {}

    class FakeScraper:
        def __init__(self, config):
            captured["config"] = config
        def scrape_full(self, term=None):
            pass
        def print_stats(self):
            pass

    argv = ["prog", "--department", "CMSC", "--workers", "12", "--rate", "3.5"]
    with patch.object(sys, "argv", argv), \
         patch.object(cli, "TestudoScraper", FakeScraper):
        # --department path also exercises config construction
        try:
            cli.main()
        except SystemExit:
            pass

    assert captured["config"].workers == 12
    assert captured["config"].requests_per_second == 3.5
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_args.py -v`
Expected: FAIL — argparse rejects `--workers` (unrecognized arguments) → SystemExit before scraper built, so `captured` is empty → KeyError/assertion fails.

**Step 3: Write minimal implementation**

In `cli.py`, add arguments (near `--delay`):

```python
    parser.add_argument(
        '--workers',
        type=int,
        default=8,
        help='Number of worker threads for full scrape (default: 8, 1 = sequential)'
    )

    parser.add_argument(
        '--rate',
        type=float,
        default=5.0,
        help='Max total requests per second across workers (default: 5.0)'
    )
```

And pass them into the `ScraperConfig(...)` constructor:

```python
    config = ScraperConfig(
        data_dir=args.data_dir,
        request_delay=args.delay,
        log_level=log_level,
        extract_syllabi=args.extract_syllabi,
        workers=args.workers,
        requests_per_second=args.rate
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_args.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli.py tests/test_cli_args.py
git commit -m "feat: add --workers and --rate CLI flags"
```

---

### Task 7: Final verification

**Step 1: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS (all tests, including pre-existing ones)

**Step 2: Smoke-test the sequential path is unaffected**

Run: `uv run python cli.py --help`
Expected: help text shows `--workers` and `--rate`.

**Step 3: Update README scraping/usage section**

Document `--workers` and `--rate` in `README.md` where CLI usage is described
(add a short "Parallel scraping" note: default 8 workers, ~5 req/sec global
cap, `--workers 1` for sequential). Keep it brief.

**Step 4: Commit docs**

```bash
git add README.md
git commit -m "docs: document parallel scraping flags"
```
