# Advanced Features Implementation Roadmap

This document outlines the implementation plan for advanced features that would significantly enhance the Photo Album Organizer.

## Overview

These features represent major enhancements beyond the current capabilities:

1. ✅ **Immich Integration** - COMPLETED
2. ✅ **Resume Capability** - COMPLETED
3. 🔧 **Multi-threaded Processing** - High Priority, Moderate Complexity
4. 🎨 **Advanced Face Swapping** - Medium Priority, High Complexity
5. 🚀 **GPU Acceleration** - Medium Priority, High Complexity
6. 📊 **HDR/Exposure Blending** - Low-Medium Priority, High Complexity
7. 🤖 **Machine Learning Selection** - Medium Priority, Very High Complexity

## Priority Recommendations

### Phase 3: Performance & Reliability (Recommended Next)
**Goal:** Make the tool faster and more robust

#### 3.1: Multi-threaded Processing
**Effort:** 2-3 days | **Impact:** High | **Complexity:** Moderate

**Benefits:**
- 3-5x faster processing on multi-core systems
- Better resource utilization
- Improved user experience

**Implementation Approach:**

```python
# Add to requirements.txt
concurrent.futures  # Built-in, no installation needed

# Update photo_organizer.py
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import multiprocessing

class PhotoOrganizer:
    def __init__(self, ..., num_workers=None):
        self.num_workers = num_workers or multiprocessing.cpu_count()

    def compute_hashes_parallel(self, photos):
        """Compute hashes in parallel using thread pool."""
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {executor.submit(self.compute_hash, photo): photo
                      for photo in photos}

            results = []
            for future in as_completed(futures):
                photo = futures[future]
                try:
                    hash_val = future.result()
                    if hash_val:
                        results.append({'photo': photo, 'hash': hash_val})
                except Exception as e:
                    print(f"Error processing {photo.id}: {e}")

            return results

    def score_faces_parallel(self, group):
        """Score faces in parallel."""
        with ProcessPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {executor.submit(self.score_face_quality, pd['photo']): pd
                      for pd in group}

            scores = {}
            for future in as_completed(futures):
                photo_data = futures[future]
                try:
                    scores[photo_data['photo'].id] = future.result()
                except Exception as e:
                    print(f"Error scoring faces: {e}")
                    scores[photo_data['photo'].id] = []

            return scores
```

**Command-line argument:**
```bash
--workers N           Number of worker threads (default: CPU count)
--parallel-hash       Enable parallel hash computation
--parallel-faces      Enable parallel face detection
```

**Testing:**
```bash
# Benchmark current performance
time python ../src/photo_organizer.py -s test_photos -o output

# Test parallel version
time python ../src/photo_organizer.py -s test_photos -o output --workers 8 --parallel-hash --parallel-faces
```

#### 3.2: Resume Capability ✅ COMPLETED
**Effort:** 1-2 days | **Impact:** High | **Complexity:** Low-Moderate

**Status:** ✅ **IMPLEMENTED** - See [RESUME_CAPABILITY.md](RESUME_CAPABILITY.md) for usage guide

**Benefits:**
- Can interrupt and resume long processing jobs
- Saves progress periodically (every 50 photos)
- Handles crashes and interrupts gracefully
- Hash caching for faster resume
- Skip already-processed groups

**Actual Implementation:**

```python
import pickle
from pathlib import Path

class ProcessingState:
    """Manages processing state for resume capability."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state = {
            'processed_hashes': {},
            'completed_groups': [],
            'current_group': None,
            'photos_processed': 0,
            'total_photos': 0
        }

    def save(self):
        """Save current state to disk."""
        with open(self.state_file, 'wb') as f:
            pickle.dump(self.state, f)

    def load(self) -> bool:
        """Load state from disk. Returns True if state exists."""
        if self.state_file.exists():
            with open(self.state_file, 'rb') as f:
                self.state = pickle.load(f)
            return True
        return False

    def mark_hash_computed(self, photo_id: str, hash_val):
        """Mark a photo as hashed."""
        self.state['processed_hashes'][photo_id] = hash_val
        self.state['photos_processed'] += 1

        # Save every 100 photos
        if self.state['photos_processed'] % 100 == 0:
            self.save()

    def mark_group_completed(self, group_id: int):
        """Mark a group as completed."""
        self.state['completed_groups'].append(group_id)
        self.save()

class PhotoOrganizer:
    def __init__(self, ..., resume=False, state_file=None):
        self.resume = resume
        self.state_file = Path(state_file or '.photo_organizer_state.pkl')
        self.state = ProcessingState(self.state_file)

        if resume and self.state.load():
            print(f"Resuming from previous run...")
            print(f"  Processed: {self.state.state['photos_processed']} photos")
            print(f"  Completed: {len(self.state.state['completed_groups'])} groups")

    def organize_photos(self, album: str = None):
        """Main method with resume support."""
        try:
            # Normal processing...
            photos = self.find_all_photos(album=album)
            self.state.state['total_photos'] = len(photos)

            # Compute hashes (skip already processed)
            photo_data = []
            for photo in photos:
                if photo.id in self.state.state['processed_hashes']:
                    # Use cached hash
                    hash_val = self.state.state['processed_hashes'][photo.id]
                    photo_data.append({'photo': photo, 'hash': hash_val, ...})
                else:
                    # Compute new hash
                    hash_val = self.compute_hash(photo)
                    if hash_val:
                        self.state.mark_hash_computed(photo.id, hash_val)
                        photo_data.append({'photo': photo, 'hash': hash_val, ...})

            # Process groups (skip completed)
            groups = self.group_similar_photos(photo_data)
            for i, group in enumerate(groups, 1):
                if i in self.state.state['completed_groups']:
                    print(f"Skipping group {i} (already completed)")
                    continue

                # Process group...
                self.process_group(group, i)
                self.state.mark_group_completed(i)

            # Clean up state file on successful completion
            self.state_file.unlink(missing_ok=True)

        except KeyboardInterrupt:
            print("\n\nInterrupted! State saved.")
            print(f"Resume with: --resume --state-file {self.state_file}")
            self.state.save()
            raise
        except Exception as e:
            print(f"\nError: {e}")
            print(f"State saved. Resume with: --resume --state-file {self.state_file}")
            self.state.save()
            raise
```

**Command-line arguments:**
```bash
--resume              Resume from previous interrupted run
--state-file PATH     State file location (default: .photo_organizer_state.pkl)
```

**Usage:**
```bash
# Start processing
python ../src/photo_organizer.py -s ~/Photos -o ~/Organized

# If interrupted (Ctrl+C), resume:
python ../src/photo_organizer.py -s ~/Photos -o ~/Organized --resume
```

### Phase 4: Advanced Image Processing (Advanced Users)

#### 4.1: GPU Acceleration for Face Detection
**Effort:** 3-5 days | **Impact:** High | **Complexity:** High

**Benefits:**
- 10-50x faster face detection
- Can process thousands of photos quickly
- Better for large libraries

**Requirements:**
- NVIDIA GPU with CUDA support
- `dlib` compiled with CUDA
- Or use `opencv-contrib-python` with CUDA

**Implementation Approach:**

```python
# requirements-gpu.txt
dlib-cuda  # CUDA-enabled dlib (requires compilation)
# OR
opencv-contrib-python-headless  # OpenCV with CUDA support

# Add to photo_organizer.py
import cv2

class PhotoOrganizer:
    def __init__(self, ..., use_gpu=False):
        self.use_gpu = use_gpu and self._check_gpu_available()

        if self.use_gpu:
            print("GPU acceleration enabled")
            # Set OpenCV to use CUDA backend
            cv2.cuda.setDevice(0)

    def _check_gpu_available(self) -> bool:
        """Check if GPU is available."""
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                return True
        except:
            pass
        return False

    def score_face_quality_gpu(self, photo):
        """GPU-accelerated face detection."""
        if not self.use_gpu:
            return self.score_face_quality(photo)

        try:
            # Load image to GPU
            img = cv2.imread(str(photo.cached_path))
            gpu_img = cv2.cuda_GpuMat()
            gpu_img.upload(img)

            # GPU-accelerated face detection
            gpu_gray = cv2.cuda.cvtColor(gpu_img, cv2.COLOR_BGR2GRAY)

            # Use GPU cascade classifier
            face_detector = cv2.cuda.CascadeClassifier_create(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )

            faces = face_detector.detectMultiScale(gpu_gray)

            # Process on CPU
            faces_cpu = faces.download()

            # Score faces (this part remains on CPU)
            # ... scoring logic ...

            return face_scores
        except Exception as e:
            print(f"GPU processing failed, falling back to CPU: {e}")
            return self.score_face_quality(photo)
```

**Command-line argument:**
```bash
--gpu                 Enable GPU acceleration (requires CUDA)
--gpu-device N        GPU device number (default: 0)
```

**Installation (NVIDIA GPU required):**
```bash
# Check CUDA availability
nvidia-smi

# Install CUDA-enabled OpenCV
pip install opencv-contrib-python

# Or compile dlib with CUDA (advanced)
```

#### 4.2: HDR/Exposure Blending
**Effort:** 4-6 days | **Impact:** Medium | **Complexity:** High

**Benefits:**
- Merge multiple exposures
- Better dynamic range in final image
- Professional-quality results

**Implementation Approach:**

```python
# requirements.txt additions
# (already have opencv and PIL)

def merge_exposures_hdr(self, group):
    """
    Merge multiple exposures using HDR technique.
    Useful when group contains bracketed shots.
    """
    if len(group) < 2:
        return None

    # Load images
    images = []
    for photo_data in group:
        img_path = photo_data['photo'].cached_path or self._get_temp_path(photo_data['photo'])
        img = cv2.imread(str(img_path))
        images.append(img)

    # Estimate camera response function
    calibrate = cv2.createCalibrateDebevec()
    response = calibrate.process(images, times=np.array([1.0] * len(images), dtype=np.float32))

    # Merge exposures to HDR
    merge = cv2.createMergeDebevec()
    hdr = merge.process(images, times=np.array([1.0] * len(images), dtype=np.float32), response=response)

    # Tone mapping
    tonemap = cv2.createTonemapDrago(gamma=2.2)
    ldr = tonemap.process(hdr)

    # Convert to 8-bit
    ldr = np.clip(ldr * 255, 0, 255).astype('uint8')

    return ldr

def should_merge_hdr(self, group) -> bool:
    """
    Determine if group should be merged using HDR.
    True if photos are taken in quick succession with different exposures.
    """
    if len(group) < 2:
        return False

    # Check if photos have different exposure values
    exposures = []
    for photo_data in group:
        exposure = photo_data['metadata'].get('exif_ExposureTime')
        if exposure:
            try:
                exposures.append(float(eval(exposure)))  # Convert "1/250" to 0.004
            except:
                pass

    # If we have multiple different exposures, likely a bracket
    if len(set(exposures)) > 1 and len(exposures) >= 2:
        return True

    return False
```

**Command-line argument:**
```bash
--enable-hdr          Enable HDR merging for bracketed shots
--hdr-gamma GAMMA     HDR tone mapping gamma (default: 2.2)
```

#### 4.3: Advanced Face Swapping
**Effort:** 5-7 days | **Impact:** Medium | **Complexity:** Very High

**Benefits:**
- Replace closed eyes with open eyes from other shots
- Swap bad expressions with good ones
- Create "perfect" group photos

**Implementation Approach:**

```python
# requirements.txt additions
face-alignment>=1.3.0
insightface>=0.7.0

import face_alignment

class FaceSwapper:
    """Advanced face swapping with alignment and blending."""

    def __init__(self):
        self.fa = face_alignment.FaceAlignment(
            face_alignment.LandmarksType._2D,
            flip_input=False
        )

    def swap_faces(self, base_image, source_images, target_faces):
        """
        Swap specific faces in base_image with faces from source_images.

        Args:
            base_image: The image to modify
            source_images: List of images to take faces from
            target_faces: List of face indices to replace
        """
        # Detect landmarks in base image
        base_landmarks = self.fa.get_landmarks(base_image)

        if not base_landmarks:
            return base_image

        result = base_image.copy()

        for face_idx in target_faces:
            if face_idx >= len(base_landmarks):
                continue

            base_face_landmarks = base_landmarks[face_idx]

            # Find best replacement face from source images
            best_face = self._find_best_replacement(
                base_face_landmarks,
                source_images
            )

            if best_face:
                # Align and blend
                result = self._align_and_blend_face(
                    result,
                    best_face['image'],
                    base_face_landmarks,
                    best_face['landmarks']
                )

        return result

    def _find_best_replacement(self, target_landmarks, source_images):
        """Find the best face from source images to replace target."""
        best_score = -1
        best_face = None

        for src_img in source_images:
            src_landmarks = self.fa.get_landmarks(src_img)
            if not src_landmarks:
                continue

            for src_face_landmarks in src_landmarks:
                # Score based on:
                # 1. Eye openness
                # 2. Smile
                # 3. Face angle similarity
                score = self._score_face_replacement(
                    target_landmarks,
                    src_face_landmarks,
                    src_img
                )

                if score > best_score:
                    best_score = score
                    best_face = {
                        'image': src_img,
                        'landmarks': src_face_landmarks,
                        'score': score
                    }

        return best_face

    def _align_and_blend_face(self, base_img, source_img,
                              base_landmarks, source_landmarks):
        """Align source face to base face and blend seamlessly."""
        # Compute transformation matrix
        transform = self._compute_transform(source_landmarks, base_landmarks)

        # Warp source face
        warped = cv2.warpAffine(source_img, transform,
                               (base_img.shape[1], base_img.shape[0]))

        # Create mask for blending
        mask = self._create_face_mask(base_landmarks, base_img.shape)

        # Seamless clone
        center = self._get_face_center(base_landmarks)
        result = cv2.seamlessClone(
            warped, base_img, mask,
            center, cv2.NORMAL_CLONE
        )

        return result
```

**Command-line argument:**
```bash
--face-swap           Enable automatic face swapping
--swap-closed-eyes    Swap faces with closed eyes
--swap-bad-expression Swap faces with poor expressions
```

#### 4.4: Machine Learning for Better Selection
**Effort:** 7-10 days | **Impact:** High | **Complexity:** Very High

**Benefits:**
- Learns from user preferences
- Considers composition, lighting, focus
- Improves over time

**Implementation Approach:**

```python
# requirements.txt additions
tensorflow>=2.13.0
keras>=2.13.0
scikit-learn>=1.3.0

from tensorflow import keras
from sklearn.ensemble import RandomForestClassifier
import numpy as np

class MLPhotoSelector:
    """Machine learning-based photo selection."""

    def __init__(self, model_path=None):
        self.model = self._load_or_create_model(model_path)
        self.feature_extractor = self._create_feature_extractor()

    def _create_feature_extractor(self):
        """Create CNN feature extractor."""
        base_model = keras.applications.MobileNetV2(
            include_top=False,
            weights='imagenet',
            pooling='avg'
        )
        return base_model

    def extract_features(self, image_path):
        """Extract ML features from image."""
        img = keras.preprocessing.image.load_img(
            image_path, target_size=(224, 224)
        )
        x = keras.preprocessing.image.img_to_array(img)
        x = np.expand_dims(x, axis=0)
        x = keras.applications.mobilenet_v2.preprocess_input(x)

        features = self.feature_extractor.predict(x)
        return features.flatten()

    def score_photo(self, photo, group_context=None):
        """
        Score a photo using ML model.

        Considers:
        - Image quality (sharpness, exposure)
        - Composition (rule of thirds, symmetry)
        - Facial expressions
        - Technical quality
        """
        features = []

        # ML features
        ml_features = self.extract_features(photo.cached_path)
        features.extend(ml_features)

        # Technical features
        features.append(self._compute_sharpness(photo))
        features.append(self._compute_exposure_quality(photo))
        features.append(self._compute_composition_score(photo))

        # Face features
        face_scores = self.score_face_quality(photo)
        features.append(np.mean(face_scores) if face_scores else 0)

        # Predict quality score
        score = self.model.predict([features])[0]
        return score

    def train_from_feedback(self, selections):
        """Train model from user selections."""
        X = []
        y = []

        for selection in selections:
            for photo in selection['group']:
                features = self.extract_features(photo['path'])
                X.append(features)
                # 1 if selected, 0 otherwise
                y.append(1 if photo == selection['chosen'] else 0)

        self.model.fit(X, y)
```

**Command-line arguments:**
```bash
--ml-selection        Use ML for photo selection
--ml-model PATH       Path to trained ML model
--train-ml            Enter training mode (user provides feedback)
```

## Implementation Priority

### Recommended Order:

**Phase 3 (Do First):**
1. **Multi-threaded Processing** - Immediate value, moderate effort
2. ✅ **Resume Capability** - COMPLETED - High value for large libraries

**Phase 4 (Do Later):**
3. **GPU Acceleration** - Only if you have many photos and NVIDIA GPU
4. **HDR Merging** - Nice to have for specific use cases
5. **Face Swapping** - Complex, specific use case
6. **ML Selection** - Most complex, do last after gathering data

## Getting Started

### Quick Win: Multi-threading

Start with multi-threading as it provides immediate performance benefits:

```bash
# Create a new branch
git checkout -b feature/multithreading

# Implement parallel hash computation (easiest)
# Test thoroughly
# Implement parallel face detection
# Update documentation
# Commit and test
```

### Building Incrementally

Each feature can be:
1. Implemented independently
2. Made optional (flag-based)
3. Tested separately
4. Documented

Would you like me to:
1. **Implement multi-threading** (quickest win, next recommended feature)
2. ✅ **Resume capability** - COMPLETED!
3. **Create a specific implementation plan** for one feature
4. **Start with a prototype** for one of these features

Let me know which direction you'd like to go!
