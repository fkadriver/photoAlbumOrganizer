# NixOS Setup Guide

This project provides both traditional `shell.nix` and modern `flake.nix` configurations for NixOS users.

## Option 1: Using shell.nix (Traditional)

```bash
# Enter the Nix shell
nix-shell

# Install Python dependencies
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models

# Verify installation
python -c "import face_recognition; print('✓ Success!')"

# Run the organizer
python photo_organizer.py -s /path/to/photos -o /path/to/output
```

## Option 2: Using flake.nix (Modern, Recommended)

### First-time setup

```bash
# Enable flakes (if not already enabled)
mkdir -p ~/.config/nix
echo "experimental-features = nix-command flakes" >> ~/.config/nix/nix.conf

# Enter the development environment
nix develop

# Install Python dependencies
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models

# Verify installation
python -c "import face_recognition; print('✓ Success!')"
```

### Subsequent uses

```bash
# Just enter the dev environment
nix develop

# Dependencies are already installed in venv
python photo_organizer.py -s /path/to/photos -o /path/to/output
```

## What's Included

Both configurations provide:

- **Python 3.11** with pip and virtualenv
- **Build tools**: cmake, gcc, make, pkg-config
- **Image libraries**: libpng, libjpeg, libwebp, opencv
- **Math libraries**: OpenBLAS, LAPACK (for optimized operations)
- **X11 support**: For dlib GUI features
- **Automatic venv**: Creates and activates Python virtual environment

## Troubleshooting

### dlib compilation fails

The NixOS environment provides all necessary headers and libraries. If compilation still fails:

```bash
# Try installing with verbose output
pip install dlib --verbose

# Or use pre-built binary
pip install dlib-binary
```

###face_recognition import error

```bash
# Reinstall face_recognition_models
pip uninstall face_recognition_models -y
pip install git+https://github.com/ageitgey/face_recognition_models

# Test
python -c "import face_recognition; print('Works!')"
```

### Exiting the environment

```bash
# Deactivate venv and exit nix shell
deactivate  # or just 'exit'
```

## Performance Tips

The NixOS shell sets `OPENBLAS_NUM_THREADS=1` by default. For better performance on multi-core systems:

```bash
export OPENBLAS_NUM_THREADS=4  # or your CPU core count
```

## IDE Integration

### VSCode with NixOS

Add to `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.terminal.activateEnvironment": true
}
```

Then run VSCode from within the nix shell:

```bash
nix develop  # or nix-shell
code .
```

### PyCharm

1. Enter nix shell: `nix develop`
2. Open PyCharm
3. Configure Python interpreter: `<project>/venv/bin/python`

## Updating Dependencies

```bash
# Enter nix shell
nix develop  # or nix-shell

# Update pip packages
pip install --upgrade -r requirements.txt

# Update Nix dependencies (flake only)
nix flake update
```

## Adding to .gitignore

The `.gitignore` already includes `venv/`, but you may want to add:

```
# Nix
result
.direnv/
```
