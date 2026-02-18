# Immich Integration Guide

Complete guide for using the Photo Album Organizer with [Immich](https://immich.app/) - the self-hosted photo and video management solution.

## Quick Start

### 1. Get Your Immich API Key

1. Open your Immich web interface
2. Go to **Settings** → **Account Settings** → **API Keys**
3. Click **New API Key**
4. Give it a name (e.g., "Photo Organizer")
5. Copy the generated API key

**Security:** Your API key is stored securely in `~/.config/photo-organizer/immich.conf` with permissions 600 (owner read/write only).

### 2. Configure the Wrapper Script

The `scripts/immich.sh` wrapper is the easiest way to use the photo organizer with Immich.

Edit line 12 in [immich.sh](../scripts/immich.sh) to set your Immich URL:
```bash
IMMICH_URL="${IMMICH_URL:-https://your-immich-url.ts.net}"
```

Or set it via environment variable:
```bash
export IMMICH_URL="https://your-immich-url.ts.net"
```

### 3. Test Connection

```bash
scripts/immich.sh test
```

This verifies your API key and connection to Immich.

### 4. Tag Duplicates (Recommended First Step)

```bash
scripts/immich.sh tag-only
# or just:
scripts/immich.sh
```

This tags similar photos in Immich with "photo-organizer-duplicate" - you can review and delete them in the Immich web UI.

## Using the immich.sh Wrapper Script

The wrapper script provides convenient commands for common Immich operations. This is the **recommended** way to use the organizer.

### Available Modes

#### Tag Mode (Safest - Default)

```bash
scripts/immich.sh tag-only
scripts/immich.sh tag
scripts/immich.sh  # tag-only is default
```

Tags duplicate photos without downloading or modifying. Perfect for:
- Initial exploration of duplicates
- Safe review before deletion
- Non-destructive duplicate detection

**What it does:**
- Scans your Immich library
- Groups similar photos
- Tags them with "photo-organizer-duplicate"
- You review and delete manually in Immich UI

#### Create Albums Mode

```bash
scripts/immich.sh create-albums
scripts/immich.sh albums
```

Creates Immich albums grouping similar photos together:
- Creates albums "Organized-0001", "Organized-0002", etc.
- Marks the best photo in each group as a favorite
- Perfect for organizing photo bursts

#### Download Mode

```bash
scripts/immich.sh download [OUTPUT_DIR]
# Default output: ~/Organized/Immich
```

Downloads photos from Immich and creates local organized folders:
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

#### Cleanup Mode

```bash
# Dry run first (safe - shows what would be deleted)
scripts/immich.sh cleanup

# Actually delete albums with "Organized-" prefix
scripts/immich.sh cleanup "Organized-" no

# Delete albums with custom prefix
scripts/immich.sh cleanup "MyPrefix-" no
```

Removes albums created by the organizer. Always run dry run first!

**Important:**
- Deletes only albums, not photos
- Photos remain in your Immich library
- Always shows dry run output first

#### Process Specific Album

```bash
scripts/immich.sh album "Album Name" [mode]
```

Modes: `tag`, `create-albums`, or `download`

**Examples:**
```bash
# Tag duplicates in vacation photos
scripts/immich.sh album "Vacation 2024" tag

# Create sub-albums from family photos
scripts/immich.sh album "Family Photos 2024" create-albums

# Download specific album
scripts/immich.sh album "Best Photos" download ~/Archive/BestPhotos
```

#### Test Connection

```bash
scripts/immich.sh test
```

Verifies connection to Immich server and API key validity.

#### Show Help

```bash
scripts/immich.sh help
```

### Advanced Options

The wrapper script supports command-line options for advanced usage:

```bash
# Disable time window check, group by visual similarity only
scripts/immich.sh --ignore-timestamp tag-only

# Enable HDR merging for bracketed exposures
scripts/immich.sh --enable-hdr create-albums

# Enable automatic face swapping to fix closed eyes
scripts/immich.sh --enable-face-swap create-albums

# Combine all advanced features
scripts/immich.sh --ignore-timestamp --enable-hdr --enable-face-swap create-albums

# Resume from previous interrupted run (auto-detected if progress file exists)
scripts/immich.sh --resume create-albums

# Force fresh start without prompting
scripts/immich.sh --force-fresh create-albums

# Limit processing to first N photos (for testing)
scripts/immich.sh --limit 100 tag-only

# Combine options
scripts/immich.sh --ignore-timestamp --limit 50 tag-only
```

**Command-Line Options:**
- `--ignore-timestamp` - Disable time window check, group by visual similarity only
- `--enable-hdr` - Merge bracketed exposures into HDR images (requires download mode)
- `--enable-face-swap` - Fix closed eyes by swapping faces from other photos (requires download mode)
- `--resume` - Resume from previous interrupted run (auto-detected by default)
- `--force-fresh` - Force fresh start, delete any existing progress without prompting
- `--limit N` - Limit processing to first N photos (for testing)

**Environment Variables (for overriding defaults):**
- `IMMICH_URL` - Override Immich server URL
- `IMMICH_API_KEY` - Override API key from config file

### Configuration

#### API Key Storage

Your API key is stored in:
```
~/.config/photo-organizer/immich.conf
```

**Security:**
- File permissions: 600 (owner read/write only)
- Not committed to git
- Can also use environment variable: `export IMMICH_API_KEY="your-key"`

#### Change Immich URL

Edit line 12 in [immich.sh](../scripts/immich.sh):
```bash
IMMICH_URL="${IMMICH_URL:-https://your-immich-url.ts.net}"
```

Or set environment variable:
```bash
export IMMICH_URL="https://your-immich-url.ts.net"
scripts/immich.sh tag-only
```

#### Adjust Similarity Threshold

Edit line 46 in [immich.sh](../scripts/immich.sh):
```bash
--threshold 5    # Change to 3 (stricter) or 8 (looser)
```

**Threshold guide:**
- 3: Very strict (only near-duplicates)
- 5: Default (burst photos)
- 8: Looser (similar compositions)

## Common Workflows

### Workflow 1: Tag and Review (Safest)

```bash
# 1. Test connection
scripts/immich.sh test

# 2. Tag duplicates to review
scripts/immich.sh tag-only

# 3. Review in Immich web UI
#    - Search for tag "photo-organizer-duplicate"
#    - Manually delete unwanted photos

# 4. If satisfied, create albums
scripts/immich.sh create-albums
```

### Workflow 2: Organize into Albums

```bash
# Create organized albums from similar photos
scripts/immich.sh create-albums

# Review created albums in Immich
# Delete unwanted photos from each album
# Keep albums or merge as needed
```

**Result:**
- Creates "Organized-0001", "Organized-0002", etc.
- Best photos marked as favorites
- Easy to review and manage

### Workflow 3: Process Specific Album

```bash
# Create organized albums from "Family Photos 2024"
scripts/immich.sh album "Family Photos 2024" create-albums

# Result: Creates "Organized-0001", "Organized-0002", etc.
# with best photos marked as favorites
```

### Workflow 4: Download to Local Archive

```bash
# Download entire library organized
scripts/immich.sh download ~/Archive/Immich/$(date +%Y-%m-%d)

# Download specific album
scripts/immich.sh album "Best Photos" download ~/Archive/BestPhotos
```

### Workflow 5: Cleanup After Testing

```bash
# Step 1: Dry run (see what would be deleted)
scripts/immich.sh cleanup "Organized-" yes

# Output shows:
# - Number of albums found
# - List of album names and asset counts
# - Confirmation that nothing was deleted

# Step 2: Actually delete if satisfied
scripts/immich.sh cleanup "Organized-" no
```

**Use cases:**
- Testing different thresholds
- Re-organizing with different settings
- Removing test albums

### Workflow 6: Batch Processing

```bash
# Process multiple albums
for album in "2020" "2021" "2022" "2023" "2024"; do
    echo "Processing $album..."
    scripts/immich.sh album "$album" create-albums
done
```

## Direct Python Usage (Advanced)

For advanced users who need more control, you can call the Python script directly.

### Basic Usage

#### Tag Potential Duplicates

```bash
python src/photo_organizer.py \
  --source-type immich \
  --immich-url http://your-immich-server:2283 \
  --immich-api-key YOUR_API_KEY_HERE \
  --tag-only \
  --threshold 5
```

After running, open Immich web UI and filter by tag "photo-organizer-duplicate".

#### Create Albums for Similar Photo Groups

```bash
python src/photo_organizer.py \
  --source-type immich \
  --immich-url http://your-immich-server:2283 \
  --immich-api-key YOUR_API_KEY_HERE \
  --create-albums \
  --album-prefix "Similar-" \
  --mark-best-favorite
```

#### Download and Organize Locally

```bash
python src/photo_organizer.py \
  --source-type immich \
  --immich-url http://your-immich-server:2283 \
  --immich-api-key YOUR_API_KEY_HERE \
  --output ~/Organized \
  --threshold 5
```

### All Command-Line Options

#### Source Selection

```
--source-type {local,immich}
    Photo source type (default: local)

-s, --source PATH
    Source directory for local photos

-o, --output PATH
    Output directory for organized photos
```

#### Immich Connection

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

#### Processing Options

```
-t, --threshold N
    Similarity threshold (0-64, lower=stricter, default=5)
    - 0-3: Only near-duplicates
    - 4-6: Burst photos (recommended)
    - 7-10: Similar compositions

--time-window SECONDS
    Time window for grouping (default: 300 seconds, use 0 to disable)

--limit N
    Limit processing to first N photos (for testing)

--resume
    Resume from previous interrupted run (auto-detected by default)

--force-fresh
    Force fresh start, delete any existing progress without prompting

--state-file PATH
    Custom state file location for resume capability
```

#### Immich Actions

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

#### Advanced Image Processing

```
--enable-hdr
    Enable HDR merging for bracketed exposure shots
    - Automatically detects exposure brackets from EXIF
    - Creates hdr_merged.jpg in group directory
    - Requires download mode (automatically enabled)

--hdr-gamma FLOAT
    HDR tone mapping gamma value (default: 2.2)

--enable-face-swap
    Enable automatic face swapping to fix closed eyes
    - Detects faces with closed eyes using Eye Aspect Ratio
    - Swaps with same person from other photos in the group
    - Creates face_swapped.jpg in group directory
    - Requires download mode and face_recognition library

--swap-closed-eyes
    Swap faces with closed eyes (default: True)
```

### Advanced Python Examples

#### Process Only Recent Photos

```bash
# Create an album in Immich with recent photos, then:
python src/photo_organizer.py \
  --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --immich-album "Recent" \
  --tag-only
```

#### Strict Duplicate Detection

```bash
python src/photo_organizer.py \
  --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --tag-only \
  --threshold 3 \
  --time-window 0
```

#### Test with Limited Photos

```bash
python src/photo_organizer.py \
  --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --tag-only \
  --limit 100
```

#### Resume Interrupted Run

```bash
# Start processing
python src/photo_organizer.py \
  --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --create-albums \
  --resume

# If interrupted, run the same command again
# It will resume from where it left off
```

## Configuration with Environment Variables

You can set environment variables to avoid typing credentials repeatedly:

```bash
# Add to ~/.bashrc or ~/.zshrc
export IMMICH_URL="http://immich:2283"
export IMMICH_API_KEY="your-api-key-here"
```

Then use simplified commands:
```bash
python src/photo_organizer.py \
  --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --tag-only
```

## Performance Considerations

### Thumbnail vs Full Resolution

**Use thumbnails (default):**
- Faster processing (10-50x faster)
- Less bandwidth usage
- Smaller cache requirements
- Good enough for duplicate detection

```bash
# Thumbnails are used by default
scripts/immich.sh tag-only
```

**Use full resolution:**
- Better quality analysis
- Slower download
- More storage needed

```bash
# Edit immich.sh and add --use-full-resolution
# Or use Python directly:
python src/photo_organizer.py \
  --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --use-full-resolution \
  --output ~/Organized
```

### Cache Management

The cache stores downloaded photos to avoid re-downloading:

**Default cache location:**
- `~/.cache/photo-organizer/immich/`

**Adjust cache size:**
```bash
python src/photo_organizer.py \
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

1. **Process by album** to handle in chunks
2. **Use tag-only mode first** to avoid downloading
3. **Increase cache size** if downloading many photos
4. **Use test mode** to verify settings first

```bash
# Test with 100 photos first
scripts/immich.sh --limit 100 tag-only

# Then process by year
for year in 2020 2021 2022 2023 2024; do
  scripts/immich.sh album "$year" create-albums
done
```

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
# Edit immich.sh and add --no-verify-ssl
# Or use Python directly:
python src/photo_organizer.py \
  --source-type immich \
  --no-verify-ssl \
  ...
```

### API Errors

**Error: Invalid API key**
- Regenerate API key in Immich settings
- Check for extra spaces in the key
- Verify config file permissions (should be 600)

```bash
# Check config file
cat ~/.config/photo-organizer/immich.conf
chmod 600 ~/.config/photo-organizer/immich.conf
```

**Error: Album not found**
- Check album name spelling (case-sensitive)
- Verify album exists in Immich

**Error: Permission denied**
- Verify API key has required permissions
- See [IMMICH_INTEGRATION.md](IMMICH_INTEGRATION.md) for permission requirements

### Script Not Executable

```bash
chmod +x scripts/immich.sh
```

### Performance Issues

**Slow processing:**
- Use thumbnails (default) instead of full resolution
- Increase `--threshold` to create fewer groups
- Process smaller batches using `--immich-album`

**Out of memory:**
- Reduce cache size: `--immich-cache-size 2000`
- Process fewer photos at once using `--limit`

### API Key Not Found

```bash
# Check if config exists
cat ~/.config/photo-organizer/immich.conf

# Recreate if needed
echo 'IMMICH_API_KEY="your-key-here"' > ~/.config/photo-organizer/immich.conf
chmod 600 ~/.config/photo-organizer/immich.conf
```

## Security Best Practices

1. **Never commit API keys to git**
2. **Use environment variables** for credentials in scripts
3. **Rotate API keys** periodically
4. **Use HTTPS** for remote Immich servers
5. **Verify SSL certificates** (disable only for trusted local servers)
6. **Set config file permissions** to 600 (owner read/write only)

## Feature Comparison

| Feature | Local Mode | Immich Mode |
|---------|-----------|-------------|
| Group similar photos | ✅ | ✅ |
| Face quality detection | ✅ | ✅ |
| HDR merging | ✅ | ✅ |
| Face swapping | ✅ | ✅ |
| Download photos | N/A | ✅ |
| Tag photos | ❌ | ✅ |
| Create albums | ❌ | ✅ |
| Mark favorites | ❌ | ✅ |
| Preserve originals | ✅ | ✅ |
| Metadata extraction | ✅ | ✅ |
| Resume capability | ✅ | ✅ |
| Auto-resume detection | ✅ | ✅ |
| Cleanup albums | ❌ | ✅ |
| Web viewer | ❌ | ✅ |
| Undo/cleanup changes | ❌ | ✅ |

## Web Viewer

After running the organizer, launch the built-in web viewer to review results visually:

```bash
# Recommended: lifecycle-managed background viewer (auto-stops when you leave the directory)
scripts/viewer start          # Start on port 8080 (loads Immich config automatically)
scripts/viewer start 9090     # Custom port
scripts/viewer status         # Check if running
scripts/viewer stop            # Manual stop

# Or from the direnv prompt: choose [v] Web viewer

# Or launch directly (foreground, no auto-stop)
./photo_organizer.py --web-viewer \
  --immich-url https://your-immich-url \
  --immich-api-key YOUR_KEY
```

The `scripts/viewer` script runs the server in the background and spawns a watchdog that polls every 3 seconds. When your shell leaves the project directory (or the terminal closes), the watchdog kills the viewer and cleans up PID files automatically. Immich credentials are loaded from `~/.config/photo-organizer/immich.conf` or environment variables.

The viewer proxies thumbnails and previews from Immich (no CORS issues, API key stays server-side). You can:
- Browse all groups with photo thumbnails
- Switch between different report runs via the dropdown
- Click to expand groups and compare EXIF metadata
- View full-resolution previews in a lightbox
- Change the "best" photo for any group
- Bulk archive, delete, or discard changes for selected groups

In interactive mode (`-i`), the web viewer is the **default action** when a previous `processing_report.json` exists. With direnv, choosing `[v]` at the prompt starts the viewer with auto-stop.

## Cleanup / Undo

To undo changes made by the organizer:

```bash
./photo_organizer.py --cleanup \
  --immich-url https://your-immich-url \
  --immich-api-key YOUR_KEY
```

Or press `[u]` at the interactive mode summary screen. Options:
1. **Delete albums** created by the organizer (by prefix)
2. **Remove tags** under `photo-organizer/*`
3. **Unfavorite** photos tagged as "best"
4. **Unarchive** photos tagged as "non-best"
5. **Full cleanup** — all of the above in sequence

Each operation shows a dry-run preview with counts before confirming.

## See Also

- [IMMICH_INTEGRATION.md](IMMICH_INTEGRATION.md) - Technical implementation details
- [README.md](README.md) - Main project documentation
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [Immich Documentation](https://immich.app/docs) - Official Immich docs
- [Immich API](https://immich.app/docs/api) - API reference

## Summary

The immich.sh wrapper script makes it easy to use the photo organizer with Immich:

✅ **Secure** - API key stored in protected config file
✅ **Simple** - Easy commands for common tasks
✅ **Flexible** - Multiple modes and options
✅ **Safe** - Default mode (tag-only) doesn't modify photos
✅ **Powerful** - Full Python API available for advanced usage

**Quick Start:**
1. `scripts/immich.sh test` - Test connection
2. `scripts/immich.sh tag-only` - Find duplicates safely
3. `scripts/viewer start` - Review results in the web viewer (auto-stops on directory exit)
4. `scripts/immich.sh create-albums` - Organize into albums
5. `./photo_organizer.py --cleanup` - Undo changes if needed
