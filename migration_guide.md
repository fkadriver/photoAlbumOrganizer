# Migration to Pure NixOS Setup

This guide helps you switch from the venv-based setup to a pure NixOS setup that avoids library linking issues.

## The Problem

When using pip to install packages in a venv on NixOS, binary packages (like numpy, opencv) may fail to find system libraries like `libstdc++.so.6` or `libGL.so.1`.

## The Solution

Use NixOS-managed Python packages instead of pip installations. This ensures all libraries are properly linked.

## Quick Migration Steps

### 1. Backup and Clean

```bash
# Exit current environment
exit

# Remove old venv
rm -rf venv

# Clean Python cache
rm -rf __pycache__
find . -type d -name "__pycache__" -exec rm -rf {} +
```

### 2. Replace Your Files

**Option A: Use the pure flake (recommended)**

The `flake.nix` has been updated to use NixOS packages. Just reload:

```bash
# Update flake.nix to use the new pure version
mv flake.nix flake.nix.backup
mv flake-pure.nix flake.nix

# Reload direnv
direnv reload

# Or manually enter
nix develop
```

**Option B: Use shell-pure.nix**

```bash
# Rename the pure shell
mv shell-pure.nix shell.nix

# Update .envrc to use shell.nix
echo "use nix" > .envrc

# Allow it
direnv allow
```

### 3. Install Face Recognition (One-Time)

The NixOS packages include everything except `face_recognition` and `imagehash` (not in nixpkgs). Install these once to your user directory:

```bash
# These will install to ~/.local/lib/python3.11/site-packages
pip install --user imagehash face_recognition
pip install --user git+https://github.com/ageitgey/face_recognition_models
```

### 4. Test It

```bash
# Test imports
python -c "import numpy; import cv2; import face_recognition; print('✓ All working!')"

# Run the organizer
python photo_organizer.py -s ~/Photos -o ~/Organized -t 7 --no-time-window
```

## What's Different?

### Before (venv approach):
```
NixOS → venv → pip install everything
Problems: Library linking issues
```

### After (pure NixOS approach):
```
NixOS packages → Python with built-in packages → Only pip for unavailable packages
Benefits: Everything properly linked
```

## Packages Now Managed by NixOS

- ✅ Python 3.11
- ✅ NumPy
- ✅ OpenCV (cv2)
- ✅ Pillow (PIL)
- ✅ SciPy
- ✅ dlib
- ✅ PyWavelets
- ✅ Click

## Packages Still via pip (user install)

- 📦 imagehash (not in nixpkgs)
- 📦 face_recognition (not in nixpkgs)
- 📦 face_recognition_models (not in nixpkgs)

## Advantages of Pure NixOS Approach

1. **No library linking issues** - Everything is properly connected
2. **Reproducible** - Same environment on any NixOS machine
3. **Faster** - No compilation needed (uses binary cache)
4. **Cleaner** - No venv directory cluttering your project
5. **Declarative** - All dependencies in nix files

## Troubleshooting

### "command not found: setup-face-recognition"

This helper script is only in flake-pure.nix. Just run manually:
```bash
pip install --user imagehash face_recognition
pip install --user git+https://github.com/ageitgey/face_recognition_models
```

### "No module named 'face_recognition'"

Install it to user packages:
```bash
pip install --user face_recognition
pip install --user git+https://github.com/ageitgey/face_recognition_models
```

### Still getting library errors

Make sure LD_LIBRARY_PATH is set (should be automatic in shellHook):
```bash
echo $LD_LIBRARY_PATH
# Should show paths to libGL, libstdc++, etc.
```

### Want to go back to venv approach?

```bash
# Restore old files
mv flake.nix.backup flake.nix
# Create venv again
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Performance Comparison

| Approach | First Load | Subsequent Loads | Disk Usage |
|----------|-----------|------------------|------------|
| venv + pip | 5-10 min (compilation) | Instant | ~500MB |
| Pure NixOS | 30-60 sec (download) | Instant | ~200MB |

## Recommendation

Use the **pure NixOS approach** (flake-pure.nix or shell-pure.nix) for:
- ✅ Better reliability
- ✅ Faster setup
- ✅ No library issues
- ✅ True NixOS benefits

Keep the venv approach only if you need packages not available in nixpkgs and that can't be installed with `pip install --user`.
