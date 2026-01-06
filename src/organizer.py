"""
Main photo organizer class that coordinates the photo organization process.
"""

import os
import sys
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
from image_processing import (
    find_best_photo, should_merge_hdr, merge_exposures_hdr,
    create_face_swapped_image, FACE_DETECTION_ENABLED
)


class PhotoOrganizer:
    """Main class for organizing photos by similarity."""

    def __init__(self, photo_source: PhotoSource, output_dir, similarity_threshold=5,
                 time_window=300, use_time_window=True, tag_only=False,
                 create_albums=False, album_prefix="Organized-", mark_best_favorite=False,
                 resume=False, state_file=None, limit=None,
                 enable_hdr=False, hdr_gamma=2.2,
                 enable_face_swap=False, swap_closed_eyes=True, threads=2, verbose=False):
        """
        Initialize the photo organizer.

        Args:
            photo_source: PhotoSource instance (LocalPhotoSource or ImmichPhotoSource)
            output_dir: Directory where organized groups will be created
            similarity_threshold: Hamming distance threshold for image similarity (lower = more similar)
            time_window: Time window in seconds for grouping photos (default: 300)
            use_time_window: Whether to use time window for grouping (default: True)
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
            threads: Number of threads for parallel processing (default: 2)
            verbose: Show verbose error output
        """
        self.photo_source = photo_source
        self.output_dir = Path(output_dir) if output_dir else None
        self.similarity_threshold = similarity_threshold
        self.time_window = time_window
        self.use_time_window = use_time_window
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

        # Resume capability
        self.resume = resume
        if state_file:
            self.state_file = Path(state_file)
        else:
            # Default state file in output directory or current directory
            if self.output_dir:
                self.state_file = self.output_dir / '.photo_organizer_state.pkl'
            else:
                self.state_file = Path('.photo_organizer_state.pkl')

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
        logging.info(f"  Tag only: {self.tag_only}")
        logging.info(f"  Create albums: {self.create_albums}")
        logging.info(f"  Album prefix: {self.album_prefix}")
        logging.info(f"  Mark best favorite: {self.mark_best_favorite}")
        logging.info(f"  Resume: {self.resume}")
        logging.info(f"  Limit: {self.limit}")
        logging.info(f"  HDR enabled: {self.enable_hdr}")
        logging.info(f"  Face swap enabled: {self.enable_face_swap}")
        logging.info(f"  Threads: {self.threads}")
        logging.info(f"  Verbose: {self.verbose}")

        # Setup signal handlers for graceful interruption
        self._interrupted = False
        self._setup_signal_handlers()

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
        """Find all photos from the photo source."""
        return self.photo_source.list_photos(album=album, limit=self.limit)

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
        """Main method to organize photos into groups."""
        try:
            logging.info("="*60)
            logging.info(f"Starting organize_photos (album={album})")
            logging.info("="*60)

            # Find all photos (limit is applied at source level for efficiency)
            photos = self.find_all_photos(album=album)

            if self.limit is not None and self.limit > 0:
                msg = f"🔬 TEST MODE: Processing {len(photos)} photos (limit: {self.limit})"
                print(msg)
                logging.info(msg)
            else:
                msg = f"Found {len(photos)} photos"
                print(msg)
                logging.info(msg)

            # Track discovered photos
            for photo in photos:
                self.state.mark_photo_discovered()

            # Group similar photos using the grouping module
            groups = group_similar_photos(
                photos, self.photo_source, self.state,
                self.extract_metadata, self.get_datetime_from_metadata,
                self.similarity_threshold, self.use_time_window, self.time_window,
                self.threads, self.verbose,
                lambda: self._interrupted
            )

            if not groups:
                msg = "No similar photo groups found."
                print(msg)
                logging.info(msg)
                self.state.cleanup()
                return

            # Record total groups found
            self.state.set_groups_found(len(groups))
            logging.info(f"Found {len(groups)} groups to process")

            # Process each group
            for i, group in enumerate(groups, 1):
                if self._interrupted:
                    break

                # Skip already completed groups
                if self.state.is_group_completed(i):
                    msg = f"\nSkipping group {i}/{len(groups)} (already completed)"
                    print(msg)
                    logging.info(msg)
                    continue

                msg = f"\nProcessing group {i}/{len(groups)} ({len(group)} photos)..."
                print(msg)
                logging.info(msg)

                # Find best photo using image_processing module
                best_photo_data = find_best_photo(group, self.photo_source)
                best_photo = best_photo_data['photo']

                # Tag-only mode (for Immich)
                if self.tag_only:
                    # Tag all photos in group as potential duplicates
                    tag = "photo-organizer-duplicate"
                    for photo_data in group:
                        self.photo_source.tag_photo(photo_data['photo'], [tag])
                    print(f"Tagged {len(group)} photos as potential duplicates")

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

                # Full organization mode (download and organize)
                if self.output_dir and not self.tag_only:
                    # Create group directory
                    group_dir = self.output_dir / f"group_{i:04d}"
                    group_dir.mkdir(exist_ok=True)

                    # Copy original photos
                    originals_dir = group_dir / 'originals'
                    originals_dir.mkdir(exist_ok=True)

                    for photo_data in group:
                        photo = photo_data['photo']

                        # Get photo data
                        if photo.cached_path:
                            src = photo.cached_path
                            dst = originals_dir / src.name
                        else:
                            # Download photo
                            data = self.photo_source.get_photo_data(photo)
                            filename = photo.metadata.get('filename', f"{photo.id}.jpg")
                            dst = originals_dir / filename

                        # Handle name collisions
                        counter = 1
                        original_dst = dst
                        while dst.exists():
                            dst = original_dst.parent / f"{original_dst.stem}_{counter}{original_dst.suffix}"
                            counter += 1

                        if photo.cached_path:
                            shutil.copy2(src, dst)
                        else:
                            dst.write_bytes(data)

                    # Save metadata
                    self.save_metadata(group, group_dir)

                    # Copy best photo
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

                    # HDR merging if enabled and appropriate
                    if should_merge_hdr(group, self.enable_hdr):
                        hdr_image = merge_exposures_hdr(group, self.photo_source, self.hdr_gamma)
                        if hdr_image is not None:
                            # Save HDR merged image
                            hdr_dst = group_dir / "hdr_merged.jpg"
                            cv2.imwrite(str(hdr_dst), hdr_image)
                            print(f"  HDR: Saved merged image: {hdr_dst.name}")

                    # Face swapping if enabled and face detection is available
                    if self.enable_face_swap and FACE_DETECTION_ENABLED:
                        face_swapped = create_face_swapped_image(group, best_dst, self.enable_face_swap)
                        if face_swapped is not None:
                            # Save face-swapped image
                            swap_dst = group_dir / "face_swapped.jpg"
                            cv2.imwrite(str(swap_dst), face_swapped)
                            print(f"  Face swap: Saved improved image: {swap_dst.name}")

                    print(f"Group {i} complete: {group_dir}")

                # Mark group as completed
                self.state.mark_group_completed(i)

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
