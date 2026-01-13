"""
Core refactoring operations using LibCST.
"""
import os
import shutil
from pathlib import Path
from typing import Optional

from .errors import RefactoringError, SymbolNotFoundError
from .parsing import SymbolByName, SymbolByPosition, TargetSpec
from .refactor import (
    add_definition,
    add_import,
    extract_definition,
    remove_definition,
    rename_attribute_in_source,
    rename_in_source,
    update_imports_in_source,
)
from .symbol_table import SymbolTable, _path_to_module


def _find_symbol_name_at_position(file_path: Path, line: int, column: int) -> str:
    """Find the symbol name at a given position in a file."""
    import libcst as cst

    source = file_path.read_text()
    lines = source.splitlines(keepends=True)

    # Calculate offset
    offset = sum(len(lines[i]) for i in range(line - 1)) + (column - 1)

    # Parse and find symbol at offset
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError as e:
        raise RefactoringError(f"Failed to parse {file_path}: {e}")

    # Find the token at the offset
    # Simple approach: find the identifier containing this offset
    code = source
    start = offset
    end = offset

    # Expand backwards to find start of identifier
    while start > 0 and (code[start - 1].isalnum() or code[start - 1] == "_"):
        start -= 1

    # Expand forwards to find end of identifier
    while end < len(code) and (code[end].isalnum() or code[end] == "_"):
        end += 1

    symbol_name = code[start:end]
    if not symbol_name or not (symbol_name[0].isalpha() or symbol_name[0] == "_"):
        raise SymbolNotFoundError(f"No symbol found at {file_path}:{line}:{column}")

    return symbol_name


def _resolve_target(project_root: Path, target: TargetSpec) -> tuple[Path, str]:
    """Resolve a target specification to a file path and symbol name."""
    if isinstance(target, SymbolByName):
        file_path = project_root / target.file_path
        return file_path, target.symbol_name
    elif isinstance(target, SymbolByPosition):
        file_path = project_root / target.file_path
        symbol_name = _find_symbol_name_at_position(file_path, target.line, target.column)
        return file_path, symbol_name
    else:
        raise RefactoringError(f"Unknown target type: {type(target)}")


def _get_python_files(project_root: Path) -> list[Path]:
    """Get all Python files in a project."""
    files = []
    for root, dirs, filenames in os.walk(project_root):
        # Skip hidden and virtual env directories
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", ".git", ".venv", "venv")]
        for filename in filenames:
            if filename.endswith(".py"):
                files.append(Path(root) / filename)
    return files


def rename_symbol(
    project_root: Path,
    target: TargetSpec,
    new_name: str,
    dry_run: bool = False,
) -> list[str]:
    """
    Rename a symbol across the codebase.

    Args:
        project_root: Path to the project root
        target: Parsed target specification
        new_name: The new name for the symbol
        dry_run: If True, return description without applying

    Returns:
        List of changed file paths (or descriptions if dry_run)
    """
    try:
        file_path, old_name = _resolve_target(project_root, target)

        if not file_path.exists():
            raise RefactoringError(f"File not found: {file_path}")

        # Build symbol table to find all references
        symbol_table = SymbolTable(project_root)
        symbol_table.build()

        # Find the definition
        rel_path = file_path.relative_to(project_root)
        definition = symbol_table.find_definition(file_path, old_name)
        if not definition:
            raise SymbolNotFoundError(f"Symbol '{old_name}' not found in {rel_path}")

        # Collect changes
        changes = {}
        module_name = _path_to_module(file_path, project_root)

        # Rename in the defining file
        source = file_path.read_text()
        new_source, count = rename_in_source(source, old_name, new_name)
        if count > 0:
            changes[file_path] = new_source

        # Find all files that import this symbol and update them
        for py_file in _get_python_files(project_root):
            if py_file == file_path:
                continue

            source = py_file.read_text()
            total_changes = 0

            # Update imports
            new_source, count = update_imports_in_source(
                source, old_name=old_name, new_name=new_name
            )
            total_changes += count

            # Update attribute accesses (module.symbol)
            file_module = _path_to_module(py_file, project_root)
            new_source, count = rename_attribute_in_source(
                new_source, module_name.split(".")[-1], old_name, new_name
            )
            total_changes += count

            # Update direct references if file imports the symbol
            file_symbols = symbol_table.files.get(py_file)
            if file_symbols:
                imports_symbol = False
                for imp in file_symbols.imports:
                    if imp.is_from_import:
                        for name, alias in imp.names:
                            if name == old_name or name == "*":
                                imports_symbol = True
                                break

                if imports_symbol:
                    new_source, count = rename_in_source(new_source, old_name, new_name)
                    total_changes += count

            if total_changes > 0 and new_source != source:
                changes[py_file] = new_source

        if dry_run:
            return _format_dry_run_changes(changes, project_root)

        # Apply changes
        for path, content in changes.items():
            path.write_text(content)

        return [str(p.relative_to(project_root)) for p in changes.keys()]

    except (SymbolNotFoundError, RefactoringError):
        raise
    except Exception as e:
        raise RefactoringError(f"Failed to rename symbol: {e}") from e


def move_symbol(
    project_root: Path,
    target: TargetSpec,
    destination_file: Path,
    dry_run: bool = False,
) -> list[str]:
    """
    Move a symbol to another file.

    Args:
        project_root: Path to the project root
        target: Parsed target specification
        destination_file: Path to the destination file (relative to project root)
        dry_run: If True, return description without applying

    Returns:
        List of changed file paths (or descriptions if dry_run)
    """
    try:
        source_file, symbol_name = _resolve_target(project_root, target)
        dest_file = project_root / destination_file

        if not source_file.exists():
            raise RefactoringError(f"Source file not found: {source_file}")
        if not dest_file.exists():
            raise RefactoringError(f"Destination file not found: {dest_file}")

        # Extract the definition
        source_content = source_file.read_text()
        definition_code = extract_definition(source_content, symbol_name)
        if not definition_code:
            raise SymbolNotFoundError(f"Symbol '{symbol_name}' not found in {source_file}")

        changes = {}

        # Remove from source file
        new_source, removed = remove_definition(source_content, symbol_name)
        if removed:
            changes[source_file] = new_source

        # Add to destination file
        dest_content = dest_file.read_text()
        new_dest = add_definition(dest_content, definition_code)
        changes[dest_file] = new_dest

        # Update imports in all files
        source_module = _path_to_module(source_file, project_root)
        dest_module = _path_to_module(dest_file, project_root)

        for py_file in _get_python_files(project_root):
            if py_file in (source_file, dest_file):
                continue

            content = py_file.read_text()
            new_content, count = update_imports_in_source(
                content,
                old_module=source_module,
                new_module=dest_module,
                old_name=symbol_name,
                new_name=symbol_name,
            )
            if count > 0 and new_content != content:
                changes[py_file] = new_content

        if dry_run:
            return _format_dry_run_changes(changes, project_root)

        # Apply changes
        for path, content in changes.items():
            path.write_text(content)

        return [str(p.relative_to(project_root)) for p in changes.keys()]

    except (SymbolNotFoundError, RefactoringError):
        raise
    except Exception as e:
        raise RefactoringError(f"Failed to move symbol: {e}") from e


def rename_file(
    project_root: Path,
    file_path: Path,
    new_name: str,
    dry_run: bool = False,
) -> list[str]:
    """
    Rename a Python file and update all imports.

    Args:
        project_root: Path to the project root
        file_path: Path to the file to rename (relative to project root)
        new_name: New name for the file (without .py extension)
        dry_run: If True, return description without applying

    Returns:
        List of changed file paths (or descriptions if dry_run)
    """
    try:
        old_file = project_root / file_path
        if not old_file.exists():
            raise RefactoringError(f"File not found: {old_file}")

        # Calculate new file path
        new_file = old_file.parent / f"{new_name}.py"

        # Get module names (full path and just the basename)
        old_module = _path_to_module(old_file, project_root)
        new_module = _path_to_module(new_file, project_root)
        old_basename = old_file.stem  # Just the filename without .py
        new_basename = new_name

        changes = {}

        # Update imports in all files
        for py_file in _get_python_files(project_root):
            if py_file == old_file:
                continue

            content = py_file.read_text()
            total_count = 0

            # Try full module path
            new_content, count = update_imports_in_source(
                content,
                old_module=old_module,
                new_module=new_module,
            )
            total_count += count

            # Also try just the basename (for relative imports like "from .errors import")
            new_content, count = update_imports_in_source(
                new_content,
                old_module=old_basename,
                new_module=new_basename,
            )
            total_count += count

            if total_count > 0 and new_content != content:
                changes[py_file] = new_content

        if dry_run:
            descriptions = _format_dry_run_changes(changes, project_root)
            descriptions.append(f"\nrename from {file_path}")
            descriptions.append(f"rename to {new_file.relative_to(project_root)}")
            return descriptions

        # Apply changes
        for path, content in changes.items():
            path.write_text(content)

        # Rename the file
        shutil.move(str(old_file), str(new_file))

        result = [str(p.relative_to(project_root)) for p in changes.keys()]
        result.append(str(new_file.relative_to(project_root)))
        return result

    except RefactoringError:
        raise
    except Exception as e:
        raise RefactoringError(f"Failed to rename file: {e}") from e


def move_file(
    project_root: Path,
    file_path: Path,
    destination_dir: Path,
    dry_run: bool = False,
) -> list[str]:
    """
    Move a Python file to a new location and update all imports.

    Args:
        project_root: Path to the project root
        file_path: Path to the file to move (relative to project root)
        destination_dir: Path to the destination directory
        dry_run: If True, return description without applying

    Returns:
        List of changed file paths (or descriptions if dry_run)
    """
    try:
        old_file = project_root / file_path
        dest_dir = project_root / destination_dir

        if not old_file.exists():
            raise RefactoringError(f"File not found: {old_file}")
        if not dest_dir.exists():
            raise RefactoringError(f"Destination directory not found: {dest_dir}")

        # Calculate new file path
        new_file = dest_dir / old_file.name

        # Get module names (full path and just the basename)
        old_module = _path_to_module(old_file, project_root)
        new_module = _path_to_module(new_file, project_root)
        old_basename = old_file.stem

        changes = {}

        # Update imports in all files
        for py_file in _get_python_files(project_root):
            if py_file == old_file:
                continue

            content = py_file.read_text()
            total_count = 0

            # Try full module path
            new_content, count = update_imports_in_source(
                content,
                old_module=old_module,
                new_module=new_module,
            )
            total_count += count

            # Also try just the basename (for relative imports)
            new_content, count = update_imports_in_source(
                new_content,
                old_module=old_basename,
                new_module=new_module,
            )
            total_count += count

            if total_count > 0 and new_content != content:
                changes[py_file] = new_content

        if dry_run:
            descriptions = _format_dry_run_changes(changes, project_root)
            descriptions.append(f"\nmove from {file_path}")
            descriptions.append(f"move to {new_file.relative_to(project_root)}")
            return descriptions

        # Apply changes
        for path, content in changes.items():
            path.write_text(content)

        # Move the file
        shutil.move(str(old_file), str(new_file))

        result = [str(p.relative_to(project_root)) for p in changes.keys()]
        result.append(str(new_file.relative_to(project_root)))
        return result

    except RefactoringError:
        raise
    except Exception as e:
        raise RefactoringError(f"Failed to move file: {e}") from e


def _format_dry_run_changes(changes: dict[Path, str], project_root: Path) -> list[str]:
    """Format changes for dry run output."""
    import difflib

    descriptions = []
    for path, new_content in changes.items():
        old_content = path.read_text()
        rel_path = path.relative_to(project_root)

        diff = difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        )
        diff_str = "".join(diff)
        if diff_str:
            descriptions.append(diff_str)

    return descriptions
