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
from .parsing import parse_target

app = typer.Typer(
    name="pycastic",
    help="Python refactoring CLI tool powered by LibCST.",
    add_completion=False,
)
console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"pycastic version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
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
    """Python refactoring CLI tool powered by rope."""
    pass


@app.command()
def rename(
    project_root: Annotated[
        Path,
        typer.Argument(
            help="Path to the project root directory.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    target: Annotated[
        str,
        typer.Argument(
            help="Target symbol: 'file.py::SymbolName' or 'file.py:line:column'",
        ),
    ],
    new_name: Annotated[
        str,
        typer.Argument(
            help="New name for the symbol.",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show changes without applying them.",
        ),
    ] = False,
):
    """
    Rename a symbol (class, function, variable) across the codebase.

    Examples:
        pycastic rename . src/utils.py::old_function new_function
        pycastic rename /path/to/project src/module.py:10:5 new_name
    """
    try:
        parsed_target = parse_target(target)
        changed_files, info_messages = rename_symbol(project_root, parsed_target, new_name, dry_run)

        # Display info messages (e.g., warnings about other symbols with same name)
        for msg in info_messages:
            console.print(f"[dim]{msg}[/dim]")
        if info_messages:
            console.print()  # Blank line after info messages

        if dry_run:
            console.print(
                Panel(
                    "\n".join(changed_files) if changed_files else "No changes",
                    title="[yellow]Dry Run - Proposed Changes[/yellow]",
                )
            )
        else:
            console.print(f"[green]Successfully renamed to '{new_name}'[/green]")
            console.print(f"Changed {len(changed_files)} file(s):")
            for f in changed_files:
                console.print(f"  - {f}")

    except AmbiguousSymbolError as e:
        console.print(f"[yellow]Ambiguous symbol:[/yellow] {e}")
        raise typer.Exit(code=1)
    except PycasticError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def move(
    project_root: Annotated[
        Path,
        typer.Argument(
            help="Path to the project root directory.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    target: Annotated[
        str,
        typer.Argument(
            help="Target: 'file.py::Symbol', 'file.py::Sym1,Sym2', or 'file.py:line:col'",
        ),
    ],
    destination_file: Annotated[
        Path,
        typer.Argument(
            help="Destination file path (relative to project root).",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show changes without applying them.",
        ),
    ] = False,
    include_deps: Annotated[
        bool,
        typer.Option(
            "--include-deps",
            help="Include shared dependencies in the move (instead of erroring).",
        ),
    ] = False,
    use_shared_file: Annotated[
        bool,
        typer.Option(
            "--shared-file/--no-shared-file",
            help="Extract shared dependencies to a common file (default: {source}_common.py)",
        ),
    ] = False,
    shared_file_path: Annotated[
        Optional[Path],
        typer.Option(
            "--shared-file-path",
            help="Custom path for shared dependencies file (implies --shared-file)",
        ),
    ] = None,
):
    """
    Move symbol(s) from one file to another.

    Automatically handles dependencies:
    - External imports are copied to destination
    - Internal deps not used elsewhere are moved automatically
    - Shared deps (used by moved AND remaining code) require --include-deps or --shared-file

    Examples:
        pycastic move . src/utils.py::helper src/helpers.py
        pycastic move . src/utils.py::func1,func2 src/funcs.py
        pycastic move . src/utils.py::my_func dest.py --include-deps
        pycastic move . src/utils.py::my_func dest.py --shared-file
        pycastic move . src/utils.py::my_func dest.py --shared-file-path src/common.py
    """
    try:
        parsed_target = parse_target(target)

        # Determine shared file path
        resolved_shared_file: Optional[Path] = None
        if shared_file_path is not None:
            # Explicit path provided
            resolved_shared_file = shared_file_path
        elif use_shared_file:
            # Use default: {source}_common.py
            source_path = Path(parsed_target.file_path)
            resolved_shared_file = source_path.parent / f"{source_path.stem}_common.py"

        changed_files, info_messages = move_symbol(
            project_root,
            parsed_target,
            destination_file,
            dry_run=dry_run,
            include_deps=include_deps,
            shared_file=resolved_shared_file,
        )

        # Display info messages
        for msg in info_messages:
            console.print(f"[dim]{msg}[/dim]")
        if info_messages:
            console.print()

        if dry_run:
            console.print(
                Panel(
                    "\n".join(changed_files) if changed_files else "No changes",
                    title="[yellow]Dry Run - Proposed Changes[/yellow]",
                )
            )
        else:
            console.print(
                f"[green]Successfully moved symbol(s) to '{destination_file}'[/green]"
            )
            console.print(f"Changed {len(changed_files)} file(s):")
            for f in changed_files:
                console.print(f"  - {f}")

    except CircularDependencyError as e:
        console.print(f"[yellow]Shared dependency conflict:[/yellow]\n{e}")
        raise typer.Exit(code=1)
    except PycasticError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("rename-file")
def rename_file_cmd(
    project_root: Annotated[
        Path,
        typer.Argument(
            help="Path to the project root directory.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    file: Annotated[
        Path,
        typer.Argument(
            help="Path to the file to rename (relative to project root).",
        ),
    ],
    new_name: Annotated[
        str,
        typer.Argument(
            help="New name for the file (without .py extension).",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show changes without applying them.",
        ),
    ] = False,
):
    """
    Rename a Python file and update all imports.

    Examples:
        pycastic rename-file . src/old_name.py new_name
        pycastic rename-file /path/to/project lib/utils.py helpers
    """
    try:
        changed_files = rename_file(project_root, file, new_name, dry_run)

        if dry_run:
            console.print(
                Panel(
                    "\n".join(changed_files) if changed_files else "No changes",
                    title="[yellow]Dry Run - Proposed Changes[/yellow]",
                )
            )
        else:
            console.print(
                f"[green]Successfully renamed file to '{new_name}.py'[/green]"
            )
            console.print(f"Changed {len(changed_files)} file(s):")
            for f in changed_files:
                console.print(f"  - {f}")

    except PycasticError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("move-file")
def move_file_cmd(
    project_root: Annotated[
        Path,
        typer.Argument(
            help="Path to the project root directory.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    file: Annotated[
        Path,
        typer.Argument(
            help="Path to the file to move (relative to project root).",
        ),
    ],
    destination_dir: Annotated[
        Path,
        typer.Argument(
            help="Destination directory (relative to project root).",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show changes without applying them.",
        ),
    ] = False,
):
    """
    Move a Python file to a new location and update all imports.

    Examples:
        pycastic move-file . src/utils.py src/lib/
        pycastic move-file /path/to/project old/module.py new/subdir/
    """
    try:
        changed_files = move_file(project_root, file, destination_dir, dry_run)

        if dry_run:
            console.print(
                Panel(
                    "\n".join(changed_files) if changed_files else "No changes",
                    title="[yellow]Dry Run - Proposed Changes[/yellow]",
                )
            )
        else:
            console.print(
                f"[green]Successfully moved file to '{destination_dir}'[/green]"
            )
            console.print(f"Changed {len(changed_files)} file(s):")
            for f in changed_files:
                console.print(f"  - {f}")

    except PycasticError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
