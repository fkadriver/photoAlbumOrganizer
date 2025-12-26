# Enhancement Roadmap

Planned enhancements for Photo Album Organizer, prioritized by user value and implementation complexity.

## Priority 1: Core Features (Next Release)

### 1. Resume Capability & Hash Persistence

**Problem:** Long-running scans can't be resumed if interrupted
**Solution:** Save progress to database

```python
# Database schema
CREATE TABLE scan_state (
    id INTEGER PRIMARY KEY,
    scan_id TEXT UNIQUE,
    source_path TEXT,
    last_photo_index INTEGER,
    total_photos INTEGER,
    started_at TIMESTAMP,
    updated_at TIMESTAMP,
    status TEXT  -- 'running', 'paused', 'completed', 'error'
);

CREATE TABLE photo_hashes (
    id INTEGER PRIMARY KEY,
    photo_path TEXT UNIQUE,
    perceptual_hash TEXT,
    file_hash TEXT,  -- For detecting file changes
    file_mtime INTEGER,
    computed_at TIMESTAMP,
    INDEX idx_photo_path (photo_path),
    INDEX idx_perceptual_hash (perceptual_hash)
);
```

**Usage:**
```bash
# Start new scan (automatically creates checkpoint)
python photo_organizer.py -s ~/Photos -o ~/Organized

# Resume interrupted scan
python photo_organizer.py --resume

# Use cached hashes (skip recomputation)
python photo_organizer.py -s ~/Photos --use-cache
```

**Implementation:**
- SQLite database for state/hashes
- Checkpoint every 100 photos
- Detect file modifications (compare mtime)
- Resume from last checkpoint

### 2. GPU Acceleration for Face Detection

**Problem:** Face detection is CPU-intensive and slow
**Solution:** Use GPU when available

```python
import torch
from facenet_pytorch import MTCNN

class GPUFaceDetector:
    def __init__(self):
        # Detect GPU availability
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.mtcnn = MTCNN(
            device=self.device,
            keep_all=True,
            post_process=False
        )
    
    def detect_faces_batch(self, images: List[np.ndarray]):
        """Process multiple images on GPU in parallel"""
        # Convert to tensors
        tensors = [torch.from_numpy(img).to(self.device) for img in images]
        
        # Batch process on GPU
        boxes, probs = self.mtcnn.detect(tensors)
        
        return boxes, probs
```

**Dependencies:**
```txt
# requirements-gpu.txt
torch>=2.0.0
torchvision>=0.15.0
facenet-pytorch>=2.5.0
```

**Usage:**
```bash
# Automatic GPU detection
python photo_organizer.py -s ~/Photos --gpu

# Force CPU (even if GPU available)
python photo_organizer.py -s ~/Photos --no-gpu

# Specify GPU device
python photo_organizer.py -s ~/Photos --gpu-device 0
```

**Performance Impact:**
- CPU: ~2-5 images/second
- GPU: ~20-50 images/second
- 10x-25x speedup for large collections

### 3. Advanced Face Swapping

**Problem:** Current face detection doesn't create composite images
**Solution:** Align faces and blend them into best photo

```python
import cv2
import dlib

class FaceSwapper:
    def __init__(self):
        # Load dlib's face landmark predictor
        self.predictor = dlib.shape_predictor(
            "shape_predictor_68_face_landmarks.dat"
        )
        self.detector = dlib.get_frontal_face_detector()
    
    def align_face(self, image: np.ndarray, landmarks):
        """Align face to canonical pose"""
        # Extract eye coordinates
        left_eye = landmarks[36:42].mean(axis=0)
        right_eye = landmarks[42:48].mean(axis=0)
        
        # Compute angle and scale
        angle = np.degrees(np.arctan2(
            right_eye[1] - left_eye[1],
            right_eye[0] - left_eye[0]
        ))
        
        # Rotate image
        center = ((left_eye + right_eye) / 2).astype(int)
        M = cv2.getRotationMatrix2D(tuple(center), angle, 1.0)
        aligned = cv2.warpAffine(image, M, (image.shape[1], image.shape[0]))
        
        return aligned
    
    def blend_faces(self, 
                    base_image: np.ndarray, 
                    face_images: List[np.ndarray],
                    masks: List[np.ndarray]) -> np.ndarray:
        """Blend multiple faces into base image"""
        result = base_image.copy()
        
        for face_img, mask in zip(face_images, masks):
            # Align face
            aligned_face = self.align_face(face_img, mask)
            
            # Poisson blending for seamless composite
            result = cv2.seamlessClone(
                aligned_face,
                result,
                mask,
                center,
                cv2.NORMAL_CLONE
            )
        
        return result
    
    def create_best_composite(self, 
                             group_photos: List[Photo]) -> np.ndarray:
        """Create composite with best face from each photo"""
        # 1. Detect faces in all photos
        all_faces = [self.detect_faces(p.image) for p in group_photos]
        
        # 2. Score each face
        scored_faces = []
        for photo, faces in zip(group_photos, all_faces):
            for face in faces:
                score = self.score_face(face)
                scored_faces.append((photo, face, score))
        
        # 3. Group faces by person (using face recognition)
        face_groups = self.group_faces_by_person(scored_faces)
        
        # 4. Select best face for each person
        best_faces = [max(group, key=lambda x: x[2]) for group in face_groups]
        
        # 5. Blend into base image
        base_photo = group_photos[0]  # or the selected best photo
        composite = self.blend_faces(
            base_photo.image,
            [f[1] for f in best_faces],
            [self.get_face_mask(f[1]) for f in best_faces]
        )
        
        return composite
```

**Usage:**
```bash
# Create composites for all groups
python photo_organizer.py -s ~/Photos -o ~/Organized --face-swap

# Show before/after comparison
python photo_organizer.py --face-swap --show-comparison

# Only create composite for groups with faces
python photo_organizer.py --face-swap --faces-only
```

**Output:**
```
output/
├── group_0001/
│   ├── originals/
│   ├── best_original.jpg       # Best photo without modification
│   ├── best_composite.jpg      # Best photo with face swapping
│   ├── comparison.jpg          # Side-by-side comparison
│   └── metadata.txt
```

## Priority 2: Immich Integration

See [IMMICH_INTEGRATION.md](IMMICH_INTEGRATION.md) for full details.

### Implementation Phases

**Phase 1: Read-Only Integration (v1.1)**
- [x] Connect to Immich API
- [x] Read photos from Immich
- [x] Tag potential duplicates
- [x] Download with caching

**Phase 2: Write Integration (v1.2)**
- [ ] Create albums for groups
- [ ] Mark best photos as favorites
- [ ] Update photo metadata
- [ ] Archive duplicates

**Phase 3: Advanced Integration (v1.3)**
- [ ] Stream processing (no download)
- [ ] Real-time sync
- [ ] Bi-directional sync
- [ ] Use Immich ML models

## Priority 3: Web Interface

See [WEB_INTERFACE_DESIGN.md](WEB_INTERFACE_DESIGN.md) for full details.

### Implementation Phases

**Phase 1: Basic UI (v1.2)**
- [ ] FastAPI backend
- [ ] React frontend
- [ ] Group listing
- [ ] Photo selection
- [ ] Apply changes

**Phase 2: Advanced Features (v1.3)**
- [ ] Real-time updates (WebSocket)
- [ ] Drag-and-drop interface
- [ ] Side-by-side comparison
- [ ] Split/merge groups
- [ ] Metadata viewer

**Phase 3: Production Ready (v1.4)**
- [ ] Authentication
- [ ] Mobile responsive
- [ ] PWA support
- [ ] Performance optimization
- [ ] Multi-user support

## Priority 4: Performance & Scalability

### Multi-Threading

```python
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import multiprocessing

class ParallelPhotoProcessor:
    def __init__(self, max_workers: int = None):
        if max_workers is None:
            max_workers = multiprocessing.cpu_count()
        self.executor = ProcessPoolExecutor(max_workers=max_workers)
    
    def process_photos_parallel(self, photos: List[Path]) -> List[Photo]:
        """Process photos in parallel across CPU cores"""
        futures = [
            self.executor.submit(self.process_single_photo, photo)
            for photo in photos
        ]
        
        results = []
        for future in tqdm(futures, desc="Processing photos"):
            results.append(future.result())
        
        return results
```

**Usage:**
```bash
# Use all CPU cores
python photo_organizer.py -s ~/Photos --parallel

# Specify thread count
python photo_organizer.py -s ~/Photos --threads 8

# Single-threaded (for debugging)
python photo_organizer.py -s ~/Photos --threads 1
```

### Database Optimization

```sql
-- Add indexes for faster queries
CREATE INDEX idx_hash_similarity ON photo_hashes(perceptual_hash);
CREATE INDEX idx_photo_path ON photo_hashes(photo_path);
CREATE INDEX idx_scan_status ON scan_state(status, updated_at);

-- Optimize hash lookups
CREATE INDEX idx_hash_prefix ON photo_hashes(substr(perceptual_hash, 1, 8));
```

## Priority 5: Advanced Features

### 1. Duplicate Confidence Scoring

```python
def calculate_similarity_confidence(hash1: str, hash2: str, 
                                   metadata1: dict, metadata2: dict) -> float:
    """Calculate confidence that photos are duplicates"""
    
    # Hamming distance
    hash_distance = hamming_distance(hash1, hash2)
    hash_score = 1.0 - (hash_distance / 64.0)
    
    # Temporal proximity
    time_diff = abs((metadata1['timestamp'] - metadata2['timestamp']).total_seconds())
    time_score = 1.0 if time_diff < 300 else max(0, 1 - time_diff / 3600)
    
    # Same camera
    camera_score = 1.0 if metadata1['camera'] == metadata2['camera'] else 0.5
    
    # Same location
    location_score = 1.0 if gps_distance(metadata1['gps'], metadata2['gps']) < 100 else 0.0
    
    # Weighted average
    confidence = (
        hash_score * 0.5 +
        time_score * 0.25 +
        camera_score * 0.15 +
        location_score * 0.10
    )
    
    return confidence
```

### 2. Machine Learning Best Photo Selection

```python
from transformers import CLIPModel, CLIPProcessor
import torch

class MLPhotoSelector:
    def __init__(self):
        self.model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        self.processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    
    def score_photo_quality(self, image: np.ndarray) -> float:
        """Use CLIP to score aesthetic quality"""
        
        # Convert to PIL
        pil_image = Image.fromarray(image)
        
        # Quality prompts
        good_prompts = [
            "a high quality photo",
            "a well composed photo",
            "a sharp and clear photo",
            "a professional photograph"
        ]
        
        bad_prompts = [
            "a blurry photo",
            "a low quality photo",
            "an out of focus photo"
        ]
        
        # Encode
        inputs = self.processor(
            text=good_prompts + bad_prompts,
            images=pil_image,
            return_tensors="pt",
            padding=True
        )
        
        outputs = self.model(**inputs)
        logits = outputs.logits_per_image
        probs = logits.softmax(dim=1)
        
        # Score: probability of good - probability of bad
        good_score = probs[0, :len(good_prompts)].sum()
        bad_score = probs[0, len(good_prompts):].sum()
        
        return (good_score - bad_score).item()
```

### 3. Video Support

```python
import cv2

class VideoHandler:
    def extract_key_frames(self, video_path: Path) -> List[np.ndarray]:
        """Extract representative frames from video"""
        cap = cv2.VideoCapture(str(video_path))
        
        frames = []
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Extract every Nth frame
        step = max(1, frame_count // 10)  # 10 frames per video
        
        for i in range(0, frame_count, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
        
        cap.release()
        return frames
    
    def find_similar_videos(self, video_paths: List[Path]) -> List[List[Path]]:
        """Group similar videos"""
        video_hashes = {}
        
        for video in video_paths:
            frames = self.extract_key_frames(video)
            # Average hash of key frames
            hashes = [compute_hash(f) for f in frames]
            avg_hash = average_hash(hashes)
            video_hashes[video] = avg_hash
        
        # Group by similarity
        return self.group_by_hash_similarity(video_hashes)
```

## Implementation Timeline

### Version 1.1 (Q1 2025) - Core Improvements
- ✅ Resume capability
- ✅ Hash persistence
- ✅ GPU acceleration
- ✅ Advanced face swapping
- ⏳ Immich integration (Phase 1)

### Version 1.2 (Q2 2025) - Integration
- ⏳ Web interface (Phase 1)
- ⏳ Immich integration (Phase 2)
- ⏳ Multi-threading
- ⏳ Mobile support

### Version 1.3 (Q3 2025) - Advanced Features
- ⏳ ML-based selection
- ⏳ Confidence scoring
- ⏳ Web interface (Phase 2)
- ⏳ Video support

### Version 2.0 (Q4 2025) - Production Ready
- ⏳ Full Immich integration
- ⏳ Web interface (Phase 3)
- ⏳ Plugin system
- ⏳ Cloud deployment

## Development Priorities

### High Priority (Must Have)
1. Resume capability - Users need this for large libraries
2. Hash persistence - Avoid re-processing
3. GPU acceleration - Major performance boost
4. Immich integration - Many users use Immich

### Medium Priority (Should Have)
5. Web interface - Better UX
6. Face swapping - Unique feature
7. Multi-threading - Performance
8. Mobile support - Accessibility

### Low Priority (Nice to Have)
9. ML selection - Advanced but optional
10. Video support - Edge case
11. Plugin system - Power users
12. Cloud deployment - Enterprise

## Contributing

Want to help implement these features? See:
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [DEVELOPMENT.md](DEVELOPMENT.md)
- Open an issue to discuss implementation
- Submit PRs for specific features

## Feedback

Have suggestions for the roadmap?
- Open an issue on GitHub
- Tag with `enhancement` label
- Describe use case and expected behavior
