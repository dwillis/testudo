# /// script
# requires-python = ">=3.9"
# dependencies = ["fastapi", "uvicorn", "sqlite-vec", "llm", "llm-ollama"]
# ///
"""
Web-based semantic search API for UMD courses.

Usage:
    uv run app.py
    uv run app.py --port 8080
    uv run uvicorn app:app --reload --port 8000
"""

import argparse
import sqlite3
import struct
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import sqlite_vec
import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

DB_PATH = "courses.db"
MODEL_NAME = "nomic-embed-text"

# Module-level state populated at startup
_db: Optional[sqlite3.Connection] = None
_embed_model = None


def get_db() -> sqlite3.Connection:
    """Get a new connection with sqlite-vec loaded."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def serialize_f32(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db, _embed_model
    import llm

    # Load embedding model
    try:
        _embed_model = llm.get_embedding_model(MODEL_NAME)
    except llm.UnknownModelError:
        print(f"Error: embedding model '{MODEL_NAME}' not found.", file=sys.stderr)
        print(f"Make sure ollama is running: ollama pull {MODEL_NAME}", file=sys.stderr)
        sys.exit(1)

    # Test embedding
    try:
        test = list(_embed_model.embed("test"))
        print(f"Embedding model ready: {MODEL_NAME} ({len(test)} dims)")
    except Exception as e:
        print(f"Error: cannot connect to ollama: {e}", file=sys.stderr)
        sys.exit(1)

    # Open DB and verify vec0 table
    _db = get_db()
    vec_count = _db.execute("SELECT count(*) FROM course_vec_map").fetchone()[0]
    print(f"Database ready: {vec_count} vectors in course_vec")

    yield

    if _db:
        _db.close()


app = FastAPI(title="Testudo Semantic Search", lifespan=lifespan)


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/api/search")
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    term: Optional[str] = Query(None, description="Filter by term"),
    department: Optional[str] = Query(None, description="Filter by department"),
    level: Optional[str] = Query(None, description="Filter by level"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    import time

    t0 = time.time()

    # Embed query
    query_vec = serialize_f32(list(_embed_model.embed(q)))
    t_embed = time.time()

    # Search vec0 — over-fetch for post-filtering
    fetch_k = limit * 10 if (department or level) else limit

    if term:
        vec_rows = _db.execute(
            """
            SELECT rowid, distance
            FROM course_vec
            WHERE embedding MATCH ? AND k = ? AND term = ?
            ORDER BY distance
            """,
            (query_vec, fetch_k, term),
        ).fetchall()
    else:
        vec_rows = _db.execute(
            """
            SELECT rowid, distance
            FROM course_vec
            WHERE embedding MATCH ? AND k = ?
            ORDER BY distance
            """,
            (query_vec, fetch_k),
        ).fetchall()
    t_vec = time.time()

    if not vec_rows:
        return {"results": [], "timing": {"total_ms": 0}}

    # Join with course metadata
    rowids = [r["rowid"] for r in vec_rows]
    distances = {r["rowid"]: r["distance"] for r in vec_rows}

    placeholders = ",".join("?" * len(rowids))
    results_query = f"""
        SELECT m.rowid, c.course_id, c.term, c.title, c.department,
               c.level, c.credits, c.description
        FROM course_vec_map m
        JOIN courses c ON m.course_id = c.course_id AND m.term = c.term
        WHERE m.rowid IN ({placeholders})
    """

    # Add post-filters
    params = list(rowids)
    if department:
        results_query += " AND c.department = ?"
        params.append(department)
    if level:
        results_query += " AND c.level = ?"
        params.append(level)

    course_rows = _db.execute(results_query, params).fetchall()
    t_meta = time.time()

    # Build results sorted by distance
    results = []
    for row in course_rows:
        d = dict(row)
        rid = d.pop("rowid")
        dist = distances[rid]
        # Convert distance to cosine similarity (sqlite-vec returns cosine distance)
        d["score"] = round(1 - dist, 4)
        results.append(d)

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:limit]

    total_ms = round((time.time() - t0) * 1000)
    timing = {
        "embed_ms": round((t_embed - t0) * 1000),
        "vec_ms": round((t_vec - t_embed) * 1000),
        "meta_ms": round((t_meta - t_vec) * 1000),
        "total_ms": total_ms,
    }

    return {"results": results, "timing": timing, "count": len(results)}


@app.get("/api/terms")
async def terms():
    rows = _db.execute(
        "SELECT DISTINCT term FROM courses ORDER BY term DESC"
    ).fetchall()
    return [r["term"] for r in rows]


@app.get("/api/departments")
async def departments():
    rows = _db.execute(
        "SELECT DISTINCT department FROM courses WHERE department IS NOT NULL ORDER BY department"
    ).fetchall()
    return [r["department"] for r in rows]


@app.get("/api/levels")
async def levels():
    rows = _db.execute(
        "SELECT DISTINCT level FROM courses WHERE level IS NOT NULL AND level != '' ORDER BY level"
    ).fetchall()
    return [r["level"] for r in rows]


@app.get("/api/health")
async def health():
    try:
        test = list(_embed_model.embed("health check"))
        vec_count = _db.execute("SELECT count(*) FROM course_vec_map").fetchone()[0]
        return {"status": "ok", "vectors": vec_count, "dims": len(test)}
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)


# Serve static files (CSS, JS if we add them later)
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    uvicorn.run("app:app", host=args.host, port=args.port, reload=True)
