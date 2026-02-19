"""
Bi-directional sync reconciliation for Immich integration.

Handles detecting and resolving conflicts when assets are modified
both locally (via photo organizer) and remotely (via Immich UI).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from .processing_state import SyncState


@dataclass
class ChangeRecord:
    """Records detected changes for an asset."""
    asset_id: str
    local_changes: Dict[str, tuple] = field(default_factory=dict)  # {field: (old, new)}
    remote_changes: Dict[str, tuple] = field(default_factory=dict)  # {field: (old, new)}
    is_conflict: bool = False
    conflict_fields: List[str] = field(default_factory=list)


class SyncReconciler:
    """
    Handles bi-directional synchronization between local state and Immich.

    Detects and resolves conflicts when the same asset is modified both
    locally (via photo organizer) and remotely (via Immich UI).
    """

    # Fields we track for bi-directional sync
    SYNC_FIELDS = ['is_favorite', 'is_archived']

    def __init__(self, client, sync_state: SyncState,
                 conflict_strategy: str = 'remote_wins'):
        """
        Initialize the reconciler.

        Args:
            client: ImmichClient instance
            sync_state: SyncState for tracking sync records
            conflict_strategy: 'remote_wins', 'local_wins', or 'manual'
        """
        self.client = client
        self.sync_state = sync_state
        self.conflict_strategy = conflict_strategy

    def detect_changes(self, asset_ids: List[str]) -> Dict[str, ChangeRecord]:
        """
        Compare local state vs Immich state for given assets.

        Args:
            asset_ids: List of asset IDs to check

        Returns:
            Dict mapping asset_id to ChangeRecord describing differences
        """
        changes = {}

        for asset_id in asset_ids:
            local_record = self.sync_state.get_asset_sync_record(asset_id)
            if not local_record:
                # No local record - this is a new asset, not a change
                continue

            # Fetch current remote state
            remote_asset = self.client.get_asset_info(asset_id)
            if not remote_asset:
                logging.warning(f"Asset {asset_id} not found in Immich")
                continue

            change = self._compare_states(asset_id, local_record, remote_asset)
            if change.local_changes or change.remote_changes:
                changes[asset_id] = change

        return changes

    def _compare_states(self, asset_id: str, local_record: Dict,
                        remote_asset) -> ChangeRecord:
        """Compare local record with remote asset state."""
        change = ChangeRecord(asset_id=asset_id)
        local_state = local_record.get('local_state', {})
        sync_snapshot = local_record.get('sync_snapshot', {})

        # Compare each tracked field
        for field in self.SYNC_FIELDS:
            local_value = local_state.get(field)
            remote_value = getattr(remote_asset, field, None)
            snapshot_value = sync_snapshot.get(field)

            # Detect local changes (local differs from snapshot)
            if local_value != snapshot_value and local_value is not None:
                change.local_changes[field] = (snapshot_value, local_value)

            # Detect remote changes (remote differs from snapshot)
            if remote_value != snapshot_value and remote_value is not None:
                change.remote_changes[field] = (snapshot_value, remote_value)

        # Check for conflicts (same field changed both locally and remotely)
        for field in change.local_changes:
            if field in change.remote_changes:
                # Only a conflict if they changed to different values
                _, local_new = change.local_changes[field]
                _, remote_new = change.remote_changes[field]
                if local_new != remote_new:
                    change.is_conflict = True
                    change.conflict_fields.append(field)

        return change

    def reconcile(self, asset_id: str, change: ChangeRecord) -> bool:
        """
        Reconcile a single asset based on detected changes.

        Args:
            asset_id: Asset ID to reconcile
            change: ChangeRecord describing the changes

        Returns:
            True if reconciled successfully, False if conflict needs manual resolution
        """
        if not change.is_conflict:
            # No conflict - apply changes
            if change.remote_changes:
                self._apply_remote_to_local(asset_id, change.remote_changes)
            if change.local_changes:
                self._apply_local_to_remote(asset_id, change.local_changes)
            self._update_sync_snapshot(asset_id)
            return True

        # Handle conflict based on strategy
        if self.conflict_strategy == 'remote_wins':
            self._apply_remote_to_local(asset_id, change.remote_changes)
            logging.info(f"Conflict on {asset_id}: remote wins (fields: {change.conflict_fields})")
            self._update_sync_snapshot(asset_id)
            return True

        elif self.conflict_strategy == 'local_wins':
            self._apply_local_to_remote(asset_id, change.local_changes)
            logging.info(f"Conflict on {asset_id}: local wins (fields: {change.conflict_fields})")
            self._update_sync_snapshot(asset_id)
            return True

        elif self.conflict_strategy == 'manual':
            # Record conflict for manual resolution
            self.sync_state.add_conflict({
                'asset_id': asset_id,
                'local_changes': change.local_changes,
                'remote_changes': change.remote_changes,
                'conflict_fields': change.conflict_fields
            })
            logging.warning(f"Conflict on {asset_id}: pending manual resolution")
            return False

        return False

    def _apply_remote_to_local(self, asset_id: str, changes: Dict[str, tuple]):
        """Apply remote changes to local state."""
        local_record = self.sync_state.get_asset_sync_record(asset_id) or {}
        local_state = local_record.get('local_state', {})

        for field, (_, new_value) in changes.items():
            local_state[field] = new_value

        local_record['local_state'] = local_state
        local_record['last_remote_update'] = datetime.now().isoformat()
        self.sync_state.update_asset_sync_record(asset_id, local_record)

        logging.debug(f"Applied remote changes to {asset_id}: {list(changes.keys())}")

    def _apply_local_to_remote(self, asset_id: str, changes: Dict[str, tuple]):
        """Apply local changes to Immich."""
        update_kwargs = {}

        for field, (_, new_value) in changes.items():
            if field == 'is_favorite':
                update_kwargs['is_favorite'] = new_value
            elif field == 'is_archived':
                update_kwargs['is_archived'] = new_value

        if update_kwargs:
            success = self.client.update_asset(asset_id, **update_kwargs)
            if success:
                logging.debug(f"Applied local changes to Immich {asset_id}: {list(changes.keys())}")
            else:
                logging.error(f"Failed to apply local changes to {asset_id}")

    def _update_sync_snapshot(self, asset_id: str):
        """Update the sync snapshot to current remote state."""
        remote_asset = self.client.get_asset_info(asset_id)
        if not remote_asset:
            return

        local_record = self.sync_state.get_asset_sync_record(asset_id) or {}
        local_record['sync_snapshot'] = {
            'is_favorite': remote_asset.is_favorite,
            'is_archived': remote_asset.is_archived,
        }
        local_record['last_sync'] = datetime.now().isoformat()
        self.sync_state.update_asset_sync_record(asset_id, local_record)

    def push_local_changes(self, asset_ids: List[str]):
        """Push all pending local changes to Immich."""
        for asset_id in asset_ids:
            local_record = self.sync_state.get_asset_sync_record(asset_id)
            if not local_record:
                continue

            local_state = local_record.get('local_state', {})
            sync_snapshot = local_record.get('sync_snapshot', {})

            # Find fields that differ
            changes = {}
            for field in self.SYNC_FIELDS:
                local_value = local_state.get(field)
                snapshot_value = sync_snapshot.get(field)
                if local_value != snapshot_value and local_value is not None:
                    changes[field] = (snapshot_value, local_value)

            if changes:
                self._apply_local_to_remote(asset_id, changes)
                self._update_sync_snapshot(asset_id)

    def pull_remote_changes(self, asset_ids: List[str]):
        """Pull all remote changes from Immich to local state."""
        for asset_id in asset_ids:
            remote_asset = self.client.get_asset_info(asset_id)
            if not remote_asset:
                continue

            local_record = self.sync_state.get_asset_sync_record(asset_id) or {}
            local_state = local_record.get('local_state', {})

            # Update local state from remote
            local_state['is_favorite'] = remote_asset.is_favorite
            local_state['is_archived'] = remote_asset.is_archived

            local_record['local_state'] = local_state
            local_record['last_remote_update'] = datetime.now().isoformat()
            self.sync_state.update_asset_sync_record(asset_id, local_record)
            self._update_sync_snapshot(asset_id)

    def initialize_asset_tracking(self, asset_id: str, is_best: bool = False,
                                  group_index: Optional[int] = None):
        """
        Initialize tracking for an asset after processing.

        Should be called after the organizer processes an asset.

        Args:
            asset_id: Asset ID to track
            is_best: Whether this is the best photo in its group
            group_index: Group index if part of a group
        """
        remote_asset = self.client.get_asset_info(asset_id)
        if not remote_asset:
            return

        record = {
            'local_state': {
                'is_favorite': remote_asset.is_favorite,
                'is_archived': remote_asset.is_archived,
                'is_best': is_best,
                'group_index': group_index,
            },
            'sync_snapshot': {
                'is_favorite': remote_asset.is_favorite,
                'is_archived': remote_asset.is_archived,
            },
            'last_sync': datetime.now().isoformat(),
            'last_local_update': datetime.now().isoformat(),
            'last_remote_update': remote_asset.updated_at,
        }

        self.sync_state.update_asset_sync_record(asset_id, record)
