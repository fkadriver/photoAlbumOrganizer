# Performance Guide

## Processing Speeds (Approximate)

| Collection Size | Estimated Time |
|----------------|----------------|
| < 1,000 photos | 5–10 minutes |
| 1,000–10,000 photos | 30–60 minutes |
| 10,000–50,000 photos | 2–4 hours |
| 128 GB+ library | 4–8 hours |

**Factors affecting speed:**
- CPU speed and core count
- Storage type (SSD vs HDD)
- Image resolution and format
- Number of faces in photos
- Face detection backend chosen

---

## Multi-Threading

Use `--threads N` to parallelize hash computation:

```bash
# Use 4 threads (good balance for most systems)
./photo_organizer.py -s ~/Photos -o ~/Organized --threads 4

# Use 8 threads (for fast CPUs with many cores)
./photo_organizer.py -s ~/Photos -o ~/Organized --threads 8

# Single-threaded (for debugging or minimal memory)
./photo_organizer.py -s ~/Photos -o ~/Organized --threads 1
```

Default is 2 threads. Increasing threads primarily speeds up the hashing phase.

---

## Memory Usage

| Scenario | Typical RAM |
|----------|------------|
| Small collection | 2–4 GB |
| Large collection | 4–8 GB |
| Peak (hash computation + face detection) | up to 8 GB |

---

## Optimization Tips

1. **Use SSD** for both source and output directories
2. **Process in batches** by year or event for very large libraries:

```bash
for year in 2020 2021 2022 2023 2024; do
  ./photo_organizer.py -s ~/Photos/$year -o ~/Organized/$year
done
```

3. **Start with a subset** to tune parameters before a full run:

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized --limit 200 --dry-run
```

4. **Use resume** if you need to run in multiple sessions:

```bash
# First run
./photo_organizer.py -s ~/Photos -o ~/Organized

# If interrupted, resume (automatically detected):
./photo_organizer.py -s ~/Photos -o ~/Organized
# → Prompts to resume or start fresh
```

5. **Tag-only mode** for Immich is much faster since no photos are downloaded:

```bash
scripts/immich.sh tag-only
```

---

## Immich-Specific Performance

### Thumbnail vs Full Resolution

Thumbnails are used by default for Immich source — 10–50× faster than full resolution and adequate for duplicate detection.

```bash
# Thumbnails (default) — fast, good for grouping
scripts/immich.sh tag-only

# Full resolution — slower, better for quality-sensitive face analysis
./photo_organizer.py --source-type immich \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" \
  --use-full-resolution \
  --output ~/Organized
```

### Concurrent Prefetching

The Immich client uses concurrent photo prefetching automatically. Adjust cache size if you have disk space:

```bash
./photo_organizer.py --source-type immich ... --immich-cache-size 10000  # 10 GB cache
```

---

## GPU Acceleration

GPU-accelerated face detection is planned — see [GPU_ACCELERATION.md](GPU_ACCELERATION.md) for the design and installation instructions. Expected speedup: **10–50× for face detection** on NVIDIA GPUs.

---

## Supported Formats

| Format | Extensions | Notes |
|--------|-----------|-------|
| **JPEG** | .jpg, .jpeg | Most common, fully supported |
| **PNG** | .png | Lossless format, fully supported |
| **HEIC** | .heic | Apple Photos format, requires Pillow HEIC support |
| **RAW** | .cr2, .nef, .arw, .dng | Canon, Nikon, Sony, Adobe RAW formats |

RAW files are processed for similarity detection and metadata extraction. The "best photo" output will be in the original RAW format.
