import sys
from mcp_code_analyzer import main

if __name__ == '__main__':
    analyze_path = sys.argv[2] if len(sys.argv) > 2 else "."
    main()