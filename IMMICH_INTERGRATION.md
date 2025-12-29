# Immich Integration Design

Integration with [Immich](https://immich.app/) - the self-hosted photo and video management solution.

## Features

### Phase 1: Basic Integration ✅ COMPLETED
- [x] Connect to Immich API
- [x] Read photos from Immich library
- [x] Tag photos as potential duplicates
- [x] Download photos for processing (with caching)

### Phase 2: Advanced Features ✅ COMPLETED
- [x] Process photos directly from Immich without downloading (tag-only mode)
- [x] Create Immich albums for photo groups
- [x] Update Immich metadata with tags
- [x] Mark best photo as favorite in Immich
- [x] Support for specific album processing
- [x] Thumbnail vs full-resolution download options

## Configuration

### Immich API Setup

1. **Get API Key** from Immich:
   - Go to Immich Settings → Account Settings → API Keys
   - Create a new API key
   - Copy the key

#### Required API Key Permissions

The Photo Organizer requires different permissions depending on the mode you're using:

**Server Permissions:**
- ✅ `server.about` or `server.statistics` - For connection testing and server info

**For tag-only mode (minimum):**
- ✅ `asset.read` - Read asset metadata, search assets, get thumbnails
- ✅ `asset.update` - Update tags on assets

**For create-albums mode:**
- ✅ `asset.read` - Read asset metadata
- ✅ `asset.update` - Mark assets as favorites
- ✅ `album.read` - List and read album information
- ✅ `album.create` - Create new albums
- ✅ `albumAsset.create` (or `album.update`) - Add assets to albums

**For cleanup mode (delete albums):**
- ✅ `album.read` - List albums to find matches
- ✅ `album.delete` - Delete albums by prefix

**For download mode:**
- ✅ `asset.read` - Read asset metadata
- ✅ `asset.download` - Download full resolution images

**Permissions NOT needed:**
- ❌ `server.versionCheck`, `server.apkLinks`, `server.storage` - Not used

**Note:** If you're running Immich version before v1.138.0, you may need to enable the **"all"** permission for the API key, as granular permissions were added in later versions.

**Recommended setup for full functionality:**
Enable these permissions when creating your API key:
- Server: `server.about`, `server.statistics`
- Asset: `asset.read`, `asset.update`, `asset.download`
- Album: `album.read`, `album.create`, `album.delete`, `albumAsset.create`

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

See [IMMICH_USAGE.md](IMMICH_USAGE.md) for complete usage guide and examples.

### Quick Examples

```bash
# Tag duplicates in Immich (no download)
python photo_organizer.py \
  --source-type immich \
  --immich-url http://immich:2283 \
  --immich-api-key YOUR_KEY \
  --tag-only

# Create Immich albums for each group
python photo_organizer.py \
  --source-type immich \
  --immich-url http://immich:2283 \
  --immich-api-key YOUR_KEY \
  --create-albums \
  --mark-best-favorite

# Download and organize locally
python photo_organizer.py \
  --source-type immich \
  --immich-url http://immich:2283 \
  --immich-api-key YOUR_KEY \
  --output ~/Organized

# Process specific album
python photo_organizer.py \
  --source-type immich \
  --immich-url http://immich:2283 \
  --immich-api-key YOUR_KEY \
  --immich-album "Vacation 2024" \
  --create-albums
```

## Implementation

The integration is fully implemented across these files:

- **[immich_client.py](immich_client.py)** - Immich API client wrapper
- **[photo_sources.py](photo_sources.py)** - Photo source abstraction layer
- **[photo_organizer.py](photo_organizer.py)** - Main organizer with Immich support

### Architecture Overview

```python
# Photo Source Abstraction
PhotoSource (ABC)
├── LocalPhotoSource (filesystem)
└── ImmichPhotoSource (Immich API)
    └── ImmichClient (API wrapper)
    └── PhotoCache (LRU cache)

# Photo Object
Photo
├── id: str
├── source: str ('local' or 'immich')
├── metadata: dict
└── cached_path: Optional[Path]
```

### Key Features Implemented

**ImmichClient** - Full API wrapper with:
- Connection testing (`ping()`)
- Asset listing and filtering
- Thumbnail and full-resolution download
- Tagging support
- Album creation and management
- Favorite marking
- Metadata extraction

**PhotoCache** - Intelligent caching with:
- LRU eviction policy
- Configurable size limits (default: 5GB)
- Access time tracking
- Automatic space management
- Metadata persistence

**ImmichPhotoSource** - Complete integration:
- Implements `PhotoSource` interface
- Automatic caching of downloads
- Thumbnail optimization for speed
- Album filtering support
- Full CRUD operations on Immich

### Caching Strategy

The PhotoCache implementation provides:

- **Automatic eviction** - Removes oldest files when cache is full
- **Safe filenames** - Uses MD5 hash of photo ID for filesystem safety
- **Metadata tracking** - JSON file tracks cache entries
- **Access time updates** - LRU based on file access time
- **Space management** - Pre-evicts before downloads to prevent errors

Default cache location: `~/.cache/photo-organizer/immich/`

## Workflow Examples

See [IMMICH_USAGE.md](IMMICH_USAGE.md) for detailed workflows.

### Quick Workflow Reference

**Tag duplicates for review:**
```bash
python photo_organizer.py --source-type immich \
  --immich-url URL --immich-api-key KEY \
  --tag-only --threshold 3
```

**Create albums with favorites:**
```bash
python photo_organizer.py --source-type immich \
  --immich-url URL --immich-api-key KEY \
  --create-albums --mark-best-favorite
```

**Download and organize:**
```bash
python photo_organizer.py --source-type immich \
  --immich-url URL --immich-api-key KEY \
  --output ~/Organized
```

## API Endpoints Used

| Endpoint | Method | Purpose | Implemented |
|----------|--------|---------|-------------|
| `/api/server-info/ping` | GET | Test connection | ✅ |
| `/api/search/metadata` | POST | Search assets | ✅ |
| `/api/assets/{id}` | GET | Get asset details | ✅ |
| `/api/assets/{id}/thumbnail` | GET | Get thumbnail | ✅ |
| `/api/assets/{id}/original` | GET | Download full resolution | ✅ |
| `/api/assets/{id}` | PUT | Update asset (favorite, tags) | ✅ |
| `/api/albums` | GET | List albums | ✅ |
| `/api/albums` | POST | Create album | ✅ |
| `/api/albums/{id}` | GET | Get album details | ✅ |
| `/api/albums/{id}` | DELETE | Delete album | ✅ |
| `/api/albums/{id}/assets` | PUT | Add assets to album | ✅ |

## Performance Considerations

### Current Implementation

**Thumbnail optimization:**
- Uses Immich's preview thumbnail API by default
- Significantly faster than full-resolution downloads
- ~90% smaller file sizes for caching
- Use `--use-full-resolution` only when needed

**Caching:**
- Default 5GB cache prevents re-downloads
- LRU eviction keeps frequently accessed photos
- Configurable via `--immich-cache-size`

**Network efficiency:**
- Connection reuse via `requests.Session`
- Concurrent processing of groups
- Optional SSL verification bypass for local servers

### Optimization Tips

1. **Use thumbnails** (default) for duplicate detection
2. **Increase cache size** if processing large libraries repeatedly
3. **Process by album** to handle libraries in chunks
4. **Tag-only mode** avoids any downloads
5. **Monitor Immich server load** during processing

## Security

### API Key Storage
- **Never commit API keys to git**
- Use environment variables or config files
- Config files should be in `.gitignore`

### Network Security
- Support HTTPS for Immich connections
- Validate SSL certificates
- Option to use self-signed certs for local servers

## Known Limitations

1. **Safe Operations Only**
   - No deletion of photos in Immich (by design)
   - No modification of original files
   - Only adds tags, creates albums, marks favorites

2. **Processing Constraints**
   - Network latency affects performance
   - Large libraries take longer
   - Face detection requires download (thumbnails or full)

3. **Immich Version Compatibility**
   - Tested with Immich v1.95+
   - API changes may require updates
   - Verify compatibility after Immich upgrades

## Testing

To test the integration:

```bash
# 1. Test connection
python -c "
from immich_client import ImmichClient
client = ImmichClient('http://immich:2283', 'YOUR_KEY')
print('Connected!' if client.ping() else 'Failed')
"

# 2. Test with small album
python photo_organizer.py \
  --source-type immich \
  --immich-url http://immich:2283 \
  --immich-api-key YOUR_KEY \
  --immich-album "Test Album" \
  --tag-only \
  --threshold 5

# 3. Verify in Immich web UI
```

## Future Enhancements

Potential future improvements:

- **Async downloads** - Parallel asset downloads using `aiohttp`
- **Batch API calls** - Process multiple assets per request
- **Machine learning** - Integration with Immich's ML features
- **Shared albums** - Handle shared/partner photos
- **Archive suggestions** - Flag low-quality photos for archival
- **Video support** - Extend to video duplicate detection

## See Also

- **[IMMICH_USAGE.md](IMMICH_USAGE.md)** - Complete usage guide with examples
- **[README.md](README.md)** - Main project documentation
- **[Immich Documentation](https://immich.app/docs)** - Official Immich docs
- **[Immich API](https://immich.app/docs/api)** - API reference

## Summary

Both Phase 1 and Phase 2 of the Immich integration are **fully implemented** and ready to use. The integration provides:

✅ **Complete API wrapper** with all essential endpoints
✅ **Intelligent caching** for performance
✅ **Tag-only mode** for non-destructive duplicate detection
✅ **Album creation** for organized grouping
✅ **Favorite marking** for best photo selection
✅ **Flexible workflows** for different use cases
✅ **Comprehensive documentation** and examples

See [IMMICH_USAGE.md](IMMICH_USAGE.md) to get started!
