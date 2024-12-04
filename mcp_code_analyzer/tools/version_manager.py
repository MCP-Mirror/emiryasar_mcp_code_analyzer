import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import shutil
import hashlib
from dataclasses import dataclass
from .base import BaseTool

logger = logging.getLogger(__name__)

@dataclass
class Version:
    """Version information container"""
    id: str
    timestamp: str
    hash: str
    metadata: Dict[str, Any]
    backup_path: Path

@dataclass
class ChangeInfo:
    """Change information container"""
    type: str  # 'modify', 'create', 'delete'
    timestamp: str
    description: str
    metadata: Dict[str, Any]

class VersionManager(BaseTool):
    """Advanced version control and change tracking tool"""

    def __init__(self):
        super().__init__()
        self._version_store = {}
        self._change_history = {}
        self._backup_root = Path('backups')
        self._metadata_file = self._backup_root / 'version_metadata.json'
        self._initialize_storage()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        operation = arguments.get('operation', 'create_version')
        target_path = arguments.get('path')

        if not target_path:
            return {"error": "Path is required"}

        operations = {
            'create_version': self._create_version,
            'restore_version': self._restore_version,
            'get_history': self._get_version_history,
            'compare_versions': self._compare_versions,
            'get_changes': self._get_changes,
            'cleanup': self._cleanup_versions
        }

        if operation not in operations:
            return {"error": f"Unknown operation: {operation}"}

        try:
            result = await operations[operation](Path(target_path), arguments)
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"VersionManager operation failed: {e}")
            return {"success": False, "error": str(e)}

    def _initialize_storage(self) -> None:
        """Initialize version storage"""
        try:
            self._backup_root.mkdir(parents=True, exist_ok=True)
            if self._metadata_file.exists():
                metadata = json.loads(self._metadata_file.read_text())
                self._version_store = metadata.get('versions', {})
                self._change_history = metadata.get('changes', {})
            else:
                self._save_metadata()
        except Exception as e:
            logger.error(f"Failed to initialize storage: {e}")

    def _save_metadata(self) -> None:
        """Save version metadata"""
        try:
            metadata = {
                'versions': self._version_store,
                'changes': self._change_history,
                'last_updated': datetime.now().isoformat()
            }
            self._metadata_file.write_text(json.dumps(metadata, indent=2))
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    async def _create_version(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create new version of a file"""
        try:
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")

            description = args.get('description', '')
            tags = args.get('tags', [])

            # Calculate file hash
            file_hash = self._calculate_file_hash(path)

            # Check if identical version exists
            for version in self._get_versions(path):
                if version.hash == file_hash:
                    return {
                        "message": "Identical version already exists",
                        "version_id": version.id,
                        "timestamp": version.timestamp
                    }

            # Create version ID
            version_id = self._generate_version_id(path)
            timestamp = datetime.now().isoformat()

            # Create backup
            backup_path = self._create_backup(path, version_id)

            # Store version information
            version = Version(
                id=version_id,
                timestamp=timestamp,
                hash=file_hash,
                metadata={
                    'description': description,
                    'tags': tags,
                    'size': path.stat().st_size,
                    'creator': args.get('creator', 'unknown')
                },
                backup_path=backup_path
            )

            self._add_version(path, version)

            # Record change
            change = ChangeInfo(
                type='create_version',
                timestamp=timestamp,
                description=description,
                metadata={
                    'version_id': version_id,
                    'tags': tags
                }
            )

            self._record_change(path, change)
            self._save_metadata()

            return {
                "version_id": version_id,
                "timestamp": timestamp,
                "backup_path": str(backup_path),
                "hash": file_hash
            }

        except Exception as e:
            raise RuntimeError(f"Failed to create version: {e}")

    async def _restore_version(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Restore file to specific version"""
        try:
            version_id = args.get('version_id')
            if not version_id:
                raise ValueError("Version ID is required")

            version = self._find_version(path, version_id)
            if not version:
                raise ValueError(f"Version not found: {version_id}")

            # Create backup of current state
            current_backup = self._create_backup(path, 'pre_restore_backup')

            # Restore from version
            shutil.copy2(version.backup_path, path)

            # Record change
            change = ChangeInfo(
                type='restore',
                timestamp=datetime.now().isoformat(),
                description=f"Restored to version {version_id}",
                metadata={
                    'version_id': version_id,
                    'previous_backup': str(current_backup)
                }
            )

            self._record_change(path, change)
            self._save_metadata()

            return {
                "message": "Version restored successfully",
                "version_id": version_id,
                "timestamp": version.timestamp,
                "previous_backup": str(current_backup)
            }

        except Exception as e:
            raise RuntimeError(f"Failed to restore version: {e}")

    async def _get_version_history(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get version history of a file"""
        try:
            versions = self._get_versions(path)
            changes = self._get_file_changes(path)

            return {
                "file": str(path),
                "versions": [
                    {
                        "id": v.id,
                        "timestamp": v.timestamp,
                        "hash": v.hash,
                        "metadata": v.metadata
                    }
                    for v in versions
                ],
                "changes": [
                    {
                        "type": c.type,
                        "timestamp": c.timestamp,
                        "description": c.description,
                        "metadata": c.metadata
                    }
                    for c in changes
                ],
                "statistics": {
                    "total_versions": len(versions),
                    "total_changes": len(changes),
                    "first_version": versions[0].timestamp if versions else None,
                    "last_version": versions[-1].timestamp if versions else None
                }
            }

        except Exception as e:
            raise RuntimeError(f"Failed to get version history: {e}")

    async def _compare_versions(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Compare two versions of a file"""
        try:
            version1_id = args.get('version1')
            version2_id = args.get('version2')

            if not (version1_id and version2_id):
                raise ValueError("Both version IDs are required")

            v1 = self._find_version(path, version1_id)
            v2 = self._find_version(path, version2_id)

            if not (v1 and v2):
                raise ValueError("One or both versions not found")

            # Compare files
            from difflib import unified_diff

            with open(v1.backup_path) as f1, open(v2.backup_path) as f2:
                diff = list(unified_diff(
                    f1.readlines(),
                    f2.readlines(),
                    fromfile=f'version_{version1_id}',
                    tofile=f'version_{version2_id}'
                ))

            return {
                "version1": {
                    "id": v1.id,
                    "timestamp": v1.timestamp,
                    "metadata": v1.metadata
                },
                "version2": {
                    "id": v2.id,
                    "timestamp": v2.timestamp,
                    "metadata": v2.metadata
                },
                "differences": {
                    "total_changes": len(diff),
                    "diff": diff
                },
                "analysis": {
                    "size_change": v2.metadata['size'] - v1.metadata['size'],
                    "time_between": (
                            datetime.fromisoformat(v2.timestamp) -
                            datetime.fromisoformat(v1.timestamp)
                    ).total_seconds()
                }
            }

        except Exception as e:
            raise RuntimeError(f"Failed to compare versions: {e}")

    async def _get_changes(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed change history"""
        try:
            changes = self._get_file_changes(path)
            filtered_changes = []

            # Apply filters
            change_type = args.get('type')
            start_date = args.get('start_date')
            end_date = args.get('end_date')

            for change in changes:
                if change_type and change.type != change_type:
                    continue

                change_date = datetime.fromisoformat(change.timestamp)

                if start_date and change_date < datetime.fromisoformat(start_date):
                    continue

                if end_date and change_date > datetime.fromisoformat(end_date):
                    continue

                filtered_changes.append(change)

            return {
                "file": str(path),
                "changes": [
                    {
                        "type": c.type,
                        "timestamp": c.timestamp,
                        "description": c.description,
                        "metadata": c.metadata
                    }
                    for c in filtered_changes
                ],
                "statistics": {
                    "total_changes": len(filtered_changes),
                    "changes_by_type": self._count_changes_by_type(filtered_changes)
                }
            }

        except Exception as e:
            raise RuntimeError(f"Failed to get changes: {e}")

    async def _cleanup_versions(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Clean up old versions"""
        try:
            keep_latest = args.get('keep_latest', 5)
            keep_days = args.get('keep_days', 30)

            versions = self._get_versions(path)
            if not versions:
                return {"message": "No versions to clean up"}

            cutoff_date = datetime.now().timestamp() - (keep_days * 86400)
            versions_to_delete = []
            kept_versions = []

            # Keep required number of latest versions
            if len(versions) > keep_latest:
                kept_versions = versions[-keep_latest:]
                versions_to_delete.extend(versions[:-keep_latest])

            # Process remaining versions
            for version in versions_to_delete[:]:
                version_date = datetime.fromisoformat(version.timestamp).timestamp()
                if version_date > cutoff_date:
                    versions_to_delete.remove(version)
                    kept_versions.append(version)

            # Delete versions
            for version in versions_to_delete:
                if version.backup_path.exists():
                    version.backup_path.unlink()

            # Update version store
            self._version_store[str(path)] = [
                {
                    'id': v.id,
                    'timestamp': v.timestamp,
                    'hash': v.hash,
                    'metadata': v.metadata,
                    'backup_path': str(v.backup_path)
                }
                for v in kept_versions
            ]

            self._save_metadata()

            return {
                "deleted_versions": len(versions_to_delete),
                "kept_versions": len(kept_versions),
                "space_freed": sum(v.metadata['size'] for v in versions_to_delete)
            }

        except Exception as e:
            raise RuntimeError(f"Failed to clean up versions: {e}")

    def _generate_version_id(self, path: Path) -> str:
        """Generate unique version ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_data = f"{path}:{timestamp}:{self._calculate_file_hash(path)}"
        return hashlib.md5(unique_data.encode()).hexdigest()[:12]

    def _calculate_file_hash(self, path: Path) -> str:
        """Calculate file hash"""
        hasher = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _create_backup(self, path: Path, version_id: str) -> Path:
        """Create backup of file"""
        backup_dir = self._backup_root / path.stem
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_path = backup_dir / f"{version_id}{path.suffix}"
        shutil.copy2(path, backup_path)

        return backup_path

    def _add_version(self, path: Path, version: Version) -> None:
        """Add version to store"""
        if str(path) not in self._version_store:
            self._version_store[str(path)] = []

        self._version_store[str(path)].append({
            'id': version.id,
            'timestamp': version.timestamp,
            'hash': version.hash,
            'metadata': version.metadata,
            'backup_path': str(version.backup_path)
        })

    def _record_change(self, path: Path, change: ChangeInfo) -> None:
        """Record a change"""
        if str(path) not in self._change_history:
            self._change_history[str(path)] = []

        self._change_history[str(path)].append({
            'type': change.type,
            'timestamp': change.timestamp,
            'description': change.description,
            'metadata': change.metadata
        })

    def _get_versions(self, path: Path) -> List[Version]:
        """Get all versions of a file"""
        versions = []
        for v in self._version_store.get(str(path), []):
            versions.append(Version(
                id=v['id'],
                timestamp=v['timestamp'],
                hash=v['hash'],
                metadata=v['metadata'],
                backup_path=Path(v['backup_path'])
            ))
        return sorted(versions, key=lambda v: v.timestamp)

    def _find_version(self, path: Path, version_id: str) -> Optional[Version]:
        """Find specific version"""
        versions = self._get_versions(path)
        for version in versions:
            if version.id == version_id:
                return version
        return None

    def _get_file_changes(self, path: Path) -> List[ChangeInfo]:
        """Get all changes for a file"""
        changes = []
        for c in self._change_history.get(str(path), []):
            changes.append(ChangeInfo(
                type=c['type'],
                timestamp=c['timestamp'],
                description=c['description'],
                metadata=c['metadata']
            ))
        return sorted(changes, key=lambda c: c.timestamp)

    def _count_changes_by_type(self, changes: List[ChangeInfo]) -> Dict[str, int]:
        """Count changes by type"""
        counts = {}
        for change in changes:
            counts[change.type] = counts.get(change.type, 0) + 1
        return counts

    async def _cleanup_backup_directory(self) -> None:
        """Clean up backup directory"""
        try:
            # Find orphaned backups
            used_backups = set()
            for versions in self._version_store.values():
                for version in versions:
                    used_backups.add(version['backup_path'])

            # Remove unused backup files
            for backup_file in self._backup_root.rglob('*'):
                if backup_file.is_file() and str(backup_file) not in used_backups:
                    try:
                        backup_file.unlink()
                    except Exception as e:
                        logger.error(f"Failed to remove orphaned backup {backup_file}: {e}")

            # Remove empty directories
            for backup_dir in sorted(self._backup_root.rglob('*'), reverse=True):
                if backup_dir.is_dir():
                    try:
                        backup_dir.rmdir()  # Will only succeed if directory is empty
                    except Exception:
                        pass  # Directory not empty, skip

        except Exception as e:
            logger.error(f"Failed to cleanup backup directory: {e}")

    async def _validate_backups(self) -> Dict[str, Any]:
        """Validate backup integrity"""
        validation_results = {
            "valid_backups": [],
            "invalid_backups": [],
            "missing_backups": []
        }

        try:
            for file_path, versions in self._version_store.items():
                for version in versions:
                    backup_path = Path(version['backup_path'])
                    if not backup_path.exists():
                        validation_results["missing_backups"].append({
                            "file": file_path,
                            "version_id": version['id'],
                            "backup_path": str(backup_path)
                        })
                        continue

                    # Verify hash
                    current_hash = self._calculate_file_hash(backup_path)
                    if current_hash != version['hash']:
                        validation_results["invalid_backups"].append({
                            "file": file_path,
                            "version_id": version['id'],
                            "expected_hash": version['hash'],
                            "actual_hash": current_hash
                        })
                    else:
                        validation_results["valid_backups"].append({
                            "file": file_path,
                            "version_id": version['id'],
                            "backup_path": str(backup_path)
                        })

            return validation_results

        except Exception as e:
            logger.error(f"Failed to validate backups: {e}")
            return validation_results

    async def _analyze_storage_usage(self) -> Dict[str, Any]:
        """Analyze backup storage usage"""
        try:
            storage_info = {
                "total_size": 0,
                "backup_count": 0,
                "files": {},
                "usage_by_date": {}
            }

            for file_path, versions in self._version_store.items():
                file_info = {
                    "versions": len(versions),
                    "total_size": 0,
                    "oldest_version": None,
                    "newest_version": None
                }

                for version in versions:
                    backup_path = Path(version['backup_path'])
                    if backup_path.exists():
                        size = backup_path.stat().st_size
                        date = version['timestamp'][:10]  # YYYY-MM-DD

                        storage_info["total_size"] += size
                        file_info["total_size"] += size
                        storage_info["backup_count"] += 1

                        # Track usage by date
                        storage_info["usage_by_date"][date] = \
                            storage_info["usage_by_date"].get(date, 0) + size

                        # Track version timestamps
                        if not file_info["oldest_version"] or \
                                version['timestamp'] < file_info["oldest_version"]:
                            file_info["oldest_version"] = version['timestamp']
                        if not file_info["newest_version"] or \
                                version['timestamp'] > file_info["newest_version"]:
                            file_info["newest_version"] = version['timestamp']

                storage_info["files"][file_path] = file_info

            # Add summary statistics
            storage_info["summary"] = {
                "average_size_per_backup": (
                    storage_info["total_size"] / storage_info["backup_count"]
                    if storage_info["backup_count"] > 0 else 0
                ),
                "average_versions_per_file": (
                    storage_info["backup_count"] / len(storage_info["files"])
                    if storage_info["files"] else 0
                ),
                "total_size_human": self._format_size(storage_info["total_size"])
            }

            return storage_info

        except Exception as e:
            logger.error(f"Failed to analyze storage usage: {e}")
            return {"error": str(e)}

    def _format_size(self, size: int) -> str:
        """Format size in bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"