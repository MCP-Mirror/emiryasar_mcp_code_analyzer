import ast
import logging
from pathlib import Path
from typing import Dict, Any, List
import networkx as nx
from .base import BaseTool ,safe_read_file

logger = logging.getLogger(__name__)

class FileDependencyAnalyzer(BaseTool):
    """Analyze file dependencies"""

    def __init__(self):
        super().__init__()
        self.dependency_graph = nx.DiGraph()

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        file_path = arguments.get('file_path')
        if not file_path:
            return {"error": "File path is required"}

        path = self._normalize_path(file_path)
        if not self._validate_path(path):
            return {"error": "Invalid file path"}

        cache_key = f"file_deps_{path}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = {
                "direct_dependencies": await self._analyze_direct_dependencies(path),
                "indirect_dependencies": await self._analyze_indirect_dependencies(path),
                "dependents": await self._find_dependents(path),
                "cycles": await self._detect_cycles(path),
                "metrics": await self._calculate_metrics(path)
            }

            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error analyzing file dependencies: {e}")
            return {"error": str(e)}

    async def _analyze_direct_dependencies(self, path: Path) -> Dict[str, Any]:
        """Analyze direct dependencies"""
        deps = {
            "imports": [],
            "from_imports": [],
            "total_count": 0
        }

        try:
            content = safe_read_file(str(path))
            if content:
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for name in node.names:
                            deps["imports"].append({
                                "name": name.name,
                                "alias": name.asname,
                                "line": node.lineno
                            })
                            self.dependency_graph.add_edge(str(path), name.name)

                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            deps["from_imports"].append({
                                "module": node.module,
                                "names": [{"name": n.name, "alias": n.asname} for n in node.names],
                                "line": node.lineno,
                                "level": node.level
                            })
                            self.dependency_graph.add_edge(str(path), node.module)

                deps["total_count"] = len(deps["imports"]) + len(deps["from_imports"])

        except Exception as e:
            logger.error(f"Error analyzing direct dependencies: {e}")

        return deps

    async def _analyze_indirect_dependencies(self, path: Path) -> List[Dict[str, Any]]:
        """Analyze indirect dependencies"""
        indirect_deps = []

        try:
            # Get all paths except input path's successors
            all_paths = list(nx.dfs_edges(self.dependency_graph, str(path)))
            direct_deps = set(self.dependency_graph.successors(str(path)))

            for source, target in all_paths:
                if target not in direct_deps and source != str(path):
                    indirect_deps.append({
                        "name": target,
                        "through": source,
                        "path": self._find_shortest_path(str(path), target)
                    })

        except Exception as e:
            logger.error(f"Error analyzing indirect dependencies: {e}")

        return indirect_deps

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

    async def _find_dependents(self, path: Path) -> List[Dict[str, Any]]:
        """Find files that depend on this file"""
        dependents = []

        try:
            for py_file in Path('.').rglob('*.py'):
                if py_file != path and not self._should_skip(py_file):
                    content = safe_read_file(str(py_file))
                    if not content:
                        continue

                    tree = ast.parse(content)
                    found = False

                    for node in ast.walk(tree):
                        if isinstance(node, (ast.Import, ast.ImportFrom)):
                            module_name = path.stem
                            if (isinstance(node, ast.Import) and
                                    any(name.name == module_name for name in node.names)):
                                found = True
                                break
                            elif (isinstance(node, ast.ImportFrom) and
                                  node.module and module_name in node.module):
                                found = True
                                break

                    if found:
                        dependents.append({
                            "file": str(py_file),
                            "type": "direct" if self.dependency_graph.has_edge(str(py_file), str(path)) else "indirect"
                        })

        except Exception as e:
            logger.error(f"Error finding dependents: {e}")

        return dependents

    async def _detect_cycles(self, path: Path) -> List[List[str]]:
        """Detect dependency cycles"""
        cycles = []
        try:
            for cycle in nx.simple_cycles(self.dependency_graph):
                if str(path) in cycle:
                    cycles.append(cycle)
        except Exception as e:
            logger.error(f"Error detecting cycles: {e}")
        return cycles

    async def _calculate_metrics(self, path: Path) -> Dict[str, Any]:
        """Calculate dependency metrics"""
        metrics = {
            "fanin": 0,  # Number of files that depend on this
            "fanout": 0,  # Number of files this depends on
            "instability": 0.0,  # fanout / (fanin + fanout)
            "dependency_depth": 0  # Longest dependency chain
        }

        try:
            metrics["fanin"] = len(list(self.dependency_graph.predecessors(str(path))))
            metrics["fanout"] = len(list(self.dependency_graph.successors(str(path))))

            if metrics["fanin"] + metrics["fanout"] > 0:
                metrics["instability"] = metrics["fanout"] / (metrics["fanin"] + metrics["fanout"])

            # Calculate dependency depth
            depths = []
            for node in self.dependency_graph.nodes():
                try:
                    path_length = nx.shortest_path_length(self.dependency_graph, str(path), node)
                    depths.append(path_length)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue

            metrics["dependency_depth"] = max(depths) if depths else 0

        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")

        return metrics

    def _find_shortest_path(self, source: str, target: str) -> List[str]:
        """Find shortest dependency path between two modules"""
        try:
            return nx.shortest_path(self.dependency_graph, source, target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []


