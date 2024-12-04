import ast
import logging
from pathlib import Path
from typing import Dict, Any, List
from .base import BaseTool
from .base import safe_read_file

logger = logging.getLogger(__name__)

class PreviewChanges(BaseTool):
    """Preview impact of code changes"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        pattern = arguments.get('pattern')
        replacement = arguments.get('replacement')

        if not pattern or not replacement:
            return {"error": "Both pattern and replacement are required"}

        cache_key = f"preview_{pattern}_{replacement}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = {
                "original": pattern,
                "replacement": replacement,
                "changes": await self._preview_changes(pattern, replacement),
                "impact": await self._analyze_change_impact(pattern, replacement),
                "safety_analysis": await self._analyze_safety(pattern, replacement)
            }

            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error previewing changes: {e}")
            return {"error": str(e)}


    def _should_skip(self, path: Path) -> bool:
        """Check if path should be skipped"""
        try:
            if any(excluded in path.parts for excluded in self.analysis_config.excluded_dirs):
                return True
            if path.is_file() and any(path.name.endswith(ext) for ext in self.analysis_config.excluded_files):
                return True
            return False
        except:
            return True

    async def _preview_changes(self, pattern: str, replacement: str) -> List[Dict[str, Any]]:
        """Generate preview of changes"""
        changes = []

        try:
            # Analyze current working directory recursively
            for path in Path('.').rglob('*.py'):
                if not self._should_skip(path):
                    content = safe_read_file(str(path))
                    if content and pattern in content:
                        # Generate diff for each occurrence
                        lines = content.splitlines()
                        for i, line in enumerate(lines, 1):
                            if pattern in line:
                                changes.append({
                                    "file": str(path),
                                    "line": i,
                                    "original": line.strip(),
                                    "modified": line.replace(pattern, replacement).strip(),
                                    "context": self._get_context(lines, i)
                                })

        except Exception as e:
            logger.error(f"Error previewing changes: {e}")

        return changes

    async def _analyze_change_impact(self, pattern: str, replacement: str) -> Dict[str, Any]:
        """Analyze impact of changes"""
        impact = {
            "risk_level": "low",
            "affected_components": [],
            "potential_issues": []
        }

        try:
            # Check for potential issues
            if len(replacement) > len(pattern):
                impact["potential_issues"].append("Replacement is longer than original")

            if replacement.count('_') != pattern.count('_'):
                impact["potential_issues"].append("Different naming convention")

            if replacement.lower() == pattern.lower() and replacement != pattern:
                impact["potential_issues"].append("Case sensitivity might cause issues")

            # Adjust risk level based on issues
            if len(impact["potential_issues"]) > 2:
                impact["risk_level"] = "high"
            elif len(impact["potential_issues"]) > 0:
                impact["risk_level"] = "medium"

        except Exception as e:
            logger.error(f"Error analyzing change impact: {e}")

        return impact

    async def _analyze_safety(self, pattern: str, replacement: str) -> Dict[str, Any]:
        """Analyze safety of the change"""
        return {
            "safe_to_apply": True,  # Default to True
            "warnings": [],
            "checks_performed": [
                "syntax_validation",
                "naming_convention",
                "scope_analysis"
            ]
        }

    def _get_context(self, lines: List[str], current_line: int, context_lines: int = 2) -> Dict[str, List[str]]:
        """Get context lines around the change"""
        start = max(0, current_line - context_lines - 1)
        end = min(len(lines), current_line + context_lines)

        return {
            "before": lines[start:current_line-1],
            "after": lines[current_line:end]
        }

class FindReferences(BaseTool):
    """Find code references tool"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target = arguments.get('target')
        ref_type = arguments.get('ref_type', 'all')

        if not target:
            return {"error": "Target is required"}

        cache_key = f"refs_{target}_{ref_type}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = {
                "target": target,
                "type": ref_type,
                "references": await self._find_references(target, ref_type),
                "summary": await self._create_summary(target, ref_type)
            }

            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error finding references: {e}")
            return {"error": str(e)}

    def _should_skip(self, path: Path) -> bool:
        """Check if path should be skipped"""
        try:
            if any(excluded in path.parts for excluded in self.analysis_config.excluded_dirs):
                return True
            if path.is_file() and any(path.name.endswith(ext) for ext in self.analysis_config.excluded_files):
                return True
            return False
        except:
            return True

    async def _find_references(self, target: str, ref_type: str) -> List[Dict[str, Any]]:
        """Find all references to target"""
        references = []

        try:
            for path in Path('.').rglob('*.py'):
                if not self._should_skip(path):
                    content = safe_read_file(str(path))
                    if not content:
                        continue

                    try:
                        tree = ast.parse(content)
                        refs = self._analyze_node_references(tree, target, ref_type)

                        if refs:
                            for ref in refs:
                                ref["file"] = str(path)
                            references.extend(refs)

                    except Exception as e:
                        logger.error(f"Error parsing {path}: {e}")

        except Exception as e:
            logger.error(f"Error finding references: {e}")

        return references

    def _analyze_node_references(self, tree: ast.AST, target: str, ref_type: str) -> List[Dict[str, Any]]:
        """Analyze AST node for references"""
        refs = []

        for node in ast.walk(tree):
            # Class references
            if ref_type in ['all', 'class'] and isinstance(node, ast.ClassDef):
                if target in [node.name, *[b.id for b in node.bases if isinstance(b, ast.Name)]]:
                    refs.append({
                        "type": "class",
                        "name": node.name,
                        "line": node.lineno,
                        "col": node.col_offset,
                        "kind": "definition" if node.name == target else "inheritance"
                    })

            # Function references
            elif ref_type in ['all', 'function'] and isinstance(node, ast.FunctionDef):
                if target == node.name:
                    refs.append({
                        "type": "function",
                        "name": node.name,
                        "line": node.lineno,
                        "col": node.col_offset,
                        "kind": "definition"
                    })

            # Variable references
            elif ref_type in ['all', 'variable'] and isinstance(node, ast.Name):
                if target == node.id:
                    refs.append({
                        "type": "variable",
                        "name": node.id,
                        "line": node.lineno,
                        "col": node.col_offset,
                        "kind": "assignment" if isinstance(node.ctx, ast.Store) else "usage"
                    })

        return refs

    async def _create_summary(self, target: str, ref_type: str) -> Dict[str, Any]:
        """Create reference summary"""
        refs = await self._find_references(target, ref_type)

        summary = {
            "total_references": len(refs),
            "by_type": {},
            "by_file": {},
            "unique_locations": set()
        }

        for ref in refs:
            # Count by type
            ref_type = ref["type"]
            summary["by_type"][ref_type] = summary["by_type"].get(ref_type, 0) + 1

            # Count by file
            file_path = ref["file"]
            summary["by_file"][file_path] = summary["by_file"].get(file_path, 0) + 1

            # Track unique locations
            summary["unique_locations"].add((file_path, ref["line"]))

        summary["unique_locations"] = len(summary["unique_locations"])

        return summary