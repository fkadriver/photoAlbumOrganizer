{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python311;
  
  # Python environment with NixOS packages
  pythonEnv = python.withPackages (ps: with ps; [
    # Image processing
    pillow
    opencv4
    numpy
    scipy
    pywavelets
    
    # Face recognition dependencies
    dlib
    click
    
    # Development tools
    pip
    setuptools
    wheel
  ]);
  
in pkgs.mkShell {
  buildInputs = [
    pythonEnv
    
    # System libraries
    pkgs.libGL
    pkgs.glib
    pkgs.zlib
    pkgs.stdenv.cc.cc.lib
    
    # Build tools
    pkgs.cmake
    pkgs.gcc
    pkgs.gnumake
    
    # Image libraries
    pkgs.libpng
    pkgs.libjpeg
    pkgs.libwebp
    
    # X11
    pkgs.xorg.libX11
    pkgs.xorg.libXext
    
    # BLAS/LAPACK
    pkgs.openblas
    pkgs.lapack
  ];

  shellHook = ''
    # Set library paths for OpenCV and other binary packages
    export LD_LIBRARY_PATH="${pkgs.libGL}/lib:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.glib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
    
    # Python user packages location
    export PYTHONPATH="$HOME/.local/lib/python${python.pythonVersion}/site-packages:$PYTHONPATH"
    
    echo ""
    echo "================================================"
    echo "Photo Album Organizer - Pure NixOS Environment"
    echo "================================================"
    echo "Python: $(python --version)"
    echo ""
    
    # Check for face_recognition
    if ! python -c "import face_recognition" 2>/dev/null; then
      echo "⚠️  First time setup needed:"
      echo "  pip install --user imagehash face_recognition"
      echo "  pip install --user git+https://github.com/ageitgey/face_recognition_models"
      echo ""
    else
      echo "✓ Ready to use!"
      echo ""
      echo "Run: python photo_organizer.py -s ~/Photos -o ~/Organized"
      echo ""
    fi
    echo "================================================"
    echo ""
  '';
}
