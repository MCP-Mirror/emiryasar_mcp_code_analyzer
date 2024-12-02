from . import server
import asyncio

def main():
    """Main entry point for the package."""
    import sys
    if '--analyze-path' in sys.argv:
        path_index = sys.argv.index('--analyze-path') + 1
        if path_index < len(sys.argv):
            analyze_path = sys.argv[path_index]
        else:
            analyze_path = "."
    else:
        analyze_path = "."

    # Run server with the path
    asyncio.run(server.main(analyze_path))

__all__ = ["main", "server"]