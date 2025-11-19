#!/usr/bin/env python3
"""
Test script for syllabus extraction using Playwright
"""

from playwright.sync_api import sync_playwright
import time
import re

def extract_syllabus_titles():
    """Extract syllabus titles from course pages"""
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Show browser for debugging
        page = browser.new_page()
        
        try:
            # Go to the page
            url = 'https://app.testudo.umd.edu/soc/202508/CMSC'
            print(f'Loading {url}...')
            page.goto(url, wait_until='networkidle')
            
            # Wait for courses to load
            page.wait_for_selector('.course', timeout=10000)
            print('Page loaded successfully')
            
            # Find courses with syllabus counts > 0
            courses = page.query_selector_all('.course')
            print(f'Found {len(courses)} courses on page')
            
            courses_with_syllabi = []
            for course in courses:
                course_id_elem = course.query_selector('.course-id')
                if course_id_elem:
                    course_id = course_id_elem.text_content().strip()
                    
                    # Check if this course has syllabi
                    syllabus_toggle = course.query_selector('a.toggle-syllabus-link')
                    if syllabus_toggle:
                        toggle_text = syllabus_toggle.text_content()
                        # Look for count in parentheses
                        count_match = re.search(r'\((\d+)\)', toggle_text)
                        if count_match and int(count_match.group(1)) > 0:
                            courses_with_syllabi.append((course_id, course, int(count_match.group(1))))
            
            print(f'Found {len(courses_with_syllabi)} courses with syllabi:')
            for course_id, _, count in courses_with_syllabi:
                print(f'  {course_id}: {count} syllabi')
            
            # Try to extract syllabus content from the first few
            results = []
            for course_id, course, count in courses_with_syllabi[:3]:
                print(f'\n--- Processing {course_id} (has {count} syllabi) ---')
                
                toggle_link = course.query_selector('a.toggle-syllabus-link')
                container_id = f'{course_id}-syllabus-container'
                
                if toggle_link:
                    # Click the toggle
                    print('Clicking toggle...')
                    toggle_link.click()
                    
                    # Wait for content
                    time.sleep(3)
                    
                    # Check for loaded content
                    container = page.query_selector(f'#{container_id}')
                    if container:
                        content_html = container.inner_html()
                        content_text = container.text_content()
                        
                        print(f'Container HTML: {content_html}')
                        print(f'Container text: {content_text}')
                        
                        if content_text.strip():
                            # Look for semester patterns - both formats
                            semester_patterns = [
                                r'(Fall|Spring|Summer|Winter)\s+(\d{4})',  # "Fall 2023"
                                r'(\d{4})\s+(Fall|Spring|Summer|Winter)'   # "2023 Fall"
                            ]
                            
                            found_syllabi = []
                            for pattern in semester_patterns:
                                matches = re.findall(pattern, content_text, re.IGNORECASE)
                                for match in matches:
                                    if len(match) == 2:
                                        if match[0].isdigit():  # Year first format
                                            year, season = match
                                        else:  # Season first format
                                            season, year = match
                                        syllabus_title = f"{season} {year}"
                                        if syllabus_title not in found_syllabi:
                                            found_syllabi.append(syllabus_title)
                            
                            if found_syllabi:
                                print(f'  📅 Found syllabi: {found_syllabi}')
                                # Use the most recent (assuming they're sorted)
                                most_recent = found_syllabi[0]
                                results.append((course_id, most_recent))
                            else:
                                print(f'  ❌ No semester patterns found in: "{content_text}"')
                        else:
                            print('  ❌ No content loaded in container')
                    else:
                        print(f'  ❌ Container #{container_id} not found')
                        
        except Exception as e:
            print(f'Error: {e}')
            import traceback
            traceback.print_exc()
        finally:
            browser.close()
            
        return results

if __name__ == "__main__":
    results = extract_syllabus_titles()
    print(f"\n=== RESULTS ===")
    for course_id, syllabus_title in results:
        print(f"{course_id}: {syllabus_title}")
