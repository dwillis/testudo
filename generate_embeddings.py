#!/usr/bin/env python3
"""
Generate embeddings for course data and store them in sqlite-vss format.

This script implements Option A from the Semantic Search Plan:
- Uses sentence-transformers (all-MiniLM-L6-v2 model)
- Stores embeddings in sqlite-vss virtual tables
- Creates a mapping table to link embeddings to courses
"""

import sys
import logging
import argparse
import sqlite3
import struct
import numpy as np
from pathlib import Path
from typing import Dict, Any, List
from sentence_transformers import SentenceTransformer
import sqlite_utils
import sqlite_vss

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_course_text(course: Dict[str, Any]) -> str:
    """
    Create rich text representation for embedding generation.

    Combines course metadata into a single text string that captures
    the semantic meaning of the course.
    """
    parts = []

    # Add course title (most important)
    if course.get('title'):
        parts.append(f"Course: {course['title']}")

    # Add department and level for context
    if course.get('department'):
        parts.append(f"Department: {course['department']}")

    if course.get('level'):
        parts.append(f"Level: {course['level']}")

    # Add description (core content)
    if course.get('description'):
        parts.append(f"Description: {course['description']}")

    # Add general education categories if present
    if course.get('gen_ed'):
        parts.append(f"General Education: {course['gen_ed']}")

    # Add grading methods if present
    if course.get('grading_methods'):
        parts.append(f"Grading: {course['grading_methods']}")

    return " | ".join(parts)


def serialize_f32(vector: np.ndarray) -> bytes:
    """Serialize a numpy array of float32 values to bytes."""
    return struct.pack(f'{len(vector)}f', *vector)


def setup_vss_tables(db: sqlite3.Connection) -> None:
    """
    Set up sqlite-vss virtual tables and mapping tables.

    Creates:
    - course_embeddings: Virtual table for vector similarity search
    - course_embedding_map: Links embeddings to courses
    """
    logger.info("Setting up sqlite-vss tables...")

    # Enable loading extensions
    db.enable_load_extension(True)

    # Load sqlite-vss extension
    sqlite_vss.load(db)

    cursor = db.cursor()

    # Drop existing tables if they exist
    cursor.execute("DROP TABLE IF EXISTS course_embedding_map")
    cursor.execute("DROP TABLE IF EXISTS course_embeddings")

    # Create virtual table for embeddings (384 dimensions for all-MiniLM-L6-v2)
    cursor.execute("""
        CREATE VIRTUAL TABLE course_embeddings USING vss0(
            embedding(384)
        )
    """)

    # Create mapping table
    cursor.execute("""
        CREATE TABLE course_embedding_map (
            course_id TEXT,
            term TEXT,
            embedding_id INTEGER,
            PRIMARY KEY (course_id, term)
        )
    """)

    db.commit()
    logger.info("✓ sqlite-vss tables created")


def generate_embeddings(
    db_path: str = 'courses_specific_terms.db',
    model_name: str = 'all-MiniLM-L6-v2',
    batch_size: int = 32,
    overwrite: bool = False
) -> None:
    """
    Generate embeddings for all courses in the database.

    Args:
        db_path: Path to SQLite database
        model_name: Name of sentence-transformers model to use
        batch_size: Number of courses to process at once
        overwrite: Whether to overwrite existing embeddings
    """
    logger.info(f"Loading database: {db_path}")

    # Connect to database
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    # Check if embeddings already exist
    cursor = db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='course_embeddings'")
    if cursor.fetchone() and not overwrite:
        logger.error("Embeddings table already exists. Use --overwrite to recreate.")
        return

    # Set up vss tables
    setup_vss_tables(db)

    # Load sentence transformer model
    logger.info(f"Loading model: {model_name}")
    logger.info("(This may take a moment on first run as the model downloads...)")
    model = SentenceTransformer(model_name)
    logger.info("✓ Model loaded")

    # Get all courses
    cursor.execute("SELECT * FROM courses ORDER BY course_id, term")
    courses = [dict(row) for row in cursor.fetchall()]

    logger.info(f"Found {len(courses)} courses")
    logger.info("Generating embeddings...")

    # Process courses in batches
    all_texts = []
    course_keys = []

    for course in courses:
        text = create_course_text(course)
        all_texts.append(text)
        course_keys.append((course['course_id'], course['term']))

    # Generate embeddings in batches
    embeddings = []
    for i in range(0, len(all_texts), batch_size):
        batch_texts = all_texts[i:i + batch_size]
        batch_embeddings = model.encode(
            batch_texts,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        embeddings.extend(batch_embeddings)

        if (i + batch_size) % 500 == 0:
            logger.info(f"  Processed {min(i + batch_size, len(all_texts))}/{len(all_texts)} courses...")

    logger.info(f"✓ Generated {len(embeddings)} embeddings")

    # Insert embeddings and create mappings
    logger.info("Storing embeddings in database...")

    cursor = db.cursor()
    for idx, (embedding, (course_id, term)) in enumerate(zip(embeddings, course_keys)):
        # Insert into virtual table
        embedding_bytes = serialize_f32(embedding.astype(np.float32))
        cursor.execute(
            "INSERT INTO course_embeddings(rowid, embedding) VALUES (?, ?)",
            (idx, embedding_bytes)
        )

        # Insert into mapping table
        cursor.execute(
            "INSERT INTO course_embedding_map(course_id, term, embedding_id) VALUES (?, ?, ?)",
            (course_id, term, idx)
        )

        if (idx + 1) % 500 == 0:
            logger.info(f"  Stored {idx + 1}/{len(embeddings)} embeddings...")

    db.commit()
    logger.info("✓ Embeddings stored successfully")

    # Print summary
    print("\n" + "="*70)
    print("EMBEDDING GENERATION COMPLETE")
    print("="*70)
    print(f"  Total courses: {len(courses)}")
    print(f"  Total embeddings: {len(embeddings)}")
    print(f"  Model: {model_name}")
    print(f"  Embedding dimensions: 384")
    print(f"  Database: {db_path}")
    print("="*70)

    # Print sample queries
    print("\nNext steps:")
    print("  1. Use the semantic_search.py script to search courses")
    print("  2. Example: python semantic_search.py 'machine learning courses'")
    print("\nYou can verify the embeddings with:")
    print(f"  sqlite-utils tables {db_path}")
    print(f"  sqlite-utils query {db_path} 'SELECT COUNT(*) FROM course_embeddings'")

    db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate embeddings for course semantic search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate embeddings with default settings
  python generate_embeddings.py

  # Use a different model
  python generate_embeddings.py --model all-mpnet-base-v2

  # Overwrite existing embeddings
  python generate_embeddings.py --overwrite

  # Use a different database
  python generate_embeddings.py --db my_courses.db
        """
    )

    parser.add_argument(
        '--db',
        default='courses_specific_terms.db',
        help='Path to SQLite database (default: courses_specific_terms.db)'
    )

    parser.add_argument(
        '--model',
        default='all-MiniLM-L6-v2',
        help='Sentence transformer model name (default: all-MiniLM-L6-v2)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=32,
        help='Batch size for encoding (default: 32)'
    )

    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing embeddings'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check if database exists
    if not Path(args.db).exists():
        logger.error(f"Database not found: {args.db}")
        logger.info("Run csv_to_db.py first to create the database")
        return 1

    try:
        generate_embeddings(
            db_path=args.db,
            model_name=args.model,
            batch_size=args.batch_size,
            overwrite=args.overwrite
        )
        return 0
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        return 1


if __name__ == '__main__':
    sys.exit(main())
