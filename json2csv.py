#!/usr/bin/env python3

"""
json2csv.py will read in the individual JSON files that testudo.py writes
and write them out as a single CSV file for processing as a spreadsheet.
"""
import os
import csv
import json
import argparse
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def process_json_to_csv(input_dir: str, output_file: str) -> None:
    """
    Convert JSON course files to a single CSV file.
    
    Args:
        input_dir: Directory containing JSON files
        output_file: Output CSV file path
    """
    
    # Ensure output directory exists
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    processed_count = 0
    failed_count = 0
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            'id',
            'title',
            'description',
            'term',
            'department',
            'level',
            'credits',
            'grading_methods',
            'sections',
            'instructors',
            'seats',
            'open_seats',
            'filled_seats',
            'waitlist',
            'syllabus_count',
            'most_recent_syllabus'
        ])
        
        for dirpath, dirnames, filenames in os.walk(input_dir):
            for filename in filenames:
                if not filename.endswith('.json'):
                    continue
                
                json_file = os.path.join(dirpath, filename)
                
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        course = json.load(f)
                    
                    # Extract basic course info
                    course_id = course.get('id', '')
                    title = course.get('title', '')
                    description = course.get('description', '')
                    term = course.get('term', '')
                    department = course.get('department', '')
                    level = course.get('level', '')
                    credits = course.get('credits', '')
                    
                    # Handle grading methods (can be list or single value)
                    grading_methods = course.get('grading-method', [])
                    if isinstance(grading_methods, list):
                        grading_methods_str = '; '.join(grading_methods)
                    else:
                        grading_methods_str = str(grading_methods) if grading_methods else ''
                    
                    sections = course.get('sections', [])
                    section_count = len(sections)
                    
                    # Collect instructors from all sections
                    instructors = set()
                    total_seats = 0
                    total_open_seats = 0
                    total_waitlist = 0
                    
                    for section in sections:
                        # Add instructors
                        section_instructors = section.get('instructors', [])
                        if section_instructors:
                            instructors.update(section_instructors)
                        
                        # Sum up seats (handle both key formats)
                        seats = section.get('seats', 0) or 0
                        total_seats += seats
                        
                        # Handle open seats (both key formats for backward compatibility)
                        open_seats = section.get('open_seats') or section.get('open-seats', 0) or 0
                        total_open_seats += open_seats
                        
                        # Handle waitlist
                        waitlist = section.get('waitlist', 0) or 0
                        total_waitlist += waitlist
                    
                    instructors_str = '; '.join(sorted(instructors)) if instructors else ''
                    filled_seats = total_seats - total_open_seats
                    
                    # Handle syllabus information
                    syllabus_count = course.get('syllabus_count', 0) or 0
                    most_recent_syllabus = course.get('most_recent_syllabus', '') or ''
                    
                    writer.writerow([
                        course_id,
                        title,
                        description,
                        term,
                        department,
                        level,
                        credits,
                        grading_methods_str,
                        section_count,
                        instructors_str,
                        total_seats,
                        total_open_seats,
                        filled_seats,
                        total_waitlist,
                        syllabus_count,
                        most_recent_syllabus
                    ])
                    
                    processed_count += 1
                    
                    if processed_count % 100 == 0:
                        logger.info(f"Processed {processed_count} courses...")
                        
                except Exception as e:
                    logger.error(f"Error processing {json_file}: {e}")
                    failed_count += 1
                    continue
    
    logger.info(f"CSV conversion complete!")
    logger.info(f"  Processed: {processed_count} courses")
    logger.info(f"  Failed: {failed_count} courses") 
    logger.info(f"  Output: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert course JSON files to CSV format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert all JSON files in data directory
  python json2csv.py
  
  # Convert specific directory
  python json2csv.py --input data/202501 --output spring2025.csv
  
  # Convert with custom paths
  python json2csv.py --input /path/to/json --output /path/to/output.csv
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        default='data',
        help='Input directory containing JSON files (default: data)'
    )
    
    parser.add_argument(
        '--output', '-o', 
        default='data/courses.csv',
        help='Output CSV file path (default: data/courses.csv)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate input directory
    if not os.path.exists(args.input):
        logger.error(f"Input directory does not exist: {args.input}")
        return 1
    
    try:
        process_json_to_csv(args.input, args.output)
        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
