#!/usr/bin/env python3
"""Check if Rust is properly set up for Python 3.14 compilation."""

import sys
import subprocess
import os

print("=" * 60)
print("Rust Setup Checker for Python 3.14")
print("=" * 60)
print()

# Check Python version
print(f"Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
if sys.version_info.minor != 14:
    print("[WARN] This script is for Python 3.14")
print()

# Check Rust
print("Checking Rust installation...")
rust_ok = False
try:
    result = subprocess.run(["rustc", "--version"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print(f"[OK] Rust found: {result.stdout.strip()}")
        rust_ok = True
    else:
        print("[FAIL] Rust not found or not working")
except (FileNotFoundError, subprocess.TimeoutExpired):
    print("[FAIL] Rust (rustc) not found in PATH")
    print("  Install from: https://rustup.rs/")
except Exception as e:
    print(f"✗ Error checking Rust: {e}")

# Check Cargo
print("\nChecking Cargo...")
cargo_ok = False
try:
    result = subprocess.run(["cargo", "--version"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print(f"[OK] Cargo found: {result.stdout.strip()}")
        cargo_ok = True
    else:
        print("[FAIL] Cargo not found or not working")
except (FileNotFoundError, subprocess.TimeoutExpired):
    print("[FAIL] Cargo not found in PATH")
    print("  Install Rust from: https://rustup.rs/ (includes Cargo)")
except Exception as e:
    print(f"✗ Error checking Cargo: {e}")

# Check PATH
print("\nChecking PATH for Rust...")
path_env = os.environ.get("PATH", "")
if ".cargo" in path_env.lower() or "cargo" in path_env.lower():
    print("[OK] Cargo path found in environment")
else:
    print("[WARN] Cargo path not found in PATH")
    print("  Typical location: C:\\Users\\YourUsername\\.cargo\\bin")
    print("  Add it to PATH or restart terminal after Rust installation")

# Summary
print("\n" + "=" * 60)
if rust_ok and cargo_ok:
    print("[OK] Rust is properly set up!")
    print("\nYou can now try installing requirements:")
    print("  pip install -r requirements.txt")
else:
    print("[FAIL] Rust is not properly set up")
    print("\nNext steps:")
    print("  1. Install Rust from: https://rustup.rs/")
    print("  2. Install Visual C++ Build Tools (see SETUP_PYTHON314.md)")
    print("  3. Restart your terminal")
    print("  4. Run this script again to verify")
print("=" * 60)

