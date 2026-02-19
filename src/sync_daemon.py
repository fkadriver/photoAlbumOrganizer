"""
Sync daemon for continuous monitoring of Immich photo library.

Provides real-time sync by polling for new/modified assets and
processing them automatically.
"""

import logging
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from .processing_state import SyncState
from .photo_sources import Photo


class SyncDaemon:
    """
    Continuous sync daemon for monitoring and processing new Immich assets.

    Polls Immich at regular intervals for new or modified assets,
    then delegates to PhotoOrganizer for processing.
    """

    def __init__(self, photo_source, sync_state: SyncState,
                 poll_interval: int = 60,
                 enable_bidir_sync: bool = False,
                 conflict_strategy: str = 'remote_wins',
                 **organizer_config):
        """
        Initialize the sync daemon.

        Args:
            photo_source: ImmichPhotoSource or HybridPhotoSource instance
            sync_state: SyncState instance for persistence
            poll_interval: Seconds between polls (default: 60)
            enable_bidir_sync: Enable bi-directional sync
            conflict_strategy: Conflict resolution strategy
            **organizer_config: Additional config passed to PhotoOrganizer
        """
        self.photo_source = photo_source
        self.sync_state = sync_state
        self.poll_interval = poll_interval
        self.enable_bidir_sync = enable_bidir_sync
        self.conflict_strategy = conflict_strategy
        self.organizer_config = organizer_config

        self._running = False
        self._interrupted = False

        # Lazy import to avoid circular dependencies
        self._reconciler = None

    def start(self):
        """
        Start the daemon loop. Blocks until shutdown signal received.
        """
        self._running = True
        self._setup_signal_handlers()

        logging.info(f"Sync daemon started (poll interval: {self.poll_interval}s)")
        print(f"\nSync daemon started. Poll interval: {self.poll_interval}s")
        print("Press Ctrl+C to stop.\n")

        while self._running:
            try:
                changes_found = self._poll_cycle()
                if changes_found:
                    logging.info(f"Poll cycle completed with changes")
                else:
                    logging.debug("Poll cycle: no changes")
            except Exception as e:
                logging.error(f"Poll cycle failed: {e}")
                self.sync_state.record_error(str(e))
                print(f"Poll error: {e}")

            # Interruptible sleep
            if self._running:
                self._interruptible_sleep(self.poll_interval)

        # Final save on shutdown
        self.sync_state.save()
        logging.info("Sync daemon stopped gracefully")
        print("\nSync daemon stopped.")

    def stop(self):
        """Signal graceful shutdown."""
        logging.info("Shutdown requested")
        self._running = False

    def _setup_signal_handlers(self):
        """Setup SIGINT/SIGTERM handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            sig_name = 'SIGINT' if signum == signal.SIGINT else 'SIGTERM'
            logging.info(f"Received {sig_name}")
            print(f"\nReceived {sig_name}, shutting down...")
            self._running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _interruptible_sleep(self, seconds: int):
        """Sleep that can be interrupted by stop signal."""
        for _ in range(seconds):
            if not self._running:
                break
            time.sleep(1)

    def _poll_cycle(self) -> bool:
        """
        Execute one poll cycle.

        Returns:
            True if changes were found and processed
        """
        # Get last sync timestamp
        last_sync = self.sync_state.get_last_sync_time()

        if last_sync is None:
            # First run - use a reasonable default (1 hour ago)
            # This prevents processing entire library on first daemon start
            last_sync = datetime.now().isoformat()
            logging.info("First sync cycle - will watch for future changes")
            self.sync_state.set_last_sync_time(last_sync)
            self.sync_state.save()
            return False

        # Get modified assets from Immich
        media_type = self.organizer_config.get('media_type', 'image')
        modified_assets = self.photo_source.client.get_modified_assets(
            since=last_sync,
            skip_archived=True,
            media_type=media_type
        )

        if not modified_assets:
            return False

        logging.info(f"Found {len(modified_assets)} modified assets")
        print(f"Found {len(modified_assets)} modified asset(s)")

        # Convert to Photo objects
        photos = self._convert_assets_to_photos(modified_assets)

        if photos:
            # Process using organizer
            self._process_photos(photos)

        # Bi-directional sync if enabled
        if self.enable_bidir_sync:
            self._run_bidir_sync(modified_assets)

        # Update sync timestamp
        self.sync_state.set_last_sync_time(datetime.now().isoformat())
        self.sync_state.clear_error()
        self.sync_state.save()

        return True

    def _convert_assets_to_photos(self, assets) -> List[Photo]:
        """Convert ImmichAsset objects to Photo objects."""
        photos = []
        for asset in assets:
            photo = Photo(
                photo_id=asset.id,
                source='immich',
                metadata={
                    'asset_id': asset.id,
                    'filename': asset.original_file_name,
                    'filepath': asset.original_path,
                    'created_at': asset.file_created_at,
                    'updated_at': asset.updated_at,
                }
            )
            photos.append(photo)
        return photos

    def _process_photos(self, photos: List[Photo]):
        """Process photos using PhotoOrganizer."""
        # Lazy import to avoid circular dependencies
        from .organizer import PhotoOrganizer
        from .grouping import group_similar_photos

        # Create a mini-organizer for this batch
        organizer = PhotoOrganizer(
            photo_source=self.photo_source,
            output_dir=self.organizer_config.get('output_dir'),
            similarity_threshold=self.organizer_config.get('threshold', 5),
            time_window=self.organizer_config.get('time_window', 300),
            use_time_window=self.organizer_config.get('use_time_window', True),
            min_group_size=self.organizer_config.get('min_group_size', 3),
            tag_only=self.organizer_config.get('tag_only', False),
            verbose=self.organizer_config.get('verbose', False),
        )

        # Mark photos as discovered
        for photo in photos:
            organizer.state.mark_photo_discovered()

        # Group and process using the grouping module directly
        try:
            groups = group_similar_photos(
                photos=photos,
                photo_source=self.photo_source,
                state=organizer.state,
                extract_metadata_func=organizer.extract_metadata,
                get_datetime_func=organizer.get_datetime_from_metadata,
                similarity_threshold=organizer.similarity_threshold,
                use_time_window=organizer.use_time_window,
                time_window=organizer.time_window,
                min_group_size=organizer.min_group_size,
                threads=self.organizer_config.get('threads', 2),
                interrupted_flag=lambda: False,
                media_type=self.organizer_config.get('media_type', 'image'),
            )
            if groups:
                print(f"Found {len(groups)} group(s) in new assets")
                organizer._process_groups(groups)
        except Exception as e:
            logging.error(f"Failed to process photos: {e}")
            raise

    def _run_bidir_sync(self, assets):
        """Run bi-directional sync for the given assets."""
        if self._reconciler is None:
            from .sync_reconciler import SyncReconciler
            self._reconciler = SyncReconciler(
                client=self.photo_source.client,
                sync_state=self.sync_state,
                conflict_strategy=self.conflict_strategy
            )

        asset_ids = [a.id for a in assets]
        changes = self._reconciler.detect_changes(asset_ids)

        if changes:
            logging.info(f"Bi-dir sync: {len(changes)} asset(s) with changes")
            for asset_id, change in changes.items():
                self._reconciler.reconcile(asset_id, change)

    def get_status(self) -> Dict[str, Any]:
        """Get current daemon status."""
        return {
            'running': self._running,
            'poll_interval': self.poll_interval,
            'enable_bidir_sync': self.enable_bidir_sync,
            'conflict_strategy': self.conflict_strategy,
            'last_sync': self.sync_state.get_last_sync_time(),
            'total_cycles': self.sync_state.state.get('total_sync_cycles', 0),
            'pending_conflicts': len(self.sync_state.get_pending_conflicts()),
            'last_error': self.sync_state.state.get('last_error'),
        }


def run_daemon(photo_source, state_file: Path, poll_interval: int = 60,
               enable_bidir_sync: bool = False,
               conflict_strategy: str = 'remote_wins',
               **organizer_config):
    """
    Convenience function to run the sync daemon.

    Args:
        photo_source: ImmichPhotoSource or HybridPhotoSource
        state_file: Path to sync state file
        poll_interval: Seconds between polls
        enable_bidir_sync: Enable bi-directional sync
        conflict_strategy: Conflict resolution strategy
        **organizer_config: Additional organizer configuration
    """
    sync_state = SyncState(state_file)
    sync_state.load()  # Load existing state if any

    daemon = SyncDaemon(
        photo_source=photo_source,
        sync_state=sync_state,
        poll_interval=poll_interval,
        enable_bidir_sync=enable_bidir_sync,
        conflict_strategy=conflict_strategy,
        **organizer_config
    )

    daemon.start()
