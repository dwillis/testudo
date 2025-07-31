"""Testudo scraper package."""

from .config import ScraperConfig, setup_logging
from .models import Course, Section, Department, ScrapingStats
from .scraper import TestudoScraper
from .parser import TestudoParser

__version__ = "1.0.0"
__all__ = [
    "ScraperConfig",
    "setup_logging", 
    "Course",
    "Section", 
    "Department",
    "ScrapingStats",
    "TestudoScraper",
    "TestudoParser"
]
