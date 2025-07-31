"""HTML parsing functions for the testudo scraper."""

import re
import datetime
import logging
from typing import List, Optional, Generator
from requests_html import HTMLSession, Element

from .models import Course, Section, Department
from .utils import retry_on_failure, safe_int, safe_text, validate_course_id, determine_course_level
from .config import ScraperConfig

logger = logging.getLogger(__name__)

class TestudoParser:
    """Parser for testudo course data."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.session = HTMLSession()
        self.session.headers['user-agent'] = config.user_agent
    
    @retry_on_failure(max_retries=3, base_delay=1.0)
    def get_terms(self, active_only: bool = True, term: Optional[str] = None) -> List[str]:
        """Get available terms from the website."""
        url = f"{self.config.base_url}/"
        logger.info(f"Fetching terms from {url}")
        
        r = self.session.get(url)
        r.raise_for_status()
        
        if term:
            return [term]
        
        terms = []
        for e in r.html.find('#term-id-input option'):
            if 'value' in e.attrs:
                terms.append(e.attrs['value'])
        
        logger.info(f"Found {len(terms)} terms")
        return terms
    
    @retry_on_failure(max_retries=3, base_delay=1.0)
    def get_departments(self) -> List[Department]:
        """Get all departments from the website."""
        url = f"{self.config.base_url}/"
        logger.info(f"Fetching departments from {url}")
        
        r = self.session.get(url)
        r.raise_for_status()
        
        departments = []
        for div in r.html.find('.course-prefix'):
            try:
                dept_id = safe_text(div, '.prefix-abbrev')
                dept_name = safe_text(div, '.prefix-name')
                
                if dept_id and dept_name:
                    departments.append(Department(id=dept_id, name=dept_name))
                    
            except (AttributeError, TypeError) as e:
                logger.warning(f"Could not parse department from div: {e}")
                continue
        
        logger.info(f"Found {len(departments)} departments")
        return departments
    
    @retry_on_failure(max_retries=3, base_delay=1.0)
    def get_courses(self, department: Department, term: str) -> Generator[Course, None, None]:
        """Get all courses for a department and term."""
        url = f"{self.config.base_url}/{term}/{department.id}"
        logger.info(f"Fetching courses from {url}")
        
        try:
            r = self.session.get(url)
            r.raise_for_status()
            
            course_divs = r.html.find('.course')
            logger.info(f"Found {len(course_divs)} courses for {department.id}")
            
            for div in course_divs:
                try:
                    course = self._parse_course(department, term, div)
                    if course:
                        yield course
                except Exception as e:
                    logger.error(f"Error parsing course in {department.id}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to fetch courses for {department.id} in {term}: {e}")
            return
    
    def _parse_course(self, department: Department, term: str, div: Element) -> Optional[Course]:
        """Parse a single course from HTML."""
        try:
            # Extract and validate course ID
            course_id = safe_text(div, '.course-id')
            if not course_id or not validate_course_id(course_id):
                logger.warning(f"Invalid course ID: '{course_id}', skipping")
                return None
            
            # Extract and validate title
            title = safe_text(div, '.course-title')
            if not title:
                logger.warning(f"No title found for {course_id}, skipping")
                return None
            
            # Get other course data
            credits = safe_text(div, '.course-min-credits') or 'Unknown'
            description = safe_text(div, '.approved-course-text') or safe_text(div, '.course-text')
            level = determine_course_level(course_id)
            
            # Parse grading methods
            grading_text = safe_text(div, '.grading-method')
            grading_methods = []
            if grading_text:
                grading_methods = [method.strip() for method in grading_text.split(',') if method.strip()]
            
            # Parse syllabus count
            syllabus_count = self._parse_syllabus_count(div, course_id)
            
            # Extract most recent syllabus title
            most_recent_syllabus = self._extract_most_recent_syllabus(div, course_id)
            
            # Get sections
            sections = self.get_sections(course_id, term)
            
            return Course(
                id=course_id,
                title=title,
                credits=credits,
                description=description,
                level=level,
                grading_method=grading_methods,
                sections=sections,
                term=term,
                department=department.name,
                syllabus_count=syllabus_count,
                most_recent_syllabus=most_recent_syllabus,
                updated=datetime.datetime.utcnow().isoformat() + 'Z'
            )
            
        except Exception as e:
            logger.error(f"Unexpected error parsing course: {e}")
            return None
    
    def _parse_syllabus_count(self, div: Element, course_id: str) -> int:
        """Parse syllabus count from course div."""
        try:
            syllabus_spans = [d for d in div.find('span') if re.findall(r'\(\d+\)', d.text)]
            if syllabus_spans:
                syllabus_text = syllabus_spans[0].text
                if syllabus_text != '(0)':
                    match = re.search(r'\((\d+)\)', syllabus_text)
                    if match:
                        return int(match.group(1))
        except (IndexError, ValueError, AttributeError) as e:
            logger.warning(f"Could not parse syllabus count for {course_id}: {e}")
        return 0
    
    def _extract_most_recent_syllabus(self, div: Element, course_id: str) -> Optional[str]:
        """Extract the most recent syllabus title from course div using JavaScript rendering.
        
        This method attempts to click the syllabus toggle and extract semester/year patterns
        like 'Fall 2023', 'Spring 2025', '2023 Spring', '2024 Fall', etc.
        """
        try:
            # Check if there are syllabi to extract
            syllabus_count = self._parse_syllabus_count(div, course_id)
            if syllabus_count == 0:
                return None
            
            # Try to use the Playwright-based extractor if available
            try:
                from .syllabus_extractor import SyllabusExtractor
                # For now, we'll skip the browser automation in the main scraper
                # and just log that syllabi are available for later extraction
                logger.debug(f"Course {course_id} has {syllabus_count} syllabi available for extraction")
                return None
            except ImportError:
                logger.debug("Playwright not available - syllabus extraction disabled")
                return None
            
        except Exception as e:
            logger.warning(f"Could not extract syllabus for {course_id}: {e}")
            return None
    
    @retry_on_failure(max_retries=2, base_delay=0.5)
    def get_sections(self, course_id: str, term: str) -> List[Section]:
        """Get sections for a course."""
        sections = []
        
        try:
            url = f"{self.config.base_url}/{term}/sections?courseIds={course_id}"
            logger.debug(f"Fetching sections for {course_id} from {url}")
            
            r = self.session.get(url)
            r.raise_for_status()
            r.html.encoding = r.encoding
            
            section_divs = r.html.find('.section')
            logger.debug(f"Found {len(section_divs)} sections for {course_id}")
            
            for div in section_divs:
                try:
                    section_id = safe_text(div, '.section-id')
                    if not section_id:
                        logger.warning(f"Section with no ID found for {course_id}")
                        continue
                    
                    # Parse instructors
                    instructors = []
                    for e in div.find('.section-instructor'):
                        if e.text and e.text.strip():
                            instructors.append(e.text.strip())
                    
                    section = Section(
                        id=section_id,
                        instructors=instructors,
                        seats=safe_int(safe_text(div, '.total-seats-count')),
                        open_seats=safe_int(safe_text(div, '.open-seats-count')),
                        waitlist=safe_int(safe_text(div, '.waitlist-count')),
                        days=safe_text(div, '.section-days'),
                        start=safe_text(div, '.class-start-time').strip(' -'),
                        end=safe_text(div, '.class-end-time'),
                        building=safe_text(div, '.building-code'),
                        room=safe_text(div, '.class-room'),
                    )
                    
                    sections.append(section)
                    
                except Exception as e:
                    logger.warning(f"Error parsing section for {course_id}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error getting sections for {course_id}: {e}")
        
        # Be nice and sleep between requests
        if self.config.request_delay:
            import time
            time.sleep(self.config.request_delay)
        
        logger.debug(f"Successfully parsed {len(sections)} sections for {course_id}")
        return sections
