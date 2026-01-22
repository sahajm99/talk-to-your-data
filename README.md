# Document Ingestion Pipeline

A small web + API service that lets you upload documents, converts them to clean text, chunks them, embeds them, and stores the vectors in Weaviate so you can later talk to your data with Claude.

## Features

- **Multi-format Support**: Extract text from HTML, PDF, DOCX, TXT, Markdown, CSV, and images (with placeholder for OCR)
- **Intelligent Chunking**: Word-based chunking with configurable overlap
- **OpenAI Embeddings**: Uses `text-embedding-3-large` by default (easily swappable)
- **Weaviate Integration**: Stores document chunks with vectors for semantic search
- **RESTful API**: FastAPI-based endpoints for programmatic access
- **Web UI**: Simple HTML interface for easy file uploads
- **Error Handling**: Graceful error handling that doesn't crash on bad files

## Tech Stack

- **Language**: Python 3.11+
- **Web Framework**: FastAPI
- **Vector DB**: Weaviate
- **Embeddings**: OpenAI `text-embedding-3-large`
- **Text Extraction**: BeautifulSoup4, pdfplumber, python-docx

## Installation

### Prerequisites

- Python 3.11 or higher
- A running Weaviate instance
- OpenAI API key

### Setup

1. **Clone or navigate to the project directory**

2. **Create a virtual environment**:
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS/Linux
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   # Copy the example file
   cp .env.example .env

   # Edit .env and add your values:
   # OPENAI_API_KEY=your_openai_api_key_here
   # WEAVIATE_URL=http://localhost:8080
   # WEAVIATE_API_KEY=  (optional, leave empty if no auth)
   # CHUNK_MAX_TOKENS=400
   # CHUNK_OVERLAP_TOKENS=50
   ```

5. **Ensure Weaviate is running**:
   - The service expects Weaviate to be accessible at the URL specified in `.env`
   - Default: `http://localhost:8080`

## Running the Service

Start the FastAPI server:

```bash
uvicorn app.main:app --reload
```

The service will be available at:
- **Web UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Usage

### Web UI

1. Open http://localhost:8000 in your browser
2. Enter a `project_id` (e.g., "msp-001" or "tenant-abc")
3. Select one or more files to upload
4. Click "Upload & Ingest"
5. View the ingestion results

### API Endpoints

#### 1. Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{"status": "ok"}
```

#### 2. Upload Files

```bash
curl -X POST "http://localhost:8000/ingest/files" \
  -F "project_id=msp-001" \
  -F "files=@document1.pdf" \
  -F "files=@document2.docx"
```

Response:
```json
{
  "project_id": "msp-001",
  "summary": [
    {
      "file_name": "document1.pdf",
      "num_chunks": 15,
      "project_id": "msp-001",
      "source_id": "document1",
      "text_preview": "This is the first 100 characters..."
    },
    {
      "file_name": "document2.docx",
      "num_chunks": 8,
      "project_id": "msp-001",
      "source_id": "document2",
      "text_preview": "..."
    }
  ]
}
```

#### 3. Ingest Directory

```bash
curl -X POST "http://localhost:8000/ingest/directory" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "msp-001",
    "path": "/path/to/documents"
  }'
```

This endpoint recursively finds all supported files in the directory and ingests them.

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entrypoint
│   ├── config.py            # Settings from environment
│   ├── models.py            # Pydantic models
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── file_types.py    # File type detection
│   │   ├── loaders.py       # File loading utilities
│   │   ├── text_extractors.py  # Text extraction from various formats
│   │   ├── chunker.py       # Text chunking strategy
│   │   ├── embedder.py      # Embedding provider abstraction
│   │   ├── vector_store.py  # Weaviate integration
│   │   └── pipeline.py      # Orchestration
│   └── api/
│       ├── __init__.py
│       ├── routes_health.py # Health check endpoint
│       └── routes_ingest.py # Ingestion endpoints
├── tests/
│   ├── test_text_extractors.py
│   ├── test_chunker.py
│   └── test_pipeline_smoke.py
├── requirements.txt
├── .env.example
└── README.md
```

## Data Model

Documents are stored in Weaviate with the following schema:

- **Class**: `IngestedChunk`
- **Properties**:
  - `projectId` (string): Project/tenant identifier
  - `sourceId` (string): Internal document ID
  - `sourceType` (string): File type (html, pdf, docx, etc.)
  - `fileName` (string): Original filename
  - `filePath` (string): File path if known
  - `chunkIndex` (int): Chunk index within document
  - `text` (text): Full chunk text
  - `metadataJson` (text): JSON string of additional metadata
- **Vector**: 3072-dimensional embedding (from `text-embedding-3-large`)

## Configuration

Environment variables (in `.env`):

- `OPENAI_API_KEY`: Required. Your OpenAI API key
- `WEAVIATE_URL`: Weaviate instance URL (default: `http://localhost:8080`)
- `WEAVIATE_API_KEY`: Optional. API key if Weaviate requires authentication
- `CHUNK_MAX_TOKENS`: Maximum words per chunk (default: 400)
- `CHUNK_OVERLAP_TOKENS`: Overlap words between chunks (default: 50)

## Testing

Run tests with pytest:

```bash
pytest tests/
```

## Extending the System

### Adding a New Embedding Provider

1. Implement the `BaseEmbedder` protocol in `app/ingestion/embedder.py`
2. Update `get_embedder()` to return your implementation based on config

### Adding OCR for Images

In `app/ingestion/text_extractors.py`, replace the image placeholder with actual OCR:

```python
# Example with pytesseract
import pytesseract
from PIL import Image

def _extract_image_ocr(content: bytes) -> str:
    image = Image.open(io.BytesIO(content))
    return pytesseract.image_to_string(image)
```

### Adding New File Types

1. Add the file type to `FileType` enum in `app/ingestion/file_types.py`
2. Update `guess_file_type()` to detect the new type
3. Add extraction logic in `app/ingestion/text_extractors.py`

## Error Handling

The service is designed to handle errors gracefully:

- If a single file fails to parse, it logs the error and continues with other files
- Failed files include an `error` field in the response summary
- The server never crashes due to a single bad file

## License

See LICENSE file for details.
