#!/usr/bin/env python3
"""
Test script to verify Immich connection and API access.
Usage: python test_immich_connection.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from immich_client import ImmichClient


def _load_config_file():
    """Load settings from config file if it exists."""
    config = {}
    config_path = os.path.expanduser('~/.config/photo-organizer/immich.conf')
    if os.path.isfile(config_path):
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, _, value = line.partition('=')
                    config[key.strip()] = value.strip().strip('"').strip("'")
    return config


def test_connection():
    """Test Immich connection and basic API access."""

    # Get credentials from environment, config file, or prompt
    config = _load_config_file()
    url = os.getenv('IMMICH_URL') or config.get('IMMICH_URL') or input("Enter Immich URL (e.g., http://immich:2283): ").strip()
    api_key = os.getenv('IMMICH_API_KEY') or config.get('IMMICH_API_KEY') or input("Enter Immich API Key: ").strip()

    if not url or not api_key:
        print("❌ Error: URL and API key are required")
        return False

    print(f"\n🔍 Testing connection to {url}...")
    print("=" * 60)

    try:
        # Create client
        client = ImmichClient(url, api_key, verify_ssl=True)

        # Test connection
        print("\n1. Testing server ping...")
        if client.ping():
            print("   ✅ Server is reachable")
        else:
            print("   ❌ Server ping failed")
            return False

        # Get assets
        print("\n2. Fetching assets...")
        assets = client.get_all_assets()
        print(f"   ✅ Found {len(assets)} image assets")

        if assets:
            sample = assets[0]
            print(f"\n   Sample asset:")
            print(f"   - ID: {sample.id}")
            print(f"   - Filename: {sample.original_file_name}")
            print(f"   - Type: {sample.type}")
            print(f"   - Favorite: {sample.is_favorite}")

            # Test thumbnail download
            print("\n3. Testing thumbnail download...")
            thumbnail = client.get_asset_thumbnail(sample.id)
            if thumbnail:
                print(f"   ✅ Downloaded thumbnail ({len(thumbnail)} bytes)")
            else:
                print("   ⚠️  Thumbnail download failed")

        # Get albums
        print("\n4. Fetching albums...")
        albums = client.get_albums()
        print(f"   ✅ Found {len(albums)} albums")

        if albums:
            print("\n   Available albums:")
            for album in albums[:5]:  # Show first 5
                name = album.get('albumName', 'Unnamed')
                count = album.get('assetCount', 0)
                print(f"   - {name} ({count} assets)")

            if len(albums) > 5:
                print(f"   ... and {len(albums) - 5} more")

        print("\n" + "=" * 60)
        print("✅ All tests passed! Immich integration is working.")
        print("\nYou can now use:")
        print(f"  python photo_organizer.py \\")
        print(f"    --source-type immich \\")
        print(f"    --immich-url {url} \\")
        print(f"    --immich-api-key YOUR_KEY \\")
        print(f"    --tag-only")
        print("=" * 60)

        return True

    except ConnectionError as e:
        print(f"\n❌ Connection error: {e}")
        print("\nTroubleshooting:")
        print("  - Verify Immich is running")
        print("  - Check the URL is correct")
        print("  - Ensure port is accessible")
        return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("  - Verify API key is correct")
        print("  - Check Immich version compatibility (v1.95+ recommended)")
        print("  - Try with --no-verify-ssl if using self-signed certificate")
        return False


if __name__ == "__main__":
    print("🔧 Immich Connection Test")
    success = test_connection()
    sys.exit(0 if success else 1)
