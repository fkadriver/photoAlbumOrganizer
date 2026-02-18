"""
Photo/Video grouping functions for similarity matching and hash computation.
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import imagehash

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from photo_sources import Photo, PhotoSource
from processing_state import ProcessingState

# Video processing imports (lazy loaded)
_video_processing = None


def _get_video_processing():
    """Lazy load video processing module."""
    global _video_processing
    if _video_processing is None:
        import video_processing as vp
        _video_processing = vp
    return _video_processing


def compute_hash(photo: Photo, photo_source: PhotoSource):
    """
    Compute perceptual hash for a photo (image).

    Args:
        photo: Photo object to hash
        photo_source: PhotoSource to get photo data from

    Returns:
        Perceptual hash or None if error
    """
    try:
        # Try to use cached file first if available
        if photo.cached_path and photo.cached_path.exists():
            try:
                with Image.open(photo.cached_path) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    return imagehash.dhash(img)
            except FileNotFoundError:
                # File was deleted between exists() check and open() - race condition
                # Fall through to re-download
                pass

        # Load from bytes (re-download if cache missing or deleted)
        data = photo_source.get_photo_data(photo)
        with Image.open(BytesIO(data)) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            return imagehash.dhash(img)
    except Exception as e:
        filename = photo.metadata.get('filename', photo.id)
        logging.warning(f"Skipped unhashable photo '{filename}': {e}")
        return None


def compute_video_hash(photo: Photo, photo_source: PhotoSource,
                       strategy: str = 'scene_change', max_frames: int = 10):
    """
    Compute video hash using key frame extraction.

    Args:
        photo: Photo object (video) to hash
        photo_source: PhotoSource to get video data from
        strategy: Key frame extraction strategy
        max_frames: Maximum frames to extract

    Returns:
        VideoHash object or None if error
    """
    vp = _get_video_processing()

    try:
        # Get video path (must be local file for OpenCV)
        video_path = None
        if photo.cached_path and photo.cached_path.exists():
            video_path = photo.cached_path
        elif photo.metadata.get('filepath'):
            video_path = Path(photo.metadata['filepath'])
        elif photo.metadata.get('local_path'):
            video_path = Path(photo.metadata['local_path'])

        if not video_path or not video_path.exists():
            # For remote videos, we'd need to download first
            # For now, skip remote videos without local cache
            filename = photo.metadata.get('filename', photo.id)
            logging.warning(f"Skipped video '{filename}': no local file available")
            return None

        # Map strategy string to enum
        strategy_map = {
            'scene_change': vp.KeyFrameStrategy.SCENE_CHANGE,
            'fixed_interval': vp.KeyFrameStrategy.FIXED_INTERVAL,
            'iframe': vp.KeyFrameStrategy.IFRAME,
        }
        strategy_enum = strategy_map.get(strategy, vp.KeyFrameStrategy.SCENE_CHANGE)

        # Compute video hash
        video_hash = vp.compute_video_hash(
            video_path,
            strategy=strategy_enum,
            max_frames=max_frames
        )

        return video_hash

    except Exception as e:
        filename = photo.metadata.get('filename', photo.id)
        logging.warning(f"Skipped unhashable video '{filename}': {e}")
        return None


def process_photo_hash(photo: Photo, photo_source: PhotoSource, state: ProcessingState,
                       extract_metadata_func, get_datetime_func,
                       media_type: str = 'image',
                       video_strategy: str = 'scene_change',
                       video_max_frames: int = 10):
    """
    Process a single photo/video's hash and metadata (for parallel processing).

    Args:
        photo: Photo object to process
        photo_source: PhotoSource to get photo data from
        state: ProcessingState for caching hashes
        extract_metadata_func: Function to extract metadata from photo
        get_datetime_func: Function to extract datetime from metadata
        media_type: 'image' or 'video'
        video_strategy: Key frame extraction strategy for videos
        video_max_frames: Maximum frames to extract for videos

    Returns:
        Dictionary with photo, hash, metadata, and datetime
    """
    if media_type == 'video':
        # Video processing
        # Note: Video hashes are more complex (VideoHash objects), not cached as hex strings
        hash_val = compute_video_hash(
            photo, photo_source,
            strategy=video_strategy,
            max_frames=video_max_frames
        )
        if hash_val is None:
            return None
    else:
        # Image processing
        # Check if we have cached hash
        cached_hash = state.get_cached_hash(photo.id)
        if cached_hash:
            hash_val = imagehash.hex_to_hash(cached_hash)
        else:
            hash_val = compute_hash(photo, photo_source)
            if hash_val is None:
                return None
            # Cache the computed hash
            state.mark_hash_computed(photo.id, hash_val)

    metadata = extract_metadata_func(photo)
    dt = get_datetime_func(metadata)

    return {
        'photo': photo,
        'hash': hash_val,
        'metadata': metadata,
        'datetime': dt
    }


def group_similar_photos(photos: List[Photo], photo_source: PhotoSource, state: ProcessingState,
                        extract_metadata_func, get_datetime_func,
                        similarity_threshold: int, use_time_window: bool, time_window: int,
                        min_group_size: int, threads: int, interrupted_flag,
                        media_type: str = 'image',
                        video_strategy: str = 'scene_change',
                        video_max_frames: int = 10):
    """
    Group photos/videos by perceptual similarity.

    Args:
        photos: List of Photo objects to group
        photo_source: PhotoSource to get photo data from
        state: ProcessingState for caching hashes
        extract_metadata_func: Function to extract metadata from photo
        get_datetime_func: Function to extract datetime from metadata
        similarity_threshold: Maximum hash difference for similarity
        use_time_window: Whether to use time window for grouping
        time_window: Time window in seconds
        min_group_size: Minimum number of photos to form a group
        threads: Number of threads for parallel processing
        interrupted_flag: Flag to check for interruption
        media_type: 'image' or 'video'
        video_strategy: Key frame extraction strategy for videos
        video_max_frames: Maximum frames to extract for videos

    Returns:
        List of groups (each group is a list of photo_data dictionaries)
    """
    media_label = "videos" if media_type == 'video' else "photos"
    logging.info(f"Computing hashes for {len(photos)} {media_label} using {threads} thread(s)...")

    # Compute hashes and metadata in parallel
    photo_data = []
    processed_count = 0

    with ThreadPoolExecutor(max_workers=threads) as executor:
        # Submit all photo processing tasks
        future_to_photo = {
            executor.submit(
                process_photo_hash, photo, photo_source, state,
                extract_metadata_func, get_datetime_func,
                media_type, video_strategy, video_max_frames
            ): photo
            for photo in photos
        }

        # Process completed tasks
        for future in as_completed(future_to_photo):
            if interrupted_flag():
                break

            processed_count += 1

            # Update progress bar
            percentage = (processed_count / len(photos)) * 100
            bar_length = 40
            filled = int(bar_length * processed_count / len(photos))
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f'\r[{bar}] {percentage:.1f}% ({processed_count}/{len(photos)})', end='', flush=True)

            # Log every 100 items
            if processed_count % 100 == 0:
                logging.info(f"Processing {processed_count}/{len(photos)} ({percentage:.1f}%)")

            try:
                result = future.result()
                if result is not None:
                    photo_data.append(result)
            except Exception as e:
                photo = future_to_photo[future]
                filename = photo.metadata.get('filename', photo.id)
                logging.warning(f"Error processing '{filename}': {e}")

    # Complete progress bar
    print()  # New line after progress bar

    skipped = processed_count - len(photo_data)
    if skipped > 0:
        print(f"\n  Skipped {skipped} unreadable {media_label}")
        logging.warning(f"Skipped {skipped} unreadable {media_label} during hashing")

    logging.info(f"Grouping {len(photo_data)} {media_label} by similarity...")

    # Group by similarity
    groups = []
    used = set()

    if media_type == 'video':
        # Video grouping uses video_hash_distance
        vp = _get_video_processing()
        for i, data1 in enumerate(photo_data):
            if i in used:
                continue

            group = [data1]
            used.add(i)

            for j, data2 in enumerate(photo_data[i+1:], start=i+1):
                if j in used:
                    continue

                # Check video hash similarity
                hash_diff = vp.video_hash_distance(data1['hash'], data2['hash'])

                if hash_diff <= similarity_threshold:
                    # Additional temporal check if enabled and both have datetime
                    if use_time_window and data1['datetime'] and data2['datetime']:
                        time_diff = abs((data1['datetime'] - data2['datetime']).total_seconds())
                        if time_diff <= time_window:
                            group.append(data2)
                            used.add(j)
                    elif not use_time_window:
                        group.append(data2)
                        used.add(j)
                    elif not data1['datetime'] or not data2['datetime']:
                        group.append(data2)
                        used.add(j)

            if len(group) >= min_group_size:
                groups.append(group)
    else:
        # Image grouping uses imagehash difference
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

                if hash_diff <= similarity_threshold:
                    # Additional temporal check if enabled and both have datetime
                    if use_time_window and data1['datetime'] and data2['datetime']:
                        time_diff = abs((data1['datetime'] - data2['datetime']).total_seconds())
                        # If within time window, consider it part of burst
                        if time_diff <= time_window:
                            group.append(data2)
                            used.add(j)
                    elif not use_time_window:
                        # If time window disabled, rely on hash alone
                        group.append(data2)
                        used.add(j)
                    elif not data1['datetime'] or not data2['datetime']:
                        # If no datetime available, rely on hash alone
                        group.append(data2)
                        used.add(j)

            if len(group) >= min_group_size:
                groups.append(group)

    logging.info(f"Found {len(groups)} groups of similar {media_label}")
    return groups
