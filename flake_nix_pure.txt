{
  description = "Photo Album Organizer - Pure NixOS Development Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;
        
        # Custom Python environment with all dependencies
        pythonEnv = python.withPackages (ps: with ps; [
          # Image processing
          pillow
          opencv4
          numpy
          scipy
          pywavelets
          
          # Face recognition (if available in nixpkgs)
          # Note: face_recognition may need manual installation
          dlib
          
          # Utilities
          click
          
          # Development tools
          pip
          setuptools
          wheel
        ]);
        
        # Face recognition needs to be installed via pip as it's not in nixpkgs
        faceRecognitionSetup = pkgs.writeShellScriptBin "setup-face-recognition" ''
          echo "Installing face_recognition packages..."
          ${pythonEnv}/bin/pip install --user imagehash face_recognition
          ${pythonEnv}/bin/pip install --user git+https://github.com/ageitgey/face_recognition_models
          echo "✓ Face recognition packages installed!"
        '';
        
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            faceRecognitionSetup
            
            # System libraries needed by OpenCV and other packages
            pkgs.libGL
            pkgs.glib
            pkgs.libz
            pkgs.stdenv.cc.cc.lib
            
            # Build tools (in case pip needs to compile anything)
            pkgs.cmake
            pkgs.gcc
            pkgs.gnumake
            pkgs.pkg-config
            
            # Image libraries
            pkgs.libpng
            pkgs.libjpeg
            pkgs.libwebp
            
            # X11 support
            pkgs.xorg.libX11
            pkgs.xorg.libXext
            
            # BLAS/LAPACK
            pkgs.openblas
            pkgs.lapack
          ];

          shellHook = ''
            # Set library paths
            export LD_LIBRARY_PATH="${pkgs.libGL}/lib:${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.glib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
            
            # Set up Python path for user packages
            export PYTHONPATH="$HOME/.local/lib/python${python.pythonVersion}/site-packages:$PYTHONPATH"
            
            echo ""
            echo "╔════════════════════════════════════════════════╗"
            echo "║   Photo Album Organizer - Pure NixOS Setup    ║"
            echo "╚════════════════════════════════════════════════╝"
            echo ""
            echo "  Python: $(python --version)"
            echo "  Using: NixOS-managed Python packages"
            echo ""
            
            # Check if face_recognition is installed
            if ! python -c "import face_recognition" 2>/dev/null; then
              echo "⚠️  face_recognition not yet installed"
              echo ""
              echo "Run this once to install face_recognition:"
              echo "  setup-face-recognition"
              echo ""
            else
              echo "✓ All packages ready!"
              echo ""
              echo "Run the organizer:"
              echo "  python photo_organizer.py -s <source> -o <output>"
              echo ""
            fi
          '';
        };
        
        # Create a package for the photo organizer
        packages.default = pkgs.python311Packages.buildPythonApplication {
          pname = "photo-organizer";
          version = "0.1.0";
          src = ./.;
          
          propagatedBuildInputs = with pkgs.python311Packages; [
            pillow
            opencv4
            numpy
            scipy
            pywavelets
            dlib
            click
          ];
          
          # Skip tests for now
          doCheck = false;
        };
      }
    );
}
