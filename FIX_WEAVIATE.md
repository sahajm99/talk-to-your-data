# Fix for Weaviate Client Error

## The Problem

**Error:**
```
ModuleNotFoundError: No module named 'weaviate.classes'
```

**Root Cause:** 
The code uses the Weaviate client v4+ API (`weaviate.classes`), but `requirements.txt` has `weaviate-client==3.25.3` which uses the older v3 API.

## The Solution

Update `weaviate-client` to version 4.0.0 or higher, which has the `weaviate.classes` module.

## Commands to Run

**In Git Bash (with venv activated):**

```bash
# Make sure venv is activated
source .venv/Scripts/activate

# Upgrade weaviate-client to v4+
pip install --upgrade "weaviate-client>=4.0.0"

# Verify installation
python -c "from weaviate.classes.config import Property, DataType; print('Weaviate client v4+ installed successfully!')"
```

## What Changed

I've updated `requirements.txt` to use:
```txt
weaviate-client>=4.0.0
```

Instead of:
```txt
weaviate-client==3.25.3
```

## After Fixing

Once you've upgraded weaviate-client, restart the application:

```bash
# Stop the current server (Ctrl+C if running)
# Then restart:
uvicorn app.main:app --reload
```

The application should now start without the import error.

