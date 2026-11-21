# Enhancement Roadmap

Planned and in-progress features. For completed features, see [Features.md](Features.md).

---

## Status Overview

| Feature | Status |
|---------|--------|
| Dynamic CPU Throttling | ⏳ Planned |
| Default to GPU When Available | ⏳ Planned |
| People vs. Non-People Separation | ⏳ Planned |
| Pet Detection | ⏳ Planned |
| Video Stabilization | ⏳ Planned |
| Viewer: Save Original Alongside Modified | ⏳ Planned |
| Viewer: Per-Group Reprocessing | ⏳ Planned |
| Viewer: Download Group(s) as ZIP | ⏳ Planned |
| Apple Photos Integration | ✅ Done |
| Google Photos Integration | ⏳ Planned |

---

## Planned Features

### Dynamic CPU Throttling
- Automatically reduce thread count when CPU load exceeds a configurable threshold
- Useful for running alongside other services (e.g., Immich on same server)
- Flag: `--cpu-limit <percent>` or `--throttle-load <threshold>`

### Default to GPU When Available
- Auto-detect GPU at startup and enable GPU acceleration without requiring `--gpu` flag
- Fall back to CPU gracefully with a log message if no compatible GPU found
- Keep `--no-gpu` flag for explicit CPU-only mode

### People vs. Non-People Separation
- Detect groups that contain no recognized people (landscapes, buildings, architecture, etc.)
- Non-people groups: skip face swap and blending entirely; only select best photo based on quality metrics
- People groups: apply full processing pipeline (face swap, blending, ML scoring)
- Flag: `--separate-non-people` or auto-applied when grouping by person/people

### Pet Detection
- Detect pets (dogs, cats, etc.) in photos using a pre-trained object detection model (e.g., YOLOv8 or COCO-trained detector)
- Tag pet photos in Immich (`photo-organizer/pet/dog`, `photo-organizer/pet/cat`, etc.)
- Group pet photos separately from people photos, or alongside them when both appear
- Integrates with People vs. Non-People separation: pet groups get their own processing pipeline (no face swap, quality-based best selection)

### Video Stabilization
Extends `--media-type video` from "group similar clips" to "pick the steadiest clip, and optionally steady it".
- **Shake score:** measure camera shake per video, using either OpenCV optical flow on frames already decoded for key-frame hashing (no new dependency) or ffmpeg `vidstabdetect` when available. Store it alongside the video hash and show it in the viewer/EXIF comparison.
- **Best-clip selection:** in a video group, prefer the steadiest clip (ties broken by resolution and duration), like `find_best_photo` does for faces.
- **Stabilize output:** an optional `--stabilize` flag writes `<name>_stabilized.<ext>` for the best clip (or every clip with `--stabilize all`) using ffmpeg's two-pass vid.stab (`vidstabdetect` → `vidstabtransform`, audio copied). Settings: `--stabilize-shakiness 1-10` and `--stabilize-smoothing N` frames.
  - Reference implementation: the `stabilize` script in the nixos repo's `modules/video-tools.nix`. Tested there with roughly 3× less frame-to-frame motion on a shaky test clip.
  - Needs an ffmpeg built with `libvidstab`: nixpkgs `ffmpeg-full` on NixOS (add it to `flake.nix`'s devShell; plain `ffmpeg` lacks it) or Homebrew `ffmpeg` on macOS. Fall back to the `deshake` filter with a warning when `vidstabdetect` is missing.
- **Viewer:** play the original and stabilized clips side by side (pairs with "Save Original Alongside Modified" below).
- **Immich:** upload the stabilized clip as a new asset tagged `photo-organizer/stabilized`, stacked with the original. Never replace the original.
- **Gyro data (later):** phones and GoPros record gyro metadata, so Gyroflow's CLI could give far better results than optical analysis for those clips.

### Viewer: Save Original Alongside Modified Photo
- When face swap or HDR merge is applied, keep both `best_<original>` and `face_swapped.jpg`/`hdr_merged.jpg` visible in the viewer
- Let users compare original vs. modified side-by-side within a group

### Viewer: Per-Group Reprocessing
- "Reprocess" button inside a group detail view
- User can choose which module(s) to apply: ML Quality Scoring, Face Swap, HDR Blending, etc.
- Enables workflow: manually group photos (merge/split via viewer UI), then reprocess with chosen options
- Results update the report in place without re-running the full organizer

### Viewer: Download Group(s) as ZIP
- Bulk-select one or more groups in the viewer and download all their photos as a single ZIP file
- ZIP includes originals and any modified files (face_swapped.jpg, hdr_merged.jpg)
- Available from the bulk-select toolbar and from within a single group detail view, or person view

### Google Photos Integration
- Google Photos via OAuth2 (read-only)

See [Cloud-Integration.md](Cloud-Integration.md) for design details.

---

## Implementation Notes

- All face backends implement `FaceBackend` from `src/face_backend.py`
- GPU support is opt-in via `--gpu`; CPU fallback is automatic
- Each feature is independently flag-gated — no breaking changes to existing workflows
- `--face-backend auto` always works; GPU-capable backends are preferred when `--gpu` is set
