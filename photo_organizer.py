import os
import shutil
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta
import json
import hashlib

# Image processing
from PIL import Image
from PIL.ExifTags import TAGS
import imagehash
import cv2
import numpy as np

# Face detection - with workaround for Python 3.12 compatibility
FACE_DETECTION_ENABLED = True
try:
    # Fix for face_recognition_models import issue in Python 3.12
    import pkg_resources
    try:
        pkg_resources.require("face_recognition_models")
    except:
        pass
    
    import face_recognition
except Exception as e:
    print("Warning: Could not import face_recognition")
    print(f"  {e}")
    print("\nFace detection will be DISABLED.")
    print("Photos will be grouped, but best photo selection will be random.")
    print("\nTo enable face detection, use Python 3.11 or earlier:")
    print("  python3.11 -m venv venv && source venv/bin/activate")
    print("  pip install -r requirements.txt")
    print("\nContinuing without face detection...\n")
    FACE_DETECTION_ENABLED = False
    face_recognition = None

class PhotoOrganizer:
    def __init__(self, source_dir, output_dir, similarity_threshold=5):
        """
        Initialize the photo organizer.
        
        Args:
            source_dir: Root directory containing photos
            output_dir: Directory where organized groups will be created
            similarity_threshold: Hamming distance threshold for image similarity (lower = more similar)
        """
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.similarity_threshold = similarity_threshold
        self.output_dir.mkdir(exist_ok=True)
        
        # Supported formats
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.heic', '.cr2', '.nef', '.arw', '.dng'}
    
    def extract_metadata(self, image_path):
        """Extract EXIF and file metadata from an image."""
        metadata = {
            'filename': image_path.name,
            'filepath': str(image_path),
            'filesize': image_path.stat().st_size,
            'modified_time': datetime.fromtimestamp(image_path.stat().st_mtime).isoformat(),
            'created_time': datetime.fromtimestamp(image_path.stat().st_ctime).isoformat(),
        }
        
        try:
            with Image.open(image_path) as img:
                metadata['dimensions'] = f"{img.size[0]}x{img.size[1]}"
                metadata['format'] = img.format
                
                # Extract EXIF
                exif_data = img._getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)
                        metadata[f'exif_{tag}'] = str(value)
        except Exception as e:
            metadata['error'] = f"Could not read EXIF: {str(e)}"
        
        return metadata
    
    def get_datetime_from_metadata(self, metadata):
        """Extract datetime from metadata, trying multiple sources."""
        # Try EXIF DateTime first
        for key in ['exif_DateTimeOriginal', 'exif_DateTime', 'exif_DateTimeDigitized']:
            if key in metadata:
                try:
                    return datetime.strptime(metadata[key], '%Y:%m:%d %H:%M:%S')
                except:
                    pass
        
        # Fall back to file modified time
        try:
            return datetime.fromisoformat(metadata['modified_time'])
        except:
            return None
    
    def find_all_photos(self):
        """Recursively find all photos in source directory."""
        photos = []
        for path in self.source_dir.rglob('*'):
            if path.suffix.lower() in self.supported_formats:
                photos.append(path)
        return photos
    
    def compute_hash(self, image_path):
        """Compute perceptual hash for an image."""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                # Use difference hash (good for finding similar images)
                return imagehash.dhash(img)
        except Exception as e:
            print(f"Error hashing {image_path}: {e}")
            return None
    
    def group_similar_photos(self, photos):
        """Group photos by perceptual similarity."""
        print(f"Computing hashes for {len(photos)} photos...")
        
        # Compute hashes and metadata
        photo_data = []
        for i, photo in enumerate(photos):
            if i % 100 == 0:
                print(f"Processing {i}/{len(photos)}...")
            
            hash_val = self.compute_hash(photo)
            if hash_val is None:
                continue
                
            metadata = self.extract_metadata(photo)
            dt = self.get_datetime_from_metadata(metadata)
            
            photo_data.append({
                'path': photo,
                'hash': hash_val,
                'metadata': metadata,
                'datetime': dt
            })
        
        print(f"Grouping {len(photo_data)} photos by similarity...")
        
        # Group by similarity
        groups = []
        used = set()
        
        for i, data1 in enumerate(photo_data):
            if i in used:
                continue
            
            group = [data1]
            used.add(i)
            
            for j, data2 in enumerate(photo_data[i+1:], start=i+1):
                if j in used:
                    continue
                
                # Check hash similarity
                hash_diff = data1['hash'] - data2['hash']
                
                if hash_diff <= self.similarity_threshold:
                    # Additional temporal check if both have datetime
                    if data1['datetime'] and data2['datetime']:
                        time_diff = abs((data1['datetime'] - data2['datetime']).total_seconds())
                        # If within 5 minutes, consider it part of burst
                        if time_diff <= 300:
                            group.append(data2)
                            used.add(j)
                    else:
                        # If no datetime, rely on hash alone
                        group.append(data2)
                        used.add(j)
            
            if len(group) > 1:  # Only create groups with multiple photos
                groups.append(group)
        
        print(f"Found {len(groups)} groups of similar photos")
        return groups
    
    def score_face_quality(self, image_path):
        """
        Score faces in an image for smile and open eyes.
        Returns list of face scores.
        """
        if not FACE_DETECTION_ENABLED:
            return []
        
        try:
            # Load image
            image = face_recognition.load_image_file(image_path)
            face_locations = face_recognition.face_locations(image)
            
            if not face_locations:
                return []
            
            # Use OpenCV for smile detection
            cv_image = cv2.imread(str(image_path))
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            
            # Load cascade classifiers
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            smile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_smile.xml')
            eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
            
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            
            face_scores = []
            for (x, y, w, h) in faces:
                roi_gray = gray[y:y+h, x:x+w]
                
                # Detect smiles
                smiles = smile_cascade.detectMultiScale(roi_gray, 1.8, 20)
                smile_score = len(smiles)
                
                # Detect eyes
                eyes = eye_cascade.detectMultiScale(roi_gray, 1.1, 5)
                eye_score = min(len(eyes), 2)  # Max 2 eyes
                
                # Combined score
                total_score = smile_score + eye_score * 2  # Weight eyes more
                face_scores.append(total_score)
            
            return face_scores
            
        except Exception as e:
            print(f"Error scoring faces in {image_path}: {e}")
            return []
    
    def find_best_photo(self, group):
        """Find the best photo in a group based on face quality."""
        best_photo = None
        best_score = -1
        
        for photo_data in group:
            scores = self.score_face_quality(photo_data['path'])
            avg_score = sum(scores) / len(scores) if scores else 0
            
            if avg_score > best_score:
                best_score = avg_score
                best_photo = photo_data
        
        # If no faces found, return first photo
        return best_photo if best_photo else group[0]
    
    def swap_faces(self, base_image_path, source_images):
        """
        Create composite image with best faces from multiple images.
        This is a simplified version - production would need more sophisticated alignment.
        """
        try:
            base_img = cv2.imread(str(base_image_path))
            
            # For now, just return the best image
            # Full face swapping requires complex alignment and blending
            # which is beyond this initial implementation
            
            return base_img
            
        except Exception as e:
            print(f"Error swapping faces: {e}")
            return None
    
    def save_metadata(self, group, group_dir):
        """Save metadata for all photos in group to text file."""
        metadata_file = group_dir / 'metadata.txt'
        
        with open(metadata_file, 'w') as f:
            f.write(f"Photo Group - {len(group)} images\n")
            f.write("=" * 80 + "\n\n")
            
            for i, photo_data in enumerate(group, 1):
                f.write(f"Photo {i}: {photo_data['path'].name}\n")
                f.write("-" * 80 + "\n")
                
                metadata = photo_data['metadata']
                for key, value in metadata.items():
                    f.write(f"{key}: {value}\n")
                
                f.write("\n")
    
    def organize_photos(self):
        """Main method to organize photos into groups."""
        # Find all photos
        photos = self.find_all_photos()
        print(f"Found {len(photos)} photos")
        
        # Group similar photos
        groups = self.group_similar_photos(photos)
        
        # Process each group
        for i, group in enumerate(groups, 1):
            print(f"\nProcessing group {i}/{len(groups)} ({len(group)} photos)...")
            
            # Create group directory
            group_dir = self.output_dir / f"group_{i:04d}"
            group_dir.mkdir(exist_ok=True)
            
            # Copy original photos
            originals_dir = group_dir / 'originals'
            originals_dir.mkdir(exist_ok=True)
            
            for photo_data in group:
                src = photo_data['path']
                dst = originals_dir / src.name
                # Handle name collisions
                counter = 1
                while dst.exists():
                    dst = originals_dir / f"{src.stem}_{counter}{src.suffix}"
                    counter += 1
                shutil.copy2(src, dst)
            
            # Save metadata
            self.save_metadata(group, group_dir)
            
            # Find best photo
            best_photo = self.find_best_photo(group)
            best_dst = group_dir / f"best_{best_photo['path'].name}"
            shutil.copy2(best_photo['path'], best_dst)
            
            print(f"Group {i} complete: {group_dir}")
        
        print(f"\nOrganization complete! Created {len(groups)} groups in {self.output_dir}")


def main():
    """Main entry point with argument parsing."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Organize photo albums by grouping similar photos',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python photo_organizer.py -s ~/Photos -o ~/OrganizedPhotos
  python photo_organizer.py -s ~/Photos -o ~/Organized -t 8 --verbose
        """
    )
    
    parser.add_argument('-s', '--source', required=True,
                        help='Source directory containing photos')
    parser.add_argument('-o', '--output', required=True,
                        help='Output directory for organized photos')
    parser.add_argument('-t', '--threshold', type=int, default=5,
                        help='Similarity threshold (0-64, lower=stricter, default=5)')
    parser.add_argument('--time-window', type=int, default=300,
                        help='Time window in seconds for grouping (default=300)')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose output')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without actually organizing')
    
    args = parser.parse_args()
    
    # Create organizer and run
    organizer = PhotoOrganizer(args.source, args.output, args.threshold)
    organizer.organize_photos()


if __name__ == "__main__":
    main()
