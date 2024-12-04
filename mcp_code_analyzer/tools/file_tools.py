import asyncio

from .base import BaseTool , safe_read_file
from .logger import LogManager
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Union, List
import ast
import astroid
from pydantic import json
from radon.complexity import cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze

logger = logging.getLogger(__name__)


class MCPFileOperations(BaseTool):
    """MCP compatible file operations implementation"""

    def __init__(self):
        super().__init__()
        self._active_streams = {}
        self._file_locks = {}

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute file operations with MCP protocol support"""
        operation = arguments.get('operation')
        if not operation:
            return {"error": "Operation is required"}

        operations = {
            'analyze': self._analyze_file,
            'create': self._create_file,
            'modify': self._modify_file,
            'stream': self._handle_stream
        }

        if operation not in operations:
            return {
                "error": f"Unknown operation: {operation}",
                "available_operations": list(operations.keys())
            }

        try:
            result = await operations[operation](arguments)
            return {
                "success": True,
                "operation": operation,
                "timestamp": datetime.now().isoformat(),
                "data": result
            }
        except Exception as e:
            logger.error(f"File operation failed: {e}")
            return {
                "success": False,
                "operation": operation,
                "error": str(e)
            }

    async def _analyze_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze file with enhanced error handling"""
        path = args.get('path')
        if not path:
            raise ValueError("Path is required for analysis")

        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not path_obj.is_file():
            raise ValueError(f"Not a file: {path}")

        try:
            stat = path_obj.stat()

            # Basic file info
            result = {
                "path": str(path_obj),
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "type": path_obj.suffix,
                "permissions": oct(stat.st_mode)[-3:]
            }

            # Add content analysis if requested
            if args.get('analyze_content', False):
                result["content_analysis"] = await self._analyze_content(path_obj)

            return result

        except Exception as e:
            raise RuntimeError(f"Analysis failed: {e}")

    async def _create_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create file with MCP protocol support"""
        path = args.get('path')
        content = args.get('content', '')
        overwrite = args.get('overwrite', False)

        if not path:
            raise ValueError("Path is required for file creation")

        path_obj = Path(path)

        try:
            # Create parent directories
            path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Handle existing file
            if path_obj.exists():
                if not overwrite:
                    raise FileExistsError(f"File already exists: {path}")
                backup_path = self._create_backup(path_obj)

            # Write file with explicit encoding
            with path_obj.open('w', encoding='utf-8') as f:
                f.write(content)

            return {
                "path": str(path_obj),
                "size": len(content.encode('utf-8')),
                "backup_path": str(backup_path) if locals().get('backup_path') else None
            }

        except Exception as e:
            raise RuntimeError(f"File creation failed: {e}")

    async def _modify_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Modify file with section support"""
        path = args.get('path')
        content = args.get('content')
        section = args.get('section')

        if not path:
            raise ValueError("Path is required for modification")

        if content is None:
            raise ValueError("Content is required for modification")

        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"File not found: {path}")

        try:
            # Create backup
            backup_path = self._create_backup(path_obj)

            # Read current content
            with path_obj.open('r', encoding='utf-8') as f:
                current_content = f.read()

            # Handle section modification if specified
            if section:
                start = section.get('start', 0)
                end = section.get('end', len(current_content))
                lines = current_content.splitlines()

                if start < 0 or start >= len(lines) or end < 0 or end > len(lines):
                    raise ValueError("Invalid section range")

                new_lines = lines[:start] + content.splitlines() + lines[end:]
                final_content = '\n'.join(new_lines)
            else:
                final_content = content

            # Write modified content
            with path_obj.open('w', encoding='utf-8') as f:
                f.write(final_content)

            return {
                "path": str(path_obj),
                "size": len(final_content.encode('utf-8')),
                "backup_path": str(backup_path),
                "sections_modified": bool(section)
            }

        except Exception as e:
            # Restore from backup if exists
            if 'backup_path' in locals():
                try:
                    shutil.copy2(backup_path, path_obj)
                except Exception as restore_error:
                    logger.error(f"Failed to restore backup: {restore_error}")

            raise RuntimeError(f"File modification failed: {e}")

    async def _handle_stream(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle streaming operations"""
        path = args.get('path')
        operation = args.get('stream_operation')
        content = args.get('content')

        if not path:
            raise ValueError("Path is required for streaming")

        if not operation:
            raise ValueError("Stream operation is required")

        path_obj = Path(path)
        stream_id = str(path_obj)

        try:
            if operation == 'start':
                return await self._start_stream(path_obj, args)
            elif operation == 'write':
                if not content:
                    raise ValueError("Content is required for write operation")
                return await self._write_stream(path_obj, content, args)
            elif operation == 'finish':
                return await self._finish_stream(path_obj)
            else:
                raise ValueError(f"Unknown stream operation: {operation}")

        except Exception as e:
            raise RuntimeError(f"Stream operation failed: {e}")

    async def _analyze_content(self, path: Path) -> Dict[str, Any]:
        """Analyze file content"""
        try:
            with path.open('r', encoding='utf-8') as f:
                content = f.read()

            lines = content.splitlines()
            return {
                "line_count": len(lines),
                "empty_lines": len([l for l in lines if not l.strip()]),
                "average_line_length": sum(len(l) for l in lines) / len(lines) if lines else 0,
                "byte_size": len(content.encode('utf-8'))
            }
        except Exception as e:
            logger.error(f"Content analysis failed: {e}")
            return {}

    def _create_backup(self, path: Path) -> Path:
        """Create backup of existing file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = path.parent / f"{path.stem}_backup_{timestamp}{path.suffix}"
        shutil.copy2(path, backup_path)
        return backup_path

    async def _start_stream(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Start a new file stream"""
        stream_id = str(path)
        if stream_id in self._active_streams:
            raise RuntimeError(f"Stream already exists for {path}")

        self._file_locks[stream_id] = asyncio.Lock()

        async with self._file_locks[stream_id]:
            backup_path = self._create_backup(path) if path.exists() else None

            self._active_streams[stream_id] = {
                'started_at': datetime.now().isoformat(),
                'buffer': [],
                'total_bytes': 0,
                'backup_path': str(backup_path) if backup_path else None
            }

        return {
            "stream_id": stream_id,
            "started_at": self._active_streams[stream_id]['started_at'],
            "backup_created": backup_path is not None
        }

    async def _write_stream(self, path: Path, content: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Write content to stream"""
        stream_id = str(path)
        if stream_id not in self._active_streams:
            raise RuntimeError(f"No active stream for {path}")

        async with self._file_locks[stream_id]:
            stream = self._active_streams[stream_id]

            try:
                with path.open('a', encoding='utf-8') as f:
                    f.write(content)

                stream['total_bytes'] += len(content.encode('utf-8'))
                return {
                    "bytes_written": len(content.encode('utf-8')),
                    "total_bytes": stream['total_bytes']
                }

            except Exception as e:
                raise RuntimeError(f"Stream write failed: {e}")

    async def _finish_stream(self, path: Path) -> Dict[str, Any]:
        """Finish and cleanup stream"""
        stream_id = str(path)
        if stream_id not in self._active_streams:
            raise RuntimeError(f"No active stream for {path}")

        async with self._file_locks[stream_id]:
            stream = self._active_streams[stream_id]

            try:
                # Remove backup if exists
                if stream['backup_path']:
                    backup_path = Path(stream['backup_path'])
                    if backup_path.exists():
                        backup_path.unlink()

                # Calculate duration
                started = datetime.fromisoformat(stream['started_at'])
                duration = (datetime.now() - started).total_seconds()

                result = {
                    "stream_id": stream_id,
                    "total_bytes": stream['total_bytes'],
                    "duration_seconds": duration
                }

                # Cleanup
                del self._active_streams[stream_id]
                del self._file_locks[stream_id]

                return result

            except Exception as e:
                raise RuntimeError(f"Failed to finish stream: {e}")


class FileAnalyzer(BaseTool):
    """File level analysis tool"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute file analysis"""
        file_path = arguments.get('file_path')
        if not file_path:
            return {"error": "No file path provided"}

        try:
            # Convert to Path object and resolve
            path = Path(file_path).resolve()

            if not path.exists():
                found_path = None
                for search_path in Path('.').rglob(Path(file_path).name):
                    if search_path.exists() and not self._should_skip(search_path):
                        found_path = search_path
                        path = found_path
                        break

                if not found_path:
                    return {"error": f"File not found: {file_path}"}

            # Read file content with proper encoding handling
            content = safe_read_file(str(path))
            if content is None:
                return {"error": f"Could not read file: {path}"}

            # Create result with content encoded as UTF-8
            result = {
                "path": str(path),
                "type": path.suffix,
                "size": path.stat().st_size,
                "content": content,
                "metrics": self._analyze_metrics(content) if path.suffix == '.py' else {},
                "encoding": "utf-8"  # Add encoding information
            }

            return result

        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return {"error": str(e)}

    async def analyze_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyze a single file"""
        try:
            path = Path(file_path).resolve()
            if not path.exists():
                return {"error": f"File not found: {path}"}

            if path.stat().st_size > self.system_config.MAX_FILE_SIZE:
                return {"error": f"File too large: {path}"}

            result = {
                "path": str(path),
                "type": path.suffix,
                "size": path.stat().st_size,
                "metrics": {},
                "content_analysis": {}
            }

            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()

                if path.suffix == '.py':
                    result["metrics"] = self._analyze_python_file(content)
                elif path.suffix in ['.js', '.jsx']:
                    result["metrics"] = self._analyze_javascript_file(content)
                elif path.suffix == '.json':
                    result["metrics"] = self._analyze_json_file(content)

                result["content_analysis"] = {
                    "line_count": len(content.splitlines()),
                    "size_human": self._format_size(path.stat().st_size),
                    "last_modified": path.stat().st_mtime,
                }

            except UnicodeDecodeError:
                result["content_analysis"] = {
                    "note": "Binary file - content analysis skipped"
                }

            return result

        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return {"error": str(e)}

    def _analyze_python_file(self, content: str) -> Dict[str, Any]:
        try:
            tree = ast.parse(content)
            return {
                "classes": len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]),
                "functions": len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]),
                "imports": len([n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))])
            }
        except:
            return {}

    def _analyze_javascript_file(self, content: str) -> Dict[str, Any]:
        metrics = {
            "component_count": content.count("export default"),
            "hook_usage": content.count("useState") + content.count("useEffect"),
            "jsx_elements": content.count("return ("),
        }
        return metrics

    def _analyze_json_file(self, content: str) -> Dict[str, Any]:
        try:
            data = json.loads(content)
            return {
                "keys": len(data) if isinstance(data, dict) else "not-dict",
                "is_valid": True
            }
        except:
            return {"is_valid": False}

    def _format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _analyze_metrics(self, content: str) -> Dict[str, Any]:
        try:
            return {
                "complexity": cc_visit(content),
                "maintainability": mi_visit(content, multi=True),
                "raw": analyze(content)
            }
        except Exception as e:
            logger.error(f"Error analyzing metrics: {e}")
            return {}

    async def _analyze_quality(self, content: str) -> Dict[str, Any]:
        """Analyze code quality"""
        try:
            tree = ast.parse(content)
            quality = {
                "issues": [],
                "suggestions": []
            }

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if len(node.body) > 50:
                        quality["issues"].append({
                            "type": "long_function",
                            "location": node.lineno,
                            "message": f"Function {node.name} is too long ({len(node.body)} lines)"
                        })
                    quality["suggestions"].append({
                        "type": "function_doc",
                        "location": node.lineno,
                        "message": f"Consider adding docstring to function {node.name}"
                    }) if not ast.get_docstring(node) else None

                elif isinstance(node, ast.ClassDef):
                    methods = len([n for n in node.body if isinstance(n, ast.FunctionDef)])
                    if methods > 10:
                        quality["issues"].append({
                            "type": "complex_class",
                            "location": node.lineno,
                            "message": f"Class {node.name} has too many methods ({methods})"
                        })

            return quality

        except Exception as e:
            logger.error(f"Error analyzing quality: {e}")
            return {}

    async def _analyze_patterns(self, content: str) -> Dict[str, Any]:
        """Analyze code patterns"""
        try:
            tree = astroid.parse(content)
            patterns = {
                "design_patterns": [],
                "anti_patterns": [],
                "code_smells": []
            }

            for class_node in tree.nodes_of_class(astroid.ClassDef):
                # Design patterns
                if any(method.name == 'get_instance' for method in class_node.methods()):
                    patterns["design_patterns"].append({
                        "type": "singleton",
                        "location": class_node.lineno,
                        "class": class_node.name
                    })

                # Anti-patterns
                method_count = len(list(class_node.methods()))
                if method_count > 20:
                    patterns["anti_patterns"].append({
                        "type": "god_class",
                        "location": class_node.lineno,
                        "class": class_node.name,
                        "methods": method_count
                    })

            return patterns

        except Exception as e:
            logger.error(f"Error analyzing patterns: {e}")
            return {}
