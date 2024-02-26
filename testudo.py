#!/usr/bin/env python3

import re
import os
import json
import time
import datetime

from urllib.parse import urljoin
from requests_html import HTMLSession

www = HTMLSession()
www.headers['user-agent'] = 'testudo.py <https://github.com/dwillis/testudo>'
sleep = 1

def main(term=None):
    for term in get_terms(active_only=True, term=term):
        print("getting term %s" % term)
        for dept in get_departments():
            print("getting courses in %s for %s" % (term, dept['id']))
            for course in get_courses(dept, term):
                json_file = os.path.join('data', term, dept['id'], course['id'] + '.json')
                print("writing %s" % json_file)
                json_dir = os.path.dirname(json_file)
                if not os.path.isdir(json_dir):
                    os.makedirs(json_dir)
                open(json_file, 'w').write(json.dumps(course, indent=2))

def get_terms(active_only=True, term=None):
    url = 'https://app.testudo.umd.edu/soc/'
    r = www.get(url)
    if term:
        terms = [term]
    else:
        terms = []
        for e in r.html.find('#term-id-input option'):
            terms.append(e.attrs['value'])
    return terms

def get_departments():
    url = 'https://app.testudo.umd.edu/soc/'
    r = www.get(url)
    depts = []
    for div in r.html.find('.course-prefix'):
        depts.append({
            'id': div.find('.prefix-abbrev', first=True).text,
            'name': div.find('.prefix-name', first=True).text
        })
    return depts

def get_courses(dept, term):
    url = 'https://app.testudo.umd.edu/soc/%s/%s' % (term, dept['id'])
    print('getting {}'.format(url))
    r = www.get(url)
    for div in r.html.find('.course'):
        yield get_course(dept, term, div)

def get_course(dept, term, div):
    course_id = div.find('.course-id', first=True).text
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    syllabus_text = [d for d in div.find('span') if re.findall(r'\(\d+\)', d.text)][0].text
    if syllabus_text == '(0)':
        syllabus_count = 0
    else:
        print(syllabus_text)
        syllabus_count = re.findall(r'\d+', syllabus_text)[0]
    return {
        'id': course_id,
        'title': div.find('.course-title', first=True).text,
        'credits': div.find('.course-min-credits', first=True).text,
        'description': t(div, '.approved-course-text') or t(div, '.course-text'),
        'grading-method': div.find('.grading-method', first=True).text.split(', '),
        'sections': get_sections(course_id, term),
        'term': term,
        'department': dept['name'],
        'syllabus_count': syllabus_count,
        'updated': now
    }

def get_sections(course_id, term):
    # 'https://app.testudo.umd.edu/soc/201801/sections?courseIds=AASP303'
    sections = []
    try:
        url = 'https://app.testudo.umd.edu/soc/%s/sections?courseIds=%s' % (term, course_id)
        r = www.get(url)
        r.html.encoding = r.encoding
        for div in r.html.find('.section'):
            sections.append({
                'id': t(div, '.section-id'),
                'instructors': [e.text for e in div.find('.section-instructor')],
                'seats': int(t(div, '.total-seats-count').strip(',')),
                'open-seats': int(t(div, '.open-seats-count').strip(',')),
                'waitlist': int(t(div, '.waitlist-count')),
                'days': t(div, '.section-days'),
                'start': t(div, '.class-start-time').strip(' -'),
                'end': t(div, '.class-end-time'),
                'building': t(div, '.building-code'),
                'room': t(div, '.class-room'),
            })
    except Exception as e:
        print(e)

    # be nice and sleep between requests for each class
    if sleep:
        time.sleep(sleep)
    return sections

def t(element, selector):
    e = element.find(selector, first=True)
    if e:
        return e.text
    else:
        return ''

if __name__ == '__main__':
    main()
