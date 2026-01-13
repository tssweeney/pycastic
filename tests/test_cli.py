"""Tests for the CLI module."""
import shutil
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pyfactor.cli import app

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

    yield temp_dir

    shutil.rmtree(temp_dir)


class TestVersionCommand:
    """Tests for --version option."""

    def test_version(self):
        """Test --version shows version."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "pyfactor version" in result.stdout


class TestRenameCommand:
    """Tests for rename command."""

    def test_rename_help(self):
        """Test rename --help."""
        result = runner.invoke(app, ["rename", "--help"])
        assert result.exit_code == 0
        assert "Rename a symbol" in result.stdout

    def test_rename_dry_run(self, cli_project):
        """Test rename with --dry-run."""
        result = runner.invoke(
            app,
            ["rename", str(cli_project), "module.py::my_function", "new_func", "-n"],
        )
        assert result.exit_code == 0
        assert "Dry Run" in result.stdout

    def test_rename_executes(self, cli_project):
        """Test rename actually renames."""
        result = runner.invoke(
            app,
            ["rename", str(cli_project), "module.py::my_function", "new_func"],
        )
        assert result.exit_code == 0
        assert "Successfully renamed" in result.stdout

        # Verify change
        content = (cli_project / "module.py").read_text()
        assert "def new_func():" in content

    def test_rename_invalid_target(self, cli_project):
        """Test rename with invalid target format."""
        result = runner.invoke(
            app,
            ["rename", str(cli_project), "invalid", "new_name"],
        )
        assert result.exit_code == 1
        assert "Error" in result.stdout


class TestRenameFileCommand:
    """Tests for rename-file command."""

    def test_rename_file_help(self):
        """Test rename-file --help."""
        result = runner.invoke(app, ["rename-file", "--help"])
        assert result.exit_code == 0
        assert "Rename a Python file" in result.stdout

    def test_rename_file_dry_run(self, cli_project):
        """Test rename-file with --dry-run."""
        result = runner.invoke(
            app,
            ["rename-file", str(cli_project), "module.py", "utils", "-n"],
        )
        assert result.exit_code == 0
        assert "Dry Run" in result.stdout

    def test_rename_file_executes(self, cli_project):
        """Test rename-file actually renames."""
        result = runner.invoke(
            app,
            ["rename-file", str(cli_project), "module.py", "utils"],
        )
        assert result.exit_code == 0
        assert "Successfully renamed file" in result.stdout

        # Verify change
        assert not (cli_project / "module.py").exists()
        assert (cli_project / "utils.py").exists()


class TestMoveCommand:
    """Tests for move command."""

    def test_move_help(self):
        """Test move --help."""
        result = runner.invoke(app, ["move", "--help"])
        assert result.exit_code == 0
        assert "Move symbol(s)" in result.stdout

    def test_move_dry_run(self, cli_project):
        """Test move with --dry-run."""
        result = runner.invoke(
            app,
            ["move", str(cli_project), "module.py::my_function", "main.py", "-n"],
        )
        assert result.exit_code == 0
        assert "Dry Run" in result.stdout


class TestMoveFileCommand:
    """Tests for move-file command."""

    def test_move_file_help(self):
        """Test move-file --help."""
        result = runner.invoke(app, ["move-file", "--help"])
        assert result.exit_code == 0
        assert "Move a Python file" in result.stdout
