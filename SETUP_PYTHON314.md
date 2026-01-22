# Setting Up Python 3.14 with Rust for pydantic-core

Since Python 3.14 doesn't have pre-built wheels for `pydantic-core`, we need to compile it from source, which requires Rust.

## Step 1: Install Rust Toolchain

### Option A: Using rustup (Recommended)

1. **Download rustup**:
   - Go to: https://rustup.rs/
   - Download and run `rustup-init.exe`

2. **Run the installer**:
   - When prompted, press `1` to proceed with default installation
   - This will install Rust and Cargo to `C:\Users\YourUsername\.cargo\bin`

3. **Restart your terminal** (Git Bash) after installation

4. **Verify installation**:
   ```bash
   rustc --version
   cargo --version
   ```

### Option B: Using Visual Studio Installer (if you have VS)

1. Open Visual Studio Installer
2. Modify your installation
3. Add "Desktop development with C++" workload
4. This includes the MSVC build tools needed for Rust on Windows

## Step 2: Install Visual C++ Build Tools (Required for Windows)

Rust on Windows needs Microsoft Visual C++ Build Tools:

1. **Download Build Tools**:
   - Go to: https://visualstudio.microsoft.com/downloads/
   - Scroll down to "Tools for Visual Studio"
   - Download "Build Tools for Visual Studio 2022"

2. **Install**:
   - Run the installer
   - Select "C++ build tools" workload
   - Click "Install"

## Step 3: Set Up Your Project

After Rust is installed:

```bash
# 1. Make sure you're in the project directory
cd /c/Users/sahaj/OneDrive/Desktop/Experiments/talk-to-your-data

# 2. Create/activate virtual environment (if not already done)
python -m venv venv
source venv/Scripts/activate

# 3. Verify Python version
python --version  # Should show 3.14.0

# 4. Upgrade pip and install build tools
python -m pip install --upgrade pip
python -m pip install --upgrade setuptools wheel

# 5. Install requirements (this will compile pydantic-core from source)
pip install -r requirements.txt
```

## Step 4: Verify Installation

```bash
# Check that pydantic installed successfully
python -c "import pydantic; print(f'Pydantic version: {pydantic.__version__}')"

# Should output: Pydantic version: 2.8.2
```

## Troubleshooting

### "rustc: command not found" after installation

**Solution**: Add Rust to your PATH manually:
```bash
# In Git Bash, add to ~/.bashrc or ~/.bash_profile:
export PATH="$HOME/.cargo/bin:$PATH"

# Then reload:
source ~/.bashrc
```

Or restart Git Bash completely.

### "error: linker `link.exe` not found"

**Solution**: Install Visual C++ Build Tools (see Step 2 above)

### "error: failed to run custom build command for `pydantic-core`"

**Solution**: 
1. Make sure Rust is properly installed: `rustc --version`
2. Make sure Visual C++ Build Tools are installed
3. Try: `pip install --upgrade pip setuptools wheel`
4. Then retry: `pip install -r requirements.txt`

### Installation takes a long time

**This is normal!** Compiling pydantic-core from source can take 5-15 minutes. Be patient.

## Alternative: Use Pre-built Development Builds

If compilation fails, you can try installing a development version that might have Python 3.14 support:

```bash
pip install --pre pydantic
```

However, this may have stability issues.

## Next Steps After Installation

Once everything is installed:

1. **Start the application**:
   ```bash
   uvicorn app.main:app --reload
   ```

2. **Access the web UI**: http://localhost:8000

3. **Test the API**: http://localhost:8000/docs



