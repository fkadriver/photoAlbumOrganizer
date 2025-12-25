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
            glib.out  # Provides libgthread-2.0.so.0
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
            export LD_LIBRARY_PATH="${pkgs.libGL}/lib:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.glib}/lib:${pkgs.glib.out}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
            
            # Fix BLAS/LAPACK warnings by using single-threaded mode
            export OMP_NUM_THREADS=1
            export OPENBLAS_NUM_THREADS=1
            export MKL_NUM_THREADS=1
            export VECLIB_MAXIMUM_THREADS=1
            export NUMEXPR_NUM_THREADS=1
            
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
