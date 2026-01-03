import os
import shutil
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional
import json
import hashlib
import signal
import sys

# Image processing
from PIL import Image
from PIL.ExifTags import TAGS
import imagehash
import cv2
import numpy as np

# Photo source abstraction
from photo_sources import PhotoSource, LocalPhotoSource, ImmichPhotoSource, Photo

# Resume capability
from processing_state import ProcessingState

# Face detection - with workaround for Python 3.12 compatibility
FACE_DETECTION_ENABLED = True
try:
    # Fix for face_recognition_models import issue in Python 3.12
    import pkg_resources
    try:
        pkg_resources.require("face_recognition_models")
    except:
        pass
    
    import face_recognition
except Exception as e:
    print("Warning: Could not import face_recognition")
    print(f"  {e}")
    print("\nFace detection will be DISABLED.")
    print("Photos will be grouped, but best photo selection will be random.")
    print("\nTo enable face detection, use Python 3.11 or earlier:")
    print("  python3.11 -m venv venv && source venv/bin/activate")
    print("  pip install -r requirements.txt")
    print("\nContinuing without face detection...\n")
    FACE_DETECTION_ENABLED = False
    face_recognition = None

class PhotoOrganizer:
    def __init__(self, photo_source: PhotoSource, output_dir, similarity_threshold=5,
                 time_window=300, use_time_window=True, tag_only=False,
                 create_albums=False, album_prefix="Organized-", mark_best_favorite=False,
                 resume=False, state_file=None):
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
        return self.photo_source.list_photos(album=album)
    
    def compute_hash(self, photo: Photo):
        """Compute perceptual hash for a photo."""
        try:
            # Get photo data
            if photo.cached_path:
                # Use cached path if available
                with Image.open(photo.cached_path) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    return imagehash.dhash(img)
            else:
                # Load from bytes
                data = self.photo_source.get_photo_data(photo)
                from io import BytesIO
                with Image.open(BytesIO(data)) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    return imagehash.dhash(img)
        except Exception as e:
            print(f"Error hashing {photo.id}: {e}")
            return None
    
    def group_similar_photos(self, photos: List[Photo]):
        """Group photos by perceptual similarity."""
        print(f"Computing hashes for {len(photos)} photos...")

        # Compute hashes and metadata
        photo_data = []
        for i, photo in enumerate(photos):
            if self._interrupted:
                break

            if i % 100 == 0:
                print(f"Processing {i}/{len(photos)}...")

            # Check if we have cached hash
            cached_hash = self.state.get_cached_hash(photo.id)
            if cached_hash:
                hash_val = imagehash.hex_to_hash(cached_hash)
            else:
                hash_val = self.compute_hash(photo)
                if hash_val is None:
                    continue
                # Cache the computed hash
                self.state.mark_hash_computed(photo.id, hash_val)

            metadata = self.extract_metadata(photo)
            dt = self.get_datetime_from_metadata(metadata)

            photo_data.append({
                'photo': photo,
                'hash': hash_val,
                'metadata': metadata,
                'datetime': dt
            })

        print(f"Grouping {len(photo_data)} photos by similarity...")

        # Group by similarity
        groups = []
        used = set()

        for i, data1 in enumerate(photo_data):
            if i in used:
                continue

            group = [data1]
            used.add(i)

            for j, data2 in enumerate(photo_data[i+1:], start=i+1):
                if j in used:
                    continue

                # Check hash similarity
                hash_diff = data1['hash'] - data2['hash']

                if hash_diff <= self.similarity_threshold:
                    # Additional temporal check if enabled and both have datetime
                    if self.use_time_window and data1['datetime'] and data2['datetime']:
                        time_diff = abs((data1['datetime'] - data2['datetime']).total_seconds())
                        # If within time window, consider it part of burst
                        if time_diff <= self.time_window:
                            group.append(data2)
                            used.add(j)
                    elif not self.use_time_window:
                        # If time window disabled, rely on hash alone
                        group.append(data2)
                        used.add(j)
                    elif not data1['datetime'] or not data2['datetime']:
                        # If no datetime available, rely on hash alone
                        group.append(data2)
                        used.add(j)

            if len(group) > 1:  # Only create groups with multiple photos
                groups.append(group)

        print(f"Found {len(groups)} groups of similar photos")
        return groups
    
    def score_face_quality(self, photo: Photo):
        """
        Score faces in a photo for smile and open eyes.
        Returns list of face scores.
        """
        if not FACE_DETECTION_ENABLED:
            return []

        try:
            # Get image path (prefer cached)
            if photo.cached_path:
                image_path = str(photo.cached_path)
            else:
                # Download and cache
                data = self.photo_source.get_photo_data(photo)
                from io import BytesIO
                import tempfile
                # Save to temp file for face_recognition
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                    tmp.write(data)
                    image_path = tmp.name

            # Load image
            image = face_recognition.load_image_file(image_path)
            face_locations = face_recognition.face_locations(image)

            if not face_locations:
                return []

            # Use OpenCV for smile detection
            cv_image = cv2.imread(image_path)
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

            # Load cascade classifiers
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            smile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_smile.xml')
            eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')

            faces = face_cascade.detectMultiScale(gray, 1.3, 5)

            face_scores = []
            for (x, y, w, h) in faces:
                roi_gray = gray[y:y+h, x:x+w]

                # Detect smiles
                smiles = smile_cascade.detectMultiScale(roi_gray, 1.8, 20)
                smile_score = len(smiles)

                # Detect eyes
                eyes = eye_cascade.detectMultiScale(roi_gray, 1.1, 5)
                eye_score = min(len(eyes), 2)  # Max 2 eyes

                # Combined score
                total_score = smile_score + eye_score * 2  # Weight eyes more
                face_scores.append(total_score)

            # Clean up temp file if created
            if not photo.cached_path:
                import os
                try:
                    os.unlink(image_path)
                except:
                    pass

            return face_scores

        except Exception as e:
            print(f"Error scoring faces in {photo.id}: {e}")
            return []
    
    def find_best_photo(self, group):
        """Find the best photo in a group based on face quality."""
        best_photo = None
        best_score = -1

        for photo_data in group:
            scores = self.score_face_quality(photo_data['photo'])
            avg_score = sum(scores) / len(scores) if scores else 0

            if avg_score > best_score:
                best_score = avg_score
                best_photo = photo_data

        # If no faces found, return first photo
        return best_photo if best_photo else group[0]
    
    def swap_faces(self, base_image_path, source_images):
        """
        Create composite image with best faces from multiple images.
        This is a simplified version - production would need more sophisticated alignment.
        """
        try:
            base_img = cv2.imread(str(base_image_path))
            
            # For now, just return the best image
            # Full face swapping requires complex alignment and blending
            # which is beyond this initial implementation
            
            return base_img
            
        except Exception as e:
            print(f"Error swapping faces: {e}")
            return None
    
    def save_metadata(self, group, group_dir):
        """Save metadata for all photos in group to text file."""
        metadata_file = group_dir / 'metadata.txt'
        
        with open(metadata_file, 'w') as f:
            f.write(f"Photo Group - {len(group)} images\n")
            f.write("=" * 80 + "\n\n")
            
            for i, photo_data in enumerate(group, 1):
                f.write(f"Photo {i}: {photo_data['path'].name}\n")
                f.write("-" * 80 + "\n")
                
                metadata = photo_data['metadata']
                for key, value in metadata.items():
                    f.write(f"{key}: {value}\n")
                
                f.write("\n")
    
    def organize_photos(self, album: str = None):
        """Main method to organize photos into groups."""
        try:
            # Find all photos
            photos = self.find_all_photos(album=album)
            print(f"Found {len(photos)} photos")

            # Track discovered photos
            for photo in photos:
                self.state.mark_photo_discovered()

            # Group similar photos
            groups = self.group_similar_photos(photos)

            if not groups:
                print("No similar photo groups found.")
                self.state.cleanup()
                return

            # Record total groups found
            self.state.set_groups_found(len(groups))

            # Process each group
            for i, group in enumerate(groups, 1):
                if self._interrupted:
                    break

                # Skip already completed groups
                if self.state.is_group_completed(i):
                    print(f"\nSkipping group {i}/{len(groups)} (already completed)")
                    continue

                print(f"\nProcessing group {i}/{len(groups)} ({len(group)} photos)...")

                # Find best photo
                best_photo_data = self.find_best_photo(group)
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

                    print(f"Group {i} complete: {group_dir}")

                # Mark group as completed
                self.state.mark_group_completed(i)

            # If we completed all groups successfully, cleanup state file
            if not self._interrupted and self.state.state['groups_processed'] == len(groups):
                print("\nAll groups processed successfully!")
                self.state.cleanup()

            if self.output_dir and not self.tag_only:
                print(f"\nOrganization complete! Created {len(groups)} groups in {self.output_dir}")
            else:
                print(f"\nProcessed {len(groups)} groups")

        except Exception as e:
            # Save state on unexpected error
            print(f"\nError during processing: {e}")
            self.state.save()
            print(f"State saved to: {self.state_file}")
            print(f"Resume with: --resume --state-file {self.state_file}")
            raise


def main():
    """Main entry point with argument parsing."""
    import argparse

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
                        help='Time window in seconds for grouping (default=300)')
    parser.add_argument('--no-time-window', action='store_true',
                        help='Disable time window check, group by visual similarity only')

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
                        help='Resume from previous interrupted run')
    parser.add_argument('--state-file',
                        help='Path to state file for resume capability')

    # Other arguments
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose output')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without actually organizing')

    args = parser.parse_args()

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
        use_time_window=not args.no_time_window,
        tag_only=args.tag_only,
        create_albums=args.create_albums,
        album_prefix=args.album_prefix,
        mark_best_favorite=args.mark_best_favorite,
        resume=args.resume,
        state_file=args.state_file
    )

    organizer.organize_photos(album=args.immich_album if args.source_type == 'immich' else None)


if __name__ == "__main__":
    main()
