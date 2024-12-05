import logging
from enum import Enum
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import sys
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
from ..tools.manager import ToolManager

logger = logging.getLogger(__name__)
__all__ = ["MCPServer", "main"]
class MCPServer:
    """MCP Server implementation for code analysis"""

    def __init__(self, analyze_paths: List[str]):
        self.analyze_paths = []
        self.base_path = Path.cwd()
        self._setup_paths(analyze_paths)
        self.tool_manager = ToolManager()
        self.server = Server("code-analyzer")
        self._setup_handlers()

    def _setup_paths(self, analyze_paths: List[str]):
        """Setup and validate analysis paths"""
        for path in analyze_paths:
            try:
                path_obj = Path(path)
                normalized_path = path_obj.resolve() if path_obj.is_absolute() \
                    else (self.base_path / path_obj).resolve()

                if normalized_path.exists():
                    self.analyze_paths.append(normalized_path)
                    logger.info(f"Added valid path: {normalized_path}")
                else:
                    logger.warning(f"Path does not exist: {path}")
            except Exception as e:
                logger.error(f"Error processing path {path}: {e}")

        if not self.analyze_paths:
            self.analyze_paths = [self.base_path]
            logger.warning(f"No valid paths provided, using current directory: {self.base_path}")


    async def _handle_tool_execution(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute tool with enhanced error handling and logging"""
        operation = arguments.get('operation', 'unknown')
        path = arguments.get('path') or arguments.get('file_path')

        logger.info(f"Starting tool execution - Name: {name}, Operation: {operation}, Path: {path}")

        try:
            # Input validation
            if not path and name in ['create_file', 'stream_edit', 'modify_code']:
                logger.error(f"No path provided for {name}")
                return {"error": "Path is required for this operation"}

            # Special handling for code modification
            if name == "code_modifier":
                result = await self.tool_manager.execute_tool(name, arguments)
                return await self._format_modification_result(result)

            # Get tool instance
            tool = self.tool_manager.get_tool(name)
            if not tool:
                logger.error(f"Tool not found: {name}")
                return {"error": f"Tool {name} not found"}

            # Execute tool operation
            logger.info(f"Executing {name} with arguments: {arguments}")
            result = await self.tool_manager.execute_tool(name, arguments)

            # Log result summary
            if isinstance(result, dict):
                success = result.get('success', False)
                error = result.get('error')
                if error:
                    logger.error(f"Tool execution failed - {name}: {error}")
                elif success:
                    logger.info(f"Tool execution successful - {name}")

            return await self._handle_tool_result(result)

        except Exception as e:
            logger.exception(f"Error executing tool {name}: {e}")
            return {"error": str(e), "details": f"Failed to execute {name}"}

    def _ensure_utf8(self, obj: Any) -> Any:
        """Ensure all strings in object are UTF-8 encoded"""
        if isinstance(obj, str):
            return obj.encode('utf-8', errors='replace').decode('utf-8')
        elif isinstance(obj, dict):
            return {k: self._ensure_utf8(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._ensure_utf8(item) for item in obj]
        return obj

    async def _handle_tool_result(self, result: Any) -> List[types.TextContent]:
        """Handle tool execution result with proper encoding"""
        try:
            # Ensure proper encoding of result
            encoded_result = self._ensure_utf8(result)
            # Convert to string safely
            try:
                if isinstance(encoded_result, (dict, list)):
                    result_str = json.dumps(encoded_result, ensure_ascii=False)
                else:
                    result_str = str(encoded_result)
                return [types.TextContent(type="text", text=result_str)]
            except Exception as json_error:
                logger.error(f"JSON encoding error: {json_error}")
                return [types.TextContent(type="text", text=str(encoded_result))]
        except Exception as e:
            logger.error(f"Error handling tool result: {e}", exc_info=True)
            return [types.TextContent(type="text", text=f"Error processing result: {str(e)}")]

    async def _format_modification_result(self, result: Dict) -> List[types.TextContent]:
        """Format code modification result"""
        if "error" in result:
            return [types.TextContent(type="text", text=json.dumps({
                "success": False,
                "error": result["error"]
            }))]

        # Format successful result
        formatted_result = {
            "success": True,
            "modification": {
                "backup_path": result.get("backup_path"),
                "affected_files": len(result.get("affected_code", [])),
                "dependencies": len(result.get("dependencies", []))
            }
        }

        if result.get("affected_code"):
            formatted_result["details"] = {
                "affected_code": [
                    {
                        "file": code["file_path"],
                        "reason": code["reason"],
                        "action": code["suggested_action"]
                    }
                    for code in result["affected_code"]
                ]
            }

        return [types.TextContent(type="text", text=json.dumps(formatted_result))]


    async def _handle_tool_result(self, result: Any) -> List[types.TextContent]:
        """Handle tool execution result with proper encoding"""
        try:
            safe_result = self._convert_to_safe_format(result)
            encoded_result = self._ensure_utf8(safe_result)

            try:
                if isinstance(encoded_result, (dict, list)):
                    result_str = json.dumps(encoded_result, ensure_ascii=False)
                else:
                    result_str = str(encoded_result)
                return [types.TextContent(type="text", text=result_str)]
            except Exception as json_error:
                logger.error(f"JSON encoding error: {json_error}")
                return [types.TextContent(type="text", text=str(encoded_result))]

        except Exception as e:
            logger.error(f"Error handling tool result: {e}", exc_info=True)
            return [types.TextContent(type="text", text=f"Error processing result: {str(e)}")]


    def _convert_to_safe_format(self, obj: Any) -> Any:
        """Convert complex objects to JSON-serializable format"""
        if isinstance(obj, dict):
            return {k: self._convert_to_safe_format(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_safe_format(item) for item in obj]
        elif isinstance(obj, Enum):
            return obj.name
        elif hasattr(obj, '__dict__'):
            return self._convert_to_safe_format(obj.__dict__)
        return obj

    def _setup_handlers(self):
        """Setup all server handlers"""

        @self.server.list_resources()
        async def handle_list_resources() -> List[types.Resource]:
            resources = []
            for path in self.analyze_paths:
                resources.append(
                    types.Resource(
                        uri=types.AnyUrl(f"memo://insights/{Path(path).name}"),
                        name=f"Analysis for {Path(path).name}",
                        description=f"Analysis results for {path}",
                        mimeType="text/plain"
                    )
                )
            return resources

        @self.server.list_prompts()
        async def handle_list_prompts() -> List[types.Prompt]:
            prompts = []
            for path in self.analyze_paths:
                prompts.append(
                    types.Prompt(
                        name=f"analyze-{Path(path).name}",
                        description=f"Analyze code in {path}",
                        arguments=[
                            types.PromptArgument(
                                name="tool",
                                description="Analysis tool to use",
                                required=True
                            )
                        ]
                    )
                )
            return prompts

        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """List available analysis tools"""
            return [
                types.Tool(
                    name="analyze_project_structure",
                    description="Directory structure and organization analysis with tree view",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"}
                        },
                        "required": ["path"]
                    }
                ),
                types.Tool(
                    name="analyze_project_statistics",
                    description="Project-wide statistics and metrics",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"}
                        },
                        "required": ["path"]
                    }
                ),

                types.Tool(
                    name="analyze_project_technology",
                    description="Detect and analyze used technologies and frameworks",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"}
                        },
                        "required": ["path"]
                    }
                ),
                # File Operations
                types.Tool(
                    name="file_operations",
                    description="File operations with MCP support",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string", "enum": ["analyze", "create", "modify", "stream"]},
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                            "section": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "number"},
                                    "end": {"type": "number"}
                                }
                            },
                            "stream_operation": {"type": "string", "enum": ["start", "write", "finish"]}
                        },
                        "required": ["operation", "path"]
                    }
                ),
                types.Tool(
                    name="code_modifier",
                    description="Safe code modification with impact analysis",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "operation": {
                                "type": "string",
                                "enum": ["modify", "insert", "delete"]
                            },
                            "section": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "number"},
                                    "end": {"type": "number"}
                                }
                            },
                            "content": {"type": "string"},
                            "description": {"type": "string"}
                        },
                        "required": ["file_path", "operation"]
                    }
                ),
                types.Tool(
                    name="manage_changes",
                    description="Manage code changes and their application",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "operation": {
                                "type": "string",
                                "enum": ["apply", "revert", "status", "history"]
                            },
                            "change_ids": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "limit": {"type": "number"}
                        },
                        "required": ["file_path", "operation"]
                    }
                ),
                types.Tool(
                    name="search_code",
                    description="Search code with pattern matching",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string"},
                            "search_type": {
                                "type": "string",
                                "enum": ["text", "regex", "ast"]
                            },
                            "scope": {"type": "string"}
                        },
                        "required": ["pattern"]
                    }
                ),
                # Code Analysis Tools
                types.Tool(
                    name="analyze_code_structure",
                    description="Analyze code structure and architecture",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"}
                        },
                        "required": ["path"]
                    }
                ),
                types.Tool(
                    name="validate_code",
                    description="Validate code quality and standards",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "validation_type": {
                                "type": "string",
                                "enum": ["syntax", "style", "security", "all"]
                            }
                        },
                        "required": ["path"]
                    }
                ),
                types.Tool(
                    name="check_syntax",
                    description="Advanced syntax checking and analysis",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "check_type": {
                                "type": "string",
                                "enum": ["all", "tokens", "ast", "imports", "naming"]
                            }
                        },
                        "required": ["path"]
                    }
                ),
                # Search Tools
                types.Tool(
                    name="search_files",
                    description="Advanced file search capabilities",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "operation": {
                                "type": "string",
                                "enum": ["find", "glob", "pattern", "recent"]
                            },
                            "pattern": {"type": "string"},
                            "recursive": {"type": "boolean"}
                        },
                        "required": ["path", "operation"]
                    }
                ),
                types.Tool(
                    name="search_content",
                    description="Search within file contents",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "operation": {
                                "type": "string",
                                "enum": ["search", "analyze", "regex", "similar"]
                            },
                            "text": {"type": "string"},
                            "pattern": {"type": "string"}
                        },
                        "required": ["path", "operation"]
                    }
                ),

                # Version Control
                types.Tool(
                    name="version_control",
                    description="Advanced version control and history management",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "operation": {
                                "type": "string",
                                "enum": [
                                    "create_version",
                                    "restore_version",
                                    "get_history",
                                    "compare_versions",
                                    "get_changes",
                                    "cleanup"
                                ]
                            },
                            "version_id": {"type": "string"},
                            "description": {"type": "string"}
                        },
                        "required": ["path", "operation"]
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
                    name="find_pattern_usages",
                    description="Find pattern occurrences and analyze usage",
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
                    name="find_references",
                    description="Find code references",
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
                    name="preview_changes",
                    description="Preview code changes",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string"},
                            "replacement": {"type": "string"}
                        },
                        "required": ["pattern", "replacement"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any] | None) -> List[types.TextContent]:
            """Handle tool execution with improved error handling"""
            if not arguments:
                return [types.TextContent(type="text", text="Missing arguments")]

            try:
                # Special handling for file operations
                if name == "file_operations":
                    tool = self.tool_manager.get_tool(name)
                    if not tool:
                        return [types.TextContent(type="text", text=f"Tool {name} not found")]

                    result = await tool.execute(arguments)
                    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

                # Handle paths for other tools
                if "file_path" in arguments:
                    arguments["file_path"] = self._resolve_path(arguments["file_path"])
                if "path" in arguments:
                    arguments["path"] = self._resolve_path(arguments["path"])

                logger.info(f"Executing tool {name} with arguments: {arguments}")
                result = await self.tool_manager.execute_tool(name, arguments)

                if isinstance(result, dict) and "error" in result:
                    return [types.TextContent(type="text", text=str(result["error"]))]

                return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}", exc_info=True)
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    def _resolve_path(self, path_str: str) -> str:
        """Resolve path string to absolute path"""
        if not path_str or path_str == ".":
            return str(self.analyze_paths[0])
        try:
            path_obj = Path(path_str)
            if not path_obj.is_absolute():
                path = str((self.analyze_paths[0] / path_obj))
                logger.info(f"Resolved path: {path}")
                return path
            return str(path_obj)
        except Exception as e:
            logger.error(f"Error resolving path: {e}")
            return path_str

    async def run(self):
        """Run the MCP server"""
        logger.info(f"Starting server with paths: {self.analyze_paths}")
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            try:
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="code-analyzer",
                        server_version="0.1.0",
                        capabilities=self.server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={},
                        ),
                    ),
                )
            except Exception as e:
                logger.error(f"Server error: {e}", exc_info=True)
                raise

async def main(analyze_paths: List[str]):
    """Main entry point for the MCP server"""
    logger.info(f"Starting Code Analyzer with paths: {analyze_paths}")
    server = MCPServer(analyze_paths)
    await server.run()
