#!/usr/bin/env bash
# Quick fix for direnv and flake issues

set -e

echo "Quick Fix for photoAlbumOrganizer"
echo "=================================="
echo ""

# 1. Fix direnvrc
echo "1. Fixing direnvrc path..."
mkdir -p ~/.config/direnv

# Detect correct nix-direnv path
if [ -f "/run/current-system/sw/share/nix-direnv/direnvrc" ]; then
    DIRENV_PATH="/run/current-system/sw/share/nix-direnv/direnvrc"
    echo "   Using system path: $DIRENV_PATH"
elif [ -f "$HOME/.nix-profile/share/nix-direnv/direnvrc" ]; then
    DIRENV_PATH="$HOME/.nix-profile/share/nix-direnv/direnvrc"
    echo "   Using user profile path: $DIRENV_PATH"
else
    echo "   ⚠️  nix-direnv not found. Installing..."
    nix-env -iA nixpkgs.nix-direnv
    DIRENV_PATH="$HOME/.nix-profile/share/nix-direnv/direnvrc"
fi

echo "source $DIRENV_PATH" > ~/.config/direnv/direnvrc
echo "   ✓ Updated ~/.config/direnv/direnvrc"

# 2. Delete pure flake files (they're loaded by default and causing confusion)
echo ""
echo "2. Removing pure flake files..."
if [ -f "flake-pure.nix" ]; then
    rm flake-pure.nix
    echo "   ✓ Removed flake-pure.nix"
fi
if [ -f "shell-pure.nix" ]; then
    rm shell-pure.nix
    echo "   ✓ Removed shell-pure.nix"
fi

# 3. Remove venv if it exists (will be recreated with correct settings)
if [ -d "venv" ]; then
    echo ""
    echo "3. Removing old venv..."
    rm -rf venv
    echo "   ✓ Removed venv"
fi

# 4. Clean direnv cache
echo ""
echo "4. Cleaning direnv cache..."
rm -rf .direnv
echo "   ✓ Cleared .direnv cache"

echo ""
echo "=================================="
echo "Fix Complete!"
echo "=================================="
echo ""
echo "Now run:"
echo "  direnv allow"
echo "  # Wait for environment to load"
echo "  pip install -r requirements.txt"
echo "  pip install git+https://github.com/ageitgey/face_recognition_models"
echo ""
