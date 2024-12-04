# MCP Code Analyzer

⚠️ **WARNING: BACKUP RECOMMENDED**  
This tool performs file operations that could potentially modify or delete files. Always backup your codebase before using any modification features.

## Overview
The Model Context Protocol (MCP) Code Analyzer is a comprehensive code analysis and management tool that integrates with Claude Desktop. It analyzes code at both project and file levels, providing insights for needed changes and project understanding.

## Prerequisites
- Python 3.10 or later
- Windows (Linux/MacOS support not yet tested)

## Installation
```bash
# Clone the repository
git clone https://github.com/[your-username]/mcp-code-analyzer.git
cd mcp-code-analyzer

# Install dependencies and package
pip install -e .
```

## Claude Desktop Integration

### Configuration
1. Access Claude Desktop config:
   ```
   Win + R → %AppData%\Claude\
   ```
2. Create/edit `claude_desktop_config.json`:
   ```json
   {
     "globalShortcut": "Ctrl+Space",
     "mcpServers": {
       "code-analyzer": {
         "command": "python",
         "args": [
           "-m",
           "mcp_code_analyzer",
           "--analyze-paths",
           "C:\\Projects\\path1",
           "C:\\Projects\\path2"
         ],
         "type": "module"
       }
     }
   }
   ```

### Path Configuration
- Multiple project paths can be specified in configuration
- Additional paths or files can be analyzed via chat messages
- No limit on number of analyzable paths/files

## 🛠️ Tools and Status

### Working Tools
- ✅ **Project Analysis**
    - analyze_project_structure (XML tree format)
    - analyze_project_statistics
    - analyze_project_technology
    - analyze_code_structure

- ✅ **Code Analysis**
    - analyze_imports
    - analyze_file
    - find_references

- ⚠️ **File Operations** (Always backup before use)
    - file_operations
    - version_control (Creates dated backups)

### Testing Phase
- 🔄 check_syntax
- 🔄 find_code_patterns
- 🔄 find_pattern_usages
- 🔄 search_content
- 🔄 search_files
- 🔄 validate_code

### Known Issues
1. Chat context limitations may interrupt large file modifications
2. AI-generated documentation comments can affect code operation in large files

## Usage Examples
[Coming Soon: Video demonstrations will be added showing tool usage and common workflows]
 
## Contributing
Contributions are welcome! Whether it's bug reports, feature requests, documentation improvements, or code contributions - every contribution helps. Simply fork the repository and submit a pull request.

## License
This project is licensed under the MIT License - see the [`LICENSE`](LICENSE) file for details.

---
**Note**: This project is under active development. Features and documentation may change frequently.