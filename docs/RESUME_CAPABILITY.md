# Resume Capability

The Photo Album Organizer now supports **resume capability**, allowing you to interrupt long-running jobs and resume them later without losing progress. This is especially useful for:

- Large photo libraries (thousands of photos)
- Unstable network connections (Immich integration)
- Testing and experimentation
- Long processing sessions that need to be paused

## How It Works

The organizer automatically saves progress to a state file during processing:

1. **Automatic state tracking**: Progress is saved every 50 photo hashes and after each group is processed
2. **Graceful interruption**: Press `Ctrl+C` to interrupt - the state will be saved automatically
3. **Resume from checkpoint**: Use `--resume` to continue from where you left off
4. **Smart caching**: Previously computed hashes are cached and reused

### State File

By default, the state file is saved as:
- `.photo_organizer_state.pkl` in the output directory (for local mode)
- `.photo_organizer_state.pkl` in the current directory (for tag-only/album modes)

You can specify a custom state file path with `--state-file`.

## Usage Examples

### Basic Local Processing with Resume

```bash
# Start processing (will be interrupted)
python ../src/photo_organizer.py -s ~/Photos -o ~/Organized

# Press Ctrl+C to interrupt

# Resume from where you left off
python ../src/photo_organizer.py -s ~/Photos -o ~/Organized --resume
```

### Immich Integration with Resume

Using the `immich.sh` wrapper:

```bash
# Start creating albums (will be interrupted)
../scripts/immich.sh create-albums

# Press Ctrl+C to interrupt

# Resume using RESUME environment variable
RESUME=1 ../scripts/immich.sh create-albums
```

Direct Python command:

```bash
# Start processing
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url https://immich.example.com \
  --immich-api-key YOUR_KEY \
  --create-albums

# Press Ctrl+C to interrupt

# Resume
python ../src/photo_organizer.py \
  --source-type immich \
  --immich-url https://immich.example.com \
  --immich-api-key YOUR_KEY \
  --create-albums \
  --resume
```

### Custom State File

```bash
# Use a specific state file location
python ../src/photo_organizer.py \
  -s ~/Photos \
  -o ~/Organized \
  --state-file /tmp/my_progress.pkl

# Resume with the same state file
python ../src/photo_organizer.py \
  -s ~/Photos \
  -o ~/Organized \
  --resume \
  --state-file /tmp/my_progress.pkl
```

## What Gets Saved

The state file contains:

- **Configuration**: Source type, paths, threshold, time window settings
- **Hash cache**: All computed perceptual hashes (avoiding re-computation)
- **Progress counters**: Photos discovered, photos hashed, groups found, groups processed
- **Completion tracking**: Which groups have been fully processed
- **Timestamps**: When processing started and last saved

## Important Notes

### Parameter Compatibility

The organizer verifies that resume parameters match the original run:

- Source type (local vs immich)
- Source path
- Similarity threshold

If parameters differ, the organizer will start fresh to avoid inconsistencies.

**Example of incompatible resume:**

```bash
# Original run with threshold 5
python ../src/photo_organizer.py -s ~/Photos -o ~/Organized --threshold 5

# This will NOT resume (threshold changed)
python ../src/photo_organizer.py -s ~/Photos -o ~/Organized --threshold 8 --resume
# Output: "Warning: Parameters have changed since last run!"
# Output: "Starting fresh to avoid inconsistencies..."
```

### State File Cleanup

The state file is automatically removed when:
- All groups are successfully processed
- You explicitly call `state.cleanup()`

If processing fails or is interrupted, the state file remains for resume.

### Limitations

- **Different albums**: If you process different Immich albums, use different state files
- **Changed source**: If you change the photo source directory, resume won't work
- **Manual changes**: If you manually modify output directory contents, resume may create unexpected results

## Progress Monitoring

During resume, you'll see:

```
============================================================
RESUMING FROM PREVIOUS RUN
============================================================
Progress Summary:
  Started: 2026-01-03 10:30:00
  Last saved: 2026-01-03 10:45:30
  Photos hashed: 1500/2000
  Groups processed: 45/60
  Completion: 75.0%
============================================================

Found 2000 photos
Computing hashes for 2000 photos...
Using cached hash for 1500 photos...
Processing 500 new photos...
...
Skipping group 1/60 (already completed)
Skipping group 2/60 (already completed)
...
Skipping group 45/60 (already completed)
Processing group 46/60 (8 photos)...
```

## Performance Benefits

Resume capability provides significant performance benefits:

1. **Hash caching**: Perceptual hash computation is expensive - caching saves time
   - ~500ms per photo → cached reads in ~1ms
   - For 1000 photos: ~8 minutes saved

2. **Group skipping**: Already processed groups are skipped entirely
   - Face detection, downloading, album creation all skipped
   - For 50 groups: ~10-30 minutes saved

3. **Network resilience**: Immich downloads can resume after network failures
   - No need to re-download already cached photos

## Troubleshooting

### Resume doesn't work

**Check if state file exists:**
```bash
ls -lh .photo_organizer_state.pkl
```

**Verify state file contents:**
```python
from processing_state import ProcessingState
from pathlib import Path

state = ProcessingState(Path('.photo_organizer_state.pkl'))
if state.load():
    print(state.get_progress_summary())
else:
    print("Failed to load state")
```

### Start fresh (delete state)

If you want to start over:

```bash
rm .photo_organizer_state.pkl
rm .photo_organizer_state.tmp
```

Or specify a different output directory to get a new state file automatically.

### State file corrupted

If the state file is corrupted, the organizer will:
1. Warn you about the failure
2. Start fresh automatically
3. Create a new state file

## Integration with immich.sh

The `immich.sh` wrapper script supports resume through the `RESUME` environment variable:

```bash
# Tag duplicates with resume support
RESUME=1 ../scripts/immich.sh tag-only

# Create albums with resume support
RESUME=1 ../scripts/immich.sh create-albums

# Download with resume support
RESUME=1 ../scripts/immich.sh download ~/Organized

# Process specific album with resume
RESUME=1 ../scripts/immich.sh album "Vacation 2024" create-albums
```

This works for all modes: tag-only, create-albums, download, and album-specific operations.

## Best Practices

1. **Long-running jobs**: Always enable resume for large libraries (>1000 photos)
2. **Testing**: Use resume to safely test on subsets before processing everything
3. **Network issues**: For Immich, resume is essential for unreliable connections
4. **Disk space**: State files are small (~KB to MB), but monitor disk for large libraries
5. **Version control**: State files are already in `.gitignore` - don't commit them

## Technical Details

### State Persistence

- **Format**: Python pickle (binary)
- **Atomic writes**: Uses temp file + rename to prevent corruption
- **Auto-save frequency**: Every 50 photos, after each group, on interrupt
- **Compatibility**: Only resumes with matching parameters

### Signal Handling

The organizer handles these signals:
- `SIGINT` (Ctrl+C): Saves state and exits gracefully
- `SIGTERM`: Saves state and exits gracefully

### Error Handling

On unexpected errors:
1. State is automatically saved
2. Error message shows resume command
3. Exit with error code

Example:
```
Error during processing: Connection timeout
State saved to: .photo_organizer_state.pkl
Resume with: --resume --state-file .photo_organizer_state.pkl
```

## See Also

- [IMMICH_USAGE.md](IMMICH_USAGE.md) - Immich integration guide
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [ADVANCED_FEATURES_ROADMAP.md](ADVANCED_FEATURES_ROADMAP.md) - Future enhancements
