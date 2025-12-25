#!/usr/bin/env python3
"""Environment verification script for Photo Album Organizer."""

import sys

def test_import(module_name, display_name=None):
    """Test if a module can be imported."""
    if display_name is None:
        display_name = module_name
    try:
        __import__(module_name)
        return True, f"✓ {display_name}"
    except ImportError as e:
        return False, f"✗ {display_name}: {str(e)}"

def main():
    print("=" * 60)
    print("Photo Album Organizer - Environment Verification")
    print("=" * 60)
    print()
    
    packages = [
        ("PIL", "Pillow"),
        ("imagehash", "ImageHash"),
        ("cv2", "OpenCV"),
        ("numpy", "NumPy"),
        ("face_recognition", "face_recognition"),
    ]
    
    results = [test_import(mod, disp) for mod, disp in packages]
    
    for success, message in results:
        print(message)
    
    print()
    print("=" * 60)
    
    passed = sum(1 for success, _ in results if success)
    total = len(results)
    
    if passed == total:
        print(f"✓ All {total} packages working!")
        sys.exit(0)
    else:
        print(f"⚠️  {total - passed} package(s) missing")
        print()
        print("Run: pip install -r requirements.txt")
        print("     pip install git+https://github.com/ageitgey/face_recognition_models")
        sys.exit(1)

if __name__ == "__main__":
    main()
