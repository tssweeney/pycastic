"""Tests for the core module."""
from pathlib import Path

import pytest

from pyfactor.core import (
    move_file,
    move_symbol,
    rename_file,
    rename_symbol,
)
from pyfactor.errors import RefactoringError, SymbolNotFoundError
from pyfactor.parsing import parse_target


class TestRenameSymbol:
    """Tests for rename_symbol function."""

    def test_rename_function_dry_run(self, simple_project):
        """Test renaming a function with dry run."""
        target = parse_target("example.py::old_name")
        result, info_messages = rename_symbol(simple_project, target, "new_name", dry_run=True)
        assert len(result) > 0
        assert "old_name" in result[0]
        assert "new_name" in result[0]

    def test_rename_function(self, simple_project):
        """Test actually renaming a function."""
        target = parse_target("example.py::old_name")
        result, info_messages = rename_symbol(simple_project, target, "new_name", dry_run=False)
        assert "example.py" in result

        # Verify the file was changed
        content = (simple_project / "example.py").read_text()
        assert "def new_name():" in content
        assert "def old_name():" not in content

    def test_rename_class(self, simple_project):
        """Test renaming a class."""
        target = parse_target("example.py::OldClass")
        result, info_messages = rename_symbol(simple_project, target, "NewClass", dry_run=False)
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
        result, info_messages = rename_symbol(simple_project, target, "renamed_func", dry_run=False)

        content = (simple_project / "example.py").read_text()
        assert "def renamed_func():" in content

    def test_rename_updates_references(self, temp_project):
        """Test that renaming updates all references."""
        target = parse_target("utils.py::helper_function")
        result, info_messages = rename_symbol(temp_project, target, "helper", dry_run=False)

        # Should update utils.py
        assert any("utils.py" in f for f in result)

        # Check utils.py was updated
        utils_content = (temp_project / "utils.py").read_text()
        assert "def helper(" in utils_content


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
        result, info_messages = move_symbol(
            temp_project, target, Path("main.py"), dry_run=True
        )
        assert len(result) > 0

    def test_move_function(self, temp_project):
        """Test actually moving a function."""
        target = parse_target("utils.py::helper_function")
        result, info_messages = move_symbol(
            temp_project, target, Path("main.py"), dry_run=False
        )

        # Function should be in main.py now
        main_content = (temp_project / "main.py").read_text()
        assert "def helper_function" in main_content

        # Function should be removed from utils.py
        utils_content = (temp_project / "utils.py").read_text()
        assert "def helper_function" not in utils_content


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


class TestErrorHandling:
    """Tests for error handling."""

    def test_rename_nonexistent_file(self, simple_project):
        """Test renaming in a nonexistent file."""
        target = parse_target("nonexistent.py::symbol")
        with pytest.raises(RefactoringError):
            rename_symbol(simple_project, target, "new_name")

    def test_rename_nonexistent_symbol(self, simple_project):
        """Test renaming a nonexistent symbol."""
        target = parse_target("example.py::nonexistent")
        with pytest.raises(SymbolNotFoundError):
            rename_symbol(simple_project, target, "new_name")


class TestAutoCreateDestination:
    """Tests for automatic creation of destination files/directories."""

    def test_move_file_creates_destination_dir(self, tmp_path):
        """Test that move_file creates destination directory if it doesn't exist."""
        # Create source file
        (tmp_path / "source.py").write_text("""
def my_func():
    return 42
""")

        # Move to non-existent directory
        result = move_file(tmp_path, Path("source.py"), Path("new_pkg/subpkg"), dry_run=False)

        # Verify directory was created
        assert (tmp_path / "new_pkg" / "subpkg").exists()
        assert (tmp_path / "new_pkg" / "subpkg" / "source.py").exists()

        # Verify __init__.py files were created for package structure
        assert (tmp_path / "new_pkg" / "__init__.py").exists()
        assert (tmp_path / "new_pkg" / "subpkg" / "__init__.py").exists()

    def test_move_symbol_creates_destination_file(self, tmp_path):
        """Test that move_symbol creates destination file if it doesn't exist."""
        # Create source file with a function
        (tmp_path / "source.py").write_text("""
def helper():
    return 42

def other():
    return 1
""")

        target = parse_target("source.py::helper")
        result, info_messages = move_symbol(tmp_path, target, Path("new_module.py"), dry_run=False)

        # Verify destination file was created
        assert (tmp_path / "new_module.py").exists()

        # Verify function was moved
        dest_content = (tmp_path / "new_module.py").read_text()
        assert "def helper" in dest_content

        # Verify function was removed from source
        source_content = (tmp_path / "source.py").read_text()
        assert "def helper" not in source_content
        assert "def other" in source_content

    def test_move_symbol_creates_nested_destination(self, tmp_path):
        """Test that move_symbol creates nested directories for destination file."""
        # Create source file
        (tmp_path / "source.py").write_text("""
def my_func():
    return 42
""")

        target = parse_target("source.py::my_func")
        result, info_messages = move_symbol(tmp_path, target, Path("pkg/subpkg/dest.py"), dry_run=False)

        # Verify nested structure was created
        assert (tmp_path / "pkg" / "subpkg" / "dest.py").exists()
        assert (tmp_path / "pkg" / "__init__.py").exists()
        assert (tmp_path / "pkg" / "subpkg" / "__init__.py").exists()

        # Verify function was moved
        dest_content = (tmp_path / "pkg" / "subpkg" / "dest.py").read_text()
        assert "def my_func" in dest_content


class TestDisambiguation:
    """Tests for symbol disambiguation."""

    def test_multiple_definitions_same_file_raises_error(self, tmp_path):
        """Test that multiple definitions of same name in same file raises AmbiguousSymbolError."""
        from pyfactor.errors import AmbiguousSymbolError

        # Create a file with two functions of the same name (in nested scopes)
        # This is a contrived example - in reality, you'd have module-level duplicates
        (tmp_path / "dupes.py").write_text("""
x = 1
x = 2  # Second assignment of x
""")

        target = parse_target("dupes.py::x")
        with pytest.raises(AmbiguousSymbolError) as exc_info:
            rename_symbol(tmp_path, target, "new_x")

        assert "Multiple definitions" in str(exc_info.value)
        assert "x" in str(exc_info.value)

    def test_info_message_for_other_file_definitions(self, tmp_path):
        """Test that info message is shown when symbol exists in other files."""
        # Create multiple files with same symbol name
        (tmp_path / "file1.py").write_text("""
def helper():
    return 1
""")
        (tmp_path / "file2.py").write_text("""
def helper():
    return 2
""")

        target = parse_target("file1.py::helper")
        result, info_messages = rename_symbol(tmp_path, target, "new_helper", dry_run=True)

        # Should have info messages about symbol in other files
        assert len(info_messages) > 0
        assert any("also defined" in msg for msg in info_messages)
        assert any("file2.py" in msg for msg in info_messages)


class TestMoveSymbolDependencies:
    """Tests for move_symbol dependency handling."""

    def test_move_updates_imports_in_using_files(self, tmp_path):
        """Files that import the moved symbol get updated imports."""
        # Create source file with a function
        (tmp_path / "utils.py").write_text('''"""Utils module."""


def helper():
    return 42
''')

        # Create a file that imports helper
        (tmp_path / "main.py").write_text('''"""Main module."""
from utils import helper


def run():
    return helper()
''')

        # Move helper to new file
        target = parse_target("utils.py::helper")
        result, info = move_symbol(tmp_path, target, Path("helpers.py"), dry_run=False)

        # Check main.py now imports from helpers
        main_content = (tmp_path / "main.py").read_text()
        assert "from helpers import helper" in main_content
        assert "from utils import helper" not in main_content

    def test_move_copies_required_imports(self, tmp_path):
        """Imports used by moved symbol are copied to destination."""
        # Create source file with a function that uses datetime
        (tmp_path / "utils.py").write_text('''"""Utils module."""
from datetime import datetime


def get_timestamp():
    return datetime.now()


def other_func():
    return 42
''')

        # Move get_timestamp to new file
        target = parse_target("utils.py::get_timestamp")
        result, info = move_symbol(tmp_path, target, Path("timestamps.py"), dry_run=False)

        # Check destination has the import
        dest_content = (tmp_path / "timestamps.py").read_text()
        assert "from datetime import datetime" in dest_content
        assert "def get_timestamp" in dest_content

    def test_move_includes_unused_internal_deps(self, tmp_path):
        """Internal dependencies not used elsewhere are moved too."""
        # Create source file where main_func depends on helper (unused elsewhere)
        (tmp_path / "utils.py").write_text('''"""Utils module."""


def internal_helper():
    return 42


def main_func():
    return internal_helper() + 1


def other_func():
    return 100
''')

        # Move main_func - should also move internal_helper
        target = parse_target("utils.py::main_func")
        result, info = move_symbol(tmp_path, target, Path("funcs.py"), dry_run=False)

        # Check both were moved to destination
        dest_content = (tmp_path / "funcs.py").read_text()
        assert "def main_func" in dest_content
        assert "def internal_helper" in dest_content

        # Check both were removed from source
        source_content = (tmp_path / "utils.py").read_text()
        assert "def main_func" not in source_content
        assert "def internal_helper" not in source_content
        assert "def other_func" in source_content  # This should remain

    def test_move_raises_on_shared_internal_deps(self, tmp_path):
        """Shared internal dependencies raise CircularDependencyError."""
        from pyfactor.errors import CircularDependencyError

        # Create source file where shared_helper is used by both func_a and func_b
        (tmp_path / "utils.py").write_text('''"""Utils module."""


def shared_helper():
    return 42


def func_a():
    return shared_helper() + 1


def func_b():
    return shared_helper() + 2
''')

        # Try to move func_a - should fail because shared_helper is used by func_b too
        target = parse_target("utils.py::func_a")
        with pytest.raises(CircularDependencyError) as exc_info:
            move_symbol(tmp_path, target, Path("dest.py"), dry_run=False)

        assert "shared_helper" in str(exc_info.value)

    def test_move_with_include_deps_flag(self, tmp_path):
        """--include-deps moves shared dependencies anyway."""
        # Create source file with shared dependency
        (tmp_path / "utils.py").write_text('''"""Utils module."""


def shared_helper():
    return 42


def func_a():
    return shared_helper() + 1


def func_b():
    return shared_helper() + 2
''')

        # Move func_a with include_deps=True
        target = parse_target("utils.py::func_a")
        result, info = move_symbol(
            tmp_path, target, Path("dest.py"), dry_run=False, include_deps=True
        )

        # Both func_a and shared_helper should be in destination
        dest_content = (tmp_path / "dest.py").read_text()
        assert "def func_a" in dest_content
        assert "def shared_helper" in dest_content

        # func_b should still be in source, and it should import shared_helper
        source_content = (tmp_path / "utils.py").read_text()
        assert "def func_b" in source_content
        assert "def shared_helper" not in source_content
        assert "from dest import shared_helper" in source_content

    def test_move_with_shared_file_option(self, tmp_path):
        """--shared-file extracts shared deps to common file."""
        # Create source file with shared dependency
        (tmp_path / "utils.py").write_text('''"""Utils module."""


def shared_helper():
    return 42


def func_a():
    return shared_helper() + 1


def func_b():
    return shared_helper() + 2
''')

        # Move func_a with shared_file option
        target = parse_target("utils.py::func_a")
        result, info = move_symbol(
            tmp_path, target, Path("dest.py"), dry_run=False, shared_file=Path("common.py")
        )

        # func_a should be in dest.py
        dest_content = (tmp_path / "dest.py").read_text()
        assert "def func_a" in dest_content
        assert "from common import shared_helper" in dest_content

        # shared_helper should be in common.py
        common_content = (tmp_path / "common.py").read_text()
        assert "def shared_helper" in common_content

        # func_b should still be in source, importing from common
        source_content = (tmp_path / "utils.py").read_text()
        assert "def func_b" in source_content
        assert "from common import shared_helper" in source_content

    def test_move_multiple_symbols(self, tmp_path):
        """Moving multiple symbols at once works correctly."""
        # Create source file with multiple functions
        (tmp_path / "utils.py").write_text('''"""Utils module."""


def func_one():
    return 1


def func_two():
    return 2


def func_three():
    return 3
''')

        # Move two functions at once
        target = parse_target("utils.py::func_one,func_two")
        result, info = move_symbol(tmp_path, target, Path("dest.py"), dry_run=False)

        # Both should be in destination
        dest_content = (tmp_path / "dest.py").read_text()
        assert "def func_one" in dest_content
        assert "def func_two" in dest_content

        # Both should be removed from source
        source_content = (tmp_path / "utils.py").read_text()
        assert "def func_one" not in source_content
        assert "def func_two" not in source_content
        assert "def func_three" in source_content  # This should remain

    def test_move_removes_unused_imports_from_original(self, tmp_path):
        """Unused imports are removed from original file after move."""
        # Create source file with function using datetime
        (tmp_path / "utils.py").write_text('''"""Utils module."""
from datetime import datetime


def get_timestamp():
    return datetime.now()


def other_func():
    return 42
''')

        # Move get_timestamp (only user of datetime)
        target = parse_target("utils.py::get_timestamp")
        result, info = move_symbol(tmp_path, target, Path("timestamps.py"), dry_run=False)

        # datetime import should be removed from source
        source_content = (tmp_path / "utils.py").read_text()
        assert "from datetime import datetime" not in source_content
        assert "def other_func" in source_content

        # datetime import should be in destination
        dest_content = (tmp_path / "timestamps.py").read_text()
        assert "from datetime import datetime" in dest_content

    def test_move_adds_import_to_original_if_needed(self, tmp_path):
        """If original file still uses moved symbol, add import."""
        # Create source file where other_func calls moved_func
        (tmp_path / "utils.py").write_text('''"""Utils module."""


def moved_func():
    return 42


def other_func():
    return moved_func() + 1
''')

        # Move moved_func
        target = parse_target("utils.py::moved_func")
        result, info = move_symbol(tmp_path, target, Path("dest.py"), dry_run=False)

        # Source should import moved_func from dest
        source_content = (tmp_path / "utils.py").read_text()
        assert "from dest import moved_func" in source_content

        # Destination should have the function
        dest_content = (tmp_path / "dest.py").read_text()
        assert "def moved_func" in dest_content
