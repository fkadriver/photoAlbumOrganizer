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
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import logging

# Suppress LAPACK/BLAS warnings from numpy/scipy/opencv
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

# Image processing
from PIL import Image
from PIL.ExifTags import TAGS
import imagehash
import cv2
import numpy as np

# Suppress numpy errors that show in stderr
np.seterr(all='ignore')

# Context manager to suppress stderr at OS level (for LAPACK/BLAS warnings)
class SuppressStderr:
    def __enter__(self):
        # Save the original stderr file descriptor
        self._original_stderr_fd = os.dup(2)
        # Open /dev/null
        self._devnull = os.open(os.devnull, os.O_WRONLY)
        # Redirect stderr (fd 2) to /dev/null
        os.dup2(self._devnull, 2)
        # Also redirect Python's sys.stderr
        self._original_stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore stderr file descriptor
        os.dup2(self._original_stderr_fd, 2)
        os.close(self._original_stderr_fd)
        os.close(self._devnull)
        # Restore Python's sys.stderr
        sys.stderr.close()
        sys.stderr = self._original_stderr

# Photo source abstraction
from photo_sources import PhotoSource, LocalPhotoSource, ImmichPhotoSource, Photo

# Resume capability
from processing_state import ProcessingState

# Face detection - with workaround for Python 3.12 compatibility
FACE_DETECTION_ENABLED = True
try:
    # Fix for face_recognition_models import issue in Python 3.12
    # Suppress warnings during import
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=DeprecationWarning)
        import pkg_resources
        try:
            pkg_resources.require("face_recognition_models")
        except:
            pass

    # Import face_recognition with suppressed stderr
    with SuppressStderr():
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

def setup_logging(output_dir=None, verbose=False):
    """
    Setup logging to both file and console.

    Args:
        output_dir: Directory for log file (default: ~/.cache/photo-organizer/logs)
        verbose: Enable verbose debug logging
    """
    # Determine log directory
    if output_dir:
        log_dir = Path(output_dir)
    else:
        log_dir = Path.home() / '.cache' / 'photo-organizer' / 'logs'

    log_dir.mkdir(parents=True, exist_ok=True)

    # Create log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'photo_organizer_{timestamp}.log'

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler - always detailed
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler - only warnings and errors by default
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Log startup
    logging.info("="*60)
    logging.info("Photo Organizer Started")
    logging.info(f"Log file: {log_file}")
    logging.info("="*60)

    return log_file

class PhotoOrganizer:
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
            error_msg = f"Error hashing {photo.id}: {e}"
            if self.verbose:
                print(error_msg)
            logging.error(error_msg)
            return None
    
    def _process_photo_hash(self, photo: Photo):
        """Process a single photo's hash and metadata (for parallel processing)."""
        # Check if we have cached hash
        cached_hash = self.state.get_cached_hash(photo.id)
        if cached_hash:
            hash_val = imagehash.hex_to_hash(cached_hash)
        else:
            hash_val = self.compute_hash(photo)
            if hash_val is None:
                return None
            # Cache the computed hash
            self.state.mark_hash_computed(photo.id, hash_val)

        metadata = self.extract_metadata(photo)
        dt = self.get_datetime_from_metadata(metadata)

        return {
            'photo': photo,
            'hash': hash_val,
            'metadata': metadata,
            'datetime': dt
        }

    def group_similar_photos(self, photos: List[Photo]):
        """Group photos by perceptual similarity."""
        msg = f"Computing hashes for {len(photos)} photos using {self.threads} thread(s)..."
        print(msg)
        logging.info(msg)

        # Compute hashes and metadata in parallel
        photo_data = []
        processed_count = 0

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            # Submit all photo processing tasks
            future_to_photo = {executor.submit(self._process_photo_hash, photo): photo for photo in photos}

            # Process completed tasks
            for future in as_completed(future_to_photo):
                if self._interrupted:
                    break

                processed_count += 1

                # Update progress bar
                percentage = (processed_count / len(photos)) * 100
                bar_length = 40
                filled = int(bar_length * processed_count / len(photos))
                bar = '█' * filled + '░' * (bar_length - filled)
                print(f'\r[{bar}] {percentage:.1f}% ({processed_count}/{len(photos)})', end='', flush=True)

                # Log every 100 photos
                if processed_count % 100 == 0:
                    logging.info(f"Processing {processed_count}/{len(photos)} ({percentage:.1f}%)")

                try:
                    result = future.result()
                    if result is not None:
                        photo_data.append(result)
                except Exception as e:
                    photo = future_to_photo[future]
                    error_msg = f"Error processing photo {photo.id}: {e}"
                    if self.verbose:
                        print(f'\n{error_msg}')  # New line to not interfere with progress bar
                    logging.error(error_msg)

        # Complete progress bar
        print()  # New line after progress bar

        grouping_msg = f"Grouping {len(photo_data)} photos by similarity..."
        print(grouping_msg)
        logging.info(grouping_msg)

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

            # Load image (suppress LAPACK warnings)
            with SuppressStderr():
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

    def should_merge_hdr(self, group) -> bool:
        """
        Determine if group should be merged using HDR.
        True if photos are taken in quick succession with different exposures.

        Args:
            group: List of photo_data dictionaries

        Returns:
            bool: True if group is likely a bracketed exposure sequence
        """
        if not self.enable_hdr or len(group) < 2:
            return False

        # Check if photos have different exposure values
        exposures = []
        for photo_data in group:
            metadata = photo_data.get('metadata', {})

            # Try to get exposure time from EXIF
            exposure = metadata.get('exif_ExposureTime')
            if not exposure:
                # Try alternate formats
                exposure = metadata.get('exif_exposure_time')

            if exposure:
                try:
                    # Convert fractional exposure (e.g., "1/250") to float
                    if isinstance(exposure, str) and '/' in exposure:
                        num, denom = exposure.split('/')
                        exposures.append(float(num) / float(denom))
                    else:
                        exposures.append(float(exposure))
                except (ValueError, ZeroDivisionError):
                    pass

        # If we have at least 2 different exposures, likely a bracket
        if len(exposures) >= 2 and len(set(exposures)) > 1:
            print(f"  HDR: Detected bracketed exposures: {exposures}")
            return True

        return False

    def merge_exposures_hdr(self, group):
        """
        Merge multiple exposures using HDR technique.
        Useful when group contains bracketed shots.

        Args:
            group: List of photo_data dictionaries with bracketed exposures

        Returns:
            numpy.ndarray: Merged HDR image (8-bit LDR), or None if merge fails
        """
        if len(group) < 2:
            return None

        try:
            # Load images
            images = []
            for photo_data in group:
                photo = photo_data['photo']

                # Get image path
                if photo.cached_path:
                    img_path = photo.cached_path
                else:
                    # Download temporarily if not cached
                    data = self.photo_source.get_photo_data(photo)
                    # Create temp file
                    import tempfile
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                    temp_file.write(data)
                    temp_file.close()
                    img_path = Path(temp_file.name)

                # Load image
                img = cv2.imread(str(img_path))
                if img is None:
                    print(f"  HDR: Warning - Could not load image: {img_path}")
                    continue

                images.append(img)

            if len(images) < 2:
                print(f"  HDR: Not enough valid images to merge ({len(images)} loaded)")
                return None

            print(f"  HDR: Merging {len(images)} exposures...")

            # Create exposure times array (use equal weighting if actual times unavailable)
            times = np.array([1.0] * len(images), dtype=np.float32)

            # Estimate camera response function (suppress LAPACK warnings)
            with SuppressStderr():
                calibrate = cv2.createCalibrateDebevec()
                response = calibrate.process(images, times)

                # Merge exposures to HDR
                merge = cv2.createMergeDebevec()
                hdr = merge.process(images, times, response)

                # Tone mapping using Drago algorithm
                tonemap = cv2.createTonemapDrago(gamma=self.hdr_gamma)
                ldr = tonemap.process(hdr)

                # Convert to 8-bit
                ldr = np.clip(ldr * 255, 0, 255).astype('uint8')

            print(f"  HDR: Merge successful (gamma={self.hdr_gamma})")
            return ldr

        except Exception as e:
            print(f"  HDR: Merge failed: {e}")
            return None

    def calculate_eye_aspect_ratio(self, eye_landmarks):
        """
        Calculate eye aspect ratio (EAR) to determine if eye is open or closed.
        EAR is based on the ratio of eye height to eye width.

        Args:
            eye_landmarks: List of (x, y) tuples for eye landmarks

        Returns:
            float: Eye aspect ratio (lower values indicate closed eyes, typically < 0.2)
        """
        if len(eye_landmarks) < 6:
            return 1.0  # Assume open if not enough landmarks

        # Calculate euclidean distances
        def distance(p1, p2):
            return np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

        # Vertical eye distances
        v1 = distance(eye_landmarks[1], eye_landmarks[5])
        v2 = distance(eye_landmarks[2], eye_landmarks[4])

        # Horizontal eye distance
        h = distance(eye_landmarks[0], eye_landmarks[3])

        # Eye aspect ratio
        ear = (v1 + v2) / (2.0 * h) if h > 0 else 1.0
        return ear

    def detect_closed_eyes(self, image_path):
        """
        Detect faces with closed eyes in an image.

        Args:
            image_path: Path to image file

        Returns:
            List of face indices with closed eyes, or empty list if face detection disabled
        """
        if not FACE_DETECTION_ENABLED:
            return []

        try:
            # Load image (suppress LAPACK warnings)
            with SuppressStderr():
                image = face_recognition.load_image_file(str(image_path))

                # Get face landmarks
                face_landmarks_list = face_recognition.face_landmarks(image)

            closed_eye_faces = []
            for i, face_landmarks in enumerate(face_landmarks_list):
                # Get eye landmarks
                left_eye = face_landmarks.get('left_eye', [])
                right_eye = face_landmarks.get('right_eye', [])

                if left_eye and right_eye:
                    # Calculate eye aspect ratios
                    left_ear = self.calculate_eye_aspect_ratio(left_eye)
                    right_ear = self.calculate_eye_aspect_ratio(right_eye)

                    # Average EAR for both eyes
                    avg_ear = (left_ear + right_ear) / 2.0

                    # Threshold for closed eyes (typically < 0.2)
                    if avg_ear < 0.2:
                        closed_eye_faces.append(i)
                        print(f"    Face {i}: Closed eyes detected (EAR={avg_ear:.3f})")

            return closed_eye_faces

        except Exception as e:
            print(f"    Error detecting closed eyes: {e}")
            return []

    def find_best_replacement_face(self, base_image_path, source_image_paths, face_index=0):
        """
        Find the best replacement face from source images for a face with closed eyes.

        Args:
            base_image_path: Path to image with closed eyes
            source_image_paths: List of paths to images with potential replacements
            face_index: Index of face to replace in base image

        Returns:
            Tuple of (best_source_path, best_source_face_index) or (None, None) if no good replacement found
        """
        if not FACE_DETECTION_ENABLED:
            return None, None

        try:
            # Load base image and get face encodings (suppress LAPACK warnings)
            with SuppressStderr():
                base_image = face_recognition.load_image_file(str(base_image_path))
                base_encodings = face_recognition.face_encodings(base_image)

            if face_index >= len(base_encodings):
                return None, None

            base_encoding = base_encodings[face_index]

            best_source = None
            best_face_idx = None
            best_score = -1

            # Search through source images
            for source_path in source_image_paths:
                if source_path == base_image_path:
                    continue  # Skip same image

                with SuppressStderr():
                    source_image = face_recognition.load_image_file(str(source_path))
                    source_encodings = face_recognition.face_encodings(source_image)
                    source_landmarks = face_recognition.face_landmarks(source_image)

                # Find matching face in source image
                for i, source_encoding in enumerate(source_encodings):
                    # Check if this is the same person (face match)
                    with SuppressStderr():
                        face_distance = face_recognition.face_distance([base_encoding], source_encoding)[0]

                    if face_distance < 0.6:  # Same person threshold
                        # Check if eyes are open
                        if i < len(source_landmarks):
                            landmarks = source_landmarks[i]
                            left_eye = landmarks.get('left_eye', [])
                            right_eye = landmarks.get('right_eye', [])

                            if left_eye and right_eye:
                                left_ear = self.calculate_eye_aspect_ratio(left_eye)
                                right_ear = self.calculate_eye_aspect_ratio(right_eye)
                                avg_ear = (left_ear + right_ear) / 2.0

                                # Score based on eye openness and face match quality
                                score = avg_ear * (1 - face_distance)

                                if score > best_score and avg_ear > 0.2:  # Eyes must be open
                                    best_score = score
                                    best_source = source_path
                                    best_face_idx = i

            if best_source:
                print(f"    Found replacement face in {Path(best_source).name} (score={best_score:.3f})")

            return best_source, best_face_idx

        except Exception as e:
            print(f"    Error finding replacement face: {e}")
            return None, None

    def swap_face(self, base_image_path, source_image_path, base_face_idx, source_face_idx):
        """
        Swap a face from source image into base image using seamless cloning.

        Args:
            base_image_path: Path to base image
            source_image_path: Path to source image with replacement face
            base_face_idx: Face index in base image to replace
            source_face_idx: Face index in source image to use

        Returns:
            numpy.ndarray: Image with swapped face, or None if swap fails
        """
        if not FACE_DETECTION_ENABLED:
            return None

        try:
            # Load images (suppress LAPACK warnings)
            with SuppressStderr():
                base_image_rgb = face_recognition.load_image_file(str(base_image_path))
                source_image_rgb = face_recognition.load_image_file(str(source_image_path))

            # Convert to BGR for OpenCV
            base_image = cv2.cvtColor(base_image_rgb, cv2.COLOR_RGB2BGR)
            source_image = cv2.cvtColor(source_image_rgb, cv2.COLOR_RGB2BGR)

            # Get face locations (suppress LAPACK warnings)
            with SuppressStderr():
                base_locations = face_recognition.face_locations(base_image_rgb)
                source_locations = face_recognition.face_locations(source_image_rgb)

            if base_face_idx >= len(base_locations) or source_face_idx >= len(source_locations):
                return None

            # Get face landmarks for alignment (suppress LAPACK warnings)
            with SuppressStderr():
                base_landmarks = face_recognition.face_landmarks(base_image_rgb)[base_face_idx]
                source_landmarks = face_recognition.face_landmarks(source_image_rgb)[source_face_idx]

            # Extract face regions
            base_top, base_right, base_bottom, base_left = base_locations[base_face_idx]
            source_top, source_right, source_bottom, source_left = source_locations[source_face_idx]

            # Expand face region slightly for better blending
            margin = 20
            source_top = max(0, source_top - margin)
            source_bottom = min(source_image.shape[0], source_bottom + margin)
            source_left = max(0, source_left - margin)
            source_right = min(source_image.shape[1], source_right + margin)

            # Extract and resize source face to match base face size
            source_face = source_image[source_top:source_bottom, source_left:source_right]
            target_height = base_bottom - base_top + 2 * margin
            target_width = base_right - base_left + 2 * margin

            source_face_resized = cv2.resize(source_face, (target_width, target_height))

            # Create mask for seamless cloning
            mask = np.full(source_face_resized.shape[:2], 255, dtype=np.uint8)

            # Calculate center point for seamless clone
            center_x = (base_left + base_right) // 2
            center_y = (base_top + base_bottom) // 2

            # Seamless clone the face
            result = cv2.seamlessClone(
                source_face_resized,
                base_image,
                mask,
                (center_x, center_y),
                cv2.NORMAL_CLONE
            )

            print(f"    Face swap successful")
            return result

        except Exception as e:
            print(f"    Face swap failed: {e}")
            return None

    def create_face_swapped_image(self, group, best_photo_path):
        """
        Create a version of the best photo with closed eyes replaced.

        Args:
            group: List of photo_data dictionaries
            best_photo_path: Path to the best photo in the group

        Returns:
            numpy.ndarray: Face-swapped image or None if no swaps needed/possible
        """
        if not self.enable_face_swap or not FACE_DETECTION_ENABLED:
            return None

        try:
            # Detect closed eyes in best photo
            closed_eye_faces = self.detect_closed_eyes(best_photo_path)

            if not closed_eye_faces:
                print(f"  Face swap: No closed eyes detected")
                return None

            print(f"  Face swap: Found {len(closed_eye_faces)} face(s) with closed eyes")

            # Get paths of other photos in group
            source_paths = []
            for photo_data in group:
                photo = photo_data['photo']
                if photo.cached_path and photo.cached_path != best_photo_path:
                    source_paths.append(photo.cached_path)

            if not source_paths:
                print(f"  Face swap: No alternative photos available")
                return None

            # Start with the best photo
            result = cv2.imread(str(best_photo_path))

            # Swap each closed-eye face
            swaps_made = 0
            for face_idx in closed_eye_faces:
                # Find best replacement
                source_path, source_face_idx = self.find_best_replacement_face(
                    best_photo_path, source_paths, face_idx
                )

                if source_path and source_face_idx is not None:
                    # Swap the face
                    swapped = self.swap_face(best_photo_path, source_path, face_idx, source_face_idx)
                    if swapped is not None:
                        result = swapped
                        swaps_made += 1

            if swaps_made > 0:
                print(f"  Face swap: Successfully swapped {swaps_made} face(s)")
                return result
            else:
                print(f"  Face swap: No suitable replacements found")
                return None

        except Exception as e:
            print(f"  Face swap: Failed - {e}")
            return None

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

            # Group similar photos
            groups = self.group_similar_photos(photos)

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

                    # HDR merging if enabled and appropriate
                    if self.should_merge_hdr(group):
                        hdr_image = self.merge_exposures_hdr(group)
                        if hdr_image is not None:
                            # Save HDR merged image
                            hdr_dst = group_dir / "hdr_merged.jpg"
                            cv2.imwrite(str(hdr_dst), hdr_image)
                            print(f"  HDR: Saved merged image: {hdr_dst.name}")

                    # Face swapping if enabled and face detection is available
                    if self.enable_face_swap and FACE_DETECTION_ENABLED:
                        face_swapped = self.create_face_swapped_image(group, best_dst)
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
        threads=args.threads,
        verbose=args.verbose
    )

    organizer.organize_photos(album=args.immich_album if args.source_type == 'immich' else None)


if __name__ == "__main__":
    main()
