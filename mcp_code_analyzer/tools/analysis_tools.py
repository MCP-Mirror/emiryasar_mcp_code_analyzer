import ast
import logging
from pathlib import Path
from typing import Dict, Any, List
from .base import BaseTool ,safe_read_file
import networkx as nx
import logging
import ast
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import re
import tokenize
import io
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class CodeStructureAnalyzer(BaseTool):
    """Analyze code structure and architecture"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        path = arguments.get('path')
        if not path:
            return {"error": "Path is required"}

        path = self._normalize_path(path)
        if not self._validate_path(path):
            return {"error": "Invalid path"}

        cache_key = f"structure_{path}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = {
                "structure": await self._analyze_structure(path),
                "metrics": await self._analyze_metrics(path),
                "dependencies": await self._analyze_dependencies(path),
                "architecture": await self._analyze_architecture(path)
            }

            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error analyzing code structure: {e}")
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

    async def _analyze_structure(self, path: Path) -> Dict[str, Any]:
        """Analyze code structure while maintaining existing path handling"""
        structure = {
            "modules": [],
            "classes": [],
            "functions": [],
            "hierarchy": {}
        }

        try:
            if isinstance(path, str):
                path = Path(path)

            for py_file in path.rglob('*.py'):
                if not self._should_skip(py_file):
                    content = safe_read_file(str(py_file))
                    if not content:
                        continue

                    try:
                        tree = ast.parse(content)
                        module_info = {
                            "name": py_file.stem,
                            "path": str(py_file.relative_to(path) if path.exists() else py_file),
                            "classes": [],
                            "functions": []
                        }

                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef):
                                class_info = {
                                    "name": node.name,
                                    "line": node.lineno,
                                    "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)],
                                    "bases": [b.id for b in node.bases if isinstance(b, ast.Name)]
                                }
                                module_info["classes"].append(class_info)
                                structure["classes"].append(class_info)

                            elif isinstance(node, ast.FunctionDef):
                                if not isinstance(node.parent, ast.ClassDef):
                                    func_info = {
                                        "name": node.name,
                                        "line": node.lineno,
                                        "args": len(node.args.args),
                                        "module": module_info["name"]
                                    }
                                    module_info["functions"].append(func_info)
                                    structure["functions"].append(func_info)

                        structure["modules"].append(module_info)
                    except Exception as e:
                        logger.error(f"Error parsing {py_file}: {e}")
                        continue

            # Build hierarchy
            structure["hierarchy"] = self._build_hierarchy(structure["classes"])

        except Exception as e:
            logger.error(f"Error analyzing structure: {e}")

        return structure

    async def _analyze_metrics(self, path: Path) -> Dict[str, Any]:
        """Analyze code metrics"""
        metrics = {
            "total_lines": 0,
            "code_lines": 0,
            "comment_lines": 0,
            "class_count": 0,
            "function_count": 0,
            "complexity": {
                "average": 0,
                "highest": 0,
                "modules": {}
            }
        }

        file_count = 0
        total_complexity = 0

        try:
            for py_file in path.rglob('*.py'):
                if not self._should_skip(py_file):
                    content = safe_read_file(str(py_file))
                    if not content:
                        continue

                    file_count += 1
                    lines = content.splitlines()
                    metrics["total_lines"] += len(lines)

                    # Count different types of lines
                    for line in lines:
                        stripped = line.strip()
                        if stripped and not stripped.startswith('#'):
                            metrics["code_lines"] += 1
                        elif stripped.startswith('#'):
                            metrics["comment_lines"] += 1

                    # Analyze AST
                    try:
                        tree = ast.parse(content)
                        module_complexity = 0

                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef):
                                metrics["class_count"] += 1
                                module_complexity += len(node.body)

                            elif isinstance(node, ast.FunctionDef):
                                metrics["function_count"] += 1
                                module_complexity += len(node.body)

                        metrics["complexity"]["modules"][py_file.stem] = module_complexity
                        total_complexity += module_complexity
                        metrics["complexity"]["highest"] = max(
                            metrics["complexity"]["highest"],
                            module_complexity
                        )

                    except Exception as e:
                        logger.error(f"Error analyzing metrics for {py_file}: {e}")

            if file_count > 0:
                metrics["complexity"]["average"] = total_complexity / file_count

        except Exception as e:
            logger.error(f"Error analyzing metrics: {e}")

        return metrics

    async def _analyze_dependencies(self, path: Path) -> Dict[str, Any]:
        """Analyze code dependencies"""
        deps = {
            "imports": {},
            "dependencies": {},
            "cycles": []
        }

        # Create dependency graph
        graph = nx.DiGraph()

        try:
            for py_file in path.rglob('*.py'):
                if not self._should_skip(py_file):
                    content = safe_read_file(str(py_file))
                    if not content:
                        continue

                    module_name = py_file.stem
                    deps["imports"][module_name] = []

                    try:
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for name in node.names:
                                    deps["imports"][module_name].append({
                                        "name": name.name,
                                        "alias": name.asname,
                                        "type": "direct"
                                    })
                                    graph.add_edge(module_name, name.name)

                            elif isinstance(node, ast.ImportFrom):
                                if node.module:
                                    deps["imports"][module_name].append({
                                        "name": node.module,
                                        "imports": [n.name for n in node.names],
                                        "type": "from"
                                    })
                                    graph.add_edge(module_name, node.module)

                    except Exception as e:
                        logger.error(f"Error analyzing dependencies for {py_file}: {e}")

            # Find dependency cycles
            try:
                cycles = list(nx.simple_cycles(graph))
                deps["cycles"] = [{"modules": cycle} for cycle in cycles]
            except Exception as e:
                logger.error(f"Error finding dependency cycles: {e}")

            # Convert graph to dependency dict
            for node in graph.nodes():
                deps["dependencies"][node] = {
                    "imports": list(graph.successors(node)),
                    "imported_by": list(graph.predecessors(node))
                }

        except Exception as e:
            logger.error(f"Error analyzing dependencies: {e}")

        return deps

    async def _analyze_architecture(self, path: Path) -> Dict[str, Any]:
        """Analyze code architecture"""
        architecture = {
            "layers": [],
            "components": [],
            "interfaces": [],
            "patterns": []
        }

        try:
            for py_file in path.rglob('*.py'):
                if not self._should_skip(py_file):
                    content = safe_read_file(str(py_file))
                    if not content:
                        continue

                    try:
                        tree = ast.parse(content)

                        # Analyze interfaces (abstract classes)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef):
                                if any(isinstance(child, ast.FunctionDef) and
                                       isinstance(child.body[0], ast.Pass)
                                       for child in node.body):
                                    architecture["interfaces"].append({
                                        "name": node.name,
                                        "file": str(py_file.relative_to(path)),
                                        "methods": [m.name for m in node.body
                                                    if isinstance(m, ast.FunctionDef)]
                                    })

                                # Detect common patterns
                                if any(base.id == 'ABC' for base in node.bases
                                       if isinstance(base, ast.Name)):
                                    architecture["patterns"].append({
                                        "type": "abstract_class",
                                        "name": node.name,
                                        "file": str(py_file.relative_to(path))
                                    })

                    except Exception as e:
                        logger.error(f"Error analyzing architecture for {py_file}: {e}")

            # Identify layers based on directory structure
            layers = set()
            for item in path.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    layers.add(item.name)

            architecture["layers"] = sorted(list(layers))

            # Identify components (modules with multiple classes)
            components = {}
            for cls in architecture["interfaces"]:
                module = Path(cls["file"]).parent.name
                if module not in components:
                    components[module] = {
                        "name": module,
                        "interfaces": [],
                        "implementations": []
                    }
                components[module]["interfaces"].append(cls["name"])

            architecture["components"] = list(components.values())

        except Exception as e:
            logger.error(f"Error analyzing architecture: {e}")

        return architecture

    def _build_hierarchy(self, classes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build class hierarchy"""
        hierarchy = {}

        for cls in classes:
            if not cls["bases"]:
                if cls["name"] not in hierarchy:
                    hierarchy[cls["name"]] = []
            else:
                for base in cls["bases"]:
                    if base not in hierarchy:
                        hierarchy[base] = []
                    hierarchy[base].append(cls["name"])

        return hierarchy

class ImportAnalyzer(BaseTool):
    """Analyze import statements and dependencies"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        path = arguments.get('path')
        if not path:
            return {"error": "Path is required"}

        path = self._normalize_path(path)
        if not self._validate_path(path):
            return {"error": "Invalid path"}

        cache_key = f"imports_{path}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = {
                "imports": await self._analyze_imports(path),
                "statistics": await self._generate_statistics(path),
                "issues": await self._find_issues(path),
                "suggestions": await self._generate_suggestions(path)
            }

            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error analyzing imports: {e}")
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

    async def _analyze_imports(self, path: Path) -> Dict[str, Any]:
        """Analyze all imports in the project"""
        imports = {
            "standard_lib": set(),
            "third_party": set(),
            "local": set(),
            "by_file": {}
        }

        try:
            for py_file in path.rglob('*.py'):
                if not self._should_skip(py_file):
                    content = safe_read_file(str(py_file))
                    if not content:
                        continue

                    file_imports = {
                        "standard_lib": [],
                        "third_party": [],
                        "local": []
                    }

                    try:
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for name in node.names:
                                    import_info = {
                                        "name": name.name,
                                        "alias": name.asname,
                                        "line": node.lineno
                                    }
                                    if self._is_stdlib_import(name.name):
                                        imports["standard_lib"].add(name.name)
                                        file_imports["standard_lib"].append(import_info)
                                    else:
                                        imports["third_party"].add(name.name)
                                        file_imports["third_party"].append(import_info)

                            elif isinstance(node, ast.ImportFrom):
                                for name in node.names:
                                    import_info = {
                                        "module": node.module,
                                        "name": name.name,
                                        "alias": name.asname,
                                        "line": node.lineno
                                    }
                                    # Assume local import if relative or matches project structure
                                    if node.level > 0 or str(path) in str(py_file):
                                        imports["local"].add(f"{node.module}.{name.name}")
                                        file_imports["local"].append(import_info)
                                    elif self._is_stdlib_import(node.module):
                                        imports["standard_lib"].add(f"{node.module}.{name.name}")
                                        file_imports["standard_lib"].append(import_info)
                                    else:
                                        imports["third_party"].add(f"{node.module}.{name.name}")
                                        file_imports["third_party"].append(import_info)

                    except Exception as e:
                        logger.error(f"Error analyzing imports for {py_file}: {e}")

                    imports["by_file"][str(py_file.relative_to(path))] = file_imports

        except Exception as e:
            logger.error(f"Error analyzing imports: {e}")

        # Convert sets to sorted lists for JSON serialization
        imports["standard_lib"] = sorted(imports["standard_lib"])
        imports["third_party"] = sorted(imports["third_party"])
        imports["local"] = sorted(imports["local"])

        return imports

    async def _generate_statistics(self, path: Path) -> Dict[str, Any]:
        """Generate import statistics"""
        stats = {
            "total_imports": 0,
            "by_type": {
                "standard_lib": 0,
                "third_party": 0,
                "local": 0
            },
            "most_imported": [],
            "files_with_most_imports": []
        }

        try:
            imports = await self._analyze_imports(path)
            import_counts = {}
            file_import_counts = {}

            # Count imports by type
            stats["by_type"]["standard_lib"] = len(imports["standard_lib"])
            stats["by_type"]["third_party"] = len(imports["third_party"])
            stats["by_type"]["local"] = len(imports["local"])
            stats["total_imports"] = sum(stats["by_type"].values())

            # Count individual imports
            for file_imports in imports["by_file"].values():
                for import_type in ["standard_lib", "third_party", "local"]:
                    for imp in file_imports[import_type]:
                        name = imp.get("module", imp["name"])
                        import_counts[name] = import_counts.get(name, 0) + 1

            # Count imports per file
            for file, file_imports in imports["by_file"].items():
                count = sum(len(imps) for imps in file_imports.values())
                file_import_counts[file] = count

            # Get most used imports
            stats["most_imported"] = sorted(
                [{"name": k, "count": v} for k, v in import_counts.items()],
                key=lambda x: x["count"],
                reverse=True
            )[:10]

            # Get files with most imports
            stats["files_with_most_imports"] = sorted(
                [{"file": k, "count": v} for k, v in file_import_counts.items()],
                key=lambda x: x["count"],
                reverse=True
            )[:10]

        except Exception as e:
            logger.error(f"Error generating import statistics: {e}")

        return stats

    async def _find_issues(self, path: Path) -> List[Dict[str, Any]]:
        """Find potential import issues"""
        issues = []

        try:
            imports = await self._analyze_imports(path)

            for file, file_imports in imports["by_file"].items():
                # Check for duplicate imports
                all_imports = []
                for imp_type in file_imports.values():
                    for imp in imp_type:
                        name = imp.get("module", imp["name"])
                        if name in all_imports:
                            issues.append({
                                "type": "duplicate_import",
                                "file": file,
                                "line": imp["line"],
                                "import": name,
                                "severity": "warning"
                            })
                        all_imports.append(name)

                # Check for unused imports (basic check)
                content = safe_read_file(str(Path(path) / file))
                if content:
                    for imp_type in file_imports.values():
                        for imp in imp_type:
                            name = imp.get("name")
                            if name and name not in content.split(f"import {name}")[1:]:
                                issues.append({
                                    "type": "potentially_unused",
                                    "file": file,
                                    "line": imp["line"],
                                    "import": name,
                                    "severity": "info"
                                })

        except Exception as e:
            logger.error(f"Error finding import issues: {e}")

        return issues

    async def _generate_suggestions(self, path: Path) -> List[Dict[str, Any]]:
        """Generate import-related suggestions"""
        suggestions = []

        try:
            stats = await self._generate_statistics(path)
            issues = await self._find_issues(path)

            # Suggest organizing imports if there are many
            if stats["total_imports"] > 50:
                suggestions.append({
                    "type": "organization",
                    "message": "Consider using import organization tools like isort",
                    "reason": "Large number of imports"
                })

            # Suggest import aliasing for commonly used long names
            for imp in stats["most_imported"]:
                if len(imp["name"].split('.')) > 2 and imp["count"] > 5:
                    suggestions.append({
                        "type": "alias",
                        "message": f"Consider using an alias for frequently used import: {imp['name']}",
                        "example": f"import {imp['name']} as {imp['name'].split('.')[-1].lower()}"
                    })

            # Suggest fixing issues
            duplicate_count = len([i for i in issues if i["type"] == "duplicate_import"])
            if duplicate_count > 0:
                suggestions.append({
                    "type": "cleanup",
                    "message": f"Clean up {duplicate_count} duplicate imports",
                    "importance": "high"
                })

        except Exception as e:
            logger.error(f"Error generating import suggestions: {e}")

        return suggestions

    def _is_stdlib_import(self, module_name: str) -> bool:
        """Check if import is from Python standard library"""
        stdlib_modules = {
            'abc', 'argparse', 'ast', 'asyncio', 'collections', 'concurrent',
            'contextlib', 'datetime', 'functools', 'importlib', 'inspect', 'io',
            'json', 'logging', 'math', 'os', 'pathlib', 'pickle', 're', 'sys',
            'threading', 'time', 'typing', 'uuid', 'warnings'
        }
        return module_name.split('.')[0] in stdlib_modules

@dataclass
class AnalysisResult:
    """Code analysis result container"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class ProjectAnalyzer(BaseTool):
    """Advanced project structure and code analysis tool"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        operation = arguments.get('operation', 'analyze')
        target_path = arguments.get('path', '.')

        operations = {
            'analyze': self._analyze_project,
            'structure': self._analyze_structure,
            'dependencies': self._analyze_dependencies,
            'complexity': self._analyze_complexity,
            'patterns': self._analyze_patterns
        }

        if operation not in operations:
            return {"error": f"Unknown operation: {operation}"}

        try:
            result = await operations[operation](Path(target_path), arguments)
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"ProjectAnalyzer operation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _analyze_project(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Perform comprehensive project analysis"""
        try:
            structure = await self._analyze_structure(path, args)
            dependencies = await self._analyze_dependencies(path, args)
            complexity = await self._analyze_complexity(path, args)
            patterns = await self._analyze_patterns(path, args)

            return {
                "overview": {
                    "path": str(path),
                    "timestamp": datetime.now().isoformat(),
                    "total_files": len(structure.get("files", [])),
                    "total_lines": complexity.get("total_lines", 0)
                },
                "structure": structure,
                "dependencies": dependencies,
                "complexity": complexity,
                "patterns": patterns
            }
        except Exception as e:
            raise RuntimeError(f"Project analysis failed: {e}")

    async def _analyze_structure(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze project structure"""
        files = []
        modules = []

        try:
            for file_path in path.rglob("*.py"):
                if self._should_skip(file_path):
                    continue

                with tokenize.open(file_path) as f:
                    content = f.read()

                try:
                    tree = ast.parse(content)

                    module_info = {
                        "name": file_path.stem,
                        "path": str(file_path.relative_to(path)),
                        "classes": [],
                        "functions": [],
                        "imports": []
                    }

                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            module_info["classes"].append({
                                "name": node.name,
                                "line": node.lineno,
                                "methods": len([m for m in node.body if isinstance(m, ast.FunctionDef)]),
                                "bases": [base.id for base in node.bases if isinstance(base, ast.Name)]
                            })
                        elif isinstance(node, ast.FunctionDef):
                            if not any(isinstance(parent, ast.ClassDef) for parent in ast.walk(tree)):
                                module_info["functions"].append({
                                    "name": node.name,
                                    "line": node.lineno,
                                    "arguments": len(node.args.args),
                                    "decorators": [d.id for d in node.decorator_list if isinstance(d, ast.Name)]
                                })
                        elif isinstance(node, (ast.Import, ast.ImportFrom)):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    module_info["imports"].append({
                                        "type": "import",
                                        "name": alias.name,
                                        "alias": alias.asname
                                    })
                            else:
                                for alias in node.names:
                                    module_info["imports"].append({
                                        "type": "from",
                                        "module": node.module,
                                        "name": alias.name,
                                        "alias": alias.asname
                                    })

                    modules.append(module_info)
                    files.append({
                        "path": str(file_path.relative_to(path)),
                        "size": file_path.stat().st_size,
                        "last_modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                    })

                except Exception as e:
                    logger.error(f"Failed to analyze {file_path}: {e}")

            return {
                "files": files,
                "modules": modules,
                "statistics": {
                    "total_files": len(files),
                    "total_modules": len(modules),
                    "total_classes": sum(len(m["classes"]) for m in modules),
                    "total_functions": sum(len(m["functions"]) for m in modules)
                }
            }

        except Exception as e:
            raise RuntimeError(f"Structure analysis failed: {e}")

    async def _analyze_dependencies(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze project dependencies"""
        try:
            import_graph = {}
            external_deps = set()
            stdlib_deps = set()

            for file_path in path.rglob("*.py"):
                if self._should_skip(file_path):
                    continue

                with tokenize.open(file_path) as f:
                    content = f.read()

                try:
                    tree = ast.parse(content)
                    relative_path = str(file_path.relative_to(path))
                    import_graph[relative_path] = {"imports": [], "imported_by": []}

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                import_graph[relative_path]["imports"].append(alias.name)
                                if self._is_stdlib_module(alias.name):
                                    stdlib_deps.add(alias.name)
                                else:
                                    external_deps.add(alias.name)
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                import_graph[relative_path]["imports"].append(node.module)
                                if self._is_stdlib_module(node.module):
                                    stdlib_deps.add(node.module)
                                else:
                                    external_deps.add(node.module)

                except Exception as e:
                    logger.error(f"Failed to analyze dependencies in {file_path}: {e}")

            # Build imported_by relationships
            for file_path, deps in import_graph.items():
                for imported in deps["imports"]:
                    for other_file, other_deps in import_graph.items():
                        if imported in other_file:
                            other_deps["imported_by"].append(file_path)

            return {
                "import_graph": import_graph,
                "external_dependencies": sorted(list(external_deps)),
                "stdlib_dependencies": sorted(list(stdlib_deps)),
                "statistics": {
                    "total_imports": sum(len(d["imports"]) for d in import_graph.values()),
                    "external_deps_count": len(external_deps),
                    "stdlib_deps_count": len(stdlib_deps)
                }
            }

        except Exception as e:
            raise RuntimeError(f"Dependency analysis failed: {e}")

    async def _analyze_complexity(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze code complexity metrics"""
        try:
            complexity_data = {
                "files": {},
                "total_lines": 0,
                "total_complexity": 0,
                "average_complexity": 0,
                "hotspots": []
            }

            file_count = 0

            for file_path in path.rglob("*.py"):
                if self._should_skip(file_path):
                    continue

                with tokenize.open(file_path) as f:
                    content = f.read()

                try:
                    tree = ast.parse(content)
                    lines = content.splitlines()

                    file_complexity = {
                        "lines": len(lines),
                        "code_lines": len([l for l in lines if l.strip() and not l.strip().startswith("#")]),
                        "classes": [],
                        "functions": [],
                        "complexity_score": 0
                    }

                    # Analyze classes and methods
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            class_info = {
                                "name": node.name,
                                "methods": [],
                                "complexity": self._calculate_node_complexity(node)
                            }

                            for method in node.body:
                                if isinstance(method, ast.FunctionDef):
                                    method_complexity = self._calculate_node_complexity(method)
                                    class_info["methods"].append({
                                        "name": method.name,
                                        "complexity": method_complexity
                                    })
                                    class_info["complexity"] += method_complexity

                            file_complexity["classes"].append(class_info)
                            file_complexity["complexity_score"] += class_info["complexity"]

                        elif isinstance(node, ast.FunctionDef):
                            if not any(isinstance(parent, ast.ClassDef) for parent in ast.walk(tree)):
                                func_complexity = self._calculate_node_complexity(node)
                                file_complexity["functions"].append({
                                    "name": node.name,
                                    "complexity": func_complexity
                                })
                                file_complexity["complexity_score"] += func_complexity

                    relative_path = str(file_path.relative_to(path))
                    complexity_data["files"][relative_path] = file_complexity
                    complexity_data["total_lines"] += file_complexity["lines"]
                    complexity_data["total_complexity"] += file_complexity["complexity_score"]

                    # Track potential hotspots
                    if file_complexity["complexity_score"] > 20:  # Arbitrary threshold
                        complexity_data["hotspots"].append({
                            "file": relative_path,
                            "complexity": file_complexity["complexity_score"],
                            "lines": file_complexity["lines"]
                        })

                    file_count += 1

                except Exception as e:
                    logger.error(f"Failed to analyze complexity in {file_path}: {e}")

            if file_count > 0:
                complexity_data["average_complexity"] = complexity_data["total_complexity"] / file_count

            # Sort hotspots by complexity
            complexity_data["hotspots"].sort(key=lambda x: x["complexity"], reverse=True)

            return complexity_data

        except Exception as e:
            raise RuntimeError(f"Complexity analysis failed: {e}")

    async def _analyze_patterns(self, path: Path, args: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze code patterns and anti-patterns"""
        try:
            patterns_data = {
                "design_patterns": [],
                "anti_patterns": [],
                "code_smells": [],
                "best_practices": {
                    "followed": [],
                    "violations": []
                }
            }

            for file_path in path.rglob("*.py"):
                if self._should_skip(file_path):
                    continue

                with tokenize.open(file_path) as f:
                    content = f.read()

                try:
                    tree = ast.parse(content)
                    relative_path = str(file_path.relative_to(path))

                    # Analyze design patterns
                    self._find_design_patterns(tree, relative_path, patterns_data)

                    # Analyze anti-patterns and code smells
                    self._find_anti_patterns(tree, relative_path, patterns_data)

                    # Check best practices
                    self._check_best_practices(tree, relative_path, patterns_data)

                except Exception as e:
                    logger.error(f"Failed to analyze patterns in {file_path}: {e}")

            return patterns_data

        except Exception as e:
            raise RuntimeError(f"Pattern analysis failed: {e}")

    def _calculate_node_complexity(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity of an AST node"""
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1

        return complexity

    def _is_stdlib_module(self, module_name: str) -> bool:
        """Check if a module is from Python standard library"""
        stdlib_modules = {
            'abc', 'argparse', 'ast', 'asyncio', 'collections', 'concurrent',
            'contextlib', 'datetime', 'functools', 'importlib', 'inspect', 'io',
            'json', 'logging', 'math', 'os', 'pathlib', 'pickle', 're', 'sys',
            'threading', 'time', 'typing', 'uuid', 'warnings'
        }
        return module_name.split('.')[0] in stdlib_modules

    def _find_design_patterns(self, tree: ast.AST, file_path: str,
                              patterns_data: Dict[str, Any]) -> None:
        """Find common design patterns in code"""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Singleton pattern
                if any(method.name == 'get_instance' for method in node.body
                       if isinstance(method, ast.FunctionDef)):
                    patterns_data["design_patterns"].append({
                        "type": "singleton",
                        "file": file_path,
                        "class": node.name,
                        "line": node.lineno
                    })

                # Factory pattern
                if any(method.name.startswith(('create_', 'make_'))
                       for method in node.body if isinstance(method, ast.FunctionDef)):
                    patterns_data["design_patterns"].append({
                        "type": "factory",
                        "file": file_path,
                        "class": node.name,
                        "line": node.lineno
                    })

                # Observer pattern
                if any(method.name in ('update', 'notify', 'subscribe', 'unsubscribe')
                       for method in node.body if isinstance(method, ast.FunctionDef)):
                    patterns_data["design_patterns"].append({
                        "type": "observer",
                        "file": file_path,
                        "class": node.name,
                        "line": node.lineno
                    })

    def _find_anti_patterns(self, tree: ast.AST, file_path: str,
                            patterns_data: Dict[str, Any]) -> None:
        """Find anti-patterns and code smells"""
        for node in ast.walk(tree):
            # God Class (too many methods)
            if isinstance(node, ast.ClassDef):
                methods = len([n for n in node.body if isinstance(n, ast.FunctionDef)])
                if methods > 20:
                    patterns_data["anti_patterns"].append({
                        "type": "god_class",
                        "file": file_path,
                        "class": node.name,
                        "methods": methods,
                        "line": node.lineno
                    })

            # Long Method
            if isinstance(node, ast.FunctionDef):
                if len(node.body) > 50:
                    patterns_data["code_smells"].append({
                        "type": "long_method",
                        "file": file_path,
                        "function": node.name,
                        "length": len(node.body),
                        "line": node.lineno
                    })

                # Too Many Parameters
                if len(node.args.args) > 5:
                    patterns_data["code_smells"].append({
                        "type": "too_many_parameters",
                        "file": file_path,
                        "function": node.name,
                        "parameter_count": len(node.args.args),
                        "line": node.lineno
                    })

    def _check_best_practices(self, tree: ast.AST, file_path: str,
                              patterns_data: Dict[str, Any]) -> None:
        """Check Python best practices"""
        for node in ast.walk(tree):
            # Proper docstrings
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                if ast.get_docstring(node):
                    patterns_data["best_practices"]["followed"].append({
                        "type": "has_docstring",
                        "file": file_path,
                        "name": node.name,
                        "line": node.lineno
                    })
                else:
                    patterns_data["best_practices"]["violations"].append({
                        "type": "missing_docstring",
                        "file": file_path,
                        "name": node.name,
                        "line": node.lineno
                    })

class CodeValidator(BaseTool):
    """Advanced code validation and quality checker"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target_path = arguments.get('path')
        validation_type = arguments.get('type', 'all')

        if not target_path:
            return {"error": "Path is required"}

        try:
            result = await self._validate_code(Path(target_path), validation_type)
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"CodeValidator operation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _validate_code(self, path: Path, validation_type: str) -> Dict[str, Any]:
        """Perform code validation"""
        validation_results = {
            "path": str(path),
            "timestamp": datetime.now().isoformat(),
            "validations": [],
            "summary": {
                "total_issues": 0,
                "error_count": 0,
                "warning_count": 0,
                "style_count": 0
            }
        }

        try:
            # Read file content
            with tokenize.open(path) as f:
                content = f.read()

            # Basic syntax check
            try:
                ast.parse(content)
                validation_results["validations"].append({
                    "type": "syntax",
                    "status": "passed",
                    "message": "Syntax is valid"
                })
            except SyntaxError as e:
                validation_results["validations"].append({
                    "type": "syntax",
                    "status": "failed",
                    "message": str(e),
                    "line": e.lineno,
                    "severity": "error"
                })
                validation_results["summary"]["error_count"] += 1

            # Style checks
            style_issues = self._check_style(content)
            validation_results["validations"].extend(style_issues)
            validation_results["summary"]["style_count"] += len(style_issues)

            # Security checks
            security_issues = self._check_security(content)
            validation_results["validations"].extend(security_issues)
            for issue in security_issues:
                if issue.get("severity") == "error":
                    validation_results["summary"]["error_count"] += 1
                else:
                    validation_results["summary"]["warning_count"] += 1

            # Complexity checks
            if validation_type in ['all', 'complexity']:
                complexity_issues = self._check_complexity(content)
                validation_results["validations"].extend(complexity_issues)
                validation_results["summary"]["warning_count"] += len(complexity_issues)

            validation_results["summary"]["total_issues"] = (
                    validation_results["summary"]["error_count"] +
                    validation_results["summary"]["warning_count"] +
                    validation_results["summary"]["style_count"]
            )

            return validation_results

        except Exception as e:
            raise RuntimeError(f"Validation failed: {e}")

    def _check_style(self, content: str) -> List[Dict[str, Any]]:
        """Check code style issues"""
        issues = []
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            # Line length check
            if len(line) > 79:
                issues.append({
                    "type": "style",
                    "rule": "line_length",
                    "message": "Line too long",
                    "line": i,
                    "severity": "style"
                })

            # Indentation check
            if line.strip() and (len(line) - len(line.lstrip())) % 4 != 0:
                issues.append({
                    "type": "style",
                    "rule": "indentation",
                    "message": "Incorrect indentation",
                    "line": i,
                    "severity": "style"
                })

            # Trailing whitespace
            if line.rstrip() != line:
                issues.append({
                    "type": "style",
                    "rule": "trailing_whitespace",
                    "message": "Trailing whitespace",
                    "line": i,
                    "severity": "style"
                })

        return issues

    def _check_security(self, content: str) -> List[Dict[str, Any]]:
        """Check security issues"""
        issues = []

        # Dangerous patterns
        dangerous_patterns = {
            r"eval\(": "Use of eval() is dangerous",
            r"exec\(": "Use of exec() is dangerous",
            r"os\.system\(": "Use subprocess module instead of os.system",
            r"subprocess\.call\(.*shell=True": "shell=True can be dangerous",
            r"pickle\.load": "Pickle can be dangerous with untrusted data"
        }

        for pattern, message in dangerous_patterns.items():
            matches = re.finditer(pattern, content)
            for match in matches:
                line_no = content.count('\n', 0, match.start()) + 1
                issues.append({
                    "type": "security",
                    "rule": pattern.replace("\\", ""),
                    "message": message,
                    "line": line_no,
                    "severity": "error"
                })

        return issues

    def _check_complexity(self, content: str) -> List[Dict[str, Any]]:
        """Check code complexity issues"""
        issues = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    complexity = self._calculate_complexity(node)
                    if complexity > 10:
                        issues.append({
                            "type": "complexity",
                            "rule": "cyclomatic_complexity",
                            "message": f"Function too complex (score: {complexity})",
                            "line": node.lineno,
                            "severity": "warning",
                            "details": {
                                "complexity_score": complexity,
                                "function_name": node.name
                            }
                        })

        except Exception as e:
            logger.error(f"Complexity check failed: {e}")

        return issues

    def _calculate_complexity(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity"""
        complexity = 1

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1

        return complexity

class SyntaxChecker(BaseTool):
    """Advanced syntax checking and analysis tool"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target_path = arguments.get('path')
        check_type = arguments.get('check_type', 'all')
        language = arguments.get('language', 'python')

        if not target_path:
            return {"error": "Path is required"}

        try:
            result = await self._analyze_syntax(Path(target_path), check_type, language)
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"SyntaxChecker operation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _analyze_syntax(self, path: Path, check_type: str,
                              language: str) -> Dict[str, Any]:
        """Analyze code syntax"""
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if language.lower() not in ['python', 'python3']:
            raise ValueError("Only Python language is supported")

        try:
            with tokenize.open(path) as f:
                content = f.read()

            analysis_result = {
                "file": str(path),
                "language": language,
                "timestamp": datetime.now().isoformat(),
                "syntax_valid": False,
                "details": []
            }

            # Basic syntax check
            try:
                tree = ast.parse(content)
                analysis_result["syntax_valid"] = True
            except SyntaxError as e:
                analysis_result["details"].append({
                    "type": "error",
                    "code": "syntax_error",
                    "message": str(e),
                    "line": e.lineno,
                    "offset": e.offset,
                    "text": e.text
                })
                return analysis_result

            # If syntax is valid, perform detailed analysis
            if check_type in ['all', 'tokens']:
                analysis_result["token_analysis"] = await self._analyze_tokens(content)

            if check_type in ['all', 'ast']:
                analysis_result["ast_analysis"] = await self._analyze_ast(tree)

            if check_type in ['all', 'imports']:
                analysis_result["import_analysis"] = await self._analyze_imports(tree)

            if check_type in ['all', 'naming']:
                analysis_result["naming_analysis"] = await self._analyze_naming(tree)

            return analysis_result

        except Exception as e:
            raise RuntimeError(f"Syntax analysis failed: {e}")

    async def _analyze_tokens(self, content: str) -> Dict[str, Any]:
        """Analyze code tokens"""
        token_analysis = {
            "token_count": 0,
            "token_types": {},
            "line_continuations": 0,
            "string_literals": 0,
            "tokens_by_line": {},
            "issues": []
        }

        try:
            # Create a string buffer and tokenize it
            buffer = io.StringIO(content)
            tokens = list(tokenize.generate_tokens(buffer.readline))

            current_line = 1
            line_tokens = []

            for token in tokens:
                token_type = tokenize.tok_name[token.type]
                token_analysis["token_count"] += 1
                token_analysis["token_types"][token_type] = \
                    token_analysis["token_types"].get(token_type, 0) + 1

                # Track tokens by line
                if token.start[0] != current_line:
                    if line_tokens:
                        token_analysis["tokens_by_line"][current_line] = line_tokens
                    current_line = token.start[0]
                    line_tokens = []
                line_tokens.append(token_type)

                # Check for specific tokens
                if token.type == tokenize.STRING:
                    token_analysis["string_literals"] += 1
                elif token.type == tokenize.NL:
                    token_analysis["line_continuations"] += 1

                # Check for potential issues
                if token.type == tokenize.OP and token.string == ';':
                    token_analysis["issues"].append({
                        "type": "style",
                        "message": "Semicolon found; multiple statements on one line",
                        "line": token.start[0]
                    })

            return token_analysis

        except Exception as e:
            logger.error(f"Token analysis failed: {e}")
            return {"error": str(e)}

    async def _analyze_ast(self, tree: ast.AST) -> Dict[str, Any]:
        """Analyze AST structure"""
        ast_analysis = {
            "node_types": {},
            "depth": 0,
            "branches": [],
            "complexity": {
                "functions": [],
                "classes": []
            }
        }

        def analyze_node(node, depth=0):
            node_type = type(node).__name__
            ast_analysis["node_types"][node_type] = \
                ast_analysis["node_types"].get(node_type, 0) + 1
            ast_analysis["depth"] = max(ast_analysis["depth"], depth)

            # Analyze functions
            if isinstance(node, ast.FunctionDef):
                function_info = {
                    "name": node.name,
                    "line": node.lineno,
                    "args": len(node.args.args),
                    "decorators": len(node.decorator_list),
                    "complexity": self._calculate_node_complexity(node)
                }
                ast_analysis["complexity"]["functions"].append(function_info)

            # Analyze classes
            elif isinstance(node, ast.ClassDef):
                class_info = {
                    "name": node.name,
                    "line": node.lineno,
                    "bases": len(node.bases),
                    "methods": len([n for n in node.body if isinstance(n, ast.FunctionDef)]),
                    "complexity": self._calculate_node_complexity(node)
                }
                ast_analysis["complexity"]["classes"].append(class_info)

            # Analyze branching
            elif isinstance(node, (ast.If, ast.For, ast.While)):
                branch_info = {
                    "type": type(node).__name__,
                    "line": node.lineno,
                    "depth": depth
                }
                ast_analysis["branches"].append(branch_info)

            for child in ast.iter_child_nodes(node):
                analyze_node(child, depth + 1)

        analyze_node(tree)
        return ast_analysis

    async def _analyze_imports(self, tree: ast.AST) -> Dict[str, Any]:
        """Analyze import statements"""
        import_analysis = {
            "imports": [],
            "from_imports": [],
            "stats": {
                "total_imports": 0,
                "unique_modules": set(),
                "relative_imports": 0
            }
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    import_info = {
                        "name": name.name,
                        "alias": name.asname,
                        "line": node.lineno
                    }
                    import_analysis["imports"].append(import_info)
                    import_analysis["stats"]["unique_modules"].add(name.name.split('.')[0])
                    import_analysis["stats"]["total_imports"] += 1

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for name in node.names:
                        import_info = {
                            "module": node.module,
                            "name": name.name,
                            "alias": name.asname,
                            "level": node.level,
                            "line": node.lineno
                        }
                        import_analysis["from_imports"].append(import_info)
                        import_analysis["stats"]["unique_modules"].add(node.module.split('.')[0])
                        import_analysis["stats"]["total_imports"] += 1
                        if node.level > 0:
                            import_analysis["stats"]["relative_imports"] += 1

        import_analysis["stats"]["unique_modules"] = list(import_analysis["stats"]["unique_modules"])
        return import_analysis

    async def _analyze_naming(self, tree: ast.AST) -> Dict[str, Any]:
        """Analyze naming conventions"""
        naming_analysis = {
            "conventions": {
                "snake_case": [],
                "camel_case": [],
                "non_conventional": []
            },
            "issues": [],
            "suggestions": []
        }

        def classify_name(name: str, node_type: str, line: int):
            if re.match(r'^[a-z][a-z0-9_]*$', name):
                naming_analysis["conventions"]["snake_case"].append({
                    "name": name,
                    "type": node_type,
                    "line": line
                })
            elif re.match(r'^[A-Z][a-zA-Z0-9]*$', name):
                naming_analysis["conventions"]["camel_case"].append({
                    "name": name,
                    "type": node_type,
                    "line": line
                })
            else:
                naming_analysis["conventions"]["non_conventional"].append({
                    "name": name,
                    "type": node_type,
                    "line": line
                })

                # Generate suggestion
                if node_type == "class" and not name[0].isupper():
                    naming_analysis["issues"].append({
                        "type": "naming_convention",
                        "message": f"Class name '{name}' should use CamelCase",
                        "line": line
                    })
                    naming_analysis["suggestions"].append({
                        "original": name,
                        "suggested": name[0].upper() + name[1:],
                        "line": line
                    })
                elif node_type == "function" and not name.islower():
                    snake_case = ''.join(['_' + c.lower() if c.isupper() else c.lower()
                                          for c in name]).lstrip('_')
                    naming_analysis["issues"].append({
                        "type": "naming_convention",
                        "message": f"Function name '{name}' should use snake_case",
                        "line": line
                    })
                    naming_analysis["suggestions"].append({
                        "original": name,
                        "suggested": snake_case,
                        "line": line
                    })

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classify_name(node.name, "class", node.lineno)
            elif isinstance(node, ast.FunctionDef):
                classify_name(node.name, "function", node.lineno)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                classify_name(node.id, "variable", node.lineno)

        return naming_analysis

    def _calculate_node_complexity(self, node: ast.AST) -> int:
        """Calculate complexity of an AST node"""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity