# NixOS Setup Guide

This project provides full NixOS support with automatic environment setup and dependency management. This guide covers setup with both flakes and traditional nix-shell.

## Quick Start with direnv (Recommended)

The fastest way to get started - the environment activates automatically when you enter the directory.

### Prerequisites

1. **NixOS with flakes enabled** (see below if not enabled)
2. **direnv installed and configured** (see [DIRENV_SETUP.md](DIRENV_SETUP.md))

### Setup

```bash
# Clone the repository
git clone https://github.com/fkadriver/photoAlbumOrganizer.git
cd photoAlbumOrganizer

# Allow direnv (first time only)
direnv allow

# Environment loads automatically with all dependencies!
# Install Python packages that aren't in nixpkgs (first time only)
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models

# Verify everything is working
python verify_environment.py

# Start organizing!
python ../src/photo_organizer.py -s ~/Photos -o ~/Organized
```

That's it! Every time you `cd` into the directory, the environment automatically activates.

## Option 1: Using flake.nix (Modern, Recommended)

### Enable Flakes (if not already enabled)

Add to your NixOS configuration:

```nix
# /etc/nixos/configuration.nix
{
  nix.settings.experimental-features = [ "nix-command" "flakes" ];
}
```

Then rebuild:
```bash
sudo nixos-rebuild switch
```

Or for user-level only:
```bash
mkdir -p ~/.config/nix
echo "experimental-features = nix-command flakes" >> ~/.config/nix/nix.conf
```

### Using the Flake

```bash
# Enter development environment
nix develop

# Or use direnv for automatic activation (see above)
```

### What the Flake Provides

- ✅ Python 3.11
- ✅ All build tools (cmake, gcc, make, pkg-config)
- ✅ System libraries (libGL, glib, zlib with proper linking)
- ✅ Image processing libraries (libpng, libjpeg, libwebp)
- ✅ OpenCV 4
- ✅ BLAS/LAPACK for optimized math operations
- ✅ X11 support for dlib
- ✅ Automatic environment verification on load
- ✅ Virtual environment (venv) management

## Option 2: Using shell.nix (Traditional)

If you prefer not to use flakes:

```bash
# Enter development environment
nix-shell

# Install Python packages
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models

# Verify
python verify_environment.py

# Run
python ../src/photo_organizer.py -s ~/Photos -o ~/Organized
```

## First-Time Setup

After entering the environment (via `nix develop`, `nix-shell`, or direnv):

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models
```

This installs:
- **From nixpkgs** (already available): NumPy, OpenCV, Pillow, SciPy, dlib
- **Via pip** (not in nixpkgs): imagehash, face_recognition, face_recognition_models

### 2. Verify Installation

```bash
python verify_environment.py
```

Expected output:
```
============================================================
Photo Album Organizer - Environment Verification
============================================================

✓ Pillow
✓ ImageHash
✓ OpenCV
✓ NumPy
✓ face_recognition

============================================================
✓ All 5 packages working!
```

### 3. Test Run

```bash
# Dry run to test without making changes
python ../src/photo_organizer.py -s ~/Photos -o ~/Test --dry-run

# Process a small subset first
python ../src/photo_organizer.py -s ~/Photos/2024 -o ~/Organized/2024
```

## Troubleshooting

### Environment Verification Shows Missing Packages

If `python verify_environment.py` shows missing packages:

```bash
⚠️  Missing packages:
  - imagehash
  - face_recognition
```

**Solution:**
```bash
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models
```

### Library Linking Errors

**Error:** `libGL.so.1: cannot open shared object file`
**Error:** `libgthread-2.0.so.0: cannot open shared object file`

This means the Nix environment isn't properly setting library paths.

**Solution:**
```bash
# Check if LD_LIBRARY_PATH is set
echo $LD_LIBRARY_PATH
# Should show paths to libGL, glib, etc.

# If empty, reload environment
direnv reload  # if using direnv
# OR
exit && nix develop  # if using nix develop
```

If still having issues, ensure your `flake.nix` or `shell.nix` includes:
```nix
export LD_LIBRARY_PATH="${pkgs.libGL}/lib:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.glib}/lib:${pkgs.glib.out}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
```

### DGESVD Warnings (Harmless)

You may see warnings like:
```
** On entry to DGESVD parameter number 11 had an illegal value
```

These are harmless BLAS/LAPACK warnings that don't affect functionality. The environment is configured to minimize these, but some may still appear.

### dlib Compilation Fails

If you see dlib compilation errors:

**Solution 1: Use pre-built dlib-binary**
```bash
pip uninstall dlib
pip install dlib-binary
```

**Solution 2: Clear cache and retry**
```bash
rm -rf venv
exit  # Exit nix environment
nix develop  # Re-enter
pip install -r requirements.txt
```

### OpenCV Import Fails

**Error:** `import cv2` fails even though it's "installed"

**Solution:**
```bash
# Verify OpenCV is in the Nix environment
python -c "import sys; print(sys.path)"
# Should show paths in /nix/store/

# Reinstall opencv-python
pip uninstall opencv-python opencv-python-headless -y
pip install opencv-python
```

### Virtual Environment Issues

If you're having persistent issues:

```bash
# Clean slate approach
rm -rf venv __pycache__
exit  # Exit environment

# Re-enter and reinstall
nix develop
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models
python verify_environment.py
```

## Advanced: Pure NixOS Setup (No venv)

For a completely pure NixOS approach without virtual environments, see `flake-pure.nix` or `shell-pure.nix`. These use only NixOS packages where possible.

**Setup:**
```bash
# Use the pure flake
nix develop .#pure  # if configured in flake.nix

# Or rename files
mv flake-pure.nix flake.nix
# Update .envrc if needed

# Only install packages not in nixpkgs
pip install --user imagehash face_recognition
pip install --user git+https://github.com/ageitgey/face_recognition_models
```

**Benefits:**
- No venv directory
- Faster environment loading
- More reproducible
- Uses Nix binary cache

**Drawbacks:**
- Some packages still need pip (imagehash, face_recognition)
- Requires `--user` flag for pip

## Performance Notes

### First Load
- **With venv**: 30-60 seconds (creating venv + pip downloads)
- **Pure NixOS**: 10-30 seconds (Nix binary cache)

### Subsequent Loads
- **With direnv**: Instant (< 1 second)
- **With nix develop**: 1-3 seconds

### Storage
- **Nix store**: ~200MB
- **venv**: ~300-500MB
- **Total**: ~700MB

## Environment Variables Set

The NixOS environment automatically sets:

```bash
LD_LIBRARY_PATH          # System library paths
PYTHONPATH               # Python package paths
CMAKE_PREFIX_PATH        # For building packages
PKG_CONFIG_PATH          # For pkg-config
OPENBLAS_NUM_THREADS     # Single-threaded BLAS
OMP_NUM_THREADS          # OpenMP threading
MKL_NUM_THREADS          # MKL threading
PYTHONDONTWRITEBYTECODE  # No .pyc files
```

## Keeping Your Environment Updated

### Update Nix Packages

```bash
# Update flake inputs
nix flake update

# Or update nixpkgs
nix-channel --update  # if using channels
```

### Update Python Packages

```bash
pip install --upgrade -r requirements.txt
```

### Full Reset

```bash
# Clean everything and start fresh
rm -rf venv .direnv
direnv reload  # or nix develop
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models
```

## Integration with IDEs

### VSCode

1. Install the "direnv" extension: `mkhl.direnv`
2. Open the project
3. VSCode will automatically use the Nix environment

Or manually set the Python interpreter:
```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python"
}
```

### PyCharm

1. Enter Nix environment: `nix develop`
2. Open PyCharm from within the environment
3. Configure interpreter: Point to `./venv/bin/python`

### Neovim/Vim

Use direnv.vim:
```vim
Plug 'direnv/direnv.vim'
```

## See Also

- [DIRENV_SETUP.md](DIRENV_SETUP.md) - Complete direnv configuration guide
- [README.md](README.md) - Main project documentation
- [migration_guide.md](migration_guide.md) - Migrating to pure NixOS setup

## Support

Having issues? 

1. Check [Troubleshooting](#troubleshooting) above
2. Run `python verify_environment.py` to diagnose
3. Check [GitHub Issues](https://github.com/fkadriver/photoAlbumOrganizer/issues)
4. See the main [README.md](README.md) troubleshooting section
