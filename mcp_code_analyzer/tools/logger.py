import logging
import sys
from pathlib import Path

class LogManager:
    """Centralized logging manager for MCP"""

    def __init__(self, log_dir: str = None):
        self.log_dir = Path(log_dir) if log_dir else Path.cwd() / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.main_log = self.log_dir / "mcp_server.log"

        self.tool_log = self.log_dir / "mcp_tools.log"

        self._setup_logging()

    def _setup_logging(self):
        main_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        tool_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(tool_name)s] - %(operation)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        main_handler = logging.FileHandler(self.main_log, encoding='utf-8')
        main_handler.setFormatter(main_formatter)

        tool_handler = logging.FileHandler(self.tool_log, encoding='utf-8')
        tool_handler.setFormatter(tool_formatter)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(main_formatter)

        # Root logger setup
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(main_handler)
        root_logger.addHandler(console_handler)

        # Tool logger setup
        tool_logger = logging.getLogger('mcp.tools')
        tool_logger.setLevel(logging.INFO)
        tool_logger.addHandler(tool_handler)

    def log_tool_operation(self, tool_name: str, operation: str, message: str,
                           level: str = 'INFO', **kwargs):
        logger = logging.getLogger('mcp.tools')

        extra = {
            'tool_name': tool_name,
            'operation': operation
        }

        if kwargs:
            message = f"{message} - {kwargs}"

        if level.upper() == 'ERROR':
            logger.error(message, extra=extra)
        elif level.upper() == 'WARNING':
            logger.warning(message, extra=extra)
        else:
            logger.info(message, extra=extra)

    def log_server_operation(self, message: str, level: str = 'INFO', **kwargs):
        logger = logging.getLogger('mcp.server')

        if kwargs:
            message = f"{message} - {kwargs}"

        if level.upper() == 'ERROR':
            logger.error(message)
        elif level.upper() == 'WARNING':
            logger.warning(message)
        else:
            logger.info(message)