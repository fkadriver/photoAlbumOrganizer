#!/usr/bin/env python3
"""
Photo Album Organizer - Main Entry Point

This tool organizes photos by grouping similar images and identifying the best photo in each group.
Supports both local filesystems and Immich photo management systems.
"""

import os
import sys
import logging
import warnings
from pathlib import Path
import argparse

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Suppress LAPACK/BLAS warnings from numpy/scipy/opencv
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

# Import after path setup
from utils import setup_logging
from photo_sources import LocalPhotoSource, ImmichPhotoSource
from organizer import PhotoOrganizer


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='Organize photo albums by grouping similar photos',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local photos
  python photo_organizer.py -s ~/Photos -o ~/OrganizedPhotos
  python photo_organizer.py -s ~/Photos -o ~/Organized -t 8 --verbose

  # Immich integration - tag duplicates
  python photo_organizer.py --source-type immich \\
    --immich-url http://immich:2283 \\
    --immich-api-key YOUR_KEY \\
    --tag-only

  # Immich integration - create albums
  python photo_organizer.py --source-type immich \\
    --immich-url http://immich:2283 \\
    --immich-api-key YOUR_KEY \\
    --create-albums \\
    --mark-best-favorite

  # Immich integration - download and organize
  python photo_organizer.py --source-type immich \\
    --immich-url http://immich:2283 \\
    --immich-api-key YOUR_KEY \\
    -o ~/Organized

  # HDR merging for bracketed exposures
  python photo_organizer.py -s ~/Photos -o ~/Organized \\
    --enable-hdr --hdr-gamma 2.2

  # Face swapping to fix closed eyes
  python photo_organizer.py -s ~/Photos -o ~/Organized \\
    --enable-face-swap

  # Both HDR and face swapping
  python photo_organizer.py -s ~/Photos -o ~/Organized \\
    --enable-hdr --enable-face-swap
        """
    )

    # Source arguments
    parser.add_argument('--source-type', choices=['local', 'immich'], default='local',
                        help='Photo source type (default: local)')
    parser.add_argument('-s', '--source',
                        help='Source directory containing photos (for local source)')
    parser.add_argument('-o', '--output',
                        help='Output directory for organized photos')

    # Immich arguments
    parser.add_argument('--immich-url',
                        help='Immich server URL (e.g., http://immich:2283)')
    parser.add_argument('--immich-api-key',
                        help='Immich API key')
    parser.add_argument('--immich-album',
                        help='Process specific Immich album')
    parser.add_argument('--immich-cache-dir',
                        help='Cache directory for Immich photos')
    parser.add_argument('--immich-cache-size', type=int, default=5000,
                        help='Cache size in MB (default: 5000)')
    parser.add_argument('--no-verify-ssl', action='store_true',
                        help='Disable SSL certificate verification')
    parser.add_argument('--use-full-resolution', action='store_true',
                        help='Download full resolution (default: use thumbnails)')

    # Processing arguments
    parser.add_argument('-t', '--threshold', type=int, default=5,
                        help='Similarity threshold (0-64, lower=stricter, default=5)')
    parser.add_argument('--time-window', type=int, default=300,
                        help='Time window in seconds for grouping (default=300, use 0 to disable time window)')

    # Immich action arguments
    parser.add_argument('--tag-only', action='store_true',
                        help='Only tag photos as duplicates (Immich only)')
    parser.add_argument('--create-albums', action='store_true',
                        help='Create Immich albums for each group')
    parser.add_argument('--album-prefix', default='Organized-',
                        help='Prefix for created albums (default: Organized-)')
    parser.add_argument('--mark-best-favorite', action='store_true',
                        help='Mark best photo in each group as favorite (Immich only)')

    # Resume capability
    parser.add_argument('--resume', action='store_true',
                        help='Resume from previous interrupted run (auto-detected by default)')
    parser.add_argument('--force-fresh', action='store_true',
                        help='Force fresh start, delete any existing progress without prompting')
    parser.add_argument('--state-file',
                        help='Path to state file for resume capability')

    # Advanced image processing
    parser.add_argument('--enable-hdr', action='store_true',
                        help='Enable HDR merging for bracketed exposure shots')
    parser.add_argument('--hdr-gamma', type=float, default=2.2,
                        help='HDR tone mapping gamma value (default: 2.2)')
    parser.add_argument('--face-backend', choices=['auto', 'face_recognition', 'mediapipe'],
                        default='auto',
                        help='Face detection backend (default: auto)')
    parser.add_argument('--enable-face-swap', action='store_true',
                        help='Enable automatic face swapping to fix closed eyes/bad expressions')
    parser.add_argument('--swap-closed-eyes', action='store_true', default=True,
                        help='Swap faces with closed eyes (default: True, use --no-swap-closed-eyes to disable)')

    # Other arguments
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose output')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without actually organizing')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit processing to first N photos (for testing, default: unlimited)')
    parser.add_argument('--threads', type=int, default=2,
                        help='Number of threads for parallel processing (default: 2)')

    args = parser.parse_args()

    # Auto-detect existing state file and prompt for resume
    if not args.resume and not args.force_fresh:
        # Determine where the state file would be
        if args.state_file:
            potential_state_file = Path(args.state_file)
        elif args.output:
            potential_state_file = Path(args.output) / '.photo_organizer_state.pkl'
        else:
            potential_state_file = Path('.photo_organizer_state.pkl')

        # Check if state file exists
        if potential_state_file.exists():
            print("\n" + "="*60)
            print("PREVIOUS RUN DETECTED")
            print("="*60)
            print(f"Found existing progress file: {potential_state_file}")
            print("\nOptions:")
            print("  [r] Resume the previous run")
            print("  [f] Start fresh (delete previous progress)")
            print("  [e] Exit")
            print("="*60)

            while True:
                choice = input("\nYour choice [r/f/e]: ").strip().lower()
                if choice in ['r', 'resume']:
                    args.resume = True
                    print("Resuming previous run...\n")
                    break
                elif choice in ['f', 'fresh']:
                    potential_state_file.unlink()
                    print("Starting fresh (previous progress deleted)...\n")
                    break
                elif choice in ['e', 'exit']:
                    print("Exiting...")
                    sys.exit(0)
                else:
                    print("Invalid choice. Please enter 'r', 'f', or 'e'")
    elif args.force_fresh:
        # Force fresh start - delete state file if it exists
        if args.state_file:
            potential_state_file = Path(args.state_file)
        elif args.output:
            potential_state_file = Path(args.output) / '.photo_organizer_state.pkl'
        else:
            potential_state_file = Path('.photo_organizer_state.pkl')

        if potential_state_file.exists():
            potential_state_file.unlink()
            print("Starting fresh (previous progress deleted)...")

    # Validate arguments
    if args.source_type == 'local':
        if not args.source:
            parser.error("--source is required for local source type")
        if not args.output:
            parser.error("--output is required for local source type")

    if args.source_type == 'immich':
        if not args.immich_url:
            parser.error("--immich-url is required for immich source type")
        if not args.immich_api_key:
            parser.error("--immich-api-key is required for immich source type")
        if not args.output and not args.tag_only and not args.create_albums:
            parser.error("--output, --tag-only, or --create-albums is required for immich source type")

    # Setup logging
    log_dir = Path(args.output) if args.output else None
    log_file = setup_logging(output_dir=log_dir, verbose=args.verbose)
    print(f"📝 Logging to: {log_file}\n")

    # Log command-line arguments
    logging.info("Command-line arguments:")
    for arg, value in vars(args).items():
        # Don't log sensitive information
        if 'api_key' in arg.lower():
            logging.info(f"  {arg}: ***REDACTED***")
        else:
            logging.info(f"  {arg}: {value}")

    # Create photo source
    if args.source_type == 'local':
        photo_source = LocalPhotoSource(args.source)
    else:  # immich
        photo_source = ImmichPhotoSource(
            url=args.immich_url,
            api_key=args.immich_api_key,
            cache_dir=args.immich_cache_dir,
            cache_size_mb=args.immich_cache_size,
            verify_ssl=not args.no_verify_ssl,
            use_thumbnails=not args.use_full_resolution
        )

    # Create organizer and run
    organizer = PhotoOrganizer(
        photo_source=photo_source,
        output_dir=args.output,
        similarity_threshold=args.threshold,
        time_window=args.time_window,
        use_time_window=(args.time_window > 0),
        tag_only=args.tag_only,
        create_albums=args.create_albums,
        album_prefix=args.album_prefix,
        mark_best_favorite=args.mark_best_favorite,
        resume=args.resume,
        state_file=args.state_file,
        limit=args.limit,
        enable_hdr=args.enable_hdr,
        hdr_gamma=args.hdr_gamma,
        enable_face_swap=args.enable_face_swap,
        swap_closed_eyes=args.swap_closed_eyes,
        face_backend=args.face_backend,
        threads=args.threads,
        verbose=args.verbose
    )

    organizer.organize_photos(album=args.immich_album if args.source_type == 'immich' else None)


if __name__ == "__main__":
    main()
