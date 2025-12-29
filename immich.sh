#!/usr/bin/env bash
#
# Immich Photo Organizer Script
#
# This script runs the photo organizer with your Immich instance.
# For security, the API key is loaded from environment or config file.
#

set -euo pipefail

# Configuration
IMMICH_URL="${IMMICH_URL:-https://immich.warthog-royal.ts.net}"
IMMICH_API_KEY="${IMMICH_API_KEY:-}"
IGNORE_TIMESTAMP="${IGNORE_TIMESTAMP:-0}"  # Set to 1 to disable time window check

# Load API key from config file if exists and not already set
CONFIG_FILE="${HOME}/.config/photo-organizer/immich.conf"
if [ -z "$IMMICH_API_KEY" ] && [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

# Check if API key is set
if [ -z "$IMMICH_API_KEY" ]; then
    echo "Error: IMMICH_API_KEY not set!"
    echo ""
    echo "Set it using one of these methods:"
    echo ""
    echo "1. Environment variable:"
    echo "   export IMMICH_API_KEY='your-key-here'"
    echo ""
    echo "2. Config file (~/.config/photo-organizer/immich.conf):"
    echo "   mkdir -p ~/.config/photo-organizer"
    echo "   echo 'IMMICH_API_KEY=\"your-key-here\"' > ~/.config/photo-organizer/immich.conf"
    echo "   chmod 600 ~/.config/photo-organizer/immich.conf"
    echo ""
    exit 1
fi

# Default mode
MODE="${1:-tag-only}"

# Common arguments
COMMON_ARGS=(
    --source-type immich
    --immich-url "$IMMICH_URL"
    --immich-api-key "$IMMICH_API_KEY"
    --threshold 5
)

# Add --no-time-window flag if IGNORE_TIMESTAMP is set
if [ "$IGNORE_TIMESTAMP" = "1" ]; then
    COMMON_ARGS+=(--no-time-window)
fi

# Run based on mode
case "$MODE" in
    tag-only|tag)
        echo "🏷️  Tagging potential duplicates in Immich..."
        echo ""
        python photo_organizer.py "${COMMON_ARGS[@]}" --tag-only
        ;;

    albums|create-albums)
        echo "📁 Creating albums for similar photo groups..."
        echo ""
        python photo_organizer.py "${COMMON_ARGS[@]}" \
            --create-albums \
            --mark-best-favorite \
            --album-prefix "Organized-"
        ;;

    download)
        OUTPUT_DIR="${2:-~/Organized/Immich}"
        echo "⬇️  Downloading and organizing photos to: $OUTPUT_DIR"
        echo ""
        python photo_organizer.py "${COMMON_ARGS[@]}" \
            --output "$OUTPUT_DIR"
        ;;

    album)
        if [ -z "${2:-}" ]; then
            echo "Error: Album name required"
            echo "Usage: $0 album 'Album Name' [mode]"
            exit 1
        fi
        ALBUM_NAME="$2"
        ALBUM_MODE="${3:-create-albums}"

        echo "📷 Processing album: $ALBUM_NAME"
        echo ""

        case "$ALBUM_MODE" in
            tag)
                python photo_organizer.py "${COMMON_ARGS[@]}" \
                    --immich-album "$ALBUM_NAME" \
                    --tag-only
                ;;
            create-albums|albums)
                python photo_organizer.py "${COMMON_ARGS[@]}" \
                    --immich-album "$ALBUM_NAME" \
                    --create-albums \
                    --mark-best-favorite
                ;;
            download)
                OUTPUT_DIR="${4:-~/Organized/Immich/$ALBUM_NAME}"
                python photo_organizer.py "${COMMON_ARGS[@]}" \
                    --immich-album "$ALBUM_NAME" \
                    --output "$OUTPUT_DIR"
                ;;
            *)
                echo "Error: Unknown album mode: $ALBUM_MODE"
                echo "Valid modes: tag, create-albums, download"
                exit 1
                ;;
        esac
        ;;

    cleanup|clean)
        PREFIX="${2:-Organized-}"
        DRY_RUN="${3:-yes}"

        echo "🗑️  Cleaning up albums with prefix: $PREFIX"
        echo ""

        if [ "$DRY_RUN" = "yes" ]; then
            echo "DRY RUN MODE - No albums will be deleted"
            echo "To actually delete, run: $0 cleanup '$PREFIX' no"
            echo ""
        fi

        python -c "
from immich_client import ImmichClient
import os

url = os.environ.get('IMMICH_URL', 'https://immich.warthog-royal.ts.net')
api_key = os.environ.get('IMMICH_API_KEY')

if not api_key:
    print('Error: IMMICH_API_KEY not set')
    exit(1)

client = ImmichClient(url, api_key)
dry_run = '$DRY_RUN' == 'yes'
matched, deleted = client.delete_albums_by_prefix('$PREFIX', dry_run=dry_run)

if not dry_run and deleted > 0:
    print(f'\n✓ Successfully cleaned up {deleted} album(s)')
"
        ;;

    test)
        echo "🧪 Testing connection to Immich..."
        echo ""
        python test_immich_connection.py
        ;;

    help|--help|-h)
        cat <<EOF
Immich Photo Organizer Script

Usage: $0 [MODE] [OPTIONS]

MODES:
  tag-only, tag          Tag duplicate photos in Immich (default, safest)
  albums, create-albums  Create albums for similar photo groups
  download [OUTPUT_DIR]  Download and organize photos locally
  album NAME [MODE]      Process specific album
  cleanup [PREFIX] [yes|no]  Delete albums by prefix (default: "Organized-", dry-run: yes)
  test                   Test Immich connection
  help                   Show this help message

ALBUM MODES:
  tag                    Tag duplicates in specific album
  create-albums          Create sub-albums from album
  download [OUTPUT_DIR]  Download and organize album

EXAMPLES:
  # Tag duplicates (safest, recommended first step)
  $0 tag-only

  # Create albums and mark favorites
  $0 create-albums

  # Download to specific directory
  $0 download ~/Photos/Organized

  # Process specific album
  $0 album "Vacation 2024" create-albums

  # Clean up created albums (dry run first)
  $0 cleanup

  # Actually delete albums with "Organized-" prefix
  $0 cleanup "Organized-" no

  # Delete albums with custom prefix
  $0 cleanup "MyPrefix-" no

  # Test connection
  $0 test

CONFIGURATION:
  Set IMMICH_API_KEY via environment or config file:
  ~/.config/photo-organizer/immich.conf

  URL: $IMMICH_URL
  API Key: ${IMMICH_API_KEY:0:10}...

OPTIONS:
  IGNORE_TIMESTAMP=1    Disable time window check, group by visual similarity only
                        (default: groups photos taken within 5 minutes)

  Example: IGNORE_TIMESTAMP=1 $0 tag-only

THRESHOLD:
  Default: 5 (burst photos)
  Lower (3): Stricter (only near-duplicates)
  Higher (8): Looser (similar compositions)

  To customize threshold, edit this script and change:
  --threshold 5

For more options, see: python photo_organizer.py --help
EOF
        ;;

    *)
        echo "Error: Unknown mode: $MODE"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac
