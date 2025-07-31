"""Tests for the testudo scraper."""

import pytest
import json
from unittest.mock import Mock, patch
from testudo import TestudoScraper, ScraperConfig, Course, Section, Department

class TestScraperConfig:
    """Test the scraper configuration."""
    
    def test_default_config(self):
        config = ScraperConfig()
        assert config.base_url == "https://app.testudo.umd.edu/soc"
        assert config.default_term == "202508"
        assert config.request_delay == 1.0

class TestModels:
    """Test the data models."""
    
    def test_section_creation(self):
        section = Section(
            id="0101",
            instructors=["John Doe"],
            seats=30,
            open_seats=5,
            waitlist=0,
            days="MWF",
            start="10:00am",
            end="10:50am",
            building="SYM",
            room="0215"
        )
        assert section.id == "0101"
        assert section.instructors == ["John Doe"]
    
    def test_course_to_dict(self):
        section = Section(
            id="0101", instructors=["John Doe"], seats=30, open_seats=5,
            waitlist=0, days="MWF", start="10:00am", end="10:50am",
            building="SYM", room="0215"
        )
        
        course = Course(
            id="AAAS100",
            title="Test Course",
            credits="3",
            description="A test course",
            level="Undergrad",
            grading_method=["Reg", "P-F"],
            sections=[section],
            term="202508",
            department="Test Department",
            syllabus_count=1,
            most_recent_syllabus="Fall 2023",
            updated="2025-07-30T00:00:00.000Z"
        )
        
        course_dict = course.to_dict()
        assert course_dict["id"] == "AAAS100"
        assert len(course_dict["sections"]) == 1
        assert course_dict["sections"][0]["id"] == "0101"
        assert course_dict["most_recent_syllabus"] == "Fall 2023"
    
    def test_course_to_json(self):
        section = Section(
            id="0101", instructors=["John Doe"], seats=30, open_seats=5,
            waitlist=0, days="MWF", start="10:00am", end="10:50am",
            building="SYM", room="0215"
        )
        
        course = Course(
            id="AAAS100",
            title="Test Course", 
            credits="3",
            description="A test course",
            level="Undergrad",
            grading_method=["Reg"],
            sections=[section],
            term="202508",
            department="Test Department",
            syllabus_count=1,
            most_recent_syllabus=None,
            updated="2025-07-30T00:00:00.000Z"
        )
        
        json_str = course.to_json()
        parsed = json.loads(json_str)
        assert parsed["id"] == "AAAS100"

class TestUtils:
    """Test utility functions."""
    
    def test_safe_int(self):
        from testudo.utils import safe_int
        
        assert safe_int("123") == 123
        assert safe_int("1,234") == 1234
        assert safe_int("") == 0
        assert safe_int(None) == 0
        assert safe_int("abc") == 0
        assert safe_int("abc", default=99) == 99
    
    def test_validate_course_id(self):
        from testudo.utils import validate_course_id
        
        assert validate_course_id("AAAS100") == True
        assert validate_course_id("CMSC131") == True
        assert validate_course_id("ENGL101H") == True
        assert validate_course_id("") == False
        assert validate_course_id("123") == False
        assert validate_course_id("ABC") == False
    
    def test_determine_course_level(self):
        from testudo.utils import determine_course_level
        
        assert determine_course_level("AAAS100") == "Undergrad"
        assert determine_course_level("AAAS499") == "Undergrad"
        assert determine_course_level("AAAS500") == "Grad"
        assert determine_course_level("AAAS700") == "Grad"

@pytest.fixture
def mock_config():
    """Create a test configuration."""
    return ScraperConfig(
        request_delay=0.1,  # Faster for testing
        test_max_courses=2
    )

class TestScraper:
    """Test the main scraper functionality."""
    
    def test_scraper_creation(self, mock_config):
        scraper = TestudoScraper(mock_config)
        assert scraper.config.request_delay == 0.1
        assert scraper.stats.successful_courses == 0

if __name__ == "__main__":
    pytest.main([__file__])
