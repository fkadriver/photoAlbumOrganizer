"""
Processing state management for resume capability.

Allows long-running photo organization jobs to be interrupted and resumed.
"""

import pickle
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import hashlib


class ProcessingState:
    """Manages processing state for resume capability."""

    def __init__(self, state_file: Path):
        """
        Initialize processing state.

        Args:
            state_file: Path to state file for persistence
        """
        self.state_file = Path(state_file)
        self._lock = threading.Lock()
        self.state = {
            'version': '1.0',
            'started_at': None,
            'last_saved': None,
            'source_type': None,
            'source_path': None,
            'output_path': None,
            'threshold': None,
            'time_window': None,
            'use_time_window': None,

            # Processing progress
            'photos_discovered': 0,
            'photos_hashed': 0,
            'groups_found': 0,
            'groups_processed': 0,

            # Cached data
            'processed_hashes': {},  # {photo_id: hash_value}
            'completed_groups': [],  # List of group indices
            'photo_metadata': {},     # {photo_id: metadata}

            # Statistics
            'total_processing_time': 0.0,
        }

    def save(self):
        """Save current state to disk (thread-safe)."""
        with self._lock:
            self._save_unlocked()

    def _save_unlocked(self):
        """Save current state to disk (caller must hold self._lock)."""
        self.state['last_saved'] = datetime.now().isoformat()

        # Create parent directory if needed
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Save with atomic write (write to temp, then rename)
        temp_file = self.state_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'wb') as f:
                pickle.dump(self.state, f)
            temp_file.replace(self.state_file)
        except Exception as e:
            print(f"Warning: Failed to save state: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def load(self) -> bool:
        """
        Load state from disk.

        Returns:
            True if state was loaded successfully, False otherwise
        """
        if not self.state_file.exists():
            return False

        try:
            with open(self.state_file, 'rb') as f:
                loaded_state = pickle.load(f)

            # Verify version compatibility
            if loaded_state.get('version') != '1.0':
                print(f"Warning: State file version mismatch")
                return False

            self.state = loaded_state
            return True

        except Exception as e:
            print(f"Warning: Failed to load state: {e}")
            return False

    def initialize(self, source_type: str, source_path: Optional[str],
                   output_path: Optional[str], threshold: int,
                   time_window: int, use_time_window: bool):
        """Initialize state for a new run."""
        self.state['started_at'] = datetime.now().isoformat()
        self.state['source_type'] = source_type
        self.state['source_path'] = source_path
        self.state['output_path'] = output_path
        self.state['threshold'] = threshold
        self.state['time_window'] = time_window
        self.state['use_time_window'] = use_time_window

    def verify_compatibility(self, source_type: str, source_path: Optional[str],
                            threshold: int) -> bool:
        """
        Verify that current run is compatible with saved state.

        Returns:
            True if compatible, False if parameters have changed
        """
        if (self.state['source_type'] != source_type or
            self.state['source_path'] != source_path or
            self.state['threshold'] != threshold):
            return False
        return True

    def mark_photo_discovered(self):
        """Increment discovered photo count."""
        self.state['photos_discovered'] += 1

    def mark_hash_computed(self, photo_id: str, hash_value):
        """
        Mark a photo as hashed.

        Args:
            photo_id: Photo identifier
            hash_value: Computed hash value
        """
        with self._lock:
            self.state['processed_hashes'][photo_id] = str(hash_value)
            self.state['photos_hashed'] += 1

            # Auto-save every 50 photos
            if self.state['photos_hashed'] % 50 == 0:
                self._save_unlocked()

    def get_cached_hash(self, photo_id: str) -> Optional[str]:
        """Get cached hash for a photo."""
        with self._lock:
            return self.state['processed_hashes'].get(photo_id)

    def set_groups_found(self, count: int):
        """Set total number of groups found."""
        self.state['groups_found'] = count

    def mark_group_completed(self, group_index: int):
        """
        Mark a group as completed.

        Args:
            group_index: Index of completed group (1-based)
        """
        if group_index not in self.state['completed_groups']:
            self.state['completed_groups'].append(group_index)
            self.state['groups_processed'] += 1
            self.save()

    def is_group_completed(self, group_index: int) -> bool:
        """Check if a group has been completed."""
        return group_index in self.state['completed_groups']

    def get_progress_summary(self) -> str:
        """Get human-readable progress summary."""
        lines = []
        lines.append(f"Progress Summary:")
        lines.append(f"  Started: {self.state['started_at']}")
        lines.append(f"  Last saved: {self.state['last_saved']}")
        lines.append(f"  Photos hashed: {self.state['photos_hashed']}/{self.state['photos_discovered']}")
        lines.append(f"  Groups processed: {self.state['groups_processed']}/{self.state['groups_found']}")

        if self.state['groups_found'] > 0:
            percent = (self.state['groups_processed'] / self.state['groups_found']) * 100
            lines.append(f"  Completion: {percent:.1f}%")

        return '\n'.join(lines)

    def cleanup(self):
        """Remove state file after successful completion."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
                print(f"State file removed: {self.state_file}")
        except Exception as e:
            print(f"Warning: Could not remove state file: {e}")

    def get_state_info(self) -> Dict[str, Any]:
        """Get state information for display."""
        return {
            'state_file': str(self.state_file),
            'started_at': self.state['started_at'],
            'last_saved': self.state['last_saved'],
            'photos_hashed': self.state['photos_hashed'],
            'groups_processed': self.state['groups_processed'],
            'groups_found': self.state['groups_found'],
        }
