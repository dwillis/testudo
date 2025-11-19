# Semantic Search Implementation Plan for Testudo Course Data

## Executive Summary

This document outlines a comprehensive plan to enable semantic search across University of Maryland course data. Semantic search allows users to find courses using natural language queries that understand meaning and context, rather than just keyword matching.

**Example Use Cases:**
- "Find courses about artificial intelligence and neural networks" → Returns CMSC courses even if they don't use exact keywords
- "What classes teach web development?" → Finds courses across departments (CMSC, INST, INFO)
- "Machine learning courses for beginners" → Filters by course level and topic
- "Database classes taught in Spring 2025" → Combines semantic search with structured filtering

---

## 1. Traditional Search vs Semantic Search

### Traditional (Keyword-Based) Search
```sql
SELECT * FROM courses
WHERE title LIKE '%machine learning%'
   OR description LIKE '%machine learning%'
```

**Limitations:**
- Misses courses that discuss ML concepts without using exact terms
- No understanding of synonyms (ML, neural networks, deep learning)
- Can't handle conceptual queries ("courses about AI ethics")
- No relevance ranking based on semantic similarity

### Semantic Search
Uses embeddings (vector representations) to understand meaning:
- "machine learning" matches courses about "neural networks", "deep learning", "AI"
- Can answer conceptual questions: "What courses prepare me for data science?"
- Ranks results by semantic relevance
- Handles typos and variations better

---

## 2. Technology Stack Options

### Option A: SQLite + sqlite-vss (Recommended for Simplicity)

**Pros:**
- Minimal infrastructure (extends existing SQLite database)
- Easy to deploy and maintain
- No external services required
- Works offline

**Cons:**
- Limited scalability (< 1M vectors)
- Slower than specialized vector DBs for large datasets
- Basic similarity search features

**Stack:**
```python
sqlite-vss          # Vector similarity search extension
sentence-transformers  # Generate embeddings
sqlite-utils        # Database management (already in use)
```

**Database Schema:**
```sql
-- Existing courses table
CREATE TABLE courses (...);

-- New embeddings table
CREATE VIRTUAL TABLE course_embeddings
USING vss0(
    course_embedding(384)  -- 384-dimensional vectors
);

-- Links embeddings to courses
CREATE TABLE course_embedding_map (
    course_id TEXT,
    term TEXT,
    embedding_id INTEGER,
    PRIMARY KEY (course_id, term)
);
```

### Option B: PostgreSQL + pgvector

**Pros:**
- More powerful than SQLite for concurrent users
- Better indexing (HNSW, IVFFlat)
- Scales to millions of vectors
- Rich query capabilities (hybrid search)

**Cons:**
- Requires PostgreSQL server setup
- More complex deployment
- Overkill for current dataset size

**Stack:**
```
PostgreSQL + pgvector extension
sentence-transformers
psycopg2
```

### Option C: Dedicated Vector Database (Qdrant, Weaviate, Pinecone)

**Pros:**
- Optimized for vector search
- Advanced features (filters, multi-vector search)
- Horizontal scalability
- Cloud-hosted options

**Cons:**
- Additional infrastructure complexity
- Potential costs for cloud services
- Over-engineered for current use case

**Recommendation:** Start with **Option A (SQLite + sqlite-vss)** for simplicity, migrate to Option B if scaling needs arise.

---

## 3. Embedding Model Selection

### Recommended Model: `all-MiniLM-L6-v2`

**Specifications:**
- Dimensions: 384
- Speed: Very fast (~14,000 sentences/sec on CPU)
- Quality: Good for general semantic similarity
- Size: 80 MB
- License: Apache 2.0

**Alternatives:**
```
all-mpnet-base-v2       # Higher quality, slower (768 dim)
paraphrase-MiniLM-L3-v2 # Faster, lower quality (384 dim)
instructor-base         # Task-specific instructions (768 dim)
```

### What to Embed

For each course, create a rich text representation:

```python
def create_course_text(course):
    """Create text for embedding generation."""
    parts = [
        f"Course: {course['title']}",
        f"Department: {course['department']}",
        f"Level: {course['level']}",
        f"Description: {course['description']}",
    ]

    # Add general education categories if present
    if course['gen_ed']:
        parts.append(f"General Education: {course['gen_ed']}")

    # Add instructor names for instructor-based search
    if course['instructors']:
        parts.append(f"Instructors: {course['instructors']}")

    return " | ".join(parts)
```

**Example:**
```
Course: Introduction to Data Science | Department: Computer Science |
Level: Upper Level | Description: An introduction to data science,
covering data manipulation, visualization, and machine learning basics.
Topics include Python programming, pandas, matplotlib, and scikit-learn. |
General Education: DSSP
```

---

## 4. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface Layer                     │
│  (CLI tool, Web API, or Python library)                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Search Service Layer                        │
│  - Query processing                                          │
│  - Embedding generation (sentence-transformers)              │
│  - Hybrid search (semantic + filters)                        │
│  - Result ranking and formatting                             │
└────────────────────┬────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
┌─────────────────────┐  ┌────────────────────┐
│  SQLite Database    │  │ Embedding Model    │
│  - courses table    │  │ (local or cached)  │
│  - sections table   │  │                    │
│  - embeddings (vss) │  │                    │
└─────────────────────┘  └────────────────────┘
```

---

## 5. Implementation Steps

### Phase 1: Data Preparation (Week 1)

**Step 1.1: Generate Embeddings**
```python
# File: generate_embeddings.py
from sentence_transformers import SentenceTransformer
import sqlite_utils
import numpy as np

model = SentenceTransformer('all-MiniLM-L6-v2')
db = sqlite_utils.Database('courses_specific_terms.db')

courses = db['courses'].rows

for course in courses:
    # Create rich text representation
    text = create_course_text(course)

    # Generate embedding
    embedding = model.encode(text)

    # Store in database (to be implemented with sqlite-vss)
    store_embedding(course['course_id'], course['term'], embedding)
```

**Step 1.2: Set up sqlite-vss**
```bash
pip install sqlite-vss
```

```python
# Initialize vector search
import sqlite_vss

db.enable_load_extension(True)
sqlite_vss.load(db.conn)

# Create virtual table for embeddings
db.executescript("""
    CREATE VIRTUAL TABLE IF NOT EXISTS course_embeddings
    USING vss0(embedding(384));
""")
```

### Phase 2: Search Interface (Week 2)

**Step 2.1: Create Search Service**
```python
# File: semantic_search.py

class CourseSemanticSearch:
    def __init__(self, db_path, model_name='all-MiniLM-L6-v2'):
        self.db = sqlite_utils.Database(db_path)
        self.model = SentenceTransformer(model_name)

    def search(self, query, limit=10, filters=None):
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
        query_embedding = self.model.encode(query)

        # Search similar embeddings
        results = self._vector_search(query_embedding, limit * 2)

        # Apply filters
        if filters:
            results = self._apply_filters(results, filters)

        # Return top results
        return results[:limit]

    def _vector_search(self, embedding, k=20):
        """Find k most similar courses using vector search."""
        # Using sqlite-vss
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

        return self.db.execute(query, [
            embedding.tobytes(),
            k
        ]).fetchall()

    def _apply_filters(self, results, filters):
        """Apply structured filters to results."""
        filtered = results

        if 'term' in filters:
            filtered = [r for r in filtered if r['term'] in filters['term']]

        if 'department' in filters:
            filtered = [r for r in filtered if r['department'] == filters['department']]

        if 'level' in filters:
            filtered = [r for r in filtered if r['level'] == filters['level']]

        if 'min_credits' in filters:
            filtered = [r for r in filtered
                       if float(r['credits']) >= filters['min_credits']]

        return filtered
```

**Step 2.2: Create CLI Tool**
```python
# File: search_cli.py

def main():
    parser = argparse.ArgumentParser(description='Semantic course search')
    parser.add_argument('query', help='Search query')
    parser.add_argument('--term', help='Filter by term(s)', nargs='+')
    parser.add_argument('--department', help='Filter by department')
    parser.add_argument('--level', help='Filter by level')
    parser.add_argument('--limit', type=int, default=10)

    args = parser.parse_args()

    searcher = CourseSemanticSearch('courses_specific_terms.db')

    filters = {}
    if args.term:
        filters['term'] = args.term
    if args.department:
        filters['department'] = args.department
    if args.level:
        filters['level'] = args.level

    results = searcher.search(args.query, limit=args.limit, filters=filters)

    # Display results
    for i, course in enumerate(results, 1):
        print(f"\n{i}. {course['course_id']} - {course['title']}")
        print(f"   {course['department']} | {course['level']} | {course['credits']} credits")
        print(f"   Term: {course['term']}")
        print(f"   {course['description'][:200]}...")
        if 'distance' in course:
            print(f"   Relevance: {1 - course['distance']:.2%}")
```

**Usage Examples:**
```bash
# Basic search
python search_cli.py "machine learning courses"

# Search with filters
python search_cli.py "web development" --term 202501 202508

# Department-specific search
python search_cli.py "data science" --department "Computer Science" --limit 5

# Level filter
python search_cli.py "introduction to programming" --level "Lower Level"
```

### Phase 3: Advanced Features (Week 3-4)

**Step 3.1: Hybrid Search (Semantic + Keyword)**
```python
def hybrid_search(self, query, limit=10, alpha=0.7):
    """
    Combine semantic and keyword search.

    Args:
        alpha: Weight for semantic search (0=keyword only, 1=semantic only)
    """
    # Semantic search results
    semantic_results = self.search(query, limit=limit * 2)

    # Keyword search results
    keyword_results = self._keyword_search(query, limit=limit * 2)

    # Combine and re-rank using alpha weighting
    combined = self._combine_results(semantic_results, keyword_results, alpha)

    return combined[:limit]

def _keyword_search(self, query, limit=20):
    """Traditional SQL full-text search."""
    sql = """
        SELECT *,
               (title LIKE ? OR description LIKE ?) as relevance
        FROM courses
        WHERE title LIKE ? OR description LIKE ?
        ORDER BY relevance DESC
        LIMIT ?
    """
    pattern = f"%{query}%"
    return self.db.execute(sql, [pattern, pattern, pattern, pattern, limit]).fetchall()
```

**Step 3.2: Query Understanding**
```python
def extract_filters_from_query(query):
    """Extract structured filters from natural language query."""
    filters = {}

    # Extract term mentions
    term_patterns = r'(spring|fall|summer|winter)\s+(\d{4})'
    if match := re.search(term_patterns, query.lower()):
        season, year = match.groups()
        term_code = f"{year}{season_to_code(season)}"
        filters['term'] = [term_code]

    # Extract level mentions
    if 'beginner' in query.lower() or 'introductory' in query.lower():
        filters['level'] = 'Lower Level'
    elif 'advanced' in query.lower() or 'graduate' in query.lower():
        filters['level'] = 'Grad'

    # Extract department mentions
    dept_map = {
        'computer science': 'Computer Science',
        'cs': 'Computer Science',
        'math': 'Mathematics',
        # ... more mappings
    }
    for key, dept in dept_map.items():
        if key in query.lower():
            filters['department'] = dept
            break

    return filters
```

**Step 3.3: Multi-Field Search**
```python
def search_instructors(self, instructor_name, limit=10):
    """Find courses taught by specific instructor."""
    # Embed instructor query
    query_embedding = self.model.encode(f"Instructor: {instructor_name}")

    # Search + filter for instructor
    results = self._vector_search(query_embedding, limit * 3)

    # Filter by instructor name match
    return [r for r in results
            if r['instructors'] and instructor_name.lower() in r['instructors'].lower()][:limit]
```

### Phase 4: Evaluation and Optimization (Week 4)

**Step 4.1: Evaluate Search Quality**
```python
# Create test queries and expected results
test_cases = [
    {
        'query': 'machine learning neural networks',
        'expected_courses': ['CMSC421', 'CMSC422', 'CMSC426'],
    },
    {
        'query': 'web development HTML CSS JavaScript',
        'expected_courses': ['CMSC388J', 'INST377'],
    },
    # ... more test cases
]

def evaluate_search_quality(searcher, test_cases):
    """Evaluate search using precision@k and recall@k."""
    for test in test_cases:
        results = searcher.search(test['query'], limit=10)
        result_ids = [r['course_id'] for r in results]

        # Calculate metrics
        hits = len(set(result_ids) & set(test['expected_courses']))
        precision = hits / len(result_ids)
        recall = hits / len(test['expected_courses'])

        print(f"Query: {test['query']}")
        print(f"  Precision@10: {precision:.2%}")
        print(f"  Recall@10: {recall:.2%}")
```

**Step 4.2: Performance Optimization**
- Index embeddings properly
- Cache model in memory
- Batch embedding generation
- Consider approximate nearest neighbor (ANN) for large datasets

---

## 6. Example Queries and Use Cases

### Academic Advising
```python
# Find prerequisites for data science career
searcher.search("courses about data analysis statistics machine learning")

# Find manageable course load
searcher.search("introductory programming", filters={'level': 'Lower Level'})
```

### Course Discovery
```python
# Explore interdisciplinary topics
searcher.search("intersection of computer science and biology")

# Find courses by teaching method
searcher.search("project-based learning hands-on coding")
```

### Schedule Planning
```python
# Find courses for specific term
searcher.search(
    "artificial intelligence deep learning",
    filters={'term': ['202501']}
)

# Find courses by instructor quality (if reviews are added)
searcher.search("highly rated professor computer science")
```

---

## 7. Performance Considerations

### Latency Targets
- **Cold start** (model load): < 2 seconds
- **Query embedding**: < 50ms
- **Vector search**: < 100ms (for 10k courses)
- **Total query time**: < 200ms

### Scalability
**Current dataset:** ~7 terms × ~3000 courses/term = ~21,000 courses
- Embedding storage: 21,000 × 384 × 4 bytes = ~32 MB
- Totally manageable with SQLite

**Future growth:** If expanding to 100k+ courses, consider:
- PostgreSQL + pgvector
- Approximate nearest neighbor (ANN) indexes
- Separate vector database (Qdrant, Milvus)

### Memory Usage
- Model in memory: ~100 MB
- Database: ~50-100 MB
- Total: ~200 MB (very lightweight)

---

## 8. Cost Considerations

### Open Source / Self-Hosted (Recommended)
**Infrastructure:** None (runs on local machine or single server)
**Costs:**
- $0 for compute (uses existing hardware)
- Developer time: ~2-4 weeks initial implementation
- Maintenance: ~2-4 hours/month

### Cloud-Hosted Options
If using managed vector databases:
- **Pinecone:** ~$70/month for 100k vectors
- **Weaviate Cloud:** ~$25-100/month depending on scale
- **Qdrant Cloud:** Free tier for < 1M vectors

**Recommendation:** Self-host with SQLite + sqlite-vss for zero ongoing costs.

---

## 9. Integration Options

### Option 1: Standalone CLI Tool
```bash
python search_courses.py "machine learning" --term 202501
```

### Option 2: Python Library
```python
from testudo import CourseSemanticSearch

searcher = CourseSemanticSearch('courses.db')
results = searcher.search('web development', limit=5)
```

### Option 3: REST API (Flask/FastAPI)
```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/search")
def search(q: str, limit: int = 10, term: str = None):
    filters = {'term': [term]} if term else {}
    results = searcher.search(q, limit=limit, filters=filters)
    return {"results": results}
```

**API Usage:**
```bash
curl "http://localhost:8000/search?q=machine+learning&term=202501&limit=5"
```

### Option 4: Web Interface
- Frontend: React/Vue.js
- Backend: FastAPI
- Features: Autocomplete, filters, course comparisons

---

## 10. Future Enhancements

### Phase 2 Features
1. **Multi-modal search:** Search by syllabus content, course materials
2. **Personalization:** Learn from user preferences and search history
3. **Course recommendations:** "Students who took this also took..."
4. **Temporal analysis:** Track how courses evolve over terms
5. **Sentiment analysis:** Incorporate student reviews/ratings

### Advanced Techniques
1. **Re-ranking with cross-encoders:** Better relevance after initial retrieval
2. **Query expansion:** Automatically add related terms
3. **Faceted search:** Dynamic filter suggestions based on results
4. **Explainability:** Show why a course matched the query

---

## 11. Success Metrics

### Technical Metrics
- Query latency < 200ms (p95)
- Search precision@10 > 80%
- Search recall@10 > 60%
- System uptime > 99%

### User Metrics
- Reduced time to find relevant courses
- Increased course discovery
- Higher user satisfaction scores
- More diverse course selections

---

## 12. Implementation Timeline

### Week 1: Foundation
- [ ] Install dependencies (sqlite-vss, sentence-transformers)
- [ ] Generate embeddings for all courses
- [ ] Set up vector search database
- [ ] Basic search functionality

### Week 2: Core Features
- [ ] Implement CourseSemanticSearch class
- [ ] Create CLI tool
- [ ] Add filters (term, department, level)
- [ ] Testing with sample queries

### Week 3: Advanced Features
- [ ] Hybrid search (semantic + keyword)
- [ ] Query understanding and filter extraction
- [ ] Instructor search
- [ ] Performance optimization

### Week 4: Polish and Deploy
- [ ] Evaluation framework
- [ ] Documentation
- [ ] Example notebooks/tutorials
- [ ] Deployment scripts

---

## 13. Getting Started

### Prerequisites
```bash
pip install sqlite-vss sentence-transformers sqlite-utils numpy
```

### Quick Start
```python
# 1. Generate embeddings
python generate_embeddings.py --input courses_specific_terms.db

# 2. Run a search
python search_cli.py "machine learning courses"

# 3. Use in Python
from testudo import CourseSemanticSearch
searcher = CourseSemanticSearch('courses_specific_terms.db')
results = searcher.search('data science')
for course in results:
    print(f"{course['course_id']}: {course['title']}")
```

---

## 14. Resources

### Documentation
- [sqlite-vss GitHub](https://github.com/asg017/sqlite-vss)
- [sentence-transformers](https://www.sbert.net/)
- [SQLite FTS5](https://www.sqlite.org/fts5.html)

### Similar Projects
- [Semantic Scholar](https://www.semanticscholar.org/) - Academic paper search
- [You.com](https://you.com/) - Semantic web search
- [Algolia](https://www.algolia.com/) - Commercial search platform

### Learning Resources
- "Dense Passage Retrieval" (Karpukhin et al., 2020)
- "Sentence-BERT" (Reimers & Gurevych, 2019)
- "Vector Search in Production" tutorials

---

## 15. Contact and Support

For questions or contributions:
- GitHub Issues: [testudo repository]
- Documentation: [link to docs]
- Developer: [contact info]

---

## Conclusion

This plan provides a comprehensive roadmap for implementing semantic search on University of Maryland course data. The recommended approach using SQLite + sqlite-vss offers:

✅ **Simple deployment** - No complex infrastructure
✅ **Low cost** - $0 ongoing costs
✅ **Good performance** - Sub-200ms query times
✅ **Extensible** - Easy to add features and scale
✅ **Maintainable** - Minimal dependencies

**Next Steps:**
1. Review and approve this plan
2. Set up development environment
3. Begin Phase 1 implementation (data preparation)
4. Iterate based on feedback and testing

The estimated timeline is 3-4 weeks for a production-ready semantic search system with basic features, with additional enhancements possible in subsequent phases.
