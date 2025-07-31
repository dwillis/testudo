#!/usr/bin/env python3
"""
Test the syllabus extractor functionality
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'testudo'))

def test_syllabus_extraction():
    """Test syllabus extraction for CMSC department"""
    try:
        from testudo.syllabus_extractor import SyllabusExtractor
        
        print("Testing syllabus extraction...")
        extractor = SyllabusExtractor(headless=True)  # Use headless for now
        
        department_url = 'https://app.testudo.umd.edu/soc/202508/CMSC'
        
        # First let's test the course finding logic
        print(f"Loading {department_url}...")
        
        results = extractor.extract_syllabi_for_department(department_url)
        
        print(f"\n=== RESULTS ===")
        print(f"Found syllabi for {len(results)} courses:")
        
        for course_id, syllabus_title in results.items():
            if syllabus_title:
                print(f"  ✅ {course_id}: {syllabus_title}")
            else:
                print(f"  ❌ {course_id}: No syllabus extracted")
                
        # Show some stats
        with_syllabi = sum(1 for title in results.values() if title)
        print(f"\nSuccessfully extracted: {with_syllabi}/{len(results)} courses")
        
        if len(results) == 0:
            print("\nNo courses found - this might indicate an issue with page loading or selectors")
        
    except ImportError as e:
        print(f"Import error: {e}")
        print("Make sure Playwright is installed: uv add playwright")
        print("And install browsers: uv run python -m playwright install")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_syllabus_extraction()
