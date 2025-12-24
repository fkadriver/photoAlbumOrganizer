# NixOS Setup Guide

This project provides both traditional `shell.nix` and modern `flake.nix` configurations for NixOS users.

## Quick Setup with direnv (Recommended)

For automatic environment activation when entering the project directory:

### 1. Install direnv

```bash
# Add to your NixOS configuration.nix
environment.systemPackages = with pkgs; [
  direnv
  nix-direnv
];

# Or install for current user
nix-env -iA nixpkgs.direnv nixpkgs.nix-direnv
```

### 2. Configure direnv

Add to your `~/.config/direnv/direnvrc` (or `~/.direnvrc`):

```bash
source $HOME/.nix-profile/share/nix-direnv/direnvrc
```

### 3. Hook direnv into your shell

**For bash** (`~/.bashrc`):
```bash
eval "$(direnv hook bash)"
```

**For zsh** (`~/.zshrc`):
```bash
eval "$(direnv hook zsh)"
```

**For fish** (`~/.config/fish/config.fish`):
```fish
direnv hook fish | source
```

### 4. Enable in this project

```bash
# The .envrc file is already in the repo
# Just allow it once
direnv allow

# Now every time you cd into this directory, the environment activates automatically!
cd ~/photoAlbumOrganizer  # Environment loads automatically
```

### 5. Install Python dependencies (first time only)

```bash
pip install -r requirements.txt
pip install git+https://github.com/ageitgey/face_recognition_models
```

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

The `.gitignore` already includes `.direnv/` and `.envrc` is tracked in git, so you're all set!

## Benefits of direnv

- ✅ **Automatic activation**: Environment loads when you `cd` into the project
- ✅ **Automatic deactivation**: Unloads when you leave the directory
- ✅ **Fast**: Caches the environment, much faster than `nix develop` each time
- ✅ **Editor integration**: Works seamlessly with VSCode, Vim, Emacs, etc.

## direnv Commands

```bash
# Allow .envrc in current directory (first time only)
direnv allow

# Reload environment (after changing .envrc or flake.nix)
direnv reload

# Disable for current session
direnv deny

# Check status
direnv status
```
