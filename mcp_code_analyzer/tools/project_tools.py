import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from .base import BaseTool
from ..config import analysis_config, system_config

logger = logging.getLogger(__name__)

class ProjectStructure(BaseTool):
    """Analyzes and creates project structure tree"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        path = self._normalize_path(arguments.get('path', '.'))
        if not self._validate_path(path):
            return {"error": "Path not found"}

        cache_key = f"project_structure_{path}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = await self._analyze_structure(path)
            self._cache_result(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Error analyzing project structure: {e}")
            return {"error": str(e)}

    async def _analyze_structure(self, path: Path) -> Dict[str, Any]:
        try:
            if isinstance(path, str):
                path = Path(path)
            path = path.resolve()

            if not path.exists():
                return {"error": f"Path does not exist: {path}"}

            def build_tree(current_path: Path, indent: int = 0) -> List[str]:
                if not current_path.exists() or indent > system_config.MAX_DEPTH:
                    return []

                result = []
                items = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                indent_str = '  ' * indent

                for item in items:
                    if self._should_skip(item):
                        continue

                    if item.is_dir():
                        result.append(f"{indent_str}<dir name='{item.name}' path='{item}'>")
                        result.extend(build_tree(item, indent + 1))
                        result.append(f"{indent_str}</dir>")
                    else:
                        if item.stat().st_size <= system_config.MAX_FILE_SIZE:
                            ext = item.suffix or 'no_ext'
                            result.append(
                                f"{indent_str}<file name='{item.name}' path='{item}' ext='{ext}' analyzable='{ext in analysis_config.analyzable_extensions}'/>"
                            )

                return result

            xml_lines = [
                f"<project name='{path.name}' path='{path}'>",
                *build_tree(path, indent=1),
                '</project>'
            ]

            return {
                "structure": {
                    "xml": '\n'.join(xml_lines),
                    "project_path": str(path)
                }
            }

        except Exception as e:
            logger.error(f"Error analyzing structure at {path}: {e}")
            return {"error": str(e)}

class ProjectStatistics(BaseTool):
    """Collects detailed project statistics"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        path = self._normalize_path(arguments.get('path', '.'))
        if not self._validate_path(path):
            return {"error": "Path not found"}

        cache_key = f"project_stats_{path}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = await self._collect_statistics(path)
            self._cache_result(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Error collecting project statistics: {e}")
            return {"error": str(e)}

    async def _collect_statistics(self, path: Path) -> Dict[str, Any]:
        try:
            stats = {
                "files": {
                    "total": 0,
                    "by_extension": {},
                    "analyzable": 0
                },
                "directories": {
                    "total": 0,
                    "max_depth": 0,
                    "by_depth": {}
                },
                "size": {
                    "total": 0,
                    "by_extension": {},
                    "average_file_size": 0
                }
            }

            for item in path.rglob("*"):
                if not self._should_skip(item):
                    depth = len(item.relative_to(path).parts)

                    if item.is_dir():
                        stats["directories"]["total"] += 1
                        stats["directories"]["max_depth"] = max(stats["directories"]["max_depth"], depth)
                        stats["directories"]["by_depth"][depth] = stats["directories"]["by_depth"].get(depth, 0) + 1

                    elif item.is_file() and item.stat().st_size <= system_config.MAX_FILE_SIZE:
                        size = item.stat().st_size
                        ext = item.suffix or 'no_ext'

                        stats["files"]["total"] += 1
                        stats["size"]["total"] += size

                        if ext not in stats["files"]["by_extension"]:
                            stats["files"]["by_extension"][ext] = 0
                            stats["size"]["by_extension"][ext] = 0

                        stats["files"]["by_extension"][ext] += 1
                        stats["size"]["by_extension"][ext] += size

                        if ext in analysis_config.analyzable_extensions:
                            stats["files"]["analyzable"] += 1

            if stats["files"]["total"] > 0:
                stats["size"]["average_file_size"] = stats["size"]["total"] / stats["files"]["total"]

            return stats

        except Exception as e:
            logger.error(f"Error collecting statistics: {e}")
            return {}

class ProjectTechnology(BaseTool):
    """Analyzes technologies used in the project"""

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        path = self._normalize_path(arguments.get('path', '.'))
        if not self._validate_path(path):
            return {"error": "Path not found"}

        cache_key = f"project_tech_{path}"
        if cached := self._get_cached_result(cache_key):
            return cached

        try:
            result = await self._detect_technologies(path)
            self._cache_result(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Error detecting technologies: {e}")
            return {"error": str(e)}

    async def _detect_technologies(self, path: Path) -> Dict[str, Any]:
        try:
            tech_info = {
                "detected_techs": {},
                "frameworks": set(),
                "languages": set()
            }

            # Scan for technology markers
            for item in path.rglob("*"):
                if not self._should_skip(item):
                    # Check against technology markers
                    for tech, markers in analysis_config.tech_markers.items():
                        for marker in markers:
                            if marker.lower() in str(item).lower():
                                if tech not in tech_info["detected_techs"]:
                                    tech_info["detected_techs"][tech] = {
                                        "markers_found": [],
                                        "files_count": 0
                                    }
                                tech_info["detected_techs"][tech]["markers_found"].append(str(item.name))
                                tech_info["detected_techs"][tech]["files_count"] += 1

                    # Special handling for framework detection
                    if item.is_file():
                        if item.suffix in ['.jsx', '.tsx']:
                            tech_info["frameworks"].add("React")
                        elif item.name == 'package.json':
                            try:
                                with open(item) as f:
                                    data = json.load(f)
                                    deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}

                                    framework_indicators = {
                                        'vue': 'Vue.js',
                                        'angular': 'Angular',
                                        'next': 'Next.js',
                                        'nest': 'NestJS'
                                    }

                                    for indicator, framework in framework_indicators.items():
                                        if indicator in deps:
                                            tech_info["frameworks"].add(framework)
                            except:
                                continue

            # Convert sets to sorted lists for JSON serialization
            tech_info["frameworks"] = sorted(list(tech_info["frameworks"]))
            tech_info["languages"] = sorted(list(tech_info["languages"]))

            return tech_info

        except Exception as e:
            logger.error(f"Error detecting technologies: {e}")
            return {}