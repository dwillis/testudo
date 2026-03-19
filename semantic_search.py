# /// script
# requires-python = ">=3.9"
# dependencies = ["llm", "llm-ollama"]
# ///
"""
Semantic search over pre-computed course embeddings in SQLite.

Usage:
    uv run semantic_search.py "machine learning"
    uv run semantic_search.py "climate change policy" --top 20
    uv run semantic_search.py "data journalism" --term 202501
    uv run semantic_search.py "intro to programming" --department CMSC
    uv run semantic_search.py "machine learning" --csv results.csv
"""

import argparse
import csv
import sqlite3
import struct
import sys
from pathlib import Path


def deserialize_embedding(data):
    n = len(data) // 4
    return list(struct.unpack(f"{n}f", data))


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def main():
    parser = argparse.ArgumentParser(description="Semantic search over UMD courses")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--db", default="courses.db", help="Path to SQLite database")
    parser.add_argument("--model", default="nomic-embed-text", help="Embedding model (must match what was used to generate)")
    parser.add_argument("--top", type=int, default=10, help="Number of results")
    parser.add_argument("--term", help="Filter to a specific term (e.g. 202501)")
    parser.add_argument("--department", help="Filter to a department (e.g. CMSC)")
    parser.add_argument("--level", help="Filter by level (e.g. 'Upper Level', 'Graduate')")
    parser.add_argument("--csv", dest="csv_output", help="Export results to CSV file")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Error: database not found: {args.db}", file=sys.stderr)
        return 1

    import llm

    try:
        model = llm.get_embedding_model(args.model)
    except llm.UnknownModelError:
        print(f"Error: model '{args.model}' not found.", file=sys.stderr)
        return 1

    # Embed the query
    query_embedding = list(model.embed(args.query))

    # Load embeddings and course data from DB
    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row

    where_clauses = []
    params = []
    if args.term:
        where_clauses.append("e.term = ?")
        params.append(args.term)
    if args.department:
        where_clauses.append("c.department = ?")
        params.append(args.department)
    if args.level:
        where_clauses.append("c.level = ?")
        params.append(args.level)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        SELECT c.course_id, c.term, c.title, c.department, c.credits,
               c.level, c.description, e.embedding
        FROM embeddings e
        JOIN courses c ON e.course_id = c.course_id AND e.term = c.term
        {where_sql}
    """

    rows = db.execute(query, params).fetchall()
    if not rows:
        print("No courses found matching filters.", file=sys.stderr)
        return 1

    print(f"Searching {len(rows)} courses...", file=sys.stderr)

    # Score all courses
    results = []
    for row in rows:
        emb = deserialize_embedding(row["embedding"])
        score = cosine_similarity(query_embedding, emb)
        results.append((score, dict(row)))

    results.sort(key=lambda x: x[0], reverse=True)
    top_results = results[: args.top]

    # Remove embedding blob from output
    for _, r in top_results:
        r.pop("embedding", None)

    if args.csv_output:
        with open(args.csv_output, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["score", "course_id", "term", "title", "department", "level", "credits", "description"])
            for score, r in top_results:
                writer.writerow([
                    f"{score:.4f}", r["course_id"], r["term"], r["title"],
                    r["department"], r["level"], r["credits"], r["description"],
                ])
        print(f"Exported {len(top_results)} results to {args.csv_output}", file=sys.stderr)
    else:
        for i, (score, r) in enumerate(top_results, 1):
            desc = r["description"] or ""
            if len(desc) > 120:
                desc = desc[:120] + "..."
            print(f"{i:>3}. [{score:.4f}] {r['course_id']} ({r['term']}) - {r['title']}")
            print(f"     {r['department']} | {r['level']} | {r['credits']} credits")
            if desc:
                print(f"     {desc}")
            print()

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
