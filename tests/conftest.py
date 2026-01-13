"""Pytest fixtures for pycastic tests."""
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_project():
    """Create a temporary project directory with sample Python files."""
    temp_dir = Path(tempfile.mkdtemp())

    # Create sample Python files
    (temp_dir / "main.py").write_text(
        '''"""Main module."""
from utils import helper_function, MyClass


def main():
    """Main entry point."""
    obj = MyClass()
    result = helper_function(obj.value)
    return result


if __name__ == "__main__":
    main()
'''
    )

    (temp_dir / "utils.py").write_text(
        '''"""Utility module."""


def helper_function(x):
    """A helper function."""
    return x * 2


class MyClass:
    """A sample class."""

    def __init__(self):
        self.value = 42

    def method(self):
        """A method."""
        return helper_function(self.value)
'''
    )

    # Create a subpackage
    subpkg = temp_dir / "subpkg"
    subpkg.mkdir()
    (subpkg / "__init__.py").write_text('"""Subpackage."""\n')
    (subpkg / "module.py").write_text(
        '''"""Subpackage module."""
from utils import MyClass


def create_instance():
    """Create a MyClass instance."""
    return MyClass()
'''
    )

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def simple_project():
    """Create a minimal project with a single file."""
    temp_dir = Path(tempfile.mkdtemp())

    (temp_dir / "example.py").write_text(
        '''"""Example module."""


def old_name():
    """A function to rename."""
    return 42


class OldClass:
    """A class to rename."""

    pass


CONSTANT = "value"
'''
    )

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)
