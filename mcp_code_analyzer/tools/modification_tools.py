import logging
from pathlib import Path
from typing import Dict, Any,  Optional
from datetime import datetime
import hashlib
import json
from dataclasses import dataclass
from .base import BaseTool

logger = logging.getLogger(__name__)

@dataclass
class CodeChange:
    """Represents a code change"""
    file_path: str
    change_type: str  # modify/insert/delete
    section: Dict[str, int]  # start, end positions
    original_content: str
    new_content: str
    metadata: Dict[str, Any]

@dataclass
class ChangeResult:
    """Result of a change operation"""
    success: bool
    change_id: Optional[str] = None
    backup_path: Optional[str] = None
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class CodeModifier(BaseTool):
    """Advanced code modification tool"""

    def __init__(self):
        super().__init__()
        self._pending_changes = {}
        self._change_history = {}

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        operation = arguments.get('operation', 'modify')
        file_path = arguments.get('file_path')

        if not file_path:
            return {"error": "File path is required"}

        operations = {
            'modify': self._modify_code,
            'insert': self._insert_code,
            'delete': self._delete_code,
            'preview': self._preview_changes,
            'validate': self._validate_changes
        }

        if operation not in operations:
            return {"error": f"Unknown operation: {operation}"}

        try:
            result = await operations[operation](Path(file_path), arguments)
            return result if isinstance(result, dict) else {"success": True, "data": result}
        except Exception as e:
            logger.error(f"CodeModifier operation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _modify_code(self, file_path: Path, args: Dict[str, Any]) -> ChangeResult:
        """Modify code in specified section"""
        try:
            section = args.get('section', {})
            new_content = args.get('content', '')

            if not all([section.get('start'), section.get('end')]):
                raise ValueError("Invalid section specification")

            # Read original content
            original_content = self._read_section(file_path, section)

            # Create change record
            change = CodeChange(
                file_path=str(file_path),
                change_type='modify',
                section=section,
                original_content=original_content,
                new_content=new_content,
                metadata={
                    'timestamp': datetime.now().isoformat(),
                    'description': args.get('description', ''),
                    'author': args.get('author', 'unknown')
                }
            )

            # Generate change ID
            change_id = self._generate_change_id(change)

            # Store pending change
            self._pending_changes[change_id] = change

            # Create backup
            backup_path = await self._create_backup(file_path)

            return ChangeResult(
                success=True,
                change_id=change_id,
                backup_path=str(backup_path),
                details={
                    'section': section,
                    'original_size': len(original_content),
                    'new_size': len(new_content)
                }
            )

        except Exception as e:
            return ChangeResult(
                success=False,
                error_message=str(e)
            )

    async def _insert_code(self, file_path: Path, args: Dict[str, Any]) -> ChangeResult:
        """Insert code at specified position"""
        try:
            position = args.get('position')
            new_content = args.get('content', '')

            if position is None:
                raise ValueError("Insert position is required")

            change = CodeChange(
                file_path=str(file_path),
                change_type='insert',
                section={'start': position, 'end': position},
                original_content='',
                new_content=new_content,
                metadata={
                    'timestamp': datetime.now().isoformat(),
                    'description': args.get('description', ''),
                    'author': args.get('author', 'unknown')
                }
            )

            change_id = self._generate_change_id(change)
            self._pending_changes[change_id] = change
            backup_path = await self._create_backup(file_path)

            return ChangeResult(
                success=True,
                change_id=change_id,
                backup_path=str(backup_path),
                details={'position': position, 'content_size': len(new_content)}
            )

        except Exception as e:
            return ChangeResult(
                success=False,
                error_message=str(e)
            )

    async def _delete_code(self, file_path: Path, args: Dict[str, Any]) -> ChangeResult:
        """Delete code in specified section"""
        try:
            section = args.get('section', {})
            if not all([section.get('start'), section.get('end')]):
                raise ValueError("Invalid section specification")

            original_content = self._read_section(file_path, section)

            change = CodeChange(
                file_path=str(file_path),
                change_type='delete',
                section=section,
                original_content=original_content,
                new_content='',
                metadata={
                    'timestamp': datetime.now().isoformat(),
                    'description': args.get('description', ''),
                    'author': args.get('author', 'unknown')
                }
            )

            change_id = self._generate_change_id(change)
            self._pending_changes[change_id] = change
            backup_path = await self._create_backup(file_path)

            return ChangeResult(
                success=True,
                change_id=change_id,
                backup_path=str(backup_path),
                details={'section': section, 'deleted_size': len(original_content)}
            )

        except Exception as e:
            return ChangeResult(
                success=False,
                error_message=str(e)
            )

    async def _preview_changes(self, file_path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Preview pending changes"""
        change_id = args.get('change_id')

        if change_id and change_id not in self._pending_changes:
            return {"error": "Change ID not found"}

        try:
            changes = [self._pending_changes[change_id]] if change_id else list(self._pending_changes.values())

            preview = []
            for change in changes:
                if str(file_path) == change.file_path:
                    preview.append({
                        'type': change.change_type,
                        'section': change.section,
                        'original': change.original_content,
                        'modified': change.new_content,
                        'metadata': change.metadata
                    })

            return {
                'file': str(file_path),
                'changes': preview,
                'total_changes': len(preview)
            }

        except Exception as e:
            return {"error": f"Preview failed: {e}"}

    async def _validate_changes(self, file_path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate pending changes"""
        try:
            validation_results = []
            conflicting_changes = []

            # Get all changes for this file
            file_changes = [change for change in self._pending_changes.values()
                            if change.file_path == str(file_path)]

            # Sort changes by section start
            file_changes.sort(key=lambda x: x.section['start'])

            # Check for overlapping sections
            for i, change in enumerate(file_changes[:-1]):
                next_change = file_changes[i + 1]
                if change.section['end'] > next_change.section['start']:
                    conflicting_changes.extend([change, next_change])

            # Validate each change
            for change in file_changes:
                validation_result = {
                    'change_type': change.change_type,
                    'section': change.section,
                    'checks': []
                }

                # Check section boundaries
                if change.section['start'] < 0:
                    validation_result['checks'].append({
                        'type': 'error',
                        'message': 'Invalid start position'
                    })

                # Check content validity
                if change.change_type == 'modify':
                    if not change.new_content.strip():
                        validation_result['checks'].append({
                            'type': 'warning',
                            'message': 'New content is empty'
                        })

                validation_results.append(validation_result)

            return {
                'valid': not conflicting_changes,
                'validation_results': validation_results,
                'conflicts': [
                    {
                        'change_1': {'type': c1.change_type, 'section': c1.section},
                        'change_2': {'type': c2.change_type, 'section': c2.section}
                    }
                    for c1, c2 in zip(conflicting_changes[::2], conflicting_changes[1::2])
                ] if conflicting_changes else []
            }

        except Exception as e:
            return {"error": f"Validation failed: {e}"}

    def _read_section(self, file_path: Path, section: Dict[str, int]) -> str:
        """Read content from specified section"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return content[section['start']:section['end']]

    async def _create_backup(self, file_path: Path) -> Path:
        """Create backup of the file"""
        backup_path = file_path.parent / f"{file_path.stem}_backup_{datetime.now():%Y%m%d_%H%M%S}{file_path.suffix}"
        backup_path.write_bytes(file_path.read_bytes())
        return backup_path

    def _generate_change_id(self, change: CodeChange) -> str:
        """Generate unique ID for change"""
        data = f"{change.file_path}:{change.change_type}:{json.dumps(change.section)}:{datetime.now().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()[:12]

class ChangeManager(BaseTool):
    """Manages code changes and their application"""

    def __init__(self):
        super().__init__()
        self._applied_changes = {}
        self._change_stack = []

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        operation = arguments.get('operation', 'apply')

        operations = {
            'apply': self._apply_changes,
            'revert': self._revert_changes,
            'status': self._get_status,
            'history': self._get_history
        }

        if operation not in operations:
            return {"error": f"Unknown operation: {operation}"}

        try:
            result = await operations[operation](arguments)
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"ChangeManager operation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _apply_changes(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Apply pending changes"""
        file_path = args.get('file_path')
        change_ids = args.get('change_ids', [])

        if not file_path:
            return {"error": "File path is required"}

        try:
            path = Path(file_path)
            if not path.exists():
                return {"error": "File not found"}

            # Get CodeModifier instance
            code_modifier = self.get_tool('code_modifier')
            if not code_modifier:
                return {"error": "CodeModifier tool not available"}

            # Get changes to apply
            changes = []
            for change_id in change_ids:
                if change_id in code_modifier._pending_changes:
                    changes.append(code_modifier._pending_changes[change_id])
                else:
                    return {"error": f"Change ID not found: {change_id}"}

            # Sort changes by position (reverse order to handle positions correctly)
            changes.sort(key=lambda x: x.section['start'], reverse=True)

            # Read original content
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Apply changes
            modified_content = content
            applied = []

            for change in changes:
                if change.change_type == 'modify':
                    modified_content = (
                            modified_content[:change.section['start']] +
                            change.new_content +
                            modified_content[change.section['end']:]
                    )
                elif change.change_type == 'insert':
                    modified_content = (
                            modified_content[:change.section['start']] +
                            change.new_content +
                            modified_content[change.section['start']:]
                    )
                elif change.change_type == 'delete':
                    modified_content = (
                            modified_content[:change.section['start']] +
                            modified_content[change.section['end']:]
                    )

                applied.append(change)

            # Write modified content
            with open(path, 'w', encoding='utf-8') as f:
                f.write(modified_content)

            # Update change records
            for change in applied:
                change_id = code_modifier._generate_change_id(change)
                self._applied_changes[change_id] = change
                self._change_stack.append(change_id)
                del code_modifier._pending_changes[change_id]

            return {
                "message": "Changes applied successfully",
                "applied_changes": len(applied),
                "file": str(path)
            }

        except Exception as e:
            return {"error": f"Failed to apply changes: {e}"}

    async def _revert_changes(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Revert applied changes"""
        file_path = args.get('file_path')
        change_ids = args.get('change_ids', [])

        if not file_path:
            return {"error": "File path is required"}

        try:
            path = Path(file_path)
            if not path.exists():
                return {"error": "File not found"}

            # Get changes to revert
            changes_to_revert = []
            for change_id in change_ids:
                if change_id in self._applied_changes:
                    changes_to_revert.append(self._applied_changes[change_id])
                else:
                    return {"error": f"Change ID not found: {change_id}"}

            # Sort changes by position (forward order for reverting)
            changes_to_revert.sort(key=lambda x: x.section['start'])

            # Read current content
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Revert changes
            reverted_content = content
            reverted = []

            for change in changes_to_revert:
                if change.change_type == 'modify':
                    reverted_content = (
                            reverted_content[:change.section['start']] +
                            change.original_content +
                            reverted_content[change.section['end']:]
                    )
                elif change.change_type == 'insert':
                    # Remove inserted content
                    reverted_content = (
                            reverted_content[:change.section['start']] +
                            reverted_content[change.section['start'] + len(change.new_content):]
                    )
                elif change.change_type == 'delete':
                    # Restore deleted content
                    reverted_content = (
                            reverted_content[:change.section['start']] +
                            change.original_content +
                            reverted_content[change.section['start']:]
                    )

                reverted.append(change)

            # Write reverted content
            with open(path, 'w', encoding='utf-8') as f:
                f.write(reverted_content)

            # Update change records
            for change in reverted:
                change_id = self._generate_change_id(change)
                del self._applied_changes[change_id]
                self._change_stack.remove(change_id)

            return {
                "message": "Changes reverted successfully",
                "reverted_changes": len(reverted),
                "file": str(path)
            }

        except Exception as e:
            return {"error": f"Failed to revert changes: {e}"}

    async def _get_status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get current change status"""
        file_path = args.get('file_path')

        try:
            # Get CodeModifier instance
            code_modifier = self.get_tool('code_modifier')
            if not code_modifier:
                return {"error": "CodeModifier tool not available"}

            # Get all changes for the file
            pending_changes = [
                change for change in code_modifier._pending_changes.values()
                if change.file_path == file_path
            ]

            applied_changes = [
                change for change in self._applied_changes.values()
                if change.file_path == file_path
            ]

            return {
                "file": file_path,
                "status": {
                    "pending_changes": len(pending_changes),
                    "applied_changes": len(applied_changes)
                },
                "changes": {
                    "pending": [
                        {
                            "type": change.change_type,
                            "section": change.section,
                            "metadata": change.metadata
                        }
                        for change in pending_changes
                    ],
                    "applied": [
                        {
                            "type": change.change_type,
                            "section": change.section,
                            "metadata": change.metadata
                        }
                        for change in applied_changes
                    ]
                }
            }

        except Exception as e:
            return {"error": f"Failed to get status: {e}"}

    async def _get_history(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get change history"""
        file_path = args.get('file_path')
        limit = args.get('limit', 10)

        try:
            # Get changes from stack (most recent first)
            recent_changes = []
            for change_id in reversed(self._change_stack[-limit:]):
                change = self._applied_changes.get(change_id)
                if change and change.file_path == file_path:
                    recent_changes.append({
                        "id": change_id,
                        "type": change.change_type,
                        "section": change.section,
                        "metadata": change.metadata,
                        "size": {
                            "original": len(change.original_content),
                            "modified": len(change.new_content)
                        }
                    })

            return {
                "file": file_path,
                "history": {
                    "total_changes": len([c for c in self._applied_changes.values()
                                          if c.file_path == file_path]),
                    "recent_changes": recent_changes
                },
                "statistics": self._calculate_history_stats(file_path)
            }

        except Exception as e:
            return {"error": f"Failed to get history: {e}"}

    def _calculate_history_stats(self, file_path: str) -> Dict[str, Any]:
        """Calculate history statistics"""
        file_changes = [c for c in self._applied_changes.values()
                        if c.file_path == file_path]

        if not file_changes:
            return {}

        modifications = sum(1 for c in file_changes if c.change_type == 'modify')
        insertions = sum(1 for c in file_changes if c.change_type == 'insert')
        deletions = sum(1 for c in file_changes if c.change_type == 'delete')

        total_original_size = sum(len(c.original_content) for c in file_changes)
        total_modified_size = sum(len(c.new_content) for c in file_changes)

        return {
            "change_counts": {
                "modifications": modifications,
                "insertions": insertions,
                "deletions": deletions
            },
            "size_impact": {
                "original_size": total_original_size,
                "modified_size": total_modified_size,
                "size_difference": total_modified_size - total_original_size
            },
            "time_stats": {
                "first_change": min(c.metadata['timestamp'] for c in file_changes),
                "last_change": max(c.metadata['timestamp'] for c in file_changes)
            }
        }

    def _generate_change_id(self, change: CodeChange) -> str:
        """Generate unique ID for change"""
        data = f"{change.file_path}:{change.change_type}:{json.dumps(change.section)}:{datetime.now().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()[:12]