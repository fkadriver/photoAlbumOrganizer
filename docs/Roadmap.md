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
| Viewer: Save Original Alongside Modified | ⏳ Planned |
| Viewer: Per-Group Reprocessing | ⏳ Planned |
| Viewer: Download Group(s) as ZIP | ⏳ Planned |
| Apple / Google Photos Integration | ⏳ Planned |

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

### Apple / Google Photos Integration
- Apple Photos via `osxphotos` (macOS only)
- Google Photos via OAuth2 (read-only)

See [Cloud-Integration.md](Cloud-Integration.md) for design details.

---

## Implementation Notes

- All face backends implement `FaceBackend` from `src/face_backend.py`
- GPU support is opt-in via `--gpu`; CPU fallback is automatic
- Each feature is independently flag-gated — no breaking changes to existing workflows
- `--face-backend auto` always works; GPU-capable backends are preferred when `--gpu` is set
