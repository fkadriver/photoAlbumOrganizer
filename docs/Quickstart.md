# Quick Start Guide

## Prerequisites

- NixOS with direnv, or Python 3.11+ with pip
- An [Immich](https://immich.app/) instance (for Immich features)

---

## Setup

### NixOS with direnv (Recommended)

```bash
# Clone the repository
git clone https://github.com/fkadriver/photoAlbumOrganizer.git
cd photoAlbumOrganizer

# Allow direnv (one-time)
direnv allow

# Install Python packages (first time only)
pip install -r requirements.txt

# Verify installation
python scripts/verify_environment.py
```

### Without direnv

```bash
git clone https://github.com/fkadriver/photoAlbumOrganizer.git
cd photoAlbumOrganizer
nix develop   # or: python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

---

## Configure Immich

Store credentials once — all tools read from the same config file:

```bash
mkdir -p ~/.config/photo-organizer
cat > ~/.config/photo-organizer/immich.conf << 'EOF'
IMMICH_URL="https://your-immich-url"
IMMICH_API_KEY="your-api-key-here"
EOF
chmod 600 ~/.config/photo-organizer/immich.conf
```

Get your API key: Immich → **Settings → Account Settings → API Keys → New API Key**

Test the connection:
```bash
scripts/immich.sh test
```

---

## Basic Workflows

### Tag duplicates (safest first step)

```bash
scripts/immich.sh tag-only
```

Tags similar photos in Immich with `photo-organizer/best` and `photo-organizer/non-best` — nothing is deleted. Review in the Immich web UI.

### Review results in the web viewer

```bash
scripts/viewer start
# → http://localhost:8080
```

The viewer starts in the background and auto-stops when you leave the project directory. Browse groups, compare EXIF data, change best photos, and take bulk actions.

### Create albums

```bash
scripts/immich.sh create-albums
```

Creates `Organized-0001`, `Organized-0002`, etc. in Immich with best photos marked as favorites.

### Interactive guided setup

```bash
./photo_organizer.py -i
```

Walks through every option step by step. Save your settings to skip the walkthrough next time.

### Run with saved settings

```bash
./photo_organizer.py -r
```

Or choose `[r]` at the direnv prompt when you `cd` into the project.

### Clean up (undo all organizer changes)

```bash
./photo_organizer.py --cleanup \
  --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY"

# Or via the wrapper:
scripts/immich.sh cleanup "Organized-" no
```

---

## Adjust the Threshold

```bash
# Strict — only near-duplicates
scripts/immich.sh -t 3 tag-only  # Hmm: pass via --threshold flag
./photo_organizer.py --source-type immich --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" --threshold 3 --tag-only

# Default burst photos
scripts/immich.sh tag-only          # default threshold is 5

# Looser — similar compositions
./photo_organizer.py --source-type immich --immich-url "$IMMICH_URL" \
  --immich-api-key "$IMMICH_API_KEY" --threshold 8 --tag-only
```

See [CONFIGURATION.md](CONFIGURATION.md) for a full threshold guide.

---

## Local Photos (No Immich)

```bash
./photo_organizer.py -s ~/Photos -o ~/Organized -t 5
```

---

## Viewer Lifecycle

```bash
scripts/viewer start        # start (port 8080)
scripts/viewer start 9090   # custom port
scripts/viewer status       # check if running
scripts/viewer stop          # manual stop
```

The viewer auto-stops when your shell leaves the project directory.

---

## Next Steps

- [IMMICH.md](IMMICH.md) — Full Immich integration guide
- [CONFIGURATION.md](CONFIGURATION.md) — Threshold, time window, and settings
- [FACE_BACKENDS.md](FACE_BACKENDS.md) — Face detection backend options
- [GPU_ACCELERATION.md](GPU_ACCELERATION.md) — GPU setup (coming soon)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Common issues and fixes
