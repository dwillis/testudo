# /// script
# requires-python = ">=3.9"
# dependencies = ["llm", "llm-ollama", "sqlite-utils"]
# ///
"""
Generate course embeddings using nomic-embed-text via llm + ollama.

Usage:
    uv run generate_embeddings_llm.py
    uv run generate_embeddings_llm.py --db courses.db --batch-size 50
    uv run generate_embeddings_llm.py --limit 100  # test with a small subset
"""

import argparse
import json
import sqlite3
import struct
import sys
import time
from pathlib import Path


def create_course_text(course):
    """Create rich text representation for embedding generation."""
    parts = []
    if course["title"]:
        parts.append(f"Course: {course['title']}")
    if course["department"]:
        parts.append(f"Department: {course['department']}")
    if course["level"]:
        parts.append(f"Level: {course['level']}")
    if course["description"]:
        parts.append(f"Description: {course['description']}")
    if course.get("grading_methods"):
        parts.append(f"Grading: {course['grading_methods']}")
    return " | ".join(parts)


def serialize_embedding(vector):
    """Serialize a list of floats to bytes (float32)."""
    return struct.pack(f"{len(vector)}f", *vector)


def deserialize_embedding(data):
    """Deserialize bytes back to a list of floats."""
    n = len(data) // 4
    return list(struct.unpack(f"{n}f", data))


def main():
    parser = argparse.ArgumentParser(description="Generate course embeddings via llm + ollama")
    parser.add_argument("--db", default="courses.db", help="Path to SQLite database")
    parser.add_argument("--model", default="nomic-embed-text", help="Ollama embedding model name")
    parser.add_argument("--batch-size", type=int, default=40, help="Batch size for embedding")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of courses (0 = all)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing embeddings")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Error: database not found: {args.db}", file=sys.stderr)
        return 1

    import llm

    # Get the embedding model
    try:
        model = llm.get_embedding_model(args.model)
    except llm.UnknownModelError:
        print(f"Error: model '{args.model}' not found.", file=sys.stderr)
        print("Make sure ollama is running and the model is pulled:", file=sys.stderr)
        print(f"  ollama pull {args.model}", file=sys.stderr)
        return 1

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row

    # Check for existing embeddings
    cursor = db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'")
    if cursor.fetchone() and not args.overwrite:
        print("Embeddings table already exists. Use --overwrite to recreate.", file=sys.stderr)
        return 1

    # Create embeddings table
    cursor.execute("DROP TABLE IF EXISTS embeddings")
    cursor.execute("""
        CREATE TABLE embeddings (
            course_id TEXT,
            term TEXT,
            embedding BLOB,
            model TEXT,
            PRIMARY KEY (course_id, term)
        )
    """)
    db.commit()

    # Load courses
    query = "SELECT * FROM courses ORDER BY course_id, term"
    if args.limit:
        query += f" LIMIT {args.limit}"
    courses = [dict(row) for row in cursor.execute(query).fetchall()]
    total = len(courses)
    print(f"Found {total} courses in {args.db}")

    # Generate embeddings in batches
    start = time.time()
    inserted = 0

    for i in range(0, total, args.batch_size):
        batch = courses[i : i + args.batch_size]
        texts = [create_course_text(c) for c in batch]

        # llm's embed_multi returns list of embedding vectors
        embeddings = list(model.embed_multi(texts))

        for course, embedding in zip(batch, embeddings):
            cursor.execute(
                "INSERT INTO embeddings (course_id, term, embedding, model) VALUES (?, ?, ?, ?)",
                (
                    course["course_id"],
                    course["term"],
                    serialize_embedding(embedding),
                    args.model,
                ),
            )
            inserted += 1

        elapsed = time.time() - start
        rate = inserted / elapsed if elapsed > 0 else 0
        print(f"  {inserted}/{total} ({rate:.0f} courses/sec)", end="\r")

    db.commit()
    elapsed = time.time() - start

    # Get embedding dimensions from first row
    row = cursor.execute("SELECT embedding FROM embeddings LIMIT 1").fetchone()
    dims = len(row[0]) // 4 if row else 0

    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Courses:    {inserted}")
    print(f"  Model:      {args.model}")
    print(f"  Dimensions: {dims}")
    print(f"  DB size:    {Path(args.db).stat().st_size / 1024 / 1024:.1f} MB")

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
