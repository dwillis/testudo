"""Utility functions for the testudo scraper."""

import time
import random
import logging
from functools import wraps
from typing import Union, Optional

logger = logging.getLogger(__name__)

def retry_on_failure(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator to retry functions with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        logger.error(f"Failed after {max_retries} attempts in {func.__name__}: {e}")
                        raise
                    
                    # Exponential backoff with jitter
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Attempt {attempt + 1} failed in {func.__name__}: {e}. Retrying in {delay:.2f}s...")
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
        return wrapper
    return decorator

def safe_int(value: Union[str, int, None], default: int = 0) -> int:
    """Safely convert a string to int, handling commas and empty values."""
    if not value:
        return default
    try:
        # Remove commas and whitespace, then convert
        clean_value = str(value).strip().replace(',', '')
        return int(clean_value) if clean_value else default
    except (ValueError, TypeError):
        return default

def safe_text(element, selector: str) -> str:
    """Safely extract text from an HTML element."""
    if not element:
        return ''
    
    e = element.find(selector, first=True)
    if e and e.text:
        return e.text.strip()
    return ''

def validate_course_id(course_id: str) -> bool:
    """Validate that a course ID looks reasonable."""
    if not course_id:
        return False
    # Basic validation: should have letters followed by numbers
    import re
    return bool(re.match(r'^[A-Z]{2,8}\d{3,4}[A-Z]?$', course_id.strip()))

def determine_course_level(course_id: str) -> str:
    """Determine if a course is undergraduate or graduate."""
    import re
    try:
        match = re.search(r'\d+', course_id)
        if match and int(match.group()) >= 500:
            return 'Grad'
        return 'Undergrad'
    except (ValueError, AttributeError):
        logger.warning(f"Could not determine level for {course_id}")
        return 'Undergrad'  # Default to undergraduate
