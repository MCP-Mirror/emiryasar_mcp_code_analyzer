import json
import os
from idlelib.iomenu import encoding
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Union, Tuple
from datetime import datetime
import logging
import shutil
import ast
import re
from dataclasses import dataclass
import tempfile
import hashlib
from enum import Enum, auto

logger = logging.getLogger(__name__)

class ChangeType(Enum):
    """Types of code changes"""
    MODIFY = auto()
    INSERT = auto()
    DELETE = auto()
    REFACTOR = auto()

class AnalysisType(Enum):
    """Types of code analysis"""
    SYNTAX = auto()
    IMPORTS = auto()
    FUNCTIONS = auto()
    CLASSES = auto()
    VARIABLES = auto()
    DEPENDENCIES = auto()

@dataclass
class AffectedCode:
    """Information about affected code"""
    file_path: str
    line_range: Dict[str, int]
    change_type: str
    reason: str
    suggested_action: str
    severity: str  # 'high', 'medium', 'low'
    reference_type: str  # 'import', 'function', 'class', 'variable'
    original_code: Optional[str] = None

@dataclass
class CodeChange:
    """Details of a code change"""
    file_path: str
    change_type: ChangeType
    section: Dict[str, int]
    original_content: str
    new_content: str
    affected_code: List[AffectedCode]
    metadata: Dict[str, Any]
    hash: str = ""

    def __post_init__(self):
        self.hash = hashlib.sha256(
            f"{self.file_path}:{self.section}:{self.original_content}:{self.new_content}"
            .encode()
        ).hexdigest()[:12]

@dataclass
class ModificationResult:
    """Result of code modification operation"""
    success: bool
    change: Optional[CodeChange] = None
    backup_path: Optional[str] = None
    error: Optional[str] = None
    validation_errors: List[str] = None
    affected_code: List[AffectedCode] = None
    details: Optional[Dict[str, Any]] = None

@dataclass
class ValidationResult:
    """Result of code validation"""
    valid: bool
    errors: List[str]
    warnings: List[str]
    details: Dict[str, Any]

class ModificationError(Exception):
    """Base error for code modifications"""
    def __init__(self, message: str, backup_path: Optional[str] = None):
        self.message = message
        self.backup_path = backup_path
        super().__init__(self.message)

class ValidationError(ModificationError):
    """Error during code validation"""
    pass

class BackupError(ModificationError):
    """Error during backup operations"""
    pass

class CodeModifier:
    """Advanced code modification tool with impact analysis"""

    def __init__(self, base_path: Optional[Union[str, Path]] = None):
        self._base_path = Path(base_path) if base_path else Path.cwd()
        self._backup_dir = self._base_path / "backups" / datetime.now().strftime('%Y%m%d')
        self._temp_dir = self._base_path / "temp"
        self._change_history: List[CodeChange] = []
        self._affected_files: Set[str] = set()
        self._cached_asts: Dict[str, ast.AST] = {}
        self._setup_directories()

    def _setup_directories(self) -> None:
        """Setup required directories"""
        try:
            self._backup_dir.mkdir(parents=True, exist_ok=True)
            self._temp_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create directories: {e}")
            raise ModificationError("Failed to initialize directory structure")

    async def modify_code(
            self,
            file_path: str,
            section: Dict[str, int],
            new_content: str,
            description: Optional[str] = None,
            validate: bool = True
    ) -> ModificationResult:
        """Modify code with comprehensive analysis and validation"""
        try:
            path = Path(file_path)
            if not self._validate_file(path):
                raise ValidationError("Invalid file path or file does not exist")

            # Create backup before any modification
            backup_path = await self._create_backup(path)

            # Read and validate file content
            original_content = self._read_file_content(path)
            if not original_content:
                raise ValidationError("Failed to read file content")

            lines = original_content.splitlines(keepends=True)
            start_line = section.get('start', 0)
            end_line = section.get('end', len(lines))

            if not self._validate_range(start_line, end_line, len(lines)):
                raise ValidationError("Invalid line range")

            # Extract original section content
            original_section = ''.join(lines[start_line:end_line])

            # Validate changes if requested
            if validate:
                validation = self._validate_modification(
                    path, original_section, new_content
                )
                if not validation.valid:
                    return ModificationResult(
                        success=False,
                        error="Validation failed",
                        validation_errors=validation.errors
                    )

            # Find affected code
            affected_code = await self._analyze_impact(
                path, original_section, new_content, section
            )

            # Prepare modification
            new_lines = lines.copy()
            new_content_lines = new_content.splitlines(keepends=True)
            new_lines[start_line:end_line] = new_content_lines

            # Create temporary file for modification
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
                tmp.writelines(new_lines)
                temp_path = Path(tmp.name)

            # Validate syntax if it's a Python file
            if path.suffix == '.py':
                try:
                    with open(temp_path, 'r') as f:
                        compile(f.read(), temp_path, 'exec')
                except SyntaxError as e:
                    temp_path.unlink()
                    raise ValidationError(f"Syntax error in modified code: {str(e)}")

            # Apply changes
            shutil.move(temp_path, path)

            # Create change record
            change = CodeChange(
                file_path=str(path),
                change_type=ChangeType.MODIFY,
                section=section,
                original_content=original_section,
                new_content=new_content,
                affected_code=affected_code,
                metadata={
                    'timestamp': datetime.now().isoformat(),
                    'backup_path': str(backup_path),
                    'description': description
                }
            )

            # Update history
            self._change_history.append(change)
            self._affected_files.update(f['file_path'] for f in affected_code)

            return ModificationResult(
                success=True,
                change=change,
                backup_path=str(backup_path),
                affected_code=affected_code,
                details={
                    'modified_lines': end_line - start_line,
                    'affected_files': len(self._affected_files),
                    'change_hash': change.hash
                }
            )

        except (ValidationError, ModificationError) as e:
            logger.error(f"Modification error: {e.message}")
            return ModificationResult(
                success=False,
                error=e.message,
                backup_path=getattr(e, 'backup_path', None)
            )
        except Exception as e:
            logger.error(f"Unexpected error during modification: {e}")
            if 'backup_path' in locals():
                try:
                    self._restore_backup(backup_path, path)
                    return ModificationResult(
                        success=False,
                        error=f"Error: {str(e)}, backup restored",
                        backup_path=str(backup_path)
                    )
                except Exception as restore_error:
                    logger.error(f"Failed to restore backup: {restore_error}")
            return ModificationResult(success=False, error=str(e))

    async def insert_code(
            self,
            file_path: str,
            line_number: int,
            content: str,
            description: Optional[str] = None,
            validate: bool = True
    ) -> ModificationResult:
        """Insert code at specific line"""
        return await self.modify_code(
            file_path,
            {"start": line_number, "end": line_number},
            content,
            description=description,
            validate=validate
        )

    async def delete_code(
            self,
            file_path: str,
            start_line: int,
            end_line: int,
            description: Optional[str] = None,
            validate: bool = True
    ) -> ModificationResult:
        """Delete code section with impact analysis"""
        return await self.modify_code(
            file_path,
            {"start": start_line, "end": end_line},
            "",
            description=description,
            validate=validate
        )

    async def _analyze_impact(
            self,
            file_path: Path,
            original_content: str,
            new_content: str,
            section: Dict[str, int]
    ) -> List[AffectedCode]:
        """Analyze impact of code changes"""
        affected_code = []

        # Analyze different aspects
        for analysis_type in AnalysisType:
            try:
                affected = await self._analyze_specific_impact(
                    analysis_type,
                    file_path,
                    original_content,
                    new_content,
                    section
                )
                affected_code.extend(affected)
            except Exception as e:
                logger.error(f"Error in {analysis_type} analysis: {e}")

        return affected_code

    async def _analyze_specific_impact(
            self,
            analysis_type: AnalysisType,
            file_path: Path,
            original_content: str,
            new_content: str,
            section: Dict[str, int]
    ) -> List[AffectedCode]:
        """Analyze specific type of impact"""
        affected = []

        if analysis_type == AnalysisType.SYNTAX:
            # Syntax changes might affect the entire file
            syntax_changes = self._analyze_syntax_changes(
                original_content,
                new_content
            )
            if syntax_changes:
                affected.append(
                    AffectedCode(
                        file_path=str(file_path),
                        line_range=section,
                        change_type="syntax",
                        reason="Syntax structure changed",
                        suggested_action="Review syntax changes",
                        severity="high",
                        reference_type="syntax",
                        original_code=original_content
                    )
                )

        elif analysis_type == AnalysisType.IMPORTS:
            # Changes in imports affect dependent files
            import_changes = self._analyze_import_changes(
                original_content,
                new_content
            )
            for change in import_changes:
                affected.extend(await self._find_import_dependents(
                    file_path, change
                ))

        elif analysis_type == AnalysisType.FUNCTIONS:
            # Function signature changes affect callers
            func_changes = self._analyze_function_changes(
                original_content,
                new_content
            )
            for change in func_changes:
                affected.extend(await self._find_function_callers(
                    file_path, change
                ))

        elif analysis_type == AnalysisType.CLASSES:
            # Class changes affect subclasses and usage
            class_changes = self._analyze_class_changes(
                original_content,
                new_content
            )
            for change in class_changes:
                affected.extend(await self._find_class_dependents(
                    file_path, change
                ))

        elif analysis_type == AnalysisType.VARIABLES:
            # Variable changes affect their usage
            var_changes = self._analyze_variable_changes(
                original_content,
                new_content
            )
            for change in var_changes:
                affected.extend(await self._find_variable_usage(
                    file_path, change
                ))

        return affected

    def _analyze_syntax_changes(self, original: str, modified: str) -> List[Dict[str, Any]]:
        """Analyze syntax structure changes"""
        changes = []
        try:
            original_ast = ast.parse(original)
            modified_ast = ast.parse(modified)

            # Compare AST structures
            original_nodes = set(type(node).__name__ for node in ast.walk(original_ast))
            modified_nodes = set(type(node).__name__ for node in ast.walk(modified_ast))

            if original_nodes != modified_nodes:
                changes.append({
                    'type': 'structure',
                    'added': modified_nodes - original_nodes,
                    'removed': original_nodes - modified_nodes
                })

        except Exception as e:
            logger.error(f"Syntax analysis error: {e}")

        return changes

    def _analyze_import_changes(self, original: str, modified: str) -> List[Dict[str, Any]]:
        """Analyze changes in imports"""
        changes = []
        try:
            original_ast = ast.parse(original)
            modified_ast = ast.parse(modified)

            def get_imports(tree: ast.AST) -> Set[str]:
                imports = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for name in node.names:
                            imports.add(name.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            for name in node.names:
                                imports.add(f"{node.module}.{name.name}")
                return imports

            original_imports = get_imports(original_ast)
            modified_imports = get_imports(modified_ast)

            if original_imports != modified_imports:
                changes.append({
                    'type': 'imports',
                    'added': modified_imports - original_imports,
                    'removed': original_imports - modified_imports
                })

        except Exception as e:
            logger.error(f"Import analysis error: {e}")

        return changes

    def _analyze_function_changes(self, original: str, modified: str) -> List[Dict[str, Any]]:
        """Analyze function signature changes"""
        changes = []
        try:
            original_ast = ast.parse(original)
            modified_ast = ast.parse(modified)

            def get_function_info(node: ast.FunctionDef) -> Dict[str, Any]:
                return {
                    'name': node.name,
                    'args': len(node.args.args),
                    'defaults': len(node.args.defaults),
                    'kwonly': len(node.args.kwonlyargs),
                    'vararg': bool(node.args.vararg),
                    'kwarg': bool(node.args.kwarg)
                }

            original_funcs = {
                node.name: get_function_info(node)
                for node in ast.walk(original_ast)
                if isinstance(node, ast.FunctionDef)
            }

            modified_funcs = {
                node.name: get_function_info(node)
                for node in ast.walk(modified_ast)
                if isinstance(node, ast.FunctionDef)
            }

            # Find changed functions
            for name, info in modified_funcs.items():
                if name in original_funcs and original_funcs[name] != info:
                    changes.append({
                        'type': 'function',
                        'name': name,
                        'original': original_funcs[name],
                        'modified': info
                    })

        except Exception as e:
            logger.error(f"Function analysis error: {e}")

        return changes

    def _analyze_class_changes(self, original: str, modified: str) -> List[Dict[str, Any]]:
        """Analyze class structure changes"""
        changes = []
        try:
            original_ast = ast.parse(original)
            modified_ast = ast.parse(modified)

            def get_class_info(node: ast.ClassDef) -> Dict[str, Any]:
                return {
                    'name': node.name,
                    'bases': [base.id for base in node.bases if isinstance(base, ast.Name)],
                    'methods': {
                        n.name: {
                            'args': len(n.args.args) - 1,  # Subtract 'self'
                            'decorators': [d.id for d in n.decorator_list if isinstance(d, ast.Name)]
                        }
                        for n in node.body if isinstance(n, ast.FunctionDef)
                    },
                    'properties': [
                        n.name for n in node.body
                        if isinstance(n, ast.FunctionDef) and
                           any(d.id == 'property' for d in n.decorator_list if isinstance(d, ast.Name))
                    ]
                }

            original_classes = {
                node.name: get_class_info(node)
                for node in ast.walk(original_ast)
                if isinstance(node, ast.ClassDef)
            }

            modified_classes = {
                node.name: get_class_info(node)
                for node in ast.walk(modified_ast)
                if isinstance(node, ast.ClassDef)
            }

            # Analyze changes
            for name, info in modified_classes.items():
                if name in original_classes:
                    orig_info = original_classes[name]
                    if orig_info != info:
                        changes.append({
                            'type': 'class',
                            'name': name,
                            'changes': {
                                'bases_changed': orig_info['bases'] != info['bases'],
                                'methods_changed': orig_info['methods'] != info['methods'],
                                'properties_changed': orig_info['properties'] != info['properties']
                            },
                            'original': orig_info,
                            'modified': info
                        })

        except Exception as e:
            logger.error(f"Class analysis error: {e}")

        return changes

    def _analyze_variable_changes(self, original: str, modified: str) -> List[Dict[str, Any]]:
        """Analyze variable changes including type hints and values"""
        changes = []
        try:
            original_ast = ast.parse(original)
            modified_ast = ast.parse(modified)

            def get_variable_info(node: ast.AST) -> Dict[str, Any]:
                variables = {}
                for n in ast.walk(node):
                    if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                        variables[n.target.id] = {
                            'type': 'annotated',
                            'annotation': ast.unparse(n.annotation) if n.annotation else None,
                            'value': ast.unparse(n.value) if n.value else None
                        }
                    elif isinstance(n, ast.Assign):
                        for target in n.targets:
                            if isinstance(target, ast.Name):
                                variables[target.id] = {
                                    'type': 'standard',
                                    'value': ast.unparse(n.value)
                                }
                return variables

            original_vars = get_variable_info(original_ast)
            modified_vars = get_variable_info(modified_ast)

            # Find changed variables
            for name, info in modified_vars.items():
                if name in original_vars:
                    orig_info = original_vars[name]
                    if orig_info != info:
                        changes.append({
                            'type': 'variable',
                            'name': name,
                            'original': orig_info,
                            'modified': info
                        })

        except Exception as e:
            logger.error(f"Variable analysis error: {e}")

        return changes

    async def _find_import_dependents(
            self,
            file_path: Path,
            import_change: Dict[str, Any]
    ) -> List[AffectedCode]:
        """Find files that depend on changed imports"""
        affected = []
        search_path = self._base_path

        for python_file in search_path.rglob('*.py'):
            if python_file == file_path:
                continue

            try:
                content = self._read_file_content(python_file)
                if not content:
                    continue

                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        imported_names = []
                        if isinstance(node, ast.Import):
                            imported_names.extend(n.name for n in node.names)
                        else:
                            if node.module:
                                imported_names.extend(f"{node.module}.{n.name}" for n in node.names)

                        for removed in import_change.get('removed', []):
                            if removed in imported_names:
                                affected.append(AffectedCode(
                                    file_path=str(python_file),
                                    line_range={'start': node.lineno, 'end': node.end_lineno or node.lineno},
                                    change_type='import',
                                    reason=f"Uses removed import '{removed}'",
                                    suggested_action="Update import statement",
                                    severity="high",
                                    reference_type="import",
                                    original_code=ast.unparse(node)
                                ))

            except Exception as e:
                logger.error(f"Error analyzing imports in {python_file}: {e}")

        return affected

    async def _find_function_callers(
            self,
            file_path: Path,
            function_change: Dict[str, Any]
    ) -> List[AffectedCode]:
        """Find all function calls that need updates"""
        affected = []
        search_path = self._base_path
        func_name = function_change['name']

        for python_file in search_path.rglob('*.py'):
            if python_file == file_path:
                continue

            try:
                content = self._read_file_content(python_file)
                if not content:
                    continue

                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if (isinstance(node.func, ast.Name) and node.func.id == func_name) or \
                                (isinstance(node.func, ast.Attribute) and node.func.attr == func_name):

                            # Check if call signature matches the changes
                            current_args = len(node.args) + len(node.keywords)
                            new_required_args = function_change['modified']['args']

                            if current_args != new_required_args:
                                affected.append(AffectedCode(
                                    file_path=str(python_file),
                                    line_range={'start': node.lineno, 'end': node.end_lineno or node.lineno},
                                    change_type='function_call',
                                    reason=f"Call to modified function '{func_name}' needs update",
                                    suggested_action=f"Update call signature ({current_args} args to {new_required_args})",
                                    severity="high",
                                    reference_type="function",
                                    original_code=ast.unparse(node)
                                ))

            except Exception as e:
                logger.error(f"Error analyzing function calls in {python_file}: {e}")

        return affected

    async def _find_class_dependents(
            self,
            file_path: Path,
            class_change: Dict[str, Any]
    ) -> List[AffectedCode]:
        """Find classes that inherit or use the modified class"""
        affected = []
        search_path = self._base_path
        class_name = class_change['name']

        for python_file in search_path.rglob('*.py'):
            if python_file == file_path:
                continue

            try:
                content = self._read_file_content(python_file)
                if not content:
                    continue

                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        # Check inheritance
                        for base in node.bases:
                            if isinstance(base, ast.Name) and base.id == class_name:
                                affected.append(AffectedCode(
                                    file_path=str(python_file),
                                    line_range={'start': node.lineno, 'end': node.end_lineno or node.lineno},
                                    change_type='inheritance',
                                    reason=f"Inherits from modified class '{class_name}'",
                                    suggested_action="Review class changes and update inheritance",
                                    severity="high",
                                    reference_type="class",
                                    original_code=ast.unparse(node)
                                ))

                    # Check instantiation and method calls
                    elif isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name) and node.func.id == class_name:
                            affected.append(AffectedCode(
                                file_path=str(python_file),
                                line_range={'start': node.lineno, 'end': node.end_lineno or node.lineno},
                                change_type='instantiation',
                                reason=f"Instantiates modified class '{class_name}'",
                                suggested_action="Review class changes and update instantiation",
                                severity="medium",
                                reference_type="class",
                                original_code=ast.unparse(node)
                            ))

            except Exception as e:
                logger.error(f"Error analyzing class usage in {python_file}: {e}")

        return affected

    async def _find_variable_usage(
            self,
            file_path: Path,
            variable_change: Dict[str, Any]
    ) -> List[AffectedCode]:
        """Find all uses of the modified variable"""
        affected = []
        search_path = self._base_path
        var_name = variable_change['name']

        for python_file in search_path.rglob('*.py'):
            if python_file == file_path:
                continue

            try:
                content = self._read_file_content(python_file)
                if not content:
                    continue

                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name) and node.id == var_name:
                        context = "write" if isinstance(node.ctx, ast.Store) else "read"
                        affected.append(AffectedCode(
                            file_path=str(python_file),
                            line_range={'start': node.lineno, 'end': node.end_lineno or node.lineno},
                            change_type='variable_usage',
                            reason=f"Uses modified variable '{var_name}' ({context} operation)",
                            suggested_action=f"Review variable changes and update {context} operation",
                            severity="medium",
                            reference_type="variable",
                            original_code=ast.unparse(node)
                        ))

            except Exception as e:
                logger.error(f"Error analyzing variable usage in {python_file}: {e}")

        return affected

    async def _create_backup(self, file_path: Path) -> Path:
        """Create backup with proper encoding"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = self._backup_dir / f"{file_path.stem}_backup_{timestamp}{file_path.suffix}"

        with open(file_path, 'r', encoding='utf-8', errors='replace') as src:
            content = src.read()
            with open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(content)

        return backup_path

    def _validate_file(self, file_path: Path) -> bool:
        """Validate file existence and permissions"""
        try:
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return False

            if not file_path.is_file():
                logger.error(f"Not a file: {file_path}")
                return False

            # Check read/write permissions
            if not os.access(file_path, os.R_OK | os.W_OK):
                logger.error(f"Insufficient permissions for {file_path}")
                return False

            return True

        except Exception as e:
            logger.error(f"File validation failed: {e}")
            return False

    def _validate_range(self, start: int, end: int, max_lines: int) -> bool:
        """Validate line range"""
        return (0 <= start < max_lines and
                0 <= end <= max_lines and
                start <= end)

    def _validate_modification(
            self,
            file_path: Path,
            original_content: str,
            new_content: str
    ) -> ValidationResult:
        """Validate proposed code modification"""
        errors = []
        warnings = []
        details = {}

        try:
            # Check for syntax errors in new content
            if file_path.suffix == '.py':
                try:
                    ast.parse(new_content)
                except SyntaxError as e:
                    errors.append(f"Syntax error: {str(e)}")
                    details['syntax_error'] = str(e)

            # Check for significant size changes
            size_ratio = len(new_content) / len(original_content) if original_content else float('inf')
            if size_ratio > 3 or size_ratio < 0.3:
                warnings.append(f"Significant size change (ratio: {size_ratio:.2f})")
                details['size_ratio'] = size_ratio

            # Check for common issues
            if new_content.strip() == '':
                warnings.append("New content is empty")

            if len(new_content.splitlines()) > 100:
                warnings.append("New content is very long")

            # Indentation check for Python files
            if file_path.suffix == '.py':
                indent_issues = self._check_indentation(new_content)
                if indent_issues:
                    warnings.extend(indent_issues)

            return ValidationResult(
                valid=len(errors) == 0,
                errors=errors,
                warnings=warnings,
                details=details
            )

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return ValidationResult(
                valid=False,
                errors=[str(e)],
                warnings=[],
                details={'exception': str(e)}
            )

    def _check_indentation(self, content: str) -> List[str]:
        """Check Python code indentation"""
        issues = []
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            if line.strip():  # Skip empty lines
                # Check if indentation is multiple of 4
                indent = len(line) - len(line.lstrip())
                if indent % 4 != 0:
                    issues.append(f"Line {i}: Indentation not a multiple of 4")

                # Check for mixed tabs and spaces
                if '\t' in line[:indent]:
                    issues.append(f"Line {i}: Mixed tabs and spaces")

        return issues

    def _read_file_content(self, file_path: Path) -> Optional[str]:
        """Safely read file content with encoding detection"""
        try:
            # Try UTF-8 first
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Try to detect encoding
            try:
                import chardet
                with open(file_path, 'rb') as f:
                    raw = f.read()
                detected = chardet.detect(raw)
                encoding = detected['encoding']

                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read file {file_path}: {e}")
                return None

    async def _restore_backup(self, backup_path: Path, target_path: Path, encoding: str) -> None:
        """Restore from backup with proper encoding"""
        try:
            with open(backup_path, 'r', encoding=encoding, errors='replace') as src:
                content = src.read()
                with open(target_path, 'w', encoding=encoding) as dst:
                    dst.write(content)
        except Exception as e:
            logger.error(f"Backup restoration failed: {e}")

    def get_changes(
            self,
            file_path: Optional[str] = None,
            change_type: Optional[ChangeType] = None
    ) -> List[CodeChange]:
        """Get filtered change history"""
        changes = self._change_history

        if file_path:
            changes = [c for c in changes if c.file_path == file_path]

        if change_type:
            changes = [c for c in changes if c.change_type == change_type]

        return changes

    def clear_old_backups(self, days: int = 7) -> int:
        """Clear backups older than specified days"""
        if not self._backup_dir.exists():
            return 0

        cleared = 0
        cutoff = datetime.now().timestamp() - (days * 86400)

        try:
            for backup_dir in self._backup_dir.parent.iterdir():
                if not backup_dir.is_dir():
                    continue

                if backup_dir.stat().st_mtime < cutoff:
                    shutil.rmtree(backup_dir)
                    cleared += 1

            return cleared

        except Exception as e:
            logger.error(f"Failed to clear old backups: {e}")
            return cleared

    def get_affected_files(self) -> Set[str]:
        """Get set of all affected files"""
        return self._affected_files

    def clear_change_history(self) -> None:
        """Clear change history and affected files tracking"""
        self._change_history.clear()
        self._affected_files.clear()