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

# Lightweight import only — heavy imports (cv2, face_recognition, etc.)
# are deferred to main() so that interactive mode can run without them.
from utils import setup_logging


class HintingArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that appends a tip about interactive mode on error."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"\n{self.prog}: error: {message}", file=sys.stderr)
        print("\nTip: Run with -i or --interactive for a guided setup menu.",
              file=sys.stderr)
        sys.exit(2)


def main():
    """Main entry point with argument parsing."""
    parser = HintingArgumentParser(
        description='Organize photo albums by grouping similar photos',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local photos
  ./photo_organizer.py -s ~/Photos -o ~/OrganizedPhotos
  ./photo_organizer.py -s ~/Photos -o ~/Organized -t 8 --verbose

  # Immich integration - tag duplicates
  ./photo_organizer.py --source-type immich \\
    --immich-url http://immich:2283 \\
    --immich-api-key YOUR_KEY \\
    --tag-only

  # Immich integration - create albums
  ./photo_organizer.py --source-type immich \\
    --immich-url http://immich:2283 \\
    --immich-api-key YOUR_KEY \\
    --create-albums \\
    --mark-best-favorite

  # Immich integration - download and organize
  ./photo_organizer.py --source-type immich \\
    --immich-url http://immich:2283 \\
    --immich-api-key YOUR_KEY \\
    -o ~/Organized

  # HDR merging for bracketed exposures
  ./photo_organizer.py -s ~/Photos -o ~/Organized \\
    --enable-hdr --hdr-gamma 2.2

  # Face swapping to fix closed eyes
  ./photo_organizer.py -s ~/Photos -o ~/Organized \\
    --enable-face-swap

  # Both HDR and face swapping
  ./photo_organizer.py -s ~/Photos -o ~/Organized \\
    --enable-hdr --enable-face-swap

  # Hybrid mode - local Immich library + API
  ./photo_organizer.py --source-type hybrid \\
    --immich-library-path /mnt/photos/immich-app/library \\
    --immich-url http://localhost:2283 \\
    --immich-api-key YOUR_KEY \\
    --tag-only

  # Hybrid mode with GPU acceleration
  ./photo_organizer.py --source-type hybrid \\
    --immich-library-path /mnt/photos/immich-app/library \\
    --immich-url http://localhost:2283 \\
    --immich-api-key YOUR_KEY \\
    --gpu --create-albums --mark-best-favorite

  # Process only videos (group similar video clips)
  ./photo_organizer.py --source-type immich \\
    --immich-url http://localhost:2283 \\
    --immich-api-key YOUR_KEY \\
    --media-type video \\
    --tag-only

  # Hybrid mode with videos
  ./photo_organizer.py --source-type hybrid \\
    --immich-library-path /mnt/photos/immich-app/library \\
    --immich-url http://localhost:2283 \\
    --immich-api-key YOUR_KEY \\
    --media-type video \\
    --video-strategy fixed_interval \\
    --create-albums
        """
    )

    # Source arguments
    parser.add_argument('--source-type', choices=['local', 'immich', 'hybrid'], default='local',
                        help='Photo source type: local, immich, or hybrid (default: local)')
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
    parser.add_argument('--immich-library-path',
                        default='/mnt/photos/immich-app/library',
                        help='Local path to Immich library for hybrid mode '
                             '(default: /mnt/photos/immich-app/library)')

    # Processing arguments
    parser.add_argument('--media-type', choices=['image', 'video'], default='image',
                        help='Media type to process: image (photos) or video (default: image)')
    parser.add_argument('-t', '--threshold', type=int, default=5, choices=range(0, 65),
                        metavar='N',
                        help='Similarity threshold (0-64, lower=stricter, default=5)')
    parser.add_argument('--time-window', type=int, default=300,
                        help='Time window in seconds for grouping (default=300, use 0 to disable time window)')
    parser.add_argument('--min-group-size', type=int, default=3,
                        help='Minimum photos per group (default: 3, min: 2)')
    parser.add_argument('--video-strategy', choices=['scene_change', 'fixed_interval', 'iframe'],
                        default='scene_change',
                        help='Video key frame extraction strategy (default: scene_change)')
    parser.add_argument('--video-max-frames', type=int, default=10,
                        help='Maximum key frames to extract per video (default: 10)')

    # Immich action arguments
    parser.add_argument('--tag-only', action='store_true',
                        help='Only tag photos as duplicates (Immich only)')
    parser.add_argument('--create-albums', action='store_true',
                        help='Create Immich albums for each group')
    parser.add_argument('--album-prefix', default='Organized-',
                        help='Prefix for created albums (default: Organized-)')
    parser.add_argument('--mark-best-favorite', action='store_true',
                        help='Mark best photo in each group as favorite (Immich only)')
    parser.add_argument('--immich-group-by-person', action='store_true',
                        help='Group photos by recognized person (Immich only)')
    parser.add_argument('--immich-person',
                        help='Filter to specific person name (Immich only)')
    parser.add_argument('--immich-use-server-faces', action='store_true',
                        help='Use Immich face data for best-photo selection')
    parser.add_argument('--archive-non-best', action='store_true',
                        help='Archive non-best photos in each group (Immich only)')
    parser.add_argument('--immich-use-duplicates', action='store_true',
                        help='Use Immich server-side duplicate detection for grouping')
    parser.add_argument('--immich-smart-search',
                        help='Pre-filter photos using CLIP semantic search query (Immich only)')

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
    parser.add_argument('--face-backend',
                        choices=['auto', 'face_recognition', 'mediapipe', 'facenet', 'insightface', 'yolov8'],
                        default='auto',
                        help='Face detection backend (default: auto). '
                             'GPU backends: facenet (CUDA/MPS), insightface (CUDA), yolov8 (CUDA/MPS)')
    parser.add_argument('--enable-face-swap', action='store_true',
                        help='Enable automatic face swapping to fix closed eyes/bad expressions')
    parser.add_argument('--swap-closed-eyes', action='store_true', default=True,
                        help='Swap faces with closed eyes (default: True, use --no-swap-closed-eyes to disable)')

    # GPU acceleration
    parser.add_argument('--gpu', action='store_true',
                        help='Enable GPU acceleration for face detection (auto-selects best GPU backend)')
    parser.add_argument('--gpu-device', type=int, default=0,
                        help='GPU device index for multi-GPU systems (default: 0)')
    parser.add_argument('--no-ml-quality', action='store_true',
                        help='Disable ML-based aesthetic quality scoring')

    # Daemon mode (Phase 3)
    parser.add_argument('--daemon', action='store_true',
                        help='Run as daemon, continuously monitoring for new photos')
    parser.add_argument('--poll-interval', type=int, default=60,
                        help='Daemon poll interval in seconds (default: 60)')
    parser.add_argument('--enable-bidir-sync', action='store_true',
                        help='Enable bi-directional sync with Immich')
    parser.add_argument('--conflict-strategy',
                        choices=['remote_wins', 'local_wins', 'manual'],
                        default='remote_wins',
                        help='Bi-directional sync conflict resolution (default: remote_wins)')
    parser.add_argument('--skip-local-hashing', action='store_true',
                        help='Use only Immich duplicate detection (skip local hashing)')

    # Other arguments
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose output')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without actually organizing')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit processing to first N photos (for testing, default: unlimited)')
    parser.add_argument('--threads', type=int, default=2,
                        help='Number of threads for parallel processing (default: 2)')

    # Cleanup mode
    parser.add_argument('--cleanup', action='store_true',
                        help='Launch Immich cleanup menu to undo organizer changes')

    # Web viewer
    parser.add_argument('--web-viewer', action='store_true',
                        help='Launch web viewer for processing report')
    parser.add_argument('--report',
                        help='Path to processing report JSON (default: reports/latest.json)')
    parser.add_argument('--report-dir', default='reports',
                        help='Directory for timestamped reports (default: reports)')
    parser.add_argument('--port', type=int, default=8080,
                        help='Web viewer port (default: 8080)')
    parser.add_argument('--live-viewer', action='store_true',
                        help='Start web viewer in background during processing')

    # Interactive mode
    parser.add_argument('-i', '--interactive', action='store_true',
                        help='Launch interactive setup menu')
    parser.add_argument('-r', '--run-settings', nargs='?',
                        const='.photo_organizer_settings.json', default=None,
                        metavar='FILE',
                        help='Run directly from a saved settings file '
                             '(default: .photo_organizer_settings.json)')

    args = parser.parse_args()

    # Handle --web-viewer early (no state file or validation needed)
    if args.web_viewer:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
        from web_viewer import start_viewer
        report_path = args.report
        if not report_path:
            # Try reports/latest.json first, fall back to processing_report.json
            if os.path.exists(os.path.join(args.report_dir, 'latest.json')):
                report_path = os.path.join(args.report_dir, 'latest.json')
            elif os.path.exists('processing_report.json'):
                report_path = 'processing_report.json'
            else:
                report_path = os.path.join(args.report_dir, 'latest.json')
        immich_client = None
        if args.immich_url and args.immich_api_key:
            from immich_client import ImmichClient
            immich_client = ImmichClient(
                url=args.immich_url,
                api_key=args.immich_api_key,
                verify_ssl=not args.no_verify_ssl,
            )
        start_viewer(report_path, port=args.port, immich_client=immich_client)
        sys.exit(0)

    # Handle --cleanup early (no state file or validation needed)
    if args.cleanup:
        if not args.immich_url or not args.immich_api_key:
            parser.error("--cleanup requires --immich-url and --immich-api-key (or use -i for interactive)")
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
        from immich_client import ImmichClient
        from cleanup import run_cleanup_menu
        client = ImmichClient(
            url=args.immich_url,
            api_key=args.immich_api_key,
            verify_ssl=not args.no_verify_ssl,
        )
        run_cleanup_menu(client, album_prefix=args.album_prefix)
        sys.exit(0)

    # Early interception: replace args with interactive menu selections
    if args.interactive:
        from interactive import run_interactive_menu
        args = run_interactive_menu()
    elif args.run_settings:
        from interactive import load_and_run_settings
        args = load_and_run_settings(args.run_settings)
        # -r is non-interactive: auto-start fresh instead of prompting
        args.force_fresh = True

    # Auto-detect existing state file and prompt for resume
    if not args.resume and not args.force_fresh:
        # Determine where the state file would be
        if args.state_file:
            potential_state_file = Path(args.state_file)
        elif args.output:
            potential_state_file = Path(args.output) / '.photo_organizer_state.json'
        else:
            potential_state_file = Path('.photo_organizer_state.json')

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
            potential_state_file = Path(args.output) / '.photo_organizer_state.json'
        else:
            potential_state_file = Path('.photo_organizer_state.json')

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

    if args.source_type == 'hybrid':
        if not args.immich_url:
            parser.error("--immich-url is required for hybrid source type")
        if not args.immich_api_key:
            parser.error("--immich-api-key is required for hybrid source type")
        if not args.immich_library_path:
            parser.error("--immich-library-path is required for hybrid source type")
        if not args.output and not args.tag_only and not args.create_albums:
            parser.error("--output, --tag-only, or --create-albums is required for hybrid source type")

    # Deferred imports — these pull in cv2, face_recognition, etc.
    # and require the Nix development environment for native libraries.
    try:
        from photo_sources import LocalPhotoSource, ImmichPhotoSource, HybridPhotoSource
        from organizer import PhotoOrganizer
    except ImportError as e:
        print(f"\nError: Failed to import required libraries: {e}\n")
        print("This usually means the development environment is not active.")
        print("Try one of:")
        print("  direnv allow        # if using direnv (recommended)")
        print("  nix develop         # enter Nix dev shell manually")
        print("  source venv/bin/activate  # if not on NixOS")
        sys.exit(1)

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
    elif args.source_type == 'hybrid':
        photo_source = HybridPhotoSource(
            library_path=args.immich_library_path,
            immich_url=args.immich_url,
            api_key=args.immich_api_key,
            verify_ssl=not args.no_verify_ssl,
        )
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
        min_group_size=args.min_group_size,
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
        gpu=getattr(args, 'gpu', False),
        gpu_device=getattr(args, 'gpu_device', 0),
        enable_ml_quality=not getattr(args, 'no_ml_quality', False),
        threads=args.threads,
        verbose=args.verbose,
        immich_group_by_person=getattr(args, 'immich_group_by_person', False),
        immich_person=getattr(args, 'immich_person', None),
        immich_use_server_faces=getattr(args, 'immich_use_server_faces', False),
        archive_non_best=getattr(args, 'archive_non_best', False),
        immich_use_duplicates=getattr(args, 'immich_use_duplicates', False),
        immich_smart_search=getattr(args, 'immich_smart_search', None),
        report_dir=getattr(args, 'report_dir', 'reports'),
        media_type=getattr(args, 'media_type', 'image'),
        video_strategy=getattr(args, 'video_strategy', 'scene_change'),
        video_max_frames=getattr(args, 'video_max_frames', 10),
    )

    # Start live viewer if requested
    if getattr(args, 'live_viewer', False):
        from web_viewer import start_viewer_background
        report_dir = getattr(args, 'report_dir', 'reports')
        report_path = os.path.join(report_dir, 'latest.json')
        # Write empty initial report so viewer can start
        organizer._write_report([])
        immich_client_for_viewer = None
        if args.source_type == 'immich':
            immich_client_for_viewer = photo_source.client
        viewer_port = getattr(args, 'port', 8080)
        start_viewer_background(report_path, port=viewer_port,
                                immich_client=immich_client_for_viewer,
                                report_dir=report_dir)
        print(f"\nLive viewer running at http://localhost:{viewer_port}")
        print(f"Report updates as processing progresses\n")

    # Daemon mode - continuous sync
    if getattr(args, 'daemon', False):
        if args.source_type == 'local':
            print("Error: Daemon mode requires --source-type immich or hybrid")
            sys.exit(1)

        from src.sync_daemon import run_daemon

        # Use sync state file
        state_file = Path(args.output or '.') / '.photo_organizer_sync_state.json'

        print("Starting sync daemon...")
        run_daemon(
            photo_source=photo_source,
            state_file=state_file,
            poll_interval=getattr(args, 'poll_interval', 60),
            enable_bidir_sync=getattr(args, 'enable_bidir_sync', False),
            conflict_strategy=getattr(args, 'conflict_strategy', 'remote_wins'),
            # Organizer config
            output_dir=args.output,
            threshold=args.threshold,
            time_window=args.time_window,
            use_time_window=(args.time_window > 0),
            min_group_size=args.min_group_size,
            media_type=getattr(args, 'media_type', 'image'),
            dry_run=args.dry_run,
        )
        return  # Daemon handles its own loop

    organizer.organize_photos(album=args.immich_album if args.source_type == 'immich' else None)

    # If live viewer is running, keep the process alive so the daemon thread persists
    if getattr(args, 'live_viewer', False):
        print(f"\nProcessing complete. Viewer still running at http://localhost:{viewer_port}")
        print("Press Ctrl+C to stop\n")
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nViewer stopped.")


if __name__ == "__main__":
    main()
