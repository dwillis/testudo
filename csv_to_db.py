#!/usr/bin/env python3
"""
Quick script to convert CSV course data to SQLite database.
"""
import csv
import sqlite_utils
import sys

def csv_to_db(csv_file='courses_202501.csv', db_file='courses_specific_terms.db'):
    """Convert CSV file to SQLite database."""
    print(f"Reading {csv_file}...")

    # Read CSV data
    courses = []
    with open(csv_file, 'r', encoding='utf-8-sig') as f:  # utf-8-sig to handle BOM
        reader = csv.DictReader(f)
        for row in reader:
            # Convert the row to match expected schema
            course = {
                'course_id': row['id'],
                'title': row['title'],
                'description': row['description'],
                'term': row['term'],
                'department': row['department'],
                'level': row['level'],
                'credits': None,  # Not in CSV
                'syllabus_count': int(row['syllabus_count']) if row['syllabus_count'] else 0,
                'most_recent_syllabus': None,
                'updated': None,
                'grading_methods': None,
                'gen_ed': None,
                'section_count': int(row['sections']) if row['sections'] else 0,
            }
            courses.append(course)

    print(f"Found {len(courses)} courses")
    print(f"Creating database {db_file}...")

    # Create database
    db = sqlite_utils.Database(db_file)

    # Insert courses
    db['courses'].insert_all(courses, replace=True)

    # Create indexes
    print("Creating indexes...")
    db['courses'].create_index(['course_id'], if_not_exists=True)
    db['courses'].create_index(['term'], if_not_exists=True)
    db['courses'].create_index(['department'], if_not_exists=True)
    db['courses'].create_index(['level'], if_not_exists=True)
    db['courses'].create_index(['title'], if_not_exists=True)

    print(f"✓ Database created successfully!")
    print(f"  Total courses: {len(courses)}")
    print(f"  Database: {db_file}")

if __name__ == '__main__':
    csv_to_db()
