#!/usr/bin/env python3
"""
Load course data for specific terms and create a unified database.

This script loads data from the following terms:
- 202301 (Spring 2023)
- 202308 (Fall 2023)
- 202401 (Spring 2024)
- 202408 (Fall 2024)
- 202501 (Spring 2025)
- 202508 (Fall 2025)
- 202601 (Spring 2026)
"""

import os
import sys
import json
import glob
import logging
import sqlite_utils
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from testudo import TestudoScraper, ScraperConfig, setup_logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define the specific terms to load
SPECIFIC_TERMS = [
    '202301',  # Spring 2023
    '202308',  # Fall 2023
    '202401',  # Spring 2024
    '202408',  # Fall 2024
    '202501',  # Spring 2025
    '202508',  # Fall 2025
    '202601',  # Spring 2026
]


def check_term_data_exists(data_dir: str, term: str) -> bool:
    """Check if data exists for a specific term."""
    term_path = os.path.join(data_dir, term)
    if not os.path.exists(term_path):
        return False

    # Check if there are any JSON files in the term directory
    json_files = glob.glob(os.path.join(term_path, '**/*.json'), recursive=True)
    return len(json_files) > 0


def scrape_term_if_needed(term: str, data_dir: str = 'data', force_rescrape: bool = False):
    """Scrape a term if data doesn't exist or force_rescrape is True."""
    if not force_rescrape and check_term_data_exists(data_dir, term):
        logger.info(f"Data already exists for term {term}, skipping scrape")
        return True

    logger.info(f"Scraping data for term {term}...")

    try:
        config = ScraperConfig(
            data_dir=data_dir,
            request_delay=1.0,
            log_level="INFO",
            extract_syllabi=False
        )
        config.default_term = term

        scraper = TestudoScraper(config)
        scraper.scrape_full(term=term)
        scraper.print_stats()

        return True
    except Exception as e:
        logger.error(f"Error scraping term {term}: {e}")
        return False


def flatten_course(course_data: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a course JSON object for insertion into SQLite."""
    # Handle both snake_case and kebab-case field names
    gen_ed = course_data.get('gen_ed') or course_data.get('gen-ed', [])
    grading_method = course_data.get('grading_method') or course_data.get('grading-method', [])

    flattened = {
        'course_id': course_data.get('id'),
        'title': course_data.get('title'),
        'credits': course_data.get('credits'),
        'description': course_data.get('description'),
        'level': course_data.get('level'),
        'term': course_data.get('term'),
        'department': course_data.get('department'),
        'syllabus_count': course_data.get('syllabus_count', 0),
        'most_recent_syllabus': course_data.get('most_recent_syllabus'),
        'updated': course_data.get('updated'),
        'grading_methods': ', '.join(grading_method) if grading_method else None,
        'gen_ed': ', '.join(gen_ed) if gen_ed else None,
        'section_count': len(course_data.get('sections', []))
    }

    return flattened


def flatten_sections(course_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract and flatten sections from a course."""
    sections = []
    course_id = course_data.get('id')
    term = course_data.get('term')

    for section in course_data.get('sections', []):
        # Handle both 'open_seats' (new format) and 'open-seats' (old format)
        open_seats = section.get('open_seats') or section.get('open-seats', 0)

        flattened_section = {
            'course_id': course_id,
            'term': term,
            'section_id': section.get('id'),
            'instructors': ', '.join(section.get('instructors', [])) if section.get('instructors') else None,
            'seats': section.get('seats', 0),
            'open_seats': open_seats,
            'waitlist': section.get('waitlist', 0),
            'days': section.get('days'),
            'start_time': section.get('start'),
            'end_time': section.get('end'),
            'building': section.get('building'),
            'room': section.get('room')
        }
        sections.append(flattened_section)

    return sections


def load_specific_terms_to_db(
    data_dir: str = 'data',
    output_db: str = 'courses_specific_terms.db',
    terms: List[str] = None,
    overwrite: bool = False,
    scrape_missing: bool = False,
    force_rescrape: bool = False
) -> None:
    """
    Load data from specific terms into a SQLite database.

    Args:
        data_dir: Directory containing the JSON data
        output_db: Output SQLite database path
        terms: List of terms to load (default: SPECIFIC_TERMS)
        overwrite: Whether to overwrite existing database
        scrape_missing: Whether to scrape terms that don't have data
        force_rescrape: Whether to rescrape all terms even if data exists
    """
    if terms is None:
        terms = SPECIFIC_TERMS

    logger.info(f"Loading data for terms: {', '.join(terms)}")

    # Scrape missing terms if requested
    if scrape_missing or force_rescrape:
        for term in terms:
            scrape_term_if_needed(term, data_dir, force_rescrape)

    # Check which terms have data
    available_terms = []
    missing_terms = []

    for term in terms:
        if check_term_data_exists(data_dir, term):
            available_terms.append(term)
        else:
            missing_terms.append(term)

    if missing_terms:
        logger.warning(f"Missing data for terms: {', '.join(missing_terms)}")
        if not scrape_missing:
            logger.warning("Use --scrape-missing to scrape missing terms")

    if not available_terms:
        logger.error("No data available for any of the specified terms")
        return

    logger.info(f"Found data for {len(available_terms)} terms: {', '.join(available_terms)}")

    # Create or open database
    if overwrite and os.path.exists(output_db):
        os.remove(output_db)
        logger.info(f"Removed existing database: {output_db}")

    db = sqlite_utils.Database(output_db)
    logger.info(f"Created/opened database: {output_db}")

    # Process each term
    all_courses_data = []
    all_sections_data = []
    processed_files = 0
    failed_files = 0

    for term in available_terms:
        term_path = os.path.join(data_dir, term)
        json_files = glob.glob(os.path.join(term_path, '**/*.json'), recursive=True)

        logger.info(f"Processing term {term}: {len(json_files)} courses")

        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    course_data = json.load(f)

                # Flatten course data
                flattened_course = flatten_course(course_data)
                all_courses_data.append(flattened_course)

                # Flatten sections data
                course_sections = flatten_sections(course_data)
                all_sections_data.extend(course_sections)

                processed_files += 1

                if processed_files % 100 == 0:
                    logger.info(f"Processed {processed_files} files...")

            except Exception as e:
                logger.error(f"Error processing {json_file}: {e}")
                failed_files += 1
                continue

    # Insert data into database
    if all_courses_data:
        logger.info(f"Inserting {len(all_courses_data)} courses into database...")
        db['courses'].insert_all(all_courses_data, replace=True)

        # Create indexes for better query performance
        db['courses'].create_index(['course_id'], if_not_exists=True)
        db['courses'].create_index(['term'], if_not_exists=True)
        db['courses'].create_index(['department'], if_not_exists=True)
        db['courses'].create_index(['level'], if_not_exists=True)
        db['courses'].create_index(['title'], if_not_exists=True)
        logger.info("Created indexes on courses table")

    if all_sections_data:
        logger.info(f"Inserting {len(all_sections_data)} sections into database...")
        db['sections'].insert_all(all_sections_data, replace=True)

        # Create indexes for better query performance
        db['sections'].create_index(['course_id'], if_not_exists=True)
        db['sections'].create_index(['term'], if_not_exists=True)
        db['sections'].create_index(['section_id'], if_not_exists=True)
        db['sections'].create_index(['instructors'], if_not_exists=True)
        logger.info("Created indexes on sections table")

    # Create a view for easy joins
    db.executescript("""
        DROP VIEW IF EXISTS course_sections;
        CREATE VIEW course_sections AS
        SELECT
            c.course_id,
            c.title,
            c.credits,
            c.description,
            c.level,
            c.term,
            c.department,
            c.syllabus_count,
            c.most_recent_syllabus,
            c.grading_methods,
            c.gen_ed,
            s.section_id,
            s.instructors,
            s.seats,
            s.open_seats,
            s.waitlist,
            s.days,
            s.start_time,
            s.end_time,
            s.building,
            s.room
        FROM courses c
        LEFT JOIN sections s ON c.course_id = s.course_id AND c.term = s.term;
    """)
    logger.info("Created course_sections view")

    # Summary
    print("\n" + "="*70)
    print("DATABASE CREATION COMPLETE")
    print("="*70)
    print(f"  Processed files: {processed_files}")
    print(f"  Failed files: {failed_files}")
    print(f"  Total courses: {len(all_courses_data)}")
    print(f"  Total sections: {len(all_sections_data)}")
    print(f"  Terms loaded: {', '.join(available_terms)}")
    print(f"  Database: {output_db}")
    print("="*70)

    # Show statistics by term
    print("\nCourses by term:")
    for term in available_terms:
        count = len([c for c in all_courses_data if c['term'] == term])
        print(f"  {term}: {count} courses")

    # Show sample queries
    print("\nSample queries you can run:")
    print(f"  # View all tables")
    print(f"  sqlite-utils tables {output_db}")
    print(f"\n  # Count courses by department")
    print(f"  sqlite-utils {output_db} 'SELECT department, COUNT(*) as count FROM courses GROUP BY department ORDER BY count DESC LIMIT 10'")
    print(f"\n  # Count courses by term")
    print(f"  sqlite-utils {output_db} 'SELECT term, COUNT(*) as count FROM courses GROUP BY term'")
    print(f"\n  # Search for courses with 'machine learning' in title or description")
    print(f"  sqlite-utils {output_db} \"SELECT course_id, title, term FROM courses WHERE title LIKE '%machine learning%' OR description LIKE '%machine learning%'\"")
    print(f"\n  # View sample course sections")
    print(f"  sqlite-utils {output_db} 'SELECT * FROM course_sections LIMIT 5'")


def main():
    parser = argparse.ArgumentParser(
        description="Load course data for specific terms into SQLite database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Terms to be loaded:
  {', '.join(SPECIFIC_TERMS)}

Examples:
  # Load existing data from specific terms
  python load_specific_terms.py

  # Load data and scrape any missing terms
  python load_specific_terms.py --scrape-missing

  # Force rescrape all terms and create new database
  python load_specific_terms.py --force-rescrape --overwrite

  # Custom output database name
  python load_specific_terms.py --output my_courses.db

  # Load only certain terms
  python load_specific_terms.py --terms 202501 202508
        """
    )

    parser.add_argument(
        '--data-dir',
        default='data',
        help='Directory containing JSON course data (default: data)'
    )

    parser.add_argument(
        '--output',
        default='courses_specific_terms.db',
        help='Output SQLite database file (default: courses_specific_terms.db)'
    )

    parser.add_argument(
        '--terms',
        nargs='+',
        help=f'Specific terms to load (default: {" ".join(SPECIFIC_TERMS)})'
    )

    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing database file'
    )

    parser.add_argument(
        '--scrape-missing',
        action='store_true',
        help='Scrape terms that do not have existing data'
    )

    parser.add_argument(
        '--force-rescrape',
        action='store_true',
        help='Force rescrape all terms even if data exists'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate data directory if not scraping
    if not args.scrape_missing and not args.force_rescrape:
        if not os.path.exists(args.data_dir):
            logger.error(f"Data directory does not exist: {args.data_dir}")
            logger.info("Use --scrape-missing to scrape the data first")
            return 1

    # Check if output database exists and warn user
    if os.path.exists(args.output) and not args.overwrite:
        logger.warning(f"Database {args.output} already exists. Use --overwrite to replace it.")
        return 1

    try:
        load_specific_terms_to_db(
            data_dir=args.data_dir,
            output_db=args.output,
            terms=args.terms,
            overwrite=args.overwrite,
            scrape_missing=args.scrape_missing,
            force_rescrape=args.force_rescrape
        )
        return 0
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        return 1


if __name__ == '__main__':
    sys.exit(main())
