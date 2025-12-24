#!/usr/bin/env bash
# Fix repository setup for PureNix + direnv

set -e

echo "================================================================"
echo "Fixing photoAlbumOrganizer Repository Setup"
echo "================================================================"
echo ""

# 1. Create proper .envrc
echo "1. Creating .envrc for direnv..."
cat > .envrc << 'EOF'
use flake
EOF
echo "   ✓ Created .envrc"

# 2. Remove incorrectly named file
if [ -f "envrc_pure.sh" ]; then
    echo "2. Removing envrc_pure.sh..."
    rm envrc_pure.sh
    echo "   ✓ Removed envrc_pure.sh"
else
    echo "2. envrc_pure.sh not found (already removed)"
fi

# 3. Rename pure nix files
echo "3. Renaming .txt files to .nix..."
if [ -f "flake_nix_pure.txt" ]; then
    mv flake_nix_pure.txt flake-pure.nix
    echo "   ✓ Renamed flake_nix_pure.txt → flake-pure.nix"
fi

if [ -f "shell_nix_pure.txt" ]; then
    mv shell_nix_pure.txt shell-pure.nix
    echo "   ✓ Renamed shell_nix_pure.txt → shell-pure.nix"
fi

# 4. Update flake.nix with library paths and verification
echo "4. Updating flake.nix with NixOS library paths..."
cat > flake.nix << 'FLAKE_EOF'
{
  description = "Photo Album Organizer - Development Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;
        pythonPackages = python.pkgs;
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Python 3.11
            python
            pythonPackages.pip
            pythonPackages.virtualenv
            
            # Build tools
            cmake
            gcc
            gnumake
            pkg-config
            
            # System libraries for OpenCV and binary packages
            libGL
            glib
            zlib
            stdenv.cc.cc.lib
            
            # Image processing libraries
            libpng
            libjpeg
            libwebp
            
            # X11 for dlib GUI support
            xorg.libX11
            xorg.libXext
            
            # BLAS/LAPACK for optimized operations
            openblas
            lapack
            
            # OpenCV
            opencv4
          ];

          shellHook = ''
            # CRITICAL: Set library paths for NixOS
            export LD_LIBRARY_PATH="${pkgs.libGL}/lib:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.glib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
            
            # Create virtual environment if it doesn't exist
            if [ ! -d "venv" ]; then
              echo "Creating Python virtual environment with Python ${python.version}..."
              ${python}/bin/python -m venv venv
            fi
            
            source venv/bin/activate
            
            # Upgrade pip
            pip install --upgrade pip setuptools wheel 2>/dev/null
            
            echo ""
            echo "╔════════════════════════════════════════════════╗"
            echo "║   Photo Album Organizer - Dev Environment     ║"
            echo "╚════════════════════════════════════════════════╝"
            echo ""
            echo "  Python: $(python --version)"
            echo "  Virtual env: activated"
            echo ""
            
            # Run verification tests
            echo "Checking installed packages..."
            echo ""
            
            MISSING_PACKAGES=()
            
            python -c "import PIL" 2>/dev/null || MISSING_PACKAGES+=("Pillow")
            python -c "import imagehash" 2>/dev/null || MISSING_PACKAGES+=("imagehash")
            python -c "import cv2" 2>/dev/null || MISSING_PACKAGES+=("opencv-python")
            python -c "import numpy" 2>/dev/null || MISSING_PACKAGES+=("numpy")
            python -c "import face_recognition" 2>/dev/null || MISSING_PACKAGES+=("face_recognition")
            
            if [ ''${#MISSING_PACKAGES[@]} -eq 0 ]; then
              echo "✓ All packages installed!"
              echo ""
              echo "Ready: python photo_organizer.py -s <source> -o <output>"
              echo ""
            else
              echo "⚠️  Missing packages:"
              for pkg in "''${MISSING_PACKAGES[@]}"; do
                echo "  - $pkg"
              done
              echo ""
              echo "Install with:"
              echo "  pip install -r requirements.txt"
              echo "  pip install git+https://github.com/ageitgey/face_recognition_models"
              echo ""
            fi
            
            # Set environment variables
            export OPENBLAS_NUM_THREADS=1
            export CMAKE_PREFIX_PATH="${pkgs.openblas}:${pkgs.lapack}"
            export PKG_CONFIG_PATH="${pkgs.openblas}/lib/pkgconfig:${pkgs.lapack}/lib/pkgconfig:$PKG_CONFIG_PATH"
            export PYTHONDONTWRITEBYTECODE=1
          '';
        };
      }
    );
}
FLAKE_EOF
echo "   ✓ Updated flake.nix"

# 5. Update shell.nix with library paths
echo "5. Updating shell.nix with NixOS library paths..."
cat > shell.nix << 'SHELL_EOF'
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    # Python 3.11
    python311
    python311Packages.pip
    python311Packages.virtualenv
    
    # System dependencies for dlib compilation
    cmake
    gcc
    gnumake
    
    # System libraries for OpenCV
    libGL
    glib
    zlib
    stdenv.cc.cc.lib
    
    # Image processing libraries
    libpng
    libjpeg
    libwebp
    
    # X11 for dlib GUI support (optional but suppresses warnings)
    xorg.libX11
    xorg.libXext
    
    # BLAS/LAPACK for optimized matrix operations
    openblas
    lapack
    
    # OpenCV dependencies
    opencv4
  ];

  shellHook = ''
    # CRITICAL: Set library paths for NixOS
    export LD_LIBRARY_PATH="${pkgs.libGL}/lib:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.glib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
    
    # Create and activate virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
      echo "Creating Python virtual environment..."
      python3.11 -m venv venv
    fi
    
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip 2>/dev/null
    
    echo ""
    echo "================================================"
    echo "Photo Album Organizer Development Environment"
    echo "================================================"
    echo "Python: $(python --version)"
    echo ""
    
    # Check packages
    echo "Checking packages..."
    MISSING_PACKAGES=()
    
    python -c "import PIL" 2>/dev/null || MISSING_PACKAGES+=("Pillow")
    python -c "import imagehash" 2>/dev/null || MISSING_PACKAGES+=("imagehash")
    python -c "import cv2" 2>/dev/null || MISSING_PACKAGES+=("opencv-python")
    python -c "import numpy" 2>/dev/null || MISSING_PACKAGES+=("numpy")
    python -c "import face_recognition" 2>/dev/null || MISSING_PACKAGES+=("face_recognition")
    
    if [ ''${#MISSING_PACKAGES[@]} -eq 0 ]; then
      echo "✓ All packages ready!"
      echo ""
    else
      echo "⚠️  Missing: ''${MISSING_PACKAGES[@]}"
      echo ""
      echo "Install: pip install -r requirements.txt"
      echo "         pip install git+https://github.com/ageitgey/face_recognition_models"
      echo ""
    fi
    
    echo "================================================"
    echo ""
    
    # Set environment variables for dlib compilation
    export OPENBLAS_NUM_THREADS=1
    export CMAKE_PREFIX_PATH="${pkgs.openblas}:${pkgs.lapack}"
    export PKG_CONFIG_PATH="${pkgs.openblas}/lib/pkgconfig:${pkgs.lapack}/lib/pkgconfig:$PKG_CONFIG_PATH"
  '';
}
SHELL_EOF
echo "   ✓ Updated shell.nix"

# 6. Create verify_environment.py
echo "6. Creating verify_environment.py..."
cat > verify_environment.py << 'VERIFY_EOF'
#!/usr/bin/env python3
"""Environment verification script for Photo Album Organizer."""

import sys

def test_import(module_name, display_name=None):
    """Test if a module can be imported."""
    if display_name is None:
        display_name = module_name
    try:
        __import__(module_name)
        return True, f"✓ {display_name}"
    except ImportError as e:
        return False, f"✗ {display_name}: {str(e)}"

def main():
    print("=" * 60)
    print("Photo Album Organizer - Environment Verification")
    print("=" * 60)
    print()
    
    packages = [
        ("PIL", "Pillow"),
        ("imagehash", "ImageHash"),
        ("cv2", "OpenCV"),
        ("numpy", "NumPy"),
        ("face_recognition", "face_recognition"),
    ]
    
    results = [test_import(mod, disp) for mod, disp in packages]
    
    for success, message in results:
        print(message)
    
    print()
    print("=" * 60)
    
    passed = sum(1 for success, _ in results if success)
    total = len(results)
    
    if passed == total:
        print(f"✓ All {total} packages working!")
        sys.exit(0)
    else:
        print(f"⚠️  {total - passed} package(s) missing")
        print()
        print("Run: pip install -r requirements.txt")
        print("     pip install git+https://github.com/ageitgey/face_recognition_models")
        sys.exit(1)

if __name__ == "__main__":
    main()
VERIFY_EOF
chmod +x verify_environment.py
echo "   ✓ Created verify_environment.py"

echo ""
echo "================================================================"
echo "Setup Complete!"
echo "================================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Allow direnv (one time):"
echo "   direnv allow"
echo ""
echo "2. Enter the environment (automatic with direnv, or manually):"
echo "   cd . # (with direnv)"
echo "   # OR"
echo "   nix develop"
echo ""
echo "3. Install Python packages (first time):"
echo "   pip install -r requirements.txt"
echo "   pip install git+https://github.com/ageitgey/face_recognition_models"
echo ""
echo "4. Verify everything:"
echo "   python verify_environment.py"
echo ""
echo "5. Run the organizer:"
echo "   python photo_organizer.py -s ~/Photos -o ~/Organized"
echo ""
