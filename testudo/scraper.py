"""Main scraper class for orchestrating the scraping process."""

import os
import json
import time
import datetime
import logging
from typing import Optional, List, Set
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import ScraperConfig
from .models import Department, Course, ScrapingStats
from .parser import TestudoParser
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

class TestudoScraper:
    """Main scraper class for University of Maryland course data."""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.parser = TestudoParser(self.config)
        self.stats = ScrapingStats(start_time=time.time())
    
    def scrape_test(self, department_id: Optional[str] = None, term: Optional[str] = None) -> None:
        """Run a test scrape of a single department."""
        dept_id = department_id or self.config.test_department
        term = term or self.config.default_term
        
        logger.info(f"Test mode: only scraping department {dept_id}")
        logger.info(f"Testing with term {term}")
        
        try:
            departments = self.parser.get_departments()
            dept = next((d for d in departments if d.id == dept_id), None)
            
            if not dept:
                logger.error(f"Department {dept_id} not found")
                return
            
            logger.info(f"Testing department: {dept.name} ({dept.id})")
            
            course_count = 0
            for course in self.parser.get_courses(dept, term):
                self.stats.total_courses += 1  # Always count total courses processed
                
                if course:
                    course_count += 1
                    self.stats.successful_courses += 1
                    logger.info(f"Found course: {course.id} - {course.title}")
                    
                    if course_count >= self.config.test_max_courses:
                        logger.info(f"Test mode: stopping after {self.config.test_max_courses} courses")
                        break
                else:
                    self.stats.failed_courses += 1
                    
        except Exception as e:
            logger.error(f"Error in test mode: {e}")
    
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
        local_stats = ScrapingStats(start_time=time.time())
        parser = TestudoParser(self.config, rate_limiter=limiter)
        seen_ids: Set[str] = set()
        prefixes: Set[str] = set()
        try:
            for course in parser.get_courses(dept, term):
                local_stats.total_courses += 1
                if course:
                    seen_ids.add(course.id)
                    prefixes.add(course.id[:4])
                    if self._save_course(course, term):
                        local_stats.successful_courses += 1
                    else:
                        local_stats.failed_courses += 1
                else:
                    local_stats.failed_courses += 1
            # Reached only when the department scrape completed without error.
            local_stats.stale_flagged += self._flag_stale_courses(term, seen_ids, prefixes)
            local_stats.departments_processed += 1
            return (dept.id, local_stats, None)
        except Exception as e:
            return (dept.id, local_stats, e)
    
    def scrape_department(self, department_id: str, term: Optional[str] = None) -> None:
        """Scrape a single department."""
        term = term or self.config.default_term
        
        logger.info(f"Scraping department {department_id} for term {term}")
        
        try:
            departments = self.parser.get_departments()
            dept = next((d for d in departments if d.id == department_id), None)
            
            if not dept:
                logger.error(f"Department {department_id} not found")
                available_depts = [d.id for d in departments[:10]]  # Show first 10
                logger.info(f"Available departments (first 10): {', '.join(available_depts)}")
                return
            
            logger.info(f"Found department: {dept.name} ({dept.id})")
            self._scrape_department(dept, term, 1, 1)
            
        except Exception as e:
            logger.error(f"Error scraping department {department_id}: {e}")
    
    def _scrape_department(self, dept: Department, term: str, dept_num: int, total_depts: int) -> None:
        """Scrape a single department."""
        dept_start = time.time()
        logger.info(f"Processing department {dept_num}/{total_depts}: {dept.id} - {dept.name}")
        
        dept_courses = 0
        dept_failed = 0
        seen_ids: Set[str] = set()
        prefixes: Set[str] = set()
        completed = False

        try:
            for course in self.parser.get_courses(dept, term):
                self.stats.total_courses += 1

                if course:
                    # Track every course Testudo returned, independent of whether
                    # the write succeeded — a save failure is transient IO, not a
                    # signal that the course was dropped.
                    seen_ids.add(course.id)
                    prefixes.add(course.id[:4])
                    success = self._save_course(course, term)
                    if success:
                        self.stats.successful_courses += 1
                        dept_courses += 1
                    else:
                        self.stats.failed_courses += 1
                        dept_failed += 1
                else:
                    self.stats.failed_courses += 1
                    dept_failed += 1
            completed = True

        except Exception as e:
            logger.error(f"Error processing department {dept.id}: {e}")

        # Only reconcile when the department scrape ran to completion — a partial
        # or failed fetch must not flag still-offered courses as removed.
        if completed:
            self.stats.stale_flagged += self._flag_stale_courses(term, seen_ids, prefixes)

        dept_time = time.time() - dept_start
        logger.info(f"Completed {dept.id}: {dept_courses} courses, {dept_failed} failed in {dept_time:.1f}s")
        self.stats.departments_processed += 1
    
    def _save_course(self, course: Course, term: str) -> bool:
        """Save a course to a JSON file."""
        try:
            json_file = Path(self.config.data_dir) / term / course.id[:4] / f"{course.id}.json"
            json_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(json_file, 'w', encoding='utf-8') as f:
                f.write(course.to_json())
            
            logger.debug(f"Wrote {json_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing course {course.id}: {e}")
            return False

    def _flag_stale_courses(self, term: str, seen_ids: Set[str], prefixes: Set[str]) -> int:
        """Flag stored courses a department no longer offers this term.

        Diffs the course ids Testudo returned against the JSON files already on
        disk for the prefixes this department touched, and flags any leftover as
        no-longer-offered. Files are flagged in place, never deleted, so a dropped
        course keeps its history and can be surfaced on the site. A course that
        reappears is overwritten by ``_save_course`` with fresh JSON, which drops
        the flag automatically.

        Returns the number of files newly flagged.
        """
        # Guard: an empty result means the department returned nothing (a failed
        # or empty fetch). Flagging everything then would be a mass false positive.
        if not seen_ids:
            return 0

        flagged = 0
        for prefix in prefixes:
            dir_path = Path(self.config.data_dir) / term / prefix
            if not dir_path.is_dir():
                continue
            for json_file in dir_path.glob('*.json'):
                if json_file.stem in seen_ids:
                    continue
                if self._mark_no_longer_offered(json_file):
                    flagged += 1
        if flagged:
            logger.info(f"Flagged {flagged} no-longer-offered course(s) for term {term}")
        return flagged

    def _mark_no_longer_offered(self, json_file: Path) -> bool:
        """Add the no-longer-offered flag to a stored course file, in place.

        Preserves the existing content and only stamps the flag once, keeping the
        original detection timestamp on subsequent scrapes. Returns True if the
        file was newly flagged.
        """
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Could not read {json_file} for staleness check: {e}")
            return False

        if data.get('no_longer_offered'):
            return False  # already flagged; keep the original detection time

        data['no_longer_offered'] = True
        data['removed_detected'] = datetime.datetime.utcnow().isoformat() + 'Z'
        try:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Flagged no-longer-offered course: {json_file.name}")
            return True
        except Exception as e:
            logger.error(f"Could not flag {json_file}: {e}")
            return False

    def print_stats(self) -> None:
        """Print final statistics."""
        logger.info(f"Scraping completed in {self.stats.elapsed_time:.1f}s")
        logger.info(f"Departments processed: {self.stats.departments_processed}")
        logger.info(f"Total courses processed: {self.stats.total_courses}")
        logger.info(f"Successful: {self.stats.successful_courses}")
        logger.info(f"Failed: {self.stats.failed_courses}")
        logger.info(f"No longer offered (flagged): {self.stats.stale_flagged}")
        logger.info(f"Success rate: {self.stats.success_rate:.1f}%")
