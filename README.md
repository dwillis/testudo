# testudo

**testudo** is a Python scraper for collecting course information from the University of Maryland's [Schedule of Classes](https://app.testudo.umd.edu/soc/). It extracts data including course titles, enrollment numbers, schedules, locations, instructor information, and more.

## Features

- 📦 **Modern Python packaging** with uv support
- 🔧 **Flexible CLI** with multiple operation modes
- 🗄️ **SQLite conversion** to transform JSON course data into queryable databases
- 📊 **CSV export** for spreadsheet analysis and data processing
- � **Syllabus extraction** using browser automation (optional)
- 🎯 **Department-specific scraping** for targeted data collection
- �🔄 **Resilient scraping** with automatic retries and exponential backoff
- 📊 **Comprehensive logging** with detailed progress tracking and error reporting
- 🧪 **Test mode** for safe development and testing
- 🏗️ **Modular architecture** with separate components for parsing, data models, and orchestration
- ✅ **Full test suite** with unit tests and type checking

## Quick Start

```bash
# Clone the repository
git clone https://github.com/dwillis/testudo.git
cd testudo

# Install dependencies using uv (recommended)
uv sync

# Test with a single department (safe for development)
uv run python cli.py --test AAAS

# Scrape a single department 
uv run python cli.py --department CMSC

# Run full scrape
uv run python cli.py --term 202508
```

You can also use the conversion scripts directly:

```bash
# SQLite conversion
uv run python json_to_sqlite.py data/202501/CMSC courses.db

# CSV conversion  
uv run python json2csv.py --input data/202501/CMSC --output courses.csv

# See all options
uv run python json_to_sqlite.py --help
uv run python json2csv.py --help
```

## Usage

### Command Line Interface

```bash
# Test with specific department
uv run python cli.py --test CMSC

# Scrape specific department
uv run python cli.py --department CMSC

# Scrape with syllabus extraction (slower, uses browser automation)
uv run python cli.py --department CMSC --extract-syllabi

# Scrape specific term
uv run python cli.py --term 202508

# Scrape department for specific term
uv run python cli.py --department JOUR --term 202508

# Enable debug logging
uv run python cli.py --verbose --test JOUR

# Custom configuration
uv run python cli.py --test --delay 0.5 --data-dir custom_data

# Convert JSON data to SQLite database
uv run python cli.py --to-sqlite courses.db --data-dir data/202501

# Convert JSON data to CSV
uv run python cli.py --to-csv courses.csv --data-dir data/202501

# Show all options
uv run python cli.py --help
```

### Data Export Options

#### SQLite Database Generation

Convert any set of course JSON files to a SQLite database for analysis:

```bash
# Convert specific department
uv run python cli.py --to-sqlite cmsc_courses.db --data-dir data/202501/CMSC

# Convert entire term
uv run python cli.py --to-sqlite spring2025.db --data-dir data/202501

# Convert with custom pattern
uv run python cli.py --to-sqlite courses.db --pattern "*/CMSC/*.json"

# Overwrite existing database
uv run python cli.py --to-sqlite courses.db --data-dir data --overwrite
```

The generated SQLite database contains two main tables:
- **`courses`**: Flattened course information (id, title, credits, level, department, etc.)
- **`sections`**: Section details (seats, instructors, schedule, location, etc.)
- **`course_sections`**: A view joining both tables for easy querying

Sample queries:
```sql
-- Top departments by course count
SELECT department, COUNT(*) as course_count 
FROM courses 
GROUP BY department 
ORDER BY course_count DESC;

-- Graduate vs undergraduate distribution
SELECT level, COUNT(*) as course_count 
FROM courses 
GROUP BY level;

-- Courses with the most sections
SELECT course_id, title, section_count 
FROM courses 
ORDER BY section_count DESC 
LIMIT 10;

-- Available seats by department
SELECT c.department, SUM(s.open_seats) as available_seats
FROM courses c 
JOIN sections s ON c.course_id = s.course_id 
GROUP BY c.department 
ORDER BY available_seats DESC;
```

#### CSV Export

Convert JSON course data to CSV format for spreadsheet analysis:

```bash
# Convert specific department  
uv run python cli.py --to-csv cmsc_courses.csv --data-dir data/202501/CMSC

# Convert entire term
uv run python cli.py --to-csv spring2025.csv --data-dir data/202501

# Convert all data
uv run python cli.py --to-csv all_courses.csv --data-dir data
```

The generated CSV includes columns for:
- Course details: id, title, description, term, department, level, credits
- Section info: section count, total seats, open seats, filled seats, waitlist
- Instructor information: all instructors across sections
- Additional data: grading methods, syllabus count
```
```

### Python API

```python
from testudo import TestudoScraper, ScraperConfig

# Create custom configuration
config = ScraperConfig(
    request_delay=0.5,
    data_dir="my_data",
    default_term="202508"
)

# Initialize scraper
scraper = TestudoScraper(config)

# Test scrape
scraper.scrape_test(department_id="CMSC")

# Full scrape
scraper.scrape_full(term="202508")

# Print statistics
scraper.print_stats()
```

## Project Structure

```
testudo/
├── cli.py                    # Modern command-line interface
├── testudo.py               # Original script (still functional)
├── testudo/                 # Main package
│   ├── config.py           # Configuration and settings
│   ├── models.py           # Data models (Course, Section, Department)
│   ├── utils.py            # Utility functions and decorators
│   ├── parser.py           # HTML parsing and data extraction
│   └── scraper.py          # Main orchestration logic
├── tests/                   # Comprehensive test suite
│   └── test_testudo.py     # Unit tests
└── data/                    # Output directory (created automatically)
    └── {term}/
        └── {dept}/
            └── {course}.json
```

## Output Format

After scraping, you'll find a directory structure like this:

    data/{term}/{dept}/{course}.json

For convenience, the included **json2csv.py** program converts all JSON files into a single CSV file saved as `data/courses.csv`.

### Example Course JSON

```json
{
  "id": "AAAS100",
  "title": "Introduction to African American and Africana Studies",
  "credits": "3",
  "description": "Credit only granted for: AASP100 or AAAS100.\nFormerly: AASP100.",
  "level": "Undergrad",
  "grading-method": [
    "Reg",
    "P-F", 
    "Aud"
  ],
  "sections": [
    {
      "id": "0101",
      "instructors": ["Shane Walsh"],
      "seats": 31,
      "open-seats": 1,
      "waitlist": 0,
      "days": "MWF",
      "start": "10:00am", 
      "end": "10:50am",
      "building": "SYM",
      "room": "0215"
    }
  ],
  "term": "202508",
  "department": "African American and Africana Studies",
  "syllabus_count": 1,
  "most_recent_syllabus": "Fall 2023",
  "updated": "2025-07-30T22:49:50.401322Z"
}
```

### Syllabus Extraction

By default, the scraper only counts the number of syllabi available for each course (`syllabus_count` field). To extract the actual syllabus titles, use the `--extract-syllabi` flag:

```bash
# Extract syllabi for a specific department
uv run python cli.py --department CMSC --extract-syllabi

# This will populate the 'most_recent_syllabus' field with values like:
# "Fall 2023", "Spring 2024", "Summer 2024", etc.
```

**Important Notes:**
- Syllabus extraction uses browser automation (Playwright) and is significantly slower
- Only the most recent syllabus title is extracted per course
- The feature caches results at the department level for efficiency
- Extraction is optional due to performance impact

## Development

### Setup Development Environment

```bash
# Install all dependencies including dev tools
uv sync --extra dev

# Run tests
uv run python -m pytest tests/ -v

# Run tests with coverage
uv run python -m pytest tests/ --cov=testudo

# Code formatting
uv run black .

# Type checking  
uv run mypy testudo/

# Linting
uv run flake8 testudo/
```

### Architecture

The scraper is built with a modular architecture:

- **`config.py`**: Centralized configuration and logging setup
- **`models.py`**: Type-safe data structures with validation
- **`utils.py`**: Reusable utilities (retry logic, safe parsing, validation)
- **`parser.py`**: HTML parsing and data extraction logic
- **`scraper.py`**: Main orchestration and file I/O operations
- **`cli.py`**: Command-line interface with argparse

### Key Improvements

- ✅ **Error Handling**: Comprehensive retry logic with exponential backoff
- ✅ **Logging**: Structured logging with multiple levels and detailed progress tracking
- ✅ **Data Validation**: Safe parsing with input validation and type checking
- ✅ **Performance**: Configurable delays and optimized request patterns
- ✅ **Testing**: Full test suite with unit tests and mock-friendly design
- ✅ **Documentation**: Type hints and comprehensive docstrings

## Configuration

### Environment Variables

You can configure the scraper using environment variables or by modifying the configuration:

```python
from testudo import ScraperConfig

config = ScraperConfig(
    base_url="https://app.testudo.umd.edu/soc",
    request_delay=1.0,          # Delay between requests (seconds)
    max_retries=3,              # Number of retry attempts
    default_term="202508",      # Default term to scrape
    data_dir="data",            # Output directory
    log_level="INFO"            # Logging level
)
```

### Command Line Options

```
--test [DEPT]         Test mode - scrape only specified department (default: AAAS)
--department DEPT     Scrape only the specified department (e.g., CMSC, JOUR, MATH)
--term TERM           Specific term to scrape (e.g., 202508)  
--verbose, -v         Enable debug logging
--data-dir DIR        Directory to save course data (default: data)
--delay SECONDS       Delay between requests in seconds (default: 1.0)
--help               Show help message and exit
```

## Error Handling

The scraper includes robust error handling:

- **Automatic retries** with exponential backoff for network failures
- **Graceful degradation** - continues processing other courses/departments if one fails
- **Comprehensive logging** - detailed error messages with context
- **Data validation** - validates course IDs, titles, and other required fields
- **Safe parsing** - handles malformed HTML and missing data gracefully

## Performance Considerations

- **Rate limiting**: Built-in delays between requests to be respectful to the server
- **Retry logic**: Automatic retries with backoff prevent temporary failures from stopping the entire scrape
- **Memory efficient**: Processes courses as a generator to handle large datasets
- **Progress tracking**: Real-time logging shows progress and estimated completion time

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Run the test suite (`uv run python -m pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contact

For questions or issues, please email dpwillis@umd.edu or open an issue on GitHub.

## Changelog

### v1.0.0 (2025-07-30)
- 🎉 **Major refactor**: Modular architecture with separate components
- ✨ **New CLI**: Modern argparse-based command-line interface  
- 🔄 **Enhanced error handling**: Retry logic with exponential backoff
- 📊 **Improved logging**: Structured logging with progress tracking
- 🧪 **Test suite**: Comprehensive unit tests with pytest
- 📦 **Modern packaging**: uv support and proper Python packaging
- 🔧 **Configuration system**: Centralized configuration management
- 🚀 **Performance improvements**: Better memory usage and request handling
