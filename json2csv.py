#!/usr/bin/env python

"""
json2csv.py will read in the individual JSON files that testudo.py writes
and write them out as as single CSV file for processing as a spreadsheet.
"""

import os
import csv
import json

output = csv.writer(open('data/courses.csv', 'w'))
output.writerow([
    'id',
    'title',
    'description',
    'term',
    'department',
    'sections',
    'instructors',
    'seats',
    'open_seats',
    'filled_seats',
    'syllabus_count'
])

for dirpath, dirnames, filenames in os.walk('./data/'):
    for filename in filenames:
        if not filename.endswith('.json'):
            continue

        course = json.load(open(dirpath + '/' + filename))

        print(f"{course['id']}-{course['term']}")

        sections = len(course['sections'])

        # collect the instructors in all sections
        instructors = set()
        for section in course['sections']:
            instructors.update(section['instructors'])

        profs = '; '.join(instructors)
        seats = sum([s['seats'] for s in course['sections']])
        try:
            open_seats = sum([s['open_seats'] for s in course['sections']])
        except:
            open_seats = sum([s['open-seats'] for s in course['sections']])

        filled_seats = seats-open_seats

        if 'syllabus_count' in course:
            syllabus_count = course['syllabus_count']
        else:
            syllabus_count = None

        output.writerow([
            course['id'],
            course['title'],
            course['description'],
            course['term'],
            course['department'],
            sections,
            profs,
            seats,
            open_seats,
            filled_seats,
            syllabus_count
        ])
