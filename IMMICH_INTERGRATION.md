# Immich Integration Design

Integration with [Immich](https://immich.app/) - the self-hosted photo and video management solution.

## Features

### Phase 1: Basic Integration
- [x] Connect to Immich API
- [x] Read photos from Immich library
- [x] Tag photos as potential duplicates
- [x] Download photos for processing (with caching)

### Phase 2: Advanced Features
- [ ] Process photos directly from Immich without downloading
- [ ] Create Immich albums for photo groups
- [ ] Update Immich metadata with similarity scores
- [ ] Sync best photo selections back to Immich

## Configuration

### Immich API Setup

1. **Get API Key** from Immich:
   - Go to Immich Settings → Account Settings → API Keys
   - Create a new API key
   - Copy the key

2. **Configure Environment**:
```bash
# Add to .envrc or export manually
export IMMICH_URL="http://your-immich-server:2283"
export IMMICH_API_KEY="your-api-key-here"
```

Or use a configuration file:
```bash
# ~/.config/photo-organizer/config.yaml
immich:
  url: "http://your-immich-server:2283"
  api_key: "your-api-key-here"
  cache_dir: "/tmp/photo-organizer-cache"
  cache_size_mb: 5000  # 5GB cache
```

## Usage

### Basic Immich Integration

```bash
# Scan Immich library for duplicates
python photo_organizer.py \
  --source immich \
  --immich-url http://immich:2283 \
  --immich-api-key YOUR_KEY \
  --output ~/Organized

# Tag duplicates in Immich (no download)
python photo_organizer.py \
  --source immich \
  --tag-only \
  --duplicate-tag "possible-duplicate"

# Process specific Immich album
python photo_organizer.py \
  --source immich \
  --immich-album "Family Photos 2024" \
  --output ~/Organized
```

### Advanced Options

```bash
# Create Immich albums for each group
python photo_organizer.py \
  --source immich \
  --create-albums \
  --album-prefix "Organized-"

# Set best photo as favorite in Immich
python photo_organizer.py \
  --source immich \
  --mark-best-favorite

# Process without downloading (stream processing)
python photo_organizer.py \
  --source immich \
  --stream-mode \
  --tag-only
```

## Architecture

### Photo Source Abstraction

```python
class PhotoSource:
    """Abstract base class for photo sources"""
    def list_photos(self) -> List[Photo]
    def get_photo(self, photo_id: str) -> bytes
    def get_metadata(self, photo_id: str) -> dict
    def tag_photo(self, photo_id: str, tags: List[str])
    def create_album(self, name: str, photo_ids: List[str])

class LocalPhotoSource(PhotoSource):
    """Local filesystem photos"""
    pass

class ImmichPhotoSource(PhotoSource):
    """Immich server photos"""
    def __init__(self, url: str, api_key: str):
        self.client = ImmichClient(url, api_key)
```

### Immich API Integration

```python
class ImmichClient:
    """Immich API client"""
    
    def __init__(self, url: str, api_key: str):
        self.url = url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'x-api-key': api_key
        })
    
    def get_all_assets(self) -> List[Asset]:
        """Fetch all assets from Immich"""
        response = self.session.get(f"{self.url}/api/assets")
        return response.json()
    
    def get_asset_thumbnail(self, asset_id: str) -> bytes:
        """Get thumbnail for similarity comparison"""
        response = self.session.get(
            f"{self.url}/api/assets/{asset_id}/thumbnail"
        )
        return response.content
    
    def tag_assets(self, asset_ids: List[str], tag: str):
        """Add tags to assets"""
        for asset_id in asset_ids:
            self.session.put(
                f"{self.url}/api/assets/{asset_id}",
                json={"tags": [tag]}
            )
    
    def create_album(self, name: str, asset_ids: List[str]):
        """Create album with selected assets"""
        response = self.session.post(
            f"{self.url}/api/albums",
            json={
                "albumName": name,
                "assetIds": asset_ids
            }
        )
        return response.json()
```

### Caching Strategy

```python
class PhotoCache:
    """Cache downloaded photos to avoid re-downloading"""
    
    def __init__(self, cache_dir: str, max_size_mb: int = 5000):
        self.cache_dir = Path(cache_dir)
        self.max_size = max_size_mb * 1024 * 1024
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_cached_photo(self, photo_id: str) -> Optional[bytes]:
        """Get photo from cache if available"""
        cache_file = self.cache_dir / f"{photo_id}.jpg"
        if cache_file.exists():
            return cache_file.read_bytes()
        return None
    
    def cache_photo(self, photo_id: str, data: bytes):
        """Cache photo data"""
        # Check cache size and evict old entries if needed
        self._ensure_space(len(data))
        cache_file = self.cache_dir / f"{photo_id}.jpg"
        cache_file.write_bytes(data)
```

## Workflow Examples

### Workflow 1: Tag Duplicates in Immich

```bash
# 1. Scan Immich for similar photos
python photo_organizer.py \
  --source immich \
  --tag-only \
  --threshold 5 \
  --duplicate-tag "review-duplicate"

# 2. Review in Immich web UI
# - Navigate to photos with "review-duplicate" tag
# - Manually review and delete/keep

# 3. Remove tags after review
python photo_organizer.py \
  --source immich \
  --remove-tag "review-duplicate"
```

### Workflow 2: Create Organized Albums

```bash
# 1. Scan and create albums for each group
python photo_organizer.py \
  --source immich \
  --create-albums \
  --album-prefix "Similar-" \
  --threshold 5

# Result: Creates albums like:
# - Similar-0001 (5 photos)
# - Similar-0002 (3 photos)
# etc.

# 2. Review albums in Immich
# 3. Pick favorites from each album
```

### Workflow 3: Hybrid Local + Immich

```bash
# 1. Process local photos first
python photo_organizer.py \
  --source local \
  -s ~/Photos \
  -o ~/Organized \
  --save-hashes hashes.db

# 2. Check Immich against local hashes
python photo_organizer.py \
  --source immich \
  --load-hashes hashes.db \
  --tag-duplicates-of-local
```

## API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/assets` | GET | List all assets |
| `/api/assets/{id}` | GET | Get asset details |
| `/api/assets/{id}/thumbnail` | GET | Get thumbnail |
| `/api/assets/{id}` | PUT | Update asset metadata |
| `/api/albums` | POST | Create album |
| `/api/albums/{id}` | PUT | Update album |
| `/api/search/metadata` | POST | Search by metadata |

## Performance Considerations

### Immich Server Load
- Use thumbnail API for similarity comparison (faster, less bandwidth)
- Batch API calls (100 assets at a time)
- Implement rate limiting to avoid overwhelming server
- Cache downloaded data locally

### Network Optimization
```python
# Download thumbnails in parallel
async def download_thumbnails_batch(asset_ids: List[str]):
    async with aiohttp.ClientSession() as session:
        tasks = [
            download_thumbnail(session, asset_id)
            for asset_id in asset_ids
        ]
        return await asyncio.gather(*tasks)
```

### Cache Management
- Default cache: 5GB
- LRU eviction policy
- Store thumbnails (smaller) instead of full resolution
- Configurable cache location

## Security

### API Key Storage
- **Never commit API keys to git**
- Use environment variables or config files
- Config files should be in `.gitignore`

### Network Security
- Support HTTPS for Immich connections
- Validate SSL certificates
- Option to use self-signed certs for local servers

## Limitations

1. **Read-Only Operations** (Phase 1)
   - No deletion of photos in Immich
   - No modification of original files
   - Only metadata/tagging changes

2. **Processing Speed**
   - Network latency affects performance
   - Thumbnail download time adds overhead
   - Consider local processing for large libraries

3. **Immich Version Compatibility**
   - Tested with Immich v1.95+
   - API may change in future versions
   - Check compatibility before major Immich upgrades

## Future Enhancements

- [ ] **Real-time sync**: Watch Immich for new photos
- [ ] **Bi-directional sync**: Sync organized photos back
- [ ] **Machine learning**: Use Immich's ML models
- [ ] **Shared albums**: Handle shared/partner photos
- [ ] **Archive integration**: Tag for archival/deletion
- [ ] **Mobile app integration**: Review on mobile

## See Also

- [Immich API Documentation](https://immich.app/docs/api)
- [Photo Organizer Main README](README.md)
- [Configuration Guide](CONFIGURATION.md)
