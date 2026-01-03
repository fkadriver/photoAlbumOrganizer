# Quick Start Guide - Immich Integration

## Installation

```bash
# Install the new dependency
pip install requests
```

## Get Your Immich API Key

1. Open your Immich web interface
2. Navigate to: **Settings → Account Settings → API Keys**
3. Click **"New API Key"**
4. Give it a name (e.g., "Photo Organizer")
5. Copy the API key (you'll need it for commands below)

## Test Connection

```bash
# Test that everything works
python ../scripts/test_immich_connection.py
```

When prompted, enter:
- Your Immich URL (e.g., `http://immich:2283` or `https://immich.example.com`)
- Your API key

## Three Ways to Use

### 1. Tag Duplicates (Fastest, Safest)

This scans your Immich library and tags similar photos without downloading anything.

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://YOUR_IMMICH:2283 \
  --immich-api-key YOUR_API_KEY \
  --tag-only \
  --threshold 5
```

**Then:**
- Open Immich web UI
- Search for tag: `photo-organizer-duplicate`
- Review and delete unwanted photos

### 2. Create Albums (Organized, Easy Review)

This creates Immich albums grouping similar photos together.

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://YOUR_IMMICH:2283 \
  --immich-api-key YOUR_API_KEY \
  --create-albums \
  --mark-best-favorite \
  --threshold 5
```

**Result:**
- Albums named `Organized-0001`, `Organized-0002`, etc.
- Best photo in each group marked as favorite
- Easy to review in Immich

### 3. Download & Organize (Traditional Method)

This downloads from Immich and creates organized local folders.

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://YOUR_IMMICH:2283 \
  --immich-api-key YOUR_API_KEY \
  --output ~/Organized \
  --threshold 5
```

**Result:**
```
~/Organized/
├── group_0001/
│   ├── originals/
│   ├── metadata.txt
│   └── best_photo.jpg
├── group_0002/
│   └── ...
```

## Adjust the Threshold

The `--threshold` parameter controls how similar photos must be:

- `--threshold 3` - Very strict (only near-duplicates)
- `--threshold 5` - **Recommended** (burst photos)
- `--threshold 8` - Looser (similar compositions)

## Process Specific Album

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://YOUR_IMMICH:2283 \
  --immich-api-key YOUR_API_KEY \
  --immich-album "Vacation 2024" \
  --create-albums
```

## Using Environment Variables

To avoid typing credentials repeatedly:

```bash
# Add to ~/.bashrc or ~/.zshrc
export IMMICH_URL="http://immich:2283"
export IMMICH_API_KEY="your-api-key-here"

# Then use:
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --tag-only
```

## Troubleshooting

### Connection Failed

```bash
# Test with curl
curl -H "x-api-key: YOUR_KEY" http://immich:2283/api/server-info/ping
```

Should return: `{"res":"pong"}`

### SSL Certificate Error (Self-Signed Certificate)

Add `--no-verify-ssl`:

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url https://YOUR_IMMICH:2283 \
  --immich-api-key YOUR_API_KEY \
  --no-verify-ssl \
  --tag-only
```

### Need Better Quality Analysis

Use full resolution instead of thumbnails:

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://YOUR_IMMICH:2283 \
  --immich-api-key YOUR_API_KEY \
  --use-full-resolution \
  --output ~/Organized
```

## Next Steps

- Read [IMMICH_USAGE.md](IMMICH_USAGE.md) for detailed usage
- Check [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) for technical details
- Review [IMMICH_INTERGRATION.md](IMMICH_INTERGRATION.md) for architecture

## Local Photos (Still Works!)

The original local photo organization still works:

```bash
python ../src/photo_organizer.py -s ~/Photos -o ~/Organized -t 5
```

All the Immich features are additions - nothing was removed!

## Summary

**Start with tag-only mode** - it's the safest way to see what will be grouped:

```bash
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url http://YOUR_IMMICH:2283 \
  --immich-api-key YOUR_API_KEY \
  --tag-only \
  --threshold 5
```

Then review the results in Immich and adjust the threshold if needed. Once you're happy with the grouping, try the other modes!
