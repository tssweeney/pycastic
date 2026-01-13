"""Tests for the CLI module."""
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pycastic.cli import app

runner = CliRunner()


@pytest.fixture
def cli_project():
    """Create a project for CLI testing."""
    temp_dir = Path(tempfile.mkdtemp())

    (temp_dir / "module.py").write_text(
        '''"""A module."""


def my_function():
    """A function."""
    return 42


class MyClass:
    """A class."""

    pass
'''
    )

    (temp_dir / "main.py").write_text(
        '''"""Main module."""
from module import my_function, MyClass


def main():
    result = my_function()
    obj = MyClass()
    return result
'''
    )

    # Store original cwd and change to temp_dir so relative paths work
    original_cwd = os.getcwd()
    os.chdir(temp_dir)

    yield temp_dir

    os.chdir(original_cwd)
    shutil.rmtree(temp_dir)


class TestVersionCommand:
    """Tests for --version option."""

    def test_version(self):
        """Test --version shows version."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "pycastic version" in result.stdout


class TestHelpCommand:
    """Tests for help output."""

    def test_help(self):
        """Test --help shows usage info."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Move or rename Python symbols and files" in result.stdout
        assert "Symbol operations" in result.stdout
        assert "File operations" in result.stdout


class TestSymbolRename:
    """Tests for symbol rename operations (same file, new name)."""

    def test_rename_symbol_dry_run(self, cli_project):
        """Test renaming a symbol with --dry-run."""
        result = runner.invoke(
            app,
            ["module.py::my_function", "module.py::new_func", "-n"],
        )
        assert result.exit_code == 0
        assert "Dry Run" in result.stdout

    def test_rename_symbol_executes(self, cli_project):
        """Test rename actually renames."""
        result = runner.invoke(
            app,
            ["module.py::my_function", "module.py::new_func"],
        )
        assert result.exit_code == 0
        assert "Successfully renamed" in result.stdout

        # Verify change
        content = (cli_project / "module.py").read_text()
        assert "def new_func():" in content


class TestSymbolMove:
    """Tests for symbol move operations (different file)."""

    def test_move_symbol_dry_run(self, cli_project):
        """Test moving a symbol with --dry-run."""
        result = runner.invoke(
            app,
            ["module.py::my_function", "main.py", "-n"],
        )
        assert result.exit_code == 0
        assert "Dry Run" in result.stdout

    def test_move_symbol_executes(self, cli_project):
        """Test move actually moves."""
        result = runner.invoke(
            app,
            ["module.py::my_function", "dest.py"],
        )
        assert result.exit_code == 0
        assert "Successfully moved" in result.stdout

        # Verify change
        assert (cli_project / "dest.py").exists()
        dest_content = (cli_project / "dest.py").read_text()
        assert "def my_function():" in dest_content


class TestFileRename:
    """Tests for file rename operations (same directory, new name)."""

    def test_rename_file_dry_run(self, cli_project):
        """Test renaming a file with --dry-run."""
        result = runner.invoke(
            app,
            ["module.py", "utils.py", "-n"],
        )
        assert result.exit_code == 0
        assert "Dry Run" in result.stdout

    def test_rename_file_executes(self, cli_project):
        """Test rename-file actually renames."""
        result = runner.invoke(
            app,
            ["module.py", "utils.py"],
        )
        assert result.exit_code == 0
        assert "Successfully renamed" in result.stdout

        # Verify change
        assert not (cli_project / "module.py").exists()
        assert (cli_project / "utils.py").exists()


class TestFileMove:
    """Tests for file move operations (different directory)."""

    def test_move_file_dry_run(self, cli_project):
        """Test moving a file with --dry-run."""
        (cli_project / "lib").mkdir()
        result = runner.invoke(
            app,
            ["module.py", "lib/", "-n"],
        )
        assert result.exit_code == 0
        assert "Dry Run" in result.stdout

    def test_move_file_executes(self, cli_project):
        """Test move-file actually moves."""
        (cli_project / "lib").mkdir()
        result = runner.invoke(
            app,
            ["module.py", "lib/"],
        )
        assert result.exit_code == 0
        assert "Successfully moved" in result.stdout

        # Verify change
        assert not (cli_project / "module.py").exists()
        assert (cli_project / "lib" / "module.py").exists()


class TestErrorHandling:
    """Tests for error handling in CLI."""

    def test_missing_target(self, cli_project):
        """Test error when target is missing."""
        result = runner.invoke(app, ["module.py::my_function"])
        assert result.exit_code == 1
        assert "Error" in result.stdout

    def test_invalid_symbol_format(self, cli_project):
        """Test error with invalid symbol format for rename."""
        # Source is symbol but target has invalid format (single colon)
        result = runner.invoke(
            app,
            ["module.py::my_function", "module.py:new_func"],
        )
        # Should not be treated as symbol rename (no ::)
        # Will try to move to a file literally named "module.py:new_func"
        # This may fail or succeed depending on filesystem, but exit != 0 if invalid
        # The important thing is it doesn't crash
        assert "Error" in result.stdout or result.exit_code != 0


class TestRootOption:
    """Tests for --root option."""

    def test_explicit_root(self, cli_project):
        """Test using explicit --root option."""
        result = runner.invoke(
            app,
            [
                "--root",
                str(cli_project),
                "module.py::my_function",
                "module.py::new_func",
                "-n",
            ],
        )
        assert result.exit_code == 0
        assert "Dry Run" in result.stdout
