"""Configuration settings for the testudo scraper."""

import logging
from dataclasses import dataclass
from typing import Optional

@dataclass
class ScraperConfig:
    """Configuration for the testudo scraper."""
    base_url: str = "https://app.testudo.umd.edu/soc"
    user_agent: str = "testudo.py <https://github.com/dwillis/testudo>"
    request_delay: float = 1.0
    max_retries: int = 3
    base_retry_delay: float = 1.0
    default_term: str = "202508"
    data_dir: str = "data"
    log_level: str = "INFO"
    
    # Test mode settings
    test_max_courses: int = 3
    test_department: str = "AAAS"

def setup_logging(level: str = "INFO") -> logging.Logger:
    """Set up logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)
