from abc import ABC, abstractmethod
from ..config import analysis_config, system_config
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import chardet
from functools import lru_cache

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1000)
def detect_file_encoding(file_path: str) -> str:
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            return result['encoding'] or 'utf-8'
    except Exception as e:
        logger.warning(f"Error detecting encoding for {file_path}: {e}")
        return 'utf-8'

def calculate_directory_size(path: Union[str, Path]) -> int:
    total_size = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file():
                    total_size += entry.stat().st_size
                elif entry.is_dir():
                    total_size += calculate_directory_size(entry.path)
            except (PermissionError, FileNotFoundError) as e:
                continue
    except Exception as e:
        logger.error(f"Error calculating directory size for {path}: {e}")
    return total_size

def safe_read_file(file_path: Union[str, Path], base_path: Optional[Union[str, Path]] = None) -> Optional[str]:
    """Safely read a file with proper encoding detection and error handling"""
    try:
        # Convert to Path object
        path = Path(file_path)

        # Handle base path
        if base_path and not path.is_absolute():
            path = Path(base_path) / path

        # Ensure path is resolved
        path = path.resolve()

        if not path.exists():
            logger.error(f"File not found: {path}")
            return None

        if not path.is_file():
            logger.error(f"Not a file: {path}")
            return None

        try:
            # First try reading as binary to detect encoding
            with open(path, 'rb') as f:
                raw_content = f.read()

            # Detect encoding with BOM check
            if raw_content.startswith(b'\xef\xbb\xbf'):
                encoding = 'utf-8-sig'
            else:
                # Try different encodings in order of likelihood
                encodings = ['utf-8', 'utf-16', 'utf-16le', 'utf-16be', 'cp1252', 'iso-8859-1']
                content = None

                for enc in encodings:
                    try:
                        content = raw_content.decode(enc)
                        encoding = enc
                        break
                    except UnicodeDecodeError:
                        continue

                if content is None:
                    # If all encodings fail, use utf-8 with error handling
                    content = raw_content.decode('utf-8', errors='replace')
                    return content

            # Read with detected encoding
            with open(path, 'r', encoding=encoding) as f:
                return f.read()

        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            # Last resort: try to decode with utf-8 and replace errors
            try:
                return raw_content.decode('utf-8', errors='replace')
            except:
                return None

    except Exception as e:
        logger.error(f"Error processing file path {file_path}: {e}")
        return None

def get_relative_path(base_path: Union[str, Path], full_path: Union[str, Path]) -> str:
    try:
        base = Path(base_path).resolve()
        full = Path(full_path).resolve()
        try:
            return str(full.relative_to(base))
        except ValueError:
            return str(full)
    except Exception as e:
        logger.error(f"Error getting relative path: {e}")
        return str(full_path)

class BaseTool(ABC):
    def __init__(self):
        self.analysis_config = analysis_config
        self.system_config = system_config
        self._cache = {}

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        pass

    def _cache_result(self, key: str, result: Any):
        if self.system_config.ENABLE_CACHE:
            if len(self._cache) >= self.system_config.MAX_CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = result

    def _get_cached_result(self, key: str) -> Optional[Any]:
        if self.system_config.ENABLE_CACHE:
            return self._cache.get(key)
        return None

    def _get_absolute_path(self, path: Union[str, Path], base_path: Optional[Union[str, Path]] = None) -> Path:
        try:
            path = Path(path)
            if base_path:
                base = Path(base_path)
                return (base / path).resolve()
            elif not path.is_absolute():
                return (Path.cwd() / path).resolve()
            return path.resolve()
        except Exception as e:
            logger.error(f"Error getting absolute path: {e}")
            return Path.cwd()

    def _normalize_path(self, path: Union[str, Path]) -> Path:
        try:
            path_obj = Path(path)

            if isinstance(path, str):
                path = path.replace('\\', '/')

            if path_obj.is_absolute():
                return path_obj.resolve()

            if path_obj.exists():
                return path_obj.resolve()
            try:
                found_paths = list(Path('.').rglob(path_obj.name))
                if found_paths:
                    for found_path in found_paths:
                        if found_path.exists() and not self._should_skip(found_path):
                            return found_path.resolve()
            except Exception:
                pass

            return Path(path).resolve()

        except Exception as e:
            logger.error(f"Error normalizing path {path}: {e}")
            return Path(path) if isinstance(path, str) else path


    def _validate_path(self, path: Path) -> bool:
        try:
            path = self._normalize_path(path)
            if not path.exists():
                return False
            return os.access(path, os.R_OK)
        except Exception as e:
            logger.error(f"Error validating path {path}: {e}")
            return False

    def _should_skip_path(self, path: Path) -> bool:
        try:
            if any(excluded in path.parts for excluded in self.analysis_config.excluded_dirs):
                return True
            if path.is_file() and any(path.name.endswith(ext) for ext in self.analysis_config.excluded_files):
                return True
            return False
        except Exception:
            return True

    def _is_valid_project_path(self, path: Path) -> bool:
        try:
            return path.is_dir() and not self._should_skip_path(path)
        except Exception:
            return False

    @staticmethod
    def create_file_tree(files: List[Dict[str, Any]]) -> Dict[str, Any]:
        tree = {}
        for file_info in files:
            path_parts = file_info['path'].split(os.sep)
            current = tree
            for part in path_parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[path_parts[-1]] = file_info
        return tree

    @staticmethod
    def group_files_by_type(files: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        grouped = {}
        for file_info in files:
            ext = file_info.get('type', '')
            if ext not in grouped:
                grouped[ext] = []
            grouped[ext].append(file_info['path'])
        return grouped

    @staticmethod
    def find_similar_files(files: List[Dict[str, Any]], threshold: float = 0.8) -> List[Dict[str, Any]]:
        from difflib import SequenceMatcher
        similar_groups = []
        for i, file1 in enumerate(files):
            similar = []
            for j, file2 in enumerate(files):
                if i != j:
                    similarity = SequenceMatcher(None, file1['name'], file2['name']).ratio()
                    if similarity >= threshold:
                        similar.append({
                            'file': file2['path'],
                            'similarity': similarity
                        })
            if similar:
                similar_groups.append({
                    'file': file1['path'],
                    'similar_to': similar
                })
        return similar_groups

    def _should_skip(self, path: Path) -> bool:
        try:
            if any(excluded in path.parts for excluded in self.analysis_config.excluded_dirs):
                return True
            if path.is_file() and any(path.name.endswith(ext) for ext in self.analysis_config.excluded_files):
                return True
            return False
        except Exception:
            return True