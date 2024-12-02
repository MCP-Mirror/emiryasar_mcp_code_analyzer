import sqlite3
import logging
from contextlib import closing
from pathlib import Path
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio
from typing import Any, Dict, List
import os
import ast
import astroid
from radon.complexity import cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze
import networkx as nx
from typing import Optional
from difflib import SequenceMatcher

logger = logging.getLogger('mcp_code_analyzer')
logger.info("Starting Enhanced MCP Code Analyzer")
EXCLUDED_DIRS = {
    'node_modules',
    'dist',
    'build',
    '.git',
    '.aws',
    '.next',
    '__pycache__',
    'venv',
    '.venv',
    'env',
    '.env',
    'coverage',
    '.coverage',
    'tmp',
    '.tmp',
    '.idea',
    '.vscode'
}

EXCLUDED_FILES = {
    '.pyc',
    '.pyo',
    '.pyd',
    '.so',
    '.dll',
    '.dylib',
    '.log',
    '.DS_Store',
    '.env',
    '.coverage',
    '.pytest_cache'
}
PROMPT_TEMPLATE = """
Project Analysis Assistant

Project Path: {path}

<analysis-phases>
1. Project Structure Analysis:
   * Directory Structure
   * File Organization
   * Project Architecture
   * Component Hierarchy

2. Technology Stack Detection:
   * Programming Languages
   * Frameworks & Libraries
   * Build Tools
   * Testing Frameworks
   * Dependencies

3. Code Analysis:
   * Code Quality Metrics
   * Complexity Analysis
   * Dependencies Graph
   * Code Patterns
   * Anti-patterns Detection

4. Documentation Analysis:
   * Code Documentation
   * Project Documentation
   * API Documentation
   * Comments Quality

<available-tools>
1. Project Analysis Tools:
   analyze_file:
   * Usage: Detailed file analysis
   * Returns: Metrics, complexity, quality

   analyze_project:
   * Usage: Full project overview
   * Features: Structure, technologies, patterns

2. Quality Analysis Tools:
   check_quality:
   * Usage: Code quality assessment
   * Features: Patterns, anti-patterns, metrics

   find_duplicates:
   * Usage: Detect code duplication
   * Features: Similar code detection

3. Dependency Tools:
   analyze_dependencies:
   * Usage: Dependency analysis
   * Features: Import graphs, coupling

<analysis-methodology>
1. Initial Scan:
   - Directory structure mapping
   - Technology identification
   - Basic metrics collection

2. Deep Analysis:
   - Code quality assessment
   - Complexity calculation
   - Pattern detection
   - Documentation review

3. Report Generation:
   - Metrics summary
   - Quality indicators
   - Recommendations
   - Improvement suggestions

Please describe what specific aspect of the project you'd like me to analyze. I can provide:
- Project structure analysis
- Code quality assessment
- Dependency analysis
- Technology stack report
- Architectural review
- Documentation analysis

I'll guide you through the analysis process and provide detailed insights about your codebase."""

@staticmethod
def similar(a: str, b: str) -> float:
    """İki string arasındaki benzerlik oranını hesaplar"""
    return SequenceMatcher(None, a, b).ratio()

class CodeAnalyzer:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        self.graph = nx.DiGraph()
        self._init_cache()

    def _init_cache(self):
        self.file_cache = {}  # Dosya içerikleri için
        self.ast_cache = {}   # AST parsları için
        self.metrics_cache = {}  # Metrikler için
        self.pattern_cache = {}  # Pattern analizleri için
        self.structure_cache = {}  # Yapı analizleri için

    def _should_skip_path(self, path: Path) -> bool:
        """Check if path should be skipped"""
        try:
            # Skip excluded directories
            if any(excluded in path.parts for excluded in EXCLUDED_DIRS):
                return True

            # Skip excluded file types
            if path.is_file() and any(path.name.endswith(ext) for ext in EXCLUDED_FILES):
                return True

            return False
        except:
            return True

    async def analyze_project(self, path: str = None) -> Dict[str, Any]:
        """Optimized project analysis"""
        analyze_path = Path(path) if path else self.project_path
        cache_key = f"project_analysis_{str(analyze_path)}"

        # Check cache first
        cached = self.metrics_cache.get(cache_key)
        if cached:
            return cached

        result = {
            "structure": await self._analyze_structure(analyze_path),
            "technologies": await self._detect_technologies(analyze_path),
        }

        # Cache the result
        self.metrics_cache[cache_key] = result
        return result

    async def _analyze_structure(self, path: Path) -> Dict[str, Any]:
        """Optimized structure analysis"""
        structure = {
            "directories": [],
            "files": [],
            "summary": {
                "total_files": 0,
                "total_dirs": 0,
                "file_types": {}
            }
        }

        try:
            # Use os.scandir for better performance
            for entry in os.scandir(path):
                if self._should_skip_path(Path(entry.path)):
                    continue

                if entry.is_dir():
                    structure["directories"].append({
                        "path": str(Path(entry.path).relative_to(path)),
                        "name": entry.name
                    })

                    # Recursively analyze subdirectories (only if not excluded)
                    subdir_structure = await self._analyze_structure(Path(entry.path))
                    structure["summary"]["total_files"] += subdir_structure["summary"]["total_files"]

                    # Merge file type counts
                    for ftype, count in subdir_structure["summary"]["file_types"].items():
                        structure["summary"]["file_types"][ftype] = \
                            structure["summary"]["file_types"].get(ftype, 0) + count

                    structure["files"].extend(subdir_structure["files"])

                elif entry.is_file():
                    file_path = Path(entry.path)
                    file_type = file_path.suffix

                    structure["summary"]["total_files"] += 1
                    structure["summary"]["file_types"][file_type] = \
                        structure["summary"]["file_types"].get(file_type, 0) + 1

                    structure["files"].append({
                        "path": str(file_path.relative_to(path)),
                        "name": entry.name,
                        "type": file_type,
                        "size": entry.stat().st_size
                    })

        except Exception as e:
            logger.error(f"Error analyzing structure: {e}")

        structure["summary"]["total_dirs"] = len(structure["directories"])
        return structure

    async def _detect_technologies(self, path: Path) -> Dict[str, List[str]]:
        """Optimized technology detection"""
        tech_markers = {
            "Python": ["requirements.txt", "setup.py", "pyproject.toml", ".py"],
            "JavaScript": ["package.json", "package-lock.json", ".js"],
            "TypeScript": ["tsconfig.json", ".ts"],
            "React": ["jsx", "tsx", "react"],
            "Vue": ["vue", "nuxt"],
            "Angular": ["angular.json", "ng"],
            "Docker": ["Dockerfile", "docker-compose.yml"],
            "Django": ["manage.py", "wsgi.py", "asgi.py"],
            "Flask": ["flask"],
            "FastAPI": ["fastapi"]
        }

        found_tech = {
            "languages": set(),
            "frameworks": set(),
            "tools": set()
        }

        try:
            for entry in os.scandir(path):
                if self._should_skip_path(Path(entry.path)):
                    continue

                entry_name = entry.name.lower()

                # Quick check for file extensions
                if entry.is_file():
                    ext = Path(entry_name).suffix
                    if ext == '.py':
                        found_tech["languages"].add("Python")
                    elif ext in ['.js', '.jsx']:
                        found_tech["languages"].add("JavaScript")
                    elif ext in ['.ts', '.tsx']:
                        found_tech["languages"].add("TypeScript")

                # Check for technology markers
                for tech, markers in tech_markers.items():
                    if any(marker in entry_name for marker in markers):
                        category = self._categorize_technology(tech)
                        found_tech[category].add(tech)

                # Recursively check directories (if not excluded)
                if entry.is_dir() and not self._should_skip_path(Path(entry.path)):
                    subdir_tech = await self._detect_technologies(Path(entry.path))
                    for category, techs in subdir_tech.items():
                        found_tech[category].update(techs)

        except Exception as e:
            logger.error(f"Error detecting technologies: {e}")

        return {
            category: list(techs)
            for category, techs in found_tech.items()
        }

    def _categorize_technology(self, tech: str) -> str:
        languages = {"Python", "JavaScript", "TypeScript", "Java", "Go"}
        frameworks = {"React", "Vue", "Angular", "Django", "Flask", "FastAPI"}
        return "languages" if tech in languages else "frameworks" if tech in frameworks else "tools"

    async def analyze_file(self, file_path: str) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            return {"error": "File not found"}

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            result = {
                "path": str(path),
                "type": path.suffix,
                "size": path.stat().st_size,
                "metrics": {},
            }

            if path.suffix == '.py':
                # Python specific analysis
                tree = ast.parse(content)
                result["metrics"] = {
                    "complexity": cc_visit(content),
                    "maintainability": mi_visit(content, multi=True),
                    "raw": analyze(content)
                }

            return result
        except Exception as e:
            return {"error": str(e)}

    async def analyze_dependencies(self, path: str) -> Dict[str, Any]:
        target_path = Path(path)
        if not target_path.exists():
            return {"error": "Path not found"}

        try:
            dependencies = {
                "imports": [],
                "dependencies": [],
                "graph": {}
            }

            if target_path.suffix == '.py':
                with open(target_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for name in node.names:
                            dependencies["imports"].append({
                                "name": name.name,
                                "alias": name.asname
                            })
                    elif isinstance(node, ast.ImportFrom):
                        dependencies["imports"].append({
                            "module": node.module,
                            "names": [n.name for n in node.names]
                        })

            return dependencies
        except Exception as e:
            return {"error": str(e)}

    async def find_references(self, target: str, ref_type: str = "all") -> Dict[str, Any]:
        """Find all references of a class, method, or variable"""
        try:
            references = {
                "target": target,
                "type": ref_type,
                "locations": [],
                "usage_count": 0
            }

            for root, _, files in os.walk(self.project_path):
                for file in files:
                    if file.endswith('.py'):
                        file_path = Path(root) / file
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                                tree = ast.parse(content)

                                for node in ast.walk(tree):
                                    if isinstance(node, ast.Name) and node.id == target:
                                        references["locations"].append({
                                            "file": str(file_path.relative_to(self.project_path)),
                                            "line": node.lineno,
                                            "col": node.col_offset,
                                            "context": "definition" if isinstance(node.ctx, ast.Store) else "usage"
                                        })
                                        references["usage_count"] += 1
                                    elif isinstance(node, ast.ClassDef) and node.name == target:
                                        references["locations"].append({
                                            "file": str(file_path.relative_to(self.project_path)),
                                            "line": node.lineno,
                                            "col": node.col_offset,
                                            "context": "class_definition"
                                        })
                                    elif isinstance(node, ast.FunctionDef) and node.name == target:
                                        references["locations"].append({
                                            "file": str(file_path.relative_to(self.project_path)),
                                            "line": node.lineno,
                                            "col": node.col_offset,
                                            "context": "function_definition"
                                        })

                        except Exception as e:
                            logger.error(f"Error analyzing file {file_path}: {e}")
                            continue

            return references
        except Exception as e:
            return {"error": str(e)}

    async def _analyze_change_impact(
            self,
            affected_files: List[str],
            dependencies: List[Dict]
    ) -> Dict[str, Any]:
        """Değişikliklerin etkisini analiz eder"""
        return {
            "direct_impacts": [
                self._analyze_file_impact(file) for file in affected_files
            ],
            "indirect_impacts": [
                self._analyze_dependency_impact(dep) for dep in dependencies
            ],
            "risk_level": self._calculate_risk_level(affected_files, dependencies)
        }

    async def _find_circular_dependencies(self, file_path: str) -> List[List[str]]:
        """Döngüsel bağımlılıkları bulur"""
        cycles = []
        if self.graph.nodes:
            try:
                cycles = list(nx.simple_cycles(self.graph))
            except Exception as e:
                logger.error(f"Error finding cycles: {e}")
        return cycles

    async def _analyze_required_changes(
            self,
            pattern: str,
            dependencies: List[Dict]
    ) -> List[Dict[str, Any]]:
        """Gerekli değişiklikleri analiz eder"""
        changes = []
        for dep in dependencies:
            impact = await self._analyze_file_impact(dep)
            if impact["risk_level"] > "low":
                changes.append({
                    "file": dep,
                    "required_changes": impact["required_changes"],
                    "risk": impact["risk_level"]
                })
        return changes

    async def _analyze_refactoring_risks(
            self,
            pattern: str,
            usages: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Refactoring risklerini analiz eder"""
        risks = []
        for occurrence in usages.get("occurrences", []):
            file_risks = await self._analyze_file_risks(
                occurrence["file"],
                pattern
            )
            if file_risks:
                risks.extend(file_risks)
        return risks

    async def check_code_quality(self, path: str) -> Dict[str, Any]:
        """Analyze code quality metrics and patterns"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            quality = {
                "metrics": {
                    "maintainability_index": 0,
                    "cyclomatic_complexity": 0,
                    "raw_metrics": {}
                },
                "issues": [],
                "suggestions": []
            }

            # Calculate metrics
            tree = ast.parse(content)
            quality["metrics"]["maintainability_index"] = mi_visit(content, multi=True)
            complexity = list(cc_visit(content))
            quality["metrics"]["cyclomatic_complexity"] = sum(item.complexity for item in complexity)
            quality["metrics"]["raw_metrics"] = analyze(content)

            # Check for issues
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if len(node.body) > 50:  # Long function
                        quality["issues"].append({
                            "type": "long_function",
                            "location": node.lineno,
                            "message": f"Function {node.name} is too long ({len(node.body)} lines)"
                        })
                        quality["suggestions"].append(
                            f"Consider breaking down function {node.name} into smaller functions"
                        )

                elif isinstance(node, ast.ClassDef):
                    method_count = len([n for n in node.body if isinstance(n, ast.FunctionDef)])
                    if method_count > 10:  # Complex class
                        quality["issues"].append({
                            "type": "complex_class",
                            "location": node.lineno,
                            "message": f"Class {node.name} has too many methods ({method_count})"
                        })
                        quality["suggestions"].append(
                            f"Consider splitting class {node.name} into smaller classes"
                        )

            return quality
        except Exception as e:
            return {"error": str(e)}

    async def analyze_imports(self, path: str) -> Dict[str, Any]:
        """Detailed analysis of imports in a file or directory"""
        try:
            result = {
                "imports": {
                    "standard_lib": [],
                    "third_party": [],
                    "local": []
                },
                "stats": {
                    "total_imports": 0,
                    "unique_modules": set()
                },
                "issues": []
            }

            if Path(path).is_file():
                files = [Path(path)]
            else:
                files = [f for f in Path(path).rglob("*.py")]

            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    tree = ast.parse(content)

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for name in node.names:
                                import_info = {
                                    "name": name.name,
                                    "alias": name.asname,
                                    "line": node.lineno,
                                    "file": str(file_path)
                                }
                                result["stats"]["total_imports"] += 1
                                result["stats"]["unique_modules"].add(name.name)

                                # Categorize import
                                if name.name in __import__('sys').stdlib_module_names:
                                    result["imports"]["standard_lib"].append(import_info)
                                else:
                                    result["imports"]["third_party"].append(import_info)

                        elif isinstance(node, ast.ImportFrom):
                            for name in node.names:
                                import_info = {
                                    "module": node.module,
                                    "name": name.name,
                                    "alias": name.asname,
                                    "line": node.lineno,
                                    "file": str(file_path)
                                }
                                result["stats"]["total_imports"] += 1
                                if node.module:
                                    result["stats"]["unique_modules"].add(node.module)

                except Exception as e:
                    result["issues"].append({
                        "file": str(file_path),
                        "error": str(e)
                    })

            result["stats"]["unique_modules"] = list(result["stats"]["unique_modules"])
            return result
        except Exception as e:
            return {"error": str(e)}

    async def find_code_patterns(self, path: str) -> Dict[str, Any]:
        """Detect common code patterns and anti-patterns"""
        try:
            patterns = {
                "design_patterns": [],
                "anti_patterns": [],
                "code_smells": []
            }

            if Path(path).is_file():
                files = [Path(path)]
            else:
                files = [f for f in Path(path).rglob("*.py")]

            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    tree = astroid.parse(content)

                    # Design patterns detection
                    for class_node in tree.nodes_of_class(astroid.ClassDef):
                        # Singleton pattern
                        if any(method.name == 'get_instance' for method in class_node.methods()):
                            patterns["design_patterns"].append({
                                "type": "singleton",
                                "location": {
                                    "file": str(file_path),
                                    "class": class_node.name,
                                    "line": class_node.lineno
                                }
                            })

                        # Factory pattern
                        if any(method.name.startswith('create_') for method in class_node.methods()):
                            patterns["design_patterns"].append({
                                "type": "factory",
                                "location": {
                                    "file": str(file_path),
                                    "class": class_node.name,
                                    "line": class_node.lineno
                                }
                            })

                        # Anti-patterns and code smells
                        method_count = len(list(class_node.methods()))
                        if method_count > 10:
                            patterns["anti_patterns"].append({
                                "type": "god_class",
                                "location": {
                                    "file": str(file_path),
                                    "class": class_node.name,
                                    "line": class_node.lineno
                                },
                                "details": f"Class has {method_count} methods"
                            })

                except Exception as e:
                    logger.error(f"Error analyzing {file_path}: {e}")

            return patterns
        except Exception as e:
            return {"error": str(e)}

    async def find_pattern_usages(self, pattern: str, pattern_type: str = "all") -> Dict[str, Any]:
        """
        Belirli bir kod pattern'ini tüm projede arar ve ilişkili kullanımları bulur.
        pattern_type: "code", "variable", "function", "class", "all"
        """
        try:
            results = {
                "pattern": pattern,
                "occurrences": [],
                "related_files": [],
                "dependencies": [],
                "impact": {
                    "direct_impacts": [],
                    "indirect_impacts": [],
                    "risk_level": "low"
                }
            }

            for root, _, files in os.walk(self.project_path):
                for file in files:
                    if file.endswith('.py'):
                        file_path = Path(root) / file
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                                rel_path = str(file_path.relative_to(self.project_path))

                                # Pattern arama
                                if pattern_type in ["all", "code"]:
                                    line_num = 1
                                    for line in content.splitlines():
                                        if pattern in line:
                                            results["occurrences"].append({
                                                "file": rel_path,
                                                "line": line_num,
                                                "content": line.strip(),
                                                "type": "code_match"
                                            })
                                        line_num += 1

                                # AST bazlı analiz
                                tree = ast.parse(content)
                                for node in ast.walk(tree):
                                    match = False

                                    if pattern_type in ["all", "variable"] and isinstance(node, ast.Name):
                                        if node.id == pattern:
                                            match = True
                                            match_type = "variable"
                                    elif pattern_type in ["all", "function"] and isinstance(node, ast.FunctionDef):
                                        if node.name == pattern:
                                            match = True
                                            match_type = "function"
                                    elif pattern_type in ["all", "class"] and isinstance(node, ast.ClassDef):
                                        if node.name == pattern:
                                            match = True
                                            match_type = "class"

                                    if match:
                                        results["occurrences"].append({
                                            "file": rel_path,
                                            "line": node.lineno,
                                            "type": match_type
                                        })
                                        if rel_path not in results["related_files"]:
                                            results["related_files"].append(rel_path)

                        except Exception as e:
                            logger.error(f"Error in file {file_path}: {e}")
                            continue

            # İlişkili dosyaları analiz et
            for file in results["related_files"]:
                deps = await self.analyze_file_dependencies(file)
                results["dependencies"].extend(deps.get("dependencies", []))

            # Impact analizi
            impact = await self._analyze_change_impact(results["related_files"], results["dependencies"])
            results["impact"] = impact

            return results
        except Exception as e:
            return {"error": str(e)}

    async def analyze_file_dependencies(self, file_path: str) -> Dict[str, Any]:
        """Bir dosyanın tüm bağımlılıklarını analiz eder"""
        try:
            results = {
                "file": file_path,
                "imports": [],
                "dependencies": [],
                "dependent_files": [],
                "circular_deps": []
            }

            # Import analizi
            file = Path(self.project_path) / file_path
            if file.exists():
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content)

                    # Direkt importları topla
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for name in node.names:
                                results["imports"].append({
                                    "name": name.name,
                                    "type": "direct",
                                    "line": node.lineno
                                })
                        elif isinstance(node, ast.ImportFrom):
                            results["imports"].append({
                                "name": node.module,
                                "imports": [n.name for n in node.names],
                                "type": "from",
                                "line": node.lineno
                            })

            # Bağımlı dosyaları bul
            for root, _, files in os.walk(self.project_path):
                for f in files:
                    if f.endswith('.py'):
                        dep_file = Path(root) / f
                        try:
                            with open(dep_file, 'r', encoding='utf-8') as df:
                                content = df.read()
                                if file_path in content:
                                    rel_path = str(dep_file.relative_to(self.project_path))
                                    if rel_path != file_path:  # Kendisini hariç tut
                                        results["dependent_files"].append({
                                            "file": rel_path,
                                            "type": "potential_dependency"
                                        })
                        except:
                            continue

            # Döngüsel bağımlılıkları kontrol et
            cycles = await self._find_circular_dependencies(file_path)
            results["circular_deps"] = cycles

            return results
        except Exception as e:
            return {"error": str(e)}

    async def suggest_refactoring(self, pattern: str, scope: str = "all") -> Dict[str, Any]:
        """
        Belirli bir pattern için refactoring önerileri sunar
        """
        try:
            result = {
                "pattern": pattern,
                "suggestions": [],
                "impact": {},
                "required_changes": [],
                "risks": []
            }

            # Pattern kullanımlarını bul
            usages = await self.find_pattern_usages(pattern)

            if not usages.get("occurrences"):
                return {"error": "Pattern not found"}

            # Pattern tipine göre öneriler
            for occurrence in usages["occurrences"]:
                if occurrence["type"] == "variable":
                    result["suggestions"].extend([
                        {
                            "type": "rename_variable",
                            "description": f"Consider renaming variable '{pattern}' to be more descriptive",
                            "location": occurrence
                        },
                        {
                            "type": "encapsulation",
                            "description": "Consider encapsulating the variable with getter/setter methods",
                            "location": occurrence
                        }
                    ])
                elif occurrence["type"] == "function":
                    result["suggestions"].extend([
                        {
                            "type": "extract_method",
                            "description": "Consider breaking down the function into smaller methods",
                            "location": occurrence
                        },
                        {
                            "type": "rename_method",
                            "description": f"Consider renaming method '{pattern}' to better reflect its purpose",
                            "location": occurrence
                        }
                    ])
                elif occurrence["type"] == "class":
                    result["suggestions"].extend([
                        {
                            "type": "split_class",
                            "description": "Consider splitting the class into smaller, more focused classes",
                            "location": occurrence
                        },
                        {
                            "type": "extract_interface",
                            "description": "Consider extracting an interface for better abstraction",
                            "location": occurrence
                        }
                    ])

            # Gerekli değişiklikleri belirle
            changes = await self._analyze_required_changes(pattern, usages["dependencies"])
            result["required_changes"] = changes

            # Risk analizi
            risks = await self._analyze_refactoring_risks(pattern, usages)
            result["risks"] = risks

            return result
        except Exception as e:
            return {"error": str(e)}

    async def preview_changes(self, pattern: str, replacement: str) -> Dict[str, Any]:
        """
        Önerilen değişikliklerin preview'ını gösterir
        """
        try:
            preview = {
                "original_pattern": pattern,
                "replacement": replacement,
                "files_affected": [],
                "preview": [],
                "estimated_impact": {}
            }

            # Pattern kullanımlarını bul
            usages = await self.find_pattern_usages(pattern)

            for occurrence in usages["occurrences"]:
                file_path = Path(self.project_path) / occurrence["file"]
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.readlines()

                    # Değişiklik preview'ı oluştur
                    line_num = occurrence["line"]
                    original_line = content[line_num - 1]
                    new_line = original_line.replace(pattern, replacement)

                    preview["preview"].append({
                        "file": occurrence["file"],
                        "line": line_num,
                        "original": original_line.strip(),
                        "modified": new_line.strip(),
                        "context": {
                            "before": content[max(0, line_num - 3):line_num - 1],
                            "after": content[line_num:min(len(content), line_num + 2)]
                        }
                    })

                    if occurrence["file"] not in preview["files_affected"]:
                        preview["files_affected"].append(occurrence["file"])

                except Exception as e:
                    logger.error(f"Error creating preview for {file_path}: {e}")
                    continue

            # Impact analizi
            preview["estimated_impact"] = await self._analyze_change_impact(
                preview["files_affected"],
                usages.get("dependencies", [])
            )

            return preview
        except Exception as e:
            return {"error": str(e)}

    async def _find_related_code(
            self,
            tree: ast.AST,
            matches: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Patternle ilişkili kodu bulur"""
        related = []
        try:
            for match in matches:
                for node in ast.walk(tree):
                    if hasattr(node, 'lineno') and \
                            abs(node.lineno - match['line']) <= 5:  # 5 satır yakınlık
                        related.append({
                            "type": node.__class__.__name__,
                            "line": node.lineno,
                            "content": ast.unparse(node)
                        })
            return related
        except:
            return []

    async def analyze_pattern_dependencies(
            self,
            file_path: str,
            pattern: str
    ) -> List[Dict[str, Any]]:
        """Pattern'in bağımlılıklarını analiz eder"""
        try:
            deps = []
            content = None
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if content:
                tree = ast.parse(content)
                pattern_nodes = []

                # Pattern'i içeren nodeları bul
                for node in ast.walk(tree):
                    if hasattr(node, 'lineno'):
                        node_content = ast.unparse(node)
                        if pattern in node_content:
                            pattern_nodes.append(node)

                # Bağımlılıkları analiz et
                for node in pattern_nodes:
                    # İmport bağımlılıkları
                    imports = set()
                    for imp in ast.walk(node):
                        if isinstance(imp, (ast.Import, ast.ImportFrom)):
                            module = imp.names[0].name if isinstance(imp, ast.Import) \
                                else imp.module
                            imports.add(module)

                    # Fonksiyon çağrıları
                    calls = set()
                    for call in ast.walk(node):
                        if isinstance(call, ast.Call):
                            if isinstance(call.func, ast.Name):
                                calls.add(call.func.id)

                    deps.append({
                        "node_type": node.__class__.__name__,
                        "line": node.lineno,
                        "imports": list(imports),
                        "calls": list(calls)
                    })

            return deps
        except Exception as e:
            logger.error(f"Error analyzing pattern dependencies: {e}")
            return []


    async def _analyze_pattern_context(
            self,
            content: str,
            matches: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Pattern'in context'ini analiz eder"""
        try:
            context = {
                "scope": {},
                "usage": {},
                "related_patterns": []
            }

            lines = content.splitlines()
            for match in matches:
                line_num = match['line']
                # Kapsam analizi
                scope_start = max(0, line_num - 10)
                scope_end = min(len(lines), line_num + 10)
                scope_lines = lines[scope_start:scope_end]

                # İlgili pattern'leri bul
                related = set()
                for line in scope_lines:
                    for word in line.split():
                        if similar(word, match['pattern']) > 0.7:  # Benzerlik skoru
                            related.add(word)

                context["scope"][line_num] = {
                    "before": lines[scope_start:line_num-1],
                    "after": lines[line_num:scope_end],
                    "related_patterns": list(related)
                }

                # Kullanım analizi
                context["usage"][line_num] = {
                    "type": match.get('type', 'unknown'),
                    "frequency": len([l for l in scope_lines
                                      if match['pattern'] in l])
                }

            return context
        except Exception as e:
            logger.error(f"Error analyzing pattern context: {e}")
            return {}

    async def analyze_code_structure(self,file_path: str,pattern: Optional[str] = None) -> Dict[str, Any]:
        """yKod yapısını analiz eder ve pattern eşleşmesi yapar"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            result = {
                "file": file_path,
                "structure": {},
                "patterns": [],
                "context": {},
                "related_code": []
            }

            # AST analizi
            tree = ast.parse(content)

            # Pattern arama
            if pattern:
                matches = await self._find_pattern_matches(content, pattern)
                if matches:
                    result["patterns"] = matches
                    # İlgili kodu bul
                    result["related_code"] = await self._find_related_code(
                        tree,
                        matches
                    )
                    # Context analizi
                    result["context"] = await self._analyze_pattern_context(
                        content,
                        matches
                    )

            return result
        except Exception as e:
            logger.error(f"Error analyzing code structure: {e}")
            return {"error": str(e)}

    async def _analyze_file_impact(self, file_path: str) -> Dict[str, Any]:
        """Dosya değişikliğinin etkisini analiz eder"""
        try:
            impact = {
                "risk_level": "low",
                "affected_components": [],
                "required_changes": [],
                "dependencies": []
            }

            # Dosya bağımlılıklarını kontrol et
            deps = await self.analyze_file_dependencies(file_path)
            if deps:
                impact["dependencies"] = deps.get("dependencies", [])
                impact["affected_components"] = deps.get("dependent_files", [])

                # Risk seviyesini hesapla
                if len(impact["affected_components"]) > 5:
                    impact["risk_level"] = "high"
                elif len(impact["affected_components"]) > 2:
                    impact["risk_level"] = "medium"

            return impact
        except Exception as e:
            logger.error(f"Error analyzing file impact: {e}")
            return {"error": str(e)}

    async def _analyze_dependency_impact(self, dependency: Dict) -> Dict[str, Any]:
        """Bağımlılık değişikliğinin etkisini analiz eder"""
        try:
            impact = {
                "dependency": dependency,
                "risk_level": "low",
                "affected_files": [],
                "cascading_effects": []
            }

            dep_name = dependency.get("name") or dependency.get("module")
            if not dep_name:
                return impact

            # Bağımlı dosyaları bul
            for root, _, files in os.walk(self.project_path):
                for file in files:
                    if file.endswith('.py'):
                        file_path = Path(root) / file
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                                if dep_name in content:
                                    rel_path = str(file_path.relative_to(self.project_path))
                                    impact["affected_files"].append(rel_path)

                                    # Cascade etkilerini kontrol et
                                    deps = await self.analyze_file_dependencies(rel_path)
                                    if deps and deps.get("dependent_files"):
                                        impact["cascading_effects"].extend(deps["dependent_files"])
                        except:
                            continue

            # Risk seviyesini belirle
            total_affected = len(impact["affected_files"]) + len(impact["cascading_effects"])
            if total_affected > 10:
                impact["risk_level"] = "high"
            elif total_affected > 5:
                impact["risk_level"] = "medium"

            return impact
        except Exception as e:
            logger.error(f"Error analyzing dependency impact: {e}")
            return {"error": str(e)}

    async def _calculate_risk_level(
            self,
            affected_files: List[str],
            dependencies: List[Dict]
    ) -> str:
        """Değişiklik riskini hesaplar"""
        try:
            risk_score = 0

            # Etkilenen dosya sayısına göre
            file_count = len(affected_files)
            if file_count > 10:
                risk_score += 3
            elif file_count > 5:
                risk_score += 2
            elif file_count > 2:
                risk_score += 1

            # Bağımlılık sayısına göre
            dep_count = len(dependencies)
            if dep_count > 5:
                risk_score += 3
            elif dep_count > 3:
                risk_score += 2
            elif dep_count > 1:
                risk_score += 1

            # Risk seviyesini belirle
            if risk_score >= 5:
                return "high"
            elif risk_score >= 3:
                return "medium"
            return "low"
        except Exception as e:
            logger.error(f"Error calculating risk level: {e}")
            return "unknown"

    async def _analyze_file_risks(
            self,
            file_path: str,
            pattern: str
    ) -> List[Dict[str, Any]]:
        """Dosya değişiklik risklerini analiz eder"""
        try:
            risks = []

            # Bağımlılıkları kontrol et
            deps = await self.analyze_file_dependencies(file_path)
            if deps.get("circular_deps"):
                risks.append({
                    "type": "circular_dependency",
                    "severity": "high",
                    "details": "Changes may cause circular dependency issues"
                })

            # Coupling kontrolü
            dependencies = deps.get("dependencies", [])
            if len(dependencies) > 5:
                risks.append({
                    "type": "high_coupling",
                    "severity": "medium",
                    "details": "High number of dependencies increases risk"
                })

            # Pattern kullanım riski
            usages = await self.find_pattern_usages(pattern)
            if len(usages.get("occurrences", [])) > 10:
                risks.append({
                    "type": "high_usage",
                    "severity": "high",
                    "details": "Pattern is used in many places, changes may have wide impact"
                })

            return risks
        except Exception as e:
            logger.error(f"Error analyzing file risks: {e}")
            return []

    async def _find_pattern_matches(
            self,
            content: str,
            pattern: str
    ) -> List[Dict[str, Any]]:
        """Kod içinde pattern eşleşmelerini bulur"""
        try:
            matches = []
            lines = content.splitlines()

            for i, line in enumerate(lines, 1):
                if pattern in line:
                    matches.append({
                        "line": i,
                        "content": line.strip(),
                        "pattern": pattern,
                        "type": "code_match"
                    })

            return matches
        except Exception as e:
            logger.error(f"Error finding pattern matches: {e}")
            return []


async def main(project_path: str):
    logger.info(f"Starting Enhanced Code Analyzer MCP Server with project path: {project_path}")
    analyzer = CodeAnalyzer(project_path)
    server = Server("code-analyzer")

    @server.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        logger.debug("Handling list_resources request")
        return [
            types.Resource(
                uri=types.AnyUrl("memo://insights"),
                name="Project Analysis Insights",
                description="Analysis results and insights about the project",
                mimeType="text/plain"
            )
        ]

    @server.list_prompts()
    async def handle_list_prompts() -> list[types.Prompt]:
        logger.debug("Handling list_prompts request")
        return [
            types.Prompt(
                name="analyze-project",
                description="A prompt to analyze project structure and provide insights",
                arguments=[
                    types.PromptArgument(
                        name="path",
                        description="Project path to analyze",
                        required=True
                    )
                ]
            )
        ]

    @server.get_prompt()
    async def handle_get_prompt(
            name: str,
            arguments: dict[str, str] | None
    ) -> types.GetPromptResult:
        logger.debug(f"Handling get_prompt request for {name} with args {arguments}")

        if name != "analyze-project":
            raise ValueError(f"Unknown prompt: {name}")

        if not arguments or "path" not in arguments:
            raise ValueError("Missing required argument: path")

        path = arguments["path"]
        prompt = PROMPT_TEMPLATE.format(path=path)

        return types.GetPromptResult(
            description=f"Analysis template for {path}",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text=prompt.strip())
                )
            ]
        )

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="analyze_project",
                description="Analyzes complete project structure and metrics",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Project path to analyze"
                        }
                    },
                    "required": ["path"]
                }
            ),
            types.Tool(
                name="analyze_code_structure",
                description="Analyzes code structure with pattern matching and context",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "pattern": {
                            "type": "string",
                            "description": "Optional pattern to search for"
                        }
                    },
                    "required": ["file_path"]
                }
            ),
            types.Tool(
                name="analyze_pattern_dependencies",
                description="Analyzes dependencies related to a specific pattern",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "pattern": {"type": "string"}
                    },
                    "required": ["file_path", "pattern"]
                }
            ),
            types.Tool(
                name="find_pattern_usages",
                description="Find all occurrences and related usages of a code pattern",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "pattern_type": {
                            "type": "string",
                            "enum": ["all", "code", "variable", "function", "class"]
                        }
                    },
                    "required": ["pattern"]
                }
            ),
            types.Tool(
                name="analyze_file_dependencies",
                description="Analyze all dependencies of a file",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"}
                    },
                    "required": ["file_path"]
                }
            ),
            types.Tool(
                name="suggest_refactoring",
                description="Get refactoring suggestions for a code pattern",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "scope": {
                            "type": "string",
                            "enum": ["all", "file", "module"]
                        }
                    },
                    "required": ["pattern"]
                }
            ),
            types.Tool(
                name="preview_changes",
                description="Preview the impact of changing a code pattern",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "replacement": {"type": "string"}
                    },
                    "required": ["pattern", "replacement"]
                }
            ),
            types.Tool(
                name="find_references",
                description="Find all references to a symbol",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "ref_type": {
                            "type": "string",
                            "enum": ["all", "class", "function", "variable"]
                        }
                    },
                    "required": ["target"]
                }
            ),
            types.Tool(
                name="check_code_quality",
                description="Analyze code quality metrics and patterns",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            ),
            types.Tool(
                name="analyze_imports",
                description="Analyze import statements and dependencies",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            ),
            types.Tool(
                name="find_code_patterns",
                description="Detect code patterns and anti-patterns",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            ),
            types.Tool(
                name="analyze_file",
                description="Analyzes a single file for metrics and quality",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file"
                        }
                    },
                    "required": ["file_path"]
                }
            ),
            types.Tool(
                name="analyze_dependencies",
                description="Analyzes project dependencies",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to analyze"
                        }
                    },
                    "required": ["path"]
                }
            )
        ]

    @server.call_tool()
    async def handle_call_tool(
            name: str,
            arguments: Dict[str, Any] | None
    ) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if not arguments:
            raise ValueError("Missing arguments")

        try:
            result = None

            if name == "analyze_project":
                result = await analyzer.analyze_project(arguments.get("path"))
            elif name == "analyze_file":
                result = await analyzer.analyze_file(arguments["file_path"])
            elif name == "analyze_dependencies":
                result = await analyzer.analyze_dependencies(arguments["path"])
            elif name == "find_references":
                result = await analyzer.find_references(
                    arguments["target"],
                    arguments.get("ref_type", "all")
                )
            elif name == "analyze_code_structure":
                result = await analyzer.analyze_code_structure(
                    arguments["file_path"],
                    arguments.get("pattern")
                )
            elif name == "analyze_pattern_dependencies":
                result = await analyzer.analyze_pattern_dependencies(
                    arguments["file_path"],
                    arguments["pattern"]
                )
            elif name == "find_pattern_usages":
                result = await analyzer.find_pattern_usages(
                    arguments["pattern"],
                    arguments.get("pattern_type", "all")
                )
            elif name == "analyze_file_dependencies":
                result = await analyzer.analyze_file_dependencies(arguments["file_path"])
            elif name == "suggest_refactoring":
                result = await analyzer.suggest_refactoring(
                    arguments["pattern"],
                    arguments.get("scope", "all")
                )
            elif name == "preview_changes":
                result = await analyzer.preview_changes(
                    arguments["pattern"],
                    arguments["replacement"]
                )
            elif name == "check_code_quality":
                result = await analyzer.check_code_quality(arguments["path"])
            elif name == "analyze_imports":
                result = await analyzer.analyze_imports(arguments["path"])
            elif name == "find_code_patterns":
                result = await analyzer.find_code_patterns(arguments["path"])
            else:
                raise ValueError(f"Unknown tool: {name}")

            return [types.TextContent(type="text", text=str(result))]
        except Exception as e:
            logger.error(f"Error in tool {name}: {str(e)}")
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        logger.info("Enhanced Code Analyzer running with stdio transport")
        try:
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="code-analyzer",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise

if __name__ == "__main__":
    import sys
    project_path = sys.argv[1] if len(sys.argv) > 1 else "."

    try:
        import asyncio
        asyncio.run(main(project_path))
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Fatal server error: {e}")