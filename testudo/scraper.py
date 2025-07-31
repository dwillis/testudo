"""Main scraper class for orchestrating the scraping process."""

import os
import json
import time
import logging
from typing import Optional, List
from pathlib import Path

from .config import ScraperConfig
from .models import Department, Course, ScrapingStats
from .parser import TestudoParser

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
        """Run a full scrape of all departments."""
        terms = self.parser.get_terms(active_only=True, term=term)
        
        for term in terms:
            logger.info(f"Starting scrape for term {term}")
            term_start = time.time()
            
            try:
                departments = self.parser.get_departments()
                logger.info(f"Found {len(departments)} departments to process")
                
                for i, dept in enumerate(departments, 1):
                    self._scrape_department(dept, term, i, len(departments))
                    
            except Exception as e:
                logger.error(f"Error processing term {term}: {e}")
                continue
            
            term_time = time.time() - term_start
            logger.info(f"Completed term {term} in {term_time:.1f}s")
    
    def _scrape_department(self, dept: Department, term: str, dept_num: int, total_depts: int) -> None:
        """Scrape a single department."""
        dept_start = time.time()
        logger.info(f"Processing department {dept_num}/{total_depts}: {dept.id} - {dept.name}")
        
        dept_courses = 0
        dept_failed = 0
        
        try:
            for course in self.parser.get_courses(dept, term):
                self.stats.total_courses += 1
                
                if course:
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
        
        except Exception as e:
            logger.error(f"Error processing department {dept.id}: {e}")
        
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
    
    def print_stats(self) -> None:
        """Print final statistics."""
        logger.info(f"Scraping completed in {self.stats.elapsed_time:.1f}s")
        logger.info(f"Departments processed: {self.stats.departments_processed}")
        logger.info(f"Total courses processed: {self.stats.total_courses}")
        logger.info(f"Successful: {self.stats.successful_courses}")
        logger.info(f"Failed: {self.stats.failed_courses}")
        logger.info(f"Success rate: {self.stats.success_rate:.1f}%")
