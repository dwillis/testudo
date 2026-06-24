"""Tests for parallel department-level scraping orchestration."""

from unittest.mock import patch
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
