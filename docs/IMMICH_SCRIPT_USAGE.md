# immich.sh Usage Guide

The [immich.sh](immich.sh) script is a convenient wrapper for running the photo organizer with your Immich instance.

## Quick Start

The script is now configured with your Immich URL and API key is stored securely.

### Test Connection

```bash
../scripts/immich.sh test
```

### Tag Duplicates (Recommended First Step)

```bash
../scripts/immich.sh tag-only
# or just:
../scripts/immich.sh
```

This tags similar photos in Immich with "photo-organizer-duplicate" - you can review and delete them in the Immich web UI.

### Create Albums

```bash
../scripts/immich.sh create-albums
```

This creates albums "Organized-0001", "Organized-0002", etc. with similar photos grouped together and marks the best photo in each group as a favorite.

### Download and Organize Locally

```bash
../scripts/immich.sh download ~/Photos/Organized
```

Downloads photos from Immich and creates local organized folders.

### Cleanup Created Albums

```bash
# Dry run first (safe - shows what would be deleted)
../scripts/immich.sh cleanup

# Actually delete albums with "Organized-" prefix
../scripts/immich.sh cleanup "Organized-" no

# Delete albums with custom prefix
../scripts/immich.sh cleanup "MyPrefix-" no
```

Removes albums created by the organizer. Always run dry run first!

## All Modes

### Basic Modes

```bash
# Tag duplicates (default, safest)
../scripts/immich.sh tag-only
../scripts/immich.sh tag

# Create albums from groups
../scripts/immich.sh create-albums
../scripts/immich.sh albums

# Download and organize locally
../scripts/immich.sh download [OUTPUT_DIR]

# Cleanup created albums
../scripts/immich.sh cleanup [PREFIX] [yes|no]
# Default: cleanup "Organized-" yes (dry run)

# Test connection
../scripts/immich.sh test

# Show help
../scripts/immich.sh help
```

### Process Specific Album

```bash
# Tag duplicates in specific album
../scripts/immich.sh album "Vacation 2024" tag

# Create sub-albums from album
../scripts/immich.sh album "Vacation 2024" create-albums

# Download specific album
../scripts/immich.sh album "Vacation 2024" download ~/Photos/Vacation2024
```

## Configuration

### API Key Storage

Your API key is stored securely in:
```
~/.config/photo-organizer/immich.conf
```

**Security:**
- File permissions: 600 (owner read/write only)
- Not committed to git
- Can also use environment variable: `export IMMICH_API_KEY="your-key"`

### Change Immich URL

Edit line 12 in [immich.sh](immich.sh):
```bash
IMMICH_URL="${IMMICH_URL:-https://your-immich-url.ts.net}"
```

Or set environment variable:
```bash
export IMMICH_URL="https://your-immich-url.ts.net"
../scripts/immich.sh tag-only
```

### Adjust Similarity Threshold

Edit line 46 in [immich.sh](immich.sh):
```bash
--threshold 5    # Change to 3 (stricter) or 8 (looser)
```

**Threshold guide:**
- 3: Very strict (only near-duplicates)
- 5: Default (burst photos)
- 8: Looser (similar compositions)

## Examples

### Safe First Run

```bash
# 1. Test connection
../scripts/immich.sh test

# 2. Tag duplicates to review
../scripts/immich.sh tag-only

# 3. Review in Immich web UI
#    - Search for tag "photo-organizer-duplicate"
#    - Manually delete unwanted photos

# 4. If satisfied, create albums
../scripts/immich.sh create-albums
```

### Process Family Photos Album

```bash
# Create organized albums from "Family Photos 2024"
../scripts/immich.sh album "Family Photos 2024" create-albums

# Result: Creates "Organized-0001", "Organized-0002", etc.
# with best photos marked as favorites
```

### Batch Processing

```bash
# Process multiple albums
for album in "2020" "2021" "2022" "2023" "2024"; do
    echo "Processing $album..."
    ../scripts/immich.sh album "$album" create-albums
done
```

### Download to Local Archive

```bash
# Download entire library organized
../scripts/immich.sh download ~/Archive/Immich/$(date +%Y-%m-%d)

# Download specific album
../scripts/immich.sh album "Best Photos" download ~/Archive/BestPhotos
```

## Workflow Recommendations

### Workflow 1: Tag and Review

```bash
../scripts/immich.sh tag-only
# Review in Immich web UI
# Delete unwanted duplicates
# Done!
```

### Workflow 2: Organized Albums

```bash
../scripts/immich.sh create-albums
# Review created albums in Immich
# Delete unwanted photos from each album
# Keep albums or merge as needed
```

### Workflow 3: Local Backup

```bash
../scripts/immich.sh download ~/Backups/Immich-Organized
# Review local folders
# Best photos already separated
# Can upload back to Immich if needed
```

## Troubleshooting

### API Key Not Found

```bash
# Check if config exists
cat ~/.config/photo-organizer/immich.conf

# Recreate if needed
echo 'IMMICH_API_KEY="your-key-here"' > ~/.config/photo-organizer/immich.conf
chmod 600 ~/.config/photo-organizer/immich.conf
```

### Connection Failed

```bash
# Test connection
../scripts/immich.sh test

# Check URL is correct
echo $IMMICH_URL

# Try with curl
curl -H "x-api-key: YOUR_KEY" https://immich.warthog-royal.ts.net/api/server-info/version
```

### Script Not Executable

```bash
chmod +x immich.sh
```

### Wrong Python Command

The script uses `python` - if your system uses `python3`, edit line 54, 60, 70, etc.:
```bash
python3 photo_organizer.py ...
```

## Advanced Usage

### Custom Threshold Per Run

Edit the script temporarily or create a copy:
```bash
cp immich.sh immich-strict.sh
# Edit immich-strict.sh line 46: --threshold 3
./immich-strict.sh tag-only
```

### Process Only Recent Photos

The script processes all photos by default. To filter by date, you'd need to:
1. Create an album in Immich with recent photos
2. Use: `../scripts/immich.sh album "Recent" tag-only`

### Dry Run

There's no built-in dry run, but you can:
1. Create a test album with a few photos
2. Run: `../scripts/immich.sh album "Test" tag-only`
3. Verify results before processing entire library

## Script Maintenance

### Update Immich URL

```bash
# Edit line 12 in immich.sh
IMMICH_URL="${IMMICH_URL:-https://new-url.ts.net}"
```

### Update API Key

```bash
# Update config file
echo 'IMMICH_API_KEY="new-key"' > ~/.config/photo-organizer/immich.conf
chmod 600 ~/.config/photo-organizer/immich.conf
```

### Add New Mode

Edit the `case "$MODE" in` section (line 50) in [immich.sh](immich.sh) to add custom modes.

## See Also

- [IMMICH_USAGE.md](IMMICH_USAGE.md) - Detailed Immich integration guide
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [README.md](README.md) - Main project documentation

## Summary

The [immich.sh](immich.sh) script makes it easy to use the photo organizer with Immich:

✅ **Secure** - API key stored in protected config file
✅ **Simple** - Easy commands for common tasks
✅ **Flexible** - Multiple modes and options
✅ **Safe** - Default mode (tag-only) doesn't modify photos

Start with: `../scripts/immich.sh test` then `../scripts/immich.sh tag-only`
