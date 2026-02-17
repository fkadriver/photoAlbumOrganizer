# Troubleshooting Guide

## Installation Issues

### dlib won't compile

```bash
# Ensure build tools are installed
# Ubuntu/Debian:
sudo apt-get install build-essential cmake python3.11-dev

# Try pre-built version instead:
pip install dlib-binary
```

### face_recognition import error

```bash
# Reinstall face_recognition_models
pip uninstall face_recognition_models -y
pip install git+https://github.com/ageitgey/face_recognition_models

# Verify:
python -c "import face_recognition; print('Success!')"
```

### OpenCV missing libraries (non-NixOS)

```bash
# Ubuntu/Debian:
sudo apt-get install libgl1-mesa-glx libglib2.0-0

# macOS: usually works out of the box
# Windows: Install Visual C++ Redistributable
```

### MediaPipe model not found

```bash
mkdir -p models
curl -sSL -o models/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
```

---

## Runtime Issues

### "Out of memory" errors

- Process smaller batches (use `--limit N`)
- Close other applications
- Use a machine with more RAM
- Process by year or folder

### Slow processing

- Move photos to SSD
- Increase similarity threshold to create fewer groups
- Use `--threads 4` or higher for parallel hash computation
- For Immich: use thumbnails (default) instead of full resolution

### No faces detected

- Ensure photos contain clear, front-facing faces
- Check photo quality and lighting
- Face detection works best with faces > 50×50 pixels
- Profile/side faces may not be detected
- Try switching backends: `--face-backend mediapipe`

### Wrong "best photo" selected

Face detection prefers:
- Open eyes (weighted heavily)
- Smiles
- Multiple faces all meeting criteria

Manual review is recommended for important photo groups — use the web viewer (`scripts/viewer start`) to change the best photo interactively.

### Resume prompts unexpectedly

If you see a resume/fresh-start prompt when you don't expect it:

```bash
# Force fresh start (deletes previous state file)
./photo_organizer.py ... --force-fresh

# Or just delete the state file manually
rm .photo_organizer_state.json
```

---

## NixOS Specific Issues

### Library linking errors

```bash
# Ensure LD_LIBRARY_PATH is set correctly
echo $LD_LIBRARY_PATH
# Should include paths to libGL, libstdc++, glib, etc.

# Reload environment
direnv reload
# or
exit && nix develop
```

### DGESVD warnings

These are harmless BLAS/LAPACK threading warnings. They're suppressed in the NixOS environment but don't affect functionality.

### direnv not activating

```bash
# Check direnv status
direnv status

# Ensure direnv is hooked into your shell
# In ~/.bashrc or ~/.zshrc:
eval "$(direnv hook bash)"   # or hook zsh

# Re-allow the .envrc
direnv allow
```

---

## Immich Issues

### Connection failed

```bash
# Test with curl
curl -H "x-api-key: YOUR_KEY" https://your-immich-url/api/server-info/ping
# Should return: {"res":"pong"}

# Run the built-in test
scripts/immich.sh test
```

### SSL certificate error (self-signed)

```bash
./photo_organizer.py --source-type immich \
  --immich-url https://your-immich-url \
  --immich-api-key YOUR_KEY \
  --no-verify-ssl \
  --tag-only
```

### Invalid API key

```bash
# Check config file
cat ~/.config/photo-organizer/immich.conf
chmod 600 ~/.config/photo-organizer/immich.conf

# Regenerate the key in Immich:
# Settings → Account Settings → API Keys
```

### Cleanup command fails with "No module named 'requests'"

The cleanup command must use the project virtualenv:

```bash
# This is handled automatically by scripts/immich.sh
scripts/immich.sh cleanup "Organized-" no

# If using the Python script directly, ensure you're in the venv:
source venv/bin/activate
./photo_organizer.py --cleanup ...
```

---

## Web Viewer Issues

### Viewer fails to start

```bash
# Check for an existing stale PID file
cat .viewer.pid
scripts/viewer stop

# Try again
scripts/viewer start

# Or check the Python error directly:
python -c "
import sys; sys.path.insert(0, 'src')
from web_viewer import start_viewer
start_viewer('processing_report.json')
"
```

### Port already in use

```bash
# Use a different port
scripts/viewer start 9090

# Or find what's using port 8080
lsof -i :8080
```

### No report found

```bash
# Check what reports exist
ls reports/
ls processing_report.json

# Run the organizer first to generate a report
./photo_organizer.py -i
```

### Thumbnails not loading

- Verify your Immich URL and API key in `~/.config/photo-organizer/immich.conf`
- Check the browser console for 503 errors (viewer started without Immich config)
- Ensure the Immich server is reachable from your machine

---

## Getting Help

- **GitHub Issues**: [Report a bug or ask for help](https://github.com/fkadriver/photoAlbumOrganizer/issues)
- **Verify your environment**: `python scripts/verify_environment.py`
- **Enable verbose output**: add `--verbose` flag for detailed error messages
