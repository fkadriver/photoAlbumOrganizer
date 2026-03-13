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
        lib = pkgs.lib;
        python = pkgs.python312;
        pythonPackages = python.pkgs;
        isDarwin = pkgs.stdenv.isDarwin;
        isLinux = pkgs.stdenv.isLinux;

        # Packages only available / needed on Linux
        linuxOnlyPkgs = if isLinux then (with pkgs; [
          libGL
          glib
          zlib
          stdenv.cc.cc.lib
          libpng
          libjpeg
          libwebp
          xorg.libX11
          xorg.libXext
          xorg.libxcb
          openblas
          lapack
          opencv4
        ]) else [];

        # LD_LIBRARY_PATH entries (Linux only)
        ldLibPath = if isLinux then
          lib.concatStringsSep ":" (map (p: "${p}/lib") (with pkgs; [
            libGL
            stdenv.cc.cc.lib
            glib
            zlib
            xorg.libX11
            xorg.libXext
            xorg.libxcb
          ]))
        else "";
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Python 3.12
            python
            pythonPackages.pip
            pythonPackages.virtualenv

            # Build tools
            cmake
            gnumake
            pkg-config
          ] ++ linuxOnlyPkgs;

          shellHook = (if isLinux then ''
            # Set library paths (Linux only)
            export LD_LIBRARY_PATH="${ldLibPath}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
          '' else ''
            # macOS: system libs handled by the OS
          '') + ''

            # Fix BLAS/LAPACK warnings by using single-threaded mode
            export OMP_NUM_THREADS=1
            export OPENBLAS_NUM_THREADS=1
            export MKL_NUM_THREADS=1
            export VECLIB_MAXIMUM_THREADS=1
            export NUMEXPR_NUM_THREADS=1

            # Set build environment variables
          '' + (if isLinux then ''
            export CMAKE_PREFIX_PATH="${pkgs.openblas}:${pkgs.lapack}"
            export PKG_CONFIG_PATH="${pkgs.openblas}/lib/pkgconfig:${pkgs.lapack}/lib/pkgconfig:''${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
          '' else "") + ''
            export PYTHONDONTWRITEBYTECODE=1

            # Create virtual environment if it doesn't exist
            if [ ! -d "venv" ]; then
              echo "Creating Python virtual environment with Python ${python.version}..."
              ${python}/bin/python -m venv venv
            fi

            # Activate virtual environment
            source venv/bin/activate

            # Only run full checks on first load or if forced
            CHECK_MARKER=".direnv/.check-done"
            FORCE_CHECK=''${FORCE_CHECK:-0}

            if [ ! -f "$CHECK_MARKER" ] || [ "$FORCE_CHECK" = "1" ]; then
              # Create .direnv directory if it doesn't exist
              mkdir -p .direnv

              # Upgrade pip quietly
              pip install --upgrade pip setuptools wheel >/dev/null 2>&1

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
              python -c "import requests" 2>/dev/null || MISSING_PACKAGES+=("requests")
              python -c "import face_recognition" 2>/dev/null || MISSING_PACKAGES+=("face_recognition")

              if [ ''${#MISSING_PACKAGES[@]} -eq 0 ]; then
                echo "✓ All packages installed!"
                echo ""
                echo "Ready to use:"
                echo "  • Interactive: ./photo_organizer.py -i"
                echo "  • Local: ./photo_organizer.py -s <source> -o <output>"
                echo "  • Immich: ./photo_organizer.py --source-type immich --immich-url <url> --immich-api-key <key> --tag-only"
                echo "  • Immich (wrapper): ./scripts/immich.sh help"
                echo ""
                echo "Tip: Run 'python scripts/test_immich_connection.py' to test Immich connectivity"
                echo ""

                # Mark check as done
                touch "$CHECK_MARKER"
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
                echo "After installing, run: FORCE_CHECK=1 direnv reload"
                echo ""
              fi
            fi
          '';
        };
      }
    );
}
