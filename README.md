# Aurora-Q-A

Member Memory QA — A conversational AI system for answering questions about member preferences and history using RAG (Retrieval-Augmented Generation).

## Architecture

### Store/Retrieval: Mem0 Embedding RAG
- **Vector Search**: Mem0 Platform provides semantic search over message embeddings
- **Keyword Filters**: Optional metadata filters (e.g., `user_id`, `timestamp`) for scoped retrieval
- **Memory Ingestion**: Messages are ingested into Mem0 with structured metadata (`message_id`, `timestamp`, `user_name`, `user_id`)
- **Name Resolution**: Local name-to-ID index (`data/index/names.json`) maps user names to UUIDs for filtering

### Reasoning: LLM with Tool-Calling
- **Retrieve → Analyze → Answer**: The LLM orchestrates retrieval via tool calls, then synthesizes answers
- **Tool**: `search_user_memory(name, query, top_k)` — searches Mem0 for a specific user's memories
- **Model**: GPT-4o (configurable via `OPENAI_MODEL`)
- **Iterative Loop**: Up to 3 tool-call iterations to refine retrieval and reasoning

### API
```
GET /ask?question=...
POST /ask {"question": "..."}

Response: {"answer": "..."}
```

**Examples:**
```bash
# Local development
curl "http://localhost:8000/ask?question=when%20does%20sophia%20have%20private%20dinner"

# Production (Railway)
curl "https://aurora-q-a-production.up.railway.app/ask?question=when%20does%20sophia%20have%20private%20dinner"

# POST request
curl -X POST "https://aurora-q-a-production.up.railway.app/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "when does sophia have private dinner"}'
```

## Design Decisions & Alternatives

### Why Mem0 RAG vs. Alternatives?

#### ✅ Chosen: Mem0 Platform (Vector Search)
**Pros:**
- Managed embeddings and vector storage
- Built-in semantic search with relevance scoring
- Automatic memory extraction and conflict resolution
- Metadata filtering for user-scoped queries
- Dashboard for memory inspection

**Cons:**
- External API dependency (rate limits, latency)
- Cost per API call
- Less control over embedding model/parameters

#### Alternative 1: Direct Vector DB (Pinecone/Weaviate/Qdrant)
**Why not:**
- Requires managing embeddings pipeline (OpenAI API → vector DB)
- No built-in memory extraction/conflict resolution
- More infrastructure to maintain
- Would need custom deduplication logic

#### Alternative 2: Full-Text Search (Elasticsearch/PostgreSQL)
**Why not:**
- Keyword matching misses semantic similarity
- "private dinner" wouldn't match "chef's tasting menu" without synonyms
- Less effective for conversational queries

#### Alternative 3: Fine-Tuned LLM (No Retrieval)
**Why not:**
- Context window limits (can't fit all messages)
- No way to update knowledge without retraining
- Expensive to fine-tune for each user
- Can't cite sources or explain reasoning

### Why LLM Tool-Calling vs. Direct Retrieval?

#### ✅ Chosen: LLM with Tool-Calling
**Pros:**
- LLM extracts user name from natural language queries
- Can refine search queries iteratively
- Handles ambiguous questions ("when does she...")
- Synthesizes multiple retrieved snippets
- Can reason about temporal relationships (timestamps)

#### Alternative: Direct Vector Search
**Why not:**
- Requires explicit user identification in query
- No query refinement or multi-step reasoning
- Limited ability to combine multiple facts
- Harder to handle implicit questions

## Core Challenge: Retrieval Accuracy

The primary bottleneck is **retrieval accuracy** — finding the right memories to answer a question.

### Current Issues

1. **Semantic Gap**: User questions may not match message phrasing
   - Question: "when does sophia have private dinner?"
   - Memory: "Sophia Al-Farsi wants to organize a private dinner under the stars in Santorini"
   - Challenge: Temporal information ("when") may be implicit or in metadata

2. **Top-K Limitations**: Fixed `top_k=10` may miss relevant memories if:
   - Many memories exist for the user
   - Query is ambiguous
   - Relevant memory has lower similarity score

3. **Metadata Underutilization**: Timestamps in metadata aren't always used effectively
   - LLM may not extract temporal patterns
   - No explicit date/time filtering in search

4. **Name Resolution Errors**: Partial name matching can fail
   - "Sophia" vs "Sophia Al-Farsi" — works
   - "Sofia" (typo) — fails
   - Multiple users with similar names — ambiguous

### Potential Improvements

1. **Hybrid Search**: Combine vector similarity with keyword matching
   - Use BM25 for exact phrase matches
   - Boost results with matching metadata fields

2. **Query Expansion**: Generate multiple query variations
   - "private dinner" → ["private dinner", "chef dinner", "exclusive dining", "personalized meal"]
   - Search with each, merge results

3. **Reranking**: Use a cross-encoder to rerank top-K results
   - More accurate than cosine similarity alone
   - Better at understanding query intent

4. **Temporal Filtering**: Extract dates from queries and filter memories
   - "next month" → filter by timestamp range
   - "in 2025" → filter metadata

5. **Multi-Hop Retrieval**: Chain multiple searches
   - First: find user's dinner preferences
   - Second: find specific dinner events matching preferences
   - Combine results

6. **Metadata-Aware Scoring**: Boost memories with matching metadata
   - If query mentions "dinner", boost memories with `categories: ["food"]`
   - Use structured attributes (e.g., `day_of_week`, `is_weekend`)

7. **Feedback Loop**: Track which retrieved memories led to correct answers
   - Log query → retrieved memories → final answer
   - Use for fine-tuning retrieval parameters

## Next Steps

### Short-Term (Immediate)
1. **Increase `max_tokens`**: Current 512 may truncate answers (already increased to 4096 in code)
2. **Add query logging**: Track retrieval performance
   - Log: query, retrieved memories, scores, final answer
   - Identify patterns in retrieval failures

3. **Improve error handling**: Better messages for edge cases
   - User not found → suggest similar names
   - No results → suggest broader query

### Medium-Term (1-2 weeks)
1. **Implement reranking**: Add cross-encoder reranking step
   - Use `sentence-transformers` or OpenAI embeddings
   - Rerank top 20 → return top 5

2. **Temporal extraction**: Parse dates from queries
   - Use LLM to extract temporal intent
   - Filter memories by timestamp range

3. **Query expansion**: Generate query variations
   - Use LLM to generate synonyms/related terms
   - Search with each, merge and deduplicate

4. **Metadata boosting**: Use categories/structured attributes
   - Boost memories with matching categories
   - Filter by structured attributes when available

### Long-Term (1+ months)
1. **Hybrid search**: Add BM25 keyword search
   - Combine with vector search
   - Weighted fusion of results

2. **Multi-hop retrieval**: Implement iterative search
   - First search: broad context
   - Second search: specific details
   - Chain results

3. **Fine-tuning**: Optimize retrieval parameters
   - A/B test different `top_k` values
   - Tune embedding model parameters
   - Optimize filter combinations

4. **Evaluation framework**: Build test suite
   - Ground truth Q&A pairs
   - Measure retrieval precision/recall
   - Track answer accuracy over time

5. **Caching**: Cache frequent queries
   - Reduce API calls for common questions
   - Invalidate on new memory ingestion

## Data Quality Notes

### Anomaly Summary
- Messages: 3,349 | Users: 10
- **Preference Conflicts**: Seat preference flips (latest wins)
- **Temporal Conflicts**: Same-day multi-city mentions (likely intents vs confirmed)
- **PII**: Phone/email placeholders in test data

**Implications:**
- Use recency for conflict resolution
- Separate "intent" vs "confirmed" bookings
- Normalize PII placeholders

---

## Quick Start

```bash
# Install dependencies
uv sync

# Set environment variables
export MEM0_API_KEY=your_key
export OPENAI_API_KEY=your_key

# Run the service locally
uvicorn app.main:app --reload

# Test locally
curl "http://localhost:8000/ask?question=when%20does%20sophia%20have%20private%20dinner"

# Or test production
curl "https://aurora-q-a-production.up.railway.app/ask?question=when%20does%20sophia%20have%20private%20dinner"
```

## Production

**Live API:** https://aurora-q-a-production.up.railway.app

**Health Check:**
```bash
curl https://aurora-q-a-production.up.railway.app/healthz
```

## Deployment

See `DEPLOYMENT.md` for Railway deployment instructions.

