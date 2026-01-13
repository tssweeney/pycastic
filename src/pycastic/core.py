"""
Core refactoring operations using LibCST.
"""
import os
import shutil
from pathlib import Path
from typing import Optional

from .dependencies import DependencyAnalyzer, ImportDependency, resolve_move_dependencies
from .errors import (
    AmbiguousSymbolError,
    CircularDependencyError,
    RefactoringError,
    SymbolNotFoundError,
)
from .parsing import SymbolByName, SymbolByPosition, SymbolsByName, TargetSpec
from .refactor import (
    add_definition,
    add_import,
    ensure_imports,
    extract_definition,
    remove_definition,
    remove_unused_imports,
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


def _resolve_target(project_root: Path, target: TargetSpec) -> tuple[Path, list[str]]:
    """Resolve a target specification to a file path and list of symbol names."""
    if isinstance(target, SymbolByName):
        file_path = project_root / target.file_path
        return file_path, [target.symbol_name]
    elif isinstance(target, SymbolsByName):
        file_path = project_root / target.file_path
        return file_path, target.symbol_names
    elif isinstance(target, SymbolByPosition):
        file_path = project_root / target.file_path
        symbol_name = _find_symbol_name_at_position(file_path, target.line, target.column)
        return file_path, [symbol_name]
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


def _ensure_package_init_files(directory: Path, project_root: Path) -> list[Path]:
    """Create __init__.py files in directory and all parent directories up to project root.

    This ensures the directory structure is a valid Python package.

    Returns:
        List of created __init__.py file paths
    """
    created = []
    current = directory

    while current != project_root and current.is_relative_to(project_root):
        init_file = current / "__init__.py"
        if not init_file.exists():
            init_file.write_text('"""Package."""\n')
            created.append(init_file)
        current = current.parent

    return created


def rename_symbol(
    project_root: Path,
    target: TargetSpec,
    new_name: str,
    dry_run: bool = False,
) -> tuple[list[str], list[str]]:
    """
    Rename a symbol across the codebase.

    Args:
        project_root: Path to the project root
        target: Parsed target specification
        new_name: The new name for the symbol
        dry_run: If True, return description without applying

    Returns:
        Tuple of (list of changed file paths, list of info messages)
        Info messages include warnings about other symbols with the same name.
    """
    info_messages = []

    try:
        file_path, symbol_names = _resolve_target(project_root, target)

        # Rename only supports single symbol
        if len(symbol_names) > 1:
            raise RefactoringError("rename only supports a single symbol. Use file.py::SymbolName format.")
        old_name = symbol_names[0]

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

        # Check for multiple definitions with the same name
        all_definitions = symbol_table.find_all_definitions_by_name(old_name)

        # Check for multiple definitions in the same file
        same_file_defs = [d for d in all_definitions if d.location.file_path == file_path]
        if len(same_file_defs) > 1:
            # Multiple definitions in the same file - ambiguous
            match_info = []
            for d in same_file_defs:
                rel = d.location.file_path.relative_to(project_root)
                match_info.append(f"  {rel}:{d.location.line}:{d.location.column} ({d.symbol_type})")
            raise AmbiguousSymbolError(
                f"Multiple definitions of '{old_name}' found in {rel_path}. "
                f"Use line:column format to disambiguate:\n" + "\n".join(match_info),
                matches=same_file_defs
            )

        # Check for definitions in other files - info message only
        other_file_defs = [d for d in all_definitions if d.location.file_path != file_path]
        if other_file_defs:
            info_messages.append(f"Note: '{old_name}' is also defined in {len(other_file_defs)} other file(s):")
            for d in other_file_defs[:5]:  # Show max 5
                rel = d.location.file_path.relative_to(project_root)
                info_messages.append(f"  {rel}:{d.location.line} ({d.symbol_type})")
            if len(other_file_defs) > 5:
                info_messages.append(f"  ... and {len(other_file_defs) - 5} more")

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
            return _format_dry_run_changes(changes, project_root), info_messages

        # Apply changes
        for path, content in changes.items():
            path.write_text(content)

        return [str(p.relative_to(project_root)) for p in changes.keys()], info_messages

    except (SymbolNotFoundError, RefactoringError, AmbiguousSymbolError):
        raise
    except Exception as e:
        raise RefactoringError(f"Failed to rename symbol: {e}") from e


def move_symbol(
    project_root: Path,
    target: TargetSpec,
    destination_file: Path,
    dry_run: bool = False,
    include_deps: bool = False,
    shared_file: Optional[Path] = None,
) -> tuple[list[str], list[str]]:
    """
    Move symbol(s) to another file with full dependency handling.

    Args:
        project_root: Path to the project root
        target: Parsed target specification (single or multiple symbols)
        destination_file: Path to the destination file (relative to project root)
        dry_run: If True, return description without applying
        include_deps: If True, include shared dependencies in the move
        shared_file: If set, extract shared dependencies to this file

    Returns:
        Tuple of (list of changed file paths, list of info messages)

    Raises:
        CircularDependencyError: When shared dependencies exist and neither
            include_deps nor shared_file is specified
    """
    info_messages = []

    try:
        source_file, initial_symbols = _resolve_target(project_root, target)
        dest_file = project_root / destination_file

        if not source_file.exists():
            raise RefactoringError(f"Source file not found: {source_file}")

        # Resolve dependencies
        final_move_list, shared_deps, required_imports = resolve_move_dependencies(
            source_file, initial_symbols, include_shared_deps=include_deps
        )

        # Handle shared dependencies - use shared_file by default
        if shared_deps and not include_deps and not shared_file:
            # Auto-generate default shared file path
            default_shared = source_file.parent / f"{source_file.stem}_common.py"
            shared_file = default_shared.relative_to(project_root)
            info_messages.append(
                f"Auto-extracting shared dependencies to: {shared_file}\n"
                f"  Shared symbols: {', '.join(shared_deps)}\n"
                f"  Use --include-deps to move them instead"
            )

        # Log what we're moving
        auto_included = set(final_move_list) - set(initial_symbols)
        if auto_included:
            info_messages.append(f"Auto-including dependencies: {', '.join(auto_included)}")

        # Create destination file if it doesn't exist
        if not dest_file.exists():
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            _ensure_package_init_files(dest_file.parent, project_root)
            dest_file.write_text(f'"""{dest_file.stem} module."""\n')

        # Handle shared file if specified
        shared_file_path = None
        if shared_file and shared_deps:
            shared_file_path = project_root / shared_file
            if not shared_file_path.exists():
                shared_file_path.parent.mkdir(parents=True, exist_ok=True)
                _ensure_package_init_files(shared_file_path.parent, project_root)
                shared_file_path.write_text(f'"""{shared_file_path.stem} module."""\n')
            info_messages.append(f"Extracting shared deps to: {shared_file}")

        changes = {}
        source_content = source_file.read_text()
        analyzer = DependencyAnalyzer(source_file)

        # --- Move shared dependencies first (if --shared-file) ---
        if shared_file_path and shared_deps:
            shared_content = shared_file_path.read_text()
            for sym in shared_deps:
                code = analyzer.get_symbol_code(sym)
                shared_content = add_definition(shared_content, code)
                source_content, _ = remove_definition(source_content, sym)

            # Add imports needed by shared deps
            shared_required = []
            for sym in shared_deps:
                deps = analyzer.analyze_symbol(sym)
                for imp in deps.required_imports:
                    shared_required.append((imp.module, imp.name, imp.alias, imp.is_from_import))
            if shared_required:
                shared_content = ensure_imports(shared_content, shared_required)

            changes[shared_file_path] = shared_content

        # --- Extract and move main symbols ---
        dest_content = dest_file.read_text()
        moved_symbols = []

        for symbol_name in final_move_list:
            try:
                code = analyzer.get_symbol_code(symbol_name)
            except ValueError:
                # Symbol might have been moved to shared file
                continue

            dest_content = add_definition(dest_content, code)
            source_content, removed = remove_definition(source_content, symbol_name)
            if removed:
                moved_symbols.append(symbol_name)

        # Add required imports to destination
        imports_to_add = []
        for imp in required_imports:
            imports_to_add.append((imp.module, imp.name, imp.alias, imp.is_from_import))

        # Also add imports for shared deps if they were extracted
        if shared_file_path and shared_deps:
            shared_module = _path_to_module(shared_file_path, project_root)
            for sym in shared_deps:
                imports_to_add.append((shared_module, sym, None, True))

        if imports_to_add:
            dest_content = ensure_imports(dest_content, imports_to_add)

        changes[dest_file] = dest_content

        # --- Update source file ---
        # Remove unused imports from source
        source_content, removed_imports = remove_unused_imports(source_content)
        if removed_imports:
            info_messages.append(f"Removed unused imports from source: {', '.join(removed_imports)}")

        # Check if source still uses any moved symbols - add imports if so
        source_needs_imports = []
        dest_module = _path_to_module(dest_file, project_root)

        # Simple check: scan source for moved symbol names
        for sym in moved_symbols:
            if sym in source_content:
                source_needs_imports.append((dest_module, sym, None, True))

        # Also add imports for shared deps that were extracted to shared file
        if shared_file_path and shared_deps:
            shared_module = _path_to_module(shared_file_path, project_root)
            for sym in shared_deps:
                if sym in source_content:
                    source_needs_imports.append((shared_module, sym, None, True))

        if source_needs_imports:
            source_content = ensure_imports(source_content, source_needs_imports)
            info_messages.append(f"Added imports to source for: {', '.join(s[1] for s in source_needs_imports)}")

        changes[source_file] = source_content

        # --- Update imports in all other files ---
        source_module = _path_to_module(source_file, project_root)

        for py_file in _get_python_files(project_root):
            if py_file in changes:
                continue

            content = py_file.read_text()
            original_content = content
            total_changes = 0

            # Update imports for each moved symbol
            for sym in moved_symbols:
                content, count = update_imports_in_source(
                    content,
                    old_module=source_module,
                    new_module=dest_module,
                    old_name=sym,
                    new_name=sym,
                )
                total_changes += count

            # Update imports for shared deps if extracted
            if shared_file_path and shared_deps:
                shared_module = _path_to_module(shared_file_path, project_root)
                for sym in shared_deps:
                    content, count = update_imports_in_source(
                        content,
                        old_module=source_module,
                        new_module=shared_module,
                        old_name=sym,
                        new_name=sym,
                    )
                    total_changes += count

            if total_changes > 0 and content != original_content:
                changes[py_file] = content

        if dry_run:
            return _format_dry_run_changes(changes, project_root), info_messages

        # Apply changes
        for path, content in changes.items():
            path.write_text(content)

        return [str(p.relative_to(project_root)) for p in changes.keys()], info_messages

    except (SymbolNotFoundError, RefactoringError, CircularDependencyError):
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

        # Create destination directory if it doesn't exist
        if not dest_dir.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)
            # Create __init__.py files for Python package structure
            _ensure_package_init_files(dest_dir, project_root)

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
