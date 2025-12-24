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
    
    # Python development headers (critical for dlib)
    python311.pkgs.python
  ];

  shellHook = ''
    # Set library paths for NixOS
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
    
    # Create and activate virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
      echo "Creating Python virtual environment..."
      python3.11 -m venv venv
    fi
    
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    echo ""
    echo "================================================"
    echo "Photo Album Organizer Development Environment"
    echo "================================================"
    echo "Python version: $(python --version)"
    echo "Virtual environment: activated"
    echo ""
    echo "To install dependencies, run:"
    echo "  pip install -r requirements.txt"
    echo "  pip install git+https://github.com/ageitgey/face_recognition_models"
    echo ""
    echo "To run the organizer:"
    echo "  python photo_organizer.py -s /source/path -o /output/path"
    echo ""
    echo "To exit this environment:"
    echo "  exit"
    echo "================================================"
    echo ""
    
    # Set environment variables for dlib compilation
    export OPENBLAS_NUM_THREADS=1
    export CMAKE_PREFIX_PATH="${pkgs.openblas}:${pkgs.lapack}"
    
    # Ensure pkg-config can find libraries
    export PKG_CONFIG_PATH="${pkgs.openblas}/lib/pkgconfig:${pkgs.lapack}/lib/pkgconfig:$PKG_CONFIG_PATH"
  '';
}