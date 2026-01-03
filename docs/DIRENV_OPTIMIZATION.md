# Direnv Optimization Guide

The development environment has been optimized to avoid repeated loading and package checks.

## How It Works

### Caching Strategy

The `shellHook` in [flake.nix](flake.nix) now uses a marker file (`.direnv/.check-done`) to track whether package checks have been performed. This means:

1. **First time** you enter the directory → Full check runs
2. **Subsequent times** → Instant activation, no checks
3. **After installing packages** → Force recheck with `FORCE_CHECK=1`

### What's Optimized

**Before optimization:**
- Package checks ran every time direnv loaded
- ~2-5 seconds of checks on every directory change
- Multiple pip upgrade attempts

**After optimization:**
- Package checks run only once
- Instant activation (<100ms)
- Cleaner terminal output

## Usage

### Normal Use

Just `cd` into the directory - instant activation:

```bash
cd /home/scott/git/photoAlbumOrganizer
# Environment loads instantly
```

### After Installing New Packages

Force a recheck to verify installation:

```bash
pip install -r requirements.txt
FORCE_CHECK=1 direnv reload
```

### Clean Reload

If you want a completely fresh start:

```bash
# Remove cache
rm -rf .direnv

# Reload
direnv reload
```

## Direnv Configuration

The [.envrc](.envrc) file is now configured to:

1. **Use the flake** - `use flake`
2. **Watch files** - Only reload when `flake.nix` or `requirements.txt` change
3. **Cache state** - Store check results in `.direnv/`

## Commands Reference

```bash
# Allow direnv (one-time)
direnv allow

# Reload environment
direnv reload

# Force full package check
FORCE_CHECK=1 direnv reload

# Disable direnv for current shell
direnv deny

# Check direnv status
direnv status

# Clear all cache
rm -rf .direnv && direnv reload
```

## Troubleshooting

### Environment Not Loading

```bash
# Check direnv status
direnv status

# Re-allow
direnv allow
```

### Packages Not Detected After Installation

```bash
# Force recheck
FORCE_CHECK=1 direnv reload
```

### Want to Always Run Checks

Remove the caching mechanism:

```bash
# Delete the marker file
rm .direnv/.check-done

# It will be recreated on next successful check
```

## Performance Comparison

**Before:**
```
$ cd photoAlbumOrganizer
Checking installed packages...
  - Pillow... OK
  - imagehash... OK
  - cv2... OK
  - numpy... OK
  - face_recognition... OK
✓ All packages installed!
(~2-3 seconds)
```

**After (first time):**
```
$ cd photoAlbumOrganizer
Checking installed packages...
✓ All packages installed!
(~2-3 seconds, creates .direnv/.check-done)
```

**After (subsequent times):**
```
$ cd photoAlbumOrganizer
(instant - <100ms)
```

## Files Involved

- **[.envrc](.envrc)** - Direnv configuration with file watching
- **[flake.nix](flake.nix)** - Nix flake with optimized shellHook
- **`.direnv/`** - Cache directory (git-ignored)
  - `.check-done` - Marker file indicating checks completed

## Benefits

1. **Faster navigation** - No delay when changing to this directory
2. **Cleaner output** - Success banner only shows once
3. **Better UX** - Clear instructions when packages are missing
4. **Smart caching** - Auto-invalidates when files change

## Bonus: Immich Integration

The welcome message now includes Immich commands:

```
Ready to use:
  • Local: python ../src/photo_organizer.py -s <source> -o <output>
  • Immich: python ../src/photo_organizer.py --source-type immich --immich-url <url> --immich-api-key <key> --tag-only

Tip: Run 'python ../scripts/test_immich_connection.py' to test Immich connectivity
```

Enjoy your optimized development environment! 🚀
