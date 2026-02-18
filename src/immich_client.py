"""
Immich API client for interacting with Immich photo server.
"""

import requests
from typing import List, Dict, Optional
import io
from PIL import Image


class ImmichAsset:
    """Represents an Immich asset."""

    def __init__(self, data: Dict):
        """
        Initialize from Immich API response.

        Args:
            data: Asset data from API
        """
        self.id = data.get('id')
        self.device_asset_id = data.get('deviceAssetId')
        self.owner_id = data.get('ownerId')
        self.device_id = data.get('deviceId')
        self.type = data.get('type')  # 'IMAGE' or 'VIDEO'
        self.original_path = data.get('originalPath')
        self.original_file_name = data.get('originalFileName')
        self.file_created_at = data.get('fileCreatedAt')
        self.file_modified_at = data.get('fileModifiedAt')
        self.updated_at = data.get('updatedAt')
        self.is_favorite = data.get('isFavorite', False)
        self.is_archived = data.get('isArchived', False)
        self.duration = data.get('duration')
        self.exif_info = data.get('exifInfo', {})
        self.tags = data.get('tags', [])
        self.people = data.get('people', [])
        self.checksum = data.get('checksum')

        # Store raw data for additional fields
        self.raw_data = data

    def __repr__(self):
        return f"ImmichAsset(id={self.id}, file={self.original_file_name})"


class ImmichClient:
    """Client for Immich API."""

    # Maps endpoint prefixes to required API key permission scopes.
    # Used to give actionable 403 error messages.
    _PERMISSION_HINTS = {
        '/api/duplicates': 'duplicate.read',
        '/api/people': 'people.read',
        '/api/faces': 'people.read',
        '/api/search/smart': 'asset.read',
        '/api/search/metadata': 'asset.read',
        '/api/tags': 'tag.read, tag.create, or tag.update',
    }

    def __init__(self, url: str, api_key: str, verify_ssl: bool = True):
        """
        Initialize Immich client.

        Args:
            url: Immich server URL (e.g., http://immich:2283)
            api_key: API key from Immich settings
            verify_ssl: Whether to verify SSL certificates
        """
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.verify_ssl = verify_ssl

        self.session = requests.Session()
        self.session.headers.update({
            'x-api-key': api_key,
            'Accept': 'application/json'
        })
        self.session.verify = verify_ssl

    def _permission_hint(self, endpoint: str) -> str:
        """Return a permission hint string for the given endpoint, or empty."""
        for prefix, scope in self._PERMISSION_HINTS.items():
            if endpoint.startswith(prefix):
                return (f"\n  Hint: Your API key may need the '{scope}' permission. "
                        f"Regenerate it in Immich → Administration → API Keys "
                        f"with the required scope (or use 'All').")
        return ""

    def _raise_with_hint(self, response: requests.Response, endpoint: str):
        """Raise for HTTP errors, adding permission hints for 403."""
        if response.status_code == 403:
            hint = self._permission_hint(endpoint)
            raise requests.HTTPError(
                f"403 Forbidden for {endpoint}{hint}",
                response=response,
            )
        response.raise_for_status()

    def _get(self, endpoint: str, **kwargs) -> requests.Response:
        """Make GET request to Immich API."""
        url = f"{self.url}{endpoint}"
        response = self.session.get(url, **kwargs)
        self._raise_with_hint(response, endpoint)
        return response

    def _post(self, endpoint: str, **kwargs) -> requests.Response:
        """Make POST request to Immich API."""
        url = f"{self.url}{endpoint}"
        response = self.session.post(url, **kwargs)
        self._raise_with_hint(response, endpoint)
        return response

    def _put(self, endpoint: str, **kwargs) -> requests.Response:
        """Make PUT request to Immich API."""
        url = f"{self.url}{endpoint}"
        response = self.session.put(url, **kwargs)
        self._raise_with_hint(response, endpoint)
        return response

    def _patch(self, endpoint: str, **kwargs) -> requests.Response:
        """Make PATCH request to Immich API."""
        url = f"{self.url}{endpoint}"
        response = self.session.patch(url, **kwargs)
        self._raise_with_hint(response, endpoint)
        return response

    def _delete(self, endpoint: str, **kwargs) -> requests.Response:
        """Make DELETE request to Immich API."""
        url = f"{self.url}{endpoint}"
        response = self.session.delete(url, **kwargs)
        self._raise_with_hint(response, endpoint)
        return response

    def ping(self) -> bool:
        """
        Test connection to Immich server.

        Returns:
            True if connection successful
        """
        try:
            # Try the newer endpoint first (v1.118+)
            try:
                response = self._get('/api/server/ping')
                data = response.json()
                if data.get('res') == 'pong':
                    return True
            except:
                pass

            # Try older endpoint
            try:
                response = self._get('/api/server-info/ping')
                data = response.json()
                if data.get('res') == 'pong':
                    return True
            except:
                pass

            # Try getting server version as fallback
            try:
                response = self._get('/api/server-info/version')
                # If we get a successful response with version info, server is up
                if response.status_code == 200:
                    return True
            except:
                pass

            return False
        except Exception as e:
            print(f"Failed to ping Immich server: {e}")
            return False

    def get_all_assets(self, skip_archived: bool = True, limit: Optional[int] = None) -> List[ImmichAsset]:
        """
        Get all assets from Immich.

        Args:
            skip_archived: Skip archived assets
            limit: Maximum number of images to return (for testing/performance)

        Returns:
            List of ImmichAsset objects
        """
        try:
            assets = []
            page = 1
            page_size = 1000  # Request 1000 items per page
            total_fetched = 0

            while True:
                # Get assets using search endpoint with pagination
                response = self._post('/api/search/metadata', json={
                    'isArchived': False if skip_archived else None,
                    'page': page,
                    'size': page_size
                })
                data = response.json()

                # Check if we got any assets
                items = []
                if 'assets' in data and 'items' in data['assets']:
                    items = data['assets']['items']
                elif 'items' in data:
                    # Some versions might return items directly
                    items = data['items']

                if not items:
                    # No more items, we're done
                    break

                # Filter and add images only
                images_this_page = 0
                for item in items:
                    # Only include images, skip videos
                    if item.get('type') == 'IMAGE':
                        assets.append(ImmichAsset(item))
                        images_this_page += 1

                        # Stop if we've reached the limit
                        if limit is not None and len(assets) >= limit:
                            print(f"\r📥 Page {page}: {len(assets)} images fetched (limit reached)        ")
                            print()  # New line after progress
                            return assets

                total_fetched += len(items)
                # Update progress in place
                print(f"\r📥 Page {page}: {len(assets)} images, {total_fetched} total assets", end='', flush=True)

                # If we got fewer items than requested, we've reached the end
                if len(items) < page_size:
                    break

                page += 1

            print()  # New line after progress
            print(f"✓ Fetched {len(assets)} images from {total_fetched} total assets")
            return assets

        except Exception as e:
            print(f"Failed to get assets: {e}")
            return []

    def get_asset_info(self, asset_id: str) -> Optional[ImmichAsset]:
        """
        Get detailed info for a specific asset.

        Args:
            asset_id: Asset ID

        Returns:
            ImmichAsset or None if not found
        """
        try:
            response = self._get(f'/api/assets/{asset_id}')
            return ImmichAsset(response.json())
        except Exception as e:
            print(f"Failed to get asset info for {asset_id}: {e}")
            return None

    def get_asset_thumbnail(self, asset_id: str, size: str = 'preview') -> Optional[bytes]:
        """
        Get thumbnail for an asset.

        Args:
            asset_id: Asset ID
            size: Thumbnail size ('preview' or 'thumbnail')

        Returns:
            Binary image data or None
        """
        try:
            response = self._get(f'/api/assets/{asset_id}/thumbnail', params={'size': size})
            return response.content
        except Exception as e:
            print(f"Failed to get thumbnail for {asset_id}: {e}")
            return None

    def download_asset(self, asset_id: str) -> Optional[bytes]:
        """
        Download full resolution asset.

        Args:
            asset_id: Asset ID

        Returns:
            Binary image data or None
        """
        try:
            response = self._get(f'/api/assets/{asset_id}/original')
            return response.content
        except Exception as e:
            print(f"Failed to download asset {asset_id}: {e}")
            return None

    def bulk_download_thumbnails(self, asset_ids: List[str], max_workers: int = 8,
                                  size: str = 'preview') -> Dict[str, Optional[bytes]]:
        """
        Download multiple thumbnails concurrently using a thread pool.

        Args:
            asset_ids: List of asset IDs to download
            max_workers: Number of concurrent download threads (default: 8)
            size: Thumbnail size ('preview' or 'thumbnail')

        Returns:
            Dict mapping asset_id -> bytes (or None if download failed)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: Dict[str, Optional[bytes]] = {}

        def _fetch(asset_id: str):
            return asset_id, self.get_asset_thumbnail(asset_id, size=size)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch, aid): aid for aid in asset_ids}
            for future in as_completed(futures):
                aid, data = future.result()
                results[aid] = data

        return results

    def update_asset(self, asset_id: str, is_favorite: Optional[bool] = None,
                     is_archived: Optional[bool] = None, description: Optional[str] = None) -> bool:
        """
        Update asset properties.

        Args:
            asset_id: Asset ID
            is_favorite: Mark as favorite
            is_archived: Mark as archived
            description: Asset description

        Returns:
            True if successful
        """
        try:
            data = {}
            if is_favorite is not None:
                data['isFavorite'] = is_favorite
            if is_archived is not None:
                data['isArchived'] = is_archived
            if description is not None:
                data['description'] = description

            self._put(f'/api/assets/{asset_id}', json=data)
            return True
        except Exception as e:
            print(f"Failed to update asset {asset_id}: {e}")
            return False

    def tag_assets(self, asset_ids: List[str], tags: List[str]) -> bool:
        """
        Add tags to multiple assets.

        Args:
            asset_ids: List of asset IDs
            tags: List of tags to add

        Returns:
            True if successful
        """
        try:
            # Tag each asset individually
            # Note: Immich API may vary - adjust based on actual API
            for asset_id in asset_ids:
                asset = self.get_asset_info(asset_id)
                if asset:
                    existing_tags = asset.tags or []
                    new_tags = list(set(existing_tags + tags))
                    self._put(f'/api/assets/{asset_id}', json={'tags': new_tags})

            return True
        except Exception as e:
            print(f"Failed to tag assets: {e}")
            return False

    def get_albums(self) -> List[Dict]:
        """
        Get all albums.

        Returns:
            List of album dictionaries
        """
        try:
            response = self._get('/api/albums')
            return response.json()
        except Exception as e:
            print(f"Failed to get albums: {e}")
            return []

    def get_album_assets(self, album_id: str, limit: Optional[int] = None) -> List[ImmichAsset]:
        """
        Get all assets in an album.

        Args:
            album_id: Album ID
            limit: Maximum number of images to return (for testing/performance)

        Returns:
            List of ImmichAsset objects
        """
        try:
            response = self._get(f'/api/albums/{album_id}')
            data = response.json()

            assets = []
            for asset_data in data.get('assets', []):
                if asset_data.get('type') == 'IMAGE':
                    assets.append(ImmichAsset(asset_data))

                    # Stop if we've reached the limit
                    if limit is not None and len(assets) >= limit:
                        print(f"✓ Reached limit of {limit} images from album")
                        break

            return assets
        except Exception as e:
            print(f"Failed to get album assets: {e}")
            return []

    def create_album(self, name: str, asset_ids: List[str], description: Optional[str] = None) -> Optional[str]:
        """
        Create a new album.

        Args:
            name: Album name
            asset_ids: List of asset IDs to include
            description: Optional album description

        Returns:
            Album ID if successful, None otherwise
        """
        try:
            data = {
                'albumName': name,
                'assetIds': asset_ids
            }
            if description:
                data['description'] = description

            response = self._post('/api/albums', json=data)
            album = response.json()
            return album.get('id')
        except Exception as e:
            print(f"Failed to create album: {e}")
            return None

    def add_assets_to_album(self, album_id: str, asset_ids: List[str]) -> bool:
        """
        Add assets to an existing album.

        Args:
            album_id: Album ID
            asset_ids: List of asset IDs to add

        Returns:
            True if successful
        """
        try:
            self._put(f'/api/albums/{album_id}/assets', json={'ids': asset_ids})
            return True
        except Exception as e:
            print(f"Failed to add assets to album: {e}")
            return False

    def delete_album(self, album_id: str) -> bool:
        """
        Delete an album.

        Args:
            album_id: Album ID to delete

        Returns:
            True if successful
        """
        try:
            self._delete(f'/api/albums/{album_id}')
            return True
        except Exception as e:
            print(f"Failed to delete album {album_id}: {e}")
            return False

    def delete_albums_by_prefix(self, prefix: str, dry_run: bool = True) -> tuple[int, int]:
        """
        Delete all albums with a specific name prefix.

        Args:
            prefix: Album name prefix to match (e.g., "Organized-")
            dry_run: If True, only show what would be deleted without actually deleting

        Returns:
            Tuple of (matched_count, deleted_count)
        """
        try:
            albums = self.get_albums()
            matched_albums = [
                album for album in albums
                if album.get('albumName', '').startswith(prefix)
            ]

            matched_count = len(matched_albums)
            deleted_count = 0

            if matched_count == 0:
                print(f"No albums found with prefix '{prefix}'")
                return (0, 0)

            print(f"\nFound {matched_count} album(s) with prefix '{prefix}':")
            for album in matched_albums:
                album_name = album.get('albumName', 'Unknown')
                album_id = album.get('id', 'Unknown')
                asset_count = album.get('assetCount', 0)
                print(f"  - {album_name} (ID: {album_id}, {asset_count} assets)")

            if dry_run:
                print(f"\nDRY RUN: Would delete {matched_count} album(s)")
                print("Run with dry_run=False to actually delete these albums")
                return (matched_count, 0)

            print(f"\nDeleting {matched_count} album(s)...")
            for album in matched_albums:
                album_name = album.get('albumName', 'Unknown')
                album_id = album.get('id')
                if album_id:
                    if self.delete_album(album_id):
                        deleted_count += 1
                        print(f"  ✓ Deleted: {album_name}")
                    else:
                        print(f"  ✗ Failed to delete: {album_name}")

            print(f"\nDeleted {deleted_count} of {matched_count} album(s)")
            return (matched_count, deleted_count)

        except Exception as e:
            print(f"Failed to delete albums by prefix: {e}")
            return (0, 0)

    # --- People / Faces ---

    def get_people(self, with_hidden: bool = False) -> List[Dict]:
        """
        Get all recognized people.

        Args:
            with_hidden: Include hidden people

        Returns:
            List of person dictionaries
        """
        try:
            params = {'withHidden': str(with_hidden).lower()}
            response = self._get('/api/people', params=params)
            data = response.json()
            return data.get('people', data if isinstance(data, list) else [])
        except Exception as e:
            print(f"Failed to get people: {e}")
            return []

    def get_person(self, person_id: str) -> Optional[Dict]:
        """
        Get details for a specific person.

        Args:
            person_id: Person ID

        Returns:
            Person dictionary or None
        """
        try:
            response = self._get(f'/api/people/{person_id}')
            return response.json()
        except Exception as e:
            print(f"Failed to get person {person_id}: {e}")
            return None

    def get_person_assets(self, person_id: str, limit: Optional[int] = None) -> List[ImmichAsset]:
        """
        Get all photo assets for a specific person.

        Args:
            person_id: Person ID
            limit: Maximum number of images to return

        Returns:
            List of ImmichAsset objects
        """
        try:
            assets = []
            page = 1
            page_size = 1000

            while True:
                response = self._post('/api/search/metadata', json={
                    'personIds': [person_id],
                    'page': page,
                    'size': page_size
                })
                data = response.json()

                items = []
                if 'assets' in data and 'items' in data['assets']:
                    items = data['assets']['items']
                elif 'items' in data:
                    items = data['items']

                if not items:
                    break

                for item in items:
                    if item.get('type') == 'IMAGE':
                        assets.append(ImmichAsset(item))
                        if limit is not None and len(assets) >= limit:
                            return assets

                if len(items) < page_size:
                    break
                page += 1

            return assets
        except Exception as e:
            print(f"Failed to get person assets for {person_id}: {e}")
            return []

    def get_asset_faces(self, asset_id: str) -> List[Dict]:
        """
        Get face bounding boxes and person links for an asset.

        Args:
            asset_id: Asset ID

        Returns:
            List of face dictionaries with bounding boxes and person info
        """
        try:
            response = self._get('/api/faces', params={'id': asset_id})
            return response.json()
        except Exception as e:
            print(f"Failed to get faces for asset {asset_id}: {e}")
            return []

    def get_person_thumbnail(self, person_id: str) -> Optional[bytes]:
        """
        Get face thumbnail for a person.

        Args:
            person_id: Person ID

        Returns:
            Binary image data or None
        """
        try:
            response = self._get(f'/api/people/{person_id}/thumbnail')
            return response.content
        except Exception as e:
            print(f"Failed to get person thumbnail {person_id}: {e}")
            return None

    # --- ML Features ---

    def smart_search(self, query: str, page: int = 1, size: int = 100) -> List[ImmichAsset]:
        """
        CLIP semantic search for photos matching a text query.

        Args:
            query: Natural language search query
            page: Page number (1-indexed)
            size: Results per page

        Returns:
            List of matching ImmichAsset objects
        """
        try:
            response = self._post('/api/search/smart', json={
                'query': query,
                'page': page,
                'size': size
            })
            data = response.json()

            items = []
            if 'assets' in data and 'items' in data['assets']:
                items = data['assets']['items']
            elif 'items' in data:
                items = data['items']

            return [ImmichAsset(item) for item in items if item.get('type') == 'IMAGE']
        except Exception as e:
            print(f"Failed to perform smart search: {e}")
            return []

    def get_duplicates(self) -> List[Dict]:
        """
        Get server-side duplicate photo groups.

        Returns:
            List of duplicate group dictionaries, each with 'duplicateId' and 'assets'
        """
        try:
            response = self._get('/api/duplicates')
            return response.json()
        except Exception as e:
            print(f"Failed to get duplicates: {e}")
            return []

    # --- Bulk Operations ---

    def bulk_update_assets(self, asset_ids: List[str], is_favorite: Optional[bool] = None,
                           is_archived: Optional[bool] = None) -> bool:
        """
        Bulk update multiple assets at once.

        Args:
            asset_ids: List of asset IDs to update
            is_favorite: Set favorite status
            is_archived: Set archived status

        Returns:
            True if successful
        """
        try:
            data = {'ids': asset_ids}
            if is_favorite is not None:
                data['isFavorite'] = is_favorite
            if is_archived is not None:
                data['isArchived'] = is_archived
            self._put('/api/assets', json=data)
            return True
        except Exception as e:
            print(f"Failed to bulk update assets: {e}")
            return False

    def bulk_delete_assets(self, asset_ids: List[str], force: bool = False) -> bool:
        """
        Bulk trash or permanently delete assets.

        Args:
            asset_ids: List of asset IDs
            force: If True, permanently delete. If False, move to trash.

        Returns:
            True if successful
        """
        try:
            self._delete('/api/assets', json={
                'ids': asset_ids,
                'force': force
            })
            return True
        except Exception as e:
            print(f"Failed to bulk delete assets: {e}")
            return False

    # --- Tag Management ---

    def get_tags(self) -> List[Dict]:
        """
        Get all tags.

        Returns:
            List of tag dictionaries
        """
        try:
            response = self._get('/api/tags')
            return response.json()
        except Exception as e:
            print(f"Failed to get tags: {e}")
            return []

    def get_or_create_tag(self, tag_name: str) -> Optional[str]:
        """
        Find a tag by name or create it if it doesn't exist.

        Args:
            tag_name: Tag name (e.g., "photo-organizer/best")

        Returns:
            Tag ID if successful, None otherwise
        """
        try:
            # Search existing tags
            tags = self.get_tags()
            for tag in tags:
                if tag.get('name') == tag_name or tag.get('value') == tag_name:
                    return tag.get('id')

            # Create new tag
            response = self._post('/api/tags', json={'name': tag_name})
            return response.json().get('id')
        except Exception as e:
            print(f"Failed to get or create tag '{tag_name}': {e}")
            return None

    def tag_assets_by_tag_id(self, tag_id: str, asset_ids: List[str]) -> bool:
        """
        Assign assets to a tag by tag ID.

        Args:
            tag_id: Tag ID
            asset_ids: List of asset IDs to tag

        Returns:
            True if successful
        """
        try:
            self._put(f'/api/tags/{tag_id}/assets', json={
                'ids': asset_ids
            })
            return True
        except Exception as e:
            print(f"Failed to tag assets with tag {tag_id}: {e}")
            return False

    def delete_tag(self, tag_id: str) -> bool:
        """
        Delete a tag by ID.

        Args:
            tag_id: Tag ID to delete

        Returns:
            True if successful
        """
        try:
            self._delete(f'/api/tags/{tag_id}')
            return True
        except Exception as e:
            print(f"Failed to delete tag {tag_id}: {e}")
            return False

    def delete_tags_by_prefix(self, prefix: str, dry_run: bool = True) -> tuple:
        """
        Delete all tags matching a prefix.

        Args:
            prefix: Tag name prefix to match (e.g., "photo-organizer/")
            dry_run: If True, only show what would be deleted

        Returns:
            Tuple of (matched_count, deleted_count)
        """
        try:
            tags = self.get_tags()
            matched = [
                t for t in tags
                if (t.get('name') or t.get('value', '')).startswith(prefix)
            ]

            if not matched:
                print(f"No tags found with prefix '{prefix}'")
                return (0, 0)

            print(f"\nFound {len(matched)} tag(s) with prefix '{prefix}':")
            for tag in matched:
                name = tag.get('name') or tag.get('value', 'Unknown')
                print(f"  - {name} (ID: {tag.get('id', '?')})")

            if dry_run:
                print(f"\nDRY RUN: Would delete {len(matched)} tag(s)")
                return (len(matched), 0)

            deleted = 0
            for tag in matched:
                tag_id = tag.get('id')
                name = tag.get('name') or tag.get('value', 'Unknown')
                if tag_id and self.delete_tag(tag_id):
                    deleted += 1
                    print(f"  Deleted: {name}")
                else:
                    print(f"  Failed to delete: {name}")

            print(f"\nDeleted {deleted} of {len(matched)} tag(s)")
            return (len(matched), deleted)
        except Exception as e:
            print(f"Failed to delete tags by prefix: {e}")
            return (0, 0)

    def search_assets_by_tag(self, tag_name: str) -> List[str]:
        """
        Find all asset IDs that have a specific tag.

        Args:
            tag_name: Tag name to search for

        Returns:
            List of asset IDs
        """
        try:
            # Find the tag ID
            tags = self.get_tags()
            tag_id = None
            for tag in tags:
                if (tag.get('name') or tag.get('value', '')) == tag_name:
                    tag_id = tag.get('id')
                    break

            if not tag_id:
                return []

            # Search for assets with this tag
            asset_ids = []
            page = 1
            while True:
                response = self._post('/api/search/metadata', json={
                    'tagIds': [tag_id],
                    'page': page,
                    'size': 1000
                })
                data = response.json()

                items = []
                if 'assets' in data and 'items' in data['assets']:
                    items = data['assets']['items']
                elif 'items' in data:
                    items = data['items']

                if not items:
                    break

                asset_ids.extend(item.get('id') for item in items if item.get('id'))

                if len(items) < 1000:
                    break
                page += 1

            return asset_ids
        except Exception as e:
            print(f"Failed to search assets by tag '{tag_name}': {e}")
            return []
