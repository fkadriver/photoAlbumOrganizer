#!/usr/bin/env bash
#
# Photo Album Organizer - Setup Script for Ubuntu/Debian and macOS
#
# This script installs system dependencies and sets up the Python environment.
# Equivalent to direnv + nix on NixOS.
#
# Usage:
#   ./scripts/setup.sh          # Full setup (system deps + Python env)
#   ./scripts/setup.sh --venv   # Python venv only (skip system deps)
#   ./scripts/setup.sh --check  # Check if environment is ready
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Photo Album Organizer - Setup${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_step() {
    echo -e "\n${GREEN}▶${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ -f /etc/debian_version ]]; then
        echo "debian"
    elif [[ -f /etc/redhat-release ]]; then
        echo "redhat"
    else
        echo "unknown"
    fi
}

detect_python() {
    # Try python3.11 first, then python3
    if command -v python3.11 &> /dev/null; then
        echo "python3.11"
    elif command -v python3 &> /dev/null; then
        local version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        if [[ "$version" == "3.11" ]] || [[ "$version" == "3.12" ]] || [[ "$version" == "3.13" ]]; then
            echo "python3"
        else
            echo ""
        fi
    else
        echo ""
    fi
}

install_macos_deps() {
    print_step "Installing macOS dependencies via Homebrew..."

    if ! command -v brew &> /dev/null; then
        print_error "Homebrew not found. Install from https://brew.sh/"
        exit 1
    fi

    # Install dependencies
    brew install python@3.11 cmake openblas lapack libheif ffmpeg || true

    print_success "macOS dependencies installed"
}

install_debian_deps() {
    print_step "Installing Ubuntu/Debian dependencies..."

    # Check if we need Python 3.11 from deadsnakes
    local python_cmd=$(detect_python)
    if [[ -z "$python_cmd" ]]; then
        print_warning "Python 3.11+ not found. Adding deadsnakes PPA..."

        if ! command -v add-apt-repository &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y software-properties-common
        fi

        sudo add-apt-repository -y ppa:deadsnakes/ppa
        sudo apt-get update
    fi

    # Install all dependencies
    print_step "Installing system packages..."
    sudo apt-get install -y \
        python3.11 python3.11-venv python3.11-dev \
        cmake build-essential \
        libopenblas-dev liblapack-dev \
        libgl1 libglib2.0-0 \
        libheif-dev ffmpeg

    print_success "Ubuntu/Debian dependencies installed"
}

setup_venv() {
    local python_cmd=$(detect_python)

    if [[ -z "$python_cmd" ]]; then
        print_error "Python 3.11+ not found. Run setup without --venv first."
        exit 1
    fi

    print_step "Setting up Python virtual environment..."
    echo "  Using: $python_cmd ($($python_cmd --version))"

    cd "$PROJECT_ROOT"

    # Create venv if it doesn't exist
    if [[ ! -d "venv" ]]; then
        $python_cmd -m venv venv
        print_success "Created virtual environment"
    else
        print_warning "Virtual environment already exists"
    fi

    # Activate and install
    source venv/bin/activate

    print_step "Upgrading pip..."
    pip install --upgrade pip wheel

    print_step "Installing Python packages..."
    pip install -r requirements.txt

    # Install face_recognition_models
    print_step "Installing face_recognition models..."
    pip install git+https://github.com/ageitgey/face_recognition_models || {
        print_warning "face_recognition_models failed - face detection may be limited"
    }

    print_success "Python environment ready"
}

verify_installation() {
    print_step "Verifying installation..."

    cd "$PROJECT_ROOT"

    if [[ ! -d "venv" ]]; then
        print_error "Virtual environment not found. Run: ./scripts/setup.sh"
        return 1
    fi

    source venv/bin/activate

    # Run verification script
    if python scripts/verify_environment.py; then
        print_success "Environment verification passed"
    else
        print_warning "Some optional features may not be available"
    fi
}

show_activation_instructions() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Setup complete!${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "To activate the environment:"
    echo -e "  ${YELLOW}source venv/bin/activate${NC}"
    echo ""
    echo "Then run:"
    echo -e "  ${YELLOW}./photo_organizer.py -i${NC}          # Interactive mode"
    echo -e "  ${YELLOW}./photo_organizer.py --help${NC}      # Show all options"
    echo -e "  ${YELLOW}scripts/viewer start${NC}             # Start web viewer"
    echo ""
}

check_environment() {
    print_header
    print_step "Checking environment..."

    local all_good=true

    # Check Python
    local python_cmd=$(detect_python)
    if [[ -n "$python_cmd" ]]; then
        print_success "Python: $($python_cmd --version)"
    else
        print_error "Python 3.11+ not found"
        all_good=false
    fi

    # Check venv
    if [[ -d "$PROJECT_ROOT/venv" ]]; then
        print_success "Virtual environment exists"
    else
        print_error "Virtual environment not found"
        all_good=false
    fi

    # Check key system dependencies
    if command -v ffmpeg &> /dev/null; then
        print_success "ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
    else
        print_warning "ffmpeg not found (needed for video support)"
    fi

    if command -v cmake &> /dev/null; then
        print_success "cmake: $(cmake --version | head -1)"
    else
        print_warning "cmake not found (needed for dlib compilation)"
    fi

    # Check Python packages if venv exists
    if [[ -d "$PROJECT_ROOT/venv" ]]; then
        source "$PROJECT_ROOT/venv/bin/activate"

        echo ""
        print_step "Python packages:"

        for pkg in pillow imagehash opencv-python face_recognition numpy; do
            if python -c "import ${pkg//-/_}" 2>/dev/null; then
                print_success "$pkg installed"
            else
                print_warning "$pkg not installed"
                all_good=false
            fi
        done
    fi

    echo ""
    if $all_good; then
        print_success "Environment is ready!"
        return 0
    else
        print_warning "Some components missing. Run: ./scripts/setup.sh"
        return 1
    fi
}

main() {
    cd "$PROJECT_ROOT"

    case "${1:-}" in
        --check)
            check_environment
            ;;
        --venv)
            print_header
            setup_venv
            verify_installation
            show_activation_instructions
            ;;
        --help|-h)
            echo "Usage: ./scripts/setup.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  (none)    Full setup (system dependencies + Python venv)"
            echo "  --venv    Python venv only (skip system deps)"
            echo "  --check   Check if environment is ready"
            echo "  --help    Show this help"
            ;;
        *)
            print_header

            local os=$(detect_os)
            echo -e "Detected OS: ${YELLOW}$os${NC}"

            case "$os" in
                macos)
                    install_macos_deps
                    ;;
                debian)
                    install_debian_deps
                    ;;
                redhat)
                    print_error "Red Hat/Fedora not yet supported. Contributions welcome!"
                    print_warning "You can try: ./scripts/setup.sh --venv (after installing deps manually)"
                    exit 1
                    ;;
                *)
                    print_warning "Unknown OS. Skipping system dependencies."
                    print_warning "Make sure Python 3.11+, cmake, ffmpeg, and libheif are installed."
                    ;;
            esac

            setup_venv
            verify_installation
            show_activation_instructions
            ;;
    esac
}

main "$@"
