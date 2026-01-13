"""
LibCST-based refactoring transformers.

Provides transformers for renaming symbols, updating imports, and
moving code between files.
"""
from pathlib import Path
from typing import Optional, Union

import libcst as cst
from libcst import matchers as m


class RenameTransformer(cst.CSTTransformer):
    """Transformer that renames occurrences of a symbol."""

    def __init__(self, old_name: str, new_name: str, rename_definitions: bool = True):
        self.old_name = old_name
        self.new_name = new_name
        self.rename_definitions = rename_definitions
        self.changes_made = 0

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        """Rename Name nodes."""
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

    def leave_ImportAlias(self, original_node: cst.ImportAlias, updated_node: cst.ImportAlias) -> cst.ImportAlias:
        """Rename imported names."""
        if isinstance(updated_node.name, cst.Name) and updated_node.name.value == self.old_name:
            self.changes_made += 1
            return updated_node.with_changes(
                name=cst.Name(self.new_name)
            )
        return updated_node


class ImportRenameTransformer(cst.CSTTransformer):
    """Transformer that updates import statements when a module or symbol is renamed."""

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

        # Update module name if needed
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
    """Create a Name or Attribute node from a dotted string."""
    parts = name.split(".")
    if len(parts) == 1:
        return cst.Name(parts[0])

    result = cst.Name(parts[0])
    for part in parts[1:]:
        result = cst.Attribute(value=result, attr=cst.Name(part))
    return result


def rename_in_source(source: str, old_name: str, new_name: str) -> tuple[str, int]:
    """
    Rename all occurrences of a symbol in source code.

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
    """Add an import statement to source code."""
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

    # Create the import statement
    import_stmt = cst.SimpleStatementLine(
        body=[
            cst.ImportFrom(
                module=_make_dotted_name(module),
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
