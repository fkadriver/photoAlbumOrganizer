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


# Supported image formats
IMAGE_FORMATS = {
    '.jpg', '.jpeg', '.png', '.heic', '.cr2', '.nef', '.arw', '.dng', '.gif', '.webp'
}

# Supported video formats
VIDEO_FORMATS = {
    '.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v',
    '.wmv', '.flv', '.mpg', '.mpeg', '.3gp', '.mts'
}


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
    def list_photos(self, album: Optional[str] = None, limit: Optional[int] = None,
                    media_type: str = 'image') -> List[Photo]:
        """
        List all photos/videos from this source.

        Args:
            album: Optional album/folder filter
            limit: Optional limit on number of photos to return (for testing/performance)
            media_type: Type of media to list ('image' or 'video')

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
            supported_formats: Set of supported file extensions (deprecated, use media_type in list_photos)
        """
        self.source_dir = Path(source_dir)
        self.supported_formats = supported_formats or IMAGE_FORMATS

    def list_photos(self, album: Optional[str] = None, limit: Optional[int] = None,
                    media_type: str = 'image') -> List[Photo]:
        """List all photos or videos in the directory.

        Args:
            album: Optional album/folder filter
            limit: Optional limit on number of photos to return
            media_type: 'image' for photos, 'video' for videos
        """
        photos = []

        # Select formats based on media type
        formats = VIDEO_FORMATS if media_type == 'video' else IMAGE_FORMATS

        search_dir = self.source_dir
        if album:
            search_dir = self.source_dir / album

        for path in search_dir.rglob('*'):
            if path.suffix.lower() in formats:
                photo_id = str(path.relative_to(self.source_dir))
                photo = Photo(
                    photo_id=photo_id,
                    source='local',
                    metadata={
                        'filepath': str(path),
                        'media_type': media_type,
                    }
                )
                photo.cached_path = path
                photos.append(photo)

                if limit and len(photos) >= limit:
                    break

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

    def list_photos(self, album: Optional[str] = None, limit: Optional[int] = None,
                    media_type: str = 'image') -> List[Photo]:
        """List all photos or videos from Immich.

        Args:
            album: Optional album name to filter
            limit: Optional limit on number of assets to return
            media_type: 'image' for photos, 'video' for videos
        """
        # Map media_type to Immich asset type
        immich_type = 'VIDEO' if media_type == 'video' else 'IMAGE'

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
            # Filter by asset type
            if asset.type != immich_type:
                continue

            photo = Photo(
                photo_id=asset.id,
                source='immich',
                metadata={
                    'asset_id': asset.id,
                    'filename': asset.original_file_name,
                    'file_created_at': asset.file_created_at,
                    'file_modified_at': asset.file_modified_at,
                    'is_favorite': asset.is_favorite,
                    'exif': asset.exif_info,
                    'media_type': media_type,
                }
            )
            photos.append(photo)

            if limit and len(photos) >= limit:
                break

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


class HybridPhotoSource(PhotoSource):
    """Hybrid photo source: local filesystem + Immich API.

    Reads photos directly from the local filesystem (for speed) while
    maintaining Immich API connectivity for tagging, albums, favorites, etc.

    Ideal for users running the organizer on the same machine as Immich,
    avoiding HTTP download overhead.
    """

    # Common Immich library paths (Docker mount points)
    DEFAULT_LIBRARY_PATHS = [
        '/mnt/photos/immich-app/library',
        '/photos/library',
        '/data/immich/library',
        '/var/lib/immich/library',
    ]

    def __init__(self, library_path: str, immich_url: str, api_key: str,
                 verify_ssl: bool = True, supported_formats: Optional[set] = None):
        """
        Initialize hybrid photo source.

        Args:
            library_path: Local path to Immich library (e.g., /mnt/photos/immich-app/library)
            immich_url: Immich server URL (e.g., http://localhost:2283)
            api_key: Immich API key for authentication
            verify_ssl: Whether to verify SSL certificates
            supported_formats: Set of supported file extensions
        """
        self.library_path = Path(library_path)
        self.supported_formats = supported_formats or {
            '.jpg', '.jpeg', '.png', '.heic', '.cr2', '.nef', '.arw', '.dng', '.gif', '.webp'
        }

        # Validate library path exists
        if not self.library_path.exists():
            raise FileNotFoundError(
                f"Immich library path not found: {library_path}\n"
                f"Common paths: {', '.join(self.DEFAULT_LIBRARY_PATHS)}"
            )

        # Initialize Immich client
        self.client = ImmichClient(immich_url, api_key, verify_ssl)

        # Test connection
        if not self.client.ping():
            raise ConnectionError(f"Failed to connect to Immich server at {immich_url}")

        # Build path -> asset_id mapping
        self._path_to_asset: Dict[str, str] = {}
        self._asset_to_path: Dict[str, str] = {}
        self._asset_metadata: Dict[str, Dict] = {}
        self._build_asset_mapping()

    def _build_asset_mapping(self):
        """Build mapping between local paths and Immich asset IDs."""
        print("Building local path to Immich asset mapping...")
        assets = self.client.get_all_assets()

        image_count = 0
        video_count = 0

        for asset in assets:
            original_path = asset.original_path
            if not original_path:
                continue

            # Track asset type
            asset_type = 'video' if asset.type == 'VIDEO' else 'image'

            # Normalize the path for comparison
            # Immich stores paths relative to its library root
            self._path_to_asset[original_path] = asset.id
            self._asset_to_path[asset.id] = original_path
            self._asset_metadata[asset.id] = {
                'asset_id': asset.id,
                'filename': asset.original_file_name,
                'file_created_at': asset.file_created_at,
                'file_modified_at': asset.file_modified_at,
                'is_favorite': asset.is_favorite,
                'exif': asset.exif_info,
                'original_path': original_path,
                'media_type': asset_type,
            }

            if asset_type == 'video':
                video_count += 1
            else:
                image_count += 1

        print(f"  Mapped {len(self._path_to_asset)} Immich assets ({image_count} images, {video_count} videos)")

    def _find_asset_id_for_path(self, local_path: Path) -> Optional[str]:
        """Find Immich asset ID for a local file path.

        Tries multiple matching strategies:
        1. Exact path match
        2. Path relative to library root
        3. Filename + size match (fallback)
        """
        path_str = str(local_path)

        # Strategy 1: Exact match
        if path_str in self._path_to_asset:
            return self._path_to_asset[path_str]

        # Strategy 2: Try path relative to library root
        try:
            rel_path = local_path.relative_to(self.library_path)
            # Immich paths often start with upload/ or library/ prefix
            for prefix in ['', 'upload/', 'library/']:
                test_path = prefix + str(rel_path)
                if test_path in self._path_to_asset:
                    return self._path_to_asset[test_path]
        except ValueError:
            pass

        # Strategy 3: Match by filename (less reliable but useful fallback)
        filename = local_path.name
        candidates = []
        for immich_path, asset_id in self._path_to_asset.items():
            if immich_path.endswith('/' + filename) or immich_path == filename:
                candidates.append(asset_id)

        if len(candidates) == 1:
            return candidates[0]

        # Strategy 4: If multiple filename matches, try to match by size
        if len(candidates) > 1:
            try:
                local_size = local_path.stat().st_size
                for asset_id in candidates:
                    meta = self._asset_metadata.get(asset_id, {})
                    exif = meta.get('exif', {})
                    if exif:
                        immich_size = exif.get('fileSizeInByte', 0)
                        if immich_size == local_size:
                            return asset_id
            except:
                pass

        return None

    def list_photos(self, album: Optional[str] = None, limit: Optional[int] = None,
                    media_type: str = 'image') -> List[Photo]:
        """List photos or videos from local filesystem that are also in Immich.

        Args:
            album: Optional album name to filter
            limit: Optional limit on number of assets to return
            media_type: 'image' for photos, 'video' for videos
        """
        photos = []

        # Select formats based on media type
        formats = VIDEO_FORMATS if media_type == 'video' else IMAGE_FORMATS

        search_dir = self.library_path
        if album:
            # For album filtering, use Immich API to get album assets
            # then filter local files to only those in the album
            albums = self.client.get_albums()
            album_id = None
            for alb in albums:
                if alb.get('albumName') == album:
                    album_id = alb.get('id')
                    break

            if not album_id:
                print(f"Album '{album}' not found in Immich")
                return []

            album_assets = self.client.get_album_assets(album_id, limit=limit)
            album_asset_ids = {a.id for a in album_assets}

            # Find local files that match album assets
            for local_path in self.library_path.rglob('*'):
                if local_path.suffix.lower() not in formats:
                    continue

                asset_id = self._find_asset_id_for_path(local_path)
                if asset_id and asset_id in album_asset_ids:
                    # Check media type matches
                    asset_meta = self._asset_metadata.get(asset_id, {})
                    if asset_meta.get('media_type', 'image') != media_type:
                        continue

                    photo = self._create_photo_from_local(local_path, asset_id, media_type)
                    photos.append(photo)

                    if limit and len(photos) >= limit:
                        break
        else:
            # Scan local filesystem
            for local_path in self.library_path.rglob('*'):
                if local_path.suffix.lower() not in formats:
                    continue

                asset_id = self._find_asset_id_for_path(local_path)
                if asset_id:
                    # Check media type matches
                    asset_meta = self._asset_metadata.get(asset_id, {})
                    if asset_meta.get('media_type', 'image') != media_type:
                        continue

                    photo = self._create_photo_from_local(local_path, asset_id, media_type)
                    photos.append(photo)

                    if limit and len(photos) >= limit:
                        break

        return photos

    def _create_photo_from_local(self, local_path: Path, asset_id: str,
                                  media_type: str = 'image') -> Photo:
        """Create a Photo object from local path with Immich metadata."""
        metadata = self._asset_metadata.get(asset_id, {}).copy()
        metadata['filepath'] = str(local_path)
        metadata['local_path'] = str(local_path)
        metadata['media_type'] = media_type

        photo = Photo(
            photo_id=asset_id,  # Use Immich asset ID as photo ID
            source='hybrid',
            metadata=metadata
        )
        photo.cached_path = local_path  # Direct filesystem access
        return photo

    def get_photo_data(self, photo: Photo) -> bytes:
        """Get photo data from local filesystem."""
        local_path = photo.metadata.get('local_path') or photo.metadata.get('filepath')
        if local_path:
            return Path(local_path).read_bytes()

        # Fallback: download from Immich
        asset_id = photo.metadata.get('asset_id', photo.id)
        data = self.client.download_asset(asset_id)
        if data:
            return data
        raise ValueError(f"Failed to get photo data for {photo.id}")

    def get_metadata(self, photo: Photo) -> Dict:
        """Get metadata combining local file info and Immich data."""
        from PIL.ExifTags import TAGS

        local_path = photo.metadata.get('local_path') or photo.metadata.get('filepath')
        if not local_path:
            # Fallback to Immich metadata
            return photo.metadata

        path = Path(local_path)
        metadata = {
            'filename': path.name,
            'filepath': str(path),
            'filesize': path.stat().st_size,
            'modified_time': datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            'created_time': datetime.fromtimestamp(path.stat().st_ctime).isoformat(),
            'asset_id': photo.metadata.get('asset_id', photo.id),
            'is_favorite': photo.metadata.get('is_favorite', False),
        }

        # Read local EXIF
        try:
            with Image.open(path) as img:
                metadata['dimensions'] = f"{img.size[0]}x{img.size[1]}"
                metadata['format'] = img.format

                exif_data = img.getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)
                        metadata[f'exif_{tag}'] = str(value)
        except Exception as e:
            metadata['error'] = f"Could not read EXIF: {str(e)}"

        return metadata

    def tag_photo(self, photo: Photo, tags: List[str]) -> bool:
        """Add tags via Immich API."""
        asset_id = photo.metadata.get('asset_id', photo.id)
        return self.client.tag_assets([asset_id], tags)

    def create_album(self, name: str, photos: List[Photo]) -> bool:
        """Create album via Immich API."""
        asset_ids = [p.metadata.get('asset_id', p.id) for p in photos]
        album_id = self.client.create_album(name, asset_ids)
        return album_id is not None

    def set_favorite(self, photo: Photo, favorite: bool = True) -> bool:
        """Mark photo as favorite via Immich API."""
        asset_id = photo.metadata.get('asset_id', photo.id)
        return self.client.update_asset(asset_id, is_favorite=favorite)

    def set_archived(self, photo: Photo, archived: bool = True) -> bool:
        """Mark photo as archived via Immich API."""
        asset_id = photo.metadata.get('asset_id', photo.id)
        return self.client.update_asset(asset_id, is_archived=archived)

    def list_people(self) -> List[Dict]:
        """List recognized people from Immich."""
        return self.client.get_people()

    def list_photos_by_person(self, person_id: str, limit: Optional[int] = None) -> List[Photo]:
        """List photos of a specific person, using local files where available."""
        assets = self.client.get_person_assets(person_id, limit=limit)
        photos = []

        for asset in assets:
            # Try to find local file for this asset
            local_path = None
            if asset.original_path:
                # Check if we can find it locally
                for test_path in [
                    self.library_path / asset.original_path,
                    Path(asset.original_path),
                ]:
                    if test_path.exists():
                        local_path = test_path
                        break

            metadata = {
                'asset_id': asset.id,
                'filename': asset.original_file_name,
                'file_created_at': asset.file_created_at,
                'file_modified_at': asset.file_modified_at,
                'is_favorite': asset.is_favorite,
                'exif': asset.exif_info,
            }

            if local_path:
                metadata['filepath'] = str(local_path)
                metadata['local_path'] = str(local_path)

            photo = Photo(
                photo_id=asset.id,
                source='hybrid',
                metadata=metadata
            )

            if local_path:
                photo.cached_path = local_path

            photos.append(photo)

        return photos

    def get_asset_face_data(self, photo: Photo) -> List[Dict]:
        """Get face bounding boxes via Immich API."""
        asset_id = photo.metadata.get('asset_id', photo.id)
        return self.client.get_asset_faces(asset_id)

    def prefetch_photos(self, photos: List[Photo], max_workers: int = 8) -> int:
        """No prefetch needed - photos are already on local filesystem."""
        # Just verify all photos have cached_path set
        count = 0
        for photo in photos:
            local_path = photo.metadata.get('local_path') or photo.metadata.get('filepath')
            if local_path and Path(local_path).exists():
                photo.cached_path = Path(local_path)
                count += 1
        return count
