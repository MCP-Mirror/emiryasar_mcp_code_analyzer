# MCP Code Analyzer
The main purpose of the MCP tool is to adapt changes to the project intelligently. 
For instance, when a code modification or structural adjustment is needed, it aims to ensure that other related usages are also updated accordingly.

Currently, the project has a lot of bugs, and the tools are not functioning as expected sometimes. Due to work commitments,
I can’t dedicate much time to it, but I’ll try to fix the issues and bring it to a working state whenever I find the time.


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
           "C:\\Projects\\path1"
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

- ⚠️🔄 **File Operations** (Always backup before use)
    - file_operations
    - version_control (Creates dated backups)
    - 
- ⚠️🔄 **Code Modify** (Always backup before use)
  - code_modifier (Performs modifying code line by line)(Currently has big issues) 
  
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

## Demo Video
Watch demonstration of MCP tool using with building Mario game:
[![Mario Game with Claude | MCP Code Analyzer Tool Demonstration](https://img.youtube.com/vi/MQtZCKNg13I/0.jpg)](https://youtu.be/MQtZCKNg13I)


Note: This is a demonstration of the tool's capabilities, not a complete game tutorial. While the game isn't fully playable due to Claude's message limits, this video shows how the MCP tool works and what you can do with it.

## Contributing
Contributions are welcome! Whether it's bug reports, feature requests, documentation improvements, or code contributions - every contribution helps. Simply fork the repository and submit a pull request.

## License
This project is licensed under the MIT License - see the [`LICENSE`](LICENSE) file for details.

---
**Note**: This project is under active development. Features and documentation may change frequently.