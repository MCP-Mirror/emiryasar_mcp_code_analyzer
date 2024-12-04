from typing import Dict, Type, Optional, List
from .base import BaseTool
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

class ToolManager:
    """Manages all available tools"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._initialize_tools()

    def _initialize_tools(self):
        # Project Analysis Tools
        self._register_tool("analyze_project_structure", ProjectStructure)
        self._register_tool("analyze_project_statistics", ProjectStatistics)
        self._register_tool("analyze_project_technology", ProjectTechnology)

        # File Operations
        self._register_tool("file_operations", MCPFileOperations)
        self._register_tool("analyze_file", FileAnalyzer)

        # Code Analysis Tools
        self._register_tool("analyze_code_structure", CodeStructureAnalyzer)
        self._register_tool("analyze_imports", ImportAnalyzer)
        self._register_tool("validate_code", CodeValidator)
        self._register_tool("check_syntax", SyntaxChecker)

        self._register_tool("search_files", PathFinder)
        self._register_tool("search_content", ContentScanner)

        # Pattern Analysis Tools
        self._register_tool("find_patterns", CodePatternAnalyzer)
        self._register_tool("analyze_pattern_usage", PatternUsageAnalyzer)

        # Reference Tools
        self._register_tool("find_references", FindReferences)
        self._register_tool("preview_changes", PreviewChanges)

        # Dependency Analysis
        self._register_tool("analyze_dependencies", FileDependencyAnalyzer)

        # Version Control
        self._register_tool("version_control", VersionManager)

    def _register_tool(self, name: str, tool_class: Type[BaseTool]):
        """Register a new tool"""
        self._tools[name] = tool_class()

    async def execute_tool(self, name: str, arguments: Dict) -> Dict:
        """Execute a tool by name"""
        if name not in self._tools:
            return {"error": f"Tool {name} not found"}

        try:
            return await self._tools[name].execute(arguments)
        except Exception as e:
            return {"error": str(e)}

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool instance by name"""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """List all available tools"""
        return list(self._tools.keys())