"""
CLI interface for pycastic using typer.
"""
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .core import move_file, move_symbol, rename_file, rename_symbol
from .errors import AmbiguousSymbolError, CircularDependencyError, PycasticError
from .parsing import parse_target, SymbolByName, SymbolsByName

console = Console()


def _find_project_root(start_path: Path) -> Path:
    """Find project root by looking for pyproject.toml or .git directory."""
    current = start_path.resolve()
    if current.is_file():
        current = current.parent

    while current != current.parent:
        if (current / "pyproject.toml").exists() or (current / ".git").exists():
            return current
        current = current.parent

    # Fallback to current directory
    return Path.cwd()


def _is_symbol_spec(spec: str) -> bool:
    """Check if a spec refers to symbols (contains :: or line:col format)."""
    return "::" in spec or (spec.count(":") == 2 and spec.split(":")[1].isdigit())


def _parse_target_spec(spec: str) -> tuple[Path, Optional[str]]:
    """
    Parse a target specification into file path and optional symbol name.

    Returns:
        (file_path, symbol_name) - symbol_name is None for file-only specs
    """
    if "::" in spec:
        parts = spec.split("::", 1)
        return Path(parts[0]), parts[1]
    return Path(spec), None


def version_callback(value: bool):
    if value:
        console.print(f"pycastic version {__version__}")
        raise typer.Exit()


def main(
    source: Annotated[
        Optional[str],
        typer.Argument(
            help="Source: 'file.py::Symbol', 'file.py::Sym1,Sym2', or 'file.py'",
        ),
    ] = None,
    target: Annotated[
        Optional[str],
        typer.Argument(
            help="Target: 'file.py::NewName', 'dest.py', or 'new_dir/'",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show changes without applying them.",
        ),
    ] = False,
    root: Annotated[
        Optional[Path],
        typer.Option(
            "--root",
            "-r",
            help="Project root directory (auto-detected if not specified).",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = None,
    include_deps: Annotated[
        bool,
        typer.Option(
            "--include-deps",
            help="Include shared dependencies in symbol moves.",
        ),
    ] = False,
    use_shared_file: Annotated[
        bool,
        typer.Option(
            "--shared-file/--no-shared-file",
            help="Extract shared dependencies to a common file.",
        ),
    ] = False,
    shared_file_path: Annotated[
        Optional[Path],
        typer.Option(
            "--shared-file-path",
            help="Custom path for shared dependencies file.",
        ),
    ] = None,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
):
    """
    Move or rename Python symbols and files.

    Automatically detects the operation based on source and target:

    \b
    Symbol operations (source contains '::'):
      pycastic src/utils.py::old_func src/utils.py::new_func    # Rename symbol
      pycastic src/utils.py::helper dest.py                     # Move symbol
      pycastic src/utils.py::helper dest.py::new_name           # Move + rename
      pycastic src/utils.py::a,b,c dest.py                      # Move multiple

    \b
    File operations (source is a file path):
      pycastic src/old.py src/new.py                            # Rename file
      pycastic src/utils.py lib/utils.py                        # Move file
      pycastic src/utils.py lib/                                # Move to directory
    """
    # If no arguments, show help
    if source is None:
        ctx = typer.Context(typer.main.get_command(app))
        console.print(ctx.get_help())
        raise typer.Exit()

    if target is None:
        console.print("[red]Error:[/red] Target is required")
        raise typer.Exit(code=1)

    try:
        # Determine project root
        source_path = Path(source.split("::")[0] if "::" in source else source)
        project_root = root or _find_project_root(source_path)

        if _is_symbol_spec(source):
            # Symbol operation
            _handle_symbol_operation(
                project_root=project_root,
                source=source,
                target=target,
                dry_run=dry_run,
                include_deps=include_deps,
                use_shared_file=use_shared_file,
                shared_file_path=shared_file_path,
            )
        else:
            # File operation
            _handle_file_operation(
                project_root=project_root,
                source=source,
                target=target,
                dry_run=dry_run,
            )

    except AmbiguousSymbolError as e:
        console.print(f"[yellow]Ambiguous symbol:[/yellow] {e}")
        raise typer.Exit(code=1)
    except CircularDependencyError as e:
        console.print(f"[yellow]Shared dependency conflict:[/yellow]\n{e}")
        raise typer.Exit(code=1)
    except PycasticError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


def _handle_symbol_operation(
    project_root: Path,
    source: str,
    target: str,
    dry_run: bool,
    include_deps: bool,
    use_shared_file: bool,
    shared_file_path: Optional[Path],
) -> None:
    """Handle symbol rename/move operations."""
    parsed_source = parse_target(source)
    source_file = parsed_source.file_path
    target_file, target_symbol = _parse_target_spec(target)

    # Determine if this is a rename (same file) or move (different file)
    is_same_file = source_file == target_file or (
        target_symbol is not None and source_file == target_file
    )

    # Get source symbol name(s)
    if isinstance(parsed_source, SymbolsByName):
        source_symbols = parsed_source.symbol_names
    elif isinstance(parsed_source, SymbolByName):
        source_symbols = [parsed_source.symbol_name]
    else:
        # SymbolByPosition - we'll let the core handle it
        source_symbols = None

    if is_same_file or (target_symbol and not target_file.suffix):
        # Rename operation: same file with new symbol name
        if target_symbol is None:
            console.print("[red]Error:[/red] Target symbol name required for rename")
            raise typer.Exit(code=1)

        if source_symbols and len(source_symbols) > 1:
            console.print("[red]Error:[/red] Cannot rename multiple symbols at once")
            raise typer.Exit(code=1)

        changed_files, info_messages = rename_symbol(
            project_root, parsed_source, target_symbol, dry_run
        )

        _display_info_messages(info_messages)
        if dry_run:
            _display_dry_run(changed_files)
        else:
            console.print(f"[green]Successfully renamed to '{target_symbol}'[/green]")
            _display_changed_files(changed_files)
    else:
        # Move operation: different file
        # Resolve shared file path
        resolved_shared_file: Optional[Path] = None
        if shared_file_path is not None:
            resolved_shared_file = shared_file_path
        elif use_shared_file:
            resolved_shared_file = source_file.parent / f"{source_file.stem}_common.py"

        changed_files, info_messages = move_symbol(
            project_root,
            parsed_source,
            target_file,
            dry_run=dry_run,
            include_deps=include_deps,
            shared_file=resolved_shared_file,
        )

        _display_info_messages(info_messages)
        if dry_run:
            _display_dry_run(changed_files)
        else:
            console.print(f"[green]Successfully moved to '{target_file}'[/green]")
            _display_changed_files(changed_files)


def _handle_file_operation(
    project_root: Path,
    source: str,
    target: str,
    dry_run: bool,
) -> None:
    """Handle file rename/move operations."""
    source_path = Path(source)
    target_path = Path(target)

    # Determine operation type:
    # - If target ends with / or is a directory path without .py -> move to directory
    # - If target is in same directory -> rename
    # - Otherwise -> move (possibly with rename)

    is_directory_target = target.endswith("/") or (
        not target_path.suffix and "/" in target
    )

    if is_directory_target:
        # Move file to directory
        target_dir = target_path
        changed_files = move_file(project_root, source_path, target_dir, dry_run)

        if dry_run:
            _display_dry_run(changed_files)
        else:
            console.print(f"[green]Successfully moved to '{target_dir}'[/green]")
            _display_changed_files(changed_files)
    elif source_path.parent == target_path.parent:
        # Same directory -> rename
        new_name = target_path.stem
        changed_files = rename_file(project_root, source_path, new_name, dry_run)

        if dry_run:
            _display_dry_run(changed_files)
        else:
            console.print(f"[green]Successfully renamed to '{new_name}.py'[/green]")
            _display_changed_files(changed_files)
    else:
        # Different directory -> move (target is full path)
        # Extract directory and check if name changes
        target_dir = target_path.parent
        if target_path.stem != source_path.stem:
            # Move and rename - do move first, then rename
            changed_files = move_file(project_root, source_path, target_dir, dry_run)
            if not dry_run:
                # Also rename if the name is different
                moved_path = target_dir / source_path.name
                rename_file(project_root, moved_path, target_path.stem, dry_run)
        else:
            changed_files = move_file(project_root, source_path, target_dir, dry_run)

        if dry_run:
            _display_dry_run(changed_files)
        else:
            console.print(f"[green]Successfully moved to '{target_path}'[/green]")
            _display_changed_files(changed_files)


def _display_info_messages(info_messages: list[str]) -> None:
    """Display info messages."""
    for msg in info_messages:
        console.print(f"[dim]{msg}[/dim]")
    if info_messages:
        console.print()


def _display_dry_run(changed_files: list[str]) -> None:
    """Display dry run results."""
    console.print(
        Panel(
            "\n".join(changed_files) if changed_files else "No changes",
            title="[yellow]Dry Run - Proposed Changes[/yellow]",
        )
    )


def _display_changed_files(changed_files: list[str]) -> None:
    """Display list of changed files."""
    console.print(f"Changed {len(changed_files)} file(s):")
    for f in changed_files:
        console.print(f"  - {f}")


# Create the app with the main function
app = typer.Typer(
    name="pycastic",
    help="Python refactoring CLI tool powered by LibCST.",
    add_completion=False,
    no_args_is_help=True,
)
app.command()(main)


if __name__ == "__main__":
    app()
