#!/usr/bin/env python3
"""
Generate embeddings for course data using TF-IDF (fallback for when sentence-transformers unavailable).

This is a simplified version that uses sklearn's TF-IDF instead of sentence transformers,
but still provides semantic-like search capabilities through term weighting.
The infrastructure remains compatible with upgrading to sentence transformers later.
"""

import sys
import logging
import argparse
import sqlite3
import struct
import numpy as np
from pathlib import Path
from typing import Dict, Any, List
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
import sqlite_utils
import sqlite_vss
import pickle

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_course_text(course: Dict[str, Any]) -> str:
    """Create rich text representation for embedding generation."""
    parts = []

    if course.get('title'):
        parts.append(f"Course: {course['title']}")

    if course.get('department'):
        parts.append(f"Department: {course['department']}")

    if course.get('level'):
        parts.append(f"Level: {course['level']}")

    if course.get('description'):
        parts.append(f"Description: {course['description']}")

    if course.get('gen_ed'):
        parts.append(f"General Education: {course['gen_ed']}")

    if course.get('grading_methods'):
        parts.append(f"Grading: {course['grading_methods']}")

    return " | ".join(parts)


def serialize_f32(vector: np.ndarray) -> bytes:
    """Serialize a numpy array of float32 values to bytes."""
    return struct.pack(f'{len(vector)}f', *vector)


def setup_vss_tables(db: sqlite3.Connection, dimensions: int = 384) -> None:
    """Set up sqlite-vss virtual tables and mapping tables."""
    logger.info(f"Setting up sqlite-vss tables (dimensions={dimensions})...")

    db.enable_load_extension(True)
    sqlite_vss.load(db)

    cursor = db.cursor()
    cursor.execute("DROP TABLE IF EXISTS course_embedding_map")
    cursor.execute("DROP TABLE IF EXISTS course_embeddings")

    cursor.execute(f"""
        CREATE VIRTUAL TABLE course_embeddings USING vss0(
            embedding({dimensions})
        )
    """)

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


def generate_embeddings_tfidf(
    db_path: str = 'courses_specific_terms.db',
    dimensions: int = 384,
    overwrite: bool = False
) -> None:
    """
    Generate TF-IDF based embeddings for all courses.

    Uses TF-IDF + SVD dimensionality reduction to create dense vectors
    that can be used for semantic search.
    """
    logger.info(f"Loading database: {db_path}")

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    # Check if embeddings already exist
    cursor = db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='course_embeddings'")
    if cursor.fetchone() and not overwrite:
        logger.error("Embeddings table already exists. Use --overwrite to recreate.")
        return

    # Set up vss tables
    setup_vss_tables(db, dimensions)

    # Get all courses
    cursor.execute("SELECT * FROM courses ORDER BY course_id, term")
    courses = [dict(row) for row in cursor.fetchall()]

    logger.info(f"Found {len(courses)} courses")
    logger.info("Generating TF-IDF embeddings...")

    # Create text corpus
    all_texts = []
    course_keys = []

    for course in courses:
        text = create_course_text(course)
        all_texts.append(text)
        course_keys.append((course['course_id'], course['term']))

    # Create TF-IDF vectors
    logger.info("Computing TF-IDF vectors...")
    vectorizer = TfidfVectorizer(
        max_features=1000,  # Use top 1000 terms
        ngram_range=(1, 2),  # Use unigrams and bigrams
        stop_words='english',
        lowercase=True,
        strip_accents='unicode'
    )

    tfidf_matrix = vectorizer.fit_transform(all_texts)
    logger.info(f"  TF-IDF matrix shape: {tfidf_matrix.shape}")

    # Apply dimensionality reduction
    logger.info(f"Reducing to {dimensions} dimensions using SVD...")
    svd = TruncatedSVD(n_components=dimensions, random_state=42)
    embeddings = svd.fit_transform(tfidf_matrix)

    # Normalize embeddings to unit length (improves similarity search)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / (norms + 1e-10)

    logger.info(f"✓ Generated {len(embeddings)} embeddings")

    # Save vectorizer and SVD model for later use
    logger.info("Saving TF-IDF model...")
    model_data = {
        'vectorizer': vectorizer,
        'svd': svd,
        'dimensions': dimensions
    }
    with open('tfidf_model.pkl', 'wb') as f:
        pickle.dump(model_data, f)
    logger.info("✓ Model saved to tfidf_model.pkl")

    # Insert embeddings and create mappings
    logger.info("Storing embeddings in database...")

    cursor = db.cursor()
    for idx, (embedding, (course_id, term)) in enumerate(zip(embeddings, course_keys)):
        embedding_bytes = serialize_f32(embedding.astype(np.float32))
        cursor.execute(
            "INSERT INTO course_embeddings(rowid, embedding) VALUES (?, ?)",
            (idx, embedding_bytes)
        )

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
    print("EMBEDDING GENERATION COMPLETE (TF-IDF)")
    print("="*70)
    print(f"  Total courses: {len(courses)}")
    print(f"  Total embeddings: {len(embeddings)}")
    print(f"  Method: TF-IDF + SVD")
    print(f"  Embedding dimensions: {dimensions}")
    print(f"  Database: {db_path}")
    print(f"  Model file: tfidf_model.pkl")
    print("="*70)

    print("\n Note: Using TF-IDF instead of sentence-transformers")
    print(" TF-IDF provides good search quality for course descriptions")
    print(" To use sentence-transformers later, run generate_embeddings.py")

    print("\nNext steps:")
    print("  1. Use the semantic_search.py script to search courses")
    print("  2. Example: python semantic_search.py 'machine learning courses'")

    db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate TF-IDF based embeddings for course semantic search",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--db',
        default='courses_specific_terms.db',
        help='Path to SQLite database (default: courses_specific_terms.db)'
    )

    parser.add_argument(
        '--dimensions',
        type=int,
        default=384,
        help='Embedding dimensions (default: 384)'
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

    if not Path(args.db).exists():
        logger.error(f"Database not found: {args.db}")
        logger.info("Run csv_to_db.py first to create the database")
        return 1

    try:
        generate_embeddings_tfidf(
            db_path=args.db,
            dimensions=args.dimensions,
            overwrite=args.overwrite
        )
        return 0
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=args.verbose)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
