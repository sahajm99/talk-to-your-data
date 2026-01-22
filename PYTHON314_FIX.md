# Fixing Installation Issues for Python 3.14

## Issues Identified

Based on the error logs, there are **two main problems**:

### Issue 1: PyO3 doesn't officially support Python 3.14 yet
**Error (line 315):**
```
error: the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)
= help: set PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 to suppress this check and build anyway using the stable ABI
```

**Root Cause:** The Rust-Python binding library (PyO3) used by `pydantic-core` only officially supports up to Python 3.13. However, Python 3.14 uses the stable ABI, so we can force it to work.

### Issue 2: lxml requires libxml2 libraries on Windows
**Error (lines 450, 455):**
```
Cannot open include file: 'libxml/xmlversion.h': No such file or directory
Could not find function xmlCheckVersion in library libxml2. Is libxml2 installed?
```

**Root Cause:** `lxml` needs to compile C extensions that depend on `libxml2` and `libxslt` libraries, which aren't installed on Windows by default. There are no pre-built wheels for Python 3.14.

## Solutions

### Solution 1: Install pydantic with ABI3 forward compatibility

Set the environment variable `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` before installing pydantic:

**In Git Bash:**
```bash
# Set the environment variable
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

# Install pydantic
pip install pydantic==2.8.2 pydantic-settings==2.4.0
```

### Solution 2: Skip lxml (it's optional)

`lxml` is used by `beautifulsoup4` as an optional parser. BeautifulSoup4 can work without it using the built-in HTML parser. Since we already have `beautifulsoup4` installed, we can skip `lxml`.

## Complete Installation Steps

Run these commands in Git Bash:

```bash
# 1. Make sure you're in the project directory and venv is activated
source venv/Scripts/activate

# 2. Set the environment variable for PyO3
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

# 3. Upgrade pip
python -m pip install --upgrade pip setuptools wheel

# 4. Install packages that don't need compilation first
pip install fastapi==0.109.0 "uvicorn[standard]==0.27.0" python-dotenv==1.0.1 openai==1.12.0 weaviate-client==3.25.3 beautifulsoup4==4.12.3 pdfplumber==0.10.4 python-docx==1.1.1 pytest==7.4.4 pytest-asyncio==0.23.3

# 5. Install pydantic with the environment variable (this will compile from source - takes 5-15 minutes)
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 pip install pydantic==2.8.2 pydantic-settings==2.4.0

# 6. Verify installation
python -c "import pydantic; print(f'Pydantic version: {pydantic.__version__}')"
```

## Or Use the Helper Script

I've created `install_python314.sh` which does all of this automatically:

```bash
# Make it executable
chmod +x install_python314.sh

# Run it
bash install_python314.sh
```

## What Changed

1. **Updated `requirements.txt`**: Commented out `lxml` since it's optional and causes issues with Python 3.14
2. **Created `install_python314.sh`**: Automated installation script with the workarounds
3. **Created this guide**: Documentation of the issues and solutions

## Why This Works

- **PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1**: Tells PyO3 to use Python's stable ABI, which is forward-compatible. Python 3.14 maintains ABI compatibility with 3.13, so this allows the build to proceed.

- **Skipping lxml**: BeautifulSoup4 works fine without lxml - it just uses a slightly slower built-in parser. For HTML extraction, this is perfectly acceptable.

## After Installation

Once everything is installed:

```bash
# Start the application
uvicorn app.main:app --reload

# Access the web UI
# http://localhost:8000
```

## Troubleshooting

### "PYO3_USE_ABI3_FORWARD_COMPATIBILITY not working"

Make sure you set it **before** running pip install:
```bash
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
pip install pydantic==2.8.2
```

### "Still getting compilation errors"

1. Make sure Rust is installed: `rustc --version`
2. Make sure Visual C++ Build Tools are installed
3. Try: `pip install --upgrade pip setuptools wheel` first

### "lxml is required"

If you really need lxml, you would need to:
1. Install libxml2 and libxslt for Windows (complex)
2. Or wait for pre-built wheels for Python 3.14
3. Or use Python 3.13 instead

But for this project, **lxml is not required** - beautifulsoup4 works fine without it.

