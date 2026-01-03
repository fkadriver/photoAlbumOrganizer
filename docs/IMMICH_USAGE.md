# Immich Integration Usage Guide

Complete guide for using the Photo Album Organizer with Immich integration.

## Quick Start

### 1. Get Your Immich API Key

1. Open your Immich web interface
2. Go to **Settings** → **Account Settings** → **API Keys**
3. Click **New API Key**
4. Give it a name (e.g., "Photo Organizer")
5. Copy the generated API key

### 2. Install Dependencies

```bash
# Install required package
pip install requests

# Or reinstall all requirements
pip install -r requirements.txt
```

### 3. Basic Usage Examples

#### Tag Potential Duplicates in Immich

This mode scans your Immich library and tags similar photos without downloading anything:

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://your-immich-server:2283 \
  --immich-api-key YOUR_API_KEY_HERE \
  --tag-only \
  --threshold 5
```

After running, you can:
- Open Immich web UI
- Filter by tag "photo-organizer-duplicate"
- Manually review and delete unwanted duplicates

#### Create Albums for Similar Photo Groups

This creates Immich albums grouping similar photos together:

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://your-immich-server:2283 \
  --immich-api-key YOUR_API_KEY_HERE \
  --create-albums \
  --album-prefix "Similar-" \
  --mark-best-favorite
```

This will:
- Create albums named "Similar-0001", "Similar-0002", etc.
- Mark the best photo in each group as a favorite

#### Download and Organize Locally

Download photos from Immich and organize them into local folders:

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://your-immich-server:2283 \
  --immich-api-key YOUR_API_KEY_HERE \
  --output ~/Organized \
  --threshold 5
```

## All Command-Line Options

### Source Selection

```
--source-type {local,immich}
    Photo source type (default: local)

-s, --source PATH
    Source directory for local photos

-o, --output PATH
    Output directory for organized photos
```

### Immich Connection

```
--immich-url URL
    Immich server URL (e.g., http://immich:2283 or https://immich.example.com)

--immich-api-key KEY
    API key from Immich settings

--immich-album NAME
    Process only photos from a specific album

--immich-cache-dir PATH
    Directory to cache downloaded photos (default: ~/.cache/photo-organizer/immich)

--immich-cache-size MB
    Cache size in megabytes (default: 5000)

--no-verify-ssl
    Disable SSL certificate verification (for self-signed certificates)

--use-full-resolution
    Download full resolution images instead of thumbnails
```

### Processing Options

```
-t, --threshold N
    Similarity threshold (0-64, lower=stricter, default=5)
    - 0-3: Only near-duplicates
    - 4-6: Burst photos (recommended)
    - 7-10: Similar compositions

--time-window SECONDS
    Time window for grouping (default: 300 seconds)

--no-time-window
    Group by visual similarity only, ignore timestamps
```

### Immich Actions

```
--tag-only
    Only tag photos as duplicates, don't download

--create-albums
    Create Immich albums for each group

--album-prefix PREFIX
    Prefix for created albums (default: "Organized-")

--mark-best-favorite
    Mark the best photo in each group as favorite
```

## Usage Workflows

### Workflow 1: Find and Review Duplicates

1. **Scan and tag duplicates:**
```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://immich:2283 \
  --immich-api-key YOUR_KEY \
  --tag-only \
  --threshold 3
```

2. **Review in Immich:**
   - Open Immich web UI
   - Search for tag "photo-organizer-duplicate"
   - Review each group
   - Delete unwanted photos

3. **Re-scan if needed** with different threshold

### Workflow 2: Organize by Albums

1. **Create albums for similar photos:**
```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://immich:2283 \
  --immich-api-key YOUR_KEY \
  --create-albums \
  --mark-best-favorite \
  --threshold 5
```

2. **Review albums in Immich:**
   - Browse the "Similar-XXXX" albums
   - The best photo is marked as favorite
   - Delete unwanted photos from each album

### Workflow 3: Process Specific Album

If you have an album called "Vacation 2024":

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://immich:2283 \
  --immich-api-key YOUR_KEY \
  --immich-album "Vacation 2024" \
  --create-albums \
  --album-prefix "Vacation-Organized-"
```

### Workflow 4: Export to Local Storage

Download and organize photos locally:

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://immich:2283 \
  --immich-api-key YOUR_KEY \
  --output ~/Organized/Immich \
  --use-full-resolution \
  --threshold 5
```

This creates:
```
~/Organized/Immich/
├── group_0001/
│   ├── originals/
│   │   ├── photo1.jpg
│   │   ├── photo2.jpg
│   │   └── photo3.jpg
│   ├── metadata.txt
│   └── best_photo1.jpg
├── group_0002/
│   └── ...
```

## Configuration with Environment Variables

You can set environment variables to avoid typing credentials repeatedly:

```bash
# Add to ~/.bashrc or ~/.zshrc
export IMMICH_URL="http://immich:2283"
export IMMICH_API_KEY="your-api-key-here"
```

Then use a wrapper script:

```bash
#!/bin/bash
# save as immich-organize.sh

python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  "$@"
```

Usage:
```bash
chmod +x immich-organize.sh
./immich-organize.sh --tag-only --threshold 5
```

## Performance Considerations

### Thumbnail vs Full Resolution

**Use thumbnails (default):**
- Faster processing
- Less bandwidth
- Smaller cache
- Good enough for duplicate detection

```bash
# Thumbnails are used by default
python ../src/photo_organizer.py --source-type immich ...
```

**Use full resolution:**
- Better quality analysis
- Slower download
- More storage needed

```bash
python ../src/photo_organizer.py --source-type immich ... --use-full-resolution
```

### Cache Management

The cache stores downloaded photos to avoid re-downloading:

**Default cache location:**
- `~/.cache/photo-organizer/immich/`

**Adjust cache size:**
```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-cache-size 10000  # 10GB cache
  ...
```

**Clear cache manually:**
```bash
rm -rf ~/.cache/photo-organizer/immich/
```

### Processing Large Libraries

For libraries with thousands of photos:

1. **Process by album:**
```bash
for album in "2020" "2021" "2022" "2023" "2024"; do
  python ../src/photo_organizer.py \
    --source-type immich \
    --immich-url "$IMMICH_URL" \
    --immich-api-key "$IMMICH_API_KEY" \
    --immich-album "$album" \
    --create-albums \
    --album-prefix "${album}-Organized-"
done
```

2. **Use tag-only mode first** to avoid downloading
3. **Increase cache size** if downloading many photos

## Troubleshooting

### Connection Issues

**Error: Failed to connect to Immich server**

Check:
1. Immich URL is correct (include http:// or https://)
2. Immich server is running
3. Port is accessible (default: 2283)
4. API key is valid

Test connection:
```bash
curl -H "x-api-key: YOUR_KEY" http://immich:2283/api/server-info/ping
```

**SSL Certificate Errors**

For self-signed certificates:
```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --no-verify-ssl \
  ...
```

### API Errors

**Error: Invalid API key**
- Regenerate API key in Immich settings
- Check for extra spaces in the key

**Error: Album not found**
- Check album name spelling (case-sensitive)
- List albums to verify:
```python
from immich_client import ImmichClient
client = ImmichClient("http://immich:2283", "YOUR_KEY")
albums = client.get_albums()
for album in albums:
    print(album['albumName'])
```

### Performance Issues

**Slow processing:**
- Use thumbnails (default) instead of full resolution
- Increase `--threshold` to create fewer groups
- Process smaller batches using `--immich-album`

**Out of memory:**
- Reduce cache size: `--immich-cache-size 2000`
- Process fewer photos at once

## Security Best Practices

1. **Never commit API keys to git**
2. **Use environment variables** for credentials
3. **Rotate API keys** periodically
4. **Use HTTPS** for remote Immich servers
5. **Verify SSL certificates** (disable only for trusted local servers)

## Integration with Immich Workflows

### Workflow: Monthly Cleanup

```bash
#!/bin/bash
# monthly-cleanup.sh

# Tag potential duplicates
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --tag-only \
  --threshold 3

echo "Review tagged photos in Immich and delete duplicates"
echo "Then run this script again to organize remaining photos"
```

### Workflow: Automatic Album Creation

```bash
#!/bin/bash
# create-organized-albums.sh

python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --create-albums \
  --mark-best-favorite \
  --album-prefix "Auto-Organized-" \
  --threshold 5 \
  --time-window 300
```

## Feature Comparison

| Feature | Local Mode | Immich Mode |
|---------|-----------|-------------|
| Group similar photos | ✅ | ✅ |
| Face quality detection | ✅ | ✅ |
| Download photos | N/A | ✅ |
| Tag photos | ❌ | ✅ |
| Create albums | ❌ | ✅ |
| Mark favorites | ❌ | ✅ |
| Preserve originals | ✅ | ✅ |
| Metadata extraction | ✅ | ✅ |

## Next Steps

1. Try the tag-only mode first to understand how grouping works
2. Adjust threshold based on your needs
3. Use album creation for easy review
4. Integrate into your photo management workflow

## Getting Help

- Check [README.md](README.md) for general usage
- See [IMMICH_INTERGRATION.md](IMMICH_INTERGRATION.md) for technical details
- Report issues on GitHub
