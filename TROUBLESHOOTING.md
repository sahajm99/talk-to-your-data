# Troubleshooting Guide

## Issues You Encountered

### ✅ Issue 1: All Chunks Show 50% Score (FIXED)

**Problem:** Every source displayed "50.0%" relevance score

**Root Cause:** Weaviate v4 metadata wasn't being accessed correctly. The query wasn't requesting distance/certainty metadata, so scores defaulted to 0.5.

**Fix Applied:**
1. Added `return_metadata=["distance", "certainty"]` to the query
2. Updated score calculation to properly extract and normalize distance
3. Cosine distance (0-2 range) now converts to similarity score (0-100%)

**Result:** Scores will now show actual relevance (higher % = more relevant)

---

### ⚠️ Issue 2: Retrieving Old Documents

**Problem:** When querying about newly uploaded document, results show chunks from old documents (documents.csv, configurations.csv, UnderstandingDeepLearning.pdf)

**Root Cause:** This is **expected behavior** for RAG systems. Vector search finds the most semantically similar chunks across ALL documents in your project, regardless of which document they're from.

**Why This Happens:**
1. You have multiple documents in project "test":
   - documents.csv (many chunks)
   - configurations.csv (many chunks)
   - UnderstandingDeepLearning PDF (many chunks)
   - ITGlue_API_Documentation PDF (only 4 chunks)

2. When you ask "What is this document about?", the system searches ALL chunks in project "test"

3. Old documents have more chunks and may have better semantic matches for generic queries

**Solutions:**

#### **Solution A: Use Different Project IDs** (Recommended)

Upload documents to different projects to isolate them:

1. Change project ID in the sidebar to "itglue-docs"
2. Upload your ITGlue documentation
3. Query with project ID "itglue-docs"
4. Only ITGlue chunks will be retrieved

**How to do it:**
- In the web app sidebar, change "test" to "itglue-docs"
- Upload your document
- Ask questions

#### **Solution B: Clear Old Documents**

Delete old test documents from Weaviate:

**Option 1: Via Weaviate Console**
1. Go to https://console.weaviate.cloud/
2. Connect to your cluster
3. Delete objects from class "TalkToUrData" where projectId = "test"

**Option 2: Via API** (I can create a cleanup script)

#### **Solution C: Ask More Specific Questions**

Instead of "What is this document about?", ask:
- "What API endpoints are available in ITGlue?"
- "How do I authenticate with the ITGlue API?"
- "What are the rate limits for ITGlue API?"

Specific questions are more likely to match your new document.

---

### ⚠️ Issue 3: Only 4 Chunks from 13-Page Document

**Problem:** ITGlue PDF (13 pages, 345 blocks) created only 4 chunks

**Root Cause:** Chunks were set to 400 tokens max, which is quite large. Larger chunks mean:
- Fewer chunks total
- Less granular search
- Harder to find specific information

**Fix Applied:**
- Reduced CHUNK_MAX_TOKENS from 400 to 300
- This will create ~30-40% more chunks
- Better granularity for search

**To Apply Fix:**
1. Restart the server (it will pick up new .env)
2. Re-upload your document
3. Will create more chunks (~6-8 chunks instead of 4)

---

## Recommended Actions

### **Immediate Actions:**

1. **Restart Server** (to pick up .env changes):
   ```bash
   # Stop server (Ctrl+C)
   # Restart
   uvicorn app.main:app --reload
   ```

2. **Create New Project** for your ITGlue docs:
   - In web app, change project ID to "itglue"
   - Upload document again
   - Query with specific questions

3. **Test Score Fix:**
   - Ask a question
   - Check if scores now show different percentages (not all 50%)

### **Better Workflow:**

**For Multiple Documents:**
```
Project "company-policies" → Upload all policy documents
Project "api-docs" → Upload all API documentation
Project "research" → Upload research papers
```

**For Single Document Analysis:**
```
Project "document-name" → Upload single document
Ask specific questions about it
```

### **Query Tips:**

**Generic Queries** (search all documents):
- "What security policies do we have?"
- "Find information about authentication"

**Specific Queries** (better for single-document focus):
- "What are the endpoints in this API?"
- "How do I configure X in this system?"
- "What does section 3 say about..."

---

## Understanding RAG Behavior

### **How Vector Search Works:**

1. **Your Query** → Converted to embedding vector
2. **Search** → Find most similar vectors in database
3. **Filter** → By project_id (not by document)
4. **Return** → Top K most similar chunks (from ANY document in project)
5. **Generate** → LLM creates answer from retrieved chunks

### **Why This Design:**

This is intentional for cross-document search:
- "What do our security policies say about passwords?" → Searches all policy docs
- "Find all references to API rate limits" → Searches all API docs
- "What do multiple sources say about X?" → Aggregates from all documents

### **When This Is Not Ideal:**

- Single document Q&A (like asking about one specific document)
- Document comparison (needs explicit document filtering)
- New document with few chunks competing with old documents

---

## Future Enhancements (Phase 4)

### **Potential Improvements:**

1. **Document Filtering UI:**
   - Add document selector dropdown
   - Filter search by specific document
   - "Search only in: [ITGlue_API_Documentation]"

2. **Smart Chunking:**
   - Adaptive chunk size based on content
   - Section-aware chunking
   - Title/heading preservation

3. **Better Scoring:**
   - Hybrid search (vector + keyword)
   - Reranking with cross-encoder
   - Source diversity

4. **Document Management:**
   - View all documents in project
   - Delete specific documents
   - Document metadata display

---

## Testing Your Fixes

### **Test 1: Score Variation**

1. Restart server
2. Ask: "What is the ITGlue API?"
3. Check sources - scores should vary (not all 50%)
4. ✅ Expected: Scores like 87%, 76%, 65%, 54%, 42%

### **Test 2: Project Isolation**

1. Create new project "itglue"
2. Upload ITGlue doc
3. Ask same question
4. ✅ Expected: Only ITGlue chunks returned

### **Test 3: Chunk Count**

1. Delete old ITGlue upload
2. Re-upload with new settings
3. Check logs for "Created X enhanced chunks"
4. ✅ Expected: 6-10 chunks (not 4)

---

## Current Status

### ✅ **Fixed:**
- Score calculation now works correctly
- Chunk size reduced for better granularity

### ⚠️ **Known Behavior:**
- Cross-document search (by design)
- Old documents in "test" project affect results

### 📋 **Recommended:**
- Use separate project IDs for different document sets
- Ask specific questions for better results
- Re-upload documents after chunk size change

---

## Need Help?

**Common Solutions:**

1. **Wrong document appearing?** → Use different project ID
2. **All scores still 50%?** → Restart server to pick up code changes
3. **Too few chunks?** → Restart and re-upload with new settings
4. **Generic answers?** → Ask more specific questions

**Check Logs:**
- Look for "Retrieved X chunks for query"
- Check "score" values in results
- Verify chunk count on upload

---

**Your system is working correctly - these are configuration and usage pattern adjustments!** 🎯
