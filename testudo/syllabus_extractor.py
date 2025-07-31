"""Syllabus extraction using browser automation."""

import re
import logging
from typing import Optional, List, Dict
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

class SyllabusExtractor:
    """Extracts syllabus information from course pages using browser automation."""
    
    def __init__(self, headless: bool = True, timeout: int = 10000):
        """Initialize the syllabus extractor.
        
        Args:
            headless: Whether to run browser in headless mode
            timeout: Timeout for page operations in milliseconds
        """
        self.headless = headless
        self.timeout = timeout
    
    def extract_syllabi_for_department(self, department_url: str) -> Dict[str, Optional[str]]:
        """Extract syllabi for all courses in a department.
        
        Args:
            department_url: URL of the department page (e.g., https://app.testudo.umd.edu/soc/202508/CMSC)
            
        Returns:
            Dictionary mapping course IDs to their most recent syllabus titles
        """
        results = {}
        
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page()
                
                logger.info(f"Loading department page: {department_url}")
                page.goto(department_url, wait_until='networkidle', timeout=self.timeout)
                
                # Wait for courses to load
                page.wait_for_selector('.course', timeout=self.timeout)
                
                # Find all courses with syllabi
                courses = page.query_selector_all('.course')
                logger.info(f"Found {len(courses)} courses on page")
                print(f"Found {len(courses)} courses on page")  # Debug print
                
                courses_with_syllabi = self._find_courses_with_syllabi(courses)
                logger.info(f"Found {len(courses_with_syllabi)} courses with syllabi")
                print(f"Found {len(courses_with_syllabi)} courses with syllabi")  # Debug print
                
                # Extract syllabus titles
                for course_id, course_elem, syllabus_count in courses_with_syllabi:
                    print(f"Processing {course_id} with {syllabus_count} syllabi...")  # Debug print
                    syllabus_title = self._extract_syllabus_title(page, course_id, course_elem)
                    results[course_id] = syllabus_title
                    
                    if syllabus_title:
                        logger.info(f"Extracted syllabus for {course_id}: {syllabus_title}")
                        print(f"✅ Extracted: {course_id} -> {syllabus_title}")  # Debug print
                    else:
                        logger.warning(f"Could not extract syllabus for {course_id}")
                        print(f"❌ Failed: {course_id}")  # Debug print
                
            except Exception as e:
                logger.error(f"Error extracting syllabi from {department_url}: {e}")
                print(f"Error: {e}")  # Debug print
                import traceback
                traceback.print_exc()
            finally:
                try:
                    browser.close()
                except:
                    pass
        
        return results
    
    def _find_courses_with_syllabi(self, courses) -> List[tuple]:
        """Find courses that have syllabi available.
        
        Args:
            courses: List of course elements from the page
            
        Returns:
            List of tuples (course_id, course_element, syllabus_count)
        """
        courses_with_syllabi = []
        
        for course in courses:
            try:
                course_id_elem = course.query_selector('.course-id')
                if not course_id_elem:
                    continue
                    
                course_id = course_id_elem.text_content().strip()
                
                # Check if this course has syllabi
                syllabus_toggle = course.query_selector('a.toggle-syllabus-link')
                if syllabus_toggle:
                    toggle_text = syllabus_toggle.text_content()
                    print(f"  {course_id}: Toggle text = '{toggle_text}'")  # Debug
                    # Look for count in parentheses
                    count_match = re.search(r'\((\d+)\)', toggle_text)
                    if count_match:
                        count = int(count_match.group(1))
                        print(f"  {course_id}: Found count = {count}")  # Debug
                        if count > 0:
                            courses_with_syllabi.append((course_id, course, count))
                            
            except Exception as e:
                logger.warning(f"Error checking course for syllabi: {e}")
                continue
        
        return courses_with_syllabi
    
    def _extract_syllabus_title(self, page, course_id: str, course_elem) -> Optional[str]:
        """Extract the most recent syllabus title for a course.
        
        Args:
            page: Playwright page object
            course_id: Course ID (e.g., 'CMSC125')
            course_elem: Course element from the page
            
        Returns:
            Most recent syllabus title or None if extraction fails
        """
        try:
            # Find and click the syllabus toggle
            toggle_link = course_elem.query_selector('a.toggle-syllabus-link')
            if not toggle_link:
                logger.warning(f"No syllabus toggle found for {course_id}")
                return None
            
            # Click the toggle to expand syllabi
            toggle_link.click()
            
            # Wait for content to load
            page.wait_for_timeout(2000)  # 2 second wait
            
            # Look for the syllabus container
            container_id = f'{course_id}-syllabus-container'
            container = page.query_selector(f'#{container_id}')
            
            if not container:
                logger.warning(f"Syllabus container not found for {course_id}")
                return None
            
            # Get the text content
            content_text = container.text_content()
            
            if not content_text or not content_text.strip():
                logger.warning(f"No content in syllabus container for {course_id}")
                return None
            
            # Extract semester/year patterns
            syllabus_titles = self._parse_semester_patterns(content_text)
            
            if syllabus_titles:
                # Return the first one (assuming most recent)
                return syllabus_titles[0]
            else:
                logger.warning(f"No semester patterns found in syllabus content for {course_id}: '{content_text}'")
                return None
                
        except PlaywrightTimeoutError:
            logger.error(f"Timeout extracting syllabus for {course_id}")
            return None
        except Exception as e:
            logger.error(f"Error extracting syllabus for {course_id}: {e}")
            return None
    
    def _parse_semester_patterns(self, text: str) -> List[str]:
        """Parse semester/year patterns from text.
        
        Supports both formats:
        - "Fall 2023", "Spring 2025"
        - "2023 Fall", "2024 Spring"
        
        Args:
            text: Text content to parse
            
        Returns:
            List of found syllabus titles, sorted by most recent first
        """
        found_syllabi = []
        
        # Define semester patterns - both formats
        patterns = [
            r'(Fall|Spring|Summer|Winter)\s+(\d{4})',  # "Fall 2023"
            r'(\d{4})\s+(Fall|Spring|Summer|Winter)'   # "2023 Fall"
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) == 2:
                    if match[0].isdigit():  # Year first format (2023 Fall)
                        year, season = match
                    else:  # Season first format (Fall 2023)
                        season, year = match
                    
                    # Normalize to "Season Year" format
                    syllabus_title = f"{season.title()} {year}"
                    
                    if syllabus_title not in found_syllabi:
                        found_syllabi.append(syllabus_title)
        
        # Sort by year (most recent first), then by season priority
        season_priority = {'Spring': 1, 'Summer': 2, 'Fall': 3, 'Winter': 4}
        
        def sort_key(title):
            parts = title.split()
            if len(parts) == 2:
                season, year = parts
                return (-int(year), season_priority.get(season, 5))
            return (0, 0)
        
        found_syllabi.sort(key=sort_key)
        
        return found_syllabi
