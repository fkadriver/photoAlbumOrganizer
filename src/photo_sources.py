"""
Photo source abstraction layer for supporting multiple photo sources.
Supports local filesystem and Immich server integration.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Optional, BinaryIO
from datetime import datetime
import hashlib
import io
import time
import os
import threading
from PIL import Image
from immich_client import ImmichClient


class Photo:
    """Represents a photo from any source."""

    def __init__(self, photo_id: str, source: str, metadata: Optional[Dict] = None):
        """
        Initialize a Photo.

        Args:
            photo_id: Unique identifier for the photo
            source: Source type ('local' or 'immich')
            metadata: Optional metadata dictionary
        """
        self.id = photo_id
        self.source = source
        self.metadata = metadata or {}
        self.cached_path: Optional[Path] = None

    def __repr__(self):
        return f"Photo(id={self.id}, source={self.source})"


class PhotoSource(ABC):
    """Abstract base class for photo sources."""

    @abstractmethod
    def list_photos(self, album: Optional[str] = None, limit: Optional[int] = None) -> List[Photo]:
        """
        List all photos from this source.

        Args:
            album: Optional album/folder filter
            limit: Optional limit on number of photos to return (for testing/performance)

        Returns:
            List of Photo objects
        """
        pass

    @abstractmethod
    def get_photo_data(self, photo: Photo) -> bytes:
        """
        Get the binary data for a photo.

        Args:
            photo: Photo object

        Returns:
            Binary photo data
        """
        pass

    @abstractmethod
    def get_metadata(self, photo: Photo) -> Dict:
        """
        Get metadata for a photo.

        Args:
            photo: Photo object

        Returns:
            Metadata dictionary
        """
        pass

    @abstractmethod
    def tag_photo(self, photo: Photo, tags: List[str]) -> bool:
        """
        Add tags to a photo.

        Args:
            photo: Photo object
            tags: List of tags to add

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def create_album(self, name: str, photos: List[Photo]) -> bool:
        """
        Create an album with specified photos.

        Args:
            name: Album name
            photos: List of photos to include

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def set_favorite(self, photo: Photo, favorite: bool = True) -> bool:
        """
        Mark a photo as favorite.

        Args:
            photo: Photo object
            favorite: True to mark as favorite, False to unmark

        Returns:
            True if successful
        """
        pass

    def set_archived(self, photo: Photo, archived: bool = True) -> bool:
        """Mark a photo as archived. Override in subclasses that support it."""
        return False

    def list_people(self) -> List[Dict]:
        """List recognized people. Override in subclasses that support it."""
        return []

    def list_photos_by_person(self, person_id: str, limit: Optional[int] = None) -> List[Photo]:
        """List photos of a specific person. Override in subclasses that support it."""
        return []

    def get_asset_face_data(self, photo: Photo) -> List[Dict]:
        """Get face bounding boxes for a photo. Override in subclasses that support it."""
        return []

    def prefetch_photos(self, photos: List[Photo], max_workers: int = 4) -> int:
        """Pre-download and cache photos concurrently. Override in subclasses that support it."""
        return 0


class LocalPhotoSource(PhotoSource):
    """Photo source for local filesystem."""

    def __init__(self, source_dir: str, supported_formats: Optional[set] = None):
        """
        Initialize local photo source.

        Args:
            source_dir: Root directory containing photos
            supported_formats: Set of supported file extensions
        """
        self.source_dir = Path(source_dir)
        self.supported_formats = supported_formats or {
            '.jpg', '.jpeg', '.png', '.heic', '.cr2', '.nef', '.arw', '.dng'
        }

    def list_photos(self, album: Optional[str] = None, limit: Optional[int] = None) -> List[Photo]:
        """List all photos in the directory."""
        photos = []

        search_dir = self.source_dir
        if album:
            search_dir = self.source_dir / album

        for path in search_dir.rglob('*'):
            if path.suffix.lower() in self.supported_formats:
                photo_id = str(path.relative_to(self.source_dir))
                photo = Photo(
                    photo_id=photo_id,
                    source='local',
                    metadata={'filepath': str(path)}
                )
                photo.cached_path = path
                photos.append(photo)

        return photos

    def get_photo_data(self, photo: Photo) -> bytes:
        """Get photo binary data from filesystem."""
        path = Path(photo.metadata['filepath'])
        return path.read_bytes()

    def get_metadata(self, photo: Photo) -> Dict:
        """Get metadata from local file."""
        from PIL.ExifTags import TAGS

        path = Path(photo.metadata['filepath'])
        metadata = {
            'filename': path.name,
            'filepath': str(path),
            'filesize': path.stat().st_size,
            'modified_time': datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            'created_time': datetime.fromtimestamp(path.stat().st_ctime).isoformat(),
        }

        try:
            with Image.open(path) as img:
                metadata['dimensions'] = f"{img.size[0]}x{img.size[1]}"
                metadata['format'] = img.format

                # Extract EXIF
                exif_data = img.getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)
                        metadata[f'exif_{tag}'] = str(value)
        except Exception as e:
            metadata['error'] = f"Could not read EXIF: {str(e)}"

        return metadata

    def tag_photo(self, photo: Photo, tags: List[str]) -> bool:
        """Local source doesn't support tagging."""
        return False

    def create_album(self, name: str, photos: List[Photo]) -> bool:
        """Local source doesn't support albums."""
        return False

    def set_favorite(self, photo: Photo, favorite: bool = True) -> bool:
        """Local source doesn't support favorites."""
        return False


class PhotoCache:
    """Cache for downloaded photos to avoid re-downloading."""

    def __init__(self, cache_dir: str, max_size_mb: int = 5000):
        """
        Initialize photo cache.

        Args:
            cache_dir: Directory to store cached photos
            max_size_mb: Maximum cache size in megabytes
        """
        self.cache_dir = Path(cache_dir)
        self.max_size = max_size_mb * 1024 * 1024
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # Create metadata file for tracking cache
        self.metadata_file = self.cache_dir / 'cache_metadata.json'
        self._load_metadata()

    def _load_metadata(self):
        """Load cache metadata."""
        import json

        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    self.metadata = json.load(f)
            except:
                self.metadata = {}
        else:
            self.metadata = {}

    def _save_metadata(self):
        """Save cache metadata."""
        import json

        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f)

    def _get_cache_size(self) -> int:
        """Get current cache size in bytes."""
        total = 0
        for path in self.cache_dir.rglob('*'):
            if path.is_file() and path != self.metadata_file:
                total += path.stat().st_size
        return total

    def _evict_old_entries(self, needed_space: int):
        """Evict old cache entries to make space."""
        current_size = self._get_cache_size()

        if current_size + needed_space <= self.max_size:
            return

        # Sort files by access time
        files = []
        for path in self.cache_dir.rglob('*'):
            if path.is_file() and path != self.metadata_file:
                files.append((path.stat().st_atime, path))

        files.sort()

        # Remove oldest files until we have space
        space_needed = (current_size + needed_space) - self.max_size
        freed = 0

        for _, path in files:
            if freed >= space_needed:
                break

            size = path.stat().st_size
            path.unlink()

            # Remove from metadata
            photo_id = path.stem
            if photo_id in self.metadata:
                del self.metadata[photo_id]

            freed += size

        self._save_metadata()

    def get_cached_photo(self, photo_id: str) -> Optional[Path]:
        """
        Get cached photo path if available.

        Args:
            photo_id: Photo identifier

        Returns:
            Path to cached file or None
        """
        # Create safe filename from photo_id
        safe_id = hashlib.md5(photo_id.encode()).hexdigest()
        cache_file = self.cache_dir / f"{safe_id}.jpg"

        if cache_file.exists():
            # Update access time
            cache_file.touch()
            return cache_file

        return None

    def cache_photo(self, photo_id: str, data: bytes) -> Path:
        """
        Cache photo data.

        Args:
            photo_id: Photo identifier
            data: Binary photo data

        Returns:
            Path to cached file
        """
        # Create safe filename
        safe_id = hashlib.md5(photo_id.encode()).hexdigest()
        cache_file = self.cache_dir / f"{safe_id}.jpg"

        with self._lock:
            # Ensure we have space
            self._evict_old_entries(len(data))

            # Write file
            cache_file.write_bytes(data)

            # Update metadata
            self.metadata[safe_id] = {
                'photo_id': photo_id,
                'cached_at': datetime.now().isoformat(),
                'size': len(data)
            }
            self._save_metadata()

        return cache_file

    def clear_cache(self):
        """Clear all cached photos."""
        for path in self.cache_dir.rglob('*'):
            if path.is_file() and path != self.metadata_file:
                path.unlink()

        self.metadata = {}
        self._save_metadata()


class ImmichPhotoSource(PhotoSource):
    """Photo source for Immich server."""

    def __init__(self, url: str, api_key: str, cache_dir: Optional[str] = None,
                 cache_size_mb: int = 5000, verify_ssl: bool = True,
                 use_thumbnails: bool = True):
        """
        Initialize Immich photo source.

        Args:
            url: Immich server URL
            api_key: API key for authentication
            cache_dir: Directory for caching downloaded photos
            cache_size_mb: Maximum cache size in MB
            verify_ssl: Whether to verify SSL certificates
            use_thumbnails: Use thumbnails for processing (faster, less bandwidth)
        """
        self.client = ImmichClient(url, api_key, verify_ssl)
        self.use_thumbnails = use_thumbnails

        # Setup cache
        if cache_dir is None:
            cache_dir = Path.home() / '.cache' / 'photo-organizer' / 'immich'

        self.cache = PhotoCache(str(cache_dir), cache_size_mb)

        # Test connection
        if not self.client.ping():
            raise ConnectionError(f"Failed to connect to Immich server at {url}")

    def list_photos(self, album: Optional[str] = None, limit: Optional[int] = None) -> List[Photo]:
        """List all photos from Immich."""
        if album:
            # Get album by name
            albums = self.client.get_albums()
            album_id = None

            for alb in albums:
                if alb.get('albumName') == album:
                    album_id = alb.get('id')
                    break

            if not album_id:
                print(f"Album '{album}' not found")
                return []

            assets = self.client.get_album_assets(album_id, limit=limit)
        else:
            assets = self.client.get_all_assets(limit=limit)

        photos = []
        for asset in assets:
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
            photos.append(photo)

        return photos

    def get_photo_data(self, photo: Photo) -> bytes:
        """Get photo data from Immich (with caching)."""
        # Check cache first
        cached_path = self.cache.get_cached_photo(photo.id)
        if cached_path:
            try:
                return cached_path.read_bytes()
            except FileNotFoundError:
                # File was deleted after cache check (race condition), re-download
                pass

        # Download from Immich
        asset_id = photo.metadata.get('asset_id', photo.id)

        if self.use_thumbnails:
            data = self.client.get_asset_thumbnail(asset_id, size='preview')
        else:
            data = self.client.download_asset(asset_id)

        if data:
            # Cache it
            cached_path = self.cache.cache_photo(photo.id, data)
            photo.cached_path = cached_path
            return data
        else:
            raise ValueError(f"Failed to download photo {photo.id}")

    def get_metadata(self, photo: Photo) -> Dict:
        """Get metadata from Immich asset."""
        asset_id = photo.metadata.get('asset_id', photo.id)
        asset = self.client.get_asset_info(asset_id)

        if not asset:
            return photo.metadata

        metadata = {
            'filename': asset.original_file_name,
            'filepath': asset.original_path,
            'filesize': asset.exif_info.get('fileSizeInByte', 0),
            'created_time': asset.file_created_at,
            'modified_time': asset.file_modified_at,
            'is_favorite': asset.is_favorite,
        }

        # Add EXIF data
        if asset.exif_info:
            for key, value in asset.exif_info.items():
                metadata[f'exif_{key}'] = str(value)

        return metadata

    def tag_photo(self, photo: Photo, tags: List[str]) -> bool:
        """Add tags to photo in Immich."""
        asset_id = photo.metadata.get('asset_id', photo.id)
        return self.client.tag_assets([asset_id], tags)

    def create_album(self, name: str, photos: List[Photo]) -> bool:
        """Create album in Immich."""
        asset_ids = [p.metadata.get('asset_id', p.id) for p in photos]
        album_id = self.client.create_album(name, asset_ids)
        return album_id is not None

    def set_favorite(self, photo: Photo, favorite: bool = True) -> bool:
        """Mark photo as favorite in Immich."""
        asset_id = photo.metadata.get('asset_id', photo.id)
        return self.client.update_asset(asset_id, is_favorite=favorite)

    def set_archived(self, photo: Photo, archived: bool = True) -> bool:
        """Mark photo as archived in Immich."""
        asset_id = photo.metadata.get('asset_id', photo.id)
        return self.client.update_asset(asset_id, is_archived=archived)

    def list_people(self) -> List[Dict]:
        """List recognized people from Immich."""
        return self.client.get_people()

    def list_photos_by_person(self, person_id: str, limit: Optional[int] = None) -> List[Photo]:
        """List photos of a specific person from Immich."""
        assets = self.client.get_person_assets(person_id, limit=limit)
        photos = []
        for asset in assets:
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
            photos.append(photo)
        return photos

    def get_asset_face_data(self, photo: Photo) -> List[Dict]:
        """Get face bounding boxes for a photo from Immich."""
        asset_id = photo.metadata.get('asset_id', photo.id)
        return self.client.get_asset_faces(asset_id)

    def prefetch_photos(self, photos: List[Photo], max_workers: int = 8) -> int:
        """Pre-download and cache photos concurrently using bulk parallel download."""
        to_download = [p for p in photos if not self.cache.get_cached_photo(p.id)]

        if not to_download:
            return 0

        print(f"Pre-fetching {len(to_download)} photos ({max_workers} parallel workers)...")

        asset_ids = [p.metadata.get('asset_id', p.id) for p in to_download]
        id_to_photo = {p.metadata.get('asset_id', p.id): p for p in to_download}

        if self.use_thumbnails:
            results = self.client.bulk_download_thumbnails(
                asset_ids, max_workers=max_workers, size='preview'
            )
        else:
            # Full resolution — parallel downloads using thread pool
            from concurrent.futures import ThreadPoolExecutor, as_completed

            results = {}

            def _dl_full(aid):
                return aid, self.client.download_asset(aid)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_dl_full, aid): aid for aid in asset_ids}
                for future in as_completed(futures):
                    aid, data = future.result()
                    results[aid] = data

        downloaded = 0
        for asset_id, data in results.items():
            if data:
                photo = id_to_photo.get(asset_id)
                if photo:
                    cached_path = self.cache.cache_photo(photo.id, data)
                    photo.cached_path = cached_path
                    downloaded += 1

        pct = (downloaded / len(to_download)) * 100 if to_download else 100
        print(f"  Pre-fetched {downloaded}/{len(to_download)} photos ({pct:.0f}%)")
        return downloaded
