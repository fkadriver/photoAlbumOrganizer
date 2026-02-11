"""
Image processing functions for HDR merging, face detection, and face swapping.
"""

import os
import cv2
import numpy as np
import tempfile
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from photo_sources import Photo, PhotoSource
from utils import SuppressStderr
from face_backend import get_face_backend, FaceBackend

# Initialize face detection backend
_face_backend: Optional[FaceBackend] = get_face_backend("auto")
FACE_DETECTION_ENABLED = _face_backend is not None


def set_face_backend(backend_name: str):
    """Set the face detection backend. Call before using any face functions."""
    global _face_backend, FACE_DETECTION_ENABLED
    _face_backend = get_face_backend(backend_name)
    FACE_DETECTION_ENABLED = _face_backend is not None


def score_face_quality(photo: Photo, photo_source: PhotoSource):
    """
    Score faces in a photo for smile and open eyes.

    Args:
        photo: Photo object to analyze
        photo_source: PhotoSource to get photo data from

    Returns:
        List of face scores
    """
    if not FACE_DETECTION_ENABLED:
        return []

    try:
        # Get image path (prefer cached)
        if photo.cached_path:
            image_path = str(photo.cached_path)
        else:
            # Download and cache
            data = photo_source.get_photo_data(photo)
            # Save to temp file for face detection
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                tmp.write(data)
                image_path = tmp.name

        # Load image and detect faces
        image = _face_backend.load_image(image_path)
        face_locations = _face_backend.detect_faces(image)

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
            try:
                os.unlink(image_path)
            except:
                pass

        return face_scores

    except Exception as e:
        logging.error(f"Error scoring faces in {photo.id}: {e}")
        return []


def find_best_photo(group, photo_source: PhotoSource):
    """
    Find the best photo in a group based on face quality.

    Args:
        group: List of photo_data dictionaries
        photo_source: PhotoSource to get photo data from

    Returns:
        Best photo_data dictionary from the group
    """
    best_photo = None
    best_score = -1

    for photo_data in group:
        scores = score_face_quality(photo_data['photo'], photo_source)
        avg_score = sum(scores) / len(scores) if scores else 0

        if avg_score > best_score:
            best_score = avg_score
            best_photo = photo_data

    # If no faces found, return first photo
    return best_photo if best_photo else group[0]


def find_best_photo_immich_faces(group, photo_source):
    """
    Find the best photo using Immich server-side face bounding boxes.

    Scores photos by total face area (larger faces = clearer, closer shots).
    Falls back to find_best_photo() if no face data is available.

    Args:
        group: List of photo_data dictionaries
        photo_source: PhotoSource with get_asset_face_data() support

    Returns:
        Best photo_data dictionary from the group
    """
    best_photo = None
    best_score = -1
    any_faces = False

    for photo_data in group:
        faces = photo_source.get_asset_face_data(photo_data['photo'])
        if not faces:
            continue

        any_faces = True
        total_area = 0
        for face in faces:
            # Immich face data includes bounding box coordinates
            bbox = face.get('boundingBoxX1', 0), face.get('boundingBoxY1', 0), \
                   face.get('boundingBoxX2', 0), face.get('boundingBoxY2', 0)
            w = abs(bbox[2] - bbox[0])
            h = abs(bbox[3] - bbox[1])
            total_area += w * h

        if total_area > best_score:
            best_score = total_area
            best_photo = photo_data

    if any_faces and best_photo:
        return best_photo

    # Fall back to local face scoring
    return find_best_photo(group, photo_source)


def should_merge_hdr(group, enable_hdr: bool) -> bool:
    """
    Determine if group should be merged using HDR.

    Args:
        group: List of photo_data dictionaries
        enable_hdr: Whether HDR is enabled

    Returns:
        True if group is likely a bracketed exposure sequence
    """
    if not enable_hdr or len(group) < 2:
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


def merge_exposures_hdr(group, photo_source: PhotoSource, hdr_gamma: float = 1.0):
    """
    Merge multiple exposures using HDR technique.

    Args:
        group: List of photo_data dictionaries with bracketed exposures
        photo_source: PhotoSource to get photo data from
        hdr_gamma: Gamma value for tone mapping

    Returns:
        Merged HDR image (8-bit LDR), or None if merge fails
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
                data = photo_source.get_photo_data(photo)
                # Create temp file
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
            tonemap = cv2.createTonemapDrago(gamma=hdr_gamma)
            ldr = tonemap.process(hdr)

            # Convert to 8-bit
            ldr = np.clip(ldr * 255, 0, 255).astype('uint8')

        print(f"  HDR: Merge successful (gamma={hdr_gamma})")
        return ldr

    except Exception as e:
        print(f"  HDR: Merge failed: {e}")
        logging.error(f"HDR merge failed: {e}")
        return None


def calculate_eye_aspect_ratio(eye_landmarks):
    """
    Calculate eye aspect ratio (EAR) to determine if eye is open or closed.

    Args:
        eye_landmarks: List of (x, y) tuples for eye landmarks

    Returns:
        Eye aspect ratio (lower values indicate closed eyes, typically < 0.2)
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


def detect_closed_eyes(image_path):
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
        # Load image and get landmarks
        image = _face_backend.load_image(str(image_path))
        face_landmarks_list = _face_backend.get_landmarks(image)

        closed_eye_faces = []
        for i, face_lm in enumerate(face_landmarks_list):
            # Get eye landmarks
            left_eye = face_lm.left_eye
            right_eye = face_lm.right_eye

            if left_eye and right_eye:
                # Calculate eye aspect ratios
                left_ear = calculate_eye_aspect_ratio(left_eye)
                right_ear = calculate_eye_aspect_ratio(right_eye)

                # Average EAR for both eyes
                avg_ear = (left_ear + right_ear) / 2.0

                # Threshold for closed eyes (typically < 0.2)
                if avg_ear < 0.2:
                    closed_eye_faces.append(i)
                    print(f"    Face {i}: Closed eyes detected (EAR={avg_ear:.3f})")

        return closed_eye_faces

    except Exception as e:
        print(f"    Error detecting closed eyes: {e}")
        logging.error(f"Error detecting closed eyes: {e}")
        return []


def find_best_replacement_face(base_image_path, source_image_paths, face_index=0):
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

    if not _face_backend.supports_encoding:
        logging.info("Face encoding not supported by current backend; "
                     "face swap same-person matching unavailable.")
        return None, None

    try:
        # Load base image and get face encodings
        base_image = _face_backend.load_image(str(base_image_path))
        base_encodings = _face_backend.encode_faces(base_image)

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

            source_image = _face_backend.load_image(str(source_path))
            source_encodings = _face_backend.encode_faces(source_image)
            source_landmarks = _face_backend.get_landmarks(source_image)

            # Find matching face in source image
            for i, source_encoding in enumerate(source_encodings):
                # Check if this is the same person (face match)
                dist = _face_backend.face_distance(base_encoding, source_encoding)

                if dist < 0.6:  # Same person threshold
                    # Check if eyes are open
                    if i < len(source_landmarks):
                        face_lm = source_landmarks[i]
                        left_eye = face_lm.left_eye
                        right_eye = face_lm.right_eye

                        if left_eye and right_eye:
                            left_ear = calculate_eye_aspect_ratio(left_eye)
                            right_ear = calculate_eye_aspect_ratio(right_eye)
                            avg_ear = (left_ear + right_ear) / 2.0

                            # Score based on eye openness and face match quality
                            score = avg_ear * (1 - dist)

                            if score > best_score and avg_ear > 0.2:  # Eyes must be open
                                best_score = score
                                best_source = source_path
                                best_face_idx = i

        if best_source:
            print(f"    Found replacement face in {Path(best_source).name} (score={best_score:.3f})")

        return best_source, best_face_idx

    except Exception as e:
        print(f"    Error finding replacement face: {e}")
        logging.error(f"Error finding replacement face: {e}")
        return None, None


def swap_face(base_image_path, source_image_path, base_face_idx, source_face_idx,
              base_override=None):
    """
    Swap a face from source image into base image using seamless cloning.

    Args:
        base_image_path: Path to base image (used for face detection)
        source_image_path: Path to source image with replacement face
        base_face_idx: Face index in base image to replace
        source_face_idx: Face index in source image to use
        base_override: Optional BGR image to use as the clone target instead of
            loading from base_image_path. Face detection still uses the path so
            that face indices remain stable across multiple swaps.

    Returns:
        Image with swapped face, or None if swap fails
    """
    if not FACE_DETECTION_ENABLED:
        return None

    try:
        # Load images (backend returns RGB) for face detection
        base_image_rgb = _face_backend.load_image(str(base_image_path))
        source_image_rgb = _face_backend.load_image(str(source_image_path))

        # Use override as clone target if provided, otherwise load from path
        if base_override is not None:
            base_image = base_override
        else:
            base_image = cv2.cvtColor(base_image_rgb, cv2.COLOR_RGB2BGR)
        source_image = cv2.cvtColor(source_image_rgb, cv2.COLOR_RGB2BGR)

        # Get face locations
        base_locations = _face_backend.detect_faces(base_image_rgb)
        source_locations = _face_backend.detect_faces(source_image_rgb)

        if base_face_idx >= len(base_locations) or source_face_idx >= len(source_locations):
            return None

        # Get face landmarks for alignment
        base_landmarks = _face_backend.get_landmarks(base_image_rgb)[base_face_idx]
        source_landmarks = _face_backend.get_landmarks(source_image_rgb)[source_face_idx]

        # Extract face regions
        base_loc = base_locations[base_face_idx]
        base_top, base_right, base_bottom, base_left = (
            base_loc.top, base_loc.right, base_loc.bottom, base_loc.left
        )
        source_loc = source_locations[source_face_idx]
        source_top, source_right, source_bottom, source_left = (
            source_loc.top, source_loc.right, source_loc.bottom, source_loc.left
        )

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
        logging.error(f"Face swap failed: {e}")
        return None


def create_face_swapped_image(group, best_photo_path, enable_face_swap: bool):
    """
    Create a version of the best photo with closed eyes replaced.

    Args:
        group: List of photo_data dictionaries
        best_photo_path: Path to the best photo in the group
        enable_face_swap: Whether face swapping is enabled

    Returns:
        Face-swapped image or None if no swaps needed/possible
    """
    if not enable_face_swap or not FACE_DETECTION_ENABLED:
        return None

    try:
        # Detect closed eyes in best photo
        closed_eye_faces = detect_closed_eyes(best_photo_path)

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
            source_path, source_face_idx = find_best_replacement_face(
                best_photo_path, source_paths, face_idx
            )

            if source_path and source_face_idx is not None:
                # Swap the face, using accumulated result as the clone target
                # so previous swaps are preserved
                swapped = swap_face(
                    best_photo_path, source_path, face_idx, source_face_idx,
                    base_override=result
                )
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
        logging.error(f"Face swap failed: {e}")
        return None
