import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import re
from dataclasses import dataclass
import fnmatch
from .base import BaseTool

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """Container for search results"""
    path: str
    match_type: str  # file, content, pattern
    line_number: Optional[int] = None
    content: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class PathFinder(BaseTool):
    """Advanced file and directory search tool"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        search_path = arguments.get('path', '.')
        operation = arguments.get('operation', 'find')

        operations = {
            'find': self._find_files,
            'glob': self._glob_search,
            'pattern': self._pattern_search,
            'recent': self._find_recent
        }

        if operation not in operations:
            return {"error": f"Unknown operation: {operation}"}

        try:
            result = await operations[operation](Path(search_path), arguments)
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"PathFinder operation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _find_files(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Find files based on criteria"""
        filters = args.get('filters', {})
        max_depth = args.get('max_depth', None)
        exclude_patterns = set(args.get('exclude', []))

        results = []
        total_scanned = 0

        try:
            for root, dirs, files in self._walk_with_depth(path, max_depth):
                # Apply directory exclusions
                dirs[:] = [d for d in dirs if not any(
                    fnmatch.fnmatch(d, pattern) for pattern in exclude_patterns
                )]

                for file in files:
                    total_scanned += 1
                    file_path = Path(root) / file

                    if self._should_skip(file_path):
                        continue

                    if self._matches_filters(file_path, filters):
                        stat = file_path.stat()
                        results.append({
                            "path": str(file_path),
                            "name": file_path.name,
                            "extension": file_path.suffix,
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
                        })

            return {
                "results": results,
                "summary": {
                    "total_found": len(results),
                    "total_scanned": total_scanned,
                    "search_path": str(path)
                }
            }

        except Exception as e:
            raise RuntimeError(f"File search failed: {e}")

    async def _glob_search(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search using glob patterns"""
        patterns = args.get('patterns', ['*'])
        recursive = args.get('recursive', True)

        results = []
        total_matches = 0

        try:
            for pattern in patterns:
                if recursive:
                    matches = path.rglob(pattern)
                else:
                    matches = path.glob(pattern)

                for match in matches:
                    if self._should_skip(match):
                        continue

                    stat = match.stat()
                    results.append({
                        "path": str(match),
                        "pattern": pattern,
                        "type": "directory" if match.is_dir() else "file",
                        "size": stat.st_size if match.is_file() else None,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                    total_matches += 1

            return {
                "results": results,
                "summary": {
                    "patterns": patterns,
                    "total_matches": total_matches,
                    "search_path": str(path)
                }
            }

        except Exception as e:
            raise RuntimeError(f"Glob search failed: {e}")

    async def _pattern_search(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search for files matching complex patterns"""
        pattern_rules = args.get('rules', {})
        max_results = args.get('max_results', None)

        results = []

        try:
            for file_path in self._recursive_search(path):
                if self._should_skip(file_path):
                    continue

                if self._matches_pattern_rules(file_path, pattern_rules):
                    stat = file_path.stat()
                    results.append({
                        "path": str(file_path),
                        "name": file_path.name,
                        "matches": self._get_matching_rules(file_path, pattern_rules),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })

                if max_results and len(results) >= max_results:
                    break

            return {
                "results": results,
                "summary": {
                    "total_matches": len(results),
                    "rules_applied": list(pattern_rules.keys()),
                    "search_path": str(path)
                }
            }

        except Exception as e:
            raise RuntimeError(f"Pattern search failed: {e}")

    async def _find_recent(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Find recently modified files"""
        hours = args.get('hours', 24)
        file_types = set(args.get('file_types', []))
        min_size = args.get('min_size', 0)
        max_size = args.get('max_size', float('inf'))

        results = []
        cutoff_time = datetime.now().timestamp() - (hours * 3600)

        try:
            for file_path in self._recursive_search(path):
                if self._should_skip(file_path):
                    continue

                stat = file_path.stat()
                if stat.st_mtime >= cutoff_time:
                    if not file_types or file_path.suffix in file_types:
                        if min_size <= stat.st_size <= max_size:
                            results.append({
                                "path": str(file_path),
                                "name": file_path.name,
                                "size": stat.st_size,
                                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                "hours_ago": (datetime.now().timestamp() - stat.st_mtime) / 3600
                            })

            # Sort by modification time
            results.sort(key=lambda x: x["modified"], reverse=True)

            return {
                "results": results,
                "summary": {
                    "total_found": len(results),
                    "time_range_hours": hours,
                    "search_path": str(path)
                }
            }

        except Exception as e:
            raise RuntimeError(f"Recent files search failed: {e}")

    def _walk_with_depth(self, path: Path, max_depth: Optional[int] = None):
        """Walk directory tree with optional depth limit"""
        base_depth = len(path.parents)
        for root, dirs, files in path.walk():
            current_depth = len(Path(root).parents) - base_depth
            if max_depth is not None and current_depth > max_depth:
                dirs.clear()
            else:
                yield root, dirs, files

    def _matches_filters(self, path: Path, filters: Dict[str, Any]) -> bool:
        """Check if file matches all filters"""
        try:
            stat = path.stat()

            for key, value in filters.items():
                if key == 'extension' and path.suffix != value:
                    return False
                elif key == 'name' and path.name != value:
                    return False
                elif key == 'min_size' and stat.st_size < value:
                    return False
                elif key == 'max_size' and stat.st_size > value:
                    return False
                elif key == 'modified_after' and stat.st_mtime < value:
                    return False
                elif key == 'modified_before' and stat.st_mtime > value:
                    return False

            return True

        except Exception:
            return False

    def _matches_pattern_rules(self, path: Path, rules: Dict[str, Any]) -> bool:
        """Check if file matches pattern rules"""
        try:
            for rule_type, pattern in rules.items():
                if rule_type == 'name_pattern':
                    if not fnmatch.fnmatch(path.name, pattern):
                        return False
                elif rule_type == 'path_pattern':
                    if not fnmatch.fnmatch(str(path), pattern):
                        return False
                elif rule_type == 'regex':
                    if not re.search(pattern, str(path)):
                        return False

            return True

        except Exception:
            return False

    def _get_matching_rules(self, path: Path, rules: Dict[str, Any]) -> List[str]:
        """Get list of matching rules for a file"""
        matches = []
        for rule_type, pattern in rules.items():
            if rule_type == 'name_pattern' and fnmatch.fnmatch(path.name, pattern):
                matches.append(rule_type)
            elif rule_type == 'path_pattern' and fnmatch.fnmatch(str(path), pattern):
                matches.append(rule_type)
            elif rule_type == 'regex' and re.search(pattern, str(path)):
                matches.append(rule_type)
        return matches

    def _recursive_search(self, path: Path) -> List[Path]:
        """Recursively search directory"""
        try:
            return list(path.rglob('*'))
        except Exception:
            return []

class ContentScanner(BaseTool):
    """Advanced content search and analysis tool"""

    def __init__(self):
        super().__init__()
        self._file_cache = {}
        self.max_workers = 4

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        operation = arguments.get('operation', 'search')
        target_path = arguments.get('path', '.')

        operations = {
            'search': self._search_content,
            'analyze': self._analyze_content,
            'regex': self._regex_search,
            'similar': self._find_similar
        }

        if operation not in operations:
            return {"error": f"Unknown operation: {operation}"}

        try:
            result = await operations[operation](Path(target_path), arguments)
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"ContentScanner operation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _search_content(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search file contents for text"""
        search_text = args.get('text')
        case_sensitive = args.get('case_sensitive', False)
        whole_word = args.get('whole_word', False)
        file_pattern = args.get('file_pattern', '*')

        if not search_text:
            return {"error": "Search text is required"}

        results = []
        total_files = 0
        matches_found = 0

        try:
            # Prepare search pattern
            if whole_word:
                pattern = r'\b' + re.escape(search_text) + r'\b'
            else:
                pattern = re.escape(search_text)

            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)

            # Search files
            for file_path in path.rglob(file_pattern):
                if self._should_skip(file_path) or not file_path.is_file():
                    continue

                total_files += 1

                try:
                    matches = await self._find_matches(file_path, regex)
                    if matches:
                        matches_found += len(matches)
                        results.append({
                            "file": str(file_path),
                            "matches": matches
                        })
                except Exception as e:
                    logger.error(f"Error searching {file_path}: {e}")

            return {
                "results": results,
                "summary": {
                    "total_files_searched": total_files,
                    "files_with_matches": len(results),
                    "total_matches": matches_found,
                    "search_pattern": {
                        "text": search_text,
                        "case_sensitive": case_sensitive,
                        "whole_word": whole_word
                    }
                }
            }

        except Exception as e:
            raise RuntimeError(f"Content search failed: {e}")

    async def _analyze_content(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze file contents"""
        file_pattern = args.get('file_pattern', '*')
        analysis_types = set(args.get('types', ['duplicates', 'statistics', 'patterns']))

        try:
            analysis_results = {
                "files_analyzed": 0,
                "total_size": 0,
                "analysis": {}
            }

            if 'duplicates' in analysis_types:
                analysis_results["analysis"]["duplicates"] = await self._find_duplicate_content(path, file_pattern)

            if 'statistics' in analysis_types:
                analysis_results["analysis"]["statistics"] = await self._generate_content_statistics(path, file_pattern)

            if 'patterns' in analysis_types:
                analysis_results["analysis"]["patterns"] = await self._analyze_content_patterns(path, file_pattern)

            return analysis_results

        except Exception as e:
            raise RuntimeError(f"Content analysis failed: {e}")

    async def _regex_search(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search using regular expressions"""
        pattern = args.get('pattern')
        file_pattern = args.get('file_pattern', '*')
        multiline = args.get('multiline', False)

        if not pattern:
            return {"error": "Regex pattern is required"}

        try:
            flags = re.MULTILINE if multiline else 0
            regex = re.compile(pattern, flags)

            results = []
            for file_path in path.rglob(file_pattern):
                if self._should_skip(file_path) or not file_path.is_file():
                    continue

                matches = await self._find_matches(file_path, regex)
                if matches:
                    results.append({
                        "file": str(file_path),
                        "matches": matches
                    })

            return {
                "results": results,
                "summary": {
                    "total_files_searched": len(list(path.rglob(file_pattern))),
                    "files_with_matches": len(results),
                    "pattern": pattern,
                    "multiline": multiline
                }
            }

        except Exception as e:
            raise RuntimeError(f"Regex search failed: {e}")

    async def _find_similar(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Find files with similar content"""
        threshold = args.get('similarity_threshold', 0.8)
        file_pattern = args.get('file_pattern', '*')
        min_size = args.get('min_size', 0)

        try:
            file_groups = []
            content_hashes = {}

            # First pass: collect file contents
            for file_path in path.rglob(file_pattern):
                if self._should_skip(file_path) or not file_path.is_file():
                    continue

                if file_path.stat().st_size < min_size:
                    continue

                try:
                    content = await self._read_file_content(file_path)
                    if content:
                        content_hashes[str(file_path)] = self._calculate_similarity_hash(content)
                except Exception as e:
                    logger.error(f"Error reading {file_path}: {e}")

            # Second pass: compare files
            analyzed_files = set()
            for file1, hash1 in content_hashes.items():
                if file1 in analyzed_files:
                    continue

                similar_files = []
                for file2, hash2 in content_hashes.items():
                    if file1 != file2 and file2 not in analyzed_files:
                        similarity = self._calculate_hash_similarity(hash1, hash2)
                        if similarity >= threshold:
                            similar_files.append({
                                "path": file2,
                                "similarity": similarity
                            })
                            analyzed_files.add(file2)

                if similar_files:
                    analyzed_files.add(file1)
                    file_groups.append({
                        "base_file": file1,
                        "similar_files": similar_files
                    })

            return {
                "groups": file_groups,
                "summary": {
                    "total_files": len(content_hashes),
                    "similarity_groups": len(file_groups),
                    "threshold": threshold
                }
            }

        except Exception as e:
            raise RuntimeError(f"Similarity analysis failed: {e}")

    async def _find_matches(self, file_path: Path, pattern: re.Pattern) -> List[Dict[str, Any]]:
        """Find pattern matches in file"""
        matches = []
        try:
            content = await self._read_file_content(file_path)
            if not content:
                return matches

            for i, line in enumerate(content.splitlines(), 1):
                for match in pattern.finditer(line):
                    matches.append({
                        "line": i,
                        "start": match.start(),
                        "end": match.end(),
                        "text": match.group(),
                        "context": self._get_line_context(content.splitlines(), i)
                    })

        except Exception as e:
            logger.error(f"Error finding matches in {file_path}: {e}")

        return matches

    async def _find_duplicate_content(self, path: Path, pattern: str) -> Dict[str, Any]:
        """Find duplicate content across files"""
        content_map = {}
        duplicates = []

        try:
            for file_path in path.rglob(pattern):
                if self._should_skip(file_path) or not file_path.is_file():
                    continue

                content = await self._read_file_content(file_path)
                if not content:
                    continue

                content_hash = self._calculate_content_hash(content)
                if content_hash in content_map:
                    # Found a duplicate
                    if content_map[content_hash] not in duplicates:
                        duplicates.append({
                            "original": content_map[content_hash],
                            "duplicates": []
                        })

                    for group in duplicates:
                        if group["original"] == content_map[content_hash]:
                            group["duplicates"].append(str(file_path))
                else:
                    content_map[content_hash] = str(file_path)

            return {
                "duplicate_groups": duplicates,
                "total_duplicates": sum(len(group["duplicates"]) for group in duplicates)
            }

        except Exception as e:
            logger.error(f"Error finding duplicates: {e}")
            return {"error": str(e)}

    async def _generate_content_statistics(self, path: Path, pattern: str) -> Dict[str, Any]:
        """Generate statistics about file contents"""
        stats = {
            "total_files": 0,
            "total_lines": 0,
            "total_size": 0,
            "average_line_length": 0,
            "file_types": {},
            "encoding_types": {},
            "line_endings": {
                "unix": 0,
                "windows": 0,
                "mixed": 0
            }
        }

        try:
            line_lengths = []

            for file_path in path.rglob(pattern):
                if self._should_skip(file_path) or not file_path.is_file():
                    continue

                stats["total_files"] += 1
                stats["total_size"] += file_path.stat().st_size

                # Track file types
                ext = file_path.suffix
                stats["file_types"][ext] = stats["file_types"].get(ext, 0) + 1

                content = await self._read_file_content(file_path)
                if not content:
                    continue

                lines = content.splitlines()
                stats["total_lines"] += len(lines)
                line_lengths.extend(len(line) for line in lines)

                # Detect line endings
                if '\r\n' in content and '\n' in content.replace('\r\n', ''):
                    stats["line_endings"]["mixed"] += 1
                elif '\r\n' in content:
                    stats["line_endings"]["windows"] += 1
                else:
                    stats["line_endings"]["unix"] += 1

                # Track encoding
                encoding = self._detect_encoding(file_path)
                stats["encoding_types"][encoding] = stats["encoding_types"].get(encoding, 0) + 1

            if line_lengths:
                stats["average_line_length"] = sum(line_lengths) / len(line_lengths)

            return stats

        except Exception as e:
            logger.error(f"Error generating statistics: {e}")
            return {"error": str(e)}

    async def _analyze_content_patterns(self, path: Path, pattern: str) -> Dict[str, Any]:
        """Analyze content for common patterns"""
        patterns = {
            "common_words": {},
            "line_patterns": [],
            "structure_patterns": []
        }

        try:
            word_freq = {}
            line_patterns = set()

            for file_path in path.rglob(pattern):
                if self._should_skip(file_path) or not file_path.is_file():
                    continue

                content = await self._read_file_content(file_path)
                if not content:
                    continue

                # Analyze words
                words = re.findall(r'\w+', content.lower())
                for word in words:
                    word_freq[word] = word_freq.get(word, 0) + 1

                # Analyze line patterns
                lines = content.splitlines()
                for line in lines:
                    # Find repeating patterns
                    pattern_match = re.match(r'^(\s*)(.+?)(\s*)$', line)
                    if pattern_match:
                        indent, content, trailing = pattern_match.groups()
                        if len(indent) > 0:
                            line_patterns.add(f"indent:{len(indent)}")

                # Analyze structure patterns
                if file_path.suffix == '.py':
                    await self._analyze_python_patterns(content, patterns)

            # Process word frequencies
            patterns["common_words"] = dict(sorted(
                word_freq.items(),
                key=lambda x: x[1],
                reverse=True
            )[:100])

            patterns["line_patterns"] = list(line_patterns)

            return patterns

        except Exception as e:
            logger.error(f"Error analyzing patterns: {e}")
            return {"error": str(e)}

    async def _read_file_content(self, path: Path) -> Optional[str]:
        """Read file content with caching"""
        if str(path) in self._file_cache:
            return self._file_cache[str(path)]

        try:
            content = path.read_text(encoding=self._detect_encoding(path))
            self._file_cache[str(path)] = content
            return content
        except Exception as e:
            logger.error(f"Error reading {path}: {e}")
            return None

    def _detect_encoding(self, path: Path) -> str:
        """Detect file encoding"""
        try:
            import chardet
            with open(path, 'rb') as f:
                raw = f.read()
                result = chardet.detect(raw)
                return result['encoding'] or 'utf-8'
        except Exception:
            return 'utf-8'

    def _calculate_content_hash(self, content: str) -> str:
        """Calculate hash of content"""
        import hashlib
        return hashlib.md5(content.encode()).hexdigest()

    def _calculate_similarity_hash(self, content: str) -> List[int]:
        """Calculate similarity hash for content"""
        # Simplified implementation of similarity hashing
        words = content.split()
        return [hash(word) for word in words]

    def _calculate_hash_similarity(self, hash1: List[int], hash2: List[int]) -> float:
        """Calculate similarity between two hashes"""
        common = set(hash1) & set(hash2)
        return len(common) / max(len(hash1), len(hash2))

    def _get_line_context(self, lines: List[str], line_number: int, context_lines: int = 2) -> Dict[str, List[str]]:
        """Get context lines around a match"""
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)
        return {
            "before": lines[start:line_number-1],
            "after": lines[line_number:end]
        }

    async def _analyze_python_patterns(self, content: str, patterns: Dict[str, Any]) -> None:
        """Analyze Python-specific patterns"""
        import ast
        try:
            tree = ast.parse(content)

            # Analyze structure patterns
            class_patterns = []
            function_patterns = []

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    methods = len([n for n in node.body if isinstance(n, ast.FunctionDef)])
                    class_patterns.append(f"class_with_{methods}_methods")

                elif isinstance(node, ast.FunctionDef):
                    args = len(node.args.args)
                    function_patterns.append(f"function_with_{args}_args")

            if class_patterns:
                patterns["structure_patterns"].extend(class_patterns)
            if function_patterns:
                patterns["structure_patterns"].extend(function_patterns)

        except Exception as e:
            logger.error(f"Error analyzing Python patterns: {e}")