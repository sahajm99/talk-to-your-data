# Phase 2 Implementation Guide: Chat Interface & RAG

## Overview

Phase 2 adds a complete RAG (Retrieval-Augmented Generation) chat system that allows you to query your ingested documents using natural language. The system retrieves relevant chunks from Weaviate and generates answers using GPT-4o-mini.

---

## What Was Implemented

### 1. **Data Models** ([app/models.py](app/models.py))

Added chat-specific Pydantic models:
- `SourceReference` - References to source chunks with visual grounding data
- `ConversationMessage` - Messages in a conversation (user/assistant)
- `ChatQuery` - Request model for chat queries
- `ChatResponse` - Response model with answer, sources, and metadata

### 2. **Session Manager** ([app/services/session_manager.py](app/services/session_manager.py))

In-memory conversation persistence with:
- Session creation and management
- Conversation history storage
- Automatic session expiration (60 minutes TTL)
- Session cleanup utilities

**Key Features:**
- Thread-safe in-memory storage
- Multi-tenant support (project-based isolation)
- Configurable session TTL
- Easy upgrade path to Redis/PostgreSQL

### 3. **Chat Service** ([app/services/chat_service.py](app/services/chat_service.py))

Core RAG pipeline implementation:

**Pipeline Steps:**
1. Generate query embedding using OpenAI
2. Search Weaviate for top-K relevant chunks
3. Retrieve conversation history from session
4. Build context from retrieved chunks
5. Generate answer using GPT-4o-mini with context
6. Store conversation in session
7. Return formatted response with sources

**Key Features:**
- Conversation context awareness (last 10 messages)
- Source citation with relevance scores
- Visual grounding metadata included
- Performance metrics (retrieval, generation, total time)

### 4. **Chat API Router** ([app/api/routes_chat.py](app/api/routes_chat.py))

REST API endpoints for chat functionality:
- `POST /chat/query` - Ask questions using RAG
- `GET /chat/history/{session_id}` - Get conversation history
- `DELETE /chat/history/{session_id}` - Clear conversation
- `GET /chat/sessions/stats` - Session statistics

### 5. **Static File Server** ([app/main.py](app/main.py))

Serves chunk images from the data directory:
- Mounted at `/data` endpoint
- Allows frontend to display chunk images
- Provides visual proof of source locations

### 6. **Test Tools**

Created two test utilities:
- `test_chat.py` - Python script for API testing
- `chat_test.html` - Interactive browser chat interface

---

## Testing the Chat System

### Prerequisites

1. **Start the server:**
   ```bash
   uvicorn app.main:app --reload
   ```

2. **Ensure you have documents ingested:**
   - You should have documents already uploaded to Weaviate
   - From Phase 1, you ingested the Bhagavad Gita (409 chunks)

### Method 1: Python Test Script

Run the automated test script:

```bash
python test_chat.py
```

This will:
- Test health check
- Send 2 sample queries
- Display answers and sources
- Show conversation history
- Display session statistics

**Expected Output:**
```
================================================================================
Testing Chat Endpoint
================================================================================

Test Query 1:
Question: What is this document about?
--------------------------------------------------------------------------------

✓ Success!
  Session ID: abc123...
  Answer:
  According to the sources, this document is the Bhagavad Gita...

  Sources Retrieved: 5

  Source Details:
    [1] Bhagavad-gita-As-It-Is.pdf (Page 12)
        Score: 0.8542
        Text: The Bhagavad Gita is a conversation between...
    ...

  Performance:
    Retrieval: 245.32ms
    Generation: 1823.45ms
    Total: 2089.12ms
```

### Method 2: Browser Chat Interface

1. **Open the chat interface:**
   ```bash
   # Just open the file in your browser
   start chat_test.html  # Windows
   # or
   open chat_test.html   # Mac/Linux
   ```

2. **Configure the chat:**
   - **Project ID:** `test` (or your project ID)
   - **Top K:** 5 (number of chunks to retrieve)
   - **Include Images:** ✓ (check to get image paths)

3. **Start chatting:**
   - Type: "What is the Bhagavad Gita about?"
   - Type: "What does Krishna teach Arjuna?"
   - Type: "Explain the concept of dharma"

4. **View results:**
   - Answer from GPT-4o-mini
   - Source citations with relevance scores
   - Performance metrics
   - Conversation maintains context

### Method 3: cURL / Postman

**Send a chat query:**

```bash
curl -X POST http://localhost:8000/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "test",
    "query": "What is this document about?",
    "top_k": 5,
    "include_images": true
  }'
```

**Get conversation history:**

```bash
curl http://localhost:8000/chat/history/{session_id}
```

**Clear conversation:**

```bash
curl -X DELETE http://localhost:8000/chat/history/{session_id}
```

---

## API Endpoints

### POST /chat/query

Ask a question using RAG.

**Request Body:**
```json
{
  "project_id": "test",
  "query": "What is this document about?",
  "session_id": "optional-session-id",
  "top_k": 5,
  "include_images": true
}
```

**Response:**
```json
{
  "answer": "According to Source 1, this document...",
  "sources": [
    {
      "chunk_id": "uuid",
      "source_id": "document-id",
      "file_name": "Bhagavad-gita-As-It-Is.pdf",
      "page_number": 12,
      "chunk_index": 5,
      "text": "The Bhagavad Gita is...",
      "score": 0.8542,
      "bounding_box": [100, 200, 500, 300],
      "image_path": "/data/documents/test/doc-id/chunk_images/chunk_5.png",
      "chunk_type": "text"
    }
  ],
  "session_id": "new-or-existing-session-id",
  "query": "What is this document about?",
  "project_id": "test",
  "retrieval_time_ms": 245.32,
  "generation_time_ms": 1823.45,
  "total_time_ms": 2089.12
}
```

### GET /chat/history/{session_id}

Get conversation history for a session.

**Response:**
```json
[
  {
    "role": "user",
    "content": "What is this document about?",
    "timestamp": "2025-01-22T10:30:00",
    "sources": null
  },
  {
    "role": "assistant",
    "content": "According to the sources...",
    "timestamp": "2025-01-22T10:30:02",
    "sources": [...]
  }
]
```

### DELETE /chat/history/{session_id}

Clear conversation history.

**Response:**
```json
{
  "message": "Conversation history cleared successfully",
  "session_id": "session-id"
}
```

### GET /chat/sessions/stats

Get session statistics.

**Response:**
```json
{
  "active_sessions": 3,
  "expired_sessions_cleaned": 1
}
```

---

## Architecture Overview

### RAG Pipeline Flow

```
User Query
    ↓
[Generate Embedding] (OpenAI text-embedding-3-large)
    ↓
[Vector Search] (Weaviate with project_id filter)
    ↓
[Retrieve Top-K Chunks] (Default: 5)
    ↓
[Build Context] (Chunks + Conversation History)
    ↓
[Generate Answer] (GPT-4o-mini with context)
    ↓
[Store in Session] (In-memory session manager)
    ↓
Response with Answer + Sources
```

### Conversation Management

```
Session Manager (In-Memory)
├── Session 1 (Project: test)
│   ├── User: "What is this about?"
│   ├── Assistant: "This is about..." [Sources: ...]
│   ├── User: "Tell me more"
│   └── Assistant: "Based on our discussion..." [Sources: ...]
├── Session 2 (Project: test)
└── Session 3 (Project: other-project)
```

### Multi-Tenancy

- **Project-level isolation:** Each query filters by `project_id`
- **Session-project binding:** Sessions are bound to projects
- **Vector search filtering:** Weaviate filters by `projectId` property

---

## Configuration

### Environment Variables

All configuration is in [.env](.env):

```env
# OpenAI Configuration
OPENAI_API_KEY=sk-...

# Weaviate Configuration
WEAVIATE_URL=https://...
WEAVIATE_API_KEY=...
WEAVIATE_CLASS_NAME=TalkToUrData

# Chunking Configuration
CHUNK_MAX_TOKENS=400
CHUNK_OVERLAP_TOKENS=50

# Data Storage
DATA_DIR=./data
USE_VISUAL_GROUNDING=true
```

### Session Configuration

Edit [app/services/session_manager.py](app/services/session_manager.py):

```python
SessionManager(session_ttl_minutes=60)  # Default: 60 minutes
```

### LLM Configuration

Edit [app/services/chat_service.py](app/services/chat_service.py):

```python
response = self.openai_client.chat.completions.create(
    model="gpt-4o-mini",  # Change model here
    temperature=0.2,      # Adjust creativity (0.0-1.0)
    max_tokens=1000,      # Maximum response length
    top_p=0.9
)
```

---

## Example Queries

Try these questions with your Bhagavad Gita document:

1. **Overview Questions:**
   - "What is this document about?"
   - "Who are the main characters?"
   - "What is the setting of the conversation?"

2. **Concept Questions:**
   - "Explain the concept of dharma"
   - "What is karma yoga?"
   - "What does Krishna teach about the soul?"

3. **Comparative Questions:**
   - "What is the difference between knowledge and wisdom?"
   - "Compare karma yoga and bhakti yoga"

4. **Contextual Questions:**
   - "Why was Arjuna confused?"
   - "What advice did Krishna give Arjuna?"

5. **Follow-up Questions** (in same session):
   - First: "What is dharma?"
   - Then: "Can you give me examples?" (maintains context)

---

## Performance Expectations

### Typical Response Times

- **Retrieval:** 100-500ms
  - Weaviate vector search + embedding generation
  - Depends on database size and network latency

- **Generation:** 1000-3000ms
  - GPT-4o-mini inference time
  - Depends on context length and answer complexity

- **Total:** 1200-3500ms
  - End-to-end query processing

### Optimization Tips

1. **Reduce top_k:** Retrieve fewer chunks (3-5 is usually sufficient)
2. **Use Haiku:** Switch to Claude Haiku for faster responses
3. **Cache embeddings:** Implement query embedding cache
4. **Upgrade session storage:** Move to Redis for multi-instance deployments

---

## Visual Grounding Integration

### Chunk Images

When `include_images: true`, responses include image paths:

```json
"image_path": "/data/documents/test/doc-id/chunk_images/chunk_5.png"
```

### Accessing Images

Images are served statically at:
```
http://localhost:8000/data/documents/{project_id}/{doc_id}/chunk_images/{chunk_id}.png
```

### Frontend Integration

In your frontend, display images alongside text:

```html
<img src="http://localhost:8000${source.image_path}" alt="Source">
```

---

## Limitations & Known Issues

### Current Limitations

1. **In-Memory Sessions:**
   - Sessions lost on server restart
   - Not suitable for multi-instance deployments
   - **Solution:** Upgrade to Redis in Phase 3/4

2. **No Streaming:**
   - Full response generated before returning
   - User waits for entire answer
   - **Solution:** Implement SSE streaming in Phase 3

3. **Basic Context Window:**
   - Only last 10 messages used
   - No intelligent context pruning
   - **Solution:** Implement sliding window in Phase 4

4. **Single-Turn Retrieval:**
   - Only retrieves chunks for current query
   - Doesn't use conversation context for retrieval
   - **Solution:** Implement conversational retrieval in Phase 4

### Known Issues

- **Session Cleanup:** Manual cleanup required via stats endpoint
- **Large Responses:** May timeout for very long answers
- **Error Handling:** Generic error messages (needs improvement)

---

## Next Steps: Phase 3 & 4

### Phase 3: Web Frontend (Coming Next)

- Modern React/Vue chat interface
- Real-time streaming responses
- Visual grounding display (images + highlights)
- Session management UI
- Document upload interface
- Project management

### Phase 4: Testing & Documentation

- Unit tests for all components
- Integration tests for RAG pipeline
- Performance benchmarking
- API documentation (OpenAPI/Swagger)
- Deployment guide (Docker, cloud)
- User manual

---

## Troubleshooting

### "Cannot connect to server"

**Problem:** Server not running

**Solution:**
```bash
uvicorn app.main:app --reload
```

### "No sources retrieved"

**Problem:** No documents in Weaviate for project

**Solution:**
1. Check project_id matches ingested documents
2. Verify documents in Weaviate console
3. Re-upload documents if needed

### "OpenAI API error"

**Problem:** Invalid API key or quota exceeded

**Solution:**
1. Verify OPENAI_API_KEY in .env
2. Check OpenAI account status
3. Check API usage limits

### "Session not found"

**Problem:** Session expired or invalid

**Solution:**
- Sessions expire after 60 minutes of inactivity
- Let the system create a new session automatically
- Don't pass `session_id` to start fresh

---

## Files Modified/Created in Phase 2

### Created Files:
- `app/models.py` - Enhanced with chat models
- `app/services/session_manager.py` - Session management
- `app/services/chat_service.py` - RAG logic
- `app/api/routes_chat.py` - Chat endpoints
- `test_chat.py` - Python test script
- `chat_test.html` - Browser chat interface
- `PHASE2_GUIDE.md` - This guide

### Modified Files:
- `app/main.py` - Added chat router + static files
- `app/api/__init__.py` - (if exists) Import chat router

---

## Summary

Phase 2 successfully implements:
✅ Complete RAG pipeline with vector search
✅ Conversation management with session persistence
✅ Source citation with visual grounding
✅ REST API for chat functionality
✅ Test utilities for validation
✅ Static file serving for chunk images

**You can now query your documents using natural language!**

Try the chat interface and see how it performs with your ingested documents.

---

## Support

If you encounter issues:
1. Check server logs: `uvicorn app.main:app --reload`
2. Verify Weaviate connection: `/health` endpoint
3. Test with `test_chat.py` script
4. Check OpenAI API status
5. Review this guide's troubleshooting section

**Ready to proceed to Phase 3 for the web frontend!**
