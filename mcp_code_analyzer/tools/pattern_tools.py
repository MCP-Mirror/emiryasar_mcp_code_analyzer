import ast
import logging
from pathlib import Path
from typing import Dict, Any, List
from .base import BaseTool , safe_read_file

logger = logging.getLogger(__name__)

class PatternDependencyAnalyzer(BaseTool):
    """Analyze dependencies related to code patterns"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        file_path = arguments.get('file_path')
        pattern = arguments.get('pattern')

        if not file_path or not pattern:
            return {"error": "Both file_path and pattern are required"}

        path = self._normalize_path(file_path)
        if not self._validate_path(path):
            return {"error": "File not found"}

        cache_key = f"pattern_deps_{path}_{pattern}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            content = safe_read_file(str(path))
            if not content:
                return {"error": "Could not read file"}

            result = {
                "pattern": pattern,
                "location": await self._find_pattern_locations(content, pattern),
                "dependencies": await self._analyze_dependencies(content, pattern),
                "impact": await self._analyze_impact(content, pattern),
            }

            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error analyzing pattern dependencies: {e}")
            return {"error": str(e)}

    async def _find_pattern_locations(self, content: str, pattern: str) -> List[Dict[str, Any]]:
        """Find pattern locations in code"""
        locations = []
        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                # Check functions
                if isinstance(node, ast.FunctionDef) and pattern in node.name:
                    locations.append({
                        "type": "function",
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": getattr(node, 'end_lineno', node.lineno)
                    })

                # Check classes
                elif isinstance(node, ast.ClassDef) and pattern in node.name:
                    locations.append({
                        "type": "class",
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": getattr(node, 'end_lineno', node.lineno)
                    })

                # Check variables
                elif isinstance(node, ast.Name) and pattern in node.id:
                    locations.append({
                        "type": "variable",
                        "name": node.id,
                        "line": node.lineno,
                        "context": "assignment" if isinstance(node.ctx, ast.Store) else "usage"
                    })

            return locations

        except Exception as e:
            logger.error(f"Error finding pattern locations: {e}")
            return []

    async def _analyze_dependencies(self, content: str, pattern: str) -> Dict[str, Any]:
        """Analyze pattern dependencies"""
        deps = {
            "imports": [],
            "functions": [],
            "variables": []
        }

        try:
            tree = ast.parse(content)
            pattern_nodes = []

            # Find nodes containing pattern
            for node in ast.walk(tree):
                if hasattr(node, 'name') and pattern in getattr(node, 'name', ''):
                    pattern_nodes.append(node)
                elif isinstance(node, ast.Name) and pattern in node.id:
                    pattern_nodes.append(node)

            # Analyze each pattern node
            for node in pattern_nodes:
                # Find imports
                imports = set()
                for n in ast.walk(node):
                    if isinstance(n, (ast.Import, ast.ImportFrom)):
                        if isinstance(n, ast.Import):
                            imports.add(n.names[0].name)
                        else:
                            imports.add(f"{n.module}.{n.names[0].name}")
                deps["imports"].extend(list(imports))

                # Find function calls
                if isinstance(node, ast.FunctionDef):
                    for n in ast.walk(node):
                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                            deps["functions"].append({
                                "name": n.func.id,
                                "line": n.lineno
                            })

                # Find variable uses
                if isinstance(node, ast.Name):
                    deps["variables"].append({
                        "name": node.id,
                        "line": node.lineno,
                        "type": type(node.ctx).__name__
                    })

            return deps

        except Exception as e:
            logger.error(f"Error analyzing dependencies: {e}")
            return {}

    async def _analyze_impact(self, content: str, pattern: str) -> Dict[str, Any]:
        """Analyze pattern impact"""
        try:
            tree = ast.parse(content)
            impact = {
                "risk_level": "low",
                "affected_components": [],
                "suggestions": []
            }

            # Count pattern occurrences
            occurrences = content.count(pattern)
            if occurrences > 10:
                impact["risk_level"] = "high"
            elif occurrences > 5:
                impact["risk_level"] = "medium"

            # Analyze affected components
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    if pattern in ast.dump(node):
                        impact["affected_components"].append({
                            "type": type(node).__name__.replace("Def", ""),
                            "name": node.name,
                            "line": node.lineno
                        })

                        # Generate suggestions
                        if len(node.body) > 20:
                            impact["suggestions"].append({
                                "type": "refactor_suggestion",
                                "message": f"Consider breaking down {node.name} into smaller components",
                                "line": node.lineno
                            })

            return impact

        except Exception as e:
            logger.error(f"Error analyzing impact: {e}")
            return {}

class SuggestRefactoring(BaseTool):
    """Suggest refactoring for code patterns"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        pattern = arguments.get('pattern')
        scope = arguments.get('scope', 'all')

        if not pattern:
            return {"error": "Pattern is required"}

        cache_key = f"refactor_{pattern}_{scope}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = {
                "pattern": pattern,
                "scope": scope,
                "suggestions": await self._generate_suggestions(pattern, scope),
                "impact": await self._analyze_impact(pattern, scope),
                "alternatives": await self._suggest_alternatives(pattern)
            }

            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error generating refactoring suggestions: {e}")
            return {"error": str(e)}

    async def _generate_suggestions(self, pattern: str, scope: str) -> List[Dict[str, Any]]:
        """Generate refactoring suggestions"""
        suggestions = []

        # Basic suggestions based on pattern type
        if '_' in pattern:  # Likely a function or variable name
            suggestions.append({
                "type": "naming",
                "message": f"Consider using camelCase instead of snake_case for {pattern}",
                "example": self._to_camel_case(pattern)
            })

        if len(pattern) < 3:  # Too short name
            suggestions.append({
                "type": "naming",
                "message": "Consider using more descriptive name",
                "severity": "medium"
            })

        if len(pattern) > 30:  # Too long name
            suggestions.append({
                "type": "naming",
                "message": "Consider using shorter, more concise name",
                "severity": "medium"
            })

        return suggestions

    async def _analyze_impact(self, pattern: str, scope: str) -> Dict[str, Any]:
        """Analyze refactoring impact"""
        return {
            "risk_level": "medium",  # Default risk level
            "affected_areas": [
                "code readability",
                "maintainability",
                "extensibility"
            ],
            "effort_level": "medium",
            "benefits": [
                "improved code quality",
                "better maintainability",
                "clearer code structure"
            ]
        }

    async def _suggest_alternatives(self, pattern: str) -> List[Dict[str, Any]]:
        """Suggest alternative patterns"""
        alternatives = []

        # Common patterns and their alternatives
        patterns = {
            "get_instance": {
                "type": "singleton",
                "alternatives": ["dependency_injection", "factory_method"],
                "reason": "Reduces coupling and improves testability"
            },
            "factory": {
                "type": "creation",
                "alternatives": ["builder_pattern", "abstract_factory"],
                "reason": "More flexible object creation"
            }
        }

        for key, value in patterns.items():
            if key in pattern.lower():
                alternatives.append(value)

        return alternatives

    def _to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case to camelCase"""
        components = snake_str.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])


class CodePatternAnalyzer(BaseTool):
    """Analyze and detect code patterns"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        path = arguments.get('path')
        if not path:
            return {"error": "Path is required"}

        path = self._normalize_path(path)
        if not self._validate_path(path):
            return {"error": "Invalid path"}

        cache_key = f"code_patterns_{path}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = {
                "design_patterns": await self._find_design_patterns(path),
                "anti_patterns": await self._find_anti_patterns(path),
                "code_smells": await self._find_code_smells(path),
                "metrics": await self._calculate_pattern_metrics(path),
                "suggestions": await self._generate_pattern_suggestions(path)
            }

            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error analyzing code patterns: {e}")
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

    async def _find_design_patterns(self, path: Path) -> List[Dict[str, Any]]:
        """Find common design patterns"""
        patterns = []

        try:
            for py_file in path.rglob('*.py'):
                if not self._should_skip(py_file):
                    content = safe_read_file(str(py_file))
                    if not content:
                        continue

                    try:
                        tree = ast.parse(content)

                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef):
                                # Singleton Pattern
                                if self._is_singleton(node):
                                    patterns.append({
                                        "type": "singleton",
                                        "class": node.name,
                                        "file": str(py_file),
                                        "line": node.lineno
                                    })

                                # Factory Pattern
                                if self._is_factory(node):
                                    patterns.append({
                                        "type": "factory",
                                        "class": node.name,
                                        "file": str(py_file),
                                        "line": node.lineno
                                    })

                                # Observer Pattern
                                if self._is_observer(node):
                                    patterns.append({
                                        "type": "observer",
                                        "class": node.name,
                                        "file": str(py_file),
                                        "line": node.lineno
                                    })

                    except Exception as e:
                        logger.error(f"Error analyzing patterns in {py_file}: {e}")

        except Exception as e:
            logger.error(f"Error finding design patterns: {e}")

        return patterns

    async def _find_anti_patterns(self, path: Path) -> List[Dict[str, Any]]:
        """Find code anti-patterns"""
        anti_patterns = []

        try:
            for py_file in path.rglob('*.py'):
                if not self._should_skip(py_file):
                    content = safe_read_file(str(py_file))
                    if not content:
                        continue

                    try:
                        tree = ast.parse(content)

                        # God Class
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef):
                                methods = len([n for n in node.body if isinstance(n, ast.FunctionDef)])
                                if methods > 20:
                                    anti_patterns.append({
                                        "type": "god_class",
                                        "class": node.name,
                                        "file": str(py_file),
                                        "line": node.lineno,
                                        "method_count": methods
                                    })

                            # Long Method
                            elif isinstance(node, ast.FunctionDef):
                                if len(node.body) > 50:
                                    anti_patterns.append({
                                        "type": "long_method",
                                        "function": node.name,
                                        "file": str(py_file),
                                        "line": node.lineno,
                                        "length": len(node.body)
                                    })

                    except Exception as e:
                        logger.error(f"Error analyzing anti-patterns in {py_file}: {e}")

        except Exception as e:
            logger.error(f"Error finding anti-patterns: {e}")

        return anti_patterns

    async def _find_code_smells(self, path: Path) -> List[Dict[str, Any]]:
        """Find code smells"""
        smells = []

        try:
            for py_file in path.rglob('*.py'):
                if not self._should_skip(py_file):
                    content = safe_read_file(str(py_file))
                    if not content:
                        continue

                    try:
                        tree = ast.parse(content)

                        for node in ast.walk(tree):
                            # Duplicate Code (simple check)
                            if isinstance(node, ast.FunctionDef):
                                body_hash = hash(ast.dump(node))
                                similar_functions = self._find_similar_functions(tree, node, body_hash)
                                if similar_functions:
                                    smells.append({
                                        "type": "duplicate_code",
                                        "function": node.name,
                                        "file": str(py_file),
                                        "line": node.lineno,
                                        "similar_to": similar_functions
                                    })

                            # Too Many Parameters
                            if isinstance(node, ast.FunctionDef) and len(node.args.args) > 5:
                                smells.append({
                                    "type": "too_many_parameters",
                                    "function": node.name,
                                    "file": str(py_file),
                                    "line": node.lineno,
                                    "param_count": len(node.args.args)
                                })

                    except Exception as e:
                        logger.error(f"Error analyzing code smells in {py_file}: {e}")

        except Exception as e:
            logger.error(f"Error finding code smells: {e}")

        return smells

    async def _calculate_pattern_metrics(self, path: Path) -> Dict[str, Any]:
        """Calculate pattern-related metrics"""
        metrics = {
            "design_pattern_count": 0,
            "anti_pattern_count": 0,
            "code_smell_count": 0,
            "pattern_distribution": {},
            "highest_risk_files": []
        }

        try:
            design_patterns = await self._find_design_patterns(path)
            anti_patterns = await self._find_anti_patterns(path)
            code_smells = await self._find_code_smells(path)

            metrics["design_pattern_count"] = len(design_patterns)
            metrics["anti_pattern_count"] = len(anti_patterns)
            metrics["code_smell_count"] = len(code_smells)

            # Calculate pattern distribution
            all_patterns = design_patterns + anti_patterns
            for pattern in all_patterns:
                pattern_type = pattern["type"]
                metrics["pattern_distribution"][pattern_type] = \
                    metrics["pattern_distribution"].get(pattern_type, 0) + 1

            # Find high-risk files
            file_risks = {}
            for item in anti_patterns + code_smells:
                file_path = item["file"]
                file_risks[file_path] = file_risks.get(file_path, 0) + 1

            metrics["highest_risk_files"] = sorted(
                [{"file": k, "issues": v} for k, v in file_risks.items()],
                key=lambda x: x["issues"],
                reverse=True
            )[:5]

        except Exception as e:
            logger.error(f"Error calculating pattern metrics: {e}")

        return metrics

    async def _generate_pattern_suggestions(self, path: Path) -> List[Dict[str, Any]]:
        """Generate pattern-based suggestions"""
        suggestions = []

        try:
            metrics = await self._calculate_pattern_metrics(path)

            # Suggest refactoring for high-risk files
            for file in metrics["highest_risk_files"]:
                if file["issues"] > 5:
                    suggestions.append({
                        "type": "refactoring",
                        "file": file["file"],
                        "message": f"Consider refactoring: file has {file['issues']} quality issues",
                        "priority": "high"
                    })

            # Suggest pattern usage improvements
            if metrics["anti_pattern_count"] > metrics["design_pattern_count"]:
                suggestions.append({
                    "type": "pattern_usage",
                    "message": "Consider using more design patterns to improve code structure",
                    "priority": "medium"
                })

            # Suggest code smell cleanup
            if metrics["code_smell_count"] > 10:
                suggestions.append({
                    "type": "code_quality",
                    "message": "High number of code smells detected, consider code cleanup",
                    "priority": "high"
                })

        except Exception as e:
            logger.error(f"Error generating pattern suggestions: {e}")

        return suggestions

    def _is_singleton(self, node: ast.ClassDef) -> bool:
        """Check if class implements singleton pattern"""
        return any(
            isinstance(n, ast.FunctionDef) and
            (n.name == 'get_instance' or n.name == 'getInstance')
            for n in node.body
        )

    def _is_factory(self, node: ast.ClassDef) -> bool:
        """Check if class implements factory pattern"""
        return any(
            isinstance(n, ast.FunctionDef) and
            (n.name.startswith('create_') or n.name.startswith('make_'))
            for n in node.body
        )

    def _is_observer(self, node: ast.ClassDef) -> bool:
        """Check if class implements observer pattern"""
        observer_methods = {'update', 'notify', 'subscribe', 'unsubscribe'}
        class_methods = {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
        return bool(observer_methods & class_methods)

    def _find_similar_functions(
            self,
            tree: ast.AST,
            current_node: ast.FunctionDef,
            current_hash: int
    ) -> List[Dict[str, Any]]:
        """Find functions with similar structure"""
        similar = []

        for node in ast.walk(tree):
            if (isinstance(node, ast.FunctionDef) and
                    node.name != current_node.name and
                    hash(ast.dump(node)) == current_hash):
                similar.append({
                    "name": node.name,
                    "line": node.lineno
                })

        return similar


class PatternUsageAnalyzer(BaseTool):
    """Find pattern usages and perform pattern analysis"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        pattern = arguments.get('pattern')
        pattern_type = arguments.get('pattern_type', 'all')

        if not pattern:
            return {"error": "Pattern is required"}

        cache_key = f"pattern_usage_{pattern}_{pattern_type}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = {
                "pattern": pattern,
                "type": pattern_type,
                "occurrences": await self._find_occurrences(pattern, pattern_type),
                "statistics": await self._generate_statistics(pattern, pattern_type),
                "context": await self._analyze_context(pattern, pattern_type),
                "suggestions": await self._generate_suggestions(pattern, pattern_type)
            }

            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error analyzing pattern usage: {e}")
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

    async def _find_occurrences(self, pattern: str, pattern_type: str) -> List[Dict[str, Any]]:
        """Find pattern occurrences"""
        occurrences = []

        try:
            for py_file in Path('.').rglob('*.py'):
                if not self._should_skip(py_file):
                    content = safe_read_file(str(py_file))
                    if not content:
                        continue

                    try:
                        tree = ast.parse(content)

                        for node in ast.walk(tree):
                            occurrence = None

                            if pattern_type in ['all', 'function']:
                                if isinstance(node, ast.FunctionDef) and pattern in node.name:
                                    occurrence = {
                                        "type": "function",
                                        "name": node.name,
                                        "line": node.lineno,
                                        "args": len(node.args.args)
                                    }

                            if pattern_type in ['all', 'class']:
                                if isinstance(node, ast.ClassDef) and pattern in node.name:
                                    occurrence = {
                                        "type": "class",
                                        "name": node.name,
                                        "line": node.lineno,
                                        "methods": len([m for m in node.body if isinstance(m, ast.FunctionDef)])
                                    }

                            if pattern_type in ['all', 'variable']:
                                if isinstance(node, ast.Name) and pattern in node.id:
                                    occurrence = {
                                        "type": "variable",
                                        "name": node.id,
                                        "line": node.lineno,
                                        "context": type(node.ctx).__name__
                                    }

                            if pattern_type in ['all', 'code']:
                                if isinstance(node, ast.Expr) and pattern in ast.dump(node):
                                    occurrence = {
                                        "type": "code",
                                        "line": node.lineno,
                                        "content": ast.unparse(node)
                                    }

                            if occurrence:
                                occurrence["file"] = str(py_file)
                                occurrences.append(occurrence)

                    except Exception as e:
                        logger.error(f"Error analyzing {py_file}: {e}")

        except Exception as e:
            logger.error(f"Error finding occurrences: {e}")

        return occurrences

    async def _generate_statistics(self, pattern: str, pattern_type: str) -> Dict[str, Any]:
        """Generate pattern usage statistics"""
        stats = {
            "total_occurrences": 0,
            "by_type": {},
            "by_file": {},
            "frequency": {}
        }

        try:
            occurrences = await self._find_occurrences(pattern, pattern_type)
            stats["total_occurrences"] = len(occurrences)

            # Count by type
            for occ in occurrences:
                stats["by_type"][occ["type"]] = stats["by_type"].get(occ["type"], 0) + 1
                stats["by_file"][occ["file"]] = stats["by_file"].get(occ["file"], 0) + 1

            # Calculate frequency metrics
            if stats["total_occurrences"] > 0:
                total_files = len(set(occ["file"] for occ in occurrences))
                stats["frequency"] = {
                    "occurrences_per_file": stats["total_occurrences"] / total_files,
                    "files_with_pattern": total_files
                }

        except Exception as e:
            logger.error(f"Error generating statistics: {e}")

        return stats

    async def _analyze_context(self, pattern: str, pattern_type: str) -> Dict[str, Any]:
        """Analyze pattern usage context"""
        context = {
            "common_patterns": [],
            "related_patterns": [],
            "usage_examples": []
        }

        try:
            occurrences = await self._find_occurrences(pattern, pattern_type)

            for occ in occurrences:
                if len(context["usage_examples"]) < 5:  # Limit examples
                    content = safe_read_file(occ["file"])
                    if content:
                        lines = content.splitlines()
                        line_idx = occ["line"] - 1

                        # Get context lines
                        start = max(0, line_idx - 2)
                        end = min(len(lines), line_idx + 3)

                        context["usage_examples"].append({
                            "file": occ["file"],
                            "line": occ["line"],
                            "code": lines[start:end],
                            "type": occ["type"]
                        })

            # Find related patterns (patterns that often appear together)
            pattern_co_occurrences = {}
            for occ in occurrences:
                content = safe_read_file(occ["file"])
                if content:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.Name, ast.FunctionDef, ast.ClassDef)):
                            name = getattr(node, 'id', getattr(node, 'name', None))
                            if name and name != pattern:
                                pattern_co_occurrences[name] = pattern_co_occurrences.get(name, 0) + 1

            # Get most common co-occurring patterns
            context["related_patterns"] = sorted(
                [{"pattern": k, "count": v} for k, v in pattern_co_occurrences.items()],
                key=lambda x: x["count"],
                reverse=True
            )[:5]

        except Exception as e:
            logger.error(f"Error analyzing context: {e}")

        return context

    async def _generate_suggestions(self, pattern: str, pattern_type: str) -> List[Dict[str, Any]]:
        """Generate pattern-related suggestions"""
        suggestions = []

        try:
            stats = await self._generate_statistics(pattern, pattern_type)

            # Suggest refactoring if pattern is used too frequently
            if stats["total_occurrences"] > 20:
                suggestions.append({
                    "type": "refactoring",
                    "message": f"Consider refactoring: pattern '{pattern}' is used frequently",
                    "severity": "high"
                })

            # Suggest consistency in usage
            if pattern_type == 'variable' and '_' in pattern:
                suggestions.append({
                    "type": "naming",
                    "message": "Consider using consistent naming convention",
                    "example": self._to_camel_case(pattern)
                })

            # Suggest documentation if pattern is widely used
            if stats["total_occurrences"] > 10:
                suggestions.append({
                    "type": "documentation",
                    "message": f"Consider documenting the pattern usage and purpose",
                    "importance": "medium"
                })

            # Check for pattern complexity
            context = await self._analyze_context(pattern, pattern_type)
            if len(context["related_patterns"]) > 5:
                suggestions.append({
                    "type": "complexity",
                    "message": "Pattern has many dependencies, consider simplifying",
                    "severity": "medium"
                })

        except Exception as e:
            logger.error(f"Error generating suggestions: {e}")

        return suggestions

    def _to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case to camelCase"""
        components = snake_str.split('_')
        return components[0] + ''.join(x.title() for x in components[1:])
