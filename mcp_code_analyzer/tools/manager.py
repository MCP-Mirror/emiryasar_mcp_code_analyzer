from pathlib import Path
from typing import Dict, Type, Optional, List
from .base import BaseTool, logger
from .file_tools import MCPFileOperations, FileAnalyzer
from .project_tools import ProjectStructure, ProjectStatistics, ProjectTechnology
from .pattern_tools import CodePatternAnalyzer, PatternUsageAnalyzer
from .analysis_tools import (
    CodeStructureAnalyzer,
    ImportAnalyzer,
    CodeValidator,
    SyntaxChecker
)
from .reference_tools import FindReferences, PreviewChanges
from .dependency_tools import FileDependencyAnalyzer
from .version_manager import VersionManager
from .search_tools import PathFinder, ContentScanner
from .modification_tools import CodeModifier
from ..config import analysis_config

class ToolManager:
    """Manages all available tools"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._code_modifier = CodeModifier()
        self._initialize_tools()

    def _initialize_tools(self):

        # Project Analysis Tools
        self._register_tool("analyze_project_structure", ProjectStructure)
        self._register_tool("analyze_project_statistics", ProjectStatistics)
        self._register_tool("analyze_project_technology", ProjectTechnology)

        # File Operations Group
        self._register_tool("file_operations", MCPFileOperations)
        self._register_tool("analyze_file", FileAnalyzer)

        # Code Modification Group
        self._register_tool("code_modifier", lambda: self._code_modifier)

        # Search and Analysis Group
        self._register_tool("path_finder", PathFinder)
        self._register_tool("search_content", ContentScanner)
        self._register_tool("dependency_analyzer", FileDependencyAnalyzer)

        # Code Analysis Tools
        self._register_tool("analyze_code_structure", CodeStructureAnalyzer)
        self._register_tool("analyze_imports", ImportAnalyzer)
        self._register_tool("validate_code", CodeValidator)
        self._register_tool("check_syntax", SyntaxChecker)

        # Pattern Analysis Tools
        self._register_tool("find_patterns", CodePatternAnalyzer)
        self._register_tool("analyze_pattern_usage", PatternUsageAnalyzer)

        # Reference Tools
        self._register_tool("find_references", FindReferences)
        self._register_tool("preview_changes", PreviewChanges)

        # Version Control
        self._register_tool("version_control", VersionManager)

    def _register_tool(self, name: str, tool_factory: Type[BaseTool] | callable):
        """Register a tool with factory pattern"""
        self._tools[name] = tool_factory() if callable(tool_factory) else tool_factory()

    async def execute_tool(self, name: str, arguments: Dict) -> Dict:
        """Execute a tool by name with enhanced error handling"""
        if name not in self._tools:
            return {"error": f"Tool {name} not found"}

        try:
            # Special handling for code modification operations
            if name == "code_modifier":
                return await self._handle_code_modification(arguments)

            return await self._tools[name].execute(arguments)
        except Exception as e:
            return {"error": str(e)}

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool instance by name"""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """List all available tools"""
        return list(self._tools.keys())

    async def execute_workflow(self, workflow_type: str, arguments: Dict) -> Dict:
        """Execute a coordinated workflow"""
        try:
            if workflow_type == "modify_code":
                return await self._handle_code_modification(arguments)
            elif workflow_type == "modify_file":
                return await self._handle_file_modification(arguments)
            elif workflow_type == "search_and_modify":
                return await self._handle_search_modify(arguments)
            else:
                return {"error": f"Unknown workflow type: {workflow_type}"}
        except Exception as e:
            return {"error": str(e), "workflow_type": workflow_type}

    async def _handle_code_modification(self, arguments: Dict) -> Dict:
        """Central code modification handler"""
        try:
            operation = arguments.get('operation', 'modify')
            file_path = arguments.get('file_path')

            # Analyze dependencies if needed
            if operation in ['modify', 'delete']:
                deps = await self._analyze_dependencies(file_path, arguments)
                if deps.get('error'):
                    return deps

            # Execute modification
            result = await self._code_modifier.modify_code(
                file_path=file_path,
                section=arguments.get('section', {}),
                new_content=arguments.get('content', ''),
                description=arguments.get('description')
            )

            if not result.success:
                return {"error": result.error}

            # Convert enum to string and prepare safe result
            return {
                "success": True,
                "modification": {
                    "change_type": result.change.change_type.name if result.change else None,
                    "backup_path": result.backup_path,
                    "affected_files": [
                        {
                            "file_path": code.file_path,
                            "reason": code.reason,
                            "suggested_action": code.suggested_action,
                            "severity": code.severity
                        }
                        for code in (result.affected_code or [])
                    ] if result.affected_code else [],
                    "dependencies": deps.get('dependencies', [])
                }
            }

        except Exception as e:
            logger.error(f"Code modification failed: {e}")
            return {"error": str(e)}

    async def _handle_file_modification(self, arguments: Dict) -> Dict:
        """Handle general file modification workflow"""
        try:
            file_ops = self.get_tool("file_operations")

            # Check if it's a code file
            if self._is_code_file(arguments.get('file_path', '')):
                return await self._handle_code_modification(arguments)

            # Regular file modification
            return await file_ops.execute({
                "operation": "modify",
                **arguments
            })

        except Exception as e:
            return {"error": str(e), "stage": "file_modification"}



    async def _analyze_dependencies(self, file_path: str, arguments: Dict) -> Dict:
        """Analyze dependencies before modification"""
        try:
            analyzer = self._tools.get('dependency_analyzer')
            if not analyzer:
                return {"error": "Dependency analyzer not available"}

            return await analyzer.execute({
                "file_path": file_path,
                "section": arguments.get('section', {}),
                "operation": arguments.get('operation')
            })

        except Exception as e:
            return {"error": f"Dependency analysis failed: {e}"}

    async def _handle_search_modify(self, arguments: Dict) -> Dict:
        """Handle search and modify workflow"""
        try:
            # 1. Search Phase
            content_scanner = self.get_tool("content_scanner")
            search_results = await content_scanner.execute({
                "operation": "search",
                "pattern": arguments.get("search_pattern"),
                "scope": arguments.get("scope", "current_file")
            })

            if not search_results.get("success"):
                return {"error": "Search failed", "details": search_results.get("error")}

            # 2. Analysis Phase
            affected_locations = []
            for result in search_results.get("results", []):
                analyzer = self.get_tool("file_analyzer")
                analysis = await analyzer.execute({
                    "file_path": result["file"],
                    "line_range": result["line_range"]
                })

                if analysis.get("success"):
                    affected_locations.append({
                        "file": result["file"],
                        "location": result["location"],
                        "analysis": analysis["data"]
                    })

            # 3. Modification Phase
            modifications = []
            for location in affected_locations:
                if self._is_code_file(location["file"]):
                    mod_result = await self._handle_code_modification({
                        "file_path": location["file"],
                        "line_range": location["location"],
                        "new_content": arguments.get("replacement"),
                        "mode": arguments.get("mode", "safe")
                    })
                else:
                    mod_result = await self._handle_file_modification({
                        "file_path": location["file"],
                        "line_range": location["location"],
                        "new_content": arguments.get("replacement")
                    })

                modifications.append({
                    "location": location,
                    "result": mod_result
                })

            return {
                "success": True,
                "search_results": search_results.get("results", []),
                "affected_locations": affected_locations,
                "modifications": modifications
            }

        except Exception as e:
            return {"error": str(e), "stage": "search_modify"}

    def _is_code_file(self, file_path: str) -> bool:
        """Determine if a file is a code file"""
        return Path(file_path).suffix.lower() in analysis_config.analyzable_extensions

