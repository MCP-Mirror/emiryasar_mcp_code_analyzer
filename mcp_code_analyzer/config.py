from dataclasses import dataclass, field
from typing import Set, Dict, Any
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

@dataclass
class SystemConfig:
    """System-wide configuration settings"""

    # Maximum file size to analyze (in bytes)
    MAX_FILE_SIZE: int = 1024 * 1024  # 1MB

    # Maximum directory depth for recursive analysis
    MAX_DEPTH: int = 10

    # Number of worker threads for parallel processing
    THREAD_POOL_SIZE: int = 4

    # Cache settings
    ENABLE_CACHE: bool = True
    MAX_CACHE_SIZE: int = 100  # Maximum number of cached results
    CACHE_TTL: int = 3600  # Cache time-to-live in seconds

@dataclass
class AnalysisConfig:
    """Analysis-specific configuration"""

    # Directories to exclude from analysis
    excluded_dirs: Set[str] = field(default_factory=lambda: {
        'node_modules', 'release', 'dist', 'build', '.git', '.aws', '.next',
        '__pycache__', 'venv', '.venv', 'env', '.env', 'coverage',
        '.coverage', 'tmp', '.tmp', '.idea', '.vscode'
    })

    # File types to exclude from analysis
    excluded_files: Set[str] = field(default_factory=lambda: {
        '.pyc', '.pyo', '.pyd', '.so', '.dll', '.dylib', '.log',
        '.DS_Store', '.env', '.coverage', '.pytest_cache'
    })

    # File types to analyze
    analyzable_extensions: Set[str] = field(default_factory=lambda: {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.go', '.java', '.rs'
    })

    # Technology markers for detection
    tech_markers: Dict[str, Any] = field(default_factory=lambda: {
        "Python": [".py", "requirements.txt", "setup.py", "pyproject.toml"],
        "JavaScript": [".js", "package.json", "package-lock.json"],
        "TypeScript": [".ts", "tsconfig.json"],
        "React": [".jsx", ".tsx"],
        "Vue": [".vue"],
        "Docker": ["Dockerfile", "docker-compose.yml"],
        "Go": [".go", "go.mod"],
        "Java": [".java", "pom.xml", "build.gradle"],
        "Rust": [".rs", "Cargo.toml"]
    })

# Global instances
system_config = SystemConfig()
analysis_config = AnalysisConfig()