# Quick Start Guide - Python 3.12

## Step-by-Step Commands

### 1. Activate Virtual Environment

**In Git Bash:**
```bash
source .venv/Scripts/activate
```

You should see `(.venv)` at the beginning of your prompt.

### 2. Verify Python Version

```bash
python --version
```

Should show: `Python 3.12.x` (NOT 3.14!)

### 3. Upgrade pip

```bash
python -m pip install --upgrade pip setuptools wheel
```

### 4. Install Requirements

```bash
pip install -r requirements.txt
```

This should install all packages successfully with pre-built wheels (no compilation needed).

### 5. Verify Installation

```bash
# Check pydantic
python -c "import pydantic; print(f'Pydantic: {pydantic.__version__}')"

# Check other key packages
python -c "import fastapi; import uvicorn; import openai; print('All packages imported successfully!')"
```

### 6. Set Up Environment Variables

Make sure you have a `.env` file in the project root with:

```env
OPENAI_API_KEY=your_openai_api_key_here
WEAVIATE_URL=http://localhost:8080
WEAVIATE_API_KEY=
CHUNK_MAX_TOKENS=400
CHUNK_OVERLAP_TOKENS=50
```

### 7. Start the Application

```bash
uvicorn app.main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete
```

### 8. Access the Application

- **Web UI**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Troubleshooting

### "python: command not found" after activation

Make sure you activated the venv:
```bash
source .venv/Scripts/activate
```

### "Module not found" errors

Make sure you're in the venv and installed requirements:
```bash
source .venv/Scripts/activate
pip install -r requirements.txt
```

### "Weaviate connection failed"

Make sure your Weaviate instance is running at the URL specified in `.env` (default: `http://localhost:8080`)

### Port already in use

If port 8000 is busy, use a different port:
```bash
uvicorn app.main:app --reload --port 8001
```

## Deactivate Virtual Environment

When you're done:
```bash
deactivate
```

