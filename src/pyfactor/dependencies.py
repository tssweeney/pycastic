"""
Dependency analysis for Python symbols.

Analyzes what imports and internal symbols a given symbol depends on,
and what other symbols depend on it.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider


@dataclass
class ImportDependency:
    """An import that a symbol depends on."""

    module: str  # The module being imported from (e.g., "datetime")
    name: str  # The name being imported (e.g., "datetime")
    alias: Optional[str]  # Alias if any (e.g., "dt" in "import datetime as dt")
    is_from_import: bool  # True for "from x import y", False for "import x"


@dataclass
class SymbolDependencies:
    """Dependencies for a symbol."""

    symbol_name: str
    file_path: Path
    # External imports this symbol needs
    required_imports: list[ImportDependency] = field(default_factory=list)
    # Other symbols in the same file this symbol uses
    internal_dependencies: list[str] = field(default_factory=list)
    # What other symbols in the same file use this symbol
    internal_usages: list[str] = field(default_factory=list)


class NameCollector(cst.CSTVisitor):
    """Collects all Name references within a code block."""

    def __init__(self):
        self.names: set[str] = set()

    def visit_Name(self, node: cst.Name) -> bool:
        self.names.add(node.value)
        return True

    def visit_Attribute(self, node: cst.Attribute) -> bool:
        # For attribute access like "module.func", collect the base name
        if isinstance(node.value, cst.Name):
            self.names.add(node.value.value)
        return True


class ImportCollector(cst.CSTVisitor):
    """Collects all imports at module level."""

    def __init__(self):
        # Maps imported name (or alias) -> ImportDependency
        self.imports: dict[str, ImportDependency] = {}

    def visit_Import(self, node: cst.Import) -> bool:
        """Handle 'import x' and 'import x as y' statements."""
        if isinstance(node.names, cst.ImportStar):
            return False

        for alias in node.names:
            if isinstance(alias.name, cst.Name):
                name = alias.name.value
            else:
                # Dotted import like 'import os.path'
                name = _get_dotted_name(alias.name)

            # The name used in code is the alias if present, otherwise the first part
            local_name = alias.asname.name.value if alias.asname else name.split(".")[0]
            alias_str = alias.asname.name.value if alias.asname else None

            self.imports[local_name] = ImportDependency(
                module=name,
                name=name,
                alias=alias_str,
                is_from_import=False,
            )
        return False

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool:
        """Handle 'from x import y' statements."""
        if isinstance(node.names, cst.ImportStar):
            return False

        # Get the module name
        module = ""
        if node.module:
            module = _get_dotted_name(node.module)

        # Handle relative imports
        relative_prefix = "." * len(node.relative) if node.relative else ""
        full_module = relative_prefix + module

        for alias in node.names:
            name = alias.name.value
            local_name = alias.asname.name.value if alias.asname else name
            alias_str = alias.asname.name.value if alias.asname else None

            self.imports[local_name] = ImportDependency(
                module=full_module,
                name=name,
                alias=alias_str,
                is_from_import=True,
            )
        return False


class DefinitionCollector(cst.CSTVisitor):
    """Collects all top-level definitions in a module."""

    def __init__(self):
        self.definitions: dict[str, cst.CSTNode] = {}
        self._depth = 0

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        if self._depth == 0:
            self.definitions[node.name.value] = node
        self._depth += 1
        return True

    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        self._depth -= 1

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        if self._depth == 0:
            self.definitions[node.name.value] = node
        self._depth += 1
        return True

    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        self._depth -= 1

    def visit_Assign(self, node: cst.Assign) -> bool:
        if self._depth == 0:
            for target in node.targets:
                if isinstance(target.target, cst.Name):
                    self.definitions[target.target.value] = node
        return False

    def visit_AnnAssign(self, node: cst.AnnAssign) -> bool:
        if self._depth == 0 and isinstance(node.target, cst.Name):
            self.definitions[node.target.value] = node
        return False


def _get_dotted_name(node: cst.BaseExpression) -> str:
    """Get a dotted name from an Attribute or Name node."""
    if isinstance(node, cst.Name):
        return node.value
    elif isinstance(node, cst.Attribute):
        return f"{_get_dotted_name(node.value)}.{node.attr.value}"
    return ""


def _get_names_used_by_node(node: cst.CSTNode) -> set[str]:
    """Get all names referenced within a CST node using recursive traversal."""
    names: set[str] = set()

    def visit(n: cst.CSTNode) -> None:
        if isinstance(n, cst.Name):
            names.add(n.value)
        elif isinstance(n, cst.Attribute):
            # For attribute access like "module.func", collect the base name
            if isinstance(n.value, cst.Name):
                names.add(n.value.value)
        # Recursively visit all children
        for child in n.children:
            if isinstance(child, cst.CSTNode):
                visit(child)

    visit(node)
    return names


class DependencyAnalyzer:
    """Analyzes dependencies for symbols in a Python file."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._source: Optional[str] = None
        self._tree: Optional[cst.Module] = None
        self._imports: Optional[dict[str, ImportDependency]] = None
        self._definitions: Optional[dict[str, cst.CSTNode]] = None

    def _ensure_parsed(self) -> None:
        """Parse the file if not already parsed."""
        if self._tree is not None:
            return

        self._source = self.file_path.read_text()
        self._tree = cst.parse_module(self._source)

        # Wrap module for visiting
        wrapper = MetadataWrapper(self._tree)

        # Collect imports
        import_collector = ImportCollector()
        wrapper.visit(import_collector)
        self._imports = import_collector.imports

        # Collect definitions
        def_collector = DefinitionCollector()
        wrapper.visit(def_collector)
        self._definitions = def_collector.definitions

    def get_all_definitions(self) -> list[str]:
        """Get names of all top-level definitions in the file."""
        self._ensure_parsed()
        return list(self._definitions.keys())

    def get_all_imports(self) -> dict[str, ImportDependency]:
        """Get all imports in the file."""
        self._ensure_parsed()
        return self._imports.copy()

    def analyze_symbol(self, symbol_name: str) -> SymbolDependencies:
        """Analyze dependencies for a specific symbol."""
        self._ensure_parsed()

        if symbol_name not in self._definitions:
            raise ValueError(f"Symbol '{symbol_name}' not found in {self.file_path}")

        symbol_node = self._definitions[symbol_name]

        # Get all names used by this symbol
        names_used = _get_names_used_by_node(symbol_node)

        # Remove the symbol's own name (for recursive functions)
        names_used.discard(symbol_name)

        # Categorize dependencies
        required_imports = []
        internal_deps = []

        for name in names_used:
            if name in self._imports:
                required_imports.append(self._imports[name])
            elif name in self._definitions and name != symbol_name:
                internal_deps.append(name)
            # else: it's a builtin or parameter, ignore

        # Find what other symbols use this symbol
        internal_usages = []
        for other_name, other_node in self._definitions.items():
            if other_name == symbol_name:
                continue
            other_names_used = _get_names_used_by_node(other_node)
            if symbol_name in other_names_used:
                internal_usages.append(other_name)

        return SymbolDependencies(
            symbol_name=symbol_name,
            file_path=self.file_path,
            required_imports=required_imports,
            internal_dependencies=internal_deps,
            internal_usages=internal_usages,
        )

    def analyze_multiple(self, symbol_names: list[str]) -> dict[str, SymbolDependencies]:
        """Analyze dependencies for multiple symbols."""
        return {name: self.analyze_symbol(name) for name in symbol_names}

    def get_symbol_code(self, symbol_name: str) -> str:
        """Get the source code for a symbol."""
        self._ensure_parsed()
        if symbol_name not in self._definitions:
            raise ValueError(f"Symbol '{symbol_name}' not found in {self.file_path}")
        return self._tree.code_for_node(self._definitions[symbol_name])


def resolve_move_dependencies(
    file_path: Path,
    symbols_to_move: list[str],
    include_shared_deps: bool = False,
) -> tuple[list[str], list[str], list[ImportDependency]]:
    """
    Resolve the full list of symbols to move and identify shared dependencies.

    Args:
        file_path: Path to the source file
        symbols_to_move: Initial list of symbols to move
        include_shared_deps: If True, include shared deps in the move list

    Returns:
        Tuple of:
        - final_move_list: All symbols that should be moved
        - shared_deps: Symbols that are used by both moved and remaining symbols
        - required_imports: All imports needed by the moved symbols
    """
    analyzer = DependencyAnalyzer(file_path)
    all_definitions = set(analyzer.get_all_definitions())

    # Build the closure of symbols to move
    move_set = set(symbols_to_move)
    shared_deps = set()
    required_imports = {}

    # Keep expanding until no new symbols are added
    changed = True
    while changed:
        changed = False
        for symbol in list(move_set):
            deps = analyzer.analyze_symbol(symbol)

            # Add required imports
            for imp in deps.required_imports:
                key = (imp.module, imp.name)
                if key not in required_imports:
                    required_imports[key] = imp

            # Check internal dependencies
            for internal_dep in deps.internal_dependencies:
                if internal_dep in move_set:
                    continue  # Already moving this

                # Check if this dep is used by anything NOT being moved
                dep_info = analyzer.analyze_symbol(internal_dep)
                remaining_users = [u for u in dep_info.internal_usages if u not in move_set]

                if not remaining_users:
                    # No other users - safe to move along
                    move_set.add(internal_dep)
                    changed = True
                else:
                    # Shared dependency
                    if include_shared_deps:
                        move_set.add(internal_dep)
                        changed = True
                    else:
                        shared_deps.add(internal_dep)

    return list(move_set), list(shared_deps), list(required_imports.values())
