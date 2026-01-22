#!/bin/bash
# Installation script for Python 3.14 with workarounds

echo "=========================================="
echo "Installing requirements for Python 3.14"
echo "=========================================="
echo ""

# Check Python version
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

if [[ ! "$python_version" =~ ^3\.14 ]]; then
    echo "Warning: This script is designed for Python 3.14"
fi

echo ""
echo "Step 1: Setting up environment variables for Python 3.14 compatibility..."
echo ""

# Set environment variable to allow PyO3 to build with Python 3.14
# This uses the stable ABI which is forward-compatible
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1

echo "PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 set"
echo ""

echo "Step 2: Upgrading pip and build tools..."
python -m pip install --upgrade pip setuptools wheel

echo ""
echo "Step 3: Installing packages that don't require compilation first..."
pip install fastapi==0.109.0 "uvicorn[standard]==0.27.0" python-dotenv==1.0.1 openai==1.12.0 weaviate-client==3.25.3 beautifulsoup4==4.12.3 pdfplumber==0.10.4 python-docx==1.1.1 pytest==7.4.4 pytest-asyncio==0.23.3

echo ""
echo "Step 4: Installing pydantic with Python 3.14 workaround..."
# Install pydantic with the environment variable set
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 pip install pydantic==2.8.2 pydantic-settings==2.4.0

echo ""
echo "Step 5: Installing lxml (will use pre-built wheel if available, or skip if not)..."
# Try to install lxml - if it fails, we'll use an alternative
pip install lxml || echo "lxml installation failed - will use alternative (beautifulsoup4 is already installed)"

echo ""
echo "=========================================="
echo "Installation complete!"
echo "=========================================="
echo ""
echo "Note: If lxml failed to install, beautifulsoup4 (already installed) can handle HTML parsing."
echo "The application should work without lxml."

