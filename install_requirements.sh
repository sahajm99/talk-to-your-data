#!/bin/bash
# Installation script for requirements.txt with proper handling of Rust dependencies

echo "Upgrading pip, setuptools, and wheel..."
python -m pip install --upgrade pip setuptools wheel

echo "Installing pydantic-core separately to avoid Rust compilation issues..."
# Try to install pydantic with binary wheels first
pip install --only-binary pydantic-core pydantic==2.8.2 pydantic-settings==2.4.0 2>/dev/null || \
pip install --no-build-isolation pydantic==2.8.2 pydantic-settings==2.4.0

echo "Installing remaining requirements..."
pip install -r requirements.txt

echo "Installation complete!"

