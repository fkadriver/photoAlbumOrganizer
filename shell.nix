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
    glib.out
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
    export LD_LIBRARY_PATH="${pkgs.libGL}/lib:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.glib}/lib:${pkgs.glib.out}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
    
    # Fix BLAS/LAPACK warnings
    export OMP_NUM_THREADS=1
    export OPENBLAS_NUM_THREADS=1
    export MKL_NUM_THREADS=1
    
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
