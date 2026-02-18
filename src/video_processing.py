"""
Video processing module for key frame extraction and similarity comparison.

Extracts representative frames from videos and computes perceptual hashes
for grouping similar video clips together.
"""

import logging
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np
from PIL import Image
import imagehash


class KeyFrameStrategy(Enum):
    """Strategy for extracting key frames from video."""
    SCENE_CHANGE = "scene_change"  # Detect scene changes (default)
    FIXED_INTERVAL = "fixed_interval"  # Every N seconds
    IFRAME = "iframe"  # Extract only I-frames (fastest)


@dataclass
class VideoInfo:
    """Information about a video file."""
    path: Path
    duration: float  # seconds
    fps: float
    frame_count: int
    width: int
    height: int
    codec: str


@dataclass
class VideoHash:
    """Perceptual hash data for a video."""
    frame_hashes: List[imagehash.ImageHash]
    thumbnail_hash: Optional[imagehash.ImageHash]
    duration: float
    frame_count: int

    def average_hash(self) -> Optional[imagehash.ImageHash]:
        """Get average of all frame hashes for quick comparison."""
        if not self.frame_hashes:
            return None
        # Use the first frame hash as representative
        return self.frame_hashes[0]


# Supported video formats
VIDEO_FORMATS = {
    '.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v',
    '.wmv', '.flv', '.mpg', '.mpeg', '.3gp', '.mts'
}


def is_video_file(path: Path) -> bool:
    """Check if a file is a supported video format."""
    return path.suffix.lower() in VIDEO_FORMATS


def get_video_info(video_path: Path) -> Optional[VideoInfo]:
    """Get information about a video file.

    Args:
        video_path: Path to the video file

    Returns:
        VideoInfo object or None if video cannot be read
    """
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])

        duration = frame_count / fps if fps > 0 else 0

        cap.release()

        return VideoInfo(
            path=video_path,
            duration=duration,
            fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
            codec=codec,
        )
    except Exception as e:
        logging.error(f"Error getting video info for {video_path}: {e}")
        return None


def extract_key_frames(
    video_path: Path,
    strategy: KeyFrameStrategy = KeyFrameStrategy.SCENE_CHANGE,
    max_frames: int = 10,
    interval_seconds: float = 5.0,
    scene_threshold: float = 30.0,
) -> List[np.ndarray]:
    """Extract key frames from a video.

    Args:
        video_path: Path to the video file
        strategy: Frame extraction strategy
        max_frames: Maximum number of frames to extract
        interval_seconds: Interval between frames (for FIXED_INTERVAL)
        scene_threshold: Threshold for scene change detection (lower = more sensitive)

    Returns:
        List of frames as numpy arrays (BGR format)
    """
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logging.error(f"Cannot open video: {video_path}")
            return []

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if frame_count == 0 or fps == 0:
            cap.release()
            return []

        frames = []

        if strategy == KeyFrameStrategy.FIXED_INTERVAL:
            frames = _extract_fixed_interval(cap, fps, frame_count, interval_seconds, max_frames)
        elif strategy == KeyFrameStrategy.SCENE_CHANGE:
            frames = _extract_scene_changes(cap, frame_count, scene_threshold, max_frames)
        elif strategy == KeyFrameStrategy.IFRAME:
            frames = _extract_iframes(cap, frame_count, max_frames)

        cap.release()
        return frames

    except Exception as e:
        logging.error(f"Error extracting frames from {video_path}: {e}")
        return []


def _extract_fixed_interval(
    cap: cv2.VideoCapture,
    fps: float,
    frame_count: int,
    interval_seconds: float,
    max_frames: int,
) -> List[np.ndarray]:
    """Extract frames at fixed time intervals."""
    frames = []
    interval_frames = int(fps * interval_seconds)

    if interval_frames == 0:
        interval_frames = 1

    # Always get first frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ret, frame = cap.read()
    if ret:
        frames.append(frame)

    # Get frames at intervals
    frame_positions = list(range(interval_frames, frame_count, interval_frames))

    for pos in frame_positions[:max_frames - 1]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)

    return frames


def _extract_scene_changes(
    cap: cv2.VideoCapture,
    frame_count: int,
    threshold: float,
    max_frames: int,
) -> List[np.ndarray]:
    """Extract frames at scene changes using histogram comparison."""
    frames = []
    prev_hist = None

    # Sample every Nth frame for efficiency
    sample_interval = max(1, frame_count // 500)

    for i in range(0, frame_count, sample_interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            continue

        # Convert to grayscale and compute histogram
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        cv2.normalize(hist, hist)

        if prev_hist is None:
            # Always include first frame
            frames.append(frame)
            prev_hist = hist
            continue

        # Compare histograms
        diff = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CHISQR)

        if diff > threshold:
            frames.append(frame)
            prev_hist = hist

            if len(frames) >= max_frames:
                break

    # If we didn't get enough frames, fall back to interval sampling
    if len(frames) < 3:
        fps = cap.get(cv2.CAP_PROP_FPS)
        return _extract_fixed_interval(cap, fps, frame_count, 5.0, max_frames)

    return frames


def _extract_iframes(
    cap: cv2.VideoCapture,
    frame_count: int,
    max_frames: int,
) -> List[np.ndarray]:
    """Extract I-frames (keyframes) from video.

    Note: OpenCV doesn't directly expose I-frame detection, so we sample
    at positions that are likely to be I-frames (every ~1 second typically).
    """
    frames = []
    fps = cap.get(cv2.CAP_PROP_FPS)

    # I-frames are typically every 1-2 seconds in most codecs
    iframe_interval = int(fps * 1.0) if fps > 0 else 30

    for i in range(0, frame_count, iframe_interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
            if len(frames) >= max_frames:
                break

    return frames


def compute_video_hash(
    video_path: Path,
    strategy: KeyFrameStrategy = KeyFrameStrategy.SCENE_CHANGE,
    max_frames: int = 10,
    hash_size: int = 8,
) -> Optional[VideoHash]:
    """Compute perceptual hash for a video.

    Args:
        video_path: Path to the video file
        strategy: Key frame extraction strategy
        max_frames: Maximum frames to hash
        hash_size: Size of perceptual hash

    Returns:
        VideoHash object or None if video cannot be processed
    """
    info = get_video_info(video_path)
    if info is None:
        return None

    frames = extract_key_frames(video_path, strategy, max_frames)
    if not frames:
        return None

    frame_hashes = []
    for frame in frames:
        # Convert BGR to RGB for PIL
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_frame)

        # Compute perceptual hash
        phash = imagehash.phash(pil_image, hash_size=hash_size)
        frame_hashes.append(phash)

    # Create thumbnail hash from middle frame
    middle_idx = len(frames) // 2
    rgb_middle = cv2.cvtColor(frames[middle_idx], cv2.COLOR_BGR2RGB)
    pil_middle = Image.fromarray(rgb_middle)
    thumbnail_hash = imagehash.phash(pil_middle, hash_size=hash_size)

    return VideoHash(
        frame_hashes=frame_hashes,
        thumbnail_hash=thumbnail_hash,
        duration=info.duration,
        frame_count=info.frame_count,
    )


def video_hash_distance(hash1: VideoHash, hash2: VideoHash) -> float:
    """Compute distance between two video hashes.

    Uses a combination of:
    - Frame hash comparison (weighted average of best matches)
    - Duration similarity
    - Thumbnail hash comparison

    Args:
        hash1: First video hash
        hash2: Second video hash

    Returns:
        Distance score (lower = more similar, 0-64 range like image hashes)
    """
    if not hash1.frame_hashes or not hash2.frame_hashes:
        return 64.0  # Maximum distance

    # Compare frame hashes - find best matches
    min_distances = []

    for h1 in hash1.frame_hashes:
        # Find minimum distance to any frame in hash2
        min_dist = min(h1 - h2 for h2 in hash2.frame_hashes)
        min_distances.append(min_dist)

    # Average of best matches
    frame_distance = sum(min_distances) / len(min_distances)

    # Thumbnail comparison (quick check)
    if hash1.thumbnail_hash and hash2.thumbnail_hash:
        thumb_distance = hash1.thumbnail_hash - hash2.thumbnail_hash
    else:
        thumb_distance = frame_distance

    # Duration similarity (penalize very different durations)
    if hash1.duration > 0 and hash2.duration > 0:
        duration_ratio = min(hash1.duration, hash2.duration) / max(hash1.duration, hash2.duration)
        duration_penalty = (1 - duration_ratio) * 10  # Up to 10 points penalty
    else:
        duration_penalty = 0

    # Combined score (weighted average)
    combined = (frame_distance * 0.6 + thumb_distance * 0.3 + duration_penalty * 0.1)

    return min(combined, 64.0)


def are_videos_similar(
    hash1: VideoHash,
    hash2: VideoHash,
    threshold: int = 10,
) -> bool:
    """Check if two videos are similar based on their hashes.

    Args:
        hash1: First video hash
        hash2: Second video hash
        threshold: Maximum distance to consider similar (default: 10)

    Returns:
        True if videos are similar
    """
    distance = video_hash_distance(hash1, hash2)
    return distance <= threshold


def extract_video_thumbnail(
    video_path: Path,
    output_path: Optional[Path] = None,
    position: float = 0.1,
) -> Optional[Path]:
    """Extract a thumbnail from a video.

    Args:
        video_path: Path to the video file
        output_path: Where to save thumbnail (temp file if None)
        position: Position in video (0.0-1.0) to extract frame

    Returns:
        Path to thumbnail image or None
    """
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        target_frame = int(frame_count * position)

        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return None

        # Convert to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_frame)

        # Save thumbnail
        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix='.jpg')
            output_path = Path(output_path)

        pil_image.save(output_path, 'JPEG', quality=85)
        return output_path

    except Exception as e:
        logging.error(f"Error extracting thumbnail from {video_path}: {e}")
        return None
