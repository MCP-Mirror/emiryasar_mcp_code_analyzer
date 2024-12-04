# __main__.py
import sys
import logging
import asyncio
import locale
from pathlib import Path
from .server.handlers import main

def configure_encoding():
    """Configure system encoding settings"""
    if sys.platform == 'win32':
        import io
        import codecs
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)
        try:
            locale.setlocale(locale.LC_ALL, 'Turkish_Turkey.utf8')
        except locale.Error:
            try:
                locale.setlocale(locale.LC_ALL, 'tr_TR.UTF-8')
            except locale.Error:
                pass

# Configure logging with encoding support
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

def run():
    """Main entry point"""
    configure_encoding()

    analyze_paths = []
    try:
        path_start = sys.argv.index('--analyze-paths') + 1
        while path_start < len(sys.argv) and not sys.argv[path_start].startswith('--'):
            path = Path(sys.argv[path_start]).resolve()
            analyze_paths.append(str(path))
            path_start += 1
    except ValueError:
        analyze_paths = [str(Path.cwd())]
    except Exception as e:
        logger.error(f"Error parsing arguments: {e}")
        sys.exit(1)

    logger.info(f"Starting analysis with paths: {analyze_paths}")

    try:
        asyncio.run(main(analyze_paths))
    except KeyboardInterrupt:
        logger.info("Analysis interrupted by user")
    except Exception as e:
        logger.error(f"Error during analysis: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    run()