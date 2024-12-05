"""MCP Code Analyzer
A code analysis tool using Model Context Protocol
"""

from .server.handlers import main
from .tools.project_tools import ProjectStructure, ProjectStatistics, ProjectTechnology
from .tools.pattern_tools import (
    PatternUsageAnalyzer,
    CodePatternAnalyzer
)
from .tools.analysis_tools import (
    CodeStructureAnalyzer,
    ImportAnalyzer,
    ProjectAnalyzer,
    CodeValidator,
    SyntaxChecker
)
from .tools.reference_tools import FindReferences, PreviewChanges
from .tools.dependency_tools import FileDependencyAnalyzer
from .tools.file_tools import (
    MCPFileOperations,
    FileAnalyzer
)
from .tools.modification_tools import CodeModifier
from .tools.search_tools import PathFinder, ContentScanner
from .tools.version_manager import VersionManager

__version__ = "0.1.0"

__all__ = [
    # Main entrypoint
    "main",

    # Project Analysis
    "ProjectStructure",
    "ProjectStatistics",
    "ProjectTechnology",
    "ProjectAnalyzer",

    # Code Analysis
    "CodeStructureAnalyzer",
    "ImportAnalyzer",
    "CodeValidator",
    "SyntaxChecker",

    # Pattern Analysis
    "PatternUsageAnalyzer",
    "CodePatternAnalyzer",

    # File Operations
    "FileAnalyzer",
    "MCPFileOperations",

    # Code Modifications
    "CodeModifier",

    # Search and Reference
    "PathFinder",
    "ContentScanner",
    "FindReferences",
    "PreviewChanges",

    # Dependencies
    "FileDependencyAnalyzer",

    # Version Control
    "VersionManager"
]