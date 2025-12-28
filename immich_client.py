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
        self.checksum = data.get('checksum')

        # Store raw data for additional fields
        self.raw_data = data

    def __repr__(self):
        return f"ImmichAsset(id={self.id}, file={self.original_file_name})"


class ImmichClient:
    """Client for Immich API."""

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

    def _get(self, endpoint: str, **kwargs) -> requests.Response:
        """Make GET request to Immich API."""
        url = f"{self.url}{endpoint}"
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response

    def _post(self, endpoint: str, **kwargs) -> requests.Response:
        """Make POST request to Immich API."""
        url = f"{self.url}{endpoint}"
        response = self.session.post(url, **kwargs)
        response.raise_for_status()
        return response

    def _put(self, endpoint: str, **kwargs) -> requests.Response:
        """Make PUT request to Immich API."""
        url = f"{self.url}{endpoint}"
        response = self.session.put(url, **kwargs)
        response.raise_for_status()
        return response

    def _patch(self, endpoint: str, **kwargs) -> requests.Response:
        """Make PATCH request to Immich API."""
        url = f"{self.url}{endpoint}"
        response = self.session.patch(url, **kwargs)
        response.raise_for_status()
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

    def get_all_assets(self, skip_archived: bool = True) -> List[ImmichAsset]:
        """
        Get all assets from Immich.

        Args:
            skip_archived: Skip archived assets

        Returns:
            List of ImmichAsset objects
        """
        try:
            # Get all assets using search endpoint
            response = self._post('/api/search/metadata', json={
                'isArchived': False if skip_archived else None
            })
            data = response.json()

            assets = []
            if 'assets' in data and 'items' in data['assets']:
                for item in data['assets']['items']:
                    # Only include images, skip videos
                    if item.get('type') == 'IMAGE':
                        assets.append(ImmichAsset(item))

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

    def get_album_assets(self, album_id: str) -> List[ImmichAsset]:
        """
        Get all assets in an album.

        Args:
            album_id: Album ID

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
