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
            # Set library paths for NixOS
            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
            
            # Create virtual environment if it doesn't exist
            if [ ! -d "venv" ]; then
              echo "Creating Python virtual environment with Python ${python.version}..."
              ${python}/bin/python -m venv venv
            fi
            
            source venv/bin/activate
            
            # Upgrade pip
            pip install --upgrade pip setuptools wheel
            
            echo ""
            echo "╔════════════════════════════════════════════════╗"
            echo "║   Photo Album Organizer - Dev Environment     ║"
            echo "╚════════════════════════════════════════════════╝"
            echo ""
            echo "  Python: $(python --version)"
            echo "  Virtual env: $(which python)"
            echo ""
            echo "Quick Start:"
            echo "  1. Install dependencies:"
            echo "     pip install -r requirements.txt"
            echo "     pip install git+https://github.com/ageitgey/face_recognition_models"
            echo ""
            echo "  2. Run the organizer:"
            echo "     python photo_organizer.py -s <source> -o <output>"
            echo ""
            echo "  3. Run tests:"
            echo "     python -c 'import face_recognition; print(\"✓ Face recognition working!\")"
            echo ""
            
            # Set environment variables for compilation
            export OPENBLAS_NUM_THREADS=1
            export CMAKE_PREFIX_PATH="${pkgs.openblas}:${pkgs.lapack}"
            export PKG_CONFIG_PATH="${pkgs.openblas}/lib/pkgconfig:${pkgs.lapack}/lib/pkgconfig:$PKG_CONFIG_PATH"
            
            # Prevent Python from writing bytecode
            export PYTHONDONTWRITEBYTECODE=1
          '';
        };
      }
    );
}