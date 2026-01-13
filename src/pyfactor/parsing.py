"""
Module for parsing dual symbol specification formats:
- file.py::SymbolName (by name)
- file.py:line:column (by position)
"""
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from rope.base.project import Project

from .errors import SymbolNotFoundError, TargetParseError


@dataclass
class SymbolByName:
    """Represents a symbol specified by name."""

    file_path: Path
    symbol_name: str


@dataclass
class SymbolByPosition:
    """Represents a symbol specified by line:column position."""

    file_path: Path
    line: int
    column: int


TargetSpec = Union[SymbolByName, SymbolByPosition]

# Regex patterns
NAME_PATTERN = re.compile(r"^(.+\.py)::(\w+)$")
POSITION_PATTERN = re.compile(r"^(.+\.py):(\d+):(\d+)$")


def parse_target(target: str) -> TargetSpec:
    """
    Parse a target specification string into a structured object.

    Args:
        target: Either 'file.py::SymbolName' or 'file.py:line:column'

    Returns:
        SymbolByName or SymbolByPosition

    Raises:
        TargetParseError: If the target format is invalid
    """
    # Try name format first (file.py::SymbolName)
    name_match = NAME_PATTERN.match(target)
    if name_match:
        return SymbolByName(
            file_path=Path(name_match.group(1)), symbol_name=name_match.group(2)
        )

    # Try position format (file.py:line:column)
    pos_match = POSITION_PATTERN.match(target)
    if pos_match:
        return SymbolByPosition(
            file_path=Path(pos_match.group(1)),
            line=int(pos_match.group(2)),
            column=int(pos_match.group(3)),
        )

    raise TargetParseError(
        f"Invalid target format: '{target}'. "
        f"Use 'file.py::SymbolName' or 'file.py:line:column'"
    )


def resolve_offset(project: Project, spec: TargetSpec) -> tuple:
    """
    Resolve a target specification to a rope Resource and offset.

    Args:
        project: The rope Project instance
        spec: A parsed target specification

    Returns:
        Tuple of (resource, offset) for rope operations
    """
    # Use project.get_resource with path relative to project root
    path_str = str(spec.file_path)
    if path_str.startswith("/"):
        # Convert absolute path to relative
        project_root = Path(project.root.real_path)
        rel_path = Path(spec.file_path).relative_to(project_root)
        path_str = str(rel_path)
    resource = project.get_resource(path_str)

    if isinstance(spec, SymbolByPosition):
        # Convert line:column to character offset
        content = resource.read()
        lines = content.splitlines(keepends=True)
        offset = sum(len(lines[i]) for i in range(spec.line - 1))
        offset += spec.column - 1  # Column is 1-indexed
        return resource, offset

    elif isinstance(spec, SymbolByName):
        # Find symbol by name in the file
        content = resource.read()
        offset = find_symbol_offset(content, spec.symbol_name)
        return resource, offset

    raise TargetParseError(f"Unknown target specification type: {type(spec)}")


def find_symbol_offset(content: str, symbol_name: str) -> int:
    """
    Find the character offset of a symbol definition in file content.

    Looks for patterns like:
    - def symbol_name(
    - class symbol_name:
    - symbol_name =

    Args:
        content: The file content as a string
        symbol_name: The name of the symbol to find

    Returns:
        Character offset of the symbol name

    Raises:
        SymbolNotFoundError: If symbol is not found
    """
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol_name:
                # Calculate offset from line/col
                lines = content.splitlines(keepends=True)
                offset = sum(len(lines[i]) for i in range(node.lineno - 1))
                offset += node.col_offset
                # Adjust for 'def ', 'async def ', or 'class ' prefix to point at name
                if isinstance(node, ast.FunctionDef):
                    offset += 4  # 'def '
                elif isinstance(node, ast.AsyncFunctionDef):
                    offset += 10  # 'async def '
                elif isinstance(node, ast.ClassDef):
                    offset += 6  # 'class '
                return offset
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol_name:
                    lines = content.splitlines(keepends=True)
                    offset = sum(len(lines[i]) for i in range(target.lineno - 1))
                    offset += target.col_offset
                    return offset

    raise SymbolNotFoundError(f"Symbol '{symbol_name}' not found in file")
