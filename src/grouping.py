"""
Photo grouping functions for similarity matching and hash computation.
"""

import logging
from io import BytesIO
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import imagehash

from photo_sources import Photo, PhotoSource
from processing_state import ProcessingState


def compute_hash(photo: Photo, photo_source: PhotoSource):
    """
    Compute perceptual hash for a photo.

    Args:
        photo: Photo object to hash
        photo_source: PhotoSource to get photo data from

    Returns:
        Perceptual hash or None if error
    """
    try:
        # Get photo data
        if photo.cached_path and photo.cached_path.exists():
            # Use cached path if available and file exists
            with Image.open(photo.cached_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                return imagehash.dhash(img)
        else:
            # Load from bytes (re-download if cache missing)
            data = photo_source.get_photo_data(photo)
            with Image.open(BytesIO(data)) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                return imagehash.dhash(img)
    except Exception as e:
        logging.error(f"Error hashing {photo.id}: {e}")
        return None


def process_photo_hash(photo: Photo, photo_source: PhotoSource, state: ProcessingState,
                       extract_metadata_func, get_datetime_func):
    """
    Process a single photo's hash and metadata (for parallel processing).

    Args:
        photo: Photo object to process
        photo_source: PhotoSource to get photo data from
        state: ProcessingState for caching hashes
        extract_metadata_func: Function to extract metadata from photo
        get_datetime_func: Function to extract datetime from metadata

    Returns:
        Dictionary with photo, hash, metadata, and datetime
    """
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
                        min_group_size: int, threads: int, interrupted_flag):
    """
    Group photos by perceptual similarity.

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

    Returns:
        List of groups (each group is a list of photo_data dictionaries)
    """
    logging.info(f"Computing hashes for {len(photos)} photos using {threads} thread(s)...")

    # Compute hashes and metadata in parallel
    photo_data = []
    processed_count = 0

    with ThreadPoolExecutor(max_workers=threads) as executor:
        # Submit all photo processing tasks
        future_to_photo = {
            executor.submit(
                process_photo_hash, photo, photo_source, state,
                extract_metadata_func, get_datetime_func
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

            # Log every 100 photos
            if processed_count % 100 == 0:
                logging.info(f"Processing {processed_count}/{len(photos)} ({percentage:.1f}%)")

            try:
                result = future.result()
                if result is not None:
                    photo_data.append(result)
            except Exception as e:
                photo = future_to_photo[future]
                logging.error(f"Error processing photo {photo.id}: {e}")

    # Complete progress bar
    print()  # New line after progress bar

    logging.info(f"Grouping {len(photo_data)} photos by similarity...")

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

    logging.info(f"Found {len(groups)} groups of similar photos")
    return groups
