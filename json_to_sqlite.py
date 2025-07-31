#!/usr/bin/env python3
"""
Convert course JSON files to SQLite database using sqlite-utils.
Flattens nested JSON structures for easier querying.
"""

import os
import json
import glob
import argparse
import sqlite_utils
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def flatten_course(course_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten a course JSON object for insertion into SQLite.
    Handles nested structures like sections and grading methods.
    """
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
        'grading_methods': ', '.join(course_data.get('grading-method', [])) if course_data.get('grading-method') else None,
        'section_count': len(course_data.get('sections', []))
    }
    
    return flattened


def flatten_sections(course_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract and flatten sections from a course.
    Each section becomes a separate row linked to the course.
    """
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


def process_json_files(
    input_path: str,
    output_db: str,
    pattern: str = "**/*.json",
    overwrite: bool = False
) -> None:
    """
    Process JSON files and create SQLite database.
    
    Args:
        input_path: Path to directory containing JSON files
        output_db: Path to output SQLite database
        pattern: Glob pattern for finding JSON files
        overwrite: Whether to overwrite existing database
    """
    
    # Create or open database
    if overwrite and os.path.exists(output_db):
        os.remove(output_db)
        logger.info(f"Removed existing database: {output_db}")
    
    db = sqlite_utils.Database(output_db)
    logger.info(f"Created/opened database: {output_db}")
    
    # Find all JSON files
    search_pattern = os.path.join(input_path, pattern)
    json_files = glob.glob(search_pattern, recursive=True)
    logger.info(f"Found {len(json_files)} JSON files matching pattern: {pattern}")
    
    if not json_files:
        logger.warning(f"No JSON files found in {input_path} with pattern {pattern}")
        return
    
    courses_data = []
    sections_data = []
    processed_files = 0
    failed_files = 0
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                course_data = json.load(f)
            
            # Flatten course data
            flattened_course = flatten_course(course_data)
            courses_data.append(flattened_course)
            
            # Flatten sections data
            course_sections = flatten_sections(course_data)
            sections_data.extend(course_sections)
            
            processed_files += 1
            
            if processed_files % 100 == 0:
                logger.info(f"Processed {processed_files} files...")
                
        except Exception as e:
            logger.error(f"Error processing {json_file}: {e}")
            failed_files += 1
            continue
    
    # Insert data into database
    if courses_data:
        logger.info(f"Inserting {len(courses_data)} courses into database...")
        db['courses'].insert_all(courses_data, replace=True)
        
        # Create indexes for better query performance
        db['courses'].create_index(['course_id'], if_not_exists=True)
        db['courses'].create_index(['term'], if_not_exists=True)
        db['courses'].create_index(['department'], if_not_exists=True)
        db['courses'].create_index(['level'], if_not_exists=True)
        logger.info("Created indexes on courses table")
    
    if sections_data:
        logger.info(f"Inserting {len(sections_data)} sections into database...")
        db['sections'].insert_all(sections_data, replace=True)
        
        # Create indexes for better query performance
        db['sections'].create_index(['course_id'], if_not_exists=True)
        db['sections'].create_index(['term'], if_not_exists=True)
        db['sections'].create_index(['section_id'], if_not_exists=True)
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
    logger.info(f"Database creation complete!")
    logger.info(f"  Processed files: {processed_files}")
    logger.info(f"  Failed files: {failed_files}")
    logger.info(f"  Total courses: {len(courses_data)}")
    logger.info(f"  Total sections: {len(sections_data)}")
    logger.info(f"  Database: {output_db}")
    
    # Show sample queries
    print("\nSample queries you can run:")
    print(f"  sqlite-utils {output_db} 'SELECT department, COUNT(*) as course_count FROM courses GROUP BY department ORDER BY course_count DESC LIMIT 10'")
    print(f"  sqlite-utils {output_db} 'SELECT level, COUNT(*) as course_count FROM courses GROUP BY level'")
    print(f"  sqlite-utils {output_db} 'SELECT term, COUNT(*) as course_count FROM courses GROUP BY term'")
    print(f"  sqlite-utils {output_db} 'SELECT * FROM course_sections WHERE department = \"Computer Science\" AND level = \"Grad\" LIMIT 5'")


def main():
    parser = argparse.ArgumentParser(
        description="Convert course JSON files to SQLite database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert all JSON files in data directory
  python json_to_sqlite.py data/ courses.db
  
  # Convert specific term
  python json_to_sqlite.py data/202501/ spring2025.db
  
  # Convert specific department
  python json_to_sqlite.py data/202501/CMSC/ cmsc_spring2025.db
  
  # Overwrite existing database
  python json_to_sqlite.py data/ courses.db --overwrite
  
  # Custom pattern
  python json_to_sqlite.py data/ courses.db --pattern "202501/**/*.json"
        """
    )
    
    parser.add_argument(
        'input_path',
        help='Path to directory containing JSON files'
    )
    
    parser.add_argument(
        'output_db',
        help='Path to output SQLite database file'
    )
    
    parser.add_argument(
        '--pattern',
        default='**/*.json',
        help='Glob pattern for finding JSON files (default: **/*.json)'
    )
    
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing database file'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate input path
    if not os.path.exists(args.input_path):
        logger.error(f"Input path does not exist: {args.input_path}")
        return 1
    
    # Check if output database exists and warn user
    if os.path.exists(args.output_db) and not args.overwrite:
        logger.warning(f"Database {args.output_db} already exists. Use --overwrite to replace it.")
        return 1
    
    try:
        process_json_files(
            args.input_path,
            args.output_db,
            args.pattern,
            args.overwrite
        )
        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
