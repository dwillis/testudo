# /// script
# requires-python = ">=3.9"
# dependencies = ["sqlite-vec"]
# ///
"""
Migrate existing BLOB embeddings into a sqlite-vec vec0 virtual table.

Usage:
    uv run migrate_to_vec.py
    uv run migrate_to_vec.py --db courses.db
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Migrate embeddings to sqlite-vec vec0 table")
    parser.add_argument("--db", default="courses.db", help="Path to SQLite database")
    parser.add_argument("--overwrite", action="store_true", help="Drop and recreate vec0 table")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Error: database not found: {args.db}", file=sys.stderr)
        return 1

    import sqlite_vec

    db = sqlite3.connect(args.db)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)

    cursor = db.cursor()

    # Check source data
    count = cursor.execute("SELECT count(*) FROM embeddings").fetchone()[0]
    if count == 0:
        print("Error: no embeddings found in database", file=sys.stderr)
        return 1

    # Check embedding dimensions
    sample = cursor.execute("SELECT embedding FROM embeddings LIMIT 1").fetchone()[0]
    dims = len(sample) // 4
    print(f"Source: {count} embeddings, {dims} dimensions")

    # Check if vec0 table already exists
    existing = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='course_vec'"
    ).fetchone()
    if existing and not args.overwrite:
        print("course_vec table already exists. Use --overwrite to recreate.", file=sys.stderr)
        return 1

    if existing:
        cursor.execute("DROP TABLE course_vec")
        cursor.execute("DROP TABLE IF EXISTS course_vec_map")
        db.commit()

    # Create vec0 virtual table with term as partition key and cosine distance
    cursor.execute(f"""
        CREATE VIRTUAL TABLE course_vec USING vec0(
            embedding float[{dims}] distance_metric=cosine,
            term text partition key
        )
    """)

    # Create mapping table (vec0 rowids -> course_id, term)
    cursor.execute("""
        CREATE TABLE course_vec_map (
            rowid INTEGER PRIMARY KEY,
            course_id TEXT NOT NULL,
            term TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX idx_vec_map_lookup ON course_vec_map(course_id, term)")
    db.commit()

    # Migrate embeddings
    start = time.time()
    rows = cursor.execute(
        "SELECT course_id, term, embedding FROM embeddings ORDER BY course_id, term"
    ).fetchall()

    batch_size = 500
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        for j, (course_id, term, embedding_blob) in enumerate(batch):
            rowid = i + j + 1  # 1-based
            cursor.execute(
                "INSERT INTO course_vec(rowid, embedding, term) VALUES (?, ?, ?)",
                (rowid, embedding_blob, term),
            )
            cursor.execute(
                "INSERT INTO course_vec_map(rowid, course_id, term) VALUES (?, ?, ?)",
                (rowid, course_id, term),
            )
        db.commit()
        elapsed = time.time() - start
        rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
        print(f"  {i + len(batch)}/{count} ({rate:.0f}/sec)", end="\r")

    elapsed = time.time() - start

    # Verify
    vec_count = cursor.execute("SELECT count(*) FROM course_vec_map").fetchone()[0]
    db_size = Path(args.db).stat().st_size / 1024 / 1024

    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Migrated:   {vec_count} vectors")
    print(f"  Dimensions: {dims}")
    print(f"  DB size:    {db_size:.1f} MB")

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
