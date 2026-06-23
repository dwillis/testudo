# Threaded Department-Level Scraping with a Shared Rate Limiter

Date: 2026-06-23

## Problem

`TestudoScraper.scrape_full` walks terms → departments → courses sequentially.
For every course it fetches sections over HTTP and then sleeps
`request_delay` (default 1.0s) to be polite (`parser.py` `get_sections`).
A full scrape is therefore I/O-bound and slow, dominated by sequential
network round-trips plus the fixed inter-request delay.

## Goal

Scrape departments concurrently so network latency overlaps, while keeping
the *total* request rate against UMD's Testudo server bounded by a single
shared rate limiter — politeness should depend on a global rate budget, not
on the number of worker threads.

## Decisions

- **Global rate budget:** ~5 requests/sec total, enforced by one shared
  token-bucket limiter regardless of worker count.
- **Default workers:** 8 (overridable via CLI).
- **Scope:** Only `scrape_full` (loops departments) is parallelized.
  `scrape_department` and `scrape_test` are unchanged.

## Architecture

### `RateLimiter` (new — `testudo/rate_limiter.py`)

Thread-safe token bucket.

- Constructed with `rate` (tokens/sec) and optional `capacity` (burst).
- `acquire()` blocks until a token is available, then consumes one.
- Internally guarded by a `threading.Lock`; refills based on elapsed wall
  time. A single instance is shared by all worker parsers, so total request
  rate is capped globally.

### Parser changes (`testudo/parser.py`)

- `TestudoParser.__init__` takes an optional `rate_limiter`.
- Introduce a `_throttle()` helper called before each outbound
  `self.session.get(...)` (in `get_courses` and `get_sections`):
  - if a `rate_limiter` is set → `rate_limiter.acquire()`
  - else → fall back to `time.sleep(config.request_delay)` (preserves
    today's sequential behavior and existing tests).
- The current `time.sleep` at the end of `get_sections` is replaced by this
  throttle-before-request model.

Each worker thread constructs its **own** `TestudoParser` (own
`HTMLSession`, own `_syllabus_cache`) because `requests_html` sessions and
the cache dict are not thread-safe. All workers share the one `RateLimiter`.

### Thread-safe stats

`ScrapingStats` counters are mutated per course. Each worker accumulates a
**local** `ScrapingStats`; on completion the orchestrator merges locals into
the main stats. Merge happens in the main thread as futures complete, so no
lock is needed on the shared object. Add a `merge(other)` helper to
`ScrapingStats`.

### `scrape_full` orchestration (`testudo/scraper.py`)

- Build one shared `RateLimiter(rate=config.requests_per_second)`.
- For each term, list departments (single request, main thread).
- Use `concurrent.futures.ThreadPoolExecutor(max_workers=config.workers)`.
  Submit one task per department. Each task:
  - builds its own `TestudoParser(config, rate_limiter=limiter)`,
  - scrapes the department into a local `ScrapingStats`,
  - saves course JSON (already isolated per-dept path, no contention),
  - returns `(dept_id, local_stats, error_or_None)`.
- As futures complete, merge stats and log per-dept completion.
- `--workers 1` skips the executor and runs the existing sequential path
  (useful for debugging and to guarantee backward compatibility).

### Config / CLI

- `ScraperConfig`: add `workers: int = 8` and
  `requests_per_second: float = 5.0`.
- `cli.py`: add `--workers N` (default 8) and `--rate N` (default 5.0).

## Error handling

- A failing department is caught inside its worker, logged, and reported via
  the returned error marker; it does not cancel the pool. The term
  continues with the remaining departments.
- `KeyboardInterrupt` cancels outstanding futures and shuts the executor
  down cleanly, then prints partial stats.

## Testing (TDD)

- `RateLimiter`:
  - N acquires at rate R take ~ (N-1)/R seconds (timing assertion with
    tolerance).
  - Concurrent acquires from multiple threads never exceed the rate and
    don't deadlock.
- `ScrapingStats.merge`: counters sum correctly.
- Scraper orchestration: with a mocked parser (no real HTTP), `scrape_full`
  fans out across departments, merges stats, and a failure in one
  department doesn't abort the others.

## Out of scope (YAGNI)

- Parallelizing within a single department (course-level threading).
- Async/await rewrite — threads are sufficient for this I/O-bound workload.
- Parallelizing the JSON→SQLite loader (`load_specific_terms.py`); SQLite is
  single-writer and that stage is not the bottleneck.
