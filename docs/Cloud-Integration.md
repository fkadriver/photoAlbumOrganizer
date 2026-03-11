# Cloud Photo Service Integration — Design Document

This document outlines the architecture for adding Apple Photos and Google Photos as photo sources, alongside the existing `local` and `immich` backends.

## Current Architecture

The `PhotoSource` ABC (`src/photo_sources.py`) defines 6 abstract methods:

```python
class PhotoSource(ABC):
    def list_photos(album, limit) -> List[Photo]
    def get_photo_data(photo) -> bytes
    def get_metadata(photo) -> Dict
    def tag_photo(photo, tags) -> bool
    def create_album(name, photos) -> bool
    def set_favorite(photo, favorite) -> bool
```

The `Photo` class carries a flexible `metadata` dict and an optional `cached_path` for local caching. `PhotoCache` (LRU, thread-safe, configurable size) is reusable by any source.

Existing implementations: `LocalPhotoSource` (filesystem), `ImmichPhotoSource` (REST API + PhotoCache).

---

## Apple Photos

### Access Options

| Approach | Platform | Read | Write | Faces | Albums | Notes |
|----------|----------|------|-------|-------|--------|-------|
| **osxphotos** | macOS only | Yes | No | Yes (from DB) | Yes | Reads SQLite DB directly; maintained, well-documented |
| **PhotoKit (pyobjc)** | macOS only | Yes | Yes | Yes | Yes | Apple's native framework; requires Objective-C bridge |
| **iCloud web API** | Cross-platform | Partial | No | No | No | Undocumented; fragile; requires Apple ID auth |
| **pyicloud** | Cross-platform | Yes (download) | No | No | Yes | Third-party; 2FA required; rate-limited |

### Recommended: osxphotos

The `osxphotos` library is the most practical choice. It reads the Apple Photos SQLite database directly, providing rich metadata including faces, keywords, albums, smart albums, and location data — all without network access.

```
pip install osxphotos
```

### Proposed Implementation

```python
class ApplePhotoSource(PhotoSource):
    """Photo source for Apple Photos (macOS only).

    Reads the local Photos library database using osxphotos.
    Cross-platform operation is not supported.
    """

    def __init__(self, library_path: Optional[str] = None):
        """
        Args:
            library_path: Path to Photos library. Auto-detected if None.
                Default: ~/Pictures/Photos Library.photoslibrary
        """
        import platform
        if platform.system() != 'Darwin':
            raise RuntimeError("Apple Photos integration requires macOS")

        import osxphotos
        self.photosdb = osxphotos.PhotosDB(dbfile=library_path)

    def list_photos(self, album=None, limit=None) -> List[Photo]:
        if album:
            photos_raw = self.photosdb.photos(albums=[album])
        else:
            photos_raw = self.photosdb.photos()

        photos = []
        for p in photos_raw:
            if limit and len(photos) >= limit:
                break
            # Filter to supported image types
            if not p.isphoto:
                continue
            photo = Photo(
                photo_id=p.uuid,
                source='apple',
                metadata={
                    'filename': p.original_filename,
                    'filepath': str(p.path) if p.path else None,
                    'date': p.date.isoformat() if p.date else None,
                    'title': p.title,
                    'description': p.description,
                    'keywords': p.keywords,
                    'albums': [a.title for a in p.album_info],
                    'persons': p.persons,  # Face recognition names
                    'favorite': p.favorite,
                    'hidden': p.hidden,
                    'latitude': p.latitude,
                    'longitude': p.longitude,
                    'uti': p.uti,  # e.g., 'public.heic', 'public.jpeg'
                }
            )
            # Set cached_path if the original file is accessible
            if p.path and Path(p.path).exists():
                photo.cached_path = Path(p.path)
            photos.append(photo)
        return photos

    def get_photo_data(self, photo: Photo) -> bytes:
        # If cached_path exists, read directly
        if photo.cached_path and photo.cached_path.exists():
            return photo.cached_path.read_bytes()
        # Otherwise export to temp directory
        p = self.photosdb.get_photo(photo.id)
        exported = p.export('/tmp/photo-organizer-apple/')
        if exported:
            return Path(exported[0]).read_bytes()
        raise FileNotFoundError(f"Could not export photo {photo.id}")

    def get_metadata(self, photo: Photo) -> Dict:
        return photo.metadata.copy()

    # Write operations — not supported by osxphotos
    def tag_photo(self, photo, tags) -> bool:
        return False

    def create_album(self, name, photos) -> bool:
        return False

    def set_favorite(self, photo, favorite) -> bool:
        return False
```

### Key Considerations

- **HEIC format**: Apple Photos stores many images as HEIC. Pillow requires `pillow-heif` for HEIC support. The `osxphotos` export can convert to JPEG on export.
- **Library locking**: The Photos app may lock the database while running. `osxphotos` handles this gracefully.
- **Faces/People**: `p.persons` returns a list of recognized person names. This enables group-by-person mode without additional API calls.
- **iCloud originals**: Photos stored only in iCloud (not downloaded locally) may not have a `path`. The `export()` method can trigger a download, but this requires the Photos app to be running.
- **Photo streams**: Shared albums and photo streams may require different access patterns.

### CLI Integration

```
--source-type apple
--apple-library PATH   # Optional, auto-detected on macOS
```

### Dependencies

```
osxphotos>=0.68.0      # Apple Photos database access (macOS only)
pillow-heif>=0.13.0    # HEIC/HEIF image support (optional)
```

---

## Google Photos

### Access Options

| Approach | Auth | Read | Write | Faces | Rate Limits |
|----------|------|------|-------|-------|-------------|
| **Google Photos Library API** | OAuth2 | Yes | Create albums only | No public API | 10K req/day, 75 req/min |
| **Google Takeout** | Manual export | Yes (offline) | No | No | None (offline) |
| **Unofficial APIs** | Google account | Yes | Yes | Yes | Fragile, may break |

### Recommended: Google Photos Library API

The official API provides reliable read access with standard OAuth2 authentication. Write operations are limited to creating albums (no tagging, favoriting, or archiving).

### OAuth2 Setup

Users create a Google Cloud project, enable the Photos Library API, and download a `credentials.json` file. The first run triggers a browser-based consent flow; the resulting token is cached locally for subsequent runs.

```
pip install google-auth-oauthlib google-api-python-client
```

### Proposed Implementation

```python
class GooglePhotoSource(PhotoSource):
    """Photo source for Google Photos.

    Uses the Google Photos Library API (read-only for media items).
    Requires OAuth2 credentials from Google Cloud Console.
    """

    SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly']

    def __init__(self, credentials_path: str, token_path: str = None,
                 cache_dir: str = None, cache_size_mb: int = 5000):
        """
        Args:
            credentials_path: Path to Google OAuth2 credentials JSON
            token_path: Path to store/load auth token (default: ~/.config/photo-organizer/google_token.json)
            cache_dir: Photo cache directory
            cache_size_mb: Cache size limit in MB
        """
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        if token_path is None:
            token_path = os.path.expanduser('~/.config/photo-organizer/google_token.json')

        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, self.SCOPES)
                creds = flow.run_local_server(port=0)
            # Save token for next run
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, 'w') as f:
                f.write(creds.to_json())

        self.service = build('photoslibrary', 'v1', credentials=creds,
                             static_discovery=False)

        # Reuse existing PhotoCache
        if cache_dir is None:
            cache_dir = os.path.expanduser('~/.cache/photo-organizer/google/')
        self.cache = PhotoCache(cache_dir, cache_size_mb)

    def list_photos(self, album=None, limit=None) -> List[Photo]:
        photos = []
        page_token = None

        while True:
            if album:
                # Search by album
                album_id = self._find_album_id(album)
                if not album_id:
                    print(f"Album '{album}' not found")
                    return []
                body = {'albumId': album_id, 'pageSize': 100}
                if page_token:
                    body['pageToken'] = page_token
                results = self.service.mediaItems().search(body=body).execute()
            else:
                params = {'pageSize': 100}
                if page_token:
                    params['pageToken'] = page_token
                results = self.service.mediaItems().list(**params).execute()

            items = results.get('mediaItems', [])
            for item in items:
                if limit and len(photos) >= limit:
                    return photos
                # Filter to photos only
                mime = item.get('mimeType', '')
                if not mime.startswith('image/'):
                    continue
                metadata = item.get('mediaMetadata', {})
                photo = Photo(
                    photo_id=item['id'],
                    source='google',
                    metadata={
                        'filename': item.get('filename'),
                        'mime_type': mime,
                        'description': item.get('description', ''),
                        'creation_time': metadata.get('creationTime'),
                        'width': metadata.get('width'),
                        'height': metadata.get('height'),
                        'base_url': item.get('baseUrl'),
                        # Camera metadata
                        'camera_make': metadata.get('photo', {}).get('cameraMake'),
                        'camera_model': metadata.get('photo', {}).get('cameraModel'),
                        'focal_length': metadata.get('photo', {}).get('focalLength'),
                        'aperture': metadata.get('photo', {}).get('apertureFNumber'),
                        'iso': metadata.get('photo', {}).get('isoEquivalent'),
                        'exposure_time': metadata.get('photo', {}).get('exposureTime'),
                    }
                )
                photos.append(photo)

            page_token = results.get('nextPageToken')
            if not page_token:
                break

        return photos

    def get_photo_data(self, photo: Photo) -> bytes:
        # Check cache first
        cached = self.cache.get_cached_photo(photo.id)
        if cached:
            photo.cached_path = cached
            return cached.read_bytes()

        # Download via baseUrl
        base_url = photo.metadata.get('base_url')
        if not base_url:
            raise ValueError(f"No base URL for photo {photo.id}")

        # Append =d for full download
        import requests
        response = requests.get(f"{base_url}=d")
        response.raise_for_status()
        data = response.content

        # Cache it
        photo.cached_path = self.cache.cache_photo(photo.id, data)
        return data

    def get_metadata(self, photo: Photo) -> Dict:
        return photo.metadata.copy()

    # Write operations — very limited in Google Photos API
    def tag_photo(self, photo, tags) -> bool:
        return False  # Not supported by Google Photos API

    def create_album(self, name, photos) -> bool:
        # Google Photos API supports album creation
        try:
            body = {'album': {'title': name}}
            album = self.service.albums().create(body=body).execute()
            album_id = album.get('id')
            if not album_id:
                return False
            # Add items to album
            items = [{'simpleMediaItem': {'id': p.id}} for p in photos]
            # Note: can only add items owned by the user
            self.service.mediaItems().batchCreate(
                body={'albumId': album_id, 'newMediaItems': items}
            ).execute()
            return True
        except Exception as e:
            print(f"Failed to create Google Photos album: {e}")
            return False

    def set_favorite(self, photo, favorite) -> bool:
        return False  # Not supported by Google Photos API

    def _find_album_id(self, album_name: str) -> Optional[str]:
        """Find album ID by name."""
        page_token = None
        while True:
            params = {'pageSize': 50}
            if page_token:
                params['pageToken'] = page_token
            results = self.service.albums().list(**params).execute()
            for album in results.get('albums', []):
                if album.get('title') == album_name:
                    return album.get('id')
            page_token = results.get('nextPageToken')
            if not page_token:
                break
        return None
```

### Key Considerations

- **baseUrl expiry**: Google Photos `baseUrl` values expire after ~1 hour. Downloads must happen promptly after listing, or the URL must be refreshed via another `mediaItems.get()` call.
- **Rate limits**: 10,000 requests/day, 75 requests/minute. For large libraries, pagination + caching is essential. Consider adding retry with exponential backoff.
- **No face recognition API**: Google Photos has built-in face grouping, but it is not exposed via the public API. Group-by-person mode would not be available for this source.
- **Read-only**: Cannot modify photos, tag them, or mark favorites. The organizer would operate in a download-and-organize-locally mode only.
- **Album creation quirk**: `batchCreate` is designed for uploading new media. Adding existing items to albums uses `albums().addMediaItems()` instead.
- **Quota costs**: The Photos Library API has no monetary cost, only rate limits.

### CLI Integration

```
--source-type google
--google-credentials PATH    # Path to OAuth2 credentials JSON
--google-token PATH          # Optional token cache location
```

### Dependencies

```
google-auth-oauthlib>=1.0.0
google-api-python-client>=2.0.0
```

---

## Abstract PhotoSource Extensions

Both new sources benefit from optional methods on the ABC:

```python
class PhotoSource(ABC):
    # ... existing 6 abstract methods ...

    def list_people(self) -> List[Dict]:
        """List recognized people. Override in subclasses that support it."""
        return []

    def list_photos_by_person(self, person_id: str, limit=None) -> List[Photo]:
        """List photos of a specific person."""
        return []

    def set_archived(self, photo: Photo, archived: bool = True) -> bool:
        """Mark a photo as archived."""
        return False

    def prefetch_photos(self, photos: List[Photo], max_workers: int = 4) -> int:
        """Pre-download and cache photos concurrently."""
        return 0
```

Apple Photos (`list_people` via `p.persons`) and Immich (`list_people` via API) support person listing. Google Photos does not.

---

## Feature Matrix

| Feature | Local | Immich | Apple (proposed) | Google (proposed) |
|---------|-------|--------|------------------|-------------------|
| List photos | Yes | Yes | Yes | Yes |
| Download/cache | N/A (local) | Yes | Yes (export) | Yes (baseUrl) |
| Metadata/EXIF | Yes | Yes | Yes | Partial |
| Tag photos | No | Yes | No | No |
| Create albums | No | Yes | No | Yes (limited) |
| Mark favorite | No | Yes | No | No |
| Archive | No | Yes | No | No |
| Face/people data | No | Yes (API) | Yes (DB) | No (not public) |
| Group by person | No | Yes | Yes | No |
| CLIP smart search | No | Yes | No | No |
| Server duplicates | No | Yes | No | No |

---

## Implementation Priority

1. **Apple Photos** — higher value (rich metadata, faces, local-only = fast), lower complexity
2. **Google Photos** — lower value (read-only, no faces), higher complexity (OAuth2 setup)

Both can be implemented independently. Neither blocks the other or the existing Immich/local functionality.
