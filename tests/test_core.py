"""Tests for the core module."""
from pathlib import Path

import pytest

from pyfactor.core import (
    RopeProject,
    _get_resource,
    move_file,
    move_symbol,
    rename_file,
    rename_symbol,
)
from pyfactor.errors import RefactoringError
from pyfactor.parsing import parse_target


class TestRopeProject:
    """Tests for RopeProject context manager."""

    def test_context_manager_opens_project(self, simple_project):
        """Test that RopeProject opens a project."""
        with RopeProject(simple_project) as project:
            assert project is not None
            assert project.root is not None

    def test_context_manager_closes_project(self, simple_project):
        """Test that RopeProject closes the project on exit."""
        rope_project = RopeProject(simple_project)
        with rope_project as project:
            assert project is not None
        # Project should be closed after exit
        assert rope_project.project is not None


class TestRenameSymbol:
    """Tests for rename_symbol function."""

    def test_rename_function_dry_run(self, simple_project):
        """Test renaming a function with dry run."""
        target = parse_target("example.py::old_name")
        result = rename_symbol(simple_project, target, "new_name", dry_run=True)
        assert len(result) > 0
        assert "old_name" in result[0]
        assert "new_name" in result[0]

    def test_rename_function(self, simple_project):
        """Test actually renaming a function."""
        target = parse_target("example.py::old_name")
        result = rename_symbol(simple_project, target, "new_name", dry_run=False)
        assert "example.py" in result

        # Verify the file was changed
        content = (simple_project / "example.py").read_text()
        assert "def new_name():" in content
        assert "def old_name():" not in content

    def test_rename_class(self, simple_project):
        """Test renaming a class."""
        target = parse_target("example.py::OldClass")
        result = rename_symbol(simple_project, target, "NewClass", dry_run=False)
        assert "example.py" in result

        content = (simple_project / "example.py").read_text()
        assert "class NewClass:" in content
        assert "class OldClass:" not in content

    def test_rename_with_line_column(self, simple_project):
        """Test renaming using line:column format."""
        # Find the line number of old_name function
        content = (simple_project / "example.py").read_text()
        lines = content.splitlines()
        line_num = None
        for i, line in enumerate(lines, 1):
            if "def old_name" in line:
                line_num = i
                break
        assert line_num is not None

        # Column 5 is where 'old_name' starts (after 'def ', 1-indexed)
        target = parse_target(f"example.py:{line_num}:5")
        result = rename_symbol(simple_project, target, "renamed_func", dry_run=False)

        content = (simple_project / "example.py").read_text()
        assert "def renamed_func():" in content

    def test_rename_updates_references(self, temp_project):
        """Test that renaming updates all references."""
        target = parse_target("utils.py::helper_function")
        result = rename_symbol(temp_project, target, "helper", dry_run=False)

        # Should update both utils.py and main.py
        assert any("utils.py" in f for f in result)

        # Check main.py still imports correctly
        main_content = (temp_project / "main.py").read_text()
        assert "helper" in main_content


class TestRenameFile:
    """Tests for rename_file function."""

    def test_rename_file_dry_run(self, simple_project):
        """Test renaming a file with dry run."""
        result = rename_file(
            simple_project, Path("example.py"), "renamed", dry_run=True
        )
        assert len(result) > 0

    def test_rename_file(self, simple_project):
        """Test actually renaming a file."""
        result = rename_file(
            simple_project, Path("example.py"), "renamed", dry_run=False
        )

        # Old file should not exist, new file should
        assert not (simple_project / "example.py").exists()
        assert (simple_project / "renamed.py").exists()

    def test_rename_file_updates_imports(self, temp_project):
        """Test that renaming a file updates imports."""
        result = rename_file(temp_project, Path("utils.py"), "helpers", dry_run=False)

        # Check that main.py imports from helpers now
        main_content = (temp_project / "main.py").read_text()
        assert "from helpers import" in main_content or "import helpers" in main_content


class TestMoveSymbol:
    """Tests for move_symbol function."""

    def test_move_function_dry_run(self, temp_project):
        """Test moving a function with dry run."""
        target = parse_target("utils.py::helper_function")
        result = move_symbol(
            temp_project, target, Path("main.py"), dry_run=True
        )
        assert len(result) > 0

    def test_move_function(self, temp_project):
        """Test actually moving a function."""
        target = parse_target("utils.py::helper_function")
        result = move_symbol(
            temp_project, target, Path("main.py"), dry_run=False
        )

        # Function should be in main.py now
        main_content = (temp_project / "main.py").read_text()
        assert "def helper_function" in main_content


class TestMoveFile:
    """Tests for move_file function."""

    def test_move_file_dry_run(self, temp_project):
        """Test moving a file with dry run."""
        result = move_file(
            temp_project, Path("utils.py"), Path("subpkg"), dry_run=True
        )
        assert len(result) > 0

    def test_move_file(self, temp_project):
        """Test actually moving a file."""
        result = move_file(
            temp_project, Path("utils.py"), Path("subpkg"), dry_run=False
        )

        # File should be in subpkg now
        assert not (temp_project / "utils.py").exists()
        assert (temp_project / "subpkg" / "utils.py").exists()


class TestGetResource:
    """Tests for _get_resource helper."""

    def test_get_resource_relative_path(self, simple_project):
        """Test getting resource with relative path."""
        with RopeProject(simple_project) as project:
            resource = _get_resource(project, Path("example.py"))
            assert resource is not None
            assert resource.exists()

    def test_get_resource_absolute_path(self, simple_project):
        """Test getting resource with absolute path."""
        with RopeProject(simple_project) as project:
            abs_path = simple_project / "example.py"
            resource = _get_resource(project, abs_path)
            assert resource is not None
            assert resource.exists()

    def test_get_resource_nonexistent_raises(self, simple_project):
        """Test that nonexistent file raises."""
        with RopeProject(simple_project) as project:
            with pytest.raises(Exception):
                _get_resource(project, Path("nonexistent.py"))
