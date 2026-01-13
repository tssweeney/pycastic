"""
CLI interface for pyfactor using typer.
"""
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .core import move_file, move_symbol, rename_file, rename_symbol
from .errors import PyfactorError
from .parsing import parse_target

app = typer.Typer(
    name="pyfactor",
    help="Python refactoring CLI tool powered by LibCST.",
    add_completion=False,
)
console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"pyfactor version {__version__}")
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
        pyfactor rename . src/utils.py::old_function new_function
        pyfactor rename /path/to/project src/module.py:10:5 new_name
    """
    try:
        parsed_target = parse_target(target)
        changed_files = rename_symbol(project_root, parsed_target, new_name, dry_run)

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

    except PyfactorError as e:
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
            help="Target symbol: 'file.py::SymbolName' or 'file.py:line:column'",
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
):
    """
    Move a symbol from one file to another.

    Examples:
        pyfactor move . src/old_module.py::MyClass src/new_module.py
        pyfactor move /path/to/project lib/utils.py:25:0 lib/helpers.py
    """
    try:
        parsed_target = parse_target(target)
        changed_files = move_symbol(
            project_root, parsed_target, destination_file, dry_run
        )

        if dry_run:
            console.print(
                Panel(
                    "\n".join(changed_files) if changed_files else "No changes",
                    title="[yellow]Dry Run - Proposed Changes[/yellow]",
                )
            )
        else:
            console.print(
                f"[green]Successfully moved symbol to '{destination_file}'[/green]"
            )
            console.print(f"Changed {len(changed_files)} file(s):")
            for f in changed_files:
                console.print(f"  - {f}")

    except PyfactorError as e:
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
        pyfactor rename-file . src/old_name.py new_name
        pyfactor rename-file /path/to/project lib/utils.py helpers
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

    except PyfactorError as e:
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
        pyfactor move-file . src/utils.py src/lib/
        pyfactor move-file /path/to/project old/module.py new/subdir/
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

    except PyfactorError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
