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
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        results.append((True, "✓ OpenCV operations working"))
    except Exception as e:
        results.append((False, f"✗ OpenCV operations failed: {e}"))
    
    # Test imagehash
    try:
        from PIL import Image
        import imagehash
        img = Image.new('RGB', (10, 10), color='blue')
        hash_val = imagehash.dhash(img)
        results.append((True, "✓ ImageHash operations working"))
    except Exception as e:
        results.append((False, f"✗ ImageHash operations failed: {e}"))
    
    # Test face_recognition
    try:
        import face_recognition
        import numpy as np
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        face_locations = face_recognition.face_locations(image)
        results.append((True, "✓ Face recognition operations working"))
    except Exception as e:
        results.append((False, f"✗ Face recognition operations failed: {e}"))
    
    return results

def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Photo Album Organizer - Environment Verification")
    print("=" * 60)
    print()
    
    # Test imports
    print("Testing package imports...")
    print("-" * 60)
    
    required_packages = [
        ("PIL", "Pillow"),
        ("imagehash", "ImageHash"),
        ("cv2", "OpenCV"),
        ("numpy", "NumPy"),
        ("scipy", "SciPy"),
        ("face_recognition", "face_recognition"),
        ("pathlib", "pathlib (stdlib)"),
        ("datetime", "datetime (stdlib)"),
        ("json", "json (stdlib)"),
    ]
    
    import_results = []
    for module, display in required_packages:
        success, message = test_import(module, display)
        import_results.append((success, message))
        print(message)
    
    print()
    
    # Test functionality
    print("Testing package functionality...")
    print("-" * 60)
    
    functionality_results = test_functionality()
    for success, message in functionality_results:
        print(message)
    
    print()
    print("=" * 60)
    
    # Summary
    all_results = import_results + functionality_results
    total = len(all_results)
    passed = sum(1 for success, _ in all_results if success)
    failed = total - passed
    
    print(f"Results: {passed}/{total} tests passed")
    
    if failed > 0:
        print()
        print("⚠️  ISSUES DETECTED")
        print()
        print("Missing or broken packages:")
        for success, message in all_results:
            if not success:
                print(f"  {message}")
        print()
        print("To fix, run:")
        print("  pip install -r requirements.txt")
        print("  pip install git+https://github.com/ageitgey/face_recognition_models")
        print()
        sys.exit(1)
    else:
        print()
        print("✓ All tests passed! Environment is ready.")
        print()
        print("You can now run:")
        print("  python photo_organizer.py -s ~/Photos -o ~/Organized")
        print()
        sys.exit(0)

if __name__ == "__main__":
    main()
