#!/usr/bin/env python3
"""
Semantic search for University of Maryland courses.

Provides natural language search over course data using vector embeddings.
Supports both TF-IDF and sentence-transformer based embeddings.
"""

import sys
import argparse
import sqlite3
import struct
import pickle
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional
import sqlite_utils
import sqlite_vss


def serialize_f32(vector: np.ndarray) -> bytes:
    """Serialize a numpy array of float32 values to bytes."""
    return struct.pack(f'{len(vector)}f', *vector)


class CourseSemanticSearch:
    """Semantic search for course data using vector embeddings."""

    def __init__(
        self,
        db_path: str = 'courses_specific_terms.db',
        model_path: str = 'tfidf_model.pkl'
    ):
        """
        Initialize semantic search.

        Args:
            db_path: Path to SQLite database with embeddings
            model_path: Path to embedding model (for query encoding)
        """
        self.db_path = db_path
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row

        # Enable sqlite-vss
        self.db.enable_load_extension(True)
        sqlite_vss.load(self.db)

        # Load embedding model
        self.model_type = 'tfidf'
        self.model_data = None

        if Path(model_path).exists():
            with open(model_path, 'rb') as f:
                self.model_data = pickle.load(f)
                print(f"Loaded TF-IDF model (dimensions={self.model_data['dimensions']})")
        else:
            raise FileNotFoundError(f"Model file not found: {model_path}")

    def _encode_query_tfidf(self, query: str) -> np.ndarray:
        """Encode query using TF-IDF model."""
        # Transform query using trained vectorizer
        tfidf_vector = self.model_data['vectorizer'].transform([query])

        # Apply SVD transformation
        embedding = self.model_data['svd'].transform(tfidf_vector)

        # Normalize to unit length
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding[0]

    def encode_query(self, query: str) -> np.ndarray:
        """Encode query text into embedding vector."""
        if self.model_type == 'tfidf':
            return self._encode_query_tfidf(query)
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")

    def _vector_search(self, embedding: np.ndarray, k: int = 20) -> List[Dict[str, Any]]:
        """
        Find k most similar courses using vector search.

        Args:
            embedding: Query embedding vector
            k: Number of results to return

        Returns:
            List of course dictionaries with distance scores
        """
        embedding_bytes = serialize_f32(embedding.astype(np.float32))

        # Use sqlite-vss for vector similarity search
        query = """
            SELECT
                c.*,
                distance
            FROM course_embeddings e
            JOIN course_embedding_map m ON e.rowid = m.embedding_id
            JOIN courses c ON m.course_id = c.course_id
                          AND m.term = c.term
            WHERE vss_search(
                e.embedding,
                vss_search_params(?, ?)
            )
            ORDER BY distance ASC
        """

        cursor = self.db.execute(query, [embedding_bytes, k])
        results = [dict(row) for row in cursor.fetchall()]

        return results

    def _apply_filters(
        self,
        results: List[Dict[str, Any]],
        filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply structured filters to search results."""
        filtered = results

        if 'term' in filters:
            terms = filters['term'] if isinstance(filters['term'], list) else [filters['term']]
            filtered = [r for r in filtered if r['term'] in terms]

        if 'department' in filters:
            filtered = [r for r in filtered if r['department'] == filters['department']]

        if 'level' in filters:
            filtered = [r for r in filtered if r['level'] == filters['level']]

        if 'min_credits' in filters:
            filtered = [r for r in filtered
                       if r.get('credits') and float(r['credits']) >= filters['min_credits']]

        return filtered

    def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search courses using semantic similarity.

        Args:
            query: Natural language search query
            limit: Maximum number of results
            filters: Dict of filters (term, department, level, etc.)

        Returns:
            List of courses ranked by relevance
        """
        # Generate embedding for query
        query_embedding = self.encode_query(query)

        # Search similar embeddings (get more than needed for filtering)
        results = self._vector_search(query_embedding, k=limit * 3)

        # Apply filters if provided
        if filters:
            results = self._apply_filters(results, filters)

        # Return top results
        return results[:limit]

    def format_result(self, course: Dict[str, Any], index: int) -> str:
        """Format a search result for display."""
        lines = []
        lines.append(f"\n{index}. {course['course_id']} - {course['title']}")

        # Add metadata
        metadata = []
        if course.get('department'):
            metadata.append(course['department'])
        if course.get('level'):
            metadata.append(course['level'])
        if course.get('credits'):
            metadata.append(f"{course['credits']} credits")
        if course.get('term'):
            metadata.append(f"Term: {course['term']}")

        if metadata:
            lines.append(f"   {' | '.join(metadata)}")

        # Add description (truncated)
        if course.get('description'):
            desc = course['description']
            if len(desc) > 200:
                desc = desc[:197] + "..."
            lines.append(f"   {desc}")

        # Add relevance score
        if 'distance' in course:
            # Convert distance to similarity percentage (lower distance = higher similarity)
            similarity = max(0, 1 - course['distance']) * 100
            lines.append(f"   Relevance: {similarity:.1f}%")

        return '\n'.join(lines)

    def close(self):
        """Close database connection."""
        self.db.close()


def main():
    parser = argparse.ArgumentParser(
        description='Semantic search for UMD courses',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search
  python semantic_search.py "machine learning courses"

  # Search with term filter
  python semantic_search.py "web development" --term 202501

  # Search with department filter
  python semantic_search.py "data science" --department "Computer Science" --limit 5

  # Search with level filter
  python semantic_search.py "introduction to programming" --level "Lower Level"

  # Multiple terms
  python semantic_search.py "artificial intelligence" --term 202501 202508
        """
    )

    parser.add_argument(
        'query',
        help='Search query (natural language)'
    )

    parser.add_argument(
        '--db',
        default='courses_specific_terms.db',
        help='Path to database (default: courses_specific_terms.db)'
    )

    parser.add_argument(
        '--model',
        default='tfidf_model.pkl',
        help='Path to embedding model (default: tfidf_model.pkl)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Maximum number of results (default: 10)'
    )

    parser.add_argument(
        '--term',
        nargs='+',
        help='Filter by term(s)'
    )

    parser.add_argument(
        '--department',
        help='Filter by department'
    )

    parser.add_argument(
        '--level',
        help='Filter by level (e.g., "Lower Level", "Upper Level", "Grad")'
    )

    parser.add_argument(
        '--min-credits',
        type=float,
        help='Minimum number of credits'
    )

    args = parser.parse_args()

    # Check if database exists
    if not Path(args.db).exists():
        print(f"Error: Database not found: {args.db}")
        print("Run csv_to_db.py first to create the database")
        return 1

    # Check if model exists
    if not Path(args.model).exists():
        print(f"Error: Model file not found: {args.model}")
        print("Run generate_embeddings_tfidf.py first to create embeddings")
        return 1

    try:
        # Initialize search
        searcher = CourseSemanticSearch(args.db, args.model)

        # Build filters
        filters = {}
        if args.term:
            filters['term'] = args.term
        if args.department:
            filters['department'] = args.department
        if args.level:
            filters['level'] = args.level
        if args.min_credits:
            filters['min_credits'] = args.min_credits

        # Perform search
        print(f"\nSearching for: '{args.query}'")
        if filters:
            print(f"Filters: {filters}")
        print("="*70)

        results = searcher.search(args.query, limit=args.limit, filters=filters)

        # Display results
        if not results:
            print("\nNo results found.")
        else:
            print(f"\nFound {len(results)} results:\n")
            for i, course in enumerate(results, 1):
                print(searcher.format_result(course, i))

        print("\n" + "="*70)

        searcher.close()
        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
