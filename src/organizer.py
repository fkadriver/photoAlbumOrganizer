"""
Main photo organizer class that coordinates the photo organization process.
"""

import os
import sys
import json
import shutil
import signal
import logging
import cv2
from pathlib import Path
from datetime import datetime
from typing import Optional

from photo_sources import PhotoSource, Photo
from processing_state import ProcessingState
from grouping import group_similar_photos
import image_processing
from image_processing import (
    find_best_photo, find_best_photo_immich_faces,
    should_merge_hdr, merge_exposures_hdr,
    create_face_swapped_image, set_face_backend
)


class PhotoOrganizer:
    """Main class for organizing photos by similarity."""

    def __init__(self, photo_source: PhotoSource, output_dir, similarity_threshold=5,
                 time_window=300, use_time_window=True, min_group_size=3,
                 tag_only=False,
                 create_albums=False, album_prefix="Organized-", mark_best_favorite=False,
                 resume=False, state_file=None, limit=None,
                 enable_hdr=False, hdr_gamma=2.2,
                 enable_face_swap=False, swap_closed_eyes=True,
                 face_backend='auto', gpu=False, gpu_device=0, enable_ml_quality=True,
                 threads=2, verbose=False,
                 immich_group_by_person=False, immich_person=None,
                 immich_use_server_faces=False,
                 archive_non_best=False,
                 immich_use_duplicates=False,
                 immich_smart_search=None,
                 report_dir="reports",
                 media_type='image', video_strategy='scene_change', video_max_frames=10):
        """
        Initialize the photo organizer.

        Args:
            photo_source: PhotoSource instance (LocalPhotoSource or ImmichPhotoSource)
            output_dir: Directory where organized groups will be created
            similarity_threshold: Hamming distance threshold for image similarity (lower = more similar)
            time_window: Time window in seconds for grouping photos (default: 300)
            use_time_window: Whether to use time window for grouping (default: True)
            min_group_size: Minimum photos per group (default: 3, min: 2)
            tag_only: Only tag photos, don't download/organize (Immich only)
            create_albums: Create albums for each group (Immich only)
            album_prefix: Prefix for created albums
            mark_best_favorite: Mark best photo as favorite (Immich only)
            resume: Resume from previous interrupted run
            state_file: Path to state file for resume capability
            limit: Maximum number of photos to process (for testing, default: None for unlimited)
            enable_hdr: Enable HDR merging for bracketed shots (default: False)
            hdr_gamma: HDR tone mapping gamma value (default: 2.2)
            enable_face_swap: Enable automatic face swapping to fix closed eyes/bad expressions (default: False)
            swap_closed_eyes: Swap faces with closed eyes when face swapping is enabled (default: True)
            face_backend: Face detection backend ('auto', 'face_recognition', 'mediapipe',
                         'facenet', 'insightface', 'yolov8')
            gpu: Enable GPU acceleration for GPU-capable backends (default: False)
            gpu_device: GPU device index for multi-GPU systems (default: 0)
            enable_ml_quality: Enable ML-based aesthetic quality scoring (default: True)
            threads: Number of threads for parallel processing (default: 2)
            verbose: Show verbose error output
            immich_group_by_person: Group photos by recognized person (Immich only)
            immich_person: Filter to specific person name (Immich only)
            immich_use_server_faces: Use Immich face data for best-photo selection
            archive_non_best: Archive non-best photos in Immich
            immich_use_duplicates: Use Immich server-side duplicate detection
            immich_smart_search: CLIP search query to pre-filter photos
            media_type: Type of media to process ('image' or 'video')
            video_strategy: Key frame extraction strategy ('scene_change', 'fixed_interval', 'iframe')
            video_max_frames: Maximum number of key frames to extract per video
        """
        self.photo_source = photo_source
        self.media_type = media_type
        self.video_strategy = video_strategy
        self.video_max_frames = video_max_frames
        self.output_dir = Path(output_dir) if output_dir else None
        self.similarity_threshold = similarity_threshold
        self.time_window = time_window
        self.use_time_window = use_time_window
        self.min_group_size = max(min_group_size, 2)
        self.tag_only = tag_only
        self.create_albums = create_albums
        self.album_prefix = album_prefix
        self.mark_best_favorite = mark_best_favorite
        self.limit = limit
        self.enable_hdr = enable_hdr
        self.hdr_gamma = hdr_gamma
        self.enable_face_swap = enable_face_swap
        self.swap_closed_eyes = swap_closed_eyes
        self.threads = threads
        self.verbose = verbose
        self.immich_group_by_person = immich_group_by_person
        self.immich_person = immich_person
        self.immich_use_server_faces = immich_use_server_faces
        self.archive_non_best = archive_non_best
        self.immich_use_duplicates = immich_use_duplicates
        self.immich_smart_search = immich_smart_search
        self.report_dir = Path(report_dir) if report_dir else Path("reports")

        # Processing report for web viewer
        self.report = {"groups": [], "metadata": {}}

        # Capture run settings for the report
        self.gpu = gpu
        self.gpu_device = gpu_device
        self.enable_ml_quality = enable_ml_quality
        self.ml_quality_scorer = None

        self.report["settings"] = {
            "source_type": photo_source.__class__.__name__,
            "similarity_threshold": similarity_threshold,
            "time_window": time_window,
            "use_time_window": use_time_window,
            "min_group_size": min_group_size,
            "tag_only": tag_only,
            "create_albums": create_albums,
            "album_prefix": album_prefix,
            "mark_best_favorite": mark_best_favorite,
            "limit": limit,
            "enable_hdr": enable_hdr,
            "enable_face_swap": enable_face_swap,
            "gpu": gpu,
            "gpu_device": gpu_device,
            "enable_ml_quality": enable_ml_quality,
            "face_backend": face_backend,
            "threads": threads,
            "immich_group_by_person": immich_group_by_person,
            "immich_person": immich_person,
            "immich_use_server_faces": immich_use_server_faces,
            "archive_non_best": archive_non_best,
            "immich_use_duplicates": immich_use_duplicates,
            "immich_smart_search": immich_smart_search,
            "media_type": media_type,
            "video_strategy": video_strategy,
            "video_max_frames": video_max_frames,
        }

        # Configure face detection backend with GPU support
        from face_backend import get_face_backend
        backend = get_face_backend(face_backend, gpu=gpu, gpu_device=gpu_device)
        if backend:
            set_face_backend(face_backend, gpu=gpu, gpu_device=gpu_device)

        # Initialize ML quality scorer if enabled
        if enable_ml_quality:
            self._init_ml_quality_scorer()

        # Resume capability
        self.resume = resume
        if state_file:
            self.state_file = Path(state_file)
        else:
            # Default state file in output directory or current directory
            if self.output_dir:
                self.state_file = self.output_dir / '.photo_organizer_state.json'
            else:
                self.state_file = Path('.photo_organizer_state.json')

        self.state = ProcessingState(self.state_file)

        # Load existing state if resuming
        if self.resume:
            if self.state.load():
                print("\n" + "="*60)
                print("RESUMING FROM PREVIOUS RUN")
                print("="*60)
                print(self.state.get_progress_summary())
                print("="*60 + "\n")

                # Verify compatibility
                source_type = photo_source.__class__.__name__
                source_path = getattr(photo_source, 'source_dir', None)
                if hasattr(source_path, '__str__'):
                    source_path = str(source_path)

                if not self.state.verify_compatibility(source_type, source_path, similarity_threshold):
                    print("Warning: Parameters have changed since last run!")
                    print("Starting fresh to avoid inconsistencies...")
                    self.state = ProcessingState(self.state_file)
                    self.resume = False
            else:
                print(f"No previous state found at {self.state_file}")
                print("Starting fresh...")
                self.resume = False
        else:
            # Initialize state for new run
            source_type = photo_source.__class__.__name__
            source_path = getattr(photo_source, 'source_dir', None)
            if hasattr(source_path, '__str__'):
                source_path = str(source_path)

            self.state.initialize(
                source_type=source_type,
                source_path=source_path,
                output_path=str(output_dir) if output_dir else None,
                threshold=similarity_threshold,
                time_window=time_window,
                use_time_window=use_time_window
            )

        if self.output_dir:
            self.output_dir.mkdir(exist_ok=True)

        # Log initialization parameters
        logging.info("PhotoOrganizer initialized with:")
        logging.info(f"  Source: {photo_source.__class__.__name__}")
        logging.info(f"  Output directory: {self.output_dir}")
        logging.info(f"  Similarity threshold: {self.similarity_threshold}")
        logging.info(f"  Time window: {self.time_window}s (enabled: {self.use_time_window})")
        logging.info(f"  Min group size: {self.min_group_size}")
        logging.info(f"  Tag only: {self.tag_only}")
        logging.info(f"  Create albums: {self.create_albums}")
        logging.info(f"  Album prefix: {self.album_prefix}")
        logging.info(f"  Mark best favorite: {self.mark_best_favorite}")
        logging.info(f"  Resume: {self.resume}")
        logging.info(f"  Limit: {self.limit}")
        logging.info(f"  HDR enabled: {self.enable_hdr}")
        logging.info(f"  Face swap enabled: {self.enable_face_swap}")
        logging.info(f"  GPU enabled: {self.gpu}")
        logging.info(f"  GPU device: {self.gpu_device}")
        logging.info(f"  ML quality scoring: {self.enable_ml_quality}")
        logging.info(f"  Threads: {self.threads}")
        logging.info(f"  Verbose: {self.verbose}")
        logging.info(f"  Group by person: {self.immich_group_by_person}")
        logging.info(f"  Person filter: {self.immich_person}")
        logging.info(f"  Use server faces: {self.immich_use_server_faces}")
        logging.info(f"  Archive non-best: {self.archive_non_best}")
        logging.info(f"  Use server duplicates: {self.immich_use_duplicates}")
        logging.info(f"  Smart search: {self.immich_smart_search}")
        logging.info(f"  Media type: {self.media_type}")
        if self.media_type == 'video':
            logging.info(f"  Video strategy: {self.video_strategy}")
            logging.info(f"  Video max frames: {self.video_max_frames}")

        # Setup signal handlers for graceful interruption
        self._interrupted = False
        self._setup_signal_handlers()

    def _init_ml_quality_scorer(self):
        """Initialize the ML quality scorer if available."""
        try:
            from backends.ml_quality_scorer import get_quality_scorer

            # Determine device for ML scorer
            if self.gpu:
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = f'cuda:{self.gpu_device}'
                    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                        device = 'mps'
                    else:
                        device = 'cpu'
                except ImportError:
                    device = 'cpu'
            else:
                device = 'cpu'

            self.ml_quality_scorer = get_quality_scorer(device=device)
            if self.ml_quality_scorer:
                logging.info(f"  ML quality scorer: {self.ml_quality_scorer.model_type} on {device}")
                print(f"ML quality scoring enabled ({self.ml_quality_scorer.model_type} on {device})")
            else:
                logging.info("  ML quality scorer: not available")
        except ImportError:
            logging.info("  ML quality scorer: not installed")
            self.ml_quality_scorer = None
        except Exception as e:
            logging.warning(f"  ML quality scorer initialization failed: {e}")
            self.ml_quality_scorer = None

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful interruption."""
        def signal_handler(signum, frame):
            print("\n\nInterrupt received! Saving state...")
            self._interrupted = True
            self.state.save()
            print(f"\nState saved to: {self.state_file}")
            print(f"Resume with: --resume --state-file {self.state_file}")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def extract_metadata(self, photo: Photo):
        """Extract metadata from a photo."""
        return self.photo_source.get_metadata(photo)

    def get_datetime_from_metadata(self, metadata):
        """Extract datetime from metadata, trying multiple sources."""
        # Try EXIF DateTime first
        for key in ['exif_DateTimeOriginal', 'exif_DateTime', 'exif_DateTimeDigitized']:
            if key in metadata:
                try:
                    return datetime.strptime(metadata[key], '%Y:%m:%d %H:%M:%S')
                except:
                    pass

        # Fall back to file modified time
        try:
            return datetime.fromisoformat(metadata['modified_time'])
        except:
            return None

    def find_all_photos(self, album: str = None):
        """Find all photos/videos from the photo source."""
        return self.photo_source.list_photos(album=album, limit=self.limit, media_type=self.media_type)

    def save_metadata(self, group, group_dir):
        """Save metadata for all photos in group to text file."""
        metadata_file = group_dir / 'metadata.txt'

        with open(metadata_file, 'w') as f:
            f.write(f"Photo Group - {len(group)} images\n")
            f.write("=" * 80 + "\n\n")

            for i, photo_data in enumerate(group, 1):
                # Get filename from metadata or photo object
                photo = photo_data['photo']
                metadata = photo_data['metadata']
                filename = metadata.get('filename', photo.id)

                f.write(f"Photo {i}: {filename}\n")
                f.write("-" * 80 + "\n")

                for key, value in metadata.items():
                    f.write(f"{key}: {value}\n")

                f.write("\n")

    def organize_photos(self, album: str = None):
        """Main method — dispatches to the appropriate strategy."""
        try:
            logging.info("="*60)
            logging.info(f"Starting organize_photos (album={album})")
            logging.info("="*60)

            if self.immich_use_duplicates:
                groups = self._organize_by_immich_duplicates(album)
            elif self.immich_group_by_person:
                groups = self._organize_by_person(album)
            else:
                groups = self._organize_by_hash(album)

            if not groups:
                msg = "No similar photo groups found."
                print(msg)
                logging.info(msg)
                self.state.cleanup()
                return

            # Record total groups found
            self.state.set_groups_found(len(groups))
            logging.info(f"Found {len(groups)} groups to process")

            self._process_groups(groups)

            logging.info("="*60)
            logging.info("Photo organization completed")
            logging.info("="*60)

        except Exception as e:
            # Save state on unexpected error
            error_msg = f"\nError during processing: {e}"
            print(error_msg)
            logging.error(error_msg, exc_info=True)
            self.state.save()
            state_msg = f"State saved to: {self.state_file}"
            print(state_msg)
            logging.info(state_msg)
            resume_msg = f"Resume with: --resume --state-file {self.state_file}"
            print(resume_msg)
            logging.info(resume_msg)
            raise

    def _organize_by_hash(self, album: str = None):
        """Group photos/videos by perceptual hash similarity (default strategy)."""
        photos = self.find_all_photos(album=album)

        # Apply CLIP smart search filter if specified (images only)
        if self.immich_smart_search and hasattr(self.photo_source, 'client') and self.media_type == 'image':
            print(f"Filtering with CLIP search: '{self.immich_smart_search}'")
            search_results = self.photo_source.client.smart_search(self.immich_smart_search, size=1000)
            search_ids = {a.id for a in search_results}
            photos = [p for p in photos if p.id in search_ids]
            print(f"  {len(photos)} photos match smart search query")

        media_label = "videos" if self.media_type == 'video' else "photos"
        if self.limit is not None and self.limit > 0:
            msg = f"🔬 TEST MODE: Processing {len(photos)} {media_label} (limit: {self.limit})"
        else:
            msg = f"Found {len(photos)} {media_label}"
        print(msg)
        logging.info(msg)

        for photo in photos:
            self.state.mark_photo_discovered()

        # Pre-fetch photos for Immich sources (images only, videos are too large)
        if hasattr(self.photo_source, 'prefetch_photos') and self.media_type == 'image':
            self.photo_source.prefetch_photos(photos, max_workers=self.threads)

        return group_similar_photos(
            photos, self.photo_source, self.state,
            self.extract_metadata, self.get_datetime_from_metadata,
            self.similarity_threshold, self.use_time_window, self.time_window,
            self.min_group_size, self.threads,
            lambda: self._interrupted,
            media_type=self.media_type,
            video_strategy=self.video_strategy,
            video_max_frames=self.video_max_frames
        )

    def _organize_by_person(self, album: str = None):
        """Group photos by recognized person, then by similarity within each person."""
        people = self.photo_source.list_people()
        if not people:
            print("No recognized people found in Immich.")
            return []

        # Filter to specific person if requested
        if self.immich_person:
            people = [p for p in people
                      if p.get('name', '').lower() == self.immich_person.lower()]
            if not people:
                print(f"Person '{self.immich_person}' not found.")
                return []

        # Filter to people with names (skip unnamed faces)
        named_people = [p for p in people if p.get('name')]
        print(f"Found {len(named_people)} named people (of {len(people)} total)")

        all_groups = []
        for person in named_people:
            if self._interrupted:
                break

            person_name = person.get('name', 'Unknown')
            person_id = person.get('id')
            if not person_id:
                continue

            photos = self.photo_source.list_photos_by_person(person_id, limit=self.limit)
            if len(photos) < self.min_group_size:
                continue

            print(f"\nProcessing person: {person_name} ({len(photos)} photos)")

            for photo in photos:
                self.state.mark_photo_discovered()

            groups = group_similar_photos(
                photos, self.photo_source, self.state,
                self.extract_metadata, self.get_datetime_from_metadata,
                self.similarity_threshold, self.use_time_window, self.time_window,
                self.min_group_size, self.threads,
                lambda: self._interrupted
            )

            if groups:
                # Tag groups with person name for context
                for group in groups:
                    for photo_data in group:
                        photo_data['person_name'] = person_name
                all_groups.extend(groups)
                print(f"  Found {len(groups)} group(s) for {person_name}")

        return all_groups

    def _organize_by_immich_duplicates(self, album: str = None):
        """Use Immich server-side duplicate detection as grouping source."""
        if not hasattr(self.photo_source, 'client'):
            print("Server-side duplicates require Immich source.")
            return []

        print("Fetching server-side duplicate groups from Immich...")
        dup_groups = self.photo_source.client.get_duplicates()

        if not dup_groups:
            print("No server-side duplicates found.")
            return []

        print(f"Found {len(dup_groups)} duplicate group(s) from Immich")

        # Convert Immich duplicate groups into our group format
        all_groups = []
        for dup in dup_groups:
            assets = dup.get('assets', [])
            if len(assets) < self.min_group_size:
                continue

            group = []
            for asset_data in assets:
                from immich_client import ImmichAsset
                asset = ImmichAsset(asset_data)
                if asset.type != 'IMAGE':
                    continue

                from photo_sources import Photo
                photo = Photo(
                    photo_id=asset.id,
                    source='immich',
                    metadata={
                        'asset_id': asset.id,
                        'filename': asset.original_file_name,
                        'file_created_at': asset.file_created_at,
                        'file_modified_at': asset.file_modified_at,
                        'is_favorite': asset.is_favorite,
                        'exif': asset.exif_info
                    }
                )
                self.state.mark_photo_discovered()

                metadata = self.extract_metadata(photo)
                dt = self.get_datetime_from_metadata(metadata)
                group.append({
                    'photo': photo,
                    'hash': None,
                    'metadata': metadata,
                    'datetime': dt
                })

            if len(group) >= self.min_group_size:
                all_groups.append(group)

        print(f"  {len(all_groups)} group(s) meet minimum size of {self.min_group_size}")
        return all_groups

    def _apply_structured_tags(self, group, best_photo, group_index, person_name=None):
        """Apply structured tags to a group using the Immich tag API."""
        if not hasattr(self.photo_source, 'client'):
            # Fall back to simple tagging for non-Immich sources
            tag = "photo-organizer-duplicate"
            for photo_data in group:
                self.photo_source.tag_photo(photo_data['photo'], [tag])
            print(f"  Tagged {len(group)} photos")
            return

        client = self.photo_source.client
        all_ids = [pd['photo'].metadata.get('asset_id', pd['photo'].id) for pd in group]
        best_id = best_photo.metadata.get('asset_id', best_photo.id)
        non_best_ids = [aid for aid in all_ids if aid != best_id]

        tags_applied = 0

        # Group tag
        group_tag_id = client.get_or_create_tag(f"photo-organizer/group-{group_index:04d}")
        if group_tag_id:
            if client.tag_assets_by_tag_id(group_tag_id, all_ids):
                tags_applied += 1

        # Best tag
        best_tag_id = client.get_or_create_tag("photo-organizer/best")
        if best_tag_id:
            client.tag_assets_by_tag_id(best_tag_id, [best_id])

        # Non-best tag
        if non_best_ids:
            non_best_tag_id = client.get_or_create_tag("photo-organizer/non-best")
            if non_best_tag_id:
                client.tag_assets_by_tag_id(non_best_tag_id, non_best_ids)

        # Person tag if available
        if person_name:
            person_tag_id = client.get_or_create_tag(f"photo-organizer/person-{person_name}")
            if person_tag_id:
                client.tag_assets_by_tag_id(person_tag_id, all_ids)

        print(f"  Tagged {len(group)} photos (best: {best_id[:8]}...)")

    def _write_report(self, groups):
        """Write processing report JSON to timestamped file in reports/ directory."""
        self.report["metadata"] = {
            "total_groups": len(groups),
            "total_photos": sum(len(g) for g in groups),
            "source_type": self.photo_source.__class__.__name__,
            "similarity_threshold": self.similarity_threshold,
            "time_window": self.time_window,
            "min_group_size": self.min_group_size,
            "generated_at": datetime.now().isoformat(),
        }
        if hasattr(self.photo_source, 'client'):
            self.report["metadata"]["immich_url"] = self.photo_source.client.url

        try:
            # Create reports directory
            self.report_dir.mkdir(parents=True, exist_ok=True)

            # Generate timestamped filename (reuse same timestamp for the run)
            if not hasattr(self, '_report_timestamp'):
                self._report_timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
            timestamped_path = self.report_dir / f"report_{self._report_timestamp}.json"

            # Write timestamped report
            with open(timestamped_path, "w") as f:
                json.dump(self.report, f, indent=2, default=str)

            # Update latest.json as a copy
            latest_path = self.report_dir / "latest.json"
            with open(latest_path, "w") as f:
                json.dump(self.report, f, indent=2, default=str)

            print(f"\nReport saved to: {timestamped_path}")
            logging.info(f"Processing report written to {timestamped_path}")
        except Exception as e:
            logging.warning(f"Failed to write processing report: {e}")

    def _process_groups(self, groups):
        """Process all groups: tag, create albums, download, HDR, face-swap."""
        for i, group in enumerate(groups, 1):
            if self._interrupted:
                break

            # Skip already completed groups
            if self.state.is_group_completed(i):
                msg = f"\nSkipping group {i}/{len(groups)} (already completed)"
                print(msg)
                logging.info(msg)
                continue

            person_label = ""
            if group[0].get('person_name'):
                person_label = f" [{group[0]['person_name']}]"

            msg = f"\nProcessing group {i}/{len(groups)} ({len(group)} photos){person_label}..."
            print(msg)
            logging.info(msg)

            # Find best photo
            if self.immich_use_server_faces:
                best_photo_data = find_best_photo_immich_faces(group, self.photo_source)
            else:
                best_photo_data = find_best_photo(group, self.photo_source)
            best_photo = best_photo_data['photo']

            # Structured tagging (for Immich with tag API)
            if self.tag_only or self.create_albums:
                self._apply_structured_tags(group, best_photo, i,
                                           group[0].get('person_name'))

            # Create albums mode (for Immich)
            if self.create_albums:
                album_name = f"{self.album_prefix}{i:04d}"
                photos_in_group = [pd['photo'] for pd in group]
                if self.photo_source.create_album(album_name, photos_in_group):
                    print(f"Created album: {album_name}")

            # Mark best as favorite (for Immich)
            if self.mark_best_favorite:
                if self.photo_source.set_favorite(best_photo, True):
                    print(f"Marked best photo as favorite: {best_photo.id}")

            # Archive non-best photos (for Immich)
            if self.archive_non_best:
                non_best = [pd['photo'] for pd in group if pd['photo'].id != best_photo.id]
                if non_best:
                    non_best_ids = [p.metadata.get('asset_id', p.id) for p in non_best]
                    # Try bulk update first, fall back to individual
                    if hasattr(self.photo_source, 'client') and \
                       hasattr(self.photo_source.client, 'bulk_update_assets'):
                        if self.photo_source.client.bulk_update_assets(non_best_ids, is_archived=True):
                            print(f"  Archived {len(non_best)} non-best photo(s)")
                        else:
                            # Fall back to individual
                            archived = sum(1 for p in non_best
                                           if self.photo_source.set_archived(p, True))
                            print(f"  Archived {archived}/{len(non_best)} non-best photo(s)")
                    else:
                        archived = sum(1 for p in non_best
                                       if self.photo_source.set_archived(p, True))
                        print(f"  Archived {archived}/{len(non_best)} non-best photo(s)")

            # Full organization mode (download and organize)
            if self.output_dir and not self.tag_only:
                group_dir = self.output_dir / f"group_{i:04d}"
                group_dir.mkdir(exist_ok=True)

                originals_dir = group_dir / 'originals'
                originals_dir.mkdir(exist_ok=True)

                for photo_data in group:
                    photo = photo_data['photo']

                    if photo.cached_path:
                        src = photo.cached_path
                        dst = originals_dir / src.name
                    else:
                        data = self.photo_source.get_photo_data(photo)
                        filename = photo.metadata.get('filename', f"{photo.id}.jpg")
                        dst = originals_dir / filename

                    counter = 1
                    original_dst = dst
                    while dst.exists():
                        dst = original_dst.parent / f"{original_dst.stem}_{counter}{original_dst.suffix}"
                        counter += 1

                    if photo.cached_path:
                        shutil.copy2(src, dst)
                    else:
                        dst.write_bytes(data)

                self.save_metadata(group, group_dir)

                best = best_photo_data['photo']
                if best.cached_path:
                    src = best.cached_path
                    filename = src.name
                else:
                    data = self.photo_source.get_photo_data(best)
                    filename = best.metadata.get('filename', f"{best.id}.jpg")

                best_dst = group_dir / f"best_{filename}"
                if best.cached_path:
                    shutil.copy2(src, best_dst)
                else:
                    best_dst.write_bytes(data)

                if should_merge_hdr(group, self.enable_hdr):
                    hdr_image = merge_exposures_hdr(group, self.photo_source, self.hdr_gamma)
                    if hdr_image is not None:
                        hdr_dst = group_dir / "hdr_merged.jpg"
                        cv2.imwrite(str(hdr_dst), hdr_image)
                        print(f"  HDR: Saved merged image: {hdr_dst.name}")

                if self.enable_face_swap and image_processing.FACE_DETECTION_ENABLED:
                    face_swapped = create_face_swapped_image(group, best_dst, self.enable_face_swap)
                    if face_swapped is not None:
                        swap_dst = group_dir / "face_swapped.jpg"
                        cv2.imwrite(str(swap_dst), face_swapped)
                        print(f"  Face swap: Saved improved image: {swap_dst.name}")

                print(f"Group {i} complete: {group_dir}")

            # Collect report data for this group
            actions_taken = []
            if self.tag_only or self.create_albums:
                actions_taken.append("tagged")
            if self.create_albums:
                actions_taken.append("album_created")
            if self.mark_best_favorite:
                actions_taken.append("best_favorited")
            if self.archive_non_best:
                actions_taken.append("non_best_archived")

            group_report = {
                "group_index": i,
                "photo_count": len(group),
                "person_name": group[0].get('person_name'),
                "best_photo": {
                    "id": best_photo.id,
                    "asset_id": best_photo.metadata.get('asset_id', best_photo.id),
                    "filename": best_photo.metadata.get('filename', best_photo.id),
                },
                "photos": [],
                "actions_taken": actions_taken,
            }
            for pd in group:
                p = pd['photo']
                photo_entry = {
                    "id": p.id,
                    "asset_id": p.metadata.get('asset_id', p.id),
                    "filename": p.metadata.get('filename', p.id),
                    "is_best": p.id == best_photo.id,
                    "hash": str(pd.get('hash')) if pd.get('hash') else None,
                }
                # Include all exif_* keys and select other metadata
                meta = pd.get('metadata', {})
                for key, value in meta.items():
                    if key.startswith('exif_') or key in ('dimensions', 'filesize',
                                                           'filepath', 'local_path'):
                        if value is not None and str(value) not in ('', 'None', '0'):
                            photo_entry[key] = str(value)
                group_report["photos"].append(photo_entry)

            self.report["groups"].append(group_report)

            # Write incremental report so live viewer can show progress
            self._write_report(groups)

            # Mark group as completed
            self.state.mark_group_completed(i)

        # Final report write (ensures complete metadata)
        self._write_report(groups)

        # If we completed all groups successfully, cleanup state file
        if not self._interrupted and self.state.state['groups_processed'] == len(groups):
            msg = "\nAll groups processed successfully!"
            print(msg)
            logging.info(msg)
            self.state.cleanup()

        if self.output_dir and not self.tag_only:
            msg = f"\nOrganization complete! Created {len(groups)} groups in {self.output_dir}"
            print(msg)
            logging.info(msg)
        else:
            msg = f"\nProcessed {len(groups)} groups"
            print(msg)
            logging.info(msg)
