"""
LibCST-based refactoring transformers.

Provides transformers for renaming symbols, updating imports, and
moving code between files.
"""
from pathlib import Path
from typing import Optional, Union

import libcst as cst
from libcst import matchers as m
from libcst.metadata import MetadataWrapper


class RenameTransformer(cst.CSTTransformer):
    """Transformer that renames occurrences of a symbol.

    IMPORTANT: This transformer is careful to NOT rename:
    - Module paths in import statements (e.g., 'console' in 'from rich.console import')
    - Parts of attribute access on external modules

    It ONLY renames:
    - Local variable definitions and usages
    - Function/class definitions
    - The actual imported names (after 'import' keyword)
    """

    def __init__(self, old_name: str, new_name: str, rename_definitions: bool = True):
        self.old_name = old_name
        self.new_name = new_name
        self.rename_definitions = rename_definitions
        self.changes_made = 0
        # Track context to avoid renaming import module paths
        self._in_import_module = False
        self._in_import_alias_name = False

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool:
        """Entering an ImportFrom - module part should not be renamed."""
        return True

    def visit_ImportFrom_module(self, node: cst.ImportFrom) -> None:
        """Visiting the module part of ImportFrom - don't rename here."""
        self._in_import_module = True

    def leave_ImportFrom_module(self, node: cst.ImportFrom) -> None:
        """Leaving the module part of ImportFrom."""
        self._in_import_module = False

    def visit_Import(self, node: cst.Import) -> bool:
        """Entering an Import statement."""
        return True

    def visit_ImportAlias_name(self, node: cst.ImportAlias) -> None:
        """Visiting the name part of ImportAlias (the module being imported)."""
        # For 'import foo.bar', foo.bar is the module path - don't rename
        # For 'from x import foo', foo is the imported name - CAN rename
        # We need to check if we're in Import vs ImportFrom
        self._in_import_alias_name = True

    def leave_ImportAlias_name(self, node: cst.ImportAlias) -> None:
        """Leaving the name part of ImportAlias."""
        self._in_import_alias_name = False

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        """Rename Name nodes, but NOT inside import module paths."""
        # Don't rename if we're in an import module path
        if self._in_import_module:
            return updated_node

        # For 'import foo.bar' style imports, don't rename the module path
        # But for 'from x import foo', we DO want to rename 'foo' if it matches
        # The _in_import_alias_name flag is set for both cases, so we need
        # to be more careful. Actually, for safety let's not rename import aliases
        # at all in this transformer - that should be done by ImportRenameTransformer
        if self._in_import_alias_name:
            return updated_node

        if updated_node.value == self.old_name:
            self.changes_made += 1
            return updated_node.with_changes(value=self.new_name)
        return updated_node

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:
        """Rename class definitions."""
        if self.rename_definitions and updated_node.name.value == self.old_name:
            self.changes_made += 1
            return updated_node.with_changes(
                name=cst.Name(self.new_name)
            )
        return updated_node

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
        """Rename function definitions."""
        if self.rename_definitions and updated_node.name.value == self.old_name:
            self.changes_made += 1
            return updated_node.with_changes(
                name=cst.Name(self.new_name)
            )
        return updated_node

    def leave_Arg(self, original_node: cst.Arg, updated_node: cst.Arg) -> cst.Arg:
        """Rename keyword arguments."""
        if updated_node.keyword and updated_node.keyword.value == self.old_name:
            self.changes_made += 1
            return updated_node.with_changes(
                keyword=cst.Name(self.new_name)
            )
        return updated_node


class ImportRenameTransformer(cst.CSTTransformer):
    """Transformer that updates import statements when a module or symbol is renamed.

    This is used for:
    1. Renaming imported symbols: 'from x import old' -> 'from x import new'
    2. Updating module paths when a file is renamed/moved

    IMPORTANT: This should only be used for LOCAL modules we control,
    never for external packages.
    """

    def __init__(
        self,
        old_module: Optional[str] = None,
        new_module: Optional[str] = None,
        old_name: Optional[str] = None,
        new_name: Optional[str] = None,
    ):
        self.old_module = old_module
        self.new_module = new_module
        self.old_name = old_name
        self.new_name = new_name
        self.changes_made = 0

    def _update_dotted_name(self, node: Union[cst.Name, cst.Attribute], old: str, new: str) -> Union[cst.Name, cst.Attribute]:
        """Update a dotted name (Name or Attribute chain)."""
        current = _get_dotted_name_str(node)
        if current == old:
            return _make_dotted_name(new)
        return node

    def leave_ImportFrom(self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom) -> cst.ImportFrom:
        """Update from ... import statements."""
        changes = {}

        # Update module name if needed (only for exact matches)
        if self.old_module and self.new_module and updated_node.module:
            current_module = _get_dotted_name_str(updated_node.module)
            if current_module == self.old_module:
                changes["module"] = _make_dotted_name(self.new_module)
                self.changes_made += 1

        # Update imported names if needed
        if self.old_name and self.new_name and not isinstance(updated_node.names, cst.ImportStar):
            new_names = []
            names_changed = False
            for alias in updated_node.names:
                if isinstance(alias.name, cst.Name) and alias.name.value == self.old_name:
                    new_alias = alias.with_changes(name=cst.Name(self.new_name))
                    new_names.append(new_alias)
                    names_changed = True
                    self.changes_made += 1
                else:
                    new_names.append(alias)
            if names_changed:
                changes["names"] = new_names

        if changes:
            return updated_node.with_changes(**changes)
        return updated_node

    def leave_Import(self, original_node: cst.Import, updated_node: cst.Import) -> cst.Import:
        """Update import statements."""
        if not self.old_module or not self.new_module:
            return updated_node

        if isinstance(updated_node.names, cst.ImportStar):
            return updated_node

        new_names = []
        names_changed = False
        for alias in updated_node.names:
            current_name = _get_dotted_name_str(alias.name)
            if current_name == self.old_module:
                new_alias = alias.with_changes(name=_make_dotted_name(self.new_module))
                new_names.append(new_alias)
                names_changed = True
                self.changes_made += 1
            else:
                new_names.append(alias)

        if names_changed:
            return updated_node.with_changes(names=new_names)
        return updated_node


class AttributeRenameTransformer(cst.CSTTransformer):
    """Transformer that renames attribute accesses (e.g., module.symbol)."""

    def __init__(self, module_name: str, old_name: str, new_name: str):
        self.module_name = module_name
        self.old_name = old_name
        self.new_name = new_name
        self.changes_made = 0

    def leave_Attribute(self, original_node: cst.Attribute, updated_node: cst.Attribute) -> cst.Attribute:
        """Rename attribute access like module.old_name -> module.new_name."""
        if updated_node.attr.value == self.old_name:
            # Check if the value is the module we're looking for
            if isinstance(updated_node.value, cst.Name) and updated_node.value.value == self.module_name:
                self.changes_made += 1
                return updated_node.with_changes(attr=cst.Name(self.new_name))
        return updated_node


def _get_dotted_name_str(node: Union[cst.Name, cst.Attribute]) -> str:
    """Convert a Name or Attribute node to a dotted string."""
    if isinstance(node, cst.Name):
        return node.value
    elif isinstance(node, cst.Attribute):
        return f"{_get_dotted_name_str(node.value)}.{node.attr.value}"
    return ""


def _make_dotted_name(name: str) -> Union[cst.Name, cst.Attribute]:
    """Create a Name or Attribute node from a dotted string.

    Note: This does NOT handle relative imports (strings starting with dots).
    For relative imports, use _parse_relative_module() instead.
    """
    # Filter out empty parts (from leading/trailing dots or double dots)
    parts = [p for p in name.split(".") if p]

    if not parts:
        raise ValueError(f"Cannot create dotted name from empty or dot-only string: {name!r}")

    if len(parts) == 1:
        return cst.Name(parts[0])

    result = cst.Name(parts[0])
    for part in parts[1:]:
        result = cst.Attribute(value=result, attr=cst.Name(part))
    return result


def _parse_relative_module(module: str) -> tuple[list[cst.Dot], Optional[Union[cst.Name, cst.Attribute]]]:
    """Parse a module string that may contain relative import dots.

    Args:
        module: Module string like ".", "..", ".foo", "..foo.bar", or "foo.bar"

    Returns:
        Tuple of (relative_dots, module_node) where:
        - relative_dots is a list of cst.Dot for relative imports
        - module_node is the module name (None for pure relative like ".")
    """
    # Count leading dots
    dot_count = 0
    for char in module:
        if char == ".":
            dot_count += 1
        else:
            break

    # Create relative dots
    relative = [cst.Dot() for _ in range(dot_count)]

    # Get the module part after the dots
    module_part = module[dot_count:]

    if module_part:
        module_node = _make_dotted_name(module_part)
    else:
        module_node = None

    return relative, module_node


def rename_in_source(source: str, old_name: str, new_name: str) -> tuple[str, int]:
    """
    Rename all occurrences of a symbol in source code.

    This is careful to NOT rename:
    - Module paths in import statements
    - External package references

    Returns:
        Tuple of (modified_source, number_of_changes)
    """
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return source, 0

    transformer = RenameTransformer(old_name, new_name)
    new_tree = tree.visit(transformer)
    return new_tree.code, transformer.changes_made


def update_imports_in_source(
    source: str,
    old_module: Optional[str] = None,
    new_module: Optional[str] = None,
    old_name: Optional[str] = None,
    new_name: Optional[str] = None,
) -> tuple[str, int]:
    """
    Update import statements in source code.

    Returns:
        Tuple of (modified_source, number_of_changes)
    """
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return source, 0

    transformer = ImportRenameTransformer(old_module, new_module, old_name, new_name)
    new_tree = tree.visit(transformer)
    return new_tree.code, transformer.changes_made


def rename_attribute_in_source(source: str, module_name: str, old_name: str, new_name: str) -> tuple[str, int]:
    """
    Rename attribute accesses in source code.

    Returns:
        Tuple of (modified_source, number_of_changes)
    """
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return source, 0

    transformer = AttributeRenameTransformer(module_name, old_name, new_name)
    new_tree = tree.visit(transformer)
    return new_tree.code, transformer.changes_made


class DefinitionExtractor(cst.CSTVisitor):
    """Extract a symbol definition from source code."""

    def __init__(self, symbol_name: str):
        self.symbol_name = symbol_name
        self.definition: Optional[cst.CSTNode] = None
        self.definition_code: Optional[str] = None

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        if node.name.value == self.symbol_name:
            self.definition = node
            return False
        return True

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        if node.name.value == self.symbol_name:
            self.definition = node
            return False
        return True

    def visit_Assign(self, node: cst.Assign) -> bool:
        for target in node.targets:
            if isinstance(target.target, cst.Name) and target.target.value == self.symbol_name:
                self.definition = node
                return False
        return True


class DefinitionRemover(cst.CSTTransformer):
    """Remove a symbol definition from source code."""

    def __init__(self, symbol_name: str):
        self.symbol_name = symbol_name
        self.removed = False

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> Union[cst.ClassDef, cst.RemovalSentinel]:
        if updated_node.name.value == self.symbol_name:
            self.removed = True
            return cst.RemovalSentinel.REMOVE
        return updated_node

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> Union[cst.FunctionDef, cst.RemovalSentinel]:
        if updated_node.name.value == self.symbol_name:
            self.removed = True
            return cst.RemovalSentinel.REMOVE
        return updated_node

    def leave_SimpleStatementLine(self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine) -> Union[cst.SimpleStatementLine, cst.RemovalSentinel]:
        for stmt in updated_node.body:
            if isinstance(stmt, cst.Assign):
                for target in stmt.targets:
                    if isinstance(target.target, cst.Name) and target.target.value == self.symbol_name:
                        self.removed = True
                        return cst.RemovalSentinel.REMOVE
        return updated_node


def extract_definition(source: str, symbol_name: str) -> Optional[str]:
    """Extract a symbol definition from source code."""
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return None

    # Search for the definition in the module body
    for stmt in tree.body:
        if isinstance(stmt, cst.ClassDef) and stmt.name.value == symbol_name:
            return tree.code_for_node(stmt)
        elif isinstance(stmt, cst.FunctionDef) and stmt.name.value == symbol_name:
            return tree.code_for_node(stmt)
        elif isinstance(stmt, cst.SimpleStatementLine):
            for body_stmt in stmt.body:
                if isinstance(body_stmt, cst.Assign):
                    for target in body_stmt.targets:
                        if isinstance(target.target, cst.Name) and target.target.value == symbol_name:
                            return tree.code_for_node(stmt)

    return None


def remove_definition(source: str, symbol_name: str) -> tuple[str, bool]:
    """Remove a symbol definition from source code."""
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return source, False

    remover = DefinitionRemover(symbol_name)
    new_tree = tree.visit(remover)
    return new_tree.code, remover.removed


def add_definition(source: str, definition_code: str) -> str:
    """Add a definition to the end of source code."""
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return source + "\n\n" + definition_code

    # Parse the definition
    try:
        def_tree = cst.parse_module(definition_code)
    except cst.ParserSyntaxError:
        return source + "\n\n" + definition_code

    # Add to end of module
    new_body = list(tree.body) + [cst.EmptyLine(whitespace=cst.SimpleWhitespace(""))] + list(def_tree.body)
    new_tree = tree.with_changes(body=new_body)
    return new_tree.code


def add_import(source: str, module: str, name: str, alias: Optional[str] = None) -> str:
    """Add an import statement to source code.

    Handles both absolute imports (from foo.bar import x) and
    relative imports (from . import x, from ..foo import x).
    """
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        import_line = f"from {module} import {name}" + (f" as {alias}" if alias else "")
        return import_line + "\n" + source

    # Create the import alias
    import_alias = cst.ImportAlias(
        name=cst.Name(name),
        asname=cst.AsName(whitespace_before_as=cst.SimpleWhitespace(" "), whitespace_after_as=cst.SimpleWhitespace(" "), name=cst.Name(alias)) if alias else None,
    )

    # Parse the module, handling relative imports
    relative, module_node = _parse_relative_module(module)

    # Create the import statement
    import_stmt = cst.SimpleStatementLine(
        body=[
            cst.ImportFrom(
                relative=relative,
                module=module_node,
                names=[import_alias],
                whitespace_after_from=cst.SimpleWhitespace(" "),
                whitespace_before_import=cst.SimpleWhitespace(" "),
                whitespace_after_import=cst.SimpleWhitespace(" "),
            )
        ]
    )

    # Find the right place to insert (after existing imports)
    insert_idx = 0
    for i, stmt in enumerate(tree.body):
        if isinstance(stmt, cst.SimpleStatementLine):
            for body_stmt in stmt.body:
                if isinstance(body_stmt, (cst.Import, cst.ImportFrom)):
                    insert_idx = i + 1

    new_body = list(tree.body)
    new_body.insert(insert_idx, import_stmt)
    new_tree = tree.with_changes(body=new_body)
    return new_tree.code


class UsedNamesCollector(cst.CSTVisitor):
    """Collects all Name nodes used in the code (excluding import statements)."""

    def __init__(self):
        self.names: set[str] = set()
        self._in_import = False

    def visit_Import(self, node: cst.Import) -> bool:
        self._in_import = True
        return True

    def leave_Import(self, node: cst.Import) -> None:
        self._in_import = False

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool:
        self._in_import = True
        return True

    def leave_ImportFrom(self, node: cst.ImportFrom) -> None:
        self._in_import = False

    def visit_Name(self, node: cst.Name) -> bool:
        if not self._in_import:
            self.names.add(node.value)
        return True


class ImportedNamesCollector(cst.CSTVisitor):
    """Collects all names that are imported."""

    def __init__(self):
        # Maps local name -> (module, imported_name, alias, is_from_import)
        self.imports: dict[str, tuple[str, str, Optional[str], bool]] = {}

    def visit_Import(self, node: cst.Import) -> bool:
        if isinstance(node.names, cst.ImportStar):
            return False
        for alias in node.names:
            if isinstance(alias.name, cst.Name):
                name = alias.name.value
            else:
                name = _get_dotted_name_str(alias.name)
            local_name = alias.asname.name.value if alias.asname else name.split(".")[0]
            alias_str = alias.asname.name.value if alias.asname else None
            self.imports[local_name] = (name, name, alias_str, False)
        return False

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool:
        if isinstance(node.names, cst.ImportStar):
            return False
        module = ""
        if node.module:
            module = _get_dotted_name_str(node.module)
        relative_prefix = "." * len(node.relative) if node.relative else ""
        full_module = relative_prefix + module

        for alias in node.names:
            name = alias.name.value
            local_name = alias.asname.name.value if alias.asname else name
            alias_str = alias.asname.name.value if alias.asname else None
            self.imports[local_name] = (full_module, name, alias_str, True)
        return False


class UnusedImportRemover(cst.CSTTransformer):
    """Removes unused imports from source code."""

    def __init__(self, used_names: set[str]):
        self.used_names = used_names
        self.removed_imports: list[str] = []

    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> Union[cst.ImportFrom, cst.RemovalSentinel]:
        if isinstance(updated_node.names, cst.ImportStar):
            return updated_node

        new_names = []
        for alias in updated_node.names:
            local_name = alias.asname.name.value if alias.asname else alias.name.value
            if local_name in self.used_names:
                new_names.append(alias)
            else:
                self.removed_imports.append(local_name)

        if not new_names:
            return cst.RemovalSentinel.REMOVE
        if len(new_names) != len(updated_node.names):
            return updated_node.with_changes(names=new_names)
        return updated_node

    def leave_Import(
        self, original_node: cst.Import, updated_node: cst.Import
    ) -> Union[cst.Import, cst.RemovalSentinel]:
        if isinstance(updated_node.names, cst.ImportStar):
            return updated_node

        new_names = []
        for alias in updated_node.names:
            if isinstance(alias.name, cst.Name):
                name = alias.name.value
            else:
                name = _get_dotted_name_str(alias.name)
            local_name = alias.asname.name.value if alias.asname else name.split(".")[0]
            if local_name in self.used_names:
                new_names.append(alias)
            else:
                self.removed_imports.append(local_name)

        if not new_names:
            return cst.RemovalSentinel.REMOVE
        if len(new_names) != len(updated_node.names):
            return updated_node.with_changes(names=new_names)
        return updated_node


def remove_unused_imports(source: str) -> tuple[str, list[str]]:
    """
    Remove imports that are not referenced in the code.

    Returns:
        Tuple of (modified_source, list of removed import names)
    """
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return source, []

    # Collect all names used in the code (excluding imports)
    used_collector = UsedNamesCollector()
    wrapper = MetadataWrapper(tree)
    wrapper.visit(used_collector)

    # Remove unused imports
    remover = UnusedImportRemover(used_collector.names)
    new_tree = tree.visit(remover)

    return new_tree.code, remover.removed_imports


def ensure_imports(
    source: str,
    imports: list[tuple[str, str, Optional[str], bool]],
) -> str:
    """
    Add imports to source if not already present.

    Args:
        source: The source code
        imports: List of (module, name, alias, is_from_import) tuples

    Returns:
        Modified source code with imports added
    """
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        # Fallback: just prepend imports
        lines = []
        for module, name, alias, is_from in imports:
            if is_from:
                line = f"from {module} import {name}"
                if alias:
                    line += f" as {alias}"
            else:
                line = f"import {module}"
                if alias:
                    line += f" as {alias}"
            lines.append(line)
        return "\n".join(lines) + "\n" + source

    # Collect existing imports
    existing_collector = ImportedNamesCollector()
    wrapper = MetadataWrapper(tree)
    wrapper.visit(existing_collector)

    # Filter out imports that already exist
    imports_to_add = []
    for module, name, alias, is_from in imports:
        local_name = alias if alias else (name if is_from else module.split(".")[0])
        if local_name not in existing_collector.imports:
            imports_to_add.append((module, name, alias, is_from))

    if not imports_to_add:
        return source

    # Add each import
    result = source
    for module, name, alias, is_from in imports_to_add:
        if is_from:
            result = add_import(result, module, name, alias)
        else:
            # For 'import x' style, use a different approach
            result = _add_plain_import(result, module, alias)

    return result


def _add_plain_import(source: str, module: str, alias: Optional[str] = None) -> str:
    """Add a plain 'import x' or 'import x as y' statement."""
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        import_line = f"import {module}" + (f" as {alias}" if alias else "")
        return import_line + "\n" + source

    # Create the import alias
    import_alias = cst.ImportAlias(
        name=_make_dotted_name(module),
        asname=cst.AsName(
            whitespace_before_as=cst.SimpleWhitespace(" "),
            whitespace_after_as=cst.SimpleWhitespace(" "),
            name=cst.Name(alias),
        ) if alias else None,
    )

    # Create the import statement
    import_stmt = cst.SimpleStatementLine(
        body=[cst.Import(names=[import_alias])]
    )

    # Find the right place to insert (after existing imports)
    insert_idx = 0
    for i, stmt in enumerate(tree.body):
        if isinstance(stmt, cst.SimpleStatementLine):
            for body_stmt in stmt.body:
                if isinstance(body_stmt, (cst.Import, cst.ImportFrom)):
                    insert_idx = i + 1

    new_body = list(tree.body)
    new_body.insert(insert_idx, import_stmt)
    new_tree = tree.with_changes(body=new_body)
    return new_tree.code
