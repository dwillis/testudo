#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "scikit-learn"]
# ///
"""
Build static JSON data files and HTML for the Testudo Course Explorer.

Usage:
    uv run build_site.py
    uv run build_site.py --db courses.db --out site
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

DAY_PATTERN = re.compile(r'Tu|Th|Sa|Su|[MWFS]')
DAY_ORDER = ['M', 'Tu', 'W', 'Th', 'F', 'Sa', 'Su']
DAY_INDEX = {d: i for i, d in enumerate(DAY_ORDER)}

SLOT_START_HOUR = 7  # 7:00am
SLOT_END_HOUR = 22   # 10:00pm
SLOTS_PER_HOUR = 2
NUM_SLOTS = (SLOT_END_HOUR - SLOT_START_HOUR) * SLOTS_PER_HOUR  # 30


def get_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def parse_time(t):
    """Parse '11:00am' -> minutes since midnight."""
    if not t:
        return None
    t = t.strip().lower()
    m = re.match(r'(\d{1,2}):(\d{2})\s*(am|pm)', t)
    if not m:
        return None
    hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
    if ampm == 'pm' and hour != 12:
        hour += 12
    if ampm == 'am' and hour == 12:
        hour = 0
    return hour * 60 + minute


def time_to_slot(minutes):
    """Convert minutes since midnight to a 30-min slot index (0-based from 7am)."""
    slot = (minutes - SLOT_START_HOUR * 60) // 30
    if slot < 0 or slot >= NUM_SLOTS:
        return None
    return slot


def slot_to_label(slot):
    """Convert slot index to time label like '7:00am'."""
    minutes = SLOT_START_HOUR * 60 + slot * 30
    hour = minutes // 60
    minute = minutes % 60
    ampm = 'am' if hour < 12 else 'pm'
    if hour == 0:
        hour = 12
    elif hour > 12:
        hour -= 12
    return f"{hour}:{minute:02d}{ampm}"


def parse_days(days_str):
    """Parse 'MWF' -> ['M','W','F'], 'TuTh' -> ['Tu','Th']."""
    if not days_str:
        return []
    return DAY_PATTERN.findall(days_str)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, separators=(',', ':'))


def build_meta(db, out_dir):
    print("Building meta.json...")
    terms = [r[0] for r in db.execute(
        "SELECT DISTINCT term FROM courses ORDER BY term").fetchall()]
    departments = [dict(r) for r in db.execute(
        "SELECT DISTINCT department FROM courses WHERE department IS NOT NULL ORDER BY department").fetchall()]
    dept_list = [d['department'] for d in departments]
    levels = [r[0] for r in db.execute(
        "SELECT DISTINCT level FROM courses WHERE level IS NOT NULL AND level != '' ORDER BY level").fetchall()]

    meta = {"terms": terms, "departments": dept_list, "levels": levels}
    write_json(out_dir / "data" / "meta.json", meta)
    print(f"  {len(terms)} terms, {len(dept_list)} departments, {len(levels)} levels")
    return meta


def build_heatmap(db, out_dir, terms):
    print("Building heatmap data...")
    heatmap_dir = out_dir / "data" / "heatmap"

    # Deduplicate cross-listed sections: when different course IDs share the
    # same title, day, time, and instructor but span undergrad+grad levels,
    # they represent one physical class. We group by (term, title, section_id,
    # days, start, end) — using section_id keeps distinct sections (e.g., 18
    # lab sections of BSCI223) separate while merging cross-listed pairs like
    # JOUR456/JOUR656 that share a section number.
    rows = db.execute("""
        SELECT s.term, c.title, s.section_id, s.days, s.start_time, s.end_time, c.level
        FROM sections s
        JOIN courses c ON s.course_id = c.course_id AND s.term = c.term
        WHERE s.days != '' AND s.start_time != ''
    """).fetchall()

    print(f"  {len(rows)} raw sections with schedule data")

    # Group by (term, title, section_id, days, start, end) to merge cross-listings
    groups = {}
    for row in rows:
        key = (row['term'], row['title'], row['section_id'],
               row['days'], row['start_time'], row['end_time'])
        if key not in groups:
            groups[key] = set()
        groups[key].add(row['level'] or '')

    deduped = len(rows) - len(groups)
    print(f"  {len(groups)} unique course-slots after deduplicating {deduped} cross-listed sections")

    all_grid = make_empty_grid()
    all_by_level = {"Undergrad": make_empty_grid(), "Grad": make_empty_grid()}
    all_total = 0

    term_buckets = {}
    for (term, title, section_id, days, start_time, end_time), levels in groups.items():
        if term not in term_buckets:
            term_buckets[term] = []
        term_buckets[term].append((days, start_time, levels))

    for term in terms:
        bucket = term_buckets.get(term, [])
        grid = make_empty_grid()
        by_level = {"Undergrad": make_empty_grid(), "Grad": make_empty_grid()}
        total = 0

        for days_str, start_time, levels in bucket:
            days = parse_days(days_str)
            minutes = parse_time(start_time)
            if minutes is None:
                continue
            slot = time_to_slot(minutes)
            if slot is None:
                continue
            for day in days:
                di = DAY_INDEX.get(day)
                if di is None:
                    continue
                grid[di][slot] += 1
                all_grid[di][slot] += 1
                total += 1
                all_total += 1
                for level in levels:
                    if level in by_level:
                        by_level[level][di][slot] += 1
                    if level in all_by_level:
                        all_by_level[level][di][slot] += 1

        max_count = max(max(row) for row in grid) if total > 0 else 0
        write_json(heatmap_dir / f"{term}.json", {
            "term": term,
            "grid": grid,
            "byLevel": by_level,
            "maxCount": max_count,
            "totalSections": total
        })

    all_max = max(max(row) for row in all_grid) if all_total > 0 else 0
    write_json(heatmap_dir / "all.json", {
        "term": "all",
        "grid": all_grid,
        "byLevel": all_by_level,
        "maxCount": all_max,
        "totalSections": all_total
    })
    print(f"  Wrote {len(terms) + 1} heatmap files (all + per-term)")


def make_empty_grid():
    return [[0] * NUM_SLOTS for _ in range(7)]


def build_departments(db, out_dir):
    print("Building department data...")
    dept_dir = out_dir / "data" / "departments"

    depts = db.execute("""
        SELECT department,
               COUNT(DISTINCT course_id) as courses,
               COUNT(DISTINCT term) as terms,
               SUM(section_count) as sections
        FROM courses
        WHERE department IS NOT NULL
        GROUP BY department
        ORDER BY department
    """).fetchall()

    index = []
    for d in depts:
        code = dept_to_code(db, d['department'])
        index.append({
            "code": code,
            "name": d['department'],
            "courses": d['courses'],
            "sections": d['sections'] or 0,
            "terms": d['terms']
        })

    write_json(dept_dir / "_index.json", index)
    print(f"  {len(index)} departments in index")

    for entry in index:
        build_single_department(db, dept_dir, entry['name'], entry['code'])

    print(f"  Wrote {len(index)} department detail files")


def dept_to_code(db, dept_name):
    """Get the most common course prefix for a department name."""
    row = db.execute("""
        SELECT course_id FROM courses WHERE department = ? LIMIT 1
    """, (dept_name,)).fetchone()
    if row:
        m = re.match(r'^([A-Z]+)', row['course_id'])
        if m:
            return m.group(1)
    return dept_name[:4].upper()


def build_single_department(db, dept_dir, dept_name, code):
    course_rows = db.execute("""
        SELECT course_id, title, level, credits, term, section_count
        FROM courses WHERE department = ?
        ORDER BY course_id, term
    """, (dept_name,)).fetchall()

    courses = {}
    for r in course_rows:
        cid = r['course_id']
        if cid not in courses:
            courses[cid] = {
                "title": r['title'],
                "level": r['level'],
                "credits": r['credits'],
                "terms": {}
            }
        sc = r['section_count']
        if sc and sc > 0:
            courses[cid]["terms"][r['term']] = sc

    # Compute lifecycle: first/last term each course ran (had sections)
    for cid, c in courses.items():
        active_terms = sorted(c["terms"].keys())
        if active_terms:
            c["firstTerm"] = active_terms[0]
            c["lastTerm"] = active_terms[-1]
        else:
            c["firstTerm"] = None
            c["lastTerm"] = None

    # Per-term stats with new vs existing breakdown
    # First term in the dataset is baseline — we can't distinguish new from existing
    term_stats = []
    all_terms = sorted(set(r['term'] for r in course_rows))
    global_first_term = all_terms[0] if all_terms else None
    seen_courses = set()
    for term in all_terms:
        active = [cid for cid, c in courses.items()
                  if term in c["terms"]]
        new_this_term = [cid for cid in active if cid not in seen_courses]
        existing = [cid for cid in active if cid in seen_courses]
        seen_courses.update(active)

        is_baseline = (term == global_first_term)
        total_sections = sum(courses[cid]["terms"].get(term, 0) for cid in active)
        term_stats.append({
            "term": term,
            "courses": len(active),
            "sections": total_sections,
            "new": 0 if is_baseline else len(new_this_term),
            "existing": len(active) if is_baseline else len(existing),
            "baseline": is_baseline,
            "newCourses": [] if is_baseline else new_this_term[:10]
        })

    instructors = [dict(r) for r in db.execute("""
        SELECT s.instructors as name, COUNT(*) as count
        FROM sections s
        JOIN courses c ON s.course_id = c.course_id AND s.term = c.term
        WHERE c.department = ? AND s.instructors != ''
        GROUP BY s.instructors ORDER BY count DESC LIMIT 15
    """, (dept_name,)).fetchall()]

    write_json(dept_dir / f"{code}.json", {
        "name": dept_name,
        "code": code,
        "courses": courses,
        "termStats": term_stats,
        "instructors": instructors
    })


def build_similarity(db, out_dir):
    print("Building similarity data...")
    sim_dir = out_dir / "data" / "similarity"
    neighbors_dir = sim_dir / "neighbors"
    neighbors_dir.mkdir(parents=True, exist_ok=True)

    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD

    print("  Loading courses (deduplicated by course_id, latest term)...")
    rows = db.execute("""
        SELECT c.course_id, c.title, c.department, c.level, c.credits,
               c.description, c.grading_methods
        FROM courses c
        INNER JOIN (
            SELECT course_id, MAX(term) as max_term
            FROM courses GROUP BY course_id
        ) latest ON c.course_id = latest.course_id AND c.term = latest.max_term
        ORDER BY c.course_id
    """).fetchall()

    print(f"  {len(rows)} unique courses")

    course_ids = []
    course_meta = {}
    texts = []

    for r in rows:
        cid = r['course_id']
        course_ids.append(cid)
        desc = r['description'] or ''
        course_meta[cid] = {
            "title": r['title'] or '',
            "dept": r['department'] or '',
            "level": r['level'] or '',
            "credits": r['credits'] or '',
            "desc": desc[:120] + '...' if len(desc) > 120 else desc
        }
        parts = []
        if r['title']:
            parts.append(r['title'])
        if r['description']:
            desc = r['description']
            # Strip prerequisite/credit boilerplate that creates false similarity
            cleaned = []
            for line in desc.split('\n'):
                line = line.strip()
                if line.lower().startswith(('prerequisite:', 'corequisite:', 'restriction:',
                    'credit only granted', 'credit will be granted',
                    'additional information:', 'formerly:', 'also offered as:')):
                    continue
                if line:
                    cleaned.append(line)
            if cleaned:
                parts.append(' '.join(cleaned))
        texts.append(" ".join(parts))

    print("  Fitting TF-IDF + SVD...")
    vectorizer = TfidfVectorizer(
        max_features=1000,
        ngram_range=(1, 2),
        stop_words='english',
        lowercase=True,
        strip_accents='unicode'
    )
    tfidf_matrix = vectorizer.fit_transform(texts)

    svd = TruncatedSVD(n_components=384, random_state=42)
    embeddings = svd.fit_transform(tfidf_matrix)

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / (norms + 1e-10)

    print(f"  TF-IDF matrix: {tfidf_matrix.shape}, SVD: {embeddings.shape}")
    print("  Computing neighbors (batched)...")

    n = len(course_ids)
    batch_size = 500
    top_k = 10

    all_neighbors = {}
    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        batch = embeddings[start:end]
        sims = batch @ embeddings.T

        for i in range(end - start):
            global_i = start + i
            scores = sims[i]
            scores[global_i] = -1
            top_indices = np.argpartition(scores, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

            neighbors = []
            for idx in top_indices:
                neighbor_id = course_ids[idx]
                neighbors.append({
                    "id": neighbor_id,
                    "score": round(float(scores[idx]), 4),
                    "title": course_meta[neighbor_id]["title"],
                    "dept": course_meta[neighbor_id]["dept"]
                })
            all_neighbors[course_ids[global_i]] = neighbors

        if end % 2000 == 0 or end == n:
            print(f"    {end}/{n} courses processed")

    print("  Writing neighbor files...")
    for cid, neighbors in all_neighbors.items():
        write_json(neighbors_dir / f"{cid}.json", {
            "course_id": cid,
            "neighbors": neighbors
        })

    write_json(sim_dir / "_index.json", course_meta)
    print(f"  Wrote {len(all_neighbors)} neighbor files + index")


def build_overview(db, out_dir, meta):
    """Build overview.json with university-wide trends for the landing page."""
    import string
    print("Building overview data...")

    terms = meta['terms']

    # Per-term totals (only terms with active sections)
    term_totals = [dict(r) for r in db.execute("""
        SELECT term,
               COUNT(DISTINCT course_id) as courses,
               COUNT(DISTINCT department) as departments
        FROM courses WHERE section_count > 0
        GROUP BY term ORDER BY term
    """).fetchall()]

    # Headline stats
    total_courses = db.execute(
        "SELECT COUNT(DISTINCT course_id) FROM courses WHERE section_count > 0").fetchone()[0]
    total_depts = db.execute(
        "SELECT COUNT(DISTINCT department) FROM courses").fetchone()[0]
    total_sections = db.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    total_instructors = db.execute(
        "SELECT COUNT(DISTINCT instructors) FROM sections WHERE instructors != ''").fetchone()[0]

    # Latest fall/spring term (skip summer/winter for "latest" display)
    latest_major = None
    for t in reversed(terms):
        if t.endswith('01') or t.endswith('08'):
            latest_major = t
            break
    if not latest_major:
        latest_major = terms[-1]

    # New courses in the latest major term
    first_seen = {}
    for row in db.execute("""
        SELECT course_id, MIN(term) as first_term
        FROM courses WHERE section_count > 0 GROUP BY course_id
    """).fetchall():
        first_seen[row['course_id']] = row['first_term']

    latest_new = []
    for row in db.execute("""
        SELECT course_id, title, department, level, credits
        FROM courses WHERE term = ? AND section_count > 0
        ORDER BY course_id
    """, (latest_major,)).fetchall():
        if first_seen.get(row['course_id']) == latest_major:
            latest_new.append(dict(row))
    # Skip generic titles
    interesting_new = [c for c in latest_new if not c['title'].startswith(('Directed', 'Independent', 'Thesis', 'Dissertation'))]

    # Fastest growing departments (most new courses in last 4 major terms)
    recent_cutoff = sorted([t for t in terms if t.endswith('01') or t.endswith('08')])[-4:]
    cutoff_term = recent_cutoff[0] if recent_cutoff else terms[-1]
    growing_depts = [dict(r) for r in db.execute("""
        SELECT c.department as name, COUNT(DISTINCT c.course_id) as new_courses
        FROM courses c
        JOIN (
            SELECT course_id, MIN(term) as first_term
            FROM courses WHERE section_count > 0 GROUP BY course_id
        ) f ON c.course_id = f.course_id
        WHERE f.first_term >= ? AND c.section_count > 0
        GROUP BY c.department
        ORDER BY new_courses DESC LIMIT 10
    """, (cutoff_term,)).fetchall()]

    # Get dept codes for linking
    for d in growing_depts:
        row = db.execute("SELECT course_id FROM courses WHERE department = ? LIMIT 1",
                         (d['name'],)).fetchone()
        m = re.match(r'^([A-Z]+)', row['course_id']) if row else None
        d['code'] = m.group(1) if m else d['name'][:4].upper()

    # Peak schedule slot
    peak = db.execute("""
        SELECT s.days, s.start_time, COUNT(*) as cnt
        FROM sections s
        WHERE s.days != '' AND s.start_time != ''
        GROUP BY s.days, s.start_time
        ORDER BY cnt DESC LIMIT 1
    """).fetchone()
    peak_stat = {
        "days": peak['days'],
        "time": peak['start_time'],
        "count": peak['cnt']
    } if peak else None

    # Top keywords in new course titles (last 2 years)
    stop = set(string.ascii_lowercase) | {
        'the', 'and', 'for', 'in', 'of', 'to', 'a', 'an', 'on', 'at', 'is',
        'with', 'from', 'by', 'or', 'as', 'its', 'their', 'this', 'that',
        'topics', 'special', 'selected', 'advanced', 'introduction', 'seminar',
        'studies', 'course', 'directed', 'independent', 'research', 'thesis',
        'problems', 'science', 'i', 'ii', 'iii', 'iv',
    }
    word_counts = {}
    for c in latest_new:
        words = re.findall(r'[a-z]+', c['title'].lower())
        for w in set(words):
            if w not in stop and len(w) > 2:
                word_counts[w] = word_counts.get(w, 0) + 1
    top_keywords = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    overview = {
        "headline": {
            "totalCourses": total_courses,
            "totalDepts": total_depts,
            "totalSections": total_sections,
            "totalInstructors": total_instructors,
            "termsSpanned": len(terms),
            "firstTerm": terms[0],
            "lastTerm": terms[-1],
        },
        "termTotals": term_totals,
        "latestTerm": latest_major,
        "latestNewCount": len(latest_new),
        "latestNewSample": interesting_new[:8],
        "growingDepts": growing_depts,
        "growthSince": cutoff_term,
        "peakSlot": peak_stat,
        "topKeywords": top_keywords,
    }

    write_json(out_dir / "data" / "overview.json", overview)
    print(f"  Latest term: {latest_major} with {len(latest_new)} new courses")
    print(f"  {len(growing_depts)} fastest-growing depts, {len(top_keywords)} top keywords")


def main():
    parser = argparse.ArgumentParser(description="Build Testudo Course Explorer static site")
    parser.add_argument("--db", default="courses.db", help="SQLite database path")
    parser.add_argument("--out", default="docs", help="Output directory")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Error: database not found: {args.db}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    (out_dir / "data").mkdir(exist_ok=True)

    db = get_db(args.db)

    meta = build_meta(db, out_dir)
    build_overview(db, out_dir, meta)
    build_heatmap(db, out_dir, meta['terms'])
    build_departments(db, out_dir)
    build_similarity(db, out_dir)

    db.close()
    print("\nDone! Serve with: python -m http.server -d docs 8080")
    return 0


if __name__ == "__main__":
    sys.exit(main())
