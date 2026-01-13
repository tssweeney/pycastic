"""
Core rope refactoring operations.
"""
from pathlib import Path
from typing import Optional

from rope.base.project import Project
from rope.refactor.move import MoveModule, create_move
from rope.refactor.rename import Rename

from .errors import RefactoringError
from .parsing import TargetSpec, resolve_offset


def _get_resource(project: Project, file_path: Path) -> object:
    """Get a rope resource for a file path relative to project root."""
    # Ensure path is relative to project root
    path_str = str(file_path)
    if path_str.startswith("/"):
        # Convert absolute path to relative, resolving symlinks
        project_root = Path(project.root.real_path).resolve()
        resolved_path = Path(file_path).resolve()
        file_path = resolved_path.relative_to(project_root)
        path_str = str(file_path)
    return project.get_resource(path_str)


class RopeProject:
    """Context manager for rope project operations."""

    def __init__(self, project_root: Path, ropefolder: Optional[str] = ".ropeproject"):
        self.project_root = project_root
        self.ropefolder = ropefolder
        self.project: Optional[Project] = None

    def __enter__(self) -> Project:
        self.project = Project(str(self.project_root), ropefolder=self.ropefolder)
        return self.project

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.project:
            self.project.close()


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
        dry_run: If True, return changes without applying

    Returns:
        List of changed file paths
    """
    try:
        with RopeProject(project_root) as project:
            resource, offset = resolve_offset(project, target)

            renamer = Rename(project, resource, offset)
            changes = renamer.get_changes(new_name)

            if dry_run:
                return _describe_changes(changes)

            project.do(changes)
            return [str(r.path) for r in changes.get_changed_resources()]
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
        dry_run: If True, return changes without applying

    Returns:
        List of changed file paths
    """
    try:
        with RopeProject(project_root) as project:
            resource, offset = resolve_offset(project, target)

            mover = create_move(project, resource, offset)

            # Get destination resource
            dest_resource = _get_resource(project, destination_file)
            changes = mover.get_changes(dest_resource)

            if dry_run:
                return _describe_changes(changes)

            project.do(changes)
            return [str(r.path) for r in changes.get_changed_resources()]
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
        dry_run: If True, return changes without applying

    Returns:
        List of changed file paths
    """
    try:
        with RopeProject(project_root) as project:
            resource = _get_resource(project, file_path)

            # Use Rename with offset=None to rename the module itself
            renamer = Rename(project, resource, offset=None)
            changes = renamer.get_changes(new_name)

            if dry_run:
                return _describe_changes(changes)

            project.do(changes)
            return [str(r.path) for r in changes.get_changed_resources()]
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
        dry_run: If True, return changes without applying

    Returns:
        List of changed file paths
    """
    try:
        with RopeProject(project_root) as project:
            resource = _get_resource(project, file_path)
            dest_folder = _get_resource(project, destination_dir)

            mover = MoveModule(project, resource)
            changes = mover.get_changes(dest_folder)

            if dry_run:
                return _describe_changes(changes)

            project.do(changes)
            return [str(r.path) for r in changes.get_changed_resources()]
    except Exception as e:
        raise RefactoringError(f"Failed to move file: {e}") from e


def _describe_changes(changes) -> list[str]:
    """Get a description of pending changes."""
    descriptions = []
    description = changes.get_description()
    if description:
        descriptions.append(description)
    return descriptions
