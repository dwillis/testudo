"""Data models for the testudo scraper."""

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
import datetime
import json

@dataclass
class Section:
    """Represents a course section."""
    id: str
    instructors: List[str]
    seats: int
    open_seats: int
    waitlist: int
    days: str
    start: str
    end: str
    building: str
    room: str

@dataclass
class Course:
    """Represents a course."""
    id: str
    title: str
    credits: str
    description: str
    level: str
    grading_method: List[str]
    sections: List[Section]
    term: str
    department: str
    syllabus_count: int
    most_recent_syllabus: Optional[str]
    updated: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert course to dictionary for JSON serialization."""
        result = asdict(self)
        # Convert sections to dictionaries
        result['sections'] = [asdict(section) for section in self.sections]
        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert course to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

@dataclass
class Department:
    """Represents a department."""
    id: str
    name: str

@dataclass
class ScrapingStats:
    """Statistics for a scraping session."""
    start_time: float
    total_courses: int = 0
    successful_courses: int = 0
    failed_courses: int = 0
    departments_processed: int = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_courses == 0:
            return 0.0
        return (self.successful_courses / self.total_courses) * 100
    
    @property
    def elapsed_time(self) -> float:
        """Calculate elapsed time in seconds."""
        import time
        return time.time() - self.start_time
