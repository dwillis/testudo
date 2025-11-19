# Semantic Search for UMD Courses

This implements **Option A** from the Semantic Search Plan: SQLite + sqlite-vss for semantic course search.

## Overview

Semantic search allows you to find courses using natural language queries that understand meaning and context, rather than just keyword matching.

**Example queries:**
- "machine learning courses" → Finds ML, neural networks, AI courses
- "web development" → Finds courses across departments
- "data science for beginners" → Finds introductory data science courses

## Implementation Details

- **Vector Database**: SQLite with sqlite-vss extension
- **Embeddings**: TF-IDF with SVD dimensionality reduction (384 dimensions)
- **Database**: ~4600 courses from UMD Spring 2025
- **Performance**: Sub-second search times

### Why TF-IDF?

Due to environment constraints preventing HuggingFace model downloads, we're using TF-IDF + SVD instead of sentence-transformers. This provides:
- ✅ Good search quality for course descriptions
- ✅ No external dependencies or model downloads
- ✅ Fast encoding and search
- ✅ Easy to upgrade to sentence-transformers later

## Quick Start

### 1. Create Database (if needed)

```bash
# Convert CSV to SQLite database
uv run python csv_to_db.py
```

### 2. Generate Embeddings

```bash
# Generate TF-IDF embeddings for all courses
uv run python generate_embeddings_tfidf.py
```

This creates:
- `course_embeddings` virtual table in the database
- `course_embedding_map` table linking embeddings to courses
- `tfidf_model.pkl` file for encoding queries

### 3. Search Courses

```bash
# Basic search
uv run python semantic_search.py "machine learning courses"

# Search with filters
uv run python semantic_search.py "web development" --term 202501

# Department filter
uv run python semantic_search.py "data science" --department "Computer Science" --limit 5

# Level filter
uv run python semantic_search.py "programming" --level "Undergrad"
```

## Usage Examples

### Basic Search

```bash
uv run python semantic_search.py "machine learning courses"
```

Output:
```
1. MSML605 - Computing Systems for Machine Learning
   Machine Learning | Grad | Term: 202501
   Relevance: 74.6%

2. PHIL408F - Topics in Contemporary Philosophy; A Gentle Introduction to Machine Learning
   Philosophy | Undergrad | Term: 202501
   Relevance: 49.5%
...
```

### Search with Filters

```bash
# Filter by term
uv run python semantic_search.py "artificial intelligence" --term 202501

# Filter by department
uv run python semantic_search.py "data analysis" --department "Computer Science"

# Filter by level
uv run python semantic_search.py "introduction to programming" --level "Undergrad"

# Limit results
uv run python semantic_search.py "databases" --limit 5
```

### Available Filters

- `--term`: Filter by term (e.g., 202501, 202508)
- `--department`: Filter by department name
- `--level`: Filter by level (Undergrad, Grad)
- `--limit`: Maximum number of results (default: 10)

## Python API

You can also use the search functionality in your own Python code:

```python
from semantic_search import CourseSemanticSearch

# Initialize searcher
searcher = CourseSemanticSearch(
    db_path='courses_specific_terms.db',
    model_path='tfidf_model.pkl'
)

# Basic search
results = searcher.search('machine learning', limit=10)

# Search with filters
filters = {
    'term': ['202501'],
    'department': 'Computer Science',
    'level': 'Grad'
}
results = searcher.search('data science', limit=5, filters=filters)

# Display results
for i, course in enumerate(results, 1):
    print(searcher.format_result(course, i))

# Close connection
searcher.close()
```

## Files

- `csv_to_db.py` - Convert CSV course data to SQLite database
- `generate_embeddings_tfidf.py` - Generate TF-IDF embeddings
- `generate_embeddings.py` - Generate sentence-transformer embeddings (requires HuggingFace access)
- `semantic_search.py` - Search interface (CLI and Python API)
- `tfidf_model.pkl` - Trained TF-IDF model (generated)
- `courses_specific_terms.db` - SQLite database with courses and embeddings (generated)

## Architecture

```
┌─────────────────────────────────────┐
│      semantic_search.py CLI         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│   CourseSemanticSearch Class        │
│   - encode_query()                  │
│   - search()                        │
│   - _vector_search()                │
└──────────────┬──────────────────────┘
               │
    ┌──────────┴──────────┐
    ▼                     ▼
┌─────────────┐   ┌──────────────────┐
│  SQLite DB  │   │  TF-IDF Model    │
│  + vss0     │   │  (tfidf_model)   │
└─────────────┘   └──────────────────┘
```

## Performance

- **Database size**: ~4600 courses
- **Embedding generation**: ~3 seconds
- **Query encoding**: <10ms
- **Vector search**: <100ms
- **Total search time**: <200ms

## Upgrading to Sentence Transformers

When HuggingFace access is available, you can upgrade to sentence-transformers:

```bash
# Generate new embeddings with sentence-transformers
uv run python generate_embeddings.py --overwrite

# Update semantic_search.py to use sentence-transformers
# (modify model loading in CourseSemanticSearch.__init__)
```

The infrastructure (database schema, search logic) is identical, only the embedding generation changes.

## Troubleshooting

### "Model file not found"
Run `generate_embeddings_tfidf.py` first to create embeddings.

### "Database not found"
Run `csv_to_db.py` first to create the database from CSV.

### No results found
- Try simpler queries
- Remove filters to see if they're too restrictive
- Check that courses exist for your filters (e.g., verify department name)

## Credits

- **sqlite-vss**: Vector similarity search for SQLite
- **scikit-learn**: TF-IDF and SVD implementation
- **Plan**: Based on SEMANTIC_SEARCH_PLAN.md Option A
