#!/usr/bin/env python3
"""
Environment verification script for Photo Album Organizer.
Tests all required dependencies and their functionality.
"""

import sys
from typing import List, Tuple


def test_import(module_name: str, display_name: str = None) -> Tuple[bool, str]:
    """Test if a module can be imported."""
    if display_name is None:
        display_name = module_name

    try:
        __import__(module_name)
        return True, f"✓ {display_name}"
    except ImportError as e:
        return False, f"✗ {display_name}: {str(e)}"
    except Exception as e:
        return False, f"✗ {display_name}: Unexpected error: {str(e)}"


def test_functionality() -> List[Tuple[bool, str]]:
    """Test actual functionality of key packages."""
    results = []

    # Test NumPy operations
    try:
        import numpy as np
        arr = np.array([1, 2, 3])
        assert arr.sum() == 6
        results.append((True, "✓ NumPy operations working"))
    except Exception as e:
        results.append((False, f"✗ NumPy operations failed: {e}"))

    # Test PIL/Pillow image operations
    try:
        from PIL import Image
        import io
        img = Image.new('RGB', (10, 10), color='red')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        results.append((True, "✓ Pillow image operations working"))
    except Exception as e:
        results.append((False, f"✗ Pillow operations failed: {e}"))

    # Test OpenCV
    try:
        import cv2
        import numpy as np
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        results.append((True, "✓ OpenCV operations working"))
    except Exception as e:
        results.append((False, f"✗ OpenCV operations failed: {e}"))

    # Test imagehash
    try:
        from PIL import Image
        import imagehash
        img = Image.new('RGB', (10, 10), color='blue')
        imagehash.dhash(img)
        results.append((True, "✓ ImageHash operations working"))
    except Exception as e:
        results.append((False, f"✗ ImageHash operations failed: {e}"))

    return results


def test_face_backends() -> List[Tuple[bool, str, bool]]:
    """Test available face detection backends. Returns (success, message, required)."""
    results = []

    # MediaPipe — default backend, should be present
    try:
        import mediapipe
        results.append((True, f"✓ MediaPipe {mediapipe.__version__} (default backend)", True))
    except ImportError:
        results.append((False, "✗ MediaPipe: not installed  →  pip install mediapipe>=0.10.0", True))

    # face_recognition / dlib — optional, adds identity matching
    try:
        import face_recognition
        results.append((True, "✓ face_recognition (dlib backend, optional)", False))
    except ImportError:
        results.append((True, "○ face_recognition not installed (optional — skip if not needed)", False))

    # GPU backends — optional
    for pkg, label in [
        ("facenet_pytorch", "FaceNet/PyTorch (GPU backend, optional)"),
        ("insightface",     "InsightFace (GPU backend, optional)"),
        ("ultralytics",     "YOLOv8-Face (GPU backend, optional)"),
    ]:
        try:
            __import__(pkg)
            results.append((True, f"✓ {label}", False))
        except ImportError:
            results.append((True, f"○ {label} not installed", False))

    return results


def test_ml_scorer() -> List[Tuple[bool, str, bool]]:
    """Test ML quality scorer backends."""
    results = []

    try:
        import pyiqa
        results.append((True, "✓ pyiqa (TOPIQ-IAA aesthetic scorer + BRISQUE pre-filter)", False))
    except ImportError:
        results.append((True, "○ pyiqa not installed (optional) — pip install pyiqa", False))

    try:
        import torch
        results.append((True, f"✓ PyTorch {torch.__version__} (GPU scoring)", False))
    except ImportError:
        results.append((True, "○ PyTorch not installed (optional, needed for GPU backends)", False))

    return results


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Photo Album Organizer - Environment Verification")
    print("=" * 60)
    print()

    # Required packages
    print("Required packages:")
    print("-" * 60)

    required_packages = [
        ("PIL",       "Pillow"),
        ("imagehash", "ImageHash"),
        ("cv2",       "OpenCV"),
        ("numpy",     "NumPy"),
        ("scipy",     "SciPy"),
        ("requests",  "requests"),
        ("pathlib",   "pathlib (stdlib)"),
        ("datetime",  "datetime (stdlib)"),
        ("json",      "json (stdlib)"),
    ]

    import_results = []
    for module, display in required_packages:
        success, message = test_import(module, display)
        import_results.append((success, message))
        print(message)

    print()

    # Functionality checks
    print("Functionality checks:")
    print("-" * 60)
    functionality_results = test_functionality()
    for success, message in functionality_results:
        print(message)

    print()

    # Face backends
    print("Face detection backends:")
    print("-" * 60)
    backend_results = test_face_backends()
    required_backend_failures = []
    for success, message, required in backend_results:
        print(message)
        if not success and required:
            required_backend_failures.append(message)

    print()

    # ML scorer
    print("ML quality scoring (optional):")
    print("-" * 60)
    scorer_results = test_ml_scorer()
    for success, message, _ in scorer_results:
        print(message)

    print()
    print("=" * 60)

    # Summary — only required items count as failures
    required_results = import_results + [(s, m) for s, m in functionality_results]
    total = len(required_results)
    passed = sum(1 for s, _ in required_results if s)
    failed = total - passed + len(required_backend_failures)

    print(f"Results: {passed}/{total} required checks passed")

    if failed > 0:
        print()
        print("⚠️  ISSUES DETECTED")
        print()
        print("Missing or broken required packages:")
        for success, message in required_results:
            if not success:
                print(f"  {message}")
        for msg in required_backend_failures:
            print(f"  {msg}")
        print()
        print("To fix, run:")
        print("  pip install -r requirements.txt")
        print()
        sys.exit(1)
    else:
        print()
        print("✓ All required checks passed! Environment is ready.")
        print()
        print("You can now run:")
        print("  python src/photo_organizer.py -s ~/Photos -o ~/Organized")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
