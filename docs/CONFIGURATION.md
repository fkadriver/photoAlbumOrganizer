# Configuration Guide

## Similarity Threshold

The `--threshold` (or `-t`) parameter controls how visually similar photos must be to be grouped together. It measures Hamming distance between perceptual hashes — lower means stricter.

| Threshold | Use Case | Description |
|-----------|----------|-------------|
| **0–3** | Duplicates | Only near-identical photos (different exposures of the exact same shot) |
| **4–6** | Burst photos | Recommended for typical burst sequences (default: **5**) |
| **7–10** | Similar scenes | Groups photos of the same subject from different angles |
| **11+** | Very loose | May group unrelated but visually similar photos |

```bash
# Near-duplicate detection (very strict)
./photo_organizer.py -s ~/Photos -o ~/Organized -t 3

# Burst photos — default, recommended starting point
./photo_organizer.py -s ~/Photos -o ~/Organized -t 5

# Similar compositions (same scene, different angles)
./photo_organizer.py -s ~/Photos -o ~/Organized -t 8
```

**Tip:** When in doubt, start strict (lower number) and run the web viewer. If groups are too small or miss related photos, increase the threshold and re-run.

---

## Time Window

The `--time-window` parameter controls how far apart in time two photos can be while still being considered for grouping. Photos outside the window are never grouped, regardless of visual similarity.

| Window | Use Case |
|--------|----------|
| **60s** | High-speed bursts, sports photography |
| **300s** (default) | Standard burst photography, family photos |
| **600s** | Event photography, multiple compositions of the same scene |
| **0** | Disable — group purely by visual similarity, ignore timestamps |

```bash
# High-speed burst — group only photos within 1 minute
./photo_organizer.py -s ~/Photos -o ~/Organized --time-window 60

# Standard burst — default
./photo_organizer.py -s ~/Photos -o ~/Organized --time-window 300

# Duplicate detection across entire library (ignore timestamps)
./photo_organizer.py -s ~/Photos -o ~/Organized --time-window 0 -t 3
```

**Note:** `--time-window 0` is most useful for finding exact duplicates spread across your library (e.g., photos copied to multiple folders). Pair with a strict threshold (`-t 3`) to avoid false positives.

---

## Minimum Group Size

`--min-group-size N` (default: 3, minimum: 2) — groups with fewer photos than this are discarded.

```bash
# Include pairs (two similar photos)
./photo_organizer.py -s ~/Photos -o ~/Organized --min-group-size 2

# Only process groups of 4 or more (strict burst detection)
./photo_organizer.py -s ~/Photos -o ~/Organized --min-group-size 4
```

---

## Choosing the Right Options

**Burst photos from the same moment:**
```bash
./photo_organizer.py -s ~/Photos -o ~/Organized -t 5
# Default settings work well
```

**Photos with incorrect timestamps:**
```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --time-window 0
# Ignores timestamps, groups purely by visual similarity
```

**Finding exact duplicates across your entire library:**
```bash
./photo_organizer.py -s ~/Photos -o ~/Organized -t 3 --time-window 0
# Very strict matching, no time restrictions
```

**Similar compositions (different angles of the same scene):**
```bash
./photo_organizer.py -s ~/Photos -o ~/Organized -t 8 --time-window 1800
# Looser matching, 30-minute window
```

**Testing settings on a subset first:**
```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --limit 200 --dry-run
# Process first 200 photos without writing anything
```

---

## Immich-Specific Configuration

### API Key

Store your Immich API key in `~/.config/photo-organizer/immich.conf` (permissions 600):

```bash
mkdir -p ~/.config/photo-organizer
echo 'IMMICH_API_KEY="your-key-here"' > ~/.config/photo-organizer/immich.conf
echo 'IMMICH_URL="https://your-immich-url"' >> ~/.config/photo-organizer/immich.conf
chmod 600 ~/.config/photo-organizer/immich.conf
```

Or use environment variables:
```bash
export IMMICH_URL="https://your-immich-url"
export IMMICH_API_KEY="your-key-here"
```

### Thumbnail vs Full Resolution

```bash
# Use thumbnails (default) — 10-50x faster, good enough for duplicate detection
scripts/immich.sh tag-only

# Use full resolution — better quality analysis, slower download
./photo_organizer.py --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --use-full-resolution --output ~/Organized
```

### Cache Management

Downloaded photos are cached at `~/.cache/photo-organizer/immich/`.

```bash
# Adjust cache size (default: 5000 MB)
./photo_organizer.py --source-type immich ... --immich-cache-size 10000

# Clear cache
rm -rf ~/.cache/photo-organizer/immich/
```

---

## Saving and Reloading Settings

In interactive mode (`-i`), press `s` at the summary screen to save your configuration to `.photo_organizer_settings.json`. The next run will offer to reload it, skipping the full walkthrough. API keys are never saved to this file.

```bash
# Run with saved settings (non-interactive)
./photo_organizer.py -r

# Run with saved settings from a specific file
./photo_organizer.py -r /path/to/my-settings.json
```

---

## See Also

- [IMMICH.md](IMMICH.md) — Full Immich integration guide
- [FACE_BACKENDS.md](FACE_BACKENDS.md) — Face detection backend configuration
- [GPU_ACCELERATION.md](GPU_ACCELERATION.md) — GPU setup and configuration
