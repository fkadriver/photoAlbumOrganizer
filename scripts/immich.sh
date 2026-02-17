#!/usr/bin/env bash
#
# Immich Photo Organizer Script
#
# This script runs the photo organizer with your Immich instance.
# For security, the API key is loaded from environment or config file.
#

set -euo pipefail

# Resolve project root from script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration
IMMICH_URL="${IMMICH_URL:-https://immich.warthog-royal.ts.net}"
IMMICH_API_KEY="${IMMICH_API_KEY:-}"

# Default options
IGNORE_TIMESTAMP=0
ENABLE_HDR=0
ENABLE_FACE_SWAP=0
RESUME=0
FORCE_FRESH=0
TEST_LIMIT=""
THREADS=2
THRESHOLD=5
MIN_GROUP_SIZE=3
ARCHIVE_NON_BEST=0
VERBOSE=0

# Load config file if exists and not already set
CONFIG_FILE="${HOME}/.config/photo-organizer/immich.conf"
if [ -z "$IMMICH_API_KEY" ] && [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

# Export for Python subprocesses
export IMMICH_URL IMMICH_API_KEY

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

# Parse options
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ignore-timestamp)
            IGNORE_TIMESTAMP=1
            shift
            ;;
        --enable-hdr)
            ENABLE_HDR=1
            shift
            ;;
        --enable-face-swap)
            ENABLE_FACE_SWAP=1
            shift
            ;;
        --resume)
            RESUME=1
            shift
            ;;
        --force-fresh)
            FORCE_FRESH=1
            shift
            ;;
        --limit)
            TEST_LIMIT="$2"
            shift 2
            ;;
        --threads)
            THREADS="$2"
            shift 2
            ;;
        --threshold|-t)
            THRESHOLD="$2"
            shift 2
            ;;
        --min-group-size)
            MIN_GROUP_SIZE="$2"
            shift 2
            ;;
        --archive-non-best)
            ARCHIVE_NON_BEST=1
            shift
            ;;
        --verbose)
            VERBOSE=1
            shift
            ;;
        *)
            break
            ;;
    esac
done

# Default mode
MODE="${1:-tag-only}"
shift || true

# Common arguments
COMMON_ARGS=(
    --source-type immich
    --immich-url "$IMMICH_URL"
    --immich-api-key "$IMMICH_API_KEY"
    --threshold "$THRESHOLD"
    --min-group-size "$MIN_GROUP_SIZE"
)

# Add --time-window 0 flag if requested (ignore timestamp)
if [ "$IGNORE_TIMESTAMP" = "1" ]; then
    COMMON_ARGS+=(--time-window 0)
fi

# Add --enable-hdr flag if requested
if [ "$ENABLE_HDR" = "1" ]; then
    COMMON_ARGS+=(--enable-hdr)
fi

# Add --enable-face-swap flag if requested
if [ "$ENABLE_FACE_SWAP" = "1" ]; then
    COMMON_ARGS+=(--enable-face-swap)
fi

# Add --resume flag if requested
if [ "$RESUME" = "1" ]; then
    COMMON_ARGS+=(--resume)
fi

# Add --force-fresh flag if requested
if [ "$FORCE_FRESH" = "1" ]; then
    COMMON_ARGS+=(--force-fresh)
fi

# Add --limit flag if set
if [ -n "$TEST_LIMIT" ]; then
    COMMON_ARGS+=(--limit "$TEST_LIMIT")
    echo "🔬 TEST MODE: Processing limited to first $TEST_LIMIT photos"
    echo ""
fi

# Add --threads flag
COMMON_ARGS+=(--threads "$THREADS")

# Add --archive-non-best flag if requested
if [ "$ARCHIVE_NON_BEST" = "1" ]; then
    COMMON_ARGS+=(--archive-non-best)
fi

# Add --verbose flag if requested
if [ "$VERBOSE" = "1" ]; then
    COMMON_ARGS+=(--verbose)
fi

# Print active features
FEATURES=()
[ "$IGNORE_TIMESTAMP" = "1" ] && FEATURES+=("ignore-timestamp")
[ "$ENABLE_HDR" = "1" ] && FEATURES+=("HDR")
[ "$ENABLE_FACE_SWAP" = "1" ] && FEATURES+=("face-swap")
[ "$RESUME" = "1" ] && FEATURES+=("resume")
[ "$ARCHIVE_NON_BEST" = "1" ] && FEATURES+=("archive-non-best")

if [ ${#FEATURES[@]} -gt 0 ]; then
    echo "✨ Active features: ${FEATURES[*]}"
    echo ""
fi

# Run based on mode
case "$MODE" in
    tag-only|tag|"")
        echo "🏷️  Tagging potential duplicates in Immich..."
        echo ""
        ./photo_organizer.py "${COMMON_ARGS[@]}" --tag-only
        ;;

    albums|create-albums)
        echo "📁 Creating albums for similar photo groups..."
        echo ""

        # For HDR and face swap, we need to download photos
        if [ "$ENABLE_HDR" = "1" ] || [ "$ENABLE_FACE_SWAP" = "1" ]; then
            OUTPUT_DIR="${1:-$HOME/Organized/Immich}"
            echo "⬇️  Also downloading to: $OUTPUT_DIR (required for HDR/face-swap)"
            echo ""
            ./photo_organizer.py "${COMMON_ARGS[@]}" \
                --create-albums \
                --mark-best-favorite \
                --album-prefix "Organized-" \
                --output "$OUTPUT_DIR"
        else
            ./photo_organizer.py "${COMMON_ARGS[@]}" \
                --create-albums \
                --mark-best-favorite \
                --album-prefix "Organized-"
        fi
        ;;

    download)
        OUTPUT_DIR="${1:-$HOME/Organized/Immich}"
        echo "⬇️  Downloading and organizing photos to: $OUTPUT_DIR"
        echo ""
        ./photo_organizer.py "${COMMON_ARGS[@]}" \
            --output "$OUTPUT_DIR"
        ;;

    album)
        if [ -z "${1:-}" ]; then
            echo "Error: Album name required"
            echo "Usage: $0 [OPTIONS] album 'Album Name' [mode]"
            exit 1
        fi
        ALBUM_NAME="$1"
        ALBUM_MODE="${2:-create-albums}"

        echo "📷 Processing album: $ALBUM_NAME"
        echo ""

        case "$ALBUM_MODE" in
            tag)
                ./photo_organizer.py "${COMMON_ARGS[@]}" \
                    --immich-album "$ALBUM_NAME" \
                    --tag-only
                ;;
            create-albums|albums)
                # For HDR and face swap, we need to download photos
                if [ "$ENABLE_HDR" = "1" ] || [ "$ENABLE_FACE_SWAP" = "1" ]; then
                    OUTPUT_DIR="${3:-$HOME/Organized/Immich/$ALBUM_NAME}"
                    echo "⬇️  Also downloading to: $OUTPUT_DIR (required for HDR/face-swap)"
                    echo ""
                    ./photo_organizer.py "${COMMON_ARGS[@]}" \
                        --immich-album "$ALBUM_NAME" \
                        --create-albums \
                        --mark-best-favorite \
                        --output "$OUTPUT_DIR"
                else
                    ./photo_organizer.py "${COMMON_ARGS[@]}" \
                        --immich-album "$ALBUM_NAME" \
                        --create-albums \
                        --mark-best-favorite
                fi
                ;;
            download)
                OUTPUT_DIR="${3:-$HOME/Organized/Immich/$ALBUM_NAME}"
                ./photo_organizer.py "${COMMON_ARGS[@]}" \
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
        PREFIX="${1:-Organized-}"
        DRY_RUN="${2:-yes}"

        echo "🗑️  Cleaning up albums with prefix: $PREFIX"
        echo ""

        if [ "$DRY_RUN" = "yes" ]; then
            echo "DRY RUN MODE - No albums will be deleted"
            echo "To actually delete, run: $0 cleanup '$PREFIX' no"
            echo ""
        fi

        "${PROJECT_ROOT}/venv/bin/python" -c "
import sys, os, traceback
sys.path.insert(0, os.path.join('${PROJECT_ROOT}', 'src'))

try:
    from immich_client import ImmichClient

    url = os.environ.get('IMMICH_URL', 'https://immich.warthog-royal.ts.net')
    api_key = os.environ.get('IMMICH_API_KEY')

    if not api_key:
        print('Error: IMMICH_API_KEY not set')
        sys.exit(1)

    client = ImmichClient(url, api_key)
    dry_run = '$DRY_RUN' == 'yes'
    prefix = '$PREFIX'

    # Find matching albums
    albums = client.get_albums()
    matched_albums = [a for a in albums if a.get('albumName', '').startswith(prefix)]

    if not matched_albums:
        print(f'No albums found with prefix \"{prefix}\"')
        sys.exit(0)

    print(f'Found {len(matched_albums)} album(s) with prefix \"{prefix}\":')
    for album in matched_albums:
        name = album.get('albumName', 'Unknown')
        aid = album.get('id', 'Unknown')
        count = album.get('assetCount', 0)
        print(f'  - {name} (ID: {aid}, {count} assets)')

    if dry_run:
        print(f'\nDRY RUN: Would delete {len(matched_albums)} album(s)')
        print('Run with dry_run=no to actually perform cleanup')
        sys.exit(0)

    # Delete albums (photos are NOT deleted, only album grouping is removed)
    deleted = 0
    total = len(matched_albums)
    for i, album in enumerate(matched_albums, 1):
        name = album.get('albumName', 'Unknown')
        aid = album.get('id')
        if aid and client.delete_album(aid):
            deleted += 1
            if deleted % 50 == 0 or deleted == total:
                print(f'  Progress: {deleted}/{total} albums deleted')
        else:
            print(f'  ✗ Failed to delete: {name}')

    print(f'\n✓ Deleted {deleted} of {total} album(s)')

except Exception as e:
    print(f'Error during cleanup: {e}')
    traceback.print_exc()
    sys.exit(1)
"
        ;;

    test)
        echo "🧪 Testing connection to Immich..."
        echo ""
        "${PROJECT_ROOT}/venv/bin/python" scripts/test_immich_connection.py
        ;;

    help|--help|-h)
        cat <<EOF
Immich Photo Organizer Script

Usage: $0 [OPTIONS] [MODE] [MODE_ARGS]

OPTIONS:
  --ignore-timestamp     Group by visual similarity only (ignore time window)
  --enable-hdr          Enable HDR merging for bracketed exposures
  --enable-face-swap    Enable face swapping to fix closed eyes
  --resume              Resume from previous interrupted run (auto-detected by default)
  --force-fresh         Force fresh start, delete any existing progress without prompting
  --limit N             Limit processing to first N photos (for testing)
  --threads N           Number of threads for parallel processing (default: 2)
  --threshold N, -t N   Similarity threshold (0-64, lower=stricter, default: 5)
  --min-group-size N    Minimum photos per group (default: 3, min: 2)
  --archive-non-best    Archive non-best photos (hides without deleting)
  --verbose             Show detailed error messages on console

MODES:
  tag-only, tag          Tag duplicate photos in Immich (default, safest)
  albums, create-albums  Create albums for similar photo groups [OUTPUT_DIR]
  download [OUTPUT_DIR]  Download and organize photos locally
  album NAME [MODE]      Process specific album
  cleanup [PREFIX] [yes|no]  Delete albums by prefix and unfavorite assets (default: "Organized-", dry-run: yes)
  test                   Test Immich connection
  help                   Show this help message

ALBUM MODES:
  tag                    Tag duplicates in specific album
  create-albums          Create sub-albums from album [OUTPUT_DIR]
  download [OUTPUT_DIR]  Download and organize album

EXAMPLES:
  # Tag duplicates (safest, recommended first step)
  $0 tag-only

  # Create albums and mark favorites
  $0 create-albums

  # Create albums with HDR and face swapping (downloads to ~/Organized/Immich)
  $0 --enable-hdr --enable-face-swap create-albums

  # Ignore timestamps, group purely by visual similarity
  $0 --ignore-timestamp create-albums

  # All advanced features together with custom output
  $0 --ignore-timestamp --enable-hdr --enable-face-swap create-albums ~/Photos/Organized

  # Download to specific directory with all features
  $0 --enable-hdr --enable-face-swap download ~/Photos/Organized

  # Process specific album with advanced features
  $0 --enable-hdr --enable-face-swap album "Vacation 2024" create-albums

  # Test with limited photos first
  $0 --limit 50 tag-only

  # Resume interrupted run (will auto-detect and prompt if progress exists)
  $0 create-albums

  # Force resume without prompting
  $0 --resume create-albums

  # Force fresh start without prompting
  $0 --force-fresh create-albums

  # Clean up created albums (dry run first)
  $0 cleanup

  # Actually delete albums with "Organized-" prefix
  $0 cleanup "Organized-" no

  # Test connection
  $0 test

CONFIGURATION:
  Set IMMICH_API_KEY via environment or config file:
  ~/.config/photo-organizer/immich.conf

  URL: $IMMICH_URL
  API Key: ${IMMICH_API_KEY:0:10}...

FEATURES:
  --ignore-timestamp     Disable time window check (default: groups photos within 5 minutes)
  --enable-hdr          Merge bracketed exposures into HDR images
                        - Automatically detects exposure brackets from EXIF
                        - Creates hdr_merged.jpg in group directory
                        - Requires download mode
  --enable-face-swap    Fix closed eyes automatically
                        - Detects faces with closed eyes
                        - Swaps with same person from other photos
                        - Creates face_swapped.jpg in group directory
                        - Requires download mode and face_recognition library
  --resume              Resume from previous interrupted run
                        - Auto-detected: if progress file exists, you'll be prompted
                        - Use --resume to skip prompt and auto-resume
                        - Use --force-fresh to skip prompt and start fresh
                        - Useful for large libraries or unstable connections
                        - Saves progress every 50 photos
  --limit N             Process only first N photos (for testing)
                        - Quick way to test features on subset before full run
  --threads N           Number of threads for parallel processing (default: 2)
                        - Speeds up hash computation for large libraries
                        - Set to 1 for serial processing (lowest memory)
                        - Set to 4-8 for faster processing (more memory/CPU)
  --threshold N, -t N   Similarity threshold (default: 5)
                        - 0-3: Very strict (only near-duplicates)
                        - 4-6: Burst photos (recommended)
                        - 7-10: Similar compositions (loose)
                        - Use --threshold 3 for strict duplicate detection
                        - Use --threshold 8 for grouping similar scenes
  --verbose             Show detailed error messages on console
                        - By default, errors are only logged to file
                        - Enable this to see errors during processing
                        - Useful for debugging issues

THRESHOLD:
  Default: 5 (burst photos)
  Lower (3): Stricter (only near-duplicates)
  Higher (8): Looser (similar compositions)

  Customize with: --threshold N or -t N

NOTE: HDR and face-swap require downloading photos, so they automatically
      enable download mode when used with 'create-albums' mode.

For more options, see: ./photo_organizer.py --help
EOF
        ;;

    *)
        echo "Error: Unknown mode: $MODE"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac
