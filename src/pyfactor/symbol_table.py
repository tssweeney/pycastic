"""
Symbol table builder for tracking definitions and usages across files.

Uses LibCST to parse Python files and build a comprehensive symbol table
that tracks where symbols are defined and where they are referenced.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import libcst as cst
from libcst.metadata import MetadataWrapper, QualifiedNameProvider, PositionProvider


@dataclass
class SymbolLocation:
    """Location of a symbol in a file."""

    file_path: Path
    line: int
    column: int
    end_line: int
    end_column: int


@dataclass
class SymbolDefinition:
    """A symbol definition (class, function, variable)."""

    name: str
    qualified_name: str
    location: SymbolLocation
    symbol_type: str  # 'class', 'function', 'variable', 'import'


@dataclass
class SymbolReference:
    """A reference to a symbol."""

    name: str
    qualified_name: str
    location: SymbolLocation


@dataclass
class ImportInfo:
    """Information about an import statement."""

    module: str
    names: list[tuple[str, Optional[str]]]  # (name, alias)
    location: SymbolLocation
    is_from_import: bool


@dataclass
class FileSymbols:
    """All symbols in a single file."""

    file_path: Path
    definitions: list[SymbolDefinition] = field(default_factory=list)
    references: list[SymbolReference] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)


class SymbolCollector(cst.CSTVisitor):
    """Collects symbol definitions and references from a CST."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, file_path: Path, module_name: str):
        self.file_path = file_path
        self.module_name = module_name
        self.definitions: list[SymbolDefinition] = []
        self.references: list[SymbolReference] = []
        self.imports: list[ImportInfo] = []
        self._scope_stack: list[str] = []

    def _get_location(self, node: cst.CSTNode) -> SymbolLocation:
        """Get the location of a node."""
        pos = self.get_metadata(PositionProvider, node)
        return SymbolLocation(
            file_path=self.file_path,
            line=pos.start.line,
            column=pos.start.column,
            end_line=pos.end.line,
            end_column=pos.end.column,
        )

    def _current_scope(self) -> str:
        """Get the current scope as a qualified name."""
        if self._scope_stack:
            return f"{self.module_name}.{'.'.join(self._scope_stack)}"
        return self.module_name

    def _qualified_name(self, name: str) -> str:
        """Get the qualified name for a symbol."""
        scope = self._current_scope()
        return f"{scope}.{name}"

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        """Record class definition."""
        name = node.name.value
        self.definitions.append(
            SymbolDefinition(
                name=name,
                qualified_name=self._qualified_name(name),
                location=self._get_location(node.name),
                symbol_type="class",
            )
        )
        self._scope_stack.append(name)
        return True

    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        """Leave class scope."""
        self._scope_stack.pop()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        """Record function definition."""
        name = node.name.value
        self.definitions.append(
            SymbolDefinition(
                name=name,
                qualified_name=self._qualified_name(name),
                location=self._get_location(node.name),
                symbol_type="function",
            )
        )
        self._scope_stack.append(name)
        return True

    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        """Leave function scope."""
        self._scope_stack.pop()

    def visit_Assign(self, node: cst.Assign) -> bool:
        """Record variable assignments at module level."""
        if not self._scope_stack:  # Only module-level
            for target in node.targets:
                if isinstance(target.target, cst.Name):
                    name = target.target.value
                    self.definitions.append(
                        SymbolDefinition(
                            name=name,
                            qualified_name=self._qualified_name(name),
                            location=self._get_location(target.target),
                            symbol_type="variable",
                        )
                    )
        return True

    def visit_AnnAssign(self, node: cst.AnnAssign) -> bool:
        """Record annotated variable assignments at module level."""
        if not self._scope_stack and isinstance(node.target, cst.Name):
            name = node.target.value
            self.definitions.append(
                SymbolDefinition(
                    name=name,
                    qualified_name=self._qualified_name(name),
                    location=self._get_location(node.target),
                    symbol_type="variable",
                )
            )
        return True

    def visit_Name(self, node: cst.Name) -> bool:
        """Record name references."""
        # Skip if this is a definition target (handled separately)
        self.references.append(
            SymbolReference(
                name=node.value,
                qualified_name=node.value,  # Will be resolved later
                location=self._get_location(node),
            )
        )
        return True

    def visit_Import(self, node: cst.Import) -> bool:
        """Record import statements."""
        names = []
        if isinstance(node.names, cst.ImportStar):
            names.append(("*", None))
        else:
            for alias in node.names:
                name = alias.name.value if isinstance(alias.name, cst.Name) else _get_dotted_name(alias.name)
                asname = alias.asname.name.value if alias.asname else None
                names.append((name, asname))

        self.imports.append(
            ImportInfo(
                module="",
                names=names,
                location=self._get_location(node),
                is_from_import=False,
            )
        )
        return True

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool:
        """Record from ... import statements."""
        module = ""
        if node.module:
            module = _get_dotted_name(node.module)

        # Handle relative imports
        relative_prefix = "." * len(node.relative) if node.relative else ""
        full_module = relative_prefix + module

        names = []
        if isinstance(node.names, cst.ImportStar):
            names.append(("*", None))
        else:
            for alias in node.names:
                name = alias.name.value
                asname = alias.asname.name.value if alias.asname else None
                names.append((name, asname))

        self.imports.append(
            ImportInfo(
                module=full_module,
                names=names,
                location=self._get_location(node),
                is_from_import=True,
            )
        )
        return True


def _get_dotted_name(node: cst.BaseExpression) -> str:
    """Get a dotted name from an Attribute or Name node."""
    if isinstance(node, cst.Name):
        return node.value
    elif isinstance(node, cst.Attribute):
        return f"{_get_dotted_name(node.value)}.{node.attr.value}"
    return ""


def _path_to_module(file_path: Path, project_root: Path) -> str:
    """Convert a file path to a module name."""
    try:
        rel_path = file_path.relative_to(project_root)
    except ValueError:
        rel_path = file_path

    # Remove .py extension and convert to module path
    parts = list(rel_path.parts)
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]

    return ".".join(parts)


def collect_file_symbols(file_path: Path, project_root: Path) -> Optional[FileSymbols]:
    """Collect all symbols from a single file."""
    try:
        source = file_path.read_text()
        tree = cst.parse_module(source)
    except Exception:
        return None

    module_name = _path_to_module(file_path, project_root)
    wrapper = MetadataWrapper(tree)
    collector = SymbolCollector(file_path, module_name)

    try:
        wrapper.visit(collector)
    except Exception:
        return None

    return FileSymbols(
        file_path=file_path,
        definitions=collector.definitions,
        references=collector.references,
        imports=collector.imports,
    )


@dataclass
class SymbolTable:
    """Complete symbol table for a project."""

    project_root: Path
    files: dict[Path, FileSymbols] = field(default_factory=dict)
    definitions_by_name: dict[str, list[SymbolDefinition]] = field(default_factory=dict)

    def build(self) -> None:
        """Build the symbol table by scanning all Python files."""
        for root, dirs, files in os.walk(self.project_root):
            # Skip hidden directories and common non-source directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", ".git", ".venv", "venv")]

            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    file_symbols = collect_file_symbols(file_path, self.project_root)
                    if file_symbols:
                        self.files[file_path] = file_symbols
                        for defn in file_symbols.definitions:
                            if defn.name not in self.definitions_by_name:
                                self.definitions_by_name[defn.name] = []
                            self.definitions_by_name[defn.name].append(defn)

    def find_definition(self, file_path: Path, name: str) -> Optional[SymbolDefinition]:
        """Find a symbol definition by file and name."""
        if file_path not in self.files:
            return None
        for defn in self.files[file_path].definitions:
            if defn.name == name:
                return defn
        return None

    def find_definition_at(self, file_path: Path, line: int, column: int) -> Optional[SymbolDefinition]:
        """Find a symbol definition at a specific location."""
        if file_path not in self.files:
            return None
        for defn in self.files[file_path].definitions:
            loc = defn.location
            if loc.line == line and loc.column <= column < loc.end_column:
                return defn
        return None

    def find_all_references(self, symbol_name: str, defining_file: Path) -> list[tuple[Path, SymbolReference]]:
        """Find all references to a symbol across the project."""
        refs = []
        module_name = _path_to_module(defining_file, self.project_root)

        for file_path, file_symbols in self.files.items():
            # Check imports to see if this file imports the symbol
            imports_symbol = False
            for imp in file_symbols.imports:
                if imp.is_from_import:
                    # Check if importing from the defining module
                    if imp.module == module_name or imp.module.endswith(f".{module_name}"):
                        for name, alias in imp.names:
                            if name == symbol_name or name == "*":
                                imports_symbol = True
                                break

            # If same file or imports the symbol, check references
            if file_path == defining_file or imports_symbol:
                for ref in file_symbols.references:
                    if ref.name == symbol_name:
                        refs.append((file_path, ref))

        return refs

    def find_importing_files(self, module_name: str, symbol_name: Optional[str] = None) -> list[tuple[Path, ImportInfo]]:
        """Find all files that import a module or symbol."""
        results = []
        for file_path, file_symbols in self.files.items():
            for imp in file_symbols.imports:
                if imp.is_from_import:
                    if imp.module == module_name or imp.module.endswith(module_name):
                        if symbol_name is None:
                            results.append((file_path, imp))
                        else:
                            for name, _ in imp.names:
                                if name == symbol_name or name == "*":
                                    results.append((file_path, imp))
                                    break
                else:
                    for name, _ in imp.names:
                        if name == module_name:
                            results.append((file_path, imp))
                            break
        return results
